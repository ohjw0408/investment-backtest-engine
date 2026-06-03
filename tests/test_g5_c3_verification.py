"""G5-C C3 강검증: 정합 앵커(A) · 분수 생존율(B) · 배당/성장/리밸 경로(C).

기존 C3 테스트가 평탄가격·단일종목·무배당에 치우쳐 생긴 구멍을 닫는다.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd

from modules.core.portfolio import Portfolio
from modules.config.simulation_config import SimulationConfig
from modules.execution.order_executor import OrderExecutor
from modules.execution.cash_allocator import CashAllocator
from modules.simulation.dividend_engine import DividendEngine
from modules.simulation.contribution_engine import ContributionEngine
from modules.simulation.withdrawal_engine import WithdrawalEngine
from modules.simulation.history_recorder import HistoryRecorder
from modules.simulation.simulation_loop import SimulationLoop
from modules.rebalance.periodic import PeriodicRebalance
from modules.retirement.multi_account_withdrawal import (
    simulate_household_window, analyze_household_withdrawal,
)

CODE = "069500"   # KR_DOMESTIC, CG 비과세
CODE2 = "458730"  # 두 번째 종목(리밸 테스트용)


def _frame(dates, px):
    return pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )


# ════════════════════════════════════════════════════════════════
# A. 정합 앵커: 단일 SimulationLoop == 멀티 1계좌 simulate_household_window
#    (단일 WithdrawalAnalyzer가 워커에서 쓰는 바로 그 엔진과 직접 등치)
# ════════════════════════════════════════════════════════════════

def _strategy(weights, rebal_mode, band_width=0.05):
    freq  = None if rebal_mode in ("none", "band") else rebal_mode
    drift = band_width if rebal_mode == "band" else None
    return PeriodicRebalance(weights, rebalance_frequency=freq, drift_threshold=drift)


def _single_loop_end(price_data, dates, monthly, initial, weights, rebal_mode="none"):
    freq = None if rebal_mode in ("none", "band") else rebal_mode
    cfg = SimulationConfig(
        start_date=str(dates[0].date()), end_date=str(dates[-1].date()),
        tickers=list(weights.keys()), target_weights=weights,
        initial_capital=initial, monthly_contribution=0,
        withdrawal_amount=monthly, dividend_mode="hold",
        rebalance_frequency=freq, inflation=0.0,
    )
    strat = _strategy(weights, rebal_mode)
    pf = Portfolio(initial)
    loop = SimulationLoop(
        DividendEngine(), ContributionEngine(), WithdrawalEngine(),
        OrderExecutor(), CashAllocator(),
    )
    rec = HistoryRecorder()
    loop.run(pf, strat, cfg, price_data, list(dates), rec)
    df = rec.to_dataframe()
    return float(df["portfolio_value"].iloc[-1])


def test_A_single_equals_multi_one_account_growth():
    """성장가격(100→200 램프) 위탁 1계좌 — 단일 SimulationLoop == 멀티 simulate_household_window."""
    dates = pd.bdate_range("2030-01-01", "2033-12-31")
    px = np.linspace(100.0, 200.0, len(dates))
    data = {CODE: _frame(dates, px)}

    single = _single_loop_end(data, dates, 80_000.0, 10_000_000.0, {CODE: 1.0})
    multi = simulate_household_window(
        [{"account_id": 0, "type": "위탁", "value": 10_000_000.0,
          "target_weights": {CODE: 1.0}}],
        data, list(dates), 80_000.0,
    )["combined_end_value"]

    assert abs(single - multi) <= 1.0, f"단일 {single} != 멀티1 {multi}"


def test_A_single_equals_multi_declining_partial_depletion():
    """하락가격(200→60) — 부분 소진 경로에서도 단일 == 멀티1 ±1원."""
    dates = pd.bdate_range("2030-01-01", "2034-12-31")
    px = np.linspace(200.0, 60.0, len(dates))
    data = {CODE: _frame(dates, px)}

    single = _single_loop_end(data, dates, 150_000.0, 12_000_000.0, {CODE: 1.0})
    multi = simulate_household_window(
        [{"account_id": 0, "type": "위탁", "value": 12_000_000.0,
          "target_weights": {CODE: 1.0}}],
        data, list(dates), 150_000.0,
    )["combined_end_value"]

    assert abs(single - multi) <= 1.0, f"단일 {single} != 멀티1 {multi}"


def test_A_single_equals_multi_with_inflation():
    """인플레이션 인출 — 단일(엔진내 인플레) == 멀티(외부 인플레) ±소액."""
    dates = pd.bdate_range("2030-01-01", "2033-12-31")
    px = np.full(len(dates), 100.0)
    data = {CODE: _frame(dates, px)}

    cfg = SimulationConfig(
        start_date="2030-01-01", end_date="2033-12-31", tickers=[CODE],
        target_weights={CODE: 1.0}, initial_capital=10_000_000.0,
        monthly_contribution=0, withdrawal_amount=100_000.0,
        dividend_mode="hold", rebalance_frequency=None, inflation=0.03,
    )
    strat = PeriodicRebalance({CODE: 1.0}, rebalance_frequency=None)
    pf = Portfolio(10_000_000.0)
    loop = SimulationLoop(DividendEngine(), ContributionEngine(),
                          WithdrawalEngine(), OrderExecutor(), CashAllocator())
    rec = HistoryRecorder()
    loop.run(pf, strat, cfg, data, list(dates), rec)
    single = float(rec.to_dataframe()["portfolio_value"].iloc[-1])

    multi = simulate_household_window(
        [{"account_id": 0, "type": "위탁", "value": 10_000_000.0,
          "target_weights": {CODE: 1.0}}],
        data, list(dates), 100_000.0, inflation=0.03,
    )["combined_end_value"]

    # 인플레 적용 타이밍 미세차 허용(±1만원)
    assert abs(single - multi) <= 10_000.0, f"단일 {single} vs 멀티1 {multi}"


# ════════════════════════════════════════════════════════════════
# B. 분수 생존율: 변동 가격경로 → 일부 윈도우 실패 → 0 < 생존율 < 1
# ════════════════════════════════════════════════════════════════

def test_B_fractional_survival_rate():
    """전반 평탄·후반 급락 → 후반 진입 윈도우만 고갈 → 생존율 (0,1) 사이."""
    dates = pd.bdate_range("2010-01-01", "2024-12-31")
    n = len(dates)
    # 전반 50%는 100 평탄, 후반 50%는 100→15 급락
    half = n // 2
    px = np.concatenate([
        np.full(half, 100.0),
        np.linspace(100.0, 15.0, n - half),
    ])
    data = {CODE: _frame(dates, px)}
    accts = [{"account_id": 0, "type": "위탁", "value": 10_000_000.0,
              "target_weights": {CODE: 1.0}}]

    res = analyze_household_withdrawal(
        accts, data, list(dates), "2010-01-01", "2024-12-31",
        withdrawal_years=5, monthly_net=130_000.0, step_months=6,
    )
    sr = res["survival_rate"]
    assert 0.0 < sr < 1.0, f"분수 생존율 아님: {sr} (n_windows={res['n_windows']})"
    assert res["n_windows"] >= 5


# ════════════════════════════════════════════════════════════════
# C. 배당·성장·리밸런싱 경로 (기존 무배당/단일종목 구멍)
# ════════════════════════════════════════════════════════════════

def _div_frame(dates, px, monthly_div):
    df = _frame(dates, px)
    # 매월 1영업일에 배당 지급
    seen = set()
    div = np.zeros(len(dates))
    for i, d in enumerate(dates):
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            div[i] = monthly_div
    df["dividend"] = div
    return df


def test_C_dividend_reinvest_increases_end_value():
    """배당 재투자 경로 작동 — 배당 있는 쪽 종료값이 무배당보다 큼."""
    dates = pd.bdate_range("2030-01-01", "2033-12-31")
    px = np.full(len(dates), 100.0)
    accts = lambda: [{"account_id": 0, "type": "위탁", "value": 10_000_000.0,
                      "target_weights": {CODE: 1.0}}]

    no_div = simulate_household_window(
        accts(), {CODE: _frame(dates, px)}, list(dates), 50_000.0,
        dividend_mode="reinvest",
    )
    with_div = simulate_household_window(
        accts(), {CODE: _div_frame(dates, px, 1.0)}, list(dates), 50_000.0,
        dividend_mode="reinvest",
    )
    assert with_div["combined_end_value"] > no_div["combined_end_value"]


def test_C_two_ticker_rebalance_actually_fires():
    """2종목 발산가격 + 분기 리밸 → 리밸 ON과 OFF 종료값이 달라짐(리밸 실제 발생 증명)."""
    dates = pd.bdate_range("2030-01-01", "2033-12-31")
    px1 = np.linspace(100.0, 220.0, len(dates))   # 상승
    px2 = np.linspace(100.0, 90.0, len(dates))    # 하락 → 비중 발산 → 리밸 매도/매수
    data = {CODE: _frame(dates, px1), CODE2: _frame(dates, px2)}

    def _acct(rebal):
        return [{"account_id": 0, "type": "위탁", "value": 10_000_000.0,
                 "target_weights": {CODE: 0.5, CODE2: 0.5}, "rebal_mode": rebal}]

    none_ = simulate_household_window(_acct("none"), data, list(dates), 60_000.0)
    quart = simulate_household_window(_acct("quarterly"), data, list(dates), 60_000.0)

    # 리밸이 실제로 일어나면 종료값이 무리밸과 달라야 함(발산가격이라 차이 큼)
    assert abs(none_["combined_end_value"] - quart["combined_end_value"]) > 1000.0, (
        f"리밸 미발생 의심 — none {none_['combined_end_value']} == quarterly {quart['combined_end_value']}"
    )


def test_A_single_equals_multi_with_rebalancing():
    """리밸 포함 정합: 2종목 분기 리밸 위탁 — 단일 SimulationLoop == 멀티1 ±1원."""
    dates = pd.bdate_range("2030-01-01", "2033-12-31")
    px1 = np.linspace(100.0, 220.0, len(dates))
    px2 = np.linspace(100.0, 90.0, len(dates))
    data = {CODE: _frame(dates, px1), CODE2: _frame(dates, px2)}
    weights = {CODE: 0.5, CODE2: 0.5}

    single = _single_loop_end(data, dates, 60_000.0, 10_000_000.0, weights,
                              rebal_mode="quarterly")
    multi = simulate_household_window(
        [{"account_id": 0, "type": "위탁", "value": 10_000_000.0,
          "target_weights": weights, "rebal_mode": "quarterly"}],
        data, list(dates), 60_000.0,
    )["combined_end_value"]

    assert abs(single - multi) <= 1.0, f"리밸 정합 위반 — 단일 {single} != 멀티1 {multi}"


def test_A_single_equals_multi_band_rebalancing():
    """밴드 리밸(드리프트 5%) 정합: 단일 == 멀티1 ±1원."""
    dates = pd.bdate_range("2030-01-01", "2033-12-31")
    px1 = np.linspace(100.0, 250.0, len(dates))
    px2 = np.full(len(dates), 100.0)
    data = {CODE: _frame(dates, px1), CODE2: _frame(dates, px2)}
    weights = {CODE: 0.5, CODE2: 0.5}

    single = _single_loop_end(data, dates, 50_000.0, 10_000_000.0, weights,
                              rebal_mode="band")
    multi = simulate_household_window(
        [{"account_id": 0, "type": "위탁", "value": 10_000_000.0,
          "target_weights": weights, "rebal_mode": "band", "band_width": 0.05}],
        data, list(dates), 50_000.0,
    )["combined_end_value"]

    assert abs(single - multi) <= 1.0, f"밴드 리밸 정합 위반 — 단일 {single} != 멀티1 {multi}"


def test_C_growth_outpaces_withdrawal():
    """고성장(100→300) → 인출에도 자산 증가 가능(성장 경로 검증)."""
    dates = pd.bdate_range("2030-01-01", "2035-12-31")
    px = np.linspace(100.0, 300.0, len(dates))
    accts = [{"account_id": 0, "type": "위탁", "value": 10_000_000.0,
              "target_weights": {CODE: 1.0}}]
    res = simulate_household_window(accts, {CODE: _frame(dates, px)},
                                    list(dates), 30_000.0)
    assert res["success"] is True
    # 3배 성장 - 소액 인출 → 종료값이 시작값보다 큼
    assert res["combined_end_value"] > 10_000_000.0


# ════════════════════════════════════════════════════════════════
# D. 합성 보충: 실윈도우 < MIN_CASES_WD(30) → GBM 합성으로 패딩
# ════════════════════════════════════════════════════════════════

def test_D_synthetic_supplements_short_history():
    """짧은 히스토리(실윈도우 소수) → 30개까지 합성 보충, 생존율 (0,1] 산출."""
    from modules.retirement.multi_account_withdrawal import MIN_CASES_WD
    # 7년 데이터, 인출 5년, step 6개월 → 실윈도우 ~4개
    dates = pd.bdate_range("2017-01-01", "2023-12-31")
    rng = np.random.default_rng(7)
    px = 100.0 * np.cumprod(1 + rng.normal(0.0003, 0.01, len(dates)))
    data = {CODE: _frame(dates, px)}
    accts = [{"account_id": 0, "type": "위탁", "value": 10_000_000.0,
              "target_weights": {CODE: 1.0}}]

    res = analyze_household_withdrawal(
        accts, data, list(dates), "2017-01-01", "2023-12-31",
        withdrawal_years=5, monthly_net=120_000.0, step_months=6,
    )
    assert res["n_real"] < MIN_CASES_WD, f"실윈도우 {res['n_real']}"
    assert res["n_synthetic"] > 0
    assert res["n_windows"] == MIN_CASES_WD
    assert 0.0 <= res["survival_rate"] <= 1.0


def test_D_no_synthetic_when_enough_real():
    """긴 히스토리(실윈도우 ≥ 30) → 합성 보충 안 함(n_synthetic=0)."""
    dates = pd.bdate_range("1990-01-01", "2024-12-31")  # 35년
    px = np.full(len(dates), 100.0)
    data = {CODE: _frame(dates, px)}
    accts = [{"account_id": 0, "type": "위탁", "value": 20_000_000.0,
              "target_weights": {CODE: 1.0}}]
    # 인출 5년, step 3개월 → 실윈도우 (30-5)*12/3 = 100+ ≥ 30
    res = analyze_household_withdrawal(
        accts, data, list(dates), "1990-01-01", "2024-12-31",
        withdrawal_years=5, monthly_net=50_000.0, step_months=3,
    )
    assert res["n_real"] >= 30
    assert res["n_synthetic"] == 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
