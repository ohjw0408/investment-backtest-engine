"""
alert_engine.py
────────────────────────────────────────────────────────────────────────────────
알림 룰 평가 — 순수 함수. 네트워크/DB 의존 없음(전부 ctx 주입) → 결정론 테스트.

룰 타입:
  daily_pct      : 전일 종가 대비 변동률 ±threshold% 초과 (direction up/down/both)
  target_price   : 가격이 threshold 이상(above)/이하(below) 도달
  new_high       : 윈도우(52w/all) 최고가 경신 — cur > 과거 최고
  new_low        : 윈도우 최저가 경신 — cur < 과거 최저
  rebalance_band : 보유자산 그룹 비중이 목표비중 대비 ±threshold%p 초과
"""

from datetime import datetime


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def cooldown_ok(rule, now):
    """직전 발화 후 cooldown_h 경과 여부. last_triggered_at 없으면 True."""
    last = _parse_dt(rule.get("last_triggered_at"))
    if last is None:
        return True
    hours = rule.get("cooldown_h") or 24
    return (now - last).total_seconds() >= hours * 3600


def _fmt_price(v, currency="USD"):
    if currency == "IDX":          # 포트폴리오 정규화 지수(시작=100) → 접두어 없이 포인트
        return f"{v:,.1f}"
    if currency == "PT":           # 시장 지수(코스피·S&P 등) → 접두어 없이 포인트
        return f"{v:,.0f}" if v >= 1000 else f"{v:,.2f}"
    pre = "₩" if currency == "KRW" else "$"
    if currency == "KRW" or v >= 1000:
        return f"{pre}{v:,.0f}"
    return f"{pre}{v:,.2f}"


def evaluate_rule(rule, ctx, now=None):
    """단일 룰 평가. 발화 시 event dict, 아니면 None.

    rule : alert_rules 행 dict (rule_type, direction, threshold, window,
           cooldown_h, last_triggered_at, last_extreme, code …)
    ctx  : 평가에 필요한 값 주입
        symbol 룰  → {cur, prev_close, change_pct, high, low, currency, name}
        rebalance → {groups: [{name, current_pct, target_pct}]}
    반환 event dict: {title, body, meta, new_extreme(optional)}
        new_extreme 가 있으면 호출측이 rule.last_extreme 갱신.
    """
    now = now or datetime.now()
    if not rule.get("enabled", 1):
        return None

    rt = rule.get("rule_type")
    if rt == "daily_pct":
        # daily_pct는 히스테리시스 상태 전이가 자체 재발화 통제 — 전역 쿨다운 미적용.
        # (24h 쿨다운이면 "1%↑ 후 다시 1%↓" 같은 방향 전환 재알림이 하루 1회로 막힘)
        return _eval_daily_pct(rule, ctx, now)
    if not cooldown_ok(rule, now):
        return None
    if rt == "target_price":
        return _eval_target_price(rule, ctx)
    if rt in ("new_high", "new_low"):
        return _eval_extreme(rule, ctx)
    if rt == "rebalance_band":
        return _eval_rebalance(rule, ctx)
    return None


def daily_pct_zone(rule, change):
    """현재 변동률이 속한 존: 'up' / 'down' / 'neutral' (임계 기준)."""
    thr = abs(rule.get("threshold") or 0)
    if change is None:
        return "neutral"
    if change >= thr:
        return "up"
    if change <= -thr:
        return "down"
    return "neutral"


# 같은 방향 재발화(neutral 복귀 후 재돌파)의 최소 간격 — 임계 주변 왕복 스팸 방지.
# 방향이 바뀐 발화(↑→↓)는 이 간격을 무시하고 즉시 알림.
SAME_DIR_REFIRE_MIN = 45 * 60  # 45분


def _eval_daily_pct(rule, ctx, now=None):
    """히스테리시스 상태 전이 발화 (알림 교통정리 2026-07-02).

    - 존 전이(neutral/down → up, neutral/up → down)일 때만 발화 → 같은 존에
      머무는 동안 15분마다 재발화하지 않음 (기존 24h 쿨다운 대체).
    - 존 이탈 후 재진입(재크로싱)은 다시 발화 — "1%↑ 알림 후 다시 1%↓" 지원.
    - 같은 방향 재발화만 45분 최소 간격(임계 주변 왕복 스팸 방지).
    - 상태(last_state)는 발화 여부와 무관하게 호출측(runner)이 매 평가마다 저장.
    """
    now = now or datetime.now()
    change = ctx.get("change_pct")
    if change is None:
        return None
    thr = abs(rule.get("threshold") or 0)
    direction = rule.get("direction") or "both"
    zone = daily_pct_zone(rule, change)
    if zone == "neutral":
        return None
    if direction == "up" and zone != "up":
        return None
    if direction == "down" and zone != "down":
        return None
    last_state = rule.get("last_state") or "neutral"
    if zone == last_state:
        return None  # 같은 존 유지 — 전이 아님
    # 같은 방향 재발화 스팸 가드 (방향 전환은 즉시 허용)
    last_fire = _parse_dt(rule.get("last_triggered_at"))
    last_dir = rule.get("last_fired_dir")
    if last_fire is not None and last_dir == zone:
        if (now - last_fire).total_seconds() < SAME_DIR_REFIRE_MIN:
            return None
    name = ctx.get("name") or rule.get("code")
    arrow = "▲" if change >= 0 else "▼"
    return {
        "title": f"{name} {arrow} {abs(change):.2f}%",
        "body": f"하루 변동률 {change:+.2f}% (기준 ±{thr:.2f}%) — 현재 "
                f"{_fmt_price(ctx['cur'], ctx.get('currency', 'USD'))}",
        "meta": {"change_pct": change, "price": ctx.get("cur"), "threshold": thr},
        "fired_dir": zone,
    }


def eval_close_summary(rule, ctx):
    """장 마감 확정 등락 요약 — daily_pct 룰 전용, 쿨다운/상태 무관 별도 레인.

    |확정 등락| >= threshold 이고 direction 매칭이면 '마감' 이벤트. 하루 1회
    (beat 스케줄 자체가 일 1회라 별도 dedup 불필요).
    """
    change = ctx.get("change_pct")
    if change is None:
        return None
    thr = abs(rule.get("threshold") or 0)
    direction = rule.get("direction") or "both"
    hit = (direction in ("up", "both") and change >= thr) or \
          (direction in ("down", "both") and change <= -thr)
    if not hit:
        return None
    name = ctx.get("name") or rule.get("code")
    arrow = "▲" if change >= 0 else "▼"
    return {
        "title": f"{name} {arrow} {abs(change):.2f}% 마감",
        "body": f"오늘 {change:+.2f}%로 마감 (기준 ±{thr:.2f}%) — 종가 "
                f"{_fmt_price(ctx['cur'], ctx.get('currency', 'USD'))}",
        "meta": {"change_pct": change, "price": ctx.get("cur"), "threshold": thr,
                 "close_summary": True},
    }


def _eval_target_price(rule, ctx):
    cur = ctx.get("cur")
    if cur is None:
        return None
    thr = rule.get("threshold")
    direction = rule.get("direction") or "above"
    hit = cur >= thr if direction == "above" else cur <= thr
    if not hit:
        return None
    name = ctx.get("name") or rule.get("code")
    cur_curr = ctx.get("currency", "USD")
    word = "도달(이상)" if direction == "above" else "도달(이하)"
    return {
        "title": f"{name} 목표가 {word}",
        "body": f"목표 {_fmt_price(thr, cur_curr)} {word} — 현재 {_fmt_price(cur, cur_curr)}",
        "meta": {"price": cur, "target": thr, "direction": direction},
    }


def _eval_extreme(rule, ctx):
    cur = ctx.get("cur")
    if cur is None:
        return None
    is_high = rule.get("rule_type") == "new_high"
    prior = ctx.get("high") if is_high else ctx.get("low")
    if prior is None:
        return None
    last_extreme = rule.get("last_extreme")
    if is_high:
        if not (cur > prior):
            return None
        if last_extreme is not None and cur <= last_extreme:
            return None  # 같은/낮은 고점 재발화 방지
    else:
        if not (cur < prior):
            return None
        if last_extreme is not None and cur >= last_extreme:
            return None
    name = ctx.get("name") or rule.get("code")
    win = "52주" if rule.get("window") == "52w" else "전체기간"
    label = "신고가" if is_high else "신저가"
    cur_curr = ctx.get("currency", "USD")
    return {
        "title": f"{name} {label} 갱신",
        "body": f"{_fmt_price(cur, cur_curr)} — {win} {label} 경신 "
                f"(직전 {_fmt_price(prior, cur_curr)})",
        "meta": {"price": cur, "prior_extreme": prior, "window": rule.get("window")},
        "new_extreme": cur,
    }


def _eval_rebalance(rule, ctx):
    band = abs(rule.get("threshold") or 0)
    groups = ctx.get("groups") or []
    breaches = []
    for g in groups:
        tgt = g.get("target_pct") or 0
        if tgt <= 0:
            continue
        cur = g.get("current_pct") or 0
        if abs(cur - tgt) >= band:
            breaches.append((g.get("name", "그룹"), cur, tgt))
    if not breaches:
        return None
    parts = [f"{n} {cur:.1f}%(목표 {tgt:.1f}%)" for n, cur, tgt in breaches]
    return {
        "title": "리밸런싱 필요",
        "body": f"목표 비중 ±{band:.1f}%p 이탈: " + ", ".join(parts),
        "meta": {"band": band, "breaches": [
            {"name": n, "current_pct": cur, "target_pct": tgt} for n, cur, tgt in breaches]},
    }
