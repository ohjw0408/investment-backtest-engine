"""트레일링 갱신 정지 회귀 (2026-08-12, SPCX 두 달 정지 사건).

① 야후 페치가 실패해도 그날 재시도를 막지 않는다 (예전엔 '시도했음'만으로 하루 잠금).
② 페치 예외가 요청 전체를 죽이지 않는다 — DB 보유분은 그대로 서빙.
③ refresh_stale_prices가 멈춘 종목을 찾아 복구하고, 연속 실패 종목은 쿨다운한다.
"""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.price_loader import PriceLoader


def _loader():
    """실 DB·네트워크 없이 PriceLoader 최소 인스턴스."""
    pl = PriceLoader.__new__(PriceLoader)
    pl.conn = sqlite3.connect(":memory:")
    pl.index_conn = None
    pl._us_tickers = set()
    pl._kr_tickers = set()
    pl._price_cache = {}
    pl._backfilled_codes = set()
    pl._backfill_skip_codes = set()
    pl._usdkrw_cache = None
    pl._backfill_engine = None
    pl.create_tables()
    return pl


def _seed(pl, code, dates, close=100.0):
    pl.conn.executemany(
        "INSERT OR IGNORE INTO price_daily (code, date, open, high, low, close, volume) "
        "VALUES (?,?,?,?,?,?,?)",
        [(code, d, close, close, close, close, 1000.0) for d in dates])
    pl.conn.commit()


def _price_df(code, dates, close=100.0):
    return pd.DataFrame([{"code": code, "date": d, "open": close, "high": close,
                          "low": close, "close": close, "volume": 1000.0} for d in dates])


def test_failed_trailing_fetch_is_retried_same_day():
    # 야후 빈 결과(레이트리밋)여도 DB가 몇 달 밀려 있으면 하루를 잠그지 않는다.
    pl = _loader()
    today = datetime.now().date()
    old   = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    _seed(pl, "SPCX", [old])
    calls = []

    def fake_fetch(yf_code, start, end):
        calls.append((start, end))
        return None, None          # 야후 실패(빈 결과)

    pl.fetch_from_api = fake_fetch
    pl.get_price("SPCX", old, today.strftime("%Y-%m-%d"), apply_fx=False)
    pl._price_cache.clear()        # 같은 키 캐시 히트 배제(가드만 검증)
    pl.get_price("SPCX", old, today.strftime("%Y-%m-%d"), apply_fx=False)
    assert len(calls) == 1, f"백오프 안에서 재페치 폭주: {calls}"

    # 백오프 경과 → 같은 날이어도 재시도해야 한다(예전엔 다음날까지 영구 스킵)
    day, done, ts = pl._gapfill_trail_state["SPCX"]
    pl._gapfill_trail_state["SPCX"] = (day, done, ts - pl.TRAIL_RETRY_SEC - 1)
    pl._price_cache.clear()
    pl.get_price("SPCX", old, today.strftime("%Y-%m-%d"), apply_fx=False)

    assert len(calls) == 2, f"실패한 트레일링 페치가 재시도되지 않음: {calls}"


def test_uptodate_code_locks_day_after_empty_fetch():
    # 반대로 이미 최신인 종목은 빈 결과 = 정상 → 하루 1회로 제한(기존 P2-3 절약 유지).
    pl = _loader()
    today  = datetime.now().date()
    recent = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    _seed(pl, "SPY", [recent])
    calls = []

    def fake_fetch(yf_code, start, end):
        calls.append((start, end))
        return None, None

    pl.fetch_from_api = fake_fetch
    for _ in range(3):
        pl._price_cache.clear()
        pl.get_price("SPY", recent, today.strftime("%Y-%m-%d"), apply_fx=False)

    assert len(calls) == 1, f"최신 종목인데 매 호출 재페치: {calls}"


def test_fetch_exception_still_serves_db_rows():
    # 페치가 터져도 DB 보유분은 반환해야 한다(위젯 시세가 통째로 비던 원인).
    pl = _loader()
    today = datetime.now().date()
    d1    = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    d2    = (today - timedelta(days=29)).strftime("%Y-%m-%d")
    _seed(pl, "AXP", [d1, d2])

    def boom(yf_code, start, end):
        raise RuntimeError("YFRateLimitError")

    pl.fetch_from_api = boom
    df = pl.get_price("AXP", d1, today.strftime("%Y-%m-%d"), apply_fx=False)

    assert len(df) == 2
    assert df["date"].tolist() == [d1, d2]


def test_refresh_stale_prices_repairs_and_cools_down():
    pl = _loader()
    today = datetime.now().date()
    stale = (today - timedelta(days=40)).strftime("%Y-%m-%d")
    fresh = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    _seed(pl, "SPCX", [stale])
    _seed(pl, "DEAD", [stale])
    _seed(pl, "SPY",  [fresh])
    new_day = (today - timedelta(days=2)).strftime("%Y-%m-%d")

    def fake_fetch(yf_code, start, end):
        if yf_code == "SPCX":
            df = _price_df("SPCX", [new_day])
            return df[["code", "date", "open", "high", "low", "close", "volume"]], None
        return None, None          # DEAD = 상폐

    pl.fetch_from_api = fake_fetch
    st = pl.refresh_stale_prices(sleep_sec=0)

    assert st["stale"] == 2 and "SPY" not in [r[0] for r in pl.conn.execute(
        "SELECT code FROM price_refresh_state")]
    assert st["repaired"] == 1 and st["failed"] == 1
    assert pl.conn.execute(
        "SELECT MAX(date) FROM price_daily WHERE code='SPCX'").fetchone()[0] == new_day

    # 연속 실패 3회 넘기면 쿨다운(상폐 종목이 매일 야후를 때리지 않게)
    for _ in range(2):
        pl.refresh_stale_prices(sleep_sec=0)
    st2 = pl.refresh_stale_prices(sleep_sec=0)
    assert st2["skipped"] >= 1, f"실패 누적 종목이 쿨다운되지 않음: {st2}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
