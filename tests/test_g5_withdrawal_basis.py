"""
tests/test_g5_withdrawal_basis.py
G5-C C1 (L12-① 일부): 적립 취득가 인계 → 위탁 인출 매도세 정확.

은퇴는 적립 무청산 인계 → 인출하면서 과세. 인출 시뮬은 적립 종료자산(gross)을
initial_capital로 받으므로, carried_cost_basis(=적립 총납입)를 넘겨 day-1 매수 직후
avg_cost를 비례 축소해야 위탁 인출 매도가 적립차익까지 양도세 과세한다.

손계산(평탄가격·정수 주수):
- gross 12,000,000 / 취득가 6,000,000 → 내재차익 6,000,000 (전부 KR_FOREIGN).
- 평탄가격 100 → 120,000주, avg_cost 축소 100→50.
- 인출 100,000/월 × 24월 = 2,400,000 인출(24,000주 매도, 차익 1,200,000).
- 잔여 96,000주는 인출종료 청산(차익 4,800,000).
- 전 차익 6,000,000 결국 실현 → 양도세 6,000,000 × 15.4% = 924,000.
- carried 미전달(취득가=현재가)이면 차익 0 → 양도세 0.
∴ end(basis 미전달) − end(basis 600만) == 924,000.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.config.simulation_config import SimulationConfig
from modules.rebalance.periodic import PeriodicRebalance
from modules.simulation.taxable_runner import TaxableSimulationRunner
from modules.tax.base_tax import TaxEngine

KRF = "458730"  # KR_FOREIGN 15.4%


def _flat_df(dates, price=100.0):
    px = np.full(len(dates), float(price))
    return pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )


def _run(carried, withdrawal):
    dates = pd.bdate_range("2020-01-01", "2021-12-31")
    df    = _flat_df(dates)
    cfg = SimulationConfig(
        start_date="2020-01-01", end_date="2021-12-31", tickers=[KRF],
        target_weights={KRF: 1.0}, initial_capital=12_000_000.0,
        monthly_contribution=0.0, withdrawal_amount=withdrawal, dividend_mode="hold",
        rebalance_frequency=None, inflation=0.0,
    )
    us = {"earned_income": 0, "age": 40}
    return TaxableSimulationRunner().run(
        cfg, {KRF: df}, list(dates),
        PeriodicRebalance({KRF: 1.0}, rebalance_frequency=None),
        tax_enabled=True, account_type="위탁",
        tax_engine=TaxEngine(us), user_settings=us,
        carried_cost_basis=carried,
    ).end_value


def test_c1_carried_basis_taxes_accumulation_gain_exact():
    """손계산 ±1원(인출0·거치, confound 없음): 취득가 인계 시 적립차익이 실현(종료청산)되어
    양도세 부과. gross 12M·취득가 6M → 내재차익 6M × 15.4% = 924,000.
    avg_cost 재조정이 종료 청산(apply_liquidation_tax의 unrealized_gain)에 반영됨을 검증."""
    e_no_basis = _run(None,        withdrawal=0)   # 취득가=현재가 → 차익0 → 세금0 → 12,000,000
    e_carried  = _run(6_000_000,   withdrawal=0)   # 내재차익 600만 과세
    assert abs(e_no_basis - 12_000_000) <= 2, f"무취득가 거치 종료값 {e_no_basis}"
    assert abs((e_no_basis - e_carried) - 924_000) <= 2, \
        f"적립차익 양도세 손계산 위반: diff={e_no_basis - e_carried} (기대 924,000)"


def test_c1_withdrawal_path_taxes_accumulation_gain():
    """인출 매도 경로(BUG-TAX-2 sell_with_tax)도 취득가 인계로 적립차익 과세 → 인출 시뮬
    종료값이 무취득가보다 작다(인출하며 판 위탁 매도차익에 양도세)."""
    e_no_basis = _run(None,      withdrawal=100_000)
    e_carried  = _run(6_000_000, withdrawal=100_000)
    assert e_carried < e_no_basis - 1, \
        f"인출 매도세 미부과: carried {e_carried} >= no_basis {e_no_basis}"


def test_c1_accumulation_loss_no_phantom_tax():
    """경계: 적립 손실(취득가 > gross) → 미실현 손실 → 위탁 양도세 0(허위과세 없음)."""
    e_none = _run(None,        withdrawal=0)   # 12,000,000
    e_loss = _run(15_000_000,  withdrawal=0)   # 취득가 15M > gross 12M → 손실 → 세금0
    assert abs(e_loss - e_none) <= 2, f"적립손실인데 과세됨: diff={e_none - e_loss}"


def test_c1_run_wd_case_delivers_cost_basis():
    """플러밍: 인출 워커 _run_wd_case가 config_dict['cost_basis']를 runner까지 전달.
    (RetirementPlanner→WithdrawalAnalyzer→config_dict→_run_wd_case→runner 체인의
    하류 절반 — 키 오타 등 전달 누락 검출.) 인출0·평탄 → 종료청산이 적립차익 과세."""
    import modules.retirement.withdrawal_analyzer as wa_mod
    dates = pd.bdate_range("2020-01-01", "2021-12-31")
    df    = _flat_df(dates)
    wa_mod._w_price_data = {KRF: df}
    wa_mod._w_dates      = list(dates)
    us = {"earned_income": 0, "age": 40}

    def _cfg(basis):
        return {
            "tickers": [KRF], "initial_capital": 12_000_000, "withdrawal_amount": 0,
            "dividend_mode": "hold", "inflation": 0.0, "tax_enabled": True,
            "account_type": "위탁", "user_settings": us, "gain_harvesting": False,
            "cost_basis": basis,
        }
    strat = {"target_weights": {KRF: 1.0}, "rebalance_frequency": None, "drift_threshold": None}

    r_none = wa_mod._run_wd_case(("2020-01-01", "2021-12-31", _cfg(None),       strat, 1))
    r_carr = wa_mod._run_wd_case(("2020-01-01", "2021-12-31", _cfg(6_000_000),  strat, 2))
    assert r_none is not None and r_carr is not None
    diff = r_none["tax_end_value"] - r_carr["tax_end_value"]
    assert abs(diff - 924_000) <= 2, f"cost_basis 전달 누락? diff={diff} (기대 924,000)"


def test_c1c2_planner_forwards_cost_basis_and_tax(monkeypatch):
    """플러밍 상류: RetirementPlanner가 cost_basis·tax_engine·account_type을
    WithdrawalAnalyzer에 전달(wd_config 경유). 인출 과세 배선(C1/C2) 전달 검출."""
    import modules.retirement.retirement_planner as rp_mod
    captured = {}

    class _StubWA:
        def __init__(self, **kw):
            captured.update(kw)
        def run(self):
            return {"success_rate": 1.0,
                    "distribution": {"end_value_ratio": {"p50": 1.0}},
                    "cases": [{"end_value_ratio": 1.0}]}

    monkeypatch.setattr(rp_mod, "WithdrawalAnalyzer", _StubWA)
    te = TaxEngine({"age": 60})
    planner = rp_mod.RetirementPlanner(
        acc_result = {"distribution": {"end_value": {"values": [10_000_000] * 11}}},
        wd_config  = {
            "portfolio_engine": None, "tickers": [KRF], "strategy_factory": lambda: None,
            "data_start": "2000-01-01", "data_end": "2030-01-01", "withdrawal_years": 5,
            "dividend_mode": "hold", "step_months": 6, "tax_engine": te,
            "account_type": "위탁", "user_settings": {}, "current_age": 60,
            "accumulation_years": 0, "gain_harvesting": False,
        },
        monthly_withdrawal = 1_000_000, withdrawal_years = 5, cost_basis = 6_000_000,
    )
    planner._run_withdrawal_samples()
    assert captured.get("cost_basis") == 6_000_000, "cost_basis 미전달"
    assert captured.get("tax_engine") is te, "tax_engine 미전달(인출 과세 안 켜짐)"
    assert captured.get("account_type") == "위탁"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
