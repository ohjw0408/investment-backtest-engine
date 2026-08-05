"""적립기(은퇴 설계·투자계산기) 지표도 TWR 기준인지 검증 (2026-08-05).

백테스트와 같은 뿌리의 버그 — `calc_metrics_from_history`/`AccumulationAnalyzer._calc_metrics`가
MDD를 계좌 잔고 cummax로 재고 있었다. 적립식은 매달 들어오는 납입금이 고점을 계속 밀어올려
낙폭이 희석된다(가격이 -40% 빠져도 MDD가 얕게 찍힘).
"""
import numpy as np
import pytest

from modules.retirement.multi_account_analyzer import calc_metrics_from_history
from tests.test_backtest_dca_metrics import _history, _price_mdd


@pytest.mark.parametrize("monthly", [0.0, 1_000_000.0, 5_000_000.0])
def test_multi_account_mdd_is_twr_based(monthly):
    hist, _dates, prices = _history(monthly)
    m = calc_metrics_from_history(
        hist, years=3, initial_capital=10_000_000.0, monthly_contribution=monthly,
    )
    assert m["mdd"] == pytest.approx(_price_mdd(prices), abs=1e-3)
    assert m["mdd"] < -0.35   # 잔고 기준이면 납입금이 고점을 밀어 얕아진다


def test_multi_account_mdd_sharpe_independent_of_contributions():
    """TWR은 정의상 납입 스케줄과 무관 — 적립식과 거치식이 같아야 한다."""
    h0 = _history(0.0)[0]
    h1 = _history(1_000_000.0)[0]
    a = calc_metrics_from_history(h0, years=3, initial_capital=10_000_000.0, monthly_contribution=0.0)
    b = calc_metrics_from_history(h1, years=3, initial_capital=10_000_000.0, monthly_contribution=1_000_000.0)
    assert a["mdd"] == pytest.approx(b["mdd"], abs=1e-3)
    assert a["sharpe"] == pytest.approx(b["sharpe"], abs=1e-2)
    assert a["sortino"] == pytest.approx(b["sortino"], abs=1e-2)


def test_mwr_survives_non_monthly_cash_flows():
    """배당 인출처럼 월중에 생기는 흐름이 섞여도 MWR이 안 깨져야 한다.

    예전 구현은 `cash_flow != 0` 행을 그대로 enumerate해 "행 하나 = 한 달"로 가정했다.
    """
    hist, _d, _p = _history(1_000_000.0)
    base = calc_metrics_from_history(
        hist, years=3, initial_capital=10_000_000.0, monthly_contribution=1_000_000.0)["cagr"]

    # 월중 랜덤 영업일에 소액 유출(배당 인출)을 섞는다 — 금액이 작으니 MWR도 거의 그대로여야.
    noisy = hist.copy()
    rng = np.random.default_rng(0)
    picks = rng.choice(np.flatnonzero(noisy["cash_flow"].to_numpy() == 0), size=30, replace=False)
    noisy.loc[noisy.index[picks], "cash_flow"] = -1_000.0
    got = calc_metrics_from_history(
        noisy, years=3, initial_capital=10_000_000.0, monthly_contribution=1_000_000.0)["cagr"]

    assert got == pytest.approx(base, abs=0.01)
