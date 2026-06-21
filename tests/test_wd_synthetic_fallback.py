"""GAP-RET-KRDATA ③ + race 가드 회귀 (2026-06-11).

① 실윈도우 0개(데이터 < 인출기간) → 하드에러 대신 전량 합성 폴백
   - 멀티: analyze_household_withdrawal (n_real=0, n_synthetic=MIN_CASES_WD)
   - 단일: WithdrawalAnalyzer (cases=MIN_CASES, 전부 is_synthetic)
② 리딩 NaN 가드 — 합집합 달력 reindex+ffill의 빈 머리(NaN)가 초기 매수를 오염시키지 않음
   (라이브 일시 생존율 0% 사고의 재발 방지).
DB 의존 차단 — 합성 가격 주입으로 결정론.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from modules.retirement.multi_account_withdrawal import (
    analyze_household_withdrawal, simulate_household_window, MIN_CASES_WD,
)
from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer, MIN_CASES
from modules.rebalance.periodic import PeriodicRebalance

CODE_A = "458730"
CODE_B = "360750"


def _growth_df(dates, start_price=10000.0, monthly_ret=0.005):
    # 월 0.5% 단조 성장 — 통계 추출 가능(sigma>0 위해 미세 진동 추가).
    n = len(dates)
    rets = np.full(n, monthly_ret / 21)
    rets[::2] += 0.001
    rets[1::2] -= 0.001
    closes = start_price * np.cumprod(1.0 + rets)
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )


def _accounts():
    return [
        {"account_id": 0, "type": "위탁", "value": 300_000_000, "cost_basis": None,
         "target_weights": {CODE_A: 1.0}},
        {"account_id": 1, "type": "연금저축", "value": 200_000_000, "cost_basis": None,
         "target_weights": {CODE_B: 1.0}},
    ]


# ── ① 멀티: 실윈도우 0개 → 전량 합성 폴백 ─────────────────────────
def test_household_zero_real_windows_falls_back_to_synthetic():
    dates = list(pd.bdate_range("2023-01-02", "2026-06-01"))   # 3.4년 < 인출 30년
    price_data = {CODE_A: _growth_df(dates), CODE_B: _growth_df(dates, 12000.0)}

    report = analyze_household_withdrawal(
        _accounts(), price_data, dates, dates[0], dates[-1],
        withdrawal_years=30, monthly_net=2_000_000,
    )
    assert report["n_real"] == 0
    assert report["n_synthetic"] == MIN_CASES_WD
    assert 0.0 <= report["survival_rate"] <= 1.0
    assert np.isfinite(report["combined_end_value"]["p50"])
    assert len(report["per_account"]) == 2


# ── ① 단일: 실윈도우 0개 → 전량 합성 폴백 ─────────────────────────
class _FakePriceLoader:
    def __init__(self, data, dates):
        self._d = (data, dates)
    def load(self, tickers, start, end, allow_synthetic=False):
        return self._d


class _FakeEngine:
    def __init__(self, data, dates):
        self.price_loader = _FakePriceLoader(data, dates)


def test_single_zero_real_windows_falls_back_to_synthetic():
    dates = list(pd.bdate_range("2023-01-02", "2026-06-01"))
    price_data = {CODE_A: _growth_df(dates)}
    engine = _FakeEngine(price_data, dates)

    analyzer = WithdrawalAnalyzer(
        portfolio_engine   = engine,
        tickers            = [CODE_A],
        strategy_factory   = lambda: PeriodicRebalance({CODE_A: 1.0}, rebalance_frequency=None),
        data_start         = "2023-01-02",
        data_end           = "2026-06-01",
        withdrawal_years   = 30,
        monthly_withdrawal = 2_000_000,
        initial_capital    = 300_000_000,
    )
    result = analyzer.run()
    assert result["n_real"] == 0
    assert result["n_synthetic"] == MIN_CASES
    assert len(result["cases"]) == MIN_CASES
    assert all(c["is_synthetic"] for c in result["cases"])
    assert 0.0 <= result["success_rate"] <= 1.0


# ── ② 리딩 NaN 가드 — 부분 데이터로 초기 매수 금지 ────────────────
def test_window_with_leading_nan_does_not_poison_portfolio():
    dates = list(pd.bdate_range("2010-01-04", "2026-06-01"))
    df_a = _growth_df(dates)
    df_b = _growth_df(dates, 12000.0)
    # B는 2013년부터만 데이터 — 합집합 달력 reindex 후 머리 3년 NaN (PriceDataLoader 동형).
    cutoff = pd.Timestamp("2013-01-02")
    df_b.loc[df_b.index < cutoff,
             ["open", "high", "low", "close", "volume"]] = np.nan

    res = simulate_household_window(
        _accounts(), {CODE_A: df_a, CODE_B: df_b}, dates, 1_000_000,
    )
    assert np.isfinite(res["combined_end_value"])
    assert res["combined_end_value"] > 0
    for acct in res["per_account"]:
        assert np.isfinite(acct["end_value"])
        assert acct["end_value"] >= 0
