# -*- coding: utf-8 -*-
"""
한국 금리 시계열 수집 (ECOS 시장금리 일별 817Y002) → index_master.db index_daily.

채권 Stage B 한국 확장용 — 국고채/CD/KOFR/회사채. 단위 = % (DGS와 동일).
키: 환경변수 ECOS_API_KEY 또는 data/meta/ecos_api_key.txt.

실행: python scripts/fetch_kr_rates.py [CODE ...]   (인자 없으면 전체)
"""
import os
import sys
from pathlib import Path
import sqlite3

import requests
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
INDEX_DB = BASE / "data" / "meta" / "index_master.db"
META_DIR = BASE / "data" / "meta"
ECOS_STAT = "817Y002"   # 시장금리(일별)

# index_master 코드 ← ECOS ITEM_CODE
KR_RATE_SERIES = {
    "KTB1Y":     "010190000",   # 국고채 1년
    "KTB2Y":     "010195000",   # 국고채 2년
    "KTB3Y":     "010200000",   # 국고채 3년
    "KTB10Y":    "010210000",   # 국고채 10년
    "KTB20Y":    "010220000",   # 국고채 20년
    "KTB30Y":    "010230000",   # 국고채 30년
    "CD91":      "010502000",   # CD 91일
    "KOFR":      "010901000",   # KOFR (익일물 RFR)
    "CORPAA3Y":  "010300000",   # 회사채 3년 AA-
    "CORPBBB3Y": "010320000",   # 회사채 3년 BBB-
}


def _load_key() -> str:
    key = os.environ.get("ECOS_API_KEY", "")
    if key:
        return key
    p = META_DIR / "ecos_api_key.txt"
    return p.read_text().strip() if p.exists() else ""


def fetch_series(key, item_code, start="19900101", end="20261231"):
    offset, batch, all_rows = 1, 10000, []
    while True:
        url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/"
               f"{offset}/{offset+batch-1}/{ECOS_STAT}/D/{start}/{end}/{item_code}")
        d = requests.get(url, timeout=30).json().get("StatisticSearch", {})
        rows = d.get("row", [])
        if not rows:
            break
        all_rows.extend(rows)
        total = int(d.get("list_total_count", 0))
        if offset + batch > total:
            break
        offset += batch
    return all_rows


def main():
    key = _load_key()
    if not key:
        print("ECOS 키 없음 (ECOS_API_KEY 또는 data/meta/ecos_api_key.txt)")
        sys.exit(1)

    codes = sys.argv[1:] or list(KR_RATE_SERIES.keys())
    conn = sqlite3.connect(str(INDEX_DB))
    print("=" * 60)
    print("한국 금리 수집 (ECOS 817Y002) → index_master")
    print("=" * 60)
    for code in codes:
        item = KR_RATE_SERIES.get(code)
        if not item:
            print(f"[{code}] 매핑 없음 — 스킵")
            continue
        rows = fetch_series(key, item)
        if not rows:
            print(f"[{code}] 데이터 없음")
            continue
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["TIME"], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
        df["close"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
        df = df[["date", "close"]].dropna()
        conn.executemany(
            "INSERT OR IGNORE INTO index_daily (code, date, close) VALUES (?,?,?)",
            [(code, d, c) for d, c in df.values.tolist()],
        )
        conn.execute(
            "INSERT OR REPLACE INTO index_meta (code, source, description, start_date, last_update) "
            "VALUES (?,?,?,?,?)",
            (code, f"ecos:{ECOS_STAT}/{item}", f"ECOS 시장금리 {code}",
             df["date"].min(), df["date"].max()),
        )
        conn.commit()
        print(f"[{code}] {len(df)}행  {df['date'].min()} ~ {df['date'].max()}")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
