"""
alert_runner.py
────────────────────────────────────────────────────────────────────────────────
알림 평가 오케스트레이션 — enabled 룰을 모아 종목 시세/극값/리밸 비중을 구하고
alert_engine.evaluate_rule 로 평가, 발화 시 수신함 이벤트 적재.

I/O(가격 로드·DB)는 이 모듈에 모으고, 판정 로직은 alert_engine(순수)에 둔다.
Celery 워커(별 프로세스)에서 호출 — Flask app import 없이 동작.
"""

from datetime import datetime, timedelta

from modules.alerts import alert_store
from modules.alerts.alert_engine import evaluate_rule
from modules import auth_manager

_KRW_CODES = {"^KS11", "KRW=X", "KRX_GOLD"}


def _currency(loader, code):
    if code in _KRW_CODES:
        return "KRW"
    try:
        return "KRW" if loader.is_kr_etf(code) else "USD"
    except Exception:
        return "USD"


def _fetch_closes(loader, code, need_all):
    """(closes[float], currency) — apply_fx=False(원화환산 없이 원시 종가, 변동률·극값용).

    need_all=True → 전체기간, False → 최근 ~400일.
    """
    today = datetime.today()
    start = "1990-01-01" if need_all else (today - timedelta(days=400)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    try:
        df = loader.get_price(code, start, end, apply_fx=False)
    except Exception:
        return [], _currency(loader, code)
    if df is None or df.empty or "close" not in df:
        return [], _currency(loader, code)
    closes = [float(x) for x in df["close"].tolist() if x == x]  # NaN 제거
    return closes, _currency(loader, code)


def _build_symbol_ctx(loader, code, need_all):
    """종목 1개의 평가 컨텍스트. 데이터 부족 시 None."""
    closes, currency = _fetch_closes(loader, code, need_all)
    if len(closes) < 2:
        return None
    cur, prev = closes[-1], closes[-2]
    change_pct = (cur - prev) / prev * 100 if prev else 0.0
    prior = closes[:-1]  # 오늘 제외 → 신고/신저 판정용 직전 극값
    ctx_full_high = max(prior)
    ctx_full_low = min(prior)
    # 52주 윈도우 = 최근 ~252 거래일(오늘 제외)
    win52 = prior[-252:] if len(prior) > 252 else prior
    return {
        "cur": cur, "prev_close": prev, "change_pct": change_pct,
        "currency": currency, "name": code,
        "high_all": ctx_full_high, "low_all": ctx_full_low,
        "high_52w": max(win52), "low_52w": min(win52),
    }


def _ctx_for_rule(bundle, rule):
    """룰의 window 에 맞춰 high/low 선택한 ctx 뷰."""
    win = rule.get("window") or "52w"
    return {
        "cur": bundle["cur"], "prev_close": bundle["prev_close"],
        "change_pct": bundle["change_pct"], "currency": bundle["currency"],
        "name": bundle["name"],
        "high": bundle["high_52w"] if win == "52w" else bundle["high_all"],
        "low": bundle["low_52w"] if win == "52w" else bundle["low_all"],
    }


def compute_user_groups(loader, user_id):
    """리밸런싱용 — 사용자 보유자산 그룹별 현재비중 vs 목표비중.

    가치 = 수량 × (manual_price or 최신종가, 원화환산). 그룹 없는 종목은 분모엔 포함
    하되 그룹 비중엔 미포함(목표 없는 자산).
    """
    try:
        holdings = auth_manager.get_holdings(user_id)
    except Exception:
        return []
    if not holdings:
        return []

    today = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=20)).strftime("%Y-%m-%d")
    price_cache = {}

    def _price_krw(code):
        if code in price_cache:
            return price_cache[code]
        try:
            df = loader.get_price(code, start, today, apply_fx=True)
            p = float(df["close"].iloc[-1]) if df is not None and not df.empty else 0.0
        except Exception:
            p = 0.0
        price_cache[code] = p
        return p

    total = 0.0
    group_val = {}     # group_id -> value
    group_meta = {}    # group_id -> (name, target_pct)
    for h in holdings:
        qty = h.get("quantity") or 0
        if qty <= 0:
            continue
        mp = h.get("manual_price")
        price = mp if (mp is not None) else _price_krw(str(h.get("code", "")).upper())
        val = qty * (price or 0)
        total += val
        gid = h.get("group_id")
        if gid is not None:
            group_val[gid] = group_val.get(gid, 0.0) + val
            if gid not in group_meta:
                group_meta[gid] = (h.get("group_name") or "그룹", h.get("group_target") or 0)

    if total <= 0:
        return []
    out = []
    for gid, val in group_val.items():
        name, target = group_meta[gid]
        out.append({"name": name, "current_pct": val / total * 100, "target_pct": target})
    return out


def run_alert_evaluation(loader, rules=None, now=None):
    """전 enabled 룰 평가 → 발화 이벤트 적재. 발화 건수 반환."""
    now = now or datetime.now()
    now_iso = now.isoformat()
    rules = rules if rules is not None else alert_store.get_all_enabled_rules()
    if not rules:
        return 0

    # 종목별 'all' 윈도우 필요 여부 산출(한 번만 풀히스토리 로드)
    need_all = {}
    symbol_codes = set()
    for r in rules:
        if r.get("scope") == "symbol" and r.get("code"):
            code = r["code"].upper()
            symbol_codes.add(code)
            if r.get("rule_type") in ("new_high", "new_low") and r.get("window") == "all":
                need_all[code] = True

    bundles = {}
    for code in symbol_codes:
        bundles[code] = _build_symbol_ctx(loader, code, need_all.get(code, False))

    group_cache = {}  # user_id -> groups
    fired = 0
    for r in rules:
        try:
            if r.get("rule_type") == "rebalance_band":
                uid = r["user_id"]
                if uid not in group_cache:
                    group_cache[uid] = compute_user_groups(loader, uid)
                ctx = {"groups": group_cache[uid]}
                ev = evaluate_rule(r, ctx, now)
            else:
                bundle = bundles.get((r.get("code") or "").upper())
                if not bundle:
                    continue
                ev = evaluate_rule(r, _ctx_for_rule(bundle, r), now)
            if not ev:
                continue
            alert_store.add_event(r["user_id"], ev["title"], ev["body"],
                                  code=r.get("code"), rule_id=r["id"], meta=ev.get("meta"))
            alert_store.mark_rule_fired(r["id"], now_iso, new_extreme=ev.get("new_extreme"))
            fired += 1
        except Exception as e:
            print(f"[alert_runner] 룰 {r.get('id')} 평가 오류: {e}")
    return fired
