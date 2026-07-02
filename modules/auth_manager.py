"""
auth_manager.py
────────────────────────────────────────────────────────────────────────────────
사용자 DB 관리 (data/private/users.db)
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "private" / "users.db"

DDL = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    google_id   TEXT UNIQUE NOT NULL,
    email       TEXT,
    name        TEXT,
    picture     TEXT,
    created_at  TEXT NOT NULL,
    last_login  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id     INTEGER PRIMARY KEY,
    tax         TEXT,
    updated_at  TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

_conn = None


def init_db():
    """앱 시작 시 DB 초기화."""
    global _conn
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    # WAL: 파일 영속 속성(1회 설정 후 유지) — gunicorn 스레드 + celery(alert_store 등)
    # 동시 접근 시 "database is locked" 방지. 새 DB 생성 시에도 자기치유.
    try:
        _conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    _conn.executescript(DDL)
    # 마이그레이션: 홈 화면 위젯 설정(JSON) 컬럼
    cols = [r[1] for r in _conn.execute("PRAGMA table_info(user_settings)").fetchall()]
    if "home_widgets" not in cols:
        _conn.execute("ALTER TABLE user_settings ADD COLUMN home_widgets TEXT")
    if "calendar_config" not in cols:
        _conn.execute("ALTER TABLE user_settings ADD COLUMN calendar_config TEXT")
    # 마이그레이션: 약관·개인정보 동의 시각(최초 1회 동의, 버전 변경 시 재동의 용도)
    ucols = [r[1] for r in _conn.execute("PRAGMA table_info(users)").fetchall()]
    if "agreed_terms_at" not in ucols:
        _conn.execute("ALTER TABLE users ADD COLUMN agreed_terms_at TEXT")
    if "agreed_privacy_at" not in ucols:
        _conn.execute("ALTER TABLE users ADD COLUMN agreed_privacy_at TEXT")
    if "push_consent_at" not in ucols:
        _conn.execute("ALTER TABLE users ADD COLUMN push_consent_at TEXT")
    if "push_revoked_at" not in ucols:
        _conn.execute("ALTER TABLE users ADD COLUMN push_revoked_at TEXT")
    _conn.commit()


def set_user_consent(user_id, push_notifications=False):
    """약관·개인정보 동의 기록(현재 시각)."""
    now = datetime.now().isoformat()
    c = _get_conn()
    if push_notifications:
        c.execute(
            "UPDATE users SET agreed_terms_at=?, agreed_privacy_at=?, "
            "push_consent_at=?, push_revoked_at=NULL WHERE id=?",
            (now, now, now, user_id),
        )
    else:
        c.execute("UPDATE users SET agreed_terms_at=?, agreed_privacy_at=? WHERE id=?",
                  (now, now, user_id))
    c.commit()


def has_consented(user_id):
    """약관·개인정보 모두 동의했는지."""
    row = _get_conn().execute(
        "SELECT agreed_terms_at, agreed_privacy_at FROM users WHERE id=?", (user_id,)
    ).fetchone()
    return bool(row and row["agreed_terms_at"] and row["agreed_privacy_at"])


def set_push_consent(user_id, enabled):
    """서비스 푸시 알림 선택 동의/철회. 광고·마케팅 동의가 아니다."""
    now = datetime.now().isoformat()
    c = _get_conn()
    if enabled:
        c.execute(
            "UPDATE users SET push_consent_at=?, push_revoked_at=NULL WHERE id=?",
            (now, user_id),
        )
    else:
        c.execute(
            "UPDATE users SET push_consent_at=NULL, push_revoked_at=? WHERE id=?",
            (now, user_id),
        )
    c.commit()


def has_push_consent(user_id):
    """서비스 푸시 알림 수신에 명시적으로 동의했는지."""
    row = _get_conn().execute(
        "SELECT push_consent_at FROM users WHERE id=?", (user_id,)
    ).fetchone()
    return bool(row and row["push_consent_at"])


def delete_user(user_id):
    """회원 탈퇴 — 해당 사용자의 모든 개인데이터 삭제(개인정보보호법 이용자 권리)."""
    c = _get_conn()
    for sql in (
        "DELETE FROM holdings WHERE user_id=?",
        "DELETE FROM asset_groups WHERE user_id=?",
        "DELETE FROM saved_portfolios WHERE user_id=?",
        "DELETE FROM alert_rules WHERE user_id=?",
        "DELETE FROM alert_events WHERE user_id=?",
        "DELETE FROM device_tokens WHERE user_id=?",
        "DELETE FROM user_settings WHERE user_id=?",
        "DELETE FROM users WHERE id=?",
    ):
        try:
            c.execute(sql, (user_id,))
        except sqlite3.OperationalError:
            pass  # 테이블 미존재 환경 방어
    c.commit()


def _get_conn():
    global _conn
    if _conn is None:
        init_db()
    return _conn


def get_or_create_user(google_id, email, name, picture):
    """구글 로그인 시 사용자 조회/생성."""
    now = datetime.now().isoformat()
    c   = _get_conn()
    row = c.execute("SELECT * FROM users WHERE google_id=?", (google_id,)).fetchone()
    if row:
        c.execute(
            "UPDATE users SET last_login=?, name=?, picture=? WHERE google_id=?",
            (now, name, picture, google_id)
        )
    else:
        c.execute(
            "INSERT INTO users (google_id, email, name, picture, created_at, last_login) "
            "VALUES (?,?,?,?,?,?)",
            (google_id, email, name, picture, now, now)
        )
    c.commit()
    return dict(c.execute("SELECT * FROM users WHERE google_id=?", (google_id,)).fetchone())


def get_user_by_id(user_id):
    if user_id is None:
        return None
    row = _get_conn().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_settings(user_id):
    row = _get_conn().execute(
        "SELECT tax FROM user_settings WHERE user_id=?", (user_id,)
    ).fetchone()
    if row and row["tax"]:
        return json.loads(row["tax"])
    return {}


def save_settings(user_id, tax):
    now = datetime.now().isoformat()
    c   = _get_conn()
    tax = dict(tax or {})
    existing = get_settings(user_id)
    if "hide_amounts" in existing and "hide_amounts" not in tax:
        tax["hide_amounts"] = existing["hide_amounts"]
    c.execute(
        "INSERT INTO user_settings (user_id, tax, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET tax=excluded.tax, updated_at=excluded.updated_at",
        (user_id, json.dumps(tax, ensure_ascii=False), now)
    )
    c.commit()


# ── 홈 화면 위젯(관심목록) 설정 ───────────────────────────
def get_home_widgets(user_id):
    """저장된 홈 위젯 config(list) 반환. 없으면 None(→ 호출측이 기본값 사용)."""
    row = _get_conn().execute(
        "SELECT home_widgets FROM user_settings WHERE user_id=?", (user_id,)
    ).fetchone()
    if row and row["home_widgets"]:
        return json.loads(row["home_widgets"])
    return None


def get_calendar_config(user_id):
    """캘린더 설정(JSON) 반환. 없으면 None(→ 기본값)."""
    row = _get_conn().execute(
        "SELECT calendar_config FROM user_settings WHERE user_id=?", (user_id,)
    ).fetchone()
    if row and row["calendar_config"]:
        return json.loads(row["calendar_config"])
    return None


def save_calendar_config(user_id, cfg):
    import datetime as _dt
    _get_conn().execute(
        "INSERT INTO user_settings (user_id, calendar_config, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET calendar_config=excluded.calendar_config, "
        "updated_at=excluded.updated_at",
        (user_id, json.dumps(cfg), _dt.datetime.now().isoformat()),
    )
    _get_conn().commit()


def save_home_widgets(user_id, widgets):
    now = datetime.now().isoformat()
    c   = _get_conn()
    c.execute(
        "INSERT INTO user_settings (user_id, home_widgets, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET home_widgets=excluded.home_widgets, "
        "updated_at=excluded.updated_at",
        (user_id, json.dumps(widgets, ensure_ascii=False), now)
    )
    c.commit()


# ── 자산 그룹 + 보유 종목 테이블 ──────────────────────────
HOLDINGS_DDL = """
CREATE TABLE IF NOT EXISTS asset_groups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    color      TEXT DEFAULT '#1976D2',
    target_pct REAL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS holdings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    code         TEXT NOT NULL,
    quantity     REAL NOT NULL DEFAULT 0,
    avg_price    REAL DEFAULT 0,
    manual_price REAL,
    buy_date     TEXT,
    account_type TEXT DEFAULT '일반',
    group_id     INTEGER,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY (user_id)  REFERENCES users(id),
    FOREIGN KEY (group_id) REFERENCES asset_groups(id)
);
"""

def init_holdings_db():
    """보유 종목 테이블 초기화."""
    c = _get_conn()
    c.executescript(HOLDINGS_DDL)
    # 수동 가격 override 컬럼 (기존 DB 마이그레이션)
    try:
        c.execute("ALTER TABLE holdings ADD COLUMN manual_price REAL")
    except Exception:
        pass
    # 매수일 컬럼 (기존 DB 마이그레이션)
    try:
        c.execute("ALTER TABLE holdings ADD COLUMN buy_date TEXT")
    except Exception:
        pass
    c.commit()


# ── 자산 그룹 CRUD ─────────────────────────────────────

def get_groups(user_id):
    return [dict(r) for r in _get_conn().execute(
        "SELECT * FROM asset_groups WHERE user_id=? ORDER BY id", (user_id,)
    ).fetchall()]


def upsert_group(user_id, name, color='#1976D2', target_pct=0, group_id=None):
    now = datetime.now().isoformat()
    c   = _get_conn()
    if group_id:
        c.execute("UPDATE asset_groups SET name=?, color=?, target_pct=? WHERE id=? AND user_id=?",
                  (name, color, target_pct, group_id, user_id))
    else:
        c.execute("INSERT INTO asset_groups (user_id, name, color, target_pct, created_at) VALUES (?,?,?,?,?)",
                  (user_id, name, color, target_pct, now))
    c.commit()


def delete_group(user_id, group_id):
    c = _get_conn()
    c.execute("UPDATE holdings SET group_id=NULL WHERE group_id=? AND user_id=?", (group_id, user_id))
    c.execute("DELETE FROM asset_groups WHERE id=? AND user_id=?", (group_id, user_id))
    c.commit()


# ── 보유 종목 CRUD ─────────────────────────────────────

def get_holdings(user_id):
    return [dict(r) for r in _get_conn().execute(
        "SELECT h.*, g.name as group_name, g.color as group_color, g.target_pct as group_target "
        "FROM holdings h "
        "LEFT JOIN asset_groups g ON h.group_id = g.id "
        "WHERE h.user_id=? ORDER BY h.group_id, h.code",
        (user_id,)
    ).fetchall()]


def upsert_holding(user_id, code, quantity, avg_price, account_type='일반', group_id=None, holding_id=None, buy_date=None):
    now = datetime.now().isoformat()
    c   = _get_conn()
    if holding_id:
        c.execute(
            "UPDATE holdings SET code=?, quantity=?, avg_price=?, account_type=?, group_id=?, buy_date=?, updated_at=? "
            "WHERE id=? AND user_id=?",
            (code, quantity, avg_price, account_type, group_id, buy_date, now, holding_id, user_id)
        )
    else:
        c.execute(
            "INSERT INTO holdings (user_id, code, quantity, avg_price, account_type, group_id, buy_date, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, code, quantity, avg_price, account_type, group_id, buy_date, now, now)
        )
    c.commit()


def delete_holding(user_id, holding_id):
    c = _get_conn()
    c.execute("DELETE FROM holdings WHERE id=? AND user_id=?", (holding_id, user_id))
    c.commit()


def set_manual_price(user_id, holding_id, price):
    """수동 가격 override 설정(KRW). price=None이면 해제 → 자동 시세 복귀."""
    now = datetime.now().isoformat()
    c   = _get_conn()
    c.execute(
        "UPDATE holdings SET manual_price=?, updated_at=? WHERE id=? AND user_id=?",
        (price, now, holding_id, user_id)
    )
    c.commit()


# ── 포트폴리오 즐겨찾기 (B1) ──────────────────────────────
PORTFOLIOS_DDL = """
CREATE TABLE IF NOT EXISTS saved_portfolios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    name         TEXT NOT NULL,
    tickers_json TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

# 사용자당 저장 한도. 추후 요금제별 차등 시 get_portfolio_limit만 바꾸면 됨.
MAX_SAVED_PORTFOLIOS = 20


def get_portfolio_limit(user_id):
    """사용자별 즐겨찾기 한도. 현재는 전원 동일 — 요금제 차등의 단일 변경점."""
    return MAX_SAVED_PORTFOLIOS


def init_portfolios_db():
    """즐겨찾기 테이블 초기화."""
    c = _get_conn()
    c.executescript(PORTFOLIOS_DDL)
    c.commit()


def get_portfolios(user_id):
    rows = _get_conn().execute(
        "SELECT * FROM saved_portfolios WHERE user_id=? ORDER BY name", (user_id,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["tickers"] = json.loads(d.pop("tickers_json"))
        out.append(d)
    return out


def get_portfolio(user_id, portfolio_id):
    row = _get_conn().execute(
        "SELECT * FROM saved_portfolios WHERE id=? AND user_id=?",
        (portfolio_id, user_id)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["tickers"] = json.loads(d.pop("tickers_json"))
    return d


def upsert_portfolio(user_id, name, tickers, portfolio_id=None):
    """저장/수정. 신규 생성 시 한도 초과면 ValueError."""
    now = datetime.now().isoformat()
    c   = _get_conn()
    tickers_json = json.dumps(tickers, ensure_ascii=False)
    if portfolio_id:
        c.execute(
            "UPDATE saved_portfolios SET name=?, tickers_json=?, updated_at=? "
            "WHERE id=? AND user_id=?",
            (name, tickers_json, now, portfolio_id, user_id)
        )
    else:
        count = c.execute(
            "SELECT COUNT(*) FROM saved_portfolios WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        if count >= get_portfolio_limit(user_id):
            raise ValueError(f"즐겨찾기는 최대 {get_portfolio_limit(user_id)}개까지 저장할 수 있어요.")
        c.execute(
            "INSERT INTO saved_portfolios (user_id, name, tickers_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            (user_id, name, tickers_json, now, now)
        )
    c.commit()


def delete_portfolio(user_id, portfolio_id):
    c = _get_conn()
    c.execute("DELETE FROM saved_portfolios WHERE id=? AND user_id=?", (portfolio_id, user_id))
    c.commit()
