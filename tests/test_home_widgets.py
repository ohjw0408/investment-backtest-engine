"""
홈 위젯(관심목록) 백엔드 검증 — auth_manager 저장 + _clean_home_widgets + 라우트 + quote.
실행: python tests/test_home_widgets.py
"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_p = _f = 0
def ok(name, cond):
    global _p, _f
    if cond: _p += 1; print("PASS  " + name)
    else:    _f += 1; print("FAIL  " + name)


# ── 1. auth_manager 저장/조회 (격리 temp DB) ──
import modules.auth_manager as am
am.DB_PATH = Path(tempfile.mkdtemp()) / "t_users.db"
am._conn = None
am.init_db()

ok("미설정 시 get_home_widgets None", am.get_home_widgets(1) is None)
W = [{"key": "w_market", "name": "시장 지수",
      "items": [{"code": "^GSPC", "name": "S&P 500"}, {"code": "TLT", "name": "美국채"}]}]
am.save_home_widgets(1, W)
got = am.get_home_widgets(1)
ok("저장 왕복 일치", got == W)
am.save_home_widgets(1, [{"key": "x", "name": "변경", "items": [{"code": "QQQ", "name": "Q"}]}])
ok("재저장 덮어쓰기", am.get_home_widgets(1)[0]["name"] == "변경")
ok("home_widgets는 tax와 독립(다른 user)", am.get_home_widgets(2) is None)

# ── 2. _clean_home_widgets 검증 (app import) ──
import app as appmod
clean = appmod._clean_home_widgets

c, e = clean([{"name": "리스트1", "items": [{"code": "spy", "name": "S&P"}]}])
ok("정상 → cleaned, code 대문자화", e is None and c[0]["items"][0]["code"] == "SPY")
ok("정상 → key 자동부여", e is None and c[0]["key"])
_, e = clean([])
ok("빈 위젯 → 에러", e is not None)
_, e = clean([{"name": "", "items": [{"code": "X"}]}])
ok("빈 이름 → 에러", e is not None)
_, e = clean([{"name": "a", "items": []}])
ok("종목 0개 → 에러", e is not None)
_, e = clean([{"name": "a", "items": [{"name": "코드없음"}]}])
ok("code 없는 종목 → 에러", e is not None)
_, e = clean([{"name": "a", "items": [{"code": "X"}]}] * 11)
ok("위젯 11개 → 에러", e is not None)

# ── 3. 라우트 (test_client, 세션 직접 주입) ──
appmod.app.config["TESTING"] = True
cl = appmod.app.test_client()

r = cl.get("/api/home-config")
j = r.get_json()
ok("GET 비로그인 → 기본 위젯", r.status_code == 200 and j["logged_in"] is False
   and j["widgets"][0]["items"][0]["code"] == "^GSPC")

r = cl.post("/api/home-config", json={"widgets": [{"name": "a", "items": [{"code": "SPY"}]}]})
ok("POST 비로그인 → 401", r.status_code == 401)

with cl.session_transaction() as s:
    s["user_id"] = 999999
r = cl.post("/api/home-config", json={"widgets": []})
ok("POST 로그인+잘못된 바디 → 400", r.status_code == 400)

# ── 4. _watchlist_quote 통합 (네트워크/DB — 관대) ──
q = appmod._watchlist_quote("^GSPC")
if q is None:
    print("SKIP  _watchlist_quote(^GSPC) None (오프라인/데이터없음)")
else:
    ok("quote 구조 (value/change/up/spark/name)",
       all(k in q for k in ("value", "change", "up", "spark", "name")))
    ok("quote code 대문자", q["code"] == "^GSPC")

print(f"\n{_p} PASS / {_f} FAIL")
sys.exit(1 if _f else 0)
