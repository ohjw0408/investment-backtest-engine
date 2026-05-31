# -*- coding: utf-8 -*-
"""
미국 회사채 yield 시계열 수집 (FRED) → index_master.db index_daily.

US 채권 ETF 자동백필(Stage B)용 — IG 회사채 캐리/듀레이션 모델의 rate 소스.
단위 = % (DGS와 동일).

- DBAA: Moody's Seasoned Baa Corporate Bond Yield (1986~, 일별). IG 회사채 프록시.
  (ICE BofA BAMLC0A0CMEY는 FRED 라이선스로 최근 3년만 제공 → 백필 불가하여 DBAA 사용.)
- HY(고수익채)는 장기 무료 yield 소스 부재 → 미수집(분류기에서 안전스킵).

키: data/meta/fred_api_key.txt (FRED API key).
실행: python scripts/fetch_us_credit_rates.py
"""
import sys
from pathlib import Path
import sqlite3

import requests
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
INDEX_DB = BASE / "data" / "meta" / "index_master.db"
KEY_FILE = BASE / "data" / "meta" / "fred_api_key.txt"

# index_master 코드 ← FRED series_id (동일하게 유지)
US_CREDIT_SERIES = {
    "DBAA": "DBAA",   # Moody's Baa 회사채 yield (IG 프록시)
}


def fetch_series(key, series_id, start="1980-01-01"):
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={key}&file_type=json"
           f"&observation_start={start}")
    obs = requests.get(url, timeout=30).json().get("observations", [])
    return [(o["date"], o["value"]) for o in obs if o["value"] not in (".", "")]


def main():
    if not KEY_FILE.exists():
        print("FRED 키 없음 (data/meta/fred_api_key.txt)")
        sys.exit(1)
    key = KEY_FILE.read_text().strip()

    conn = sqlite3.connect(str(INDEX_DB))
    print("=" * 60)
    print("미국 회사채 yield 수집 (FRED) → index_master")
    print("=" * 60)
    for code, sid in US_CREDIT_SERIES.items():
        rows = fetch_series(key, sid)
        if not rows:
            print(f"[{code}] 데이터 없음")
            continue
        df = pd.DataFrame(rows, columns=["date", "close"])
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna()
        conn.executemany(
            "INSERT OR IGNORE INTO index_daily (code, date, close) VALUES (?,?,?)",
            [(code, d, c) for d, c in df.values.tolist()],
        )
        conn.execute(
            "INSERT OR REPLACE INTO index_meta (code, source, description, start_date, last_update) "
            "VALUES (?,?,?,?,?)",
            (code, f"fred:{sid}", f"FRED {code} 회사채 yield",
             df["date"].min(), df["date"].max()),
        )
        conn.commit()
        print(f"[{code}] {len(df)}행  {df['date'].min()} ~ {df['date'].max()}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
