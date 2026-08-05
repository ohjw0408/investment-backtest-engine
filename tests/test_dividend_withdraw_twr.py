"""배당 인출(dividend_mode='withdraw')이 수익으로 잡히는지 검증 (2026-08-05).

배당 인출은 포트폴리오 밖으로 나가는 유출인데 `cash_flow`에 기록되지 않아,
TWR이 이걸 "손실"로 읽었다 — 배당수익률만큼 수익률이 통째로 깎였다.
평탄가(가격 무변동) + 정기 배당이면 수익 = 배당뿐이므로 효과가 그대로 드러난다.
"""
import os
import sys
from contextlib import contextmanager

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import backtest_logic

ETF = "069500"
DIV_PER_SHARE = 0.5          # 분기 배당, 주가 100 → 연 2%
DIV_EVERY_N_BDAYS = 63       # 달력일 기준으로 잡으면 주말에 걸려 배당 없는 해가 생긴다


def _flat_df_with_dividends(dates):
    px = np.full(len(dates), 100.0)
    div = np.zeros(len(dates))
    div[DIV_EVERY_N_BDAYS - 1::DIV_EVERY_N_BDAYS] = DIV_PER_SHARE
    assert div.sum() > 0, "테스트 달력에 배당일이 하나도 안 잡혔다"
    return pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": div, "split": 1.0},
        index=dates,
    )


@contextmanager
def _patched_prices(price_data, dates):
    eng  = backtest_logic._get_portfolio_engine()
    orig = eng.price_loader.load
    eng.price_loader.load = lambda tickers, s, e: (
        {t: price_data[t] for t in tickers if t in price_data}, list(dates)
    )
    try:
        yield
    finally:
        eng.price_loader.load = orig


def _run(div_mode, monthly=1_000_000.0):
    return backtest_logic.run_backtest_logic({
        "tickers": [{"code": ETF, "weight": 1.0}],
        "start_date": "2018-01-01", "end_date": "2020-12-31",
        "initial_capital": 10_000_000,
        "monthly_contribution": monthly,
        "rebal_mode": "none",
        "dividend_mode": div_mode,
    })


@pytest.fixture
def patched():
    dates = pd.bdate_range("2018-01-01", "2020-12-31")
    with _patched_prices({ETF: _flat_df_with_dividends(dates)}, dates):
        yield


def test_withdrawn_dividends_count_as_return(patched):
    wd = _run("withdraw")
    assert wd["metrics"]["total_dividend"] > 0
    # 가격이 평탄하므로 수익 = 배당뿐. 수정 전엔 잔고가 안 늘어 0% 근처(또는 음수)였다.
    for a in wd["annual_returns"][1:]:      # 2018은 첫 배당 전 구간이 섞여 부분연도
        assert a["return"] > 0.01, wd["annual_returns"]


def test_withdraw_and_reinvest_have_same_twr(patched):
    """TWR은 배당을 재투자했든 빼갔든 같아야 한다(수익률이지 잔고가 아니므로)."""
    rein = _run("reinvest")
    wd   = _run("withdraw")
    assert rein["metrics"]["end_value"] > wd["metrics"]["end_value"]   # 잔고는 당연히 다름
    for a, b in zip(rein["annual_returns"], wd["annual_returns"]):
        assert a["year"] == b["year"]
        assert a["return"] == pytest.approx(b["return"], abs=0.005), (rein["annual_returns"], wd["annual_returns"])


def test_withdraw_mdd_not_dragged_down_by_payouts(patched):
    """평탄가 + 배당 유출 → 낙폭 0이어야. 유출을 손실로 읽으면 배당일마다 낙폭이 찍힌다."""
    wd = _run("withdraw")
    assert wd["metrics"]["mdd"] > -0.005, wd["metrics"]["mdd"]


def test_total_invested_ignores_dividend_outflow(patched):
    """음수 cash_flow(배당 유출)가 총 납입금에 섞이면 안 된다."""
    wd = _run("withdraw")
    assert wd["metrics"]["total_invested"] == 10_000_000 + 36 * 1_000_000
