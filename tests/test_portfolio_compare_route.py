import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import risk_return_logic  # noqa: E402


SAVED_PORTFOLIOS = [
    {"id": 1, "name": "A", "tickers": [{"code": "SPY", "weight": 100}]},
    {"id": 2, "name": "B", "tickers": [{"code": "QQQ", "weight": 100}]},
]


def _client(monkeypatch):
    appmod.app.config["TESTING"] = True
    monkeypatch.setattr(appmod, "has_consented", lambda _uid: True)
    monkeypatch.setattr(appmod, "get_portfolios", lambda _uid: SAVED_PORTFOLIOS)
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = 1
    return c


def test_compare_preserves_portfolio_order_and_empty_benchmarks(monkeypatch):
    captured = {}

    def fake_compute(selected, benchmarks, _loader):
        captured["selected"] = [p["name"] for p in selected]
        captured["benchmarks"] = list(benchmarks)
        return {"items": [], "period": None, "skipped": []}

    monkeypatch.setattr(risk_return_logic, "compute_comparison", fake_compute)

    res = _client(monkeypatch).post(
        "/api/portfolio/compare",
        json={"portfolio_ids": [2, 1], "benchmarks": []},
    )

    assert res.status_code == 200
    assert captured["selected"] == ["B", "A"]
    assert captured["benchmarks"] == []


def test_compare_defaults_benchmarks_only_when_key_missing(monkeypatch):
    captured = {}

    def fake_compute(_selected, benchmarks, _loader):
        captured["benchmarks"] = list(benchmarks)
        return {"items": [], "period": None, "skipped": []}

    monkeypatch.setattr(risk_return_logic, "compute_comparison", fake_compute)

    res = _client(monkeypatch).post(
        "/api/portfolio/compare",
        json={"portfolio_ids": [1]},
    )

    assert res.status_code == 200
    assert [b["code"] for b in captured["benchmarks"]] == [
        b["code"] for b in risk_return_logic.DEFAULT_BENCHMARKS
    ]


def test_portfolio_index_series_can_use_price_or_total_return(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE price_daily (code TEXT, date TEXT, close REAL, volume REAL)")
    conn.execute("CREATE TABLE corporate_actions (code TEXT, date TEXT, dividend REAL)")
    conn.executemany(
        "INSERT INTO price_daily VALUES (?, ?, ?, ?)",
        [
            ("AAA", "2024-01-01", 100.0, 1000.0),
            ("AAA", "2024-01-02", 100.0, 1000.0),
            ("AAA", "2024-01-03", 110.0, 1000.0),
        ],
    )
    conn.execute("INSERT INTO corporate_actions VALUES (?, ?, ?)", ("AAA", "2024-01-02", 10.0))
    monkeypatch.setattr(appmod.portfolio_engine.loader, "ensure_full_history", lambda _code: False)
    appmod._TS_TKCACHE.clear()
    appmod._TS_RESCACHE.clear()

    tickers = [{"code": "AAA", "weight": 100}]
    tr = appmod._portfolio_index_series(tickers, conn=conn, downsample=0, total_return=True)
    price = appmod._portfolio_index_series(tickers, conn=conn, downsample=0, total_return=False)

    assert [p[1] for p in tr] == [100.0, 110.0, 121.0]
    assert [p[1] for p in price] == [100.0, 100.0, 110.0]
