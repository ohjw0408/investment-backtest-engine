"""D4 거래수수료 — logic 관통 (2026-06-13). 결정론 가격 패치로 run_backtest_logic 직접 구동.

규약: fee_enabled+fee_rate → 결과 total_fees>0 + 수수료만큼 종료값 하락.
fee_enabled 꺼지면 total_fees=None(기존 동작 무변경).
"""
import os
import sys
from contextlib import contextmanager

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import backtest_logic

ETF = "069500"  # KR ETF (is_etf=1 → 매도 거래세 비대상)


def _df(px, dates):
    return pd.DataFrame(
        {"open": px, "high": px, "low": px, "close": px,
         "volume": 1.0, "dividend": 0.0, "split": 1.0},
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


def _body(**over):
    b = {
        "tickers": [{"code": ETF, "weight": 1.0}],
        "start_date": "2018-01-01", "end_date": "2020-12-31",
        "initial_capital": 10_000_000,
        "monthly_contribution": 1_000_000,
        "rebal_mode": "monthly",
    }
    b.update(over)
    return b


def test_fee_flows_and_reduces_end_value():
    dates = pd.bdate_range("2018-01-01", "2020-12-31")
    pdata = {ETF: _df(np.full(len(dates), 100.0), dates)}  # 평탄가 → 순수 수수료 효과 격리

    with _patched_prices(pdata, dates):
        off = backtest_logic.run_backtest_logic(_body())
        on  = backtest_logic.run_backtest_logic(_body(fee_enabled=True, fee_rate=0.001))

    # 수수료 OFF → total_fees 미표시(기존 동작)
    assert off.get("total_fees") is None
    # 수수료 ON → 누적 수수료 > 0 + 매수 12회×3년 적립이라 유의미
    assert on["total_fees"] > 0
    # 수수료만큼 종료값 하락(평탄가라 수수료가 유일 차이)
    assert on["metrics"]["end_value"] < off["metrics"]["end_value"]


def test_fee_zero_rate_is_noop():
    dates = pd.bdate_range("2019-01-01", "2020-12-31")
    pdata = {ETF: _df(np.full(len(dates), 100.0), dates)}
    with _patched_prices(pdata, dates):
        on0 = backtest_logic.run_backtest_logic(_body(fee_enabled=True, fee_rate=0.0))
    # fee_enabled지만 율 0 → 수수료 0
    assert on0["total_fees"] == 0.0


# ── fast-follow ① 계좌별 수수료: normalize 계약(UI가 계좌별 fee_rate 전송 시 폴백 우선) ──
from modules.multi_account_common import normalize_multi_accounts


def test_normalize_per_account_fee_rate_overrides_body_fallback():
    body = {
        "fee_enabled": True,
        "fee_rate": 0.00015,  # 탭레벨 공통(폴백)
        "accounts": [
            {"tickers": [{"code": ETF, "weight": 1.0}], "fee_rate": 0.0002},  # 계좌 지정
            {"tickers": [{"code": ETF, "weight": 1.0}]},                       # 미지정 → 폴백
        ],
    }
    accs = normalize_multi_accounts(body)
    assert accs[0]["fee_rate"] == 0.0002      # 계좌 지정값 우선
    assert accs[1]["fee_rate"] == 0.00015     # 미지정 → 탭레벨 폴백


def test_normalize_fee_rate_zero_when_disabled():
    body = {
        "fee_enabled": False,
        "fee_rate": 0.0002,
        "accounts": [{"tickers": [{"code": ETF, "weight": 1.0}], "fee_rate": 0.0002}],
    }
    accs = normalize_multi_accounts(body)
    assert accs[0]["fee_rate"] == 0.0         # opt-out → 0(기존 결과 회귀 없음)
