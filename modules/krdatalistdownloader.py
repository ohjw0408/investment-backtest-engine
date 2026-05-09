"""
fetch_kr_stocks.py
────────────────────────────────────────────────────────────────────────────────
KRX API로 코스피/코스닥 전종목 받아서 symbol_master.db에 추가
실행: python fetch_kr_stocks.py
────────────────────────────────────────────────────────────────────────────────
"""

import sys
import sqlite3
import requests
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent
if not (ROOT / "modules").exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

DB_PATH      = ROOT / "data" / "meta" / "symbol_master.db"
KRX_KEY_PATH = ROOT / "data" / "meta" / "krx_api_key.txt"

HEADERS = {
    "AUTH_KEY":   KRX_KEY_PATH.read_text().strip(),
    "User-Agent": "Mozilla/5.0",
}


def recent_bizdays(n=5):
    """최근 n개 영업일 목록 (최신 → 과거)"""
    days = []
    d = datetime.today()
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return days


def fetch_listing(url, bas_dd, debug=False):
    r = requests.get(url, headers=HEADERS, params={"basDd": bas_dd}, timeout=30)
    if debug:
        print(f"  RAW RESPONSE ({len(r.text)}자): {r.text[:300]}")
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []
    rows = (data.get("OutBlock_1")
            or data.get("output")
            or data.get("result")
            or data.get("data")
            or [])
    return rows


def main():
    conn = sqlite3.connect(str(DB_PATH))
    inserted = skipped = 0

    markets = [
        ("KOSPI",  "https://data-dbg.krx.co.kr/svc/apis/sto/stk_isu_base_info"),
        ("KOSDAQ", "https://data-dbg.krx.co.kr/svc/apis/sto/ksq_isu_base_info"),
    ]

    bizdays = recent_bizdays(5)
    print(f"시도할 날짜: {bizdays}\n")

    for market, url in markets:
        print(f"{'='*50}")
        print(f"{market} 조회 중...")

        rows = []
        for bas_dd in bizdays:
            r = requests.get(url, headers=HEADERS, params={"basDd": bas_dd}, timeout=30)
            print(f"  {bas_dd} → STATUS {r.status_code}  응답길이: {len(r.text)}자")
            print(f"  응답 미리보기: {r.text[:200]}")

            if r.status_code == 200 and len(r.text) > 10:
                try:
                    data  = r.json()
                    rows  = (data.get("OutBlock_1") or data.get("output")
                             or data.get("result") or data.get("data") or [])
                    if rows:
                        print(f"  → 데이터 {len(rows)}개 수신 (기준일: {bas_dd})")
                        print(f"  → 필드: {list(rows[0].keys())[:6]}")
                        break
                    else:
                        print(f"  → JSON은 왔지만 rows 없음. 키: {list(data.keys())}")
                except Exception as e:
                    print(f"  → JSON 파싱 실패: {e}")
            print()

        if not rows:
            print(f"  ❌ {market} 데이터 수신 실패\n")
            continue

        for row in rows:
            code = str(row.get("ISU_SRT_CD", "")).strip()
            name = str(row.get("ISU_ABBRV", "") or row.get("ISU_NM", "")).strip()

            if not code or not name or len(code) != 6:
                continue

            exists = conn.execute("SELECT 1 FROM symbols WHERE code=?", (code,)).fetchone()
            if exists:
                skipped += 1
                continue

            conn.execute(
                "INSERT INTO symbols (code, name, market, country, is_etf) VALUES (?,?,?,?,?)",
                (code, name, market, "KR", 0)
            )
            inserted += 1

        conn.commit()
        print(f"  ✅ 추가: {inserted}개\n")

    conn.close()
    print(f"완료: 신규 {inserted:,}개 / 이미 있음 {skipped:,}개")


if __name__ == "__main__":
    main()