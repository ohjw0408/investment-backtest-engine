"""
tests/test_g5_backtest_multi.py
G5-A L10: 백테스트 단일윈도우 멀티계좌 검증 (결정론 픽스처, ±1원).

- 정상 손계산/골든: 1계좌 멀티경로 = 기존 TaxableSimulationRunner ±1원.
- 불변식: combined end_value = Σ account end_value.
- 경계/노이즈0: 평탄가격·거치 → 수익 0(end=초기, total_return 0).
- 세금 ON/OFF: 양쪽 관통.

price_loader.load를 결정론 가격으로 패치해 _run_multi_account_backtest_logic 직접 구동.
"""
import os
import sys
from contextlib import contextmanager

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import backtest_logic
from modules.config.simulation_config   import SimulationConfig
from modules.rebalance.periodic          import PeriodicRebalance
from modules.simulation.taxable_runner   import TaxableSimulationRunner
from modules.tax.base_tax                import TaxEngine

KRF = "458730"  # KR_FOREIGN
KRD = "069500"  # KR_DOMESTIC


def _df(px: np.ndarray, dates) -> pd.DataFrame:
    return pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )


@contextmanager
def _patched_prices(price_data: dict, dates: list):
    """portfolio_engine.price_loader.load를 결정론 데이터로 임시 교체."""
    eng  = backtest_logic._get_portfolio_engine()
    orig = eng.price_loader.load
    eng.price_loader.load = lambda tickers, s, e: (
        {t: price_data[t] for t in tickers if t in price_data}, dates
    )
    try:
        yield
    finally:
        eng.price_loader.load = orig


def test_l10_single_account_matches_runner():
    """골든: 1계좌(위탁) 멀티경로 종료값 = 기존 TaxableSimulationRunner ±1원 (세금 ON)."""
    dates = pd.bdate_range("2018-01-01", "2022-12-31")
    n     = len(dates)
    px    = np.where(np.arange(n) < n // 2, 100.0, 200.0)  # 계단 상승
    pdata = {KRF: _df(px, dates)}

    body = {
        "accounts": [{
            "type": "위탁", "initial_capital": 10_000_000, "monthly_contribution": 0,
            "tickers": [{"code": KRF, "weight": 1.0}], "rebal_mode": "none",
            "dividend_mode": "hold",
        }],
        "start_date": "2018-01-01", "end_date": "2022-12-31",
        "tax_enabled": True, "user_settings": {"earned_income": 0, "age": 40},
        "dividend_mode": "hold",
    }
    with _patched_prices(pdata, list(dates)):
        res = backtest_logic._run_multi_account_backtest_logic(body)
    multi_end = res["metrics"]["end_value"]

    cfg = SimulationConfig(
        start_date="2018-01-01", end_date="2022-12-31", tickers=[KRF],
        target_weights={KRF: 1.0}, initial_capital=10_000_000.0,
        monthly_contribution=0.0, withdrawal_amount=0, dividend_mode="hold",
        rebalance_frequency=None, inflation=0.0,
    )
    strat = PeriodicRebalance({KRF: 1.0}, rebalance_frequency=None)
    r = TaxableSimulationRunner().run(
        cfg, pdata, list(dates), strat, tax_enabled=True, account_type="위탁",
        tax_engine=TaxEngine({"earned_income": 0, "age": 40}),
        user_settings={"earned_income": 0, "age": 40},
    )
    assert abs(multi_end - round(r.end_value)) <= 1, f"멀티 {multi_end} vs Runner {round(r.end_value)}"


def test_l10_combined_equals_sum_and_no_growth():
    """불변식 combined=Σaccounts + 평탄가격·거치 → 수익0(end=초기합, total_return 0). 세금 OFF."""
    dates = pd.bdate_range("2018-01-01", "2019-12-31")
    px    = np.full(len(dates), 100.0)  # 평탄
    pdata = {KRF: _df(px, dates), KRD: _df(px, dates)}

    body = {
        "accounts": [
            {"type": "위탁", "initial_capital": 5_000_000, "monthly_contribution": 0,
             "tickers": [{"code": KRF, "weight": 1.0}], "rebal_mode": "none", "dividend_mode": "hold"},
            {"type": "위탁", "initial_capital": 3_000_000, "monthly_contribution": 0,
             "tickers": [{"code": KRD, "weight": 1.0}], "rebal_mode": "none", "dividend_mode": "hold"},
        ],
        "start_date": "2018-01-01", "end_date": "2019-12-31",
        "tax_enabled": False, "user_settings": {}, "dividend_mode": "hold",
    }
    with _patched_prices(pdata, list(dates)):
        res = backtest_logic._run_multi_account_backtest_logic(body)

    # 불변식: combined = Σ account end_value
    assert res["metrics"]["end_value"] == sum(a["end_value"] for a in res["accounts"])
    # 평탄가격·거치·세금OFF → 수익 0 → 종료값 = 초기 합(8,000,000)
    assert abs(res["metrics"]["end_value"] - 8_000_000) <= 1
    assert abs(res["metrics"]["total_return"]) < 1e-6


def test_l10_tax_reduces_end_value():
    """세금 ON/OFF: 상승분 실현(리밸런싱) 위탁에 양도세 → ON 종료값 < OFF."""
    dates = pd.bdate_range("2018-01-01", "2022-12-31")
    n     = len(dates)
    px    = np.where(np.arange(n) < n // 2, 100.0, 200.0)
    pdata = {KRF: _df(px, dates)}
    base  = {
        "accounts": [{
            "type": "위탁", "initial_capital": 10_000_000, "monthly_contribution": 0,
            "tickers": [{"code": KRF, "weight": 1.0}], "rebal_mode": "none", "dividend_mode": "hold",
        }],
        "start_date": "2018-01-01", "end_date": "2022-12-31", "dividend_mode": "hold",
    }
    with _patched_prices(pdata, list(dates)):
        off = backtest_logic._run_multi_account_backtest_logic(
            {**base, "tax_enabled": False, "user_settings": {}})
        on = backtest_logic._run_multi_account_backtest_logic(
            {**base, "tax_enabled": True, "user_settings": {"earned_income": 0, "age": 40}})
    # 위탁 KR_FOREIGN 청산세(미실현차익 15.4%) → ON < OFF
    assert on["metrics"]["end_value"] < off["metrics"]["end_value"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
