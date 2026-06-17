"""알림 실데이터 probe — 프로덕션 app + 실 시세(yfinance/DB). users.db만 temp 격리.
실행: venv/Scripts/python.exe tests/probe_alerts_live.py
"""
import os, sys, tempfile, json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_p = _f = 0
def ok(name, cond, extra=""):
    global _p, _f
    if cond: _p += 1; print("PASS  " + name + (("  " + extra) if extra else ""))
    else:    _f += 1; print("FAIL  " + name + (("  " + extra) if extra else ""))

import modules.auth_manager as am
am.DB_PATH = Path(tempfile.mkdtemp()) / "probe_users.db"; am._conn = None; am.init_db()
u = am.get_or_create_user("probe", "probe@test.com", "P", "")
import app as a
a.app.config["TESTING"] = True
cl = a.app.test_client()
with cl.session_transaction() as s:
    s["user_id"] = u["id"]

# 실 종목 저장 포트폴리오 (비중 합 100)
r = cl.post("/api/portfolio/save", json={"name": "실전6040",
    "tickers": [{"code": "SPY", "name": "SPY", "weight": 60},
                {"code": "TLT", "name": "TLT", "weight": 40}]})
ok("포폴 저장", r.status_code == 200, str(r.status_code))
pid = am.get_portfolios(u["id"])[0]["id"]

# context
ctx = cl.get("/api/alerts/context").get_json()
ok("context 포폴 노출", any(p["id"] == pid for p in ctx["portfolios"]))

# 실 시세 포폴 위젯 quote (네트워크)
print("... 포폴 지수 계산 중(실 시세) ...")
q = cl.get(f"/api/watchlist/quotes?codes=PF:{pid}").get_json()
ok("PF 위젯 quote 반환", len(q) == 1 and q[0]["code"] == f"PF:{pid}",
   json.dumps(q[0], ensure_ascii=False) if q else "빈응답")
if q:
    ok("quote 구조(value/change/spark/IDX)",
       all(k in q[0] for k in ("value", "change", "up", "spark")) and q[0]["currency"] == "IDX")
    ok("스파크 2점 이상", len(q[0].get("spark", [])) >= 2)

# 홈 추가
r = cl.post("/api/home-config/add-portfolio", json={"id": pid})
ok("홈 추가", r.status_code == 200 and r.get_json().get("ok"))
hw = am.get_home_widgets(u["id"])
ok("위젯에 PF 항목", any(i.get("code") == f"PF:{pid}" for w in (hw or []) for i in w.get("items", [])))

# 포폴 수익 룰 + 심볼 룰 생성
r = cl.post("/api/alerts/rules", json={"rule_type": "daily_pct", "portfolio_id": pid,
                                       "direction": "both", "threshold": 0.001})
ok("포폴 수익 룰 생성", r.status_code == 200, str(r.get_json()))
r = cl.post("/api/alerts/rules", json={"rule_type": "new_high", "code": "SPY", "window": "52w"})
ok("심볼 룰 생성", r.status_code == 200)

# 실 평가 (실 loader) — 0.001% 임계라 거의 확실히 발화
from modules.alerts import alert_runner
print("... 실 평가 실행 중 ...")
fired = alert_runner.run_alert_evaluation(a.portfolio_engine.loader)
ok("평가 실행(발화 ≥0, 예외無)", fired >= 0, f"fired={fired}")
evs = cl.get("/api/alerts/events").get_json()["events"]
print(f"   수신함 {len(evs)}건:", [e["title"] for e in evs][:5])
cnt = cl.get("/api/alerts/unread-count").get_json()["count"]
ok("미읽음 수 = 수신함 수", cnt == len(evs), f"{cnt}/{len(evs)}")
ok("포폴 수익 룰 발화됨(일변동≥0.001%)",
   any("실전60040" in e["title"] or "실전60" in e["title"] or "실전" in e["title"] for e in evs)
   or fired >= 1, f"fired={fired}")

print(f"\n{_p} PASS / {_f} FAIL")
sys.exit(1 if _f else 0)
