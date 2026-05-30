# -*- coding: utf-8 -*-
"""
Stage B 전수 검증 — 채권 가격모델·쿠폰·총수익보존·시변듀레이션을 config 전 종목에 대해.

A. 가격모델 정확도 : 모델 price-return vs 실측 close(price-only) — 월상관/TE/CAGR
B. 쿠폰 정확성     : 모델 연쿠폰yield(=DGS yield) vs 실측 분배yield(실 배당/가격)
C. 총수익 보존     : model_TR(price + carry) vs 실측 adj-close(total-return) — 월상관/CAGR차
D. 시변 듀레이션   : 실측 일수익을 -Δyield에 1년 롤링 회귀 → 유효듀레이션 범위 vs config 고정값

실측 데이터 없는 종목은 yfinance로 먼저 로드(PriceLoader.get_price).
실행(서버): python scripts/stage_b_full_verify.py [TICKER ...]
"""
import sys
from pathlib import Path
import sqlite3
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from modules.bond_model import _BOND_ETF_CONFIG, build_bond_price_series

PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"
INDEX_DB = BASE / "data" / "meta" / "index_master.db"
TICKERS = sys.argv[1:] or list(_BOND_ETF_CONFIG.keys())


def _load_yield(code):
    c = sqlite3.connect(str(INDEX_DB))
    df = pd.read_sql("SELECT date, close FROM index_daily WHERE code=? ORDER BY date", c, params=(code,))
    c.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float)


def _ensure_loaded(code):
    """실측 데이터 없으면 PriceLoader로 로드 (yfinance fetch + DB 저장)."""
    c = sqlite3.connect(str(PRICE_DB))
    n = c.execute("SELECT COUNT(*) FROM price_daily WHERE code=? AND volume>0", (code,)).fetchone()[0]
    c.close()
    if n > 0:
        return
    try:
        from modules.portfolio_engine import PortfolioEngine
        pe = PortfolioEngine()
        pe.loader.get_price(code, "1990-01-01", "2026-12-31", allow_synthetic=False)
    except Exception as e:
        print(f"  [{code}] 로드 실패: {e}")


def _load_close(code):
    c = sqlite3.connect(str(PRICE_DB))
    df = pd.read_sql("SELECT date, close FROM price_daily WHERE code=? AND volume>0 ORDER BY date", c, params=(code,))
    c.close()
    if df.empty:
        return pd.Series(dtype=float)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float)


def _load_actual_div(code):
    c = sqlite3.connect(str(PRICE_DB))
    df = pd.read_sql(
        "SELECT date, dividend FROM corporate_actions WHERE code=? AND dividend>0 ORDER BY date", c, params=(code,))
    c.close()
    if df.empty:
        return pd.Series(dtype=float)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["dividend"].astype(float)


def _yf_total_return(code):
    """yfinance auto_adjust=True adj-close = 배당 재투자 총수익."""
    try:
        import yfinance as yf
        h = yf.Ticker(code).history(period="max", auto_adjust=True)
        if h.empty:
            return pd.Series(dtype=float)
        s = h["Close"].copy(); s.index = s.index.tz_localize(None).normalize()
        return s.astype(float)
    except Exception as e:
        print(f"  [{code}] yfinance TR 실패: {e}")
        return pd.Series(dtype=float)


def _cagr(s):
    s = s.dropna()
    if len(s) < 2:
        return float("nan")
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    return (s.iloc[-1] / s.iloc[0]) ** (1.0 / yrs) - 1.0 if yrs > 0 else float("nan")


def _corr_monthly(a, b):
    am = a.resample("ME").last().pct_change().dropna()
    bm = b.resample("ME").last().pct_change().dropna()
    j = am.index.intersection(bm.index)
    return float(np.corrcoef(am[j], bm[j])[0, 1]) if len(j) > 2 else float("nan")


def check(code):
    cfg = _BOND_ETF_CONFIG.get(code)
    print(f"\n=== {code}  (rate={cfg['rate']}  config_dur={cfg['duration']}) ===")
    _ensure_loaded(code)
    y = _load_yield(cfg["rate"])
    close = _load_close(code)
    if close.empty:
        print("  실측 데이터 없음 — 스킵")
        return
    start, end = max(y.index.min(), close.index.min()), min(y.index.max(), close.index.max())
    y_o = y[(y.index >= start) & (y.index <= end)]
    close_o = close[(close.index >= start) & (close.index <= end)]
    idx = close_o.index.intersection(build_bond_price_series(y_o, cfg["duration"]).index)
    if len(idx) < 250:
        print(f"  오버랩 부족({len(idx)}일) — 스킵")
        return
    dur = cfg["duration"]
    model_px = build_bond_price_series(y_o, dur).reindex(idx).ffill()
    actual_px = close_o.reindex(idx).ffill()
    print(f"  오버랩: {idx.min().date()} ~ {idx.max().date()} ({len(idx)}일)")

    # A. 가격모델
    corr = _corr_monthly(model_px, actual_px)
    mr, ar = model_px.pct_change().dropna(), actual_px.pct_change().dropna()
    jd = mr.index.intersection(ar.index)
    te = float((mr[jd] - ar[jd]).std() * np.sqrt(252))
    print(f"  [A 가격] 월상관={corr:.3f}  TE={te*100:.2f}%  CAGR 모델/실측={_cagr(model_px)*100:.2f}%/{_cagr(actual_px)*100:.2f}%")

    # B. 쿠폰 정확성
    div = _load_actual_div(code)
    div_o = div[(div.index >= start) & (div.index <= end)]
    model_cyield = float((y_o / 100.0).mean())  # 모델 연쿠폰yield ≈ 평균 DGS
    if not div_o.empty:
        yr_div = div_o.groupby(div_o.index.year).sum()
        yr_px = actual_px.groupby(actual_px.index.year).mean()
        cj = yr_div.index.intersection(yr_px.index)
        actual_cyield = float((yr_div[cj] / yr_px[cj]).mean())
        print(f"  [B 쿠폰] 모델yield={model_cyield*100:.2f}%  실측분배yield={actual_cyield*100:.2f}%  비={model_cyield/actual_cyield:.2f}x")
    else:
        print(f"  [B 쿠폰] 모델yield={model_cyield*100:.2f}%  실측 분배 데이터 없음")

    # C. 총수익 보존
    tr = _yf_total_return(code)
    if not tr.empty:
        tr_o = tr[(tr.index >= idx.min()) & (tr.index <= idx.max())]
        # model TR = price-return + carry(y/252)
        dy = y_o.reindex(idx).ffill().diff().fillna(0.0) / 100.0
        yv = (y_o.reindex(idx).ffill() / 100.0).shift(1).fillna(method="bfill")
        model_tr_ret = (-dur * dy + yv / 252.0).clip(-0.10, 0.10)
        model_tr = (1 + model_tr_ret).cumprod()
        ti = model_tr.index.intersection(tr_o.index)
        if len(ti) > 250:
            corr_tr = _corr_monthly(model_tr.reindex(ti), tr_o.reindex(ti))
            print(f"  [C 총수익] 월상관={corr_tr:.3f}  CAGR 모델/실측={_cagr(model_tr.reindex(ti))*100:.2f}%/{_cagr(tr_o.reindex(ti))*100:.2f}%  차={abs(_cagr(model_tr.reindex(ti))-_cagr(tr_o.reindex(ti)))*100:.2f}%p")
        else:
            print("  [C 총수익] TR 오버랩 부족")
    else:
        print("  [C 총수익] yfinance TR 없음")

    # D. 시변 듀레이션 (1년 롤링: actual_ret ≈ -beta*Δy)
    dy_all = (y_o.reindex(idx).ffill().diff() / 100.0)
    ret_all = actual_px.pct_change()
    df = pd.DataFrame({"ret": ret_all, "dy": dy_all}).dropna()
    betas = []
    for _, w in df.groupby(df.index.year):
        if len(w) > 60 and w["dy"].var() > 0:
            betas.append(-np.cov(w["ret"], w["dy"])[0, 1] / np.var(w["dy"]))
    if betas:
        betas = np.array(betas)
        print(f"  [D 듀레이션] 실측 유효듀레이션 연도별: 최소{betas.min():.1f} 중앙{np.median(betas):.1f} 최대{betas.max():.1f}  (config={dur})")


if __name__ == "__main__":
    print("=" * 70)
    print("Stage B 전수 검증 (A 가격 · B 쿠폰 · C 총수익보존 · D 시변듀레이션)")
    print("=" * 70)
    for t in TICKERS:
        check(t)
