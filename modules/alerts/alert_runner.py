"""
alert_runner.py
────────────────────────────────────────────────────────────────────────────────
알림 평가 오케스트레이션 — enabled 룰을 모아 종목 시세/극값/리밸 비중을 구하고
alert_engine.evaluate_rule 로 평가, 발화 시 수신함 이벤트 적재.

I/O(가격 로드·DB)는 이 모듈에 모으고, 판정 로직은 alert_engine(순수)에 둔다.
Celery 워커(별 프로세스)에서 호출 — Flask app import 없이 동작.
"""

from datetime import datetime, timedelta

from modules.alerts import alert_store, live_quote
from modules.alerts.alert_engine import evaluate_rule, eval_close_summary, daily_pct_zone
from modules import auth_manager

_KRW_CODES = {"^KS11", "KRW=X", "KRX_GOLD"}


def rule_market(code):
    """심볼 → 거래 시장: 'KR' / 'US' / 'ANY'(크립토·선물·FX = 상시).

    시장 게이팅(알림 교통정리 2026-07-02): 코스피 룰이 미국장 시간(22:30 KST 등)에
    평가되던 문제의 근본 수정 — 각 룰은 자기 시장이 열린 슬롯에서만 평가.
    """
    code = str(code or "").upper()
    if not code:
        return "ANY"
    if code.isdigit() or code.endswith((".KS", ".KQ")) or code.startswith("^KS")             or code == "KRX_GOLD" or (len(code) == 6 and code[:1].isdigit()):
        return "KR"
    if code.endswith("-USD") or code.endswith("=X") or code.endswith("=F") or "/" in code:
        return "ANY"
    return "US"


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
    """종목 1개의 평가 컨텍스트. 데이터 부족 시 None.

    시세 축(알림 교통정리 2026-07-02): 일봉 DB는 당일봉이 첫 조회 스냅샷으로 박제돼
    장중 변동 감지가 안 됐음 → live_quote(지수=index_ohlc 준라이브, 주식=yf 직접)로
    cur/prev/change를 덮어쓴다. 라이브 실패 시 기존 일봉 폴백(테스트 FakeLoader 경로).
    cur_is_today: 마지막 시세가 오늘 것인지 — daily_pct 장중 평가는 이때만 발화
    (확정 종가가 밤에 뒤늦게 들어와 "어제 등락"으로 오발화하는 것 차단).
    """
    closes, currency = _fetch_closes(loader, code, need_all)
    if len(closes) < 2:
        return None
    cur, prev = closes[-1], closes[-2]
    cur_is_today = True  # 일봉 폴백 시 판단 불가 → 기존 동작 보존
    # supports_live_quotes=False 로더(테스트 FakeLoader)는 네트워크 라이브 경로 스킵
    live = (live_quote.get_live_price(loader, code)
            if getattr(loader, "supports_live_quotes", True) else None)
    if live is not None:
        cur, prev = live["cur"], live["prev"]
        cur_is_today = live["cur_is_today"]
    change_pct = (cur - prev) / prev * 100 if prev else 0.0
    prior = closes[:-1]  # 오늘 제외 → 신고/신저 판정용 직전 극값
    ctx_full_high = max(prior)
    ctx_full_low = min(prior)
    # 52주 윈도우 = 최근 ~252 거래일(오늘 제외)
    win52 = prior[-252:] if len(prior) > 252 else prior
    return {
        "cur": cur, "prev_close": prev, "change_pct": change_pct,
        "currency": currency, "name": code, "cur_is_today": cur_is_today,
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


def _target_for_rule(rule):
    if rule.get("scope") == "symbol" and rule.get("code"):
        return "/symbol/%s" % str(rule["code"]).upper()
    if rule.get("rule_type") == "rebalance_band":
        return "/myassets"
    if rule.get("scope") == "portfolio" and rule.get("portfolio_id") is not None:
        return "/myportfolios/%s" % rule["portfolio_id"]
    return "/alerts#inbox"


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


def run_alert_evaluation(loader, rules=None, now=None, markets=None):
    """전 enabled 룰 평가 → 발화 이벤트 적재. 발화 건수 반환.

    markets: 현재 열린 시장 집합({'KR','US'}) — 지정 시 symbol 룰을 자기 시장이
    열린 슬롯에서만 평가('ANY' 시장은 항상). None이면 전체 평가(기존 동작·테스트).
    """
    now = now or datetime.now()
    now_iso = now.isoformat()
    rules = rules if rules is not None else alert_store.get_all_enabled_rules()
    if markets is not None:
        # symbol 룰: 자기 시장이 열렸거나 ANY(크립토·환율·선물=상시).
        # portfolio/rebalance 룰: 일봉 기반 혼합 자산 → KR/US 아무 장이나 열려있을 때만.
        rules = [r for r in rules
                 if (rule_market(r.get("code")) in (markets | {"ANY"})
                     if r.get("scope") == "symbol" else bool(markets))]
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
                if r.get("rule_type") == "daily_pct" and not bundle.get("cur_is_today", True):
                    continue  # 마지막 시세가 오늘 것이 아님 — "어제 등락" 오발화 차단
                ev = evaluate_rule(r, _ctx_for_rule(bundle, r), now)
            # daily_pct 히스테리시스: 발화 여부와 무관하게 존 상태 저장(재무장 추적)
            if r.get("rule_type") == "daily_pct":
                try:
                    _ctx = _ctx_for_rule(bundle, r) if r.get("scope") == "symbol" else None
                    change = (_ctx or {}).get("change_pct")
                    if r.get("scope") == "portfolio" and r.get("portfolio_id") is not None:
                        b = pf_cache.get((r["user_id"], r["portfolio_id"]))
                        change = _ctx_for_rule(b, r).get("change_pct") if b else None
                    zone = daily_pct_zone(r, change)
                    if zone != (r.get("last_state") or "neutral"):
                        alert_store.update_rule_state(r["id"], zone)
                except Exception:
                    pass
            if not ev:
                continue
            target_url = _target_for_rule(r)
            meta = dict(ev.get("meta") or {})
            meta.update({
                "target_url": target_url,
                "type": r.get("rule_type"),
                "rule_type": r.get("rule_type"),
                "scope": r.get("scope"),
            })
            if r.get("code"):
                meta["code"] = str(r.get("code")).upper()
            if r.get("portfolio_id") is not None:
                meta["portfolio_id"] = r.get("portfolio_id")
            alert_store.add_event(r["user_id"], ev["title"], ev["body"],
                                  code=r.get("code"), rule_id=r["id"], meta=meta)
            alert_store.mark_rule_fired(r["id"], now_iso, new_extreme=ev.get("new_extreme"),
                                        fired_dir=ev.get("fired_dir"))
            fired += 1
            # 앱 푸시(FCM) — 비활성/실패해도 인앱 수신함엔 영향 없음
            try:
                from modules.alerts import push_sender
                push_sender.send_to_user(
                    r["user_id"], ev["title"], ev["body"],
                    data={
                        "code": r.get("code") or "",
                        "rule_id": str(r["id"]),
                        "type": r.get("rule_type") or "",
                        "target_url": target_url,
                        "portfolio_id": r.get("portfolio_id") or "",
                    })
            except Exception as pe:
                print(f"[alert_runner] 룰 {r.get('id')} 푸시 실패(무시): {pe}")
        except Exception as e:
            print(f"[alert_runner] 룰 {r.get('id')} 평가 오류: {e}")
    return fired


def run_close_summary(loader, market, now=None):
    """장 마감 확정 등락 요약 (알림 교통정리 2026-07-02, 오너 요청).

    해당 시장(KR/US)의 daily_pct symbol 룰만 — 확정 종가 기준 |등락| >= threshold면
    "마감" 이벤트. 장중 발화와 독립(쿨다운/상태 미변경 — mark_rule_fired 안 함:
    24h 쿨다운으로 다음날 장중 알림이 막히는 것 방지). beat가 일 1회라 dedup 불필요.
    """
    now = now or datetime.now()
    rules = [r for r in alert_store.get_all_enabled_rules()
             if r.get("scope") == "symbol" and r.get("rule_type") == "daily_pct"
             and rule_market(r.get("code")) == market]
    if not rules:
        return 0
    bundles = {}
    fired = 0
    for r in rules:
        try:
            code = (r.get("code") or "").upper()
            if code not in bundles:
                bundles[code] = _build_symbol_ctx(loader, code, False)
            bundle = bundles[code]
            if not bundle:
                continue
            ev = eval_close_summary(r, _ctx_for_rule(bundle, r))
            if not ev:
                continue
            meta = dict(ev.get("meta") or {})
            meta.update({"target_url": _target_for_rule(r), "type": "daily_pct",
                         "rule_type": "daily_pct", "scope": "symbol", "code": code})
            alert_store.add_event(r["user_id"], ev["title"], ev["body"],
                                  code=code, rule_id=r["id"], meta=meta)
            fired += 1
            try:
                from modules.alerts import push_sender
                push_sender.send_to_user(
                    r["user_id"], ev["title"], ev["body"],
                    data={"code": code, "rule_id": str(r["id"]), "type": "daily_pct",
                          "target_url": _target_for_rule(r), "portfolio_id": ""})
            except Exception as pe:
                print(f"[alert_runner] 마감요약 {r.get('id')} 푸시 실패(무시): {pe}")
        except Exception as e:
            print(f"[alert_runner] 마감요약 룰 {r.get('id')} 오류: {e}")
    return fired
