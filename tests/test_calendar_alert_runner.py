"""
calendar_alert_runner 결정론 검증 — 거시지표·통화정책 전용(실적·배당락 이관 후).
market_calendar 조회는 스텁(네트워크 0). 실행: python tests/test_calendar_alert_runner.py
"""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_p = _f = 0
def ok(name, cond):
    global _p, _f
    if cond: _p += 1; print("PASS  " + name)
    else:    _f += 1; print("FAIL  " + name)

import modules.auth_manager as am
am.DB_PATH = Path(tempfile.mkdtemp()) / "t_users.db"
am._conn = None
am.init_db()

from modules.alerts import alert_store, calendar_alert_runner as CAR
alert_store.init_alerts_db()

UID = 21
TODAY = "2026-08-20"

CAR.market_calendar = type("MC", (), {
    "econ_events": staticmethod(lambda ids: [
        {"date": TODAY, "type": "econ", "title": "🇺🇸 소비자물가 CPI", "rid": 10}
    ] if 10 in set(ids or []) else []),
    "policy_events": staticmethod(lambda: [
        {"date": TODAY, "type": "policy", "title": "🇺🇸 FOMC (기준금리 결정)"}
    ]),
})()


def prefs(**kw):
    base = {"user_id": UID, "enabled": 1, "show_econ": 1, "show_policy": 1,
            "econ_ids": [10], "last_sent_date": None}
    base.update(kw)
    return [base]


fired = CAR.run_calendar_alerts(today=TODAY, prefs_list=prefs())
ok("거시 2건 발화", fired == 1)
ev = alert_store.get_events(UID, limit=1)[0]
ok("묶음 제목 2건", ev["title"] == "📅 오늘의 증시 일정 2건")
ok("본문에 CPI+FOMC", "CPI" in ev["body"] and "FOMC" in ev["body"])

fired = CAR.run_calendar_alerts(today=TODAY, prefs_list=prefs(show_policy=0))
ok("통화정책 끄면 경제지표만", fired == 1)
ok("본문 CPI만", "FOMC" not in alert_store.get_events(UID, limit=1)[0]["body"])

fired = CAR.run_calendar_alerts(today=TODAY, prefs_list=prefs(show_econ=0, show_policy=0))
ok("둘 다 끄면 무발화", fired == 0)

fired = CAR.run_calendar_alerts(today=TODAY, prefs_list=prefs(last_sent_date=TODAY))
ok("당일 재발송 차단", fired == 0)

fired = CAR.run_calendar_alerts(today="2026-08-25", prefs_list=prefs())
ok("일정 없는 날 무발화", fired == 0)

print(f"\n{_p} PASS / {_f} FAIL")
sys.exit(1 if _f else 0)
