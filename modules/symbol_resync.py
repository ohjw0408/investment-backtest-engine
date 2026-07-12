"""신규 상장 종목 동기화.

검색 마스터(`symbol_master.db`)는 한 번 빌드된 스냅샷이라, 그 뒤 상장된 종목은
검색에 안 잡힌다. 거래소 현재 상장목록과 대조해 **누락된 신규 종목만** 마스터에
추가한다. 멱등 — 기존 code는 건드리지 않고 신규만 INSERT.

대상 4종:
  - 미국 주식: fdr NASDAQ/NYSE (키 불필요)
  - 미국 ETF: fdr ETF/US (키 불필요, 메타는 code/name뿐 → category NULL 허용)
  - 한국 ETF: fdr ETF/KR (키 불필요, naver Category 번호 → 라벨 매핑,
    이름에서 issuer/leverage/hedge 파생)
  - 한국 주식: KRX 공식 API stk/ksq_bydd_trd (키 필요 — KRX_API_KEY env 또는
    data/meta/krx_api_key.txt. 키 없으면 이 패스만 스킵)

메타 강등 주의: 시드 ETF의 index_name(백필 프록시·IRP 안전자산 enum)은 큐레이션
산물이라 자동추가분엔 없다 → 해당 종목은 백필 없이 실데이터만 사용(정상 강등).
KR ETF category 라벨은 세금분류(_classify_kr_etf_uncached)의 해외 키워드 매칭에
쓰이므로 '해외주식' 라벨이 정확해야 한다.

DB는 git 추적 seed라, 프로드 반영은 이 함수로 갱신 후 커밋→배포 경로로 운반한다.
(GitHub Actions 월간 워크플로 또는 로컬 수동 실행 → 커밋)
"""
import sqlite3
from datetime import datetime, timedelta

import FinanceDataReader as fdr

from config import SYMBOL_DB_PATH

US_MARKETS = ("NASDAQ", "NYSE")

# naver ETF Category 번호 → 라벨 (2026-07-12 실측: 각 번호의 대표 종목명으로 검증)
KR_ETF_CATEGORY = {
    1: "국내시장지수", 2: "국내업종테마", 3: "국내파생",
    4: "해외주식", 5: "원자재", 6: "채권", 7: "혼합자산",
}


def _kr_etf_meta(name: str, cat_no) -> dict:
    """KR ETF 이름/카테고리번호에서 메타 파생 (시드 CSV 큐레이션의 근사치)."""
    category = KR_ETF_CATEGORY.get(int(cat_no) if cat_no is not None else -1)
    issuer = (name.split() or [""])[0]
    if "인버스2X" in name or "곱버스" in name:
        leverage = -2.0
    elif "인버스" in name:
        leverage = -1.0
    elif "레버리지" in name or "2X" in name:
        leverage = 2.0
    else:
        leverage = 1.0
    if "(H)" in name:
        hedge = "hedge"
    elif category in ("해외주식", "원자재"):
        hedge = "unhedged"
    else:
        hedge = "none"
    return {"category": category, "issuer": issuer, "leverage": leverage, "hedge": hedge}


def _iter_us_stocks():
    for mk in US_MARKETS:
        df = fdr.StockListing(mk).rename(columns={"Symbol": "code", "Name": "name"})
        for _, row in df.iterrows():
            yield {"code": str(row.get("code") or "").strip(),
                   "name": str(row.get("name") or "").strip(),
                   "market": mk, "country": "US", "is_etf": 0, "meta": {}}


def _iter_us_etfs():
    df = fdr.StockListing("ETF/US")
    for _, row in df.iterrows():
        yield {"code": str(row.get("Symbol") or "").strip(),
               "name": str(row.get("Name") or "").strip(),
               "market": "US_ETF", "country": "US", "is_etf": 1, "meta": {}}


def _iter_kr_etfs():
    df = fdr.StockListing("ETF/KR")
    for _, row in df.iterrows():
        code = str(row.get("Symbol") or "").strip().zfill(6)
        name = str(row.get("Name") or "").strip()
        yield {"code": code, "name": name, "market": "KRX", "country": "KR",
               "is_etf": 1, "meta": _kr_etf_meta(name, row.get("Category"))}


def _iter_kr_stocks():
    """KRX 공식 API 일별매매 목록 = 그날 거래된 전 상장종목. 키 없으면 raise."""
    from modules.krx.krx_client import KRXClient
    client = KRXClient(debug=False)  # 키 로드 실패 시 FileNotFoundError
    urls = {
        "KOSPI": "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd",
        "KOSDAQ": "https://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd",
    }
    # 최근 영업일 탐색: 주말·휴장일은 빈 응답이라 최대 7일 거슬러 첫 데이터 사용
    for delta in range(7):
        bas_dd = (datetime.today() - timedelta(days=delta)).strftime("%Y%m%d")
        rows_by_market = {}
        for mk, url in urls.items():
            try:
                rows_by_market[mk] = client._extract_rows(client._get(url, {"basDd": bas_dd}))
            except Exception:
                rows_by_market[mk] = []
        if all(rows_by_market.values()):
            break
    for mk, rows in rows_by_market.items():
        for r in rows:
            yield {"code": str(r.get("ISU_CD") or "").strip(),
                   "name": str(r.get("ISU_NM") or "").strip(),
                   "market": mk, "country": "KR", "is_etf": 0, "meta": {}}


def resync_symbols() -> dict:
    """거래소 상장목록과 대조해 마스터에 신규 종목만 추가. 멱등.

    Returns: {"added": int, "codes": [..], "by_market": {mk: n}, "skipped": [..]}
    """
    # ETF 패스를 주식 패스보다 먼저: 양쪽 목록에 겹치는 코드는 is_etf=1이 이겨야 함
    sources = [
        ("KR_ETF", _iter_kr_etfs),
        ("US_ETF", _iter_us_etfs),
        ("KR_STOCK", _iter_kr_stocks),
        ("US_STOCK", _iter_us_stocks),
    ]
    conn = sqlite3.connect(SYMBOL_DB_PATH)
    try:
        existing = {r[0] for r in conn.execute("SELECT code FROM symbols")}
        added, by_market, skipped = [], {}, []
        for label, it in sources:
            n0 = len(added)
            try:
                items = list(it())
            except Exception as e:
                skipped.append(f"{label}: {type(e).__name__}: {e}")
                continue
            for item in items:
                code = item["code"]
                if not code or not item["name"] or code in existing:
                    continue
                m = item["meta"]
                existing.add(code)
                conn.execute(
                    "INSERT INTO symbols (code, name, market, country, is_etf,"
                    " category, issuer, leverage, hedge) VALUES (?,?,?,?,?,?,?,?,?)",
                    (code, item["name"], item["market"], item["country"], item["is_etf"],
                     m.get("category"), m.get("issuer"), m.get("leverage"), m.get("hedge")),
                )
                added.append(code)
            by_market[label] = len(added) - n0
        conn.commit()
        return {"added": len(added), "codes": added, "by_market": by_market,
                "skipped": skipped}
    finally:
        conn.close()


if __name__ == "__main__":
    r = resync_symbols()
    print(f"[resync_symbols] added {r['added']} - {r['by_market']}")
    for s in r["skipped"]:
        print("skipped:", s)
    if r["codes"]:
        print("codes:", ", ".join(r["codes"][:50]) + (" ..." if len(r["codes"]) > 50 else ""))
