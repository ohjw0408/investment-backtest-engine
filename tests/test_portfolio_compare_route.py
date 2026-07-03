import os
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
