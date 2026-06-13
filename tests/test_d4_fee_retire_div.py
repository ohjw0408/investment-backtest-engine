"""D4 fast-follow ② — 은퇴·배당 거래수수료 흐름 (결정론, loader 패치).

규약: fee_rate>0 → 리밸 매매에 수수료 발생(total_fees>0). fee_rate=0 → 0(기존 무변경).
은퇴 인출 엔진(WithdrawalAnalyzer)은 멀티프로세싱이라 라이브 probe로 검증 — 여기선
배당 단일/멀티 엔진의 fee 주입·집계를 빠르게 고정한다.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.dividend_simulator import DividendSimulator
from modules.dividend_multi import MultiDividendSimulator


_IDX = pd.date_range("2015-01-01", "2020-12-31", freq="D")


def _mkdf(prices):
    return pd.DataFrame({"close": prices, "dividend": 0.0}, index=_IDX)


# 한 종목 상승·한 종목 횡보 → 월 리밸 시 매도·매수 발생 → 수수료 부과 경로 활성.
_PRICES = {
    "AAA": _mkdf(np.linspace(100, 300, len(_IDX))),
    "BBB": _mkdf(np.full(len(_IDX), 100.0)),
}


def _patch(sim):
    sim._load = lambda t: _PRICES[t]
    for child in getattr(sim, "_children", []):
        child._load = lambda t: _PRICES[t]
    return sim


def test_dividend_single_fee_flows():
    def run(fee):
        sim = DividendSimulator(
            loader=None, tickers=["AAA", "BBB"], weights={"AAA": 0.5, "BBB": 0.5},
            div_mode="reinvest", step_months=3, rebal_mode="monthly",
            fee_rate=fee, stock_tickers=None,
        )
        _patch(sim)._simulate_one(10_000_000, 500_000, 5, "2015-01-02")
        return sim._last_fees

    assert run(0.0) == 0.0           # opt-out → 수수료 0(기존 결과 회귀 없음)
    assert run(0.005) > 0.0          # 0.5% → 리밸 매매 수수료 발생


def test_dividend_single_fee_reduces_or_equal():
    # 수수료는 현금을 깎으므로 동일 시드의 배당 결과를 늘릴 수 없다(≤).
    def run(fee):
        sim = DividendSimulator(
            loader=None, tickers=["AAA", "BBB"], weights={"AAA": 0.5, "BBB": 0.5},
            div_mode="reinvest", step_months=3, rebal_mode="monthly",
            fee_rate=fee, stock_tickers=None,
        )
        return _patch(sim)._simulate_one(10_000_000, 500_000, 5, "2015-01-02")

    assert run(0.005) <= run(0.0) + 1e-6


def test_dividend_multi_fee_flows():
    # 멀티(MultiAccountSimulationLoop) — 계좌별 fee_rate(normalize 규약) → result.total_fees.
    def run(fee):
        accounts = [
            {"type": "위탁", "initial_capital": 10_000_000, "monthly_contribution": 500_000,
             "tickers": [{"code": "AAA", "weight": 0.5}, {"code": "BBB", "weight": 0.5}],
             "rebal_mode": "monthly", "band_width": 0.05, "fee_rate": fee},
            {"type": "위탁", "initial_capital": 5_000_000, "monthly_contribution": 0,
             "tickers": [{"code": "AAA", "weight": 1.0}],
             "rebal_mode": "monthly", "band_width": 0.05, "fee_rate": fee},
        ]
        sim = MultiDividendSimulator(
            loader=None, accounts=accounts, div_mode="reinvest", step_months=3,
        )
        _patch(sim)._simulate_one(10_000_000, 500_000, 5, "2015-01-02")
        return sim._last_fees

    assert run(0.0) == 0.0
    assert run(0.005) > 0.0
