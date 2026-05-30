# -*- coding: utf-8 -*-
"""
Stage B 검증 — 채권 듀레이션 가격모델이 실측 ETF와 맞는지 오버랩 구간에서 대조.

모델 가격(=금리변화 기반 price-return) vs 실측 ETF 원가격(price_daily raw close, ex-div).
둘 다 price-only(쿠폰 제외)라 동일 비교. 지표: 월수익 상관, 연환산 추적오차, 구간 CAGR.

실행(서버): python scripts/stage_b_verify.py [TICKER ...]
"""
import sys
from pathlib import Path
import sqlite3
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from modules.bond_model import bond_config, build_bond_price_series

PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"
INDEX_DB = BASE / "data" / "meta" / "index_master.db"

TICKERS = sys.argv[1:] or ["TLT"]


def _load_yield(code):
    c = sqlite3.connect(str(INDEX_DB))
    df = pd.read_sql("SELECT date, close FROM index_daily WHERE code=? ORDER BY date", c, params=(code,))
    c.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float)


def _load_etf(code):
    c = sqlite3.connect(str(PRICE_DB))
    df = pd.read_sql("SELECT date, close FROM price_daily WHERE code=? AND volume>0 ORDER BY date", c, params=(code,))
    c.close()
    if df.empty:
        return pd.Series(dtype=float)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float)


def _cagr(series):
    s = series.dropna()
    if len(s) < 2:
        return float("nan")
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    return (s.iloc[-1] / s.iloc[0]) ** (1.0 / yrs) - 1.0 if yrs > 0 else float("nan")


def check(code):
    cfg = bond_config(code)
    print(f"\n=== {code} (rate={cfg['rate'] if cfg else '?'} dur={cfg['duration'] if cfg else '?'}) ===")
    if not cfg:
        print("  config 없음 — 스킵")
        return
    y = _load_yield(cfg["rate"])
    etf = _load_etf(code)
    if etf.empty:
        print("  실측 ETF 데이터 없음 — 검증 불가 (요청 시 로드됨)")
        return

    # 오버랩
    start = max(y.index.min(), etf.index.min())
    end   = min(y.index.max(), etf.index.max())
    y_o   = y[(y.index >= start) & (y.index <= end)]
    etf_o = etf[(etf.index >= start) & (etf.index <= end)]
    model = build_bond_price_series(y_o, cfg["duration"])

    # 공통 날짜로 정렬
    idx = model.index.intersection(etf_o.index)
    model = model.reindex(idx).ffill()
    actual = etf_o.reindex(idx).ffill()
    print(f"  오버랩: {idx.min().date()} ~ {idx.max().date()} ({len(idx)}일)")

    # 월수익 상관
    mm = model.resample("ME").last().pct_change().dropna()
    aa = actual.resample("ME").last().pct_change().dropna()
    j = mm.index.intersection(aa.index)
    corr = float(np.corrcoef(mm[j], aa[j])[0, 1]) if len(j) > 2 else float("nan")

    # 연환산 추적오차 (일수익 차이 표준편차 × sqrt(252))
    mr = model.pct_change().dropna()
    ar = actual.pct_change().dropna()
    jd = mr.index.intersection(ar.index)
    te = float((mr[jd] - ar[jd]).std() * np.sqrt(252))

    cagr_m, cagr_a = _cagr(model), _cagr(actual)

    # Grade (플랜 임계: 월상관 ≥0.95 A/B, ≥0.85 C; TE ≤3% A/B, ≤8% C; CAGR차 ≤2%/5%)
    cagr_diff = abs(cagr_m - cagr_a)
    if corr >= 0.95 and te <= 0.03 and cagr_diff <= 0.02:
        grade = "A/B"
    elif corr >= 0.85 and te <= 0.08 and cagr_diff <= 0.05:
        grade = "C"
    else:
        grade = "FAIL (임계 미달)"

    print(f"  월수익 상관   : {corr:.3f}   (목표 ≥0.85 C / ≥0.95 A·B)")
    print(f"  연환산 추적오차: {te*100:.2f}%  (목표 ≤8% C / ≤3% A·B)")
    print(f"  CAGR 모델/실측 : {cagr_m*100:.2f}% / {cagr_a*100:.2f}%  (차이 {cagr_diff*100:.2f}%p)")
    print(f"  → Grade: {grade}")


if __name__ == "__main__":
    print("=" * 60)
    print("Stage B 채권 가격모델 검증")
    print("=" * 60)
    for t in TICKERS:
        check(t)
