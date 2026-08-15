"""
symbol_event_runner.py
────────────────────────────────────────────────────────────────────────────────
종목 일정 알림 발화 — 실적 발표 · 배당락일(+계좌별 예상 배당금). 매일 1회(08:05 KST).
워커(별 프로세스)에서 동작 — Flask app import 없음.

2026-08-15 신설. 실적·배당락은 원래 증시 캘린더 알림(거시지표)에 얹혀 있었는데,
① 대상 종목을 전역 excluded 집합으로 고르는 구조라 한 그룹에서 끄면 같은 코드가 든
다른 그룹까지 죽었고 ② 거시 일정과 한 통에 묶여 본문 앞 3건에 밀려 잘려나갔다.
그래서 일반 종목 알림과 같은 룰(alert_rules)로 옮기고 발화 레인도 분리했다.

룰 규약 (기존 컬럼 재사용):
  rule_type = 'earnings' | 'dividend'
  scope     = 'holdings'(보유 종목 전체, code=NULL) | 'symbol'(code 지정)
  window    = 'd0'(당일) | 'd1'(하루 전)
  direction = 'amount'(배당 전용 — 계좌별·종목별 예상 배당금 동봉) | None

⚠️ 배당 '지급일'은 다루지 않는다. 데이터 소스(yfinance)가 지급일을 주는 건 미국
개별주의 다음 1회뿐이고 ETF·한국 종목은 아예 없다(2026-08-15 실측). 따라서 금액은
'배당락일 기준 예상 배당금'이며 실제 입금일과 다르다 — 본문에 그대로 표기한다.
"""

import datetime
from concurrent.futures import ThreadPoolExecutor

from modules.alerts import alert_store
from modules.alerts.alert_runner import _display_name
from modules import auth_manager, market_calendar
from modules.dividend_history import EXEMPT_ACCOUNTS, KR_DIV_TAX, US_DIV_TAX

EVENT_TYPES = ("earnings", "dividend")
MAX_CODES = 60      # 룰 1개가 훑는 종목 상한(yfinance 호출 폭주 방지)
MAX_LIST = 5        # 본문에 이름을 나열할 최대 종목 수


def kst_today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date()


def _target_date(rule, today):
    """window='d1'이면 '내일 일정'을 하루 전에 알린다."""
    return today + datetime.timedelta(days=1) if rule.get("window") == "d1" else today


def _holding_rows(uid):
    try:
        return [h for h in auth_manager.get_holdings(uid) if h.get("code")]
    except Exception:
        return []


def _rule_codes(rule, holdings):
    if rule.get("scope") == "symbol" and rule.get("code"):
        return [str(rule["code"]).upper()]
    return list(dict.fromkeys(str(h["code"]).upper() for h in holdings))[:MAX_CODES]


# ── 일정 조회(사용자 간 캐시) ───────────────────────────

def _earnings_for(codes, cache):
    todo = [c for c in codes if c not in cache]
    if todo:
        market_calendar._load_earn_disk()   # 오늘자 디스크캐시 주입 → yfinance 재조회 회피
        with ThreadPoolExecutor(max_workers=min(8, len(todo))) as ex:
            for c, evs in zip(todo, ex.map(
                    lambda x: market_calendar.earnings_events(x, _display_name(x)), todo)):
                cache[c] = evs
        market_calendar._save_earn_disk()
    return [e for c in codes for e in cache.get(c, [])]


def _dividends_for(loader, codes, cache):
    key = tuple(sorted(codes))
    if key not in cache:
        cache[key] = market_calendar.dividend_events(
            loader, list(codes), {c: _display_name(c) for c in codes})
    return cache[key]


# ── 배당 금액(계좌별·종목별) ────────────────────────────

def _div_tax(loader, code, account):
    """계좌 성격별 배당소득세율. ISA·연금저축·IRP = 운용 중 비과세(dividend_history 규약)."""
    if (account or "일반") in EXEMPT_ACCOUNTS:
        return 0.0
    try:
        is_kr = bool(loader.is_kr_etf(code))
    except Exception:
        is_kr = str(code).isdigit()
    return KR_DIV_TAX if is_kr else US_DIV_TAX


def _dividend_amounts(loader, events, holdings):
    """배당락 이벤트(1주당 원화 세전) × 보유 수량 → (종목별, 계좌별, 합계) 세후 원화."""
    dps = {}
    for e in events:
        v = e.get("dps_krw")
        if v:
            dps[str(e.get("symbol") or "").upper()] = float(v)
    by_code, by_account, total = {}, {}, 0.0
    for h in holdings:
        code = str(h.get("code") or "").upper()
        qty = float(h.get("quantity") or 0)
        if qty <= 0 or code not in dps:
            continue
        acct = h.get("account_type") or "일반"
        net = qty * dps[code] * (1 - _div_tax(loader, code, acct))
        by_code[code] = by_code.get(code, 0.0) + net
        by_account[acct] = by_account.get(acct, 0.0) + net
        total += net
    return by_code, by_account, total


# ── 문안 ────────────────────────────────────────────────

def _won(v):
    return f"{v:,.0f}원"


def _names_line(names, unit):
    head = " · ".join(names[:MAX_LIST])
    return head + (f" 외 {len(names) - MAX_LIST}{unit}" if len(names) > MAX_LIST else "")


def _compose_earnings(events, when):
    names = [_display_name(e.get("symbol") or "") for e in events]
    title = (f"📊 {when} 실적 발표 — {names[0]}" if len(names) == 1
             else f"📊 {when} 실적 발표 {len(names)}건")
    return title, _names_line(names, "건")


def _compose_dividend(events, when, amounts=None):
    names = [_display_name(e.get("symbol") or "") for e in events]
    title = (f"💰 {when} 배당락 — {names[0]}" if len(names) == 1
             else f"💰 {when} 배당락 {len(names)}종")
    lines = [_names_line(names, "종")]
    if amounts:
        by_code, by_account, total = amounts
        title += f" · 예상 배당 {_won(total)}"
        lines.append("종목별 " + " · ".join(
            f"{_display_name(c)} {_won(v)}"
            for c, v in sorted(by_code.items(), key=lambda x: -x[1])[:MAX_LIST]))
        lines.append("계좌별 " + " · ".join(
            f"{a} {_won(v)}" for a, v in sorted(by_account.items(), key=lambda x: -x[1])))
        lines.append("세후 원화 환산 · 배당락일 기준 예상액이며 실제 입금일은 종목별 지급일이에요.")
    elif any(e.get("projected") for e in events):
        lines.append("과거 배당 패턴으로 추정한 예상일이 포함돼 있어요.")
    return title, "\n".join(lines)


def _target_url(rule):
    if rule.get("scope") == "symbol" and rule.get("code"):
        return "/symbol/%s" % str(rule["code"]).upper()
    return "/myassets" if rule.get("rule_type") == "dividend" else "/calendar"


# ── 발화 ────────────────────────────────────────────────

def run_symbol_event_alerts(loader, today=None, rules=None):
    """enabled 실적·배당 룰 평가 → 수신함 + 푸시. 발화 건수 반환."""
    today = today or kst_today()
    if isinstance(today, str):
        today = datetime.date.fromisoformat(today)
    tk = today.isoformat()
    if rules is None:
        rules = [r for r in alert_store.get_all_enabled_rules()
                 if r.get("rule_type") in EVENT_TYPES]
    if not rules:
        return 0

    # last_triggered_at의 날짜 부분 = 평가 기준 KST 날짜. 서버 로컬(UTC) 날짜를 쓰면
    # 08:05 KST = 전날 23:05 UTC라 같은 KST 날짜에 재실행돼도 중복 차단이 안 걸린다.
    now_iso = datetime.datetime.combine(today, datetime.datetime.now().time()).isoformat()
    holdings_cache, earn_cache, div_cache = {}, {}, {}
    fired = 0
    for r in rules:
        uid = r.get("user_id")
        try:
            if str(r.get("last_triggered_at") or "")[:10] == tk:
                continue    # 하루 1회(beat 중복 실행 안전망)
            if uid not in holdings_cache:
                holdings_cache[uid] = _holding_rows(uid)
            holdings = holdings_cache[uid]
            codes = _rule_codes(r, holdings)
            if not codes:
                continue
            target = _target_date(r, today).isoformat()
            when = "오늘" if target == tk else "내일"

            if r["rule_type"] == "earnings":
                evs = [e for e in _earnings_for(codes, earn_cache) if e.get("date") == target]
                if not evs:
                    continue
                title, body = _compose_earnings(evs, when)
            else:
                evs = [e for e in _dividends_for(loader, codes, div_cache)
                       if e.get("date") == target]
                if not evs:
                    continue
                amounts = (_dividend_amounts(loader, evs, holdings)
                           if r.get("direction") == "amount" else None)
                if amounts and amounts[2] <= 0:
                    amounts = None      # 보유 수량이 없으면 금액 없이 일정만
                title, body = _compose_dividend(evs, when, amounts)

            url = _target_url(r)
            meta = {"type": r["rule_type"], "rule_type": r["rule_type"],
                    "scope": r.get("scope"), "target_url": url,
                    "event_date": target, "count": len(evs)}
            if r.get("code"):
                meta["code"] = str(r["code"]).upper()
            alert_store.add_event(uid, title, body, code=r.get("code"),
                                  rule_id=r["id"], meta=meta)
            alert_store.mark_rule_fired(r["id"], now_iso)
            fired += 1
            try:
                from modules.alerts import push_sender
                push_sender.send_to_user(uid, title, body, data={
                    "code": r.get("code") or "", "rule_id": str(r["id"]),
                    "type": r["rule_type"], "target_url": url, "portfolio_id": ""})
            except Exception as pe:
                print(f"[symbol_event] 룰 {r.get('id')} 푸시 실패(무시): {pe}")
        except Exception as e:
            print(f"[symbol_event] 룰 {r.get('id')} 오류: {e}")
    return fired
