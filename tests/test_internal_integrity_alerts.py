import sqlite3

from modules.alerts import alert_store
import tasks


def _temp_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_integrity_scan_does_not_create_user_inbox_event(monkeypatch):
    conn = _temp_conn()
    monkeypatch.setattr(alert_store.auth_manager, "_get_conn", lambda: conn)
    alert_store.init_alerts_db()

    tasks._integrity_notify_owner(["합성 백필 손상 검출: ['379780', 'INDV']"])

    assert conn.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0] == 0


def test_init_purges_legacy_integrity_events(monkeypatch):
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
    assert [r["title"] for r in rows] == ["정상 알림"]
    assert alert_store.unread_count(1) == 1
    assert [e["title"] for e in alert_store.get_events(1)] == ["정상 알림"]
