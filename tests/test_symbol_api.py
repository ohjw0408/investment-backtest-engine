"""A4 종목 상세 — 분류(asset_type)·OHLC·시간봉 API 결정론 검증.

- asset_type: symbol_master.is_etf + country로 산출 (yfinance .info 불필요).
- 일봉 prices에 OHLC 포함.
- 시간봉(get_intraday_data): price_hourly 캐시 우선(같은 날 있으면 fetch 생략) → 캐시 시드로 무네트워크 검증.
"""
from datetime import datetime

import pytest

from modules.portfolio_engine import PortfolioEngine

pe = PortfolioEngine()
L = pe.loader


@pytest.mark.parametrize("code,expect", [
    ("SPY",     "US_ETF"),
    ("005930",  "KR_STOCK"),
    ("069500",  "KR_ETF"),
    ("BTC-USD", "CRYPTO"),
    ("^KS11",   "INDEX"),
])
def test_asset_type(code, expect):
    d = L.get_symbol_data(code)
    assert d["asset_type"] == expect
    assert isinstance(d["is_etf"], bool)


def test_daily_prices_have_ohlc():
    d = L.get_symbol_data("SPY")
    p = d["prices"][-1]
    for k in ("open", "high", "low", "close"):
        assert k in p and isinstance(p[k], (int, float))
    assert p["high"] >= p["low"]


def test_stock_fundamentals_keys_present():
    # 값은 yfinance 의존(오프라인이면 None) — 키 존재만 계약으로 보장
    d = L.get_symbol_data("005930")
    for k in ("market_cap", "per", "pbr", "sector"):
        assert k in d


def test_intraday_reads_cache_without_fetch():
    code  = "ZZTESTINTRADAY"   # isalpha → US/USD, KRX 코드 아님
    today = datetime.today().strftime("%Y-%m-%d")
    L.conn.execute("DELETE FROM price_hourly WHERE code=?", (code,))
    L.conn.executemany(
        "INSERT OR REPLACE INTO price_hourly "
        "(code,datetime,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
        [(code, f"{today} 09:00", 100.0, 101.0, 99.0, 100.5, 1000),
         (code, f"{today} 10:00", 100.5, 102.0, 100.0, 101.5, 1200)],
    )
    L.conn.commit()
    try:
        out = L.get_intraday_data(code, "1d")
        assert out["range"] == "1d"
        assert out["currency"] == "USD"
        assert len(out["prices"]) == 2
        assert out["prices"][0]["open"] == 100.0
        assert all(k in out["prices"][0] for k in ("open", "high", "low", "close"))
    finally:
        L.conn.execute("DELETE FROM price_hourly WHERE code=?", (code,))
        L.conn.commit()
