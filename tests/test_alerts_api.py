"""
알림 룰 + 수신함 API/스토어 검증 (격리 temp DB, test_client).
실행: python tests/test_alerts_api.py
"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_p = _f = 0
def ok(name, cond):
    global _p, _f
    if cond: _p += 1; print("PASS  " + name)
    else:    _f += 1; print("FAIL  " + name)

# temp DB로 전환 후 app import (모듈 로드 시 init_*_db 가 temp DB에 생성됨)
import modules.auth_manager as am
am.DB_PATH = Path(tempfile.mkdtemp()) / "t_users.db"
am._conn = None
am.init_db()

from modules.alerts import alert_store
import app as appmod

UID = 4242

# ── 1. 스토어 직접 ──
rid = alert_store.create_rule(UID, scope="symbol", rule_type="daily_pct",
                              code="TSLA", direction="up", threshold=5)
ok("create_rule 반환 id", isinstance(rid, int) and rid > 0)
ok("get_rules 조회", len(alert_store.get_rules(UID)) == 1)
ok("get_all_enabled_rules", len(alert_store.get_all_enabled_rules()) == 1)

alert_store.update_rule(UID, rid, enabled=0)
ok("update enabled=0", alert_store.get_rules(UID)[0]["enabled"] == 0)
ok("enabled_only 제외", len(alert_store.get_rules(UID, enabled_only=True)) == 0)

alert_store.mark_rule_fired(rid, "2026-06-17T14:00:00", new_extreme=123.4)
row = alert_store.get_rules(UID)[0]
ok("mark_rule_fired 기록", row["last_triggered_at"] and row["last_extreme"] == 123.4)

# 수신함
eid = alert_store.add_event(UID, "제목", "본문", code="TSLA", rule_id=rid, meta={"price": 100})
ok("add_event", isinstance(eid, int))
ok("unread_count=1", alert_store.unread_count(UID) == 1)
ev = alert_store.get_events(UID)[0]
ok("event meta json 복원", ev["meta"]["price"] == 100)
alert_store.mark_read(UID, eid)
ok("mark_read → unread 0", alert_store.unread_count(UID) == 0)

# 한도 (별도 UID로 격리 — 본 UID 룰 수에 영향 X)
UID_LIMIT = 9999
hit_limit = False
for i in range(alert_store.MAX_ALERT_RULES + 5):
    try:
        alert_store.create_rule(UID_LIMIT, scope="symbol", rule_type="target_price",
                                code=f"T{i}", direction="above", threshold=10)
    except ValueError:
        hit_limit = True
        break
ok("MAX_ALERT_RULES 한도 ValueError",
   hit_limit and alert_store.count_rules(UID_LIMIT) == alert_store.MAX_ALERT_RULES)

# ── 2. 입력 검증 ──
v = appmod._validate_alert_payload
_, e = v({"rule_type": "bogus"})
ok("알 수 없는 타입 → 에러", e is not None)
c, e = v({"rule_type": "daily_pct", "code": "spy", "direction": "up", "threshold": 5})
ok("daily_pct 정상 → code 대문자", e is None and c["code"] == "SPY")
_, e = v({"rule_type": "daily_pct", "code": "SPY", "direction": "sideways", "threshold": 5})
ok("잘못된 방향 → 에러", e is not None)
_, e = v({"rule_type": "daily_pct", "code": "SPY", "direction": "up", "threshold": 200})
ok("변동률 200% → 에러", e is not None)
_, e = v({"rule_type": "target_price", "code": "SPY", "direction": "above", "threshold": -1})
ok("목표가 음수 → 에러", e is not None)
c, e = v({"rule_type": "new_high", "code": "SPY", "window": "52w"})
ok("new_high 정상", e is None and c["window"] == "52w")
_, e = v({"rule_type": "new_high", "code": "SPY", "window": "10y"})
ok("잘못된 윈도우 → 에러", e is not None)
c, e = v({"rule_type": "rebalance_band", "threshold": 5})
ok("rebalance 정상 → scope portfolio", e is None and c["scope"] == "portfolio")
_, e = v({"rule_type": "rebalance_band", "threshold": 0})
ok("rebalance 밴드 0 → 에러", e is not None)

# ── 3. 라우트(test_client) ──
appmod.app.config["TESTING"] = True
cl = appmod.app.test_client()

ok("GET rules 비로그인 → 401", cl.get("/api/alerts/rules").status_code == 401)
ok("unread-count 비로그인 → count 0",
   cl.get("/api/alerts/unread-count").get_json()["count"] == 0)

with cl.session_transaction() as s:
    s["user_id"] = UID
r = cl.post("/api/alerts/rules",
            json={"rule_type": "new_low", "code": "QQQ", "window": "all"})
ok("POST 룰 생성 200", r.status_code == 200 and r.get_json().get("ok"))
r = cl.post("/api/alerts/rules", json={"rule_type": "daily_pct", "code": "SPY"})
ok("POST 불완전 룰 → 400", r.status_code == 400)
new_id = None
for rr in cl.get("/api/alerts/rules").get_json()["rules"]:
    if rr["code"] == "QQQ":
        new_id = rr["id"]
ok("생성된 룰 조회됨", new_id is not None)
r = cl.patch(f"/api/alerts/rules/{new_id}", json={"enabled": False})
ok("PATCH 토글 200", r.status_code == 200)
r = cl.delete(f"/api/alerts/rules/{new_id}")
ok("DELETE 200", r.status_code == 200)
ok("삭제 반영",
   all(rr["code"] != "QQQ" for rr in cl.get("/api/alerts/rules").get_json()["rules"]))

# ── 4. /api/alerts/context ──
am.init_holdings_db(); am.init_portfolios_db()
am.upsert_holding(UID, "AAPL", quantity=10, avg_price=100)
am.upsert_portfolio(UID, "성장주", [{"code": "NVDA", "name": "엔비디아"}, {"code": "MSFT", "name": "MS"}])
ctx = cl.get("/api/alerts/context").get_json()
ok("context holdings 포함", any(h["code"] == "AAPL" for h in ctx["holdings"]))
ok("context portfolios 구조",
   ctx["portfolios"] and ctx["portfolios"][0]["name"] == "성장주"
   and any(s["code"] == "NVDA" for s in ctx["portfolios"][0]["symbols"]))
ok("context 비로그인 → logged_in False",
   __import__("app").app.test_client().get("/api/alerts/context").get_json()["logged_in"] is False)

# ── 5. 포트폴리오 수익 룰 검증 + 홈 추가 ──
c, e = v({"rule_type": "daily_pct", "portfolio_id": 3, "direction": "up", "threshold": 3})
ok("포폴 daily_pct 정상 → scope portfolio", e is None and c["scope"] == "portfolio" and c["portfolio_id"] == 3)
c, e = v({"rule_type": "new_high", "portfolio_id": 3, "window": "all"})
ok("포폴 신고가 정상", e is None and c["window"] == "all")
_, e = v({"rule_type": "target_price", "portfolio_id": 3, "direction": "above", "threshold": 100})
ok("포폴 목표가 → 미지원 에러", e is not None)

# 홈 추가
pid_api = None
for p in __import__("modules.auth_manager", fromlist=["get_portfolios"]).get_portfolios(UID):
    if p["name"] == "성장주":
        pid_api = p["id"]
r = cl.post("/api/home-config/add-portfolio", json={"id": pid_api})
ok("홈 추가 200", r.status_code == 200 and r.get_json().get("ok"))
r = cl.post("/api/home-config/add-portfolio", json={"id": pid_api})
ok("홈 재추가 → already", r.get_json().get("already") is True)
hw = __import__("modules.auth_manager", fromlist=["get_home_widgets"]).get_home_widgets(UID)
ok("위젯에 PF 항목 존재",
   any(i.get("code") == f"PF:{pid_api}" for w in (hw or []) for i in w.get("items", [])))

print(f"\n{_p} PASS / {_f} FAIL")
sys.exit(1 if _f else 0)
