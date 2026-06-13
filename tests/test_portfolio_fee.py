"""거래수수료 Portfolio 적용 (D4, 2026-06-13 오너 결정).

규약: 통합 수수료율(매수=매도) + 개별주식 매도 거래세 0.18% 가산(ETF 면제).
fee_rate=0이면 기존 동작과 완전 동일(opt-in).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from modules.core.portfolio import Portfolio, TaxTrackedPortfolio, STOCK_SELL_TAX


def test_fee_zero_is_noop():
    # 기본(fee_rate=0) → 수수료 0, cash 기존 동작
    p = Portfolio(10_000)
    p.buy("ETF", 10, 100)        # 1,000원
    assert p.cash == 9_000
    assert p.total_fees == 0.0
    p.sell("ETF", 5, 100)        # +500
    assert p.cash == 9_500
    assert p.total_fees == 0.0


def test_buy_fee():
    p = Portfolio(10_000, fee_rate=0.001)   # 0.1%
    p.buy("ETF", 10, 100)                   # cost 1,000 + fee 1
    assert p.cash == pytest.approx(8_999.0)
    assert p.total_fees == pytest.approx(1.0)


def test_sell_fee_etf():
    p = Portfolio(10_000, fee_rate=0.001)
    p.buy("ETF", 10, 100)                   # cash 8,999, fee 1
    p.sell("ETF", 10, 100)                  # proceeds 1,000 - fee 1 = +999
    assert p.cash == pytest.approx(9_998.0)
    assert p.total_fees == pytest.approx(2.0)


def test_sell_fee_stock_has_transaction_tax():
    # 개별주식(stock_tickers) 매도 → fee_rate + 0.18% 거래세
    p = Portfolio(10_000, fee_rate=0.001, stock_tickers={"005930"})
    p.buy("005930", 10, 100)                # 매수: 거래세 없음 → fee 1
    assert p.total_fees == pytest.approx(1.0)
    p.sell("005930", 10, 100)               # 매도: (0.001 + 0.0018)*1000 = 2.8
    assert p.total_fees == pytest.approx(1.0 + 2.8)
    assert STOCK_SELL_TAX == 0.0018


def test_buy_insufficient_with_fee_raises():
    # cash가 cost와 정확히 같으면 수수료 때문에 매수 불가
    p = Portfolio(1_000, fee_rate=0.001)
    with pytest.raises(ValueError):
        p.buy("ETF", 10, 100)               # cost 1,000 + fee 1 > 1,000


def test_tax_tracked_fee_not_in_avg_cost():
    # 수수료는 cash만 줄이고 취득단가(avg_cost)에는 미포함
    p = TaxTrackedPortfolio(10_000, fee_rate=0.01)
    p.buy("ETF", 10, 100)
    assert p.get_avg_cost("ETF") == pytest.approx(100.0)   # 수수료 무관
    assert p.total_fees == pytest.approx(10.0)             # 1,000 * 0.01
