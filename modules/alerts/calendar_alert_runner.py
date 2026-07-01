"""
calendar_alert_runner.py
────────────────────────────────────────────────────────────────────────────────
증시 캘린더 일정 알림 발화 — 매일 1회(08:00 KST). 그날 일정이 있으면 수신함 + 푸시.
워커(별 프로세스)에서 동작 — Flask app import 없음. 종목 그룹은 auth_manager 직접 조회.

이벤트 종류: econ(경제지표) · policy(통화정책) · earnings(실적) · dividend(배당락).
종목(earnings·dividend)은 알림 전용 prefs.sources/excluded 적용(캘린더 설정과 독립).
"""

import datetime
from collections import OrderedDict

from modules.alerts import alert_store
from modules import auth_manager, market_calendar


def kst_today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date().isoformat()


def _user_groups(uid):
    """알림용 종목 소스 그룹(holdings·pf:<id>·watchlist) + 이름맵. app `_calendar_grouped` 워커 복제."""
    groups = OrderedDict()
    groups["holdings"] = []
    names = {}
    try:
        for h in auth_manager.get_holdings(uid):
            if h.get("code"):
                groups["holdings"].append(str(h["code"]))
    except Exception:
        pass
    try:
        for pf in auth_manager.get_portfolios(uid):
            codes = []
            for t in pf.get("tickers", []):
                if isinstance(t, dict) and t.get("code"):
                    c = str(t["code"]); codes.append(c)
                    if t.get("name"):
                        names.setdefault(c, t["name"])
            if codes:
                groups["pf:%s" % pf["id"]] = codes
    except Exception:
        pass
    groups["watchlist"] = []
    try:
        for w in (auth_manager.get_home_widgets(uid) or []):
            for it in (w.get("items") or []):
                if isinstance(it, dict) and it.get("code"):
                    c = str(it["code"]); groups["watchlist"].append(c)
                    if it.get("name"):
                        names.setdefault(c, it["name"])
    except Exception:
        pass
    for k in groups:
        groups[k] = list(dict.fromkeys(groups[k]))
    return groups, names


def _alert_codes(uid, prefs):
    """prefs(소스 on/off + 개별 제외) 적용해 알림 대상 종목 코드 + 이름맵."""
    groups, names = _user_groups(uid)
    src = prefs.get("sources") or {}
    excl = set(prefs.get("excluded") or [])
    codes = []
    for g in groups:
        if src.get(g, True):
            codes += groups[g]
    return [c for c in dict.fromkeys(codes) if c not in excl][:60], names


def _compose(events):
    n = len(events)
    titles = [e.get("title", "일정") for e in events]
    body = " · ".join(titles[:3]) + (f" 외 {n - 3}건" if n > 3 else "")
    return f"📅 오늘의 증시 일정 {n}건", body


def run_calendar_alerts(loader, today=None, prefs_list=None):
    """enabled 사용자별 오늘 일정 → 수신함 + 푸시(묶음 1건). 발화 사용자 수 반환."""
    today = today or kst_today()
    users = prefs_list if prefs_list is not None else alert_store.get_all_cal_alert_enabled()
    fired = 0
    for prefs in users:
        uid = prefs.get("user_id")
        try:
            if prefs.get("last_sent_date") == today:
                continue  # 당일 이미 발송(안전망)
            need_sym = prefs.get("show_earnings") or prefs.get("show_dividend")
            codes, names = _alert_codes(uid, prefs) if need_sym else ([], {})
            econ_ids = set(prefs.get("econ_ids") or []) if prefs.get("show_econ") else set()
            evs = market_calendar.events_for(
                codes, loader, econ_ids=econ_ids,
                show_earnings=bool(prefs.get("show_earnings")),
                show_dividend=bool(prefs.get("show_dividend")), names=names)
            kinds = set()
            if prefs.get("show_econ"):
                kinds.add("econ")
            if prefs.get("show_policy"):
                kinds.add("policy")
            if prefs.get("show_earnings"):
                kinds.add("earnings")
            if prefs.get("show_dividend"):
                kinds.add("dividend")
            todays = [e for e in evs if e.get("date") == today and e.get("type") in kinds]
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
