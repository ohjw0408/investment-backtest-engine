"""
scripts/build_djdiv_proxy.py

DJ US Dividend 100 proxy chain builder -> index_master.db

Chain (earlier segments scaled to match the later anchor):
  SCHD  (price_daily.db actual,  2011-10-20 ~ present)  <- anchor
  SDY   (yfinance adj close,     2005-11-15 ~ 2011-10-19)
  DVY   (yfinance adj close,     2003-11-07 ~ 2005-11-14)
  ^GSPC (index_master.db,        1928 ~ 2003-11-06)

Dividends are embedded in adj close -> no separate injection needed.
Saved as DJUSDIV_PROXY in index_master.db.

Usage:
  python scripts/build_djdiv_proxy.py
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE_DIR  = Path(__file__).resolve().parent.parent
INDEX_DB  = BASE_DIR / "data" / "meta" / "index_master.db"
PRICE_DB  = BASE_DIR / "data" / "price_cache" / "price_daily.db"

PROXY_CODE = "DJUSDIV_PROXY"


# ------------------------------------------------------------------ loaders

def _fetch_yf(symbol):
    hist = yf.Ticker(symbol).history(period="max", auto_adjust=True)
    if hist.empty:
        raise ValueError(f"yfinance: no data for {symbol}")
    s = hist["Close"].copy()
    s.index = s.index.tz_localize(None).normalize()
    return s.rename(symbol)


def _fetch_price_daily(code):
    conn = sqlite3.connect(str(PRICE_DB))
    df = pd.read_sql(
        "SELECT date, close FROM price_daily WHERE code=? AND volume>0 ORDER BY date",
        conn, params=(code,),
    )
    conn.close()
    if df.empty:
        raise ValueError(f"price_daily.db: no actual data for {code}")
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float).rename(code)


def _fetch_index_db(code):
    conn = sqlite3.connect(str(INDEX_DB))
    df = pd.read_sql(
        "SELECT date, close FROM index_daily WHERE code=? ORDER BY date",
        conn, params=(code,),
    )
    conn.close()
    if df.empty:
        raise ValueError(f"index_master.db: no data for {code}")
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float).rename(code)


# ------------------------------------------------------------------ stitching

def _scale_earlier_to_later(earlier, later):
    """
    Scale `earlier` so its value matches `later` at later.index[0].
    Returns only the portion of earlier that is strictly before later.index[0].
    """
    join_date = later.index[0]

    before = earlier[earlier.index <= join_date]
    if before.empty:
        raise ValueError(f"{earlier.name}: no data on or before {join_date.date()}")
    e_val = float(before.iloc[-1])

    after = later[later.index >= join_date]
    if after.empty:
        raise ValueError(f"{later.name}: empty at join point")
    l_val = float(after.iloc[0])

    if e_val == 0:
        raise ValueError(f"{earlier.name}: zero value at join point {join_date.date()}")

    return (earlier * (l_val / e_val))[earlier.index < join_date]


# ------------------------------------------------------------------ build

def build_chain():
    print("1) SCHD - price_daily.db actual...")
    schd = _fetch_price_daily("SCHD")
    print(f"   {schd.index[0].date()} ~ {schd.index[-1].date()}  ({len(schd):,} rows)")

    print("2) SDY - yfinance...")
    sdy = _fetch_yf("SDY")
    print(f"   {sdy.index[0].date()} ~ {sdy.index[-1].date()}  ({len(sdy):,} rows)")

    print("3) DVY - yfinance...")
    dvy = _fetch_yf("DVY")
    print(f"   {dvy.index[0].date()} ~ {dvy.index[-1].date()}  ({len(dvy):,} rows)")

    print("4) ^GSPC - index_master.db...")
    gspc = _fetch_index_db("^GSPC")
    print(f"   {gspc.index[0].date()} ~ {gspc.index[-1].date()}  ({len(gspc):,} rows)")

    print("\nStitching chain...")

    # Segment 1: SCHD full (anchor)
    seg_schd = schd.copy()
    schd_start = schd.index[0]

    # Segment 2: SDY scaled to SCHD, covering period before SCHD start
    seg_sdy = _scale_earlier_to_later(sdy, schd)
    sdy_start = sdy.index[0]

    # For segment 3 we need sdy fully scaled (including dates before schd start)
    # Re-scale sdy to schd over their overlapping period
    overlap_sdy_schd = sdy[sdy.index >= schd_start]
    if overlap_sdy_schd.empty:
        raise ValueError("SDY and SCHD do not overlap")
    sdy_join_val = float(schd[schd.index >= schd_start].iloc[0])
    sdy_at_join  = float(overlap_sdy_schd.iloc[0])
    sdy_scaled_full = sdy * (sdy_join_val / sdy_at_join)

    # Segment 3: DVY scaled to sdy_scaled_full, covering period before SDY start
    seg_dvy = _scale_earlier_to_later(dvy, sdy_scaled_full)
    dvy_start = dvy.index[0]

    # For segment 4 we need dvy fully scaled
    overlap_dvy_sdy = sdy_scaled_full[sdy_scaled_full.index >= dvy_start]
    if overlap_dvy_sdy.empty:
        raise ValueError("DVY and SDY do not overlap")
    dvy_join_val  = float(overlap_dvy_sdy.iloc[0])
    dvy_at_join   = float(dvy[dvy.index >= dvy_start].iloc[0])
    dvy_scaled_full = dvy * (dvy_join_val / dvy_at_join)

    # Segment 4: ^GSPC scaled to dvy_scaled_full, covering period before DVY start
    seg_gspc = _scale_earlier_to_later(gspc, dvy_scaled_full)

    print(f"  ^GSPC: {seg_gspc.index[0].date()} ~ {seg_gspc.index[-1].date()} ({len(seg_gspc):,} rows)")
    print(f"  DVY:   {seg_dvy.index[0].date()} ~ {seg_dvy.index[-1].date()} ({len(seg_dvy):,} rows)")
    print(f"  SDY:   {seg_sdy.index[0].date()} ~ {seg_sdy.index[-1].date()} ({len(seg_sdy):,} rows)")
    print(f"  SCHD:  {seg_schd.index[0].date()} ~ {seg_schd.index[-1].date()} ({len(seg_schd):,} rows)")

    chain = pd.concat([seg_gspc, seg_dvy, seg_sdy, seg_schd]).sort_index()
    chain = chain[~chain.index.duplicated(keep="last")]
    chain = chain.dropna()
    chain = chain[chain > 0]

    print(f"\n  => chain: {chain.index[0].date()} ~ {chain.index[-1].date()} ({len(chain):,} rows)")
    return chain


# ------------------------------------------------------------------ save

def save_to_db(chain):
    conn = sqlite3.connect(str(INDEX_DB))

    conn.execute("DELETE FROM index_daily WHERE code=?", (PROXY_CODE,))
    conn.execute("DELETE FROM index_meta   WHERE code=?", (PROXY_CODE,))
    conn.commit()

    rows = [
        (PROXY_CODE, d.strftime("%Y-%m-%d"), float(v))
        for d, v in chain.items()
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO index_daily (code, date, close) VALUES (?,?,?)",
        rows,
    )

    conn.execute(
        "INSERT OR REPLACE INTO index_meta (code, source, description, start_date, last_update) "
        "VALUES (?,?,?,?,?)",
        (
            PROXY_CODE,
            "chain:SCHD/SDY/DVY/^GSPC",
            "DJ US Dividend 100 Proxy (SCHD<-SDY<-DVY<-^GSPC)",
            chain.index[0].strftime("%Y-%m-%d"),
            chain.index[-1].strftime("%Y-%m-%d"),
        ),
    )
    conn.commit()
    conn.close()
    print(f"\nSaved: '{PROXY_CODE}' {len(rows):,} rows -> index_master.db")


def verify():
    conn = sqlite3.connect(str(INDEX_DB))
    row = conn.execute(
        "SELECT COUNT(*), MIN(date), MAX(date) FROM index_daily WHERE code=?",
        (PROXY_CODE,),
    ).fetchone()
    conn.close()
    print(f"Verify: {PROXY_CODE}  rows={row[0]:,}  {row[1]} ~ {row[2]}")


# ------------------------------------------------------------------ main

if __name__ == "__main__":
    print("=" * 60)
    print("Building DJUSDIV_PROXY chain")
    print("=" * 60)
    try:
        chain = build_chain()
        save_to_db(chain)
        verify()
        print("Done.")
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
