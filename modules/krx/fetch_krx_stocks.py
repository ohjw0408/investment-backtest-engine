"""
한국주식 종목목록 + 일별시세 수집

실행:
  python modules/krx/fetch_krx_stocks.py --list              # 종목 목록 갱신
  python modules/krx/fetch_krx_stocks.py --price             # 오늘 시세
  python modules/krx/fetch_krx_stocks.py --price --date 20260331
  python modules/krx/fetch_krx_stocks.py --all               # 목록 + 오늘 시세
"""

import sys
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

BASE_DIR  = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

META_DIR  = BASE_DIR / "data" / "meta"
CACHE_DIR = BASE_DIR / "data" / "price_cache"
SYMBOL_DB = META_DIR / "symbol_master.db"
PRICE_DB  = CACHE_DIR / "price_daily.db"

from modules.krx.krx_client import KRXClient


def update_stock_list(client):
    print("[종목 목록] KOSPI + KOSDAQ 갱신 중...")
    conn = sqlite3.connect(str(SYMBOL_DB))
    ins = upd = 0

    for market in ["KOSPI", "KOSDAQ"]:
        print(f"  · {market} 조회 중...")
        df = client.get_stock_list(market=market)
        if df.empty:
            print(f"  [WARN] {market} 데이터 없음")
            continue
        for _, row in df.iterrows():
            code = str(row["code"]).zfill(6)
            name = str(row["name"]).strip()
            if not code or not name:
                continue
            exists = conn.execute(
                "SELECT id FROM symbols WHERE code=?", (code,)
            ).fetchone()
            if exists:
                conn.execute(
                    "UPDATE symbols SET name=?, market=?, country='KR' WHERE code=?",
                    (name, market, code)
                )
                upd += 1
            else:
                conn.execute(
                    "INSERT INTO symbols (code, name, market, country, is_etf) VALUES (?,?,?,'KR',0)",
                    (code, name, market)
                )
                ins += 1
        conn.commit()
        print(f"  → {market}: {len(df)}개 처리")

    conn.close()
    print(f"[종목 목록] 완료: {ins}개 추가, {upd}개 갱신")


def update_stock_prices(client, bas_dd=None):
    day = bas_dd or datetime.today().strftime("%Y%m%d")
    print(f"[일별 시세] {day} KOSPI + KOSDAQ 저장 중...")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(PRICE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_daily (
            code TEXT, date TEXT, open REAL, high REAL,
            low REAL, close REAL, volume REAL,
            PRIMARY KEY (code, date)
        )
    """)
    conn.commit()

    total = 0
    for market in ["KOSPI", "KOSDAQ"]:
        print(f"  · {market} 조회 중...")
        df = client.get_stock_price(bas_dd=day, market=market)
        if df.empty:
            print(f"  [WARN] {market} 데이터 없음")
            continue
        rows = []
        for _, r in df.iterrows():
            if r["close"] > 0:
                raw = str(r["date"]).replace("/", "").replace("-", "")
                fmt = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
                rows.append((
                    str(r["code"]).zfill(6), fmt,
                    float(r["open"]), float(r["high"]),
                    float(r["low"]),  float(r["close"]),
                    float(r["volume"]),
                ))
        conn.executemany(
            "INSERT OR REPLACE INTO price_daily (code,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
            rows
        )
        conn.commit()
        total += len(rows)
        print(f"  → {market}: {len(rows)}개 저장")

    conn.close()
    print(f"[일별 시세] 총 {total}개 저장 완료")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list",  action="store_true")
    parser.add_argument("--price", action="store_true")
    parser.add_argument("--date",  type=str, default=None)
    parser.add_argument("--all",   action="store_true")
    args = parser.parse_args()

    client = KRXClient()

    if args.all or args.list:
        update_stock_list(client)
    if args.all or args.price:
        update_stock_prices(client, bas_dd=args.date)
    if not any([args.list, args.price, args.all]):
        parser.print_help()


if __name__ == "__main__":
    main()