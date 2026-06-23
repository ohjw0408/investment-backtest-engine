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


def compute_portfolio_index(loader, tickers, years=6, daily_rebal=True):
    """저장 포트폴리오 → 정규화 지수(시작=100) 종가 리스트(오래된→최신).

    daily_rebal=True: 매일 비중 고정 리밸런싱 가정(일별 가중 수익률 복리). 원화환산(apply_fx=True)
    으로 실제 수익 추종. 데이터 부족 시 [].
    """
    today = datetime.today()
    start = (today - timedelta(days=int(years * 365))).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    wsum = sum(float(t.get("weight") or 0) for t in tickers) or 1.0
    valid = []
    for t in tickers:
        code = str(t.get("code") or "").upper()
        w = float(t.get("weight") or 0) / wsum
        if w > 0 and code:
            valid.append((code, w))
    if not valid:
        return []

    series = {}
    for code, w in valid:
        try:
            df = loader.get_price(code, start, end, apply_fx=True)
        except Exception:
            df = None
        if df is None or df.empty or "close" not in df:
            continue
        # 날짜는 'date' 컬럼(인덱스는 정수). 종목 간 같은 날짜로 정렬해야 일수익이 맞음.
        dcol = df["date"] if "date" in df else df.index
        m = {str(d): float(c) for d, c in zip(dcol, df["close"]) if c == c}
        if m:
            series[code] = (w, m)
    if not series:
        return []

    common = None
    for _, m in series.values():
        ks = set(m.keys())
        common = ks if common is None else (common & ks)
    dates = sorted(common or [])
    if len(dates) < 2:
        return []

    if daily_rebal:
        idx = 100.0
        out = [100.0]
        for k in range(1, len(dates)):
            d0, d1 = dates[k - 1], dates[k]
            day = 0.0
            for _, (w, m) in series.items():
                p0 = m.get(d0)
                if p0:
                    day += w * (m[d1] / p0 - 1.0)
            idx *= (1.0 + day)
            out.append(idx)
        return out
    # buy-and-hold
    t0 = dates[0]
    out = []
    for dt in dates:
        val = 0.0
        for _, (w, m) in series.items():
            base = m.get(t0)
            if base:
                val += w * (m[dt] / base) * 100.0
        out.append(val)
    return out


def build_portfolio_bundle(loader, tickers, name):
    """포트폴리오 지수 → 평가 컨텍스트(symbol bundle과 동일 형태, currency='IDX')."""
    closes = compute_portfolio_index(loader, tickers, daily_rebal=True)
    if len(closes) < 2:
        return None
    cur, prev = closes[-1], closes[-2]
    change_pct = (cur - prev) / prev * 100 if prev else 0.0
    prior = closes[:-1]
    win52 = prior[-252:] if len(prior) > 252 else prior
    return {
        "cur": cur, "prev_close": prev, "change_pct": change_pct,
        "currency": "IDX", "name": name,
        "high_all": max(prior), "low_all": min(prior),
        "high_52w": max(win52), "low_52w": min(win52),
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

    group_cache = {}     # user_id -> groups (리밸런싱)
    pf_cache = {}        # (user_id, portfolio_id) -> bundle (포트폴리오 수익)
    fired = 0
    for r in rules:
        try:
            if r.get("rule_type") == "rebalance_band":
                uid = r["user_id"]
                if uid not in group_cache:
                    group_cache[uid] = compute_user_groups(loader, uid)
                ctx = {"groups": group_cache[uid]}
                ev = evaluate_rule(r, ctx, now)
            elif r.get("scope") == "portfolio" and r.get("portfolio_id") is not None:
                key = (r["user_id"], r["portfolio_id"])
                if key not in pf_cache:
                    pf = auth_manager.get_portfolio(r["user_id"], r["portfolio_id"])
                    pf_cache[key] = build_portfolio_bundle(
                        loader, pf.get("tickers") or [], pf.get("name", "포트폴리오")) if pf else None
                bundle = pf_cache[key]
                if not bundle:
                    continue
                ev = evaluate_rule(r, _ctx_for_rule(bundle, r), now)
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
            # 앱 푸시(FCM) — 비활성/실패해도 인앱 수신함엔 영향 없음
            try:
                from modules.alerts import push_sender
                push_sender.send_to_user(
                    r["user_id"], ev["title"], ev["body"],
                    data={"code": r.get("code") or "", "rule_id": str(r["id"])})
            except Exception as pe:
                print(f"[alert_runner] 룰 {r.get('id')} 푸시 실패(무시): {pe}")
        except Exception as e:
            print(f"[alert_runner] 룰 {r.get('id')} 평가 오류: {e}")
    return fired
