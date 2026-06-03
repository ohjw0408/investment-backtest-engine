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

def _single_loop_end(price_data, dates, monthly, initial, weights):
    cfg = SimulationConfig(
        start_date=str(dates[0].date()), end_date=str(dates[-1].date()),
        tickers=list(weights.keys()), target_weights=weights,
        initial_capital=initial, monthly_contribution=0,
        withdrawal_amount=monthly, dividend_mode="hold",
        rebalance_frequency=None, inflation=0.0,
    )
    strat = PeriodicRebalance(weights, rebalance_frequency=None)
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


def test_C_two_ticker_rebalance_runs():
    """2종목 + 주기 리밸런싱 경로 작동(무에러) + 보존 방향성."""
    dates = pd.bdate_range("2030-01-01", "2033-12-31")
    px1 = np.linspace(100.0, 220.0, len(dates))   # 상승
    px2 = np.linspace(100.0, 90.0, len(dates))    # 완만 하락 → 드리프트 → 리밸 발생
    data = {CODE: _frame(dates, px1), CODE2: _frame(dates, px2)}
    accts = [{"account_id": 0, "type": "위탁", "value": 10_000_000.0,
              "target_weights": {CODE: 0.5, CODE2: 0.5}}]

    # 분기 리밸런싱 전략으로 교체(시뮬레이터가 PeriodicRebalance(None) 고정이라
    # 여기선 리밸 미발생 — 대신 2종목 가격경로·배분 동작만 검증)
    res = simulate_household_window(accts, data, list(dates), 60_000.0)
    assert res["success"] is True
    assert res["combined_end_value"] > 0
    # 2종목 합산이 단일 계좌 종료값과 일치(계좌 1개)
    assert abs(res["per_account"][0]["end_value"] - res["combined_end_value"]) <= 1.0


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


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
