"""포트폴리오 즐겨찾기 (B1) — auth_manager CRUD + /api/portfolio/* 라우트.

users.db를 임시 경로로 돌려 실제 dev DB를 오염시키지 않는다 (app import 전에 패치).
"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import modules.auth_manager as am

_TMP = Path(tempfile.mkdtemp(prefix="mm_fav_test_"))
am.DB_PATH = _TMP / "users.db"
am._conn = None

from app import app  # noqa: E402  (패치 후 import — init_*_db가 임시 DB에 생성)

app.config["TESTING"] = True


def _user(google_id, email):
    return am.get_or_create_user(google_id, email, email.split("@")[0], "")["id"]


UID_A = _user("g-a", "a@test.com")
UID_B = _user("g-b", "b@test.com")

TICKERS = [
    {"code": "069500", "name": "KODEX 200", "badge": "KR ETF", "weight": 60},
    {"code": "458730", "name": "TIGER 미국배당다우존스", "badge": "KR ETF", "weight": 40},
]


def _client(uid=None):
    c = app.test_client()
    if uid is not None:
        with c.session_transaction() as s:
            s["user_id"] = uid
    return c


def _clear(uid):
    for p in am.get_portfolios(uid):
        am.delete_portfolio(uid, p["id"])


# ── 1. 비로그인 401 ──────────────────────────────────────
def test_requires_login():
    c = _client()
    assert c.get("/api/portfolio/list").status_code == 401
    assert c.post("/api/portfolio/save", json={"name": "x", "tickers": TICKERS}).status_code == 401
    assert c.delete("/api/portfolio/1").status_code == 401


# ── 2. 저장 → 목록 → 수정 → 삭제 왕복 ─────────────────────
def test_save_list_update_delete_roundtrip():
    _clear(UID_A)
    c = _client(UID_A)

    r = c.post("/api/portfolio/save", json={"name": "성장형", "tickers": TICKERS})
    assert r.status_code == 200 and r.get_json()["ok"]

    items = c.get("/api/portfolio/list").get_json()
    assert len(items) == 1
    p = items[0]
    assert p["name"] == "성장형"
    assert p["tickers"] == TICKERS  # 한글 이름·badge·weight 그대로 왕복

    # id 지정 수정 — 이름·구성 교체, 개수 불변
    new_tickers = [{"code": "SPY", "name": "SPY", "badge": "US ETF", "weight": 100}]
    r = c.post("/api/portfolio/save",
               json={"id": p["id"], "name": "미국형", "tickers": new_tickers})
    assert r.status_code == 200
    items = c.get("/api/portfolio/list").get_json()
    assert len(items) == 1
    assert items[0]["name"] == "미국형"
    assert items[0]["tickers"][0]["code"] == "SPY"

    assert c.delete(f"/api/portfolio/{p['id']}").status_code == 200
    assert c.get("/api/portfolio/list").get_json() == []


# ── 3. 입력 검증 400 ─────────────────────────────────────
def test_validation_errors():
    _clear(UID_A)
    c = _client(UID_A)
    bad = [
        {"name": "", "tickers": TICKERS},                       # 빈 이름
        {"name": "x" * 51, "tickers": TICKERS},                 # 이름 51자
        {"name": "ok", "tickers": []},                          # 종목 0개
        {"name": "ok", "tickers": "not-a-list"},                # 리스트 아님
        {"name": "ok", "tickers": [{"weight": 50}]},            # code 없음
        {"name": "ok", "tickers": [{"code": "SPY", "weight": "abc"}]},  # 비중 비숫자
        {"name": "ok", "tickers": [{"code": "SPY", "weight": 1}] * 31}, # 31개 초과
    ]
    for body in bad:
        assert c.post("/api/portfolio/save", json=body).status_code == 400, body
    assert c.get("/api/portfolio/list").get_json() == []


# ── 4. 한도: 신규 생성만 차단, 수정은 허용 ─────────────────
def test_limit_blocks_create_not_update(monkeypatch):
    _clear(UID_A)
    monkeypatch.setattr(am, "get_portfolio_limit", lambda uid: 3)
    c = _client(UID_A)

    for i in range(3):
        assert c.post("/api/portfolio/save",
                      json={"name": f"p{i}", "tickers": TICKERS}).status_code == 200
    r = c.post("/api/portfolio/save", json={"name": "p3", "tickers": TICKERS})
    assert r.status_code == 400
    assert "최대 3개" in r.get_json()["error"]

    # 한도 도달 상태에서도 기존 항목 수정은 가능
    pid = c.get("/api/portfolio/list").get_json()[0]["id"]
    assert c.post("/api/portfolio/save",
                  json={"id": pid, "name": "p0-수정", "tickers": TICKERS}).status_code == 200
    _clear(UID_A)


# ── 5. 소유권 격리 ───────────────────────────────────────
def test_ownership_isolation():
    _clear(UID_A)
    _clear(UID_B)
    ca = _client(UID_A)
    cb = _client(UID_B)

    ca.post("/api/portfolio/save", json={"name": "A의것", "tickers": TICKERS})
    pid = ca.get("/api/portfolio/list").get_json()[0]["id"]

    # B 목록엔 안 보임, B가 A의 id를 지워도 A 것은 남음(user_id 스코프)
    assert cb.get("/api/portfolio/list").get_json() == []
    cb.delete(f"/api/portfolio/{pid}")
    assert len(ca.get("/api/portfolio/list").get_json()) == 1
    _clear(UID_A)
