"""
alert_store.py
────────────────────────────────────────────────────────────────────────────────
알림 룰 + 수신함 DB CRUD. users.db(auth_manager 연결) 재사용.
"""

import json
from datetime import datetime

from modules import auth_manager

ALERTS_DDL = """
CREATE TABLE IF NOT EXISTS alert_rules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    scope        TEXT NOT NULL,
    code         TEXT,
    portfolio_id INTEGER,
    rule_type    TEXT NOT NULL,
    direction    TEXT,
    threshold    REAL,
    window       TEXT,
    enabled      INTEGER NOT NULL DEFAULT 1,
    cooldown_h   INTEGER NOT NULL DEFAULT 24,
    last_triggered_at TEXT,
    last_extreme REAL,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS alert_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    rule_id    INTEGER,
    code       TEXT,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    meta       TEXT,
    created_at TEXT NOT NULL,
    read_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_events_inbox ON alert_events(user_id, read_at, id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_user ON alert_rules(user_id);

CREATE TABLE IF NOT EXISTS device_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    token      TEXT NOT NULL UNIQUE,
    platform   TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens(user_id);
"""

# 사용자당 알림 룰 한도(스팸/부하 방지). 요금제 차등 시 단일 변경점.
MAX_ALERT_RULES = 50

VALID_TYPES = {"daily_pct", "target_price", "new_high", "new_low", "rebalance_band"}


def init_alerts_db():
    c = auth_manager._get_conn()
    c.executescript(ALERTS_DDL)
    c.commit()


def _conn():
    return auth_manager._get_conn()


# ── 룰 CRUD ────────────────────────────────────────────

def get_rules(user_id, enabled_only=False):
    q = "SELECT * FROM alert_rules WHERE user_id=?"
    if enabled_only:
        q += " AND enabled=1"
    q += " ORDER BY id"
    return [dict(r) for r in _conn().execute(q, (user_id,)).fetchall()]


def get_all_enabled_rules():
    """평가 task용 — 전 사용자 enabled 룰."""
    return [dict(r) for r in _conn().execute(
        "SELECT * FROM alert_rules WHERE enabled=1 ORDER BY user_id, id"
    ).fetchall()]


def count_rules(user_id):
    return _conn().execute(
        "SELECT COUNT(*) FROM alert_rules WHERE user_id=?", (user_id,)
    ).fetchone()[0]


def create_rule(user_id, scope, rule_type, code=None, portfolio_id=None,
                direction=None, threshold=None, window=None, cooldown_h=24):
    if rule_type not in VALID_TYPES:
        raise ValueError("알 수 없는 알림 종류입니다.")
    if count_rules(user_id) >= MAX_ALERT_RULES:
        raise ValueError(f"알림은 최대 {MAX_ALERT_RULES}개까지 만들 수 있어요.")
    now = datetime.now().isoformat()
    c = _conn()
    cur = c.execute(
        "INSERT INTO alert_rules (user_id, scope, code, portfolio_id, rule_type, "
        "direction, threshold, window, enabled, cooldown_h, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,1,?,?)",
        (user_id, scope, code, portfolio_id, rule_type, direction,
         threshold, window, cooldown_h, now)
    )
    c.commit()
    return cur.lastrowid


def update_rule(user_id, rule_id, **fields):
    """허용 필드만 부분 수정. enabled 토글·임계값 변경 등."""
    allowed = {"direction", "threshold", "window", "enabled", "cooldown_h"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return False
    vals += [rule_id, user_id]
    c = _conn()
    c.execute(f"UPDATE alert_rules SET {', '.join(sets)} WHERE id=? AND user_id=?", vals)
    c.commit()
    return True


def delete_rule(user_id, rule_id):
    c = _conn()
    c.execute("DELETE FROM alert_rules WHERE id=? AND user_id=?", (rule_id, user_id))
    c.commit()


def mark_rule_fired(rule_id, now_iso, new_extreme=None):
    """평가 task가 발화 후 호출 — 쿨다운/재무장 추적."""
    c = _conn()
    if new_extreme is not None:
        c.execute("UPDATE alert_rules SET last_triggered_at=?, last_extreme=? WHERE id=?",
                  (now_iso, new_extreme, rule_id))
    else:
        c.execute("UPDATE alert_rules SET last_triggered_at=? WHERE id=?",
                  (now_iso, rule_id))
    c.commit()


# ── 수신함(events) ──────────────────────────────────────

def add_event(user_id, title, body, code=None, rule_id=None, meta=None):
    now = datetime.now().isoformat()
    c = _conn()
    cur = c.execute(
        "INSERT INTO alert_events (user_id, rule_id, code, title, body, meta, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (user_id, rule_id, code, title, body,
         json.dumps(meta, ensure_ascii=False) if meta is not None else None, now)
    )
    c.commit()
    return cur.lastrowid


def get_events(user_id, unread_only=False, limit=50):
    q = "SELECT * FROM alert_events WHERE user_id=?"
    if unread_only:
        q += " AND read_at IS NULL"
    q += " ORDER BY id DESC LIMIT ?"
    out = []
    for r in _conn().execute(q, (user_id, limit)).fetchall():
        d = dict(r)
        if d.get("meta"):
            try:
                d["meta"] = json.loads(d["meta"])
            except Exception:
                pass
        out.append(d)
    return out


def unread_count(user_id):
    return _conn().execute(
        "SELECT COUNT(*) FROM alert_events WHERE user_id=? AND read_at IS NULL",
        (user_id,)
    ).fetchone()[0]


def mark_read(user_id, event_id):
    c = _conn()
    c.execute("UPDATE alert_events SET read_at=? WHERE id=? AND user_id=? AND read_at IS NULL",
              (datetime.now().isoformat(), event_id, user_id))
    c.commit()


def mark_all_read(user_id):
    c = _conn()
    c.execute("UPDATE alert_events SET read_at=? WHERE user_id=? AND read_at IS NULL",
              (datetime.now().isoformat(), user_id))
    c.commit()


# ── 푸시 기기 토큰(FCM) ──────────────────────────────────

def register_device_token(user_id, token, platform):
    """기기 토큰 등록(업서트). 토큰은 기기당 1개라 unique — 재로그인/계정전환 시 user_id 재배정."""
    now = datetime.now().isoformat()
    c = _conn()
    c.execute(
        "INSERT INTO device_tokens (user_id, token, platform, created_at, updated_at) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(token) DO UPDATE SET user_id=excluded.user_id, "
        "platform=excluded.platform, updated_at=excluded.updated_at",
        (user_id, token, platform, now, now)
    )
    c.commit()


def get_device_tokens(user_id):
    return [dict(r) for r in _conn().execute(
        "SELECT token, platform FROM device_tokens WHERE user_id=?", (user_id,)
    ).fetchall()]


def delete_device_token(token):
    """죽은 토큰(FCM UNREGISTERED) 또는 로그아웃 시 정리."""
    c = _conn()
    c.execute("DELETE FROM device_tokens WHERE token=?", (token,))
    c.commit()


def has_device_tokens(user_id):
    """푸시 알림 켜짐 여부 = 등록된 기기 토큰 존재."""
    return _conn().execute(
        "SELECT 1 FROM device_tokens WHERE user_id=? LIMIT 1", (user_id,)
    ).fetchone() is not None


def delete_user_device_tokens(user_id):
    """사용자 푸시 끄기 — 전 기기 토큰 제거."""
    c = _conn()
    c.execute("DELETE FROM device_tokens WHERE user_id=?", (user_id,))
    c.commit()
