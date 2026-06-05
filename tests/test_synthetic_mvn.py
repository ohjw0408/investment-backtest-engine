"""
test_synthetic_mvn.py — BUG-SYNTH-CORR 조건부 다변량 합성 검증.

핵심 지표(plan §6.1): 재생성한 합성 prefix의 종목 간 상관이 추정 상관행렬에 부합하는가.
독립 GBM은 합성구간 상관 ≈ 0이었음 → 조건부 다변량은 실종목 등락을 추종해 상관 복원.
"""

import sqlite3
import numpy as np
import pandas as pd
import pytest

from modules.retirement.synthetic_mvn import (
    estimate_joint_stats, generate_joint_window, _nearest_psd_corr,
)


class FakeLoader:
    """price_daily 인메모리 sqlite 기반 최소 loader (get_price + conn)."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE price_daily (code TEXT, date TEXT, open REAL, high REAL, "
            "low REAL, close REAL, volume REAL)"
        )

    def add_series(self, code, dates, closes):
        rows = [(code, d.strftime("%Y-%m-%d"), c, c, c, c, 0.0)
                for d, c in zip(dates, closes)]
        self.conn.executemany(
            "INSERT INTO price_daily VALUES (?,?,?,?,?,?,?)", rows
        )
        self.conn.commit()

    def get_price(self, code, start, end, allow_synthetic=False):
        df = pd.read_sql(
            "SELECT date, open, high, low, close, volume FROM price_daily "
            "WHERE code=? AND date BETWEEN ? AND ? ORDER BY date",
            self.conn, params=(code, start, end),
        )
        return df


def _correlated_series(rho=0.8, n_common=5400, seed=1):
    """공통팩터로 corr≈rho인 두 일일수익 → 가격. AAA 장기, BBB 후상장."""
    rng = np.random.default_rng(seed)
    full_dates = pd.bdate_range("2000-01-01", periods=n_common)
    f  = rng.standard_normal(n_common)
    ea = rng.standard_normal(n_common)
    eb = rng.standard_normal(n_common)
    ra = 0.0003 + 0.010 * (np.sqrt(rho) * f + np.sqrt(1 - rho) * ea)
    rb = 0.0004 + 0.012 * (np.sqrt(rho) * f + np.sqrt(1 - rho) * eb)

    pa = 100.0 * np.cumprod(1 + ra)
    pb = 50.0 * np.cumprod(1 + rb)
    return full_dates, pa, pb


def _build_loader(rho=0.8):
    dates, pa, pb = _correlated_series(rho=rho)
    loader = FakeLoader()
    loader.add_series("AAA", dates, pa)            # 2000~ 전체
    cut = len(dates) // 2                           # BBB는 절반 시점부터 상장
    loader.add_series("BBB", dates[cut:], pb[cut:])
    return loader, dates, cut


def test_nearest_psd_restores_unit_diag():
    bad = np.array([[1.0, 0.9, -0.9], [0.9, 1.0, 0.9], [-0.9, 0.9, 1.0]])
    psd = _nearest_psd_corr(bad)
    vals = np.linalg.eigvalsh(psd)
    assert np.all(vals > -1e-9)                      # PSD
    assert np.allclose(np.diag(psd), 1.0)


def test_estimate_joint_recovers_correlation():
    loader, _, _ = _build_loader(rho=0.8)
    js = estimate_joint_stats(["AAA", "BBB"], loader)
    assert js["ok"]
    i, j = js["order"].index("AAA"), js["order"].index("BBB")
    rho_hat = js["corr"][i, j]
    assert 0.65 < rho_hat < 0.92, f"추정 상관 {rho_hat:.3f}"


def test_estimate_fails_on_insufficient_overlap():
    """겹침<252 → 상관 0 가정(여전히 ok), 표본<252 종목 → ok=False."""
    loader = FakeLoader()
    short = pd.bdate_range("2020-01-01", periods=100)
    loader.add_series("AAA", short, 100 * np.ones(100))
    js = estimate_joint_stats(["AAA"], loader)
    assert js["ok"] is False


def test_conditional_prefix_follows_real_ticker():
    """합성 prefix(BBB)가 실종목(AAA) 등락을 추정 corr대로 추종 → 상관 복원."""
    loader, dates, cut = _build_loader(rho=0.8)
    js = estimate_joint_stats(["AAA", "BBB"], loader)
    assert js["ok"]

    bbb_start = dates[cut]
    win_start = dates[cut // 2]                      # BBB 상장 전부터
    win_end   = dates[cut + 1000]                    # 상장 후까지

    combined, _ = generate_joint_window(
        ["AAA", "BBB"], js, win_start, win_end, loader
    )
    assert "AAA" in combined and "BBB" in combined

    # 합성구간(상장 전) AAA·BBB 일일수익 상관
    pre = pd.bdate_range(win_start, bbb_start - pd.Timedelta(days=1))
    a = combined["AAA"]["close"].reindex(pre).pct_change().dropna()
    b = combined["BBB"]["close"].reindex(pre).pct_change().dropna()
    common = a.index.intersection(b.index)
    corr = np.corrcoef(a.loc[common], b.loc[common])[0, 1]
    assert corr > 0.5, f"합성구간 상관 {corr:.3f} (독립이면 ≈0)"

    # 경계 연속성: 합성 마지막 → 실 첫값 점프 작음
    bbb = combined["BBB"]["close"].dropna()
    pre_last  = bbb[bbb.index < bbb_start].iloc[-1]
    real_first = bbb[bbb.index >= bbb_start].iloc[0]
    jump = real_first / pre_last
    assert 0.5 < jump < 2.0, f"경계 점프 {jump:.3f}"


def test_deterministic():
    loader, dates, cut = _build_loader(rho=0.8)
    js = estimate_joint_stats(["AAA", "BBB"], loader)
    args = (["AAA", "BBB"], js, dates[cut // 2], dates[cut + 500], loader)
    c1, _ = generate_joint_window(*args)
    c2, _ = generate_joint_window(*args)
    assert np.allclose(c1["BBB"]["close"].values, c2["BBB"]["close"].values, equal_nan=True)
