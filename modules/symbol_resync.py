"""신규 상장 종목 동기화.

검색 마스터(`symbol_master.db`)는 한 번 빌드된 스냅샷이라, 그 뒤 상장된 종목은
검색에 안 잡힌다. 거래소 현재 상장목록(FinanceDataReader)과 대조해 **누락된 신규
종목만** 마스터에 추가한다. 멱등 — 기존 code는 건드리지 않고 신규만 INSERT.

대상: 미국 주식(NASDAQ/NYSE). ETF/KRX는 별도 소스라 제외.
가격 이력은 종목별 on-demand 백필(backfill_engine)이 처리하므로 여기선 메타데이터만.

DB는 git 추적 seed라, 프로드 반영은 이 함수로 갱신 후 커밋→배포 경로로 운반한다.
(GitHub Actions 월간 워크플로 또는 로컬 수동 실행 → 커밋)
"""
import sqlite3
import FinanceDataReader as fdr

from config import SYMBOL_DB_PATH

US_MARKETS = ("NASDAQ", "NYSE")


def resync_symbols() -> dict:
    """거래소 상장목록과 대조해 마스터에 신규 US 종목만 추가. 멱등.

    Returns: {"added": int, "codes": [..], "by_market": {mk: n}}
    """
    conn = sqlite3.connect(SYMBOL_DB_PATH)
    try:
        existing = {r[0] for r in conn.execute("SELECT code FROM symbols")}
        added, by_market = [], {}
        for mk in US_MARKETS:
            df = fdr.StockListing(mk).rename(columns={"Symbol": "code", "Name": "name"})
            n0 = len(added)
            for _, row in df.iterrows():
                code = str(row.get("code") or "").strip()
                if not code or code in existing:
                    continue
                name = str(row.get("name") or "").strip()
                existing.add(code)
                conn.execute(
                    "INSERT INTO symbols (code, name, market, country, is_etf) "
                    "VALUES (?, ?, ?, 'US', 0)",
                    (code, name, mk),
                )
                added.append(code)
            by_market[mk] = len(added) - n0
        conn.commit()
        return {"added": len(added), "codes": added, "by_market": by_market}
    finally:
        conn.close()


if __name__ == "__main__":
    r = resync_symbols()
    print(f"[resync_symbols] added {r['added']} — {r['by_market']}")
    if r["codes"]:
        print("codes:", ", ".join(r["codes"][:50]) + (" …" if len(r["codes"]) > 50 else ""))
