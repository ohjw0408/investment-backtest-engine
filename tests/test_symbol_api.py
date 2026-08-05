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


# --- 시간봉 타임존 회귀 (2026-08-06 BUG-INTRADAY-TZ) -------------------------
# price_hourly는 UTC 저장, API는 거래소 현지 벽시계로 반환한다.
# 이 계약이 깨지면 코스피 09:00 봉이 전날 15:00으로 찍힌다(날짜가 하루씩 밀림).

def _seed_hourly(code, dts):
    L.conn.execute("DELETE FROM price_hourly WHERE code=?", (code,))
    L.conn.executemany(
        "INSERT OR REPLACE INTO price_hourly "
        "(code,datetime,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
        [(code, d, 100.0, 101.0, 99.0, 100.5, 1000) for d in dts],
    )
    L.conn.commit()


@pytest.mark.parametrize("code,utc_dt,expect_local", [
    ("^KS11", "2026-07-13 00:00", "2026-07-13 09:00"),   # KST = UTC+9 (DST 없음)
    ("^KS11", "2026-07-13 05:00", "2026-07-13 14:00"),
    ("SPY",   "2026-07-13 13:30", "2026-07-13 09:30"),   # EDT = UTC-4
    ("SPY",   "2026-01-05 14:30", "2026-01-05 09:30"),   # EST = UTC-5 (DST 전환 반영)
])
def test_intraday_returns_exchange_local_time(code, utc_dt, expect_local):
    saved = L.conn.execute(
        "SELECT datetime,open,high,low,close,volume FROM price_hourly WHERE code=?", (code,)
    ).fetchall()
    from datetime import datetime, timedelta
    # 30일 이전 앵커 = has_deep 성립 → 730d 네트워크 페치 회피
    anchor = (datetime.utcnow() - timedelta(days=200)).strftime("%Y-%m-%d 12:00")
    try:
        _seed_hourly(code, [anchor, utc_dt])
        # 네트워크 재조회(최근·결손복구) 전부 차단 → 시드만으로 결정론 검증
        L._intraday_fetch_ts = {code: 9e18, code + ":deep": 9e18}
        out = L.get_intraday_data(code, "max")
        assert out["tz"] == ("Asia/Seoul" if code == "^KS11" else "America/New_York")
        assert expect_local in [p["date"] for p in out["prices"]]
        assert len(out["prices"]) == 2
    finally:
        L.conn.execute("DELETE FROM price_hourly WHERE code=?", (code,))
        if saved:
            L.conn.executemany(
                "INSERT OR REPLACE INTO price_hourly "
                "(code,datetime,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
                [(code,) + r for r in saved])
        L.conn.commit()
        L._intraday_fetch_ts = {}


# --- 시간봉 결손 감지 회귀 (2026-08-06) --------------------------------------
# has_deep만 보고 7d만 갱신하면 방문 공백기 구간이 영구히 비어 "7/13 다음 7/27"이 된다.

def test_intraday_hole_detection():
    code = "ZZTESTHOLE"
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    try:
        # 연속(휴장 수준 공백만) → 결손 아님
        _seed_hourly(code, [(now - timedelta(days=n)).strftime("%Y-%m-%d 12:00")
                            for n in range(0, 40, 3)])
        assert L._has_intraday_hole(code) is False
        # 중간 30일 공백 → 결손
        _seed_hourly(code, [(now - timedelta(days=n)).strftime("%Y-%m-%d 12:00")
                            for n in list(range(0, 10, 3)) + list(range(40, 60, 3))])
        assert L._has_intraday_hole(code) is True
        # 마지막 봉이 30일 전 → 결손(꼬리 공백)
        _seed_hourly(code, [(now - timedelta(days=n)).strftime("%Y-%m-%d 12:00")
                            for n in range(30, 60, 3)])
        assert L._has_intraday_hole(code) is True
    finally:
        L.conn.execute("DELETE FROM price_hourly WHERE code=?", (code,))
        L.conn.commit()
