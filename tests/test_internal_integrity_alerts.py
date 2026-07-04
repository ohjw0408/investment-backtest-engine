import sqlite3

from modules.alerts import alert_store
from modules.alerts import push_sender
import tasks


def _temp_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _create_users(conn):
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    conn.execute("INSERT INTO users (id, email) VALUES (?, ?)", (1, "owner@example.com"))
    conn.execute("INSERT INTO users (id, email) VALUES (?, ?)", (2, "user@example.com"))
    conn.commit()


def test_integrity_scan_notifies_owner_only(monkeypatch):
    conn = _temp_conn()
    monkeypatch.setattr(alert_store.auth_manager, "_get_conn", lambda: conn)
    monkeypatch.setenv("OWNER_EMAIL", "owner@example.com")
    sent = []
    monkeypatch.setattr(push_sender, "send_to_user", lambda *args, **kwargs: sent.append((args, kwargs)))
    _create_users(conn)
    alert_store.init_alerts_db()

    tasks._integrity_notify_owner(["합성 백필 손상 검출: ['379780', 'INDV']"])

    rows = conn.execute("SELECT user_id, title, body, meta FROM alert_events").fetchall()
    assert len(rows) == 1
    assert rows[0]["user_id"] == 1
    assert rows[0]["title"] == "데이터 무결성 이상 1건"
    assert "379780" in rows[0]["body"]
    assert '"audience": "owner"' in rows[0]["meta"]
    assert alert_store.unread_count(1) == 1
    assert alert_store.unread_count(2) == 0
    assert sent[0][0][0] == 1


def test_owner_integrity_event_remains_visible(monkeypatch):
    conn = _temp_conn()
    monkeypatch.setattr(alert_store.auth_manager, "_get_conn", lambda: conn)
    alert_store.init_alerts_db()
    conn.execute(
        "INSERT INTO alert_events (user_id, title, body, meta, created_at) VALUES (?,?,?,?,?)",
        (1, "데이터 무결성 이상 1건", "379780, INDV", '{"type": "integrity"}', "2026-07-04T00:00:00"),
    )
    conn.execute(
        "INSERT INTO alert_events (user_id, title, body, meta, created_at) VALUES (?,?,?,?,?)",
        (1, "정상 알림", "SPY", '{"type": "user"}', "2026-07-04T00:00:00"),
    )
    conn.commit()

    alert_store.init_alerts_db()

    rows = conn.execute("SELECT title FROM alert_events ORDER BY id").fetchall()
    assert [r["title"] for r in rows] == ["데이터 무결성 이상 1건", "정상 알림"]
    assert alert_store.unread_count(1) == 2
    assert [e["title"] for e in alert_store.get_events(1)] == ["정상 알림", "데이터 무결성 이상 1건"]
