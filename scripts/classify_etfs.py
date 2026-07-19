# -*- coding: utf-8 -*-
"""symbol_master.db ETF 분류 실행 — 스키마 보장 + KR/US 전 종목 UPDATE.

US는 data/meta/us_etf_categories.csv(수집분)를 소스로 쓰며, 파일이 없거나
일부만 있어도 있는 만큼 + 이름규칙으로 분류한다(재실행 안전 — 멱등).
"""
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import SYMBOL_DB_PATH  # noqa: E402
from modules.etf_classifier import CLS_COLS, classify_kr, classify_us  # noqa: E402

US_CSV = ROOT / "data" / "meta" / "us_etf_categories.csv"


def ensure_schema(conn):
    have = {r[1] for r in conn.execute("PRAGMA table_info(symbols)")}
    for col in CLS_COLS:
        if col not in have:
            conn.execute(f"ALTER TABLE symbols ADD COLUMN {col} TEXT")
    conn.commit()


def load_us_categories():
    """code → (category, family). family는 검색 랭킹(주요 운용사 우선)에 씀."""
    cats = {}
    if US_CSV.exists():
        with open(US_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status") == "ok" and row.get("category"):
                    cats[row["code"]] = (row["category"], (row.get("family") or "").strip())
    return cats


def main():
    conn = sqlite3.connect(str(SYMBOL_DB_PATH))
    ensure_schema(conn)
    set_sql = ", ".join(f"{c}=?" for c in CLS_COLS)

    # ---- KR ----
    kr = conn.execute("SELECT code, name, index_name, category FROM symbols "
                      "WHERE is_etf=1 AND country='KR'").fetchall()
    for code, name, index_name, category in kr:
        out = classify_kr(name, index_name, category)
        conn.execute(f"UPDATE symbols SET {set_sql} WHERE code=? AND country='KR'",
                     tuple(out[c] for c in CLS_COLS) + (code,))
    print(f"KR classified: {len(kr)}")

    # ---- US ----
    # US 레버리지는 이름규칙 산출물뿐(시드가 NULL) → 매 실행 전체 재산출(멱등)
    us_cats = load_us_categories()
    us = conn.execute("SELECT code, name FROM symbols "
                      "WHERE is_etf=1 AND country!='KR'").fetchall()
    n_yf = 0
    for code, name in us:
        cat, family = us_cats.get(code, (None, ""))
        out, name_lev = classify_us(name, cat)
        if out["cls_src"] == "yf":
            n_yf += 1
        conn.execute(f"UPDATE symbols SET {set_sql}, leverage=? "
                     "WHERE code=? AND country!='KR'",
                     tuple(out[c] for c in CLS_COLS) + (name_lev, code))
        if family:   # US issuer 시드는 NULL — yfinance fundFamily로 채움(랭킹용)
            conn.execute("UPDATE symbols SET issuer=? WHERE code=? AND country!='KR'",
                         (family, code))
    print(f"US classified: {len(us)} (yf_category={n_yf}, csv_rows={len(us_cats)})")

    conn.commit()

    # ---- 분포 리포트 ----
    for country in ("KR", "US"):
        cc = "='KR'" if country == "KR" else "!='KR'"
        print(f"\n[{country}] asset_class:")
        for r in conn.execute(f"SELECT asset_class, COUNT(*) FROM symbols "
                              f"WHERE is_etf=1 AND country{cc} GROUP BY 1 ORDER BY 2 DESC"):
            print("  ", r)
        print(f"[{country}] region:")
        for r in conn.execute(f"SELECT region, COUNT(*) FROM symbols "
                              f"WHERE is_etf=1 AND country{cc} GROUP BY 1 ORDER BY 2 DESC"):
            print("  ", r)
        print(f"[{country}] bond bond_type/bond_dur:")
        for r in conn.execute(f"SELECT bond_type, bond_dur, COUNT(*) FROM symbols "
                              f"WHERE is_etf=1 AND country{cc} AND asset_class='bond' "
                              f"GROUP BY 1,2 ORDER BY 3 DESC LIMIT 15"):
            print("  ", r)
    conn.close()


if __name__ == "__main__":
    main()
