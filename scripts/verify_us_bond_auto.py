# -*- coding: utf-8 -*-
"""
US 채권 ETF 자동분류(classify_us_bond_etf) end-to-end 검증.

yfinance 총수익(auto_adjust=close=adj) vs 분류기 config 모델TR 비교.
모델TR = -dur×Δyield + carry(yield/252 ×book_factor)  (stage_b_verify_kr와 동일).
rate: 국채 DGS*, 회사채 DBAA — index_master.

판정: 월TR상관(shape) + CAGR차(level). Grade C 목표 ≤ ~1.5p.
실행: python scripts/verify_us_bond_auto.py
"""
import sys
from pathlib import Path
import sqlite3
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from modules.bond_model import classify_us_bond_etf, COUPON_BOOK_FACTOR

INDEX_DB = BASE / "data" / "meta" / "index_master.db"

# (ticker, 정식명) — 자동분류 대상 다양화: 회사채 만기별 + 국채 만기별 + 광범위본드
TARGETS = [
    ("LQD",  "iShares iBoxx $ Investment Grade Corporate Bond ETF"),
    ("VCIT", "Vanguard Intermediate-Term Corporate Bond ETF"),
    ("VCSH", "Vanguard Short-Term Corporate Bond ETF"),
    ("VCLT", "Vanguard Long-Term Corporate Bond ETF"),
    ("TLH",  "iShares 10-20 Year Treasury Bond ETF"),
    ("IEI",  "iShares 3-7 Year Treasury Bond ETF"),
    ("SHY",  "iShares 1-3 Year Treasury Bond ETF"),
    ("BND",  "Vanguard Total Bond Market ETF"),
    ("BSV",  "Vanguard Short-Term Bond ETF"),
    ("BIV",  "Vanguard Intermediate-Term Bond ETF"),
    ("BLV",  "Vanguard Long-Term Bond ETF"),
]


def _yield(code):
    c = sqlite3.connect(str(INDEX_DB))
    df = pd.read_sql("SELECT date, close FROM index_daily WHERE code=? ORDER BY date", c, params=(code,))
    c.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float)


def _model_tr(idx, rate_s, dur):
    y = rate_s.reindex(idx).ffill()
    dy = y.diff() / 100.0
    ret = (-dur) * dy + (y.shift(1) / 100.0 / 252.0) * COUPON_BOOK_FACTOR
    return (1 + ret.fillna(0.0)).cumprod()


def _cagr(s):
    s = s.dropna()
    yr = (s.index[-1] - s.index[0]).days / 365.25
    return (s.iloc[-1] / s.iloc[0]) ** (1 / yr) - 1 if yr > 0 else float("nan")


def _corr_m(a, b):
    am = a.resample("ME").last().pct_change().dropna()
    bm = b.resample("ME").last().pct_change().dropna()
    j = am.index.intersection(bm.index)
    return float(np.corrcoef(am[j], bm[j])[0, 1]) if len(j) > 3 else float("nan")


def main():
    import yfinance as yf
    print("=" * 92)
    print("US 채권 ETF 자동분류 검증 (yfinance 총수익 vs 분류기 모델)")
    print("=" * 92)
    for tk, nm in TARGETS:
        cfg = classify_us_bond_etf(nm)
        if not cfg:
            print(f"  {tk}: 분류 안 됨(스킵) — {nm}")
            continue
        try:
            df = yf.download(tk, period="max", auto_adjust=True, progress=False)
            atr = df["Close"].dropna()
            if isinstance(atr, pd.DataFrame):
                atr = atr.iloc[:, 0]
            atr.index = pd.to_datetime(atr.index)
        except Exception as e:
            print(f"  {tk}: yf 실패 {e}")
            continue
        if len(atr) < 250:
            print(f"  {tk}: 데이터 부족 {len(atr)}")
            continue
        rate_s = _yield(cfg["rate"])
        mtr = _model_tr(atr.index, rate_s, cfg["duration"])
        j = atr.index.intersection(mtr.index)
        a, m = atr.reindex(j).ffill(), mtr.reindex(j).ffill()
        ca, cm = _cagr(a), _cagr(m)
        print(f"  {tk:5s} [{cfg['rate']:5s} dur={cfg['duration']:.1f}] "
              f"월TR상관={_corr_m(m, a):.2f}  CAGR 모델/실={cm*100:5.2f}/{ca*100:5.2f}% "
              f"(차{abs(cm-ca)*100:.2f}p)  n={len(j)}  | {nm[:34]}")


if __name__ == "__main__":
    main()
