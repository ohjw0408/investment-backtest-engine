# -*- coding: utf-8 -*-
"""읽기전용 prod 데이터 진단 — 배포 시 Actions 로그로 prod의 가격/배당/백필/프록시 상태 출력.

데이터를 일절 변경하지 않는다(SELECT만). 인출 시뮬 배당커버리지 0% 원인 규명용.
실행: venv/bin/python scripts/diag_prod_data.py
"""
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"
INDEX_DB = BASE / "data" / "meta" / "index_master.db"

CODES = sys.argv[1:] or ["SPY", "QQQ", "SCHD", "VOO", "JEPI", "TLT"]
SEP = "=" * 70


def q1(conn, sql, args=()):
    try:
        return conn.execute(sql, args).fetchone()
    except Exception as e:
        return ("ERR", str(e)[:60])


def main():
    print(SEP)
    print("PROD DATA DIAGNOSTIC (read-only)")
    print("PRICE_DB:", PRICE_DB, "exists:", PRICE_DB.exists())
    print("INDEX_DB:", INDEX_DB, "exists:", INDEX_DB.exists())
    print(SEP)

    pc = sqlite3.connect(str(PRICE_DB))
    # 테이블 존재
    tbls = [r[0] for r in pc.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("price_daily tables:", tbls)
    print(SEP)

    for code in CODES:
        real_start = q1(pc, "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,))
        bf = q1(pc, "SELECT COUNT(*), MIN(date), MAX(date) FROM price_daily WHERE code=? AND volume=0", (code,))
        div = q1(pc, "SELECT COUNT(*), MIN(date), MAX(date) FROM corporate_actions WHERE code=? AND dividend>0", (code,))
        # 백필 구간(실시작 이전) 배당
        rs = real_start[0] if isinstance(real_start, tuple) and real_start and not str(real_start[0]).startswith('ERR') else real_start
        predv = q1(pc, "SELECT COUNT(*) FROM corporate_actions WHERE code=? AND dividend>0 AND date<?",
                   (code, rs if rs else "0000")) if rs else "(no real_start)"
        print(f"[{code}] real_start={rs}")
        print(f"      backfill(vol=0) rows={bf}")
        print(f"      dividends(all)={div}")
        print(f"      dividends pre-real={predv}")
    print(SEP)

    # 프록시 / yield 테이블
    if INDEX_DB.exists():
        ic = sqlite3.connect(str(INDEX_DB))
        itbls = [r[0] for r in ic.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print("index_master tables:", itbls)
        for px in ("DJUSDIV_PROXY", "DJUSDIV100"):
            print(f"  index_daily {px}:",
                  q1(ic, "SELECT COUNT(*), MIN(date), MAX(date) FROM index_daily WHERE code=?", (px,)))
        if "index_div_yield" in itbls:
            print("  index_div_yield DJUSDIV100:",
                  q1(ic, "SELECT COUNT(*) FROM index_div_yield WHERE index_code=?", ("DJUSDIV100",)))
        else:
            print("  index_div_yield table MISSING")
    print(SEP)
    print("DONE")


if __name__ == "__main__":
    main()
