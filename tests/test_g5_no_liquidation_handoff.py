"""
tests/test_g5_no_liquidation_handoff.py
BUG-TAX-3: 은퇴 적립 무청산 인계 — AccumulationAnalyzer 단위 검증.

AccumulationAnalyzer는 **단일 은퇴(run_retirement_logic)** 와 **투자계산기(legacy)** 가
공유하는 적립 엔진이다. 여기서 apply_final_liquidation 플래그를 직접 검증하면
단일 은퇴 경로의 무청산을 보증한다(L11은 멀티만 커버 → 이 파일이 단일 갭을 메움).

검증(연금=이중과세 당사자 + 위탁):
- 무청산(False) 적립 종료값 == 세금OFF gross (청산세 미부과 증명).
- 일괄청산(True, 투자계산기) 종료값 < 무청산 (연금 5.5% / 위탁 15.4% 실제 부과 — 회귀: 계산기 불변).
- 선형성장 픽스처 → 전 윈도우 차익 보장(차익 0이면 청산세 0이라 구분 안 됨).
"""
import os
import sys
from contextlib import contextmanager

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
from modules.tax.base_tax import TaxEngine

KRF = "458730"   # KR_FOREIGN (위탁 청산세 15.4%)
PEN_TICKER = "069500"  # 연금/IRP 가능 국내 ETF

START = "2014-01-01"
END   = "2022-12-31"

_engine = PortfolioEngine()


def _ramp_frame(dates, lo=100.0, hi=200.0):
    """선형 성장 — 전 윈도우가 차익을 갖도록."""
    n = len(dates)
    px = np.linspace(lo, hi, n)
    return pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
        index=dates,
    )


@contextmanager
def _patched_load(frame_map):
    orig = _engine.price_loader.load
    def fake(tickers, s, e, allow_synthetic=False):
        idx = pd.bdate_range(start=s, end=e)
        out = {}
        for t in tickers:
            if t not in frame_map:
                continue
            df = frame_map[t].reindex(idx)
            df[["open", "high", "low", "close", "volume"]] = (
                df[["open", "high", "low", "close", "volume"]].ffill().bfill()
            )
            df["dividend"] = df["dividend"].fillna(0.0)
            df["split"] = df["split"].fillna(1.0)
            out[t] = df
        return out, list(idx)
    _engine.price_loader.load = fake
    try:
        yield
    finally:
        _engine.price_loader.load = orig


def _make_analyzer(ticker, account_type, tax_engine, apply_final_liquidation):
    return AccumulationAnalyzer(
        portfolio_engine     = _engine,
        tickers              = [ticker],
        strategy_factory     = lambda: PeriodicRebalance({ticker: 1.0}, rebalance_frequency=None),
        data_start           = START,
        data_end             = END,
        accumulation_years   = 2,
        monthly_contribution = 0,
        initial_capital      = 10_000_000,
        dividend_mode        = "hold",
        step_months          = 6,
        verbose              = False,
        tax_engine           = tax_engine,
        account_type         = account_type,
        apply_final_liquidation = apply_final_liquidation,
    )


def _p50(ticker, account_type, frame_map, tax_engine, apply_final_liquidation):
    with _patched_load(frame_map):
        res = _make_analyzer(ticker, account_type, tax_engine, apply_final_liquidation).run()
    return res["distribution"]["end_value"]["p50"]


def test_pension_no_liquidation_equals_gross():
    """연금저축 적립: 무청산(False) == 세금OFF gross. 일괄청산(True) < 무청산(5.5% 부과)."""
    dates = pd.bdate_range(START, END)
    fmap  = {PEN_TICKER: _ramp_frame(dates)}

    off    = _p50(PEN_TICKER, "연금저축", fmap, None, True)               # 세금엔진 없음 = gross
    no_liq = _p50(PEN_TICKER, "연금저축", fmap, TaxEngine({"age": 60}), False)
    liq    = _p50(PEN_TICKER, "연금저축", fmap, TaxEngine({"age": 60}), True)

    # 무청산 = gross (연금 적립기 비과세 → 중간세 0, 최종청산 스킵 → OFF와 동일)
    assert abs(no_liq - off) <= 1, f"연금 무청산 {no_liq} != gross {off}"
    # 일괄청산 = 연금소득세 5.5% 부과 → gross보다 작음 (투자계산기 동작, 회귀)
    assert liq < no_liq - 1, f"연금 일괄청산 {liq} 이 무청산 {no_liq} 보다 안 작음(세금 미부과?)"


def test_brokerage_no_liquidation_equals_gross():
    """위탁 적립(배당0·리밸none): 무청산(False) == 세금OFF gross. 일괄청산(True) < 무청산(양도세)."""
    dates = pd.bdate_range(START, END)
    fmap  = {KRF: _ramp_frame(dates)}

    off    = _p50(KRF, "위탁", fmap, None, True)
    no_liq = _p50(KRF, "위탁", fmap, TaxEngine({"earned_income": 0, "age": 40}), False)
    liq    = _p50(KRF, "위탁", fmap, TaxEngine({"earned_income": 0, "age": 40}), True)

    assert abs(no_liq - off) <= 1, f"위탁 무청산 {no_liq} != gross {off}"
    assert liq < no_liq - 1, f"위탁 일괄청산 {liq} 이 무청산 {no_liq} 보다 안 작음(양도세 미부과?)"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
