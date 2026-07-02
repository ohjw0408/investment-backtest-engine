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

-- 증시 캘린더 일정 알림 설정(사용자 1:1). 가격 룰과 독립.
CREATE TABLE IF NOT EXISTS cal_alert_prefs (
    user_id        INTEGER PRIMARY KEY,
    enabled        INTEGER NOT NULL DEFAULT 0,
    show_econ      INTEGER NOT NULL DEFAULT 1,
    show_earnings  INTEGER NOT NULL DEFAULT 1,
    show_policy    INTEGER NOT NULL DEFAULT 1,
    show_dividend  INTEGER NOT NULL DEFAULT 1,
    econ_ids       TEXT,
    sources        TEXT,
    excluded       TEXT,
    last_sent_date TEXT,
    updated_at     TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

# 사용자당 알림 룰 한도(스팸/부하 방지). 요금제 차등 시 단일 변경점.
MAX_ALERT_RULES = 50

VALID_TYPES = {"daily_pct", "target_price", "new_high", "new_low", "rebalance_band"}


def init_alerts_db():
    c = auth_manager._get_conn()
    c.executescript(ALERTS_DDL)
    # 마이그레이션: daily_pct 히스테리시스 상태 (알림 교통정리 2026-07-02)
    cols = [r[1] for r in c.execute("PRAGMA table_info(alert_rules)").fetchall()]
    if "last_state" not in cols:
        c.execute("ALTER TABLE alert_rules ADD COLUMN last_state TEXT")
    if "last_fired_dir" not in cols:
        c.execute("ALTER TABLE alert_rules ADD COLUMN last_fired_dir TEXT")
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


def mark_rule_fired(rule_id, now_iso, new_extreme=None, fired_dir=None):
    """평가 task가 발화 후 호출 — 쿨다운/재무장/방향 추적."""
    c = _conn()
    sets, vals = ["last_triggered_at=?"], [now_iso]
    if new_extreme is not None:
        sets.append("last_extreme=?"); vals.append(new_extreme)
    if fired_dir is not None:
        sets.append("last_fired_dir=?"); vals.append(fired_dir)
    vals.append(rule_id)
    c.execute(f"UPDATE alert_rules SET {', '.join(sets)} WHERE id=?", vals)
    c.commit()


def update_rule_state(rule_id, state):
    """daily_pct 존 상태 저장 — 발화 여부와 무관하게 매 평가 후 호출(히스테리시스 재무장)."""
    c = _conn()
    c.execute("UPDATE alert_rules SET last_state=? WHERE id=?", (state, rule_id))
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
    if not auth_manager.has_push_consent(user_id):
        return False
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
    return True


def get_device_tokens(user_id):
    if not auth_manager.has_push_consent(user_id):
        return []
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
    if not auth_manager.has_push_consent(user_id):
        return False
    return _conn().execute(
        "SELECT 1 FROM device_tokens WHERE user_id=? LIMIT 1", (user_id,)
    ).fetchone() is not None


def delete_user_device_tokens(user_id):
    """사용자 푸시 끄기 — 전 기기 토큰 제거."""
    c = _conn()
    c.execute("DELETE FROM device_tokens WHERE user_id=?", (user_id,))
    c.commit()


# ── 캘린더 일정 알림 설정(cal_alert_prefs) ───────────────

_CAL_DEFAULT = {
    "enabled": 0, "show_econ": 1, "show_earnings": 1, "show_policy": 1,
    "show_dividend": 1, "econ_ids": [], "sources": {}, "excluded": [],
    "last_sent_date": None,
}


def _cal_row_to_dict(r):
    d = dict(r)
    for k in ("econ_ids", "sources", "excluded"):
        try:
            d[k] = json.loads(d[k]) if d.get(k) else _CAL_DEFAULT[k]
        except Exception:
            d[k] = _CAL_DEFAULT[k]
    return d


def get_cal_alert_prefs(user_id):
    """사용자 캘린더 알림 설정. 없으면 기본값(enabled=0)."""
    r = _conn().execute("SELECT * FROM cal_alert_prefs WHERE user_id=?", (user_id,)).fetchone()
    if not r:
        return {"user_id": user_id, **_CAL_DEFAULT}
    return _cal_row_to_dict(r)


def save_cal_alert_prefs(user_id, prefs):
    """업서트. prefs = {enabled, show_*, econ_ids[list], sources{dict}, excluded[list]}."""
    now = datetime.now().isoformat()
    c = _conn()
    c.execute(
        "INSERT INTO cal_alert_prefs (user_id, enabled, show_econ, show_earnings, "
        "show_policy, show_dividend, econ_ids, sources, excluded, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled, "
        "show_econ=excluded.show_econ, show_earnings=excluded.show_earnings, "
        "show_policy=excluded.show_policy, show_dividend=excluded.show_dividend, "
        "econ_ids=excluded.econ_ids, sources=excluded.sources, "
        "excluded=excluded.excluded, updated_at=excluded.updated_at",
        (user_id, int(bool(prefs.get("enabled"))), int(bool(prefs.get("show_econ", 1))),
         int(bool(prefs.get("show_earnings", 1))), int(bool(prefs.get("show_policy", 1))),
         int(bool(prefs.get("show_dividend", 1))),
         json.dumps(prefs.get("econ_ids") or []),
         json.dumps(prefs.get("sources") or {}),
         json.dumps(prefs.get("excluded") or []), now)
    )
    c.commit()


def get_all_cal_alert_enabled():
    """발화 task용 — enabled=1 사용자 prefs 전체."""
    return [_cal_row_to_dict(r) for r in _conn().execute(
        "SELECT * FROM cal_alert_prefs WHERE enabled=1 ORDER BY user_id"
    ).fetchall()]


def mark_cal_alert_sent(user_id, date_str):
    c = _conn()
    c.execute("UPDATE cal_alert_prefs SET last_sent_date=? WHERE user_id=?", (date_str, user_id))
    c.commit()
