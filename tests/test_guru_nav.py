"""대가 시점별 NAV 사전계산(modules/gurus/nav.py) + 비교 guru 경로 타겟 테스트.

수작업 검산 가능한 미니 데이터: 티커 2개 × 2분기(공시 2회) 체인.
"""
import os
import sqlite3
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.gurus import nav as guru_nav


@pytest.fixture()
def mini_env(tmp_path, monkeypatch):
    """임시 guru DB + price DB. AAA/BBB 두 종목, 공시 2회(리밸런싱 1회)."""
    gdb = tmp_path / "guru.db"
    con = sqlite3.connect(gdb)
    con.executescript(
        """
        CREATE TABLE gurus (cik TEXT PRIMARY KEY, slug TEXT, name TEXT, fund TEXT,
            stance INTEGER, stance_label TEXT, monogram TEXT, latest_period TEXT, stale INTEGER DEFAULT 0);
        CREATE TABLE filings (cik TEXT, period TEXT, filed TEXT, accession TEXT, form TEXT,
            PRIMARY KEY (cik, period));
        CREATE TABLE holdings (cik TEXT, period TEXT, rank INTEGER, cusip TEXT, ticker TEXT,
            name TEXT, shares REAL, value REAL, weight REAL, covered INTEGER);
        """
    )
    con.execute("INSERT INTO gurus VALUES ('111','tguru','T Guru','TF',1,'낙관','TG','2020-03-31',0)")
    # 공시1(filed 2020-01-10): AAA 100% / 공시2(filed 2020-01-20): AAA 50%·BBB 50%
    con.execute("INSERT INTO filings VALUES ('111','2019-12-31','2020-01-10','a1','13F-HR')")
    con.execute("INSERT INTO filings VALUES ('111','2020-03-31','2020-01-20','a2','13F-HR')")
    con.execute("INSERT INTO holdings VALUES ('111','2019-12-31',1,'c1','AAA','A',1,100,1.0,1)")
    con.execute("INSERT INTO holdings VALUES ('111','2020-03-31',1,'c1','AAA','A',1,50,0.5,1)")
    con.execute("INSERT INTO holdings VALUES ('111','2020-03-31',2,'c2','BBB','B',1,50,0.5,1)")
    con.commit(); con.close()
    monkeypatch.setattr(guru_nav, "_GURU_DB", str(gdb))

    pdb = tmp_path / "price.db"
    pc = sqlite3.connect(pdb)
    pc.executescript(
        """
        CREATE TABLE price_daily (code TEXT, date TEXT, open REAL, high REAL, low REAL,
            close REAL, volume REAL, PRIMARY KEY (code, date));
        CREATE TABLE corporate_actions (code TEXT, date TEXT, dividend REAL, split REAL,
            PRIMARY KEY (code, date));
        CREATE TABLE guru_nav (cik TEXT, date TEXT, value REAL, PRIMARY KEY (cik, date));
        """
    )
    # 영업일 나열(주말 무시한 가짜 달력) — AAA 매일 +1%, BBB 매일 +2%
    dates = [f"2020-01-{d:02d}" for d in range(8, 25)]
    a, b = 100.0, 200.0
    for d in dates:
        pc.execute("INSERT INTO price_daily VALUES (?,?,?,?,?,?,?)", ("AAA", d, a, a, a, a, 1000))
        pc.execute("INSERT INTO price_daily VALUES (?,?,?,?,?,?,?)", ("BBB", d, b, b, b, b, 1000))
        a *= 1.01; b *= 1.02
    pc.commit()
    return pc


def test_nav_chain_rebalances_at_filed(mini_env):
    pts = guru_nav.build_guru_nav("111", mini_env)
    assert pts, "NAV 곡선이 비어있음"
    d0, v0 = pts[0]
    assert d0 == "2020-01-10" and v0 == 100.0   # 첫 공시일 시작=100

    by_date = dict(pts)
    # 세그먼트1: 공시일(01-10) 종가 매수 → 01-11부터 AAA 100% 일 +1%
    assert by_date["2020-01-15"] == pytest.approx(100.0 * 1.01 ** 5, rel=1e-6)
    # 공시2(01-20) 종가 리밸런싱: 01-20 수익까진 구비중(AAA +1%), 01-21부터 50/50 일 +1.5%
    v19 = 100.0 * 1.01 ** 9
    assert by_date["2020-01-19"] == pytest.approx(v19, rel=1e-6)
    assert by_date["2020-01-20"] == pytest.approx(v19 * 1.01, rel=1e-6)
    assert by_date["2020-01-22"] == pytest.approx(v19 * 1.01 * 1.015 ** 2, rel=1e-6)


def test_rebuild_and_load_roundtrip(mini_env, monkeypatch):
    out = guru_nav.rebuild_all(price_conn=mini_env)
    assert out == {"tguru": 15}    # 01-10~01-24
    rows = mini_env.execute("SELECT COUNT(*) FROM guru_nav WHERE cik='111'").fetchone()[0]
    assert rows == 15
    # load_nav는 실 price DB를 열므로 여기선 rebuild가 쓴 conn을 직접 검증
    v = mini_env.execute("SELECT value FROM guru_nav WHERE cik='111' AND date='2020-01-15'").fetchone()[0]
    assert v == pytest.approx(100.0 * 1.01 ** 5, rel=1e-6)


def test_compare_uses_guru_nav(monkeypatch):
    """compute_comparison: guru 슬러그 포폴은 NAV 곡선으로 수익 계산(+ point_in_time 플래그)."""
    import risk_return_logic as rr

    dates = pd.bdate_range("2018-01-02", periods=600)
    nav_pts = [[d.strftime("%Y-%m-%d"), 100.0 * (1.001 ** i)] for i, d in enumerate(dates)]
    monkeypatch.setattr("modules.gurus.nav.load_nav", lambda slug: nav_pts if slug == "tguru" else [])

    class FakeLoader:
        def get_price(self, code, start, end, **kw):
            df = pd.DataFrame({
                "date": dates.strftime("%Y-%m-%d"),
                "close": [100.0 * (1.0005 ** i) for i in range(len(dates))],
                "dividend": 0.0, "volume": 1000,
            })
            return df

    res = rr.compute_comparison(
        [{"name": "티구루", "tickers": [{"code": "AAA", "weight": 100}], "guru": "tguru"}],
        [{"code": "SPY", "name": "SPY"}], FakeLoader())
    ports = [i for i in res["items"] if i["kind"] == "portfolio"]
    assert len(ports) == 1 and ports[0].get("point_in_time") is True
    # NAV 일 +0.1% vs 티커 +0.05% — NAV 기반이면 CAGR이 SPY(가짜 +0.05%)보다 뚜렷이 큼
    spy = next(i for i in res["items"] if i.get("code") == "SPY")
    assert ports[0]["cagr"] > spy["cagr"] * 1.5
