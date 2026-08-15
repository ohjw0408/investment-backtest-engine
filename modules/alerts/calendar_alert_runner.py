"""
calendar_alert_runner.py
────────────────────────────────────────────────────────────────────────────────
증시 캘린더 일정 알림 발화 — 매일 1회(08:00 KST). 그날 일정이 있으면 수신함 + 푸시.
워커(별 프로세스)에서 동작 — Flask app import 없음.

이벤트 종류: econ(경제지표) · policy(통화정책) — **거시 일정 전용**.
실적·배당락은 2026-08-15에 종목 알림 룰로 이관됐다(modules/alerts/symbol_event_runner.py).
종목 일정을 여기서 다루던 시절의 "대상 종목 선택"(sources/excluded)은 제거됐다 —
전역 코드 집합이라 한 그룹에서 끄면 다른 그룹의 같은 종목까지 죽는 구조였다.
"""

import datetime

from modules.alerts import alert_store
from modules import market_calendar


def kst_today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date().isoformat()


def _compose(events):
    n = len(events)
    titles = [e.get("title", "일정") for e in events]
    body = " · ".join(titles[:3]) + (f" 외 {n - 3}건" if n > 3 else "")
    return f"📅 오늘의 증시 일정 {n}건", body


def run_calendar_alerts(loader=None, today=None, prefs_list=None):
    """enabled 사용자별 오늘 거시 일정 → 수신함 + 푸시(묶음 1건). 발화 사용자 수 반환.

    loader는 쓰지 않지만 호출부(tasks.evaluate_calendar_alerts) 시그니처 보존용으로 받는다.
    """
    today = today or kst_today()
    users = prefs_list if prefs_list is not None else alert_store.get_all_cal_alert_enabled()
    fired = 0
    for prefs in users:
        uid = prefs.get("user_id")
        try:
            if prefs.get("last_sent_date") == today:
                continue  # 당일 이미 발송(안전망)
            evs = []
            if prefs.get("show_econ"):
                evs += market_calendar.econ_events(set(prefs.get("econ_ids") or []))
            if prefs.get("show_policy"):
                evs += market_calendar.policy_events()
            todays = [e for e in evs if e.get("date") == today]
            if not todays:
                continue
            title, body = _compose(todays)
            alert_store.add_event(uid, title, body,
                                  meta={"cal": True, "type": "calendar", "target_url": "/calendar",
                                        "date": today, "count": len(todays)})
            alert_store.mark_cal_alert_sent(uid, today)
            fired += 1
            try:
                from modules.alerts import push_sender
                push_sender.send_to_user(uid, title, body,
                                         data={"type": "calendar", "target_url": "/calendar"})
            except Exception as pe:
                print(f"[cal_alert] user {uid} 푸시 실패(무시): {pe}")
        except Exception as e:
            print(f"[cal_alert] user {uid} 오류: {e}")
    return fired
