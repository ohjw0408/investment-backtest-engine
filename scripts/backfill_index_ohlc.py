"""지수 OHLCV 백필 — 캔들차트용.

index_daily는 종가만 보관(라인 차트·장기 시계열). 캔들은 OHLCV가 필요하므로
시장지수에 한해 yfinance OHLCV를 신규 테이블 index_ohlc에 적재한다.

대상: 시세 캔들이 의미있는 시장지수/선물/FX만 (금리·프록시·종가전용 제외).
KRX_GOLD는 yfinance에 없어 제외 → 캔들 미지원(종가 라인만).

사용: venv\\Scripts\\python.exe scripts\\backfill_index_ohlc.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sqlite3
from pathlib import Path
import pandas as pd
import yfinance as yf

DB = Path(__file__).resolve().parent.parent / "data" / "meta" / "index_master.db"

# 캔들 가능한 시장지수 (yfinance OHLCV 존재)
CODES = [
    "^GSPC", "^IXIC", "^KS11", "^NDX", "^DJI", "^N225",
    "GC=F", "SI=F", "CL=F", "NG=F", "HG=F", "KRW=X",
]


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS index_ohlc (
            code   TEXT,
            date   TEXT,
            open   REAL,
            high   REAL,
            low    REAL,
            close  REAL,
            volume REAL,
            PRIMARY KEY (code, date)
        )
    """)
    conn.commit()


def backfill_one(conn, code):
    raw = yf.download(code, period="max", progress=False,
                      auto_adjust=False, threads=False)
    if raw.empty:
        print(f"  SKIP {code}: yfinance 빈 데이터")
        return 0
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.reset_index()
    rows = []
    for _, r in raw.iterrows():
        d = r["Date"]
        ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        try:
            rows.append((code, ds,
                         float(r["Open"]), float(r["High"]),
                         float(r["Low"]), float(r["Close"]),
                         float(r["Volume"]) if pd.notna(r["Volume"]) else 0.0))
        except (ValueError, TypeError):
            continue
    conn.executemany(
        "INSERT OR REPLACE INTO index_ohlc "
        "(code, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
        rows)
    conn.commit()
    print(f"  {code}: {len(rows)}행 ({rows[0][1]}~{rows[-1][1]})")
    return len(rows)


def main():
    conn = sqlite3.connect(str(DB))
    ensure_table(conn)
    total = 0
    for code in CODES:
        try:
            total += backfill_one(conn, code)
        except Exception as e:
            print(f"  ERR {code}: {e}")
    conn.close()
    print(f"완료 — 총 {total}행")


if __name__ == "__main__":
    main()
