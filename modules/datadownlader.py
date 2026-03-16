"""
get_ecos_data.py
────────────────────────────────────────────────────────────────────────────────
한국은행 ECOS API로 데이터 가져오기

USD/KRW: 731Y001 (원/달러 환율, 1964년~)
KS200:   802Y001 (KOSPI200, 1990년~)
────────────────────────────────────────────────────────────────────────────────
"""

import sys
import sqlite3
import requests
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd

ECOS_API_KEY = "FRBWDOA2XRL1E33R2681"
BASE_DIR     = Path(__file__).resolve().parent.parent
DB_PATH      = BASE_DIR / "data" / "meta" / "index_master.db"
BASE_URL     = "https://ecos.bok.or.kr/api"

conn = sqlite3.connect(str(DB_PATH))

def fetch_ecos(stat_code, item_code1, cycle, start, end):
    """
    ECOS API StatisticSearch 호출
    cycle: D(일), M(월), Q(분기), A(연)
    start/end: YYYYMMDD 또는 YYYYMM
    """
    # 최대 100000건씩 페이지네이션
    all_rows = []
    offset = 1
    batch = 10000

    while True:
        url = (
            f"{BASE_URL}/StatisticSearch/{ECOS_API_KEY}/json/kr"
            f"/{offset}/{offset + batch - 1}"
            f"/{stat_code}/{cycle}/{start}/{end}/{item_code1}"
        )
        resp = requests.get(url, timeout=30)
        data = resp.json()

        if "StatisticSearch" not in data:
            err = data.get("RESULT", {})
            print(f"    ECOS 오류: {err}")
            break

        rows = data["StatisticSearch"].get("row", [])
        if not rows:
            break

        all_rows.extend(rows)
        total = int(data["StatisticSearch"].get("list_total_count", 0))

        if offset + batch > total:
            break
        offset += batch

    return all_rows

def save(code, df):
    df = df.copy()
    df["code"] = code
    rows = df[["code", "date", "close"]].dropna().values.tolist()
    conn.executemany(
        "INSERT OR IGNORE INTO index_daily (code, date, close) VALUES (?, ?, ?)",
        rows
    )
    conn.commit()

def delete_code(code):
    conn.execute("DELETE FROM index_daily WHERE code=?", (code,))
    conn.commit()

def print_range(code):
    row = conn.execute(
        "SELECT MIN(date), MAX(date), COUNT(*) FROM index_daily WHERE code=?",
        (code,)
    ).fetchone()
    print(f"  → {code}: {row[0]} ~ {row[1]}  ({row[2]:,}행)")

print("=" * 65)
print("한국은행 ECOS API 데이터 수집")
print("=" * 65)

# ── 1. USD/KRW 환율 (731Y001, 1964년~) ───────────────────
print("\n[1/2] USD/KRW → ECOS 731Y001 원/달러 환율 (일별, 1964년~)")
try:
    # 먼저 통계 탐색
    url = f"{BASE_URL}/StatisticSearch/{ECOS_API_KEY}/json/kr/1/5/731Y001/D/19640101/20261231/0000001"
    resp = requests.get(url, timeout=30)
    data = resp.json()
    print(f"  API 응답 확인: {list(data.keys())}")

    if "StatisticSearch" in data:
        sample = data["StatisticSearch"].get("row", [])[:3]
        for s in sample:
            print(f"    샘플: {s}")

    rows = fetch_ecos("731Y001", "0000001", "D", "19640101", "20261231")
    if rows:
        df = pd.DataFrame(rows)
        print(f"  컬럼: {df.columns.tolist()}")
        print(f"  샘플:\n{df.head(3).to_string()}")

        # 날짜/값 컬럼 찾기
        date_col  = "TIME" if "TIME" in df.columns else df.columns[0]
        value_col = "DATA_VALUE" if "DATA_VALUE" in df.columns else df.columns[-1]

        df["date"]  = pd.to_datetime(df[date_col], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
        df["close"] = pd.to_numeric(df[value_col], errors="coerce")
        df = df[["date", "close"]].dropna()

        print(f"  범위: {df['date'].min()} ~ {df['date'].max()} ({len(df):,}행)")
        avg = df[df["date"] >= "2020-01-01"]["close"].mean()
        print(f"  2020년 이후 평균: {avg:.1f} (1000~1500이면 정상)")

        delete_code("USD/KRW")
        save("USD/KRW", df)
        print_range("USD/KRW")
    else:
        print("  ⚠️  데이터 없음 - item_code 확인 필요")

        # item_code 탐색
        url2 = f"{BASE_URL}/StatisticItemList/{ECOS_API_KEY}/json/kr/1/20/731Y001"
        resp2 = requests.get(url2, timeout=30)
        data2 = resp2.json()
        print(f"  731Y001 항목 목록:")
        for item in data2.get("StatisticItemList", {}).get("row", [])[:10]:
            print(f"    {item}")

except Exception as e:
    print(f"  ❌ {e}")
    import traceback
    traceback.print_exc()

# ── 2. KOSPI200 (802Y001, 1990년~) ───────────────────────
print("\n[2/2] KS200 → ECOS 802Y001 KOSPI200 (일별, 1990년~)")
try:
    # 항목 탐색
    url = f"{BASE_URL}/StatisticItemList/{ECOS_API_KEY}/json/kr/1/20/802Y001"
    resp = requests.get(url, timeout=30)
    data = resp.json()
    print(f"  802Y001 항목 목록:")
    for item in data.get("StatisticItemList", {}).get("row", [])[:10]:
        print(f"    {item}")

    # KOSPI200 항목코드 찾기
    rows_meta = data.get("StatisticItemList", {}).get("row", [])
    kospi200_code = None
    for item in rows_meta:
        name = str(item.get("ITEM_NAME1", ""))
        if "200" in name or "KOSPI200" in name.upper():
            kospi200_code = item.get("ITEM_CODE1", "")
            print(f"  KOSPI200 코드 발견: {kospi200_code} ({name})")
            break

    if kospi200_code:
        rows = fetch_ecos("802Y001", kospi200_code, "D", "19900101", "20261231")
        if rows:
            df = pd.DataFrame(rows)
            date_col  = "TIME" if "TIME" in df.columns else df.columns[0]
            value_col = "DATA_VALUE" if "DATA_VALUE" in df.columns else df.columns[-1]

            df["date"]  = pd.to_datetime(df[date_col], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
            df["close"] = pd.to_numeric(df[value_col], errors="coerce")
            df = df[["date", "close"]].dropna()

            print(f"  범위: {df['date'].min()} ~ {df['date'].max()} ({len(df):,}행)")
            delete_code("KS200")
            save("KS200", df)
            print_range("KS200")
    else:
        print("  ⚠️  KOSPI200 항목코드 못 찾음")

except Exception as e:
    print(f"  ❌ {e}")
    import traceback
    traceback.print_exc()

conn.close()