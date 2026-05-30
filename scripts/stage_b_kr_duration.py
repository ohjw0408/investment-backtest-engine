# -*- coding: utf-8 -*-
"""
한국 채권 ETF 유효 듀레이션 실측 — 카테고리별 대표 종목.

유효듀레이션 = -cov(ETF 일수익, Δrate(decimal)) / var(Δrate). 카테고리 rate(KTB/DGS) 사용.
운용사간 듀레이션이 일관되면 카테고리 단일값, 흩어지면 ETF별 필요 → 판단용.
실행(서버): python scripts/stage_b_kr_duration.py
"""
import sys
from pathlib import Path
import sqlite3
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from modules.bond_model import _BOND_CATEGORY_CONFIG

PRICE_DB = BASE / "data" / "price_cache" / "price_daily.db"
INDEX_DB = BASE / "data" / "meta" / "index_master.db"

REPS = {
    "KR_TREASURY_3Y":   ["114260", "114100", "114820", "114470"],
    "KR_TREASURY_10Y":  ["148070", "471230", "365780", "438570"],
    "KR_TREASURY_30Y":  ["385560", "439870", "451530", "471460"],
    "KR_BOND_AGGREGATE":["273130", "356540", "451540", "436140"],
    "KR_CORPORATE":     ["438330", "473290", "0016X0"],
    "US_TREASURY_30Y":  ["453850", "484790", "473330"],
}


def _yield(code):
    c = sqlite3.connect(str(INDEX_DB))
    df = pd.read_sql("SELECT date, close FROM index_daily WHERE code=? ORDER BY date", c, params=(code,))
    c.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float)


def _close(code):
    c = sqlite3.connect(str(PRICE_DB))
    df = pd.read_sql("SELECT date, close FROM price_daily WHERE code=? AND volume>0 ORDER BY date", c, params=(code,))
    c.close()
    if df.empty:
        return pd.Series(dtype=float)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].astype(float)


def eff_duration(code, rate_code):
    px = _close(code)
    y = _yield(rate_code)
    if px.empty or y.empty:
        return None
    ret = px.pct_change()
    dy = y.reindex(px.index).ffill().diff() / 100.0
    df = pd.DataFrame({"ret": ret, "dy": dy}).dropna()
    df = df[df["dy"].abs() > 0]  # 금리 변동 있는 날만
    if len(df) < 60 or df["dy"].var() == 0:
        return {"n": len(df), "dur": None}
    beta = np.cov(df["ret"], df["dy"])[0, 1] / np.var(df["dy"])
    dur = -beta
    # R²
    pred = beta * df["dy"]
    ss_res = ((df["ret"] - pred) ** 2).sum()
    ss_tot = ((df["ret"] - df["ret"].mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"n": len(df), "dur": dur, "r2": r2,
            "from": px.index.min().date(), "to": px.index.max().date()}


def main():
    print("=" * 72)
    print("한국 채권 ETF 유효듀레이션 실측 (카테고리별 운용사 비교)")
    print("=" * 72)
    for cat, codes in REPS.items():
        rate = _BOND_CATEGORY_CONFIG[cat]["rate"]
        cfg_dur = _BOND_CATEGORY_CONFIG[cat]["duration"]
        print(f"\n=== {cat}  (rate={rate}, config_dur={cfg_dur}) ===")
        durs = []
        for code in codes:
            r = eff_duration(code, rate)
            if r is None:
                print(f"  {code}: 데이터 없음")
                continue
            if r.get("dur") is None:
                print(f"  {code}: n={r['n']} 부족")
                continue
            durs.append(r["dur"])
            print(f"  {code}: dur={r['dur']:.2f}  R²={r['r2']:.2f}  n={r['n']}  {r['from']}~{r['to']}")
        if durs:
            durs = np.array(durs)
            print(f"  >> 운용사 범위: {durs.min():.2f} ~ {durs.max():.2f}  (중앙 {np.median(durs):.2f}, 표준편차 {durs.std():.2f})")


if __name__ == "__main__":
    main()
