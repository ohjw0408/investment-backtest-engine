# -*- coding: utf-8 -*-
"""
한국 채권 ETF 종합 검증 — 카테고리당 2~3종.

총수익(TR)을 DB 실데이터로 재구성(yfinance 불필요):
  실TR_return(t) = close수익(t) + 배당(t)/close(t-1)   (분배형·누적형 모두 일관)
모델TR = -dur×Δyield + carry(yield/252 ×book_factor), ×leverage.

C 총수익보존: 월 TR 상관 + CAGR차.   D 유효듀레이션: close수익 ~ -Δyield 회귀.
실행(서버): python scripts/stage_b_verify_kr.py
"""
import sys
from pathlib import Path
import csv
import sqlite3
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from modules.bond_model import (
    _BOND_CATEGORY_CONFIG, _BOND_ETF_CONFIG, COUPON_BOOK_FACTOR, STRIP_DURATION_MULT,
)

PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"
INDEX_DB = BASE / "data" / "meta" / "index_master.db"
KR_ETF = BASE / "data" / "meta" / "kr_etf_list.csv"

REPS = {
    "KR_TREASURY_3Y":   ["114260", "114100", "114820"],
    "KR_TREASURY_10Y":  ["148070", "365780", "471230"],
    "KR_TREASURY_30Y":  ["439870", "471460", "451530"],   # 451530=스트립
    "KR_BOND_AGGREGATE":["273130", "356540", "451540"],
    "KR_CORPORATE":     ["438330", "473290", "0016X0"],   # 473290/0016X0=만기형
    "KR_MONEY_MARKET":  ["459580", "423160", "153130"],   # CD/KOFR/단기채
    "US_TREASURY_30Y":  ["453850", "484790", "458250", "267490"],  # 헤지/스트립/레버리지
}


def _meta():
    m = {}
    with open(KR_ETF, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            m[r["code"]] = r
    return m


META = _meta()


def _yield(code):
    c = sqlite3.connect(str(INDEX_DB))
    df = pd.read_sql("SELECT date, close FROM index_daily WHERE code=? ORDER BY date", c, params=(code,))
    c.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float)


def _real(code):
    c = sqlite3.connect(str(PRICE_DB))
    px = pd.read_sql("SELECT date, close FROM price_daily WHERE code=? AND volume>0 ORDER BY date", c, params=(code,))
    dv = pd.read_sql("SELECT date, dividend FROM corporate_actions WHERE code=? AND dividend>0 ORDER BY date", c, params=(code,))
    c.close()
    if px.empty:
        return None, None
    px["date"] = pd.to_datetime(px["date"]); px = px.set_index("date")["close"].astype(float)
    if not dv.empty:
        dv["date"] = pd.to_datetime(dv["date"]); dv = dv.set_index("date")["dividend"].astype(float)
    else:
        dv = pd.Series(dtype=float)
    return px, dv


def _resolve(code):
    m = META.get(code, {})
    cat = m.get("index"); name = m.get("name", code)
    lev = float(m.get("leverage", 1.0) or 1.0)
    cfg = _BOND_ETF_CONFIG.get(code) or _BOND_CATEGORY_CONFIG.get(cat)
    if not cfg:
        return None
    dur = cfg["duration"]
    if "스트립" in name or "strip" in name.lower():
        dur *= STRIP_DURATION_MULT
    return {"rate": cfg["rate"], "duration": dur, "model": cfg["model"], "lev": lev, "name": name}


def _actual_tr(px, dv):
    ret = px.pct_change().fillna(0.0)
    if not dv.empty:
        d = dv.reindex(px.index).fillna(0.0) / px.shift(1)
        ret = ret + d.fillna(0.0)
    return (1 + ret).cumprod()


def _model_tr(px_index, rate_s, dur, model, lev, hedge_cost=None):
    y = rate_s.reindex(px_index).ffill()
    if model == "carry":
        ret = (y.shift(1) / 100.0 / 252.0) * COUPON_BOOK_FACTOR
    else:
        dy = y.diff() / 100.0
        ret = (-dur) * dy + (y.shift(1) / 100.0 / 252.0) * COUPON_BOOK_FACTOR
    # 환헤지 비용 = 미-한 단기금리차(연율 %)/252 차감 (production build_bond_price_series 동일).
    if hedge_cost is not None:
        ret = ret - hedge_cost.reindex(px_index).ffill().fillna(0.0) / 100.0 / 252.0
    ret = (ret.fillna(0.0) * lev).clip(-0.3, 0.3)
    return (1 + ret).cumprod()


def _corr_m(a, b):
    am = a.resample("ME").last().pct_change().dropna()
    bm = b.resample("ME").last().pct_change().dropna()
    j = am.index.intersection(bm.index)
    return float(np.corrcoef(am[j], bm[j])[0, 1]) if len(j) > 3 else float("nan")


def _cagr(s):
    s = s.dropna()
    if len(s) < 2:
        return float("nan")
    yr = (s.index[-1] - s.index[0]).days / 365.25
    return (s.iloc[-1] / s.iloc[0]) ** (1 / yr) - 1 if yr > 0 else float("nan")


def _eff_dur(px, rate_s):
    ret = px.pct_change()
    dy = rate_s.reindex(px.index).ffill().diff() / 100.0
    df = pd.DataFrame({"r": ret, "d": dy}).dropna()
    df = df[df["d"].abs() > 0]
    if len(df) < 60 or df["d"].var() == 0:
        return None
    return -np.cov(df["r"], df["d"])[0, 1] / np.var(df["d"])


def check(code):
    r = _resolve(code)
    if not r:
        print(f"  {code}: config 없음"); return
    px, dv = _real(code)
    if px is None or len(px) < 120:
        print(f"  {code} [{r['name'][:16]}]: 실데이터 부족"); return
    rate_s = _yield(r["rate"])
    # 환헤지 ETF(hedge="hedge")는 헤지비용(DGS3MO−CD91) 차감 — production과 동일.
    hedge_cost = None
    if META.get(code, {}).get("hedge") == "hedge":
        hedge_cost = _yield("DGS3MO") - _yield("CD91").reindex(_yield("DGS3MO").index).ffill()
    atr = _actual_tr(px, dv)
    mtr = _model_tr(px.index, rate_s, r["duration"], r["model"], r["lev"], hedge_cost=hedge_cost)
    j = atr.index.intersection(mtr.index)
    atr, mtr = atr.reindex(j).ffill(), mtr.reindex(j).ffill()
    c_corr = _corr_m(mtr, atr)
    c_cagr_m, c_cagr_a = _cagr(mtr), _cagr(atr)
    ed = _eff_dur(px, rate_s)
    eds = f"{ed:.1f}" if ed is not None else "—"
    print(f"  {code} [{r['name'][:18]}] dur={r['duration']:.1f} lev={r['lev']:.0f} {r['model']}"
          f" | C: 월TR상관={c_corr:.2f} CAGR 모델/실={c_cagr_m*100:.2f}/{c_cagr_a*100:.2f}%(차{abs(c_cagr_m-c_cagr_a)*100:.2f}p)"
          f" | D실측dur={eds}  n={len(j)}")


def main():
    print("=" * 90)
    print("한국 채권 ETF 종합 검증 (C 총수익보존 · D 듀레이션) — 카테고리당 2~3종")
    print("=" * 90)
    for cat, codes in REPS.items():
        print(f"\n=== {cat} ===")
        for code in codes:
            check(code)


if __name__ == "__main__":
    main()
