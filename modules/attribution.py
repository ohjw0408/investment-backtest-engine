"""
attribution.py
────────────────────────────────────────────────────────────────────────────────
포트폴리오 수익의 종목별 기여도 분해 — 상승 견인 / 하락 방어 지분.

부호 가법 분해(arithmetic): 종목 기여 = Σ 비중 × 종목 일간수익.
Σ 종목기여 = 구간 포폴 일간수익 합 (정확히 100% 분해).

I/O(가격 로드)는 loader 주입, 계산은 순수 → 결정론 테스트.
"""

from datetime import datetime, timedelta


def aligned_series(loader, codes, start, end, apply_fx=True):
    """공통 거래일로 정렬된 종가. (dates[str], {code: [close]}). 데이터 없는 종목 제외."""
    maps = {}
    for code in codes:
        code = str(code).upper()
        try:
            df = loader.get_price(code, start, end, apply_fx=apply_fx)
        except Exception:
            df = None
        if df is None or getattr(df, "empty", True) or "close" not in df:
            continue
        dcol = df["date"] if "date" in df else df.index  # 날짜는 'date' 컬럼
        m = {str(d): float(c) for d, c in zip(dcol, df["close"]) if c == c}
        if m:
            maps[code] = m
    if not maps:
        return [], {}
    common = None
    for m in maps.values():
        ks = set(m.keys())
        common = ks if common is None else (common & ks)
    dates = sorted(common or [])
    if len(dates) < 2:
        return [], {}
    return dates, {code: [m[d] for d in dates] for code, m in maps.items()}


def daily_returns(dates, series):
    """(pdates, {code:[ret]}). pdates = dates[1:]."""
    pdates = dates[1:]
    rets = {}
    for code, vals in series.items():
        r = []
        for k in range(1, len(vals)):
            p0 = vals[k - 1]
            r.append((vals[k] / p0 - 1.0) if p0 else 0.0)
        rets[code] = r
    return pdates, rets


def _norm_weights(weights, codes):
    w = {c: float(weights.get(c, 0) or 0) for c in codes}
    s = sum(w.values()) or 1.0
    return {c: w[c] / s for c in codes}


def regime_masks(rets, weights):
    """포폴 자체 일간 등락 기준. (up_idx, down_idx, port_daily[])."""
    codes = list(rets.keys())
    w = _norm_weights(weights, codes)
    n = len(next(iter(rets.values()))) if rets else 0
    port = []
    for t in range(n):
        port.append(sum(w[c] * rets[c][t] for c in codes))
    up = [t for t in range(n) if port[t] > 0]
    down = [t for t in range(n) if port[t] < 0]
    return up, down, port


def contributions(rets, weights, idxs):
    """{code: Σ_{t∈idxs} 비중×수익}. 합 = 해당 구간 포폴 일간수익 합."""
    codes = list(rets.keys())
    w = _norm_weights(weights, codes)
    out = {c: 0.0 for c in codes}
    for c in codes:
        rc = rets[c]
        out[c] = sum(w[c] * rc[t] for t in idxs)
    return out


def shares(contrib):
    """같은 부호 기여 합 대비 지분(%) — 견인/방어 비중. {code: pct}."""
    pos = sum(v for v in contrib.values() if v > 0) or 0.0
    neg = sum(v for v in contrib.values() if v < 0) or 0.0
    out = {}
    for c, v in contrib.items():
        base = pos if v >= 0 else abs(neg)
        out[c] = (v / base * 100.0) if base else 0.0
    return out


def analyze_window(loader, codes, weights, start, end, apply_fx=True):
    """백테 사용자 지정 구간 — 구간 전체 기여 + 지분. 반환 pct(%p) 단위."""
    dates, series = aligned_series(loader, codes, start, end, apply_fx=apply_fx)
    if not series:
        return None
    pdates, rets = daily_returns(dates, series)
    if not pdates:
        return None
    allc = contributions(rets, weights, list(range(len(pdates))))
    port = sum(allc.values())
    rows = [{"code": c, "contrib": allc[c] * 100.0, "share": shares(allc).get(c, 0.0)}
            for c in allc]
    rows.sort(key=lambda r: r["contrib"], reverse=True)
    return {"period": [pdates[0], pdates[-1]], "n_days": len(pdates),
            "port_return": port * 100.0, "rows": rows}


def analyze_regime(loader, codes, weights, years=6, apply_fx=True):
    """내자산 — 상승장/하락장 구간 종목 기여. 텍스트 요약용."""
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=int(years * 365))).strftime("%Y-%m-%d")
    dates, series = aligned_series(loader, codes, start, end, apply_fx=apply_fx)
    if not series:
        return None
    pdates, rets = daily_returns(dates, series)
    if not pdates:
        return None
    up, down, _ = regime_masks(rets, weights)
    up_c = contributions(rets, weights, up)
    down_c = contributions(rets, weights, down)

    def _top(cd, defender=False):
        if not cd:
            return None
        # 견인: 최대 기여 / 방어: 하락구간 기여 최대(덜 마이너스/플러스)
        code = max(cd, key=lambda c: cd[c])
        return {"code": code, "contrib": cd[code] * 100.0,
                "share": shares(cd).get(code, 0.0)}

    return {
        "period": [pdates[0], pdates[-1]],
        "n_up": len(up), "n_down": len(down),
        "up_driver": _top(up_c),
        "down_defender": _top(down_c, defender=True),
        "up_rows": sorted([{"code": c, "contrib": up_c[c] * 100.0} for c in up_c],
                          key=lambda r: r["contrib"], reverse=True),
        "down_rows": sorted([{"code": c, "contrib": down_c[c] * 100.0} for c in down_c],
                            key=lambda r: r["contrib"], reverse=True),
    }


def _percentile(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def analyze_rolling(loader, codes, weights, window_days=252, step=21, years=15, apply_fx=True):
    """투자계산기 — 롤링 윈도우별 상승기여·하락방어 분포(mean·p25·p75). %p 단위."""
    end = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=int(years * 365))).strftime("%Y-%m-%d")
    dates, series = aligned_series(loader, codes, start, end, apply_fx=apply_fx)
    if not series:
        return None
    pdates, rets = daily_returns(dates, series)
    n = len(pdates)
    if n < window_days:
        window_days = n
    codes_v = list(rets.keys())
    up_samples = {c: [] for c in codes_v}
    down_samples = {c: [] for c in codes_v}
    wins = 0
    for s in range(0, n - window_days + 1, step):
        idxs = list(range(s, s + window_days))
        sub = {c: rets[c][s:s + window_days] for c in codes_v}
        up = [t for t in range(window_days)
              if sum(_norm_weights(weights, codes_v)[c] * sub[c][t] for c in codes_v) > 0]
        down = [t for t in range(window_days) if t not in up]
        uc = contributions(sub, weights, up)
        dc = contributions(sub, weights, down)
        for c in codes_v:
            up_samples[c].append(uc[c] * 100.0)
            down_samples[c].append(dc[c] * 100.0)
        wins += 1

    def _stat(samples):
        return {c: {"mean": (sum(v) / len(v) if v else 0.0),
                    "p25": _percentile(v, 0.25), "p75": _percentile(v, 0.75)}
                for c, v in samples.items()}

    return {"windows": wins, "window_days": window_days,
            "up": _stat(up_samples), "down": _stat(down_samples)}
