"""
update_index_meta.py
1. KS200 description/source 업데이트
2. SCHD 삭제
3. DJUSDIV100 추가 (^DJDVP, 1992년~)
"""
import sys
import sqlite3
import requests
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "meta" / "index_master.db"
conn     = sqlite3.connect(str(DB_PATH))

# ── 1. KS200 meta 업데이트 ────────────────────────────────
conn.execute("""
    UPDATE index_meta
    SET source      = 'ecos',
        description = 'KOSPI Index (ECOS 802Y001)'
    WHERE code = 'KS200'
""")
conn.commit()
print("✅ KS200 meta 업데이트 완료")

# ── 2. SCHD 삭제 ─────────────────────────────────────────
conn.execute("DELETE FROM index_daily WHERE code='SCHD'")
conn.execute("DELETE FROM index_meta  WHERE code='SCHD'")
conn.commit()
print("✅ SCHD 삭제 완료")

# ── 3. DJUSDIV100 추가 (^DJDVP, 1992년~) ─────────────────
print("\n[3] DJUSDIV100 → ^DJDVP (1992년~)")
try:
    t  = yf.Ticker("^DJDVP")
    df = t.history(start="1992-01-01", end="2026-12-31", auto_adjust=True)

    if df.empty:
        print("  ⚠️  ^DJDVP 데이터 없음")
    else:
        df = df.reset_index()
        df["date"]  = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        df["close"] = df["Close"]
        df = df[["date", "close"]].dropna()
        df["code"]  = "DJUSDIV100"

        rows = df[["code", "date", "close"]].values.tolist()
        conn.executemany(
            "INSERT OR IGNORE INTO index_daily (code, date, close) VALUES (?, ?, ?)", rows
        )
        conn.execute("""
            INSERT OR REPLACE INTO index_meta (code, source, description, start_date, last_update)
            VALUES ('DJUSDIV100', 'yfinance', 'DJ US Dividend 100 Index (^DJDVP proxy)', ?, date('now'))
        """, (df["date"].min(),))
        conn.commit()

        row = conn.execute(
            "SELECT MIN(date), MAX(date), COUNT(*) FROM index_daily WHERE code='DJUSDIV100'"
        ).fetchone()
        print(f"  → DJUSDIV100: {row[0]} ~ {row[1]}  ({row[2]:,}행)")

except Exception as e:
    print(f"  ❌ {e}")

# ── 최종 현황 ─────────────────────────────────────────────
print("\n── 최종 index_meta ─────────────────────────────────")
rows = conn.execute("""
    SELECT m.code, m.source, m.description, m.start_date
    FROM index_meta m
    ORDER BY m.start_date
""").fetchall()
for code, source, desc, start in rows:
    print(f"  {code:15s} {str(source):10s} {str(start):12s} {str(desc)[:40]}")

conn.close()