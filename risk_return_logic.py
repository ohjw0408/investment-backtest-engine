"""리스크-리턴 도표 (P3) — 저장 포트폴리오·벤치마크의 위험-수익 산점도 데이터.

오너 결정(2026-06-12):
- y = CAGR, x = 일간수익률 std×√252(연율화). 총수익(배당 재투자) 기준.
- 기간 정렬 = 전 점(포트폴리오+벤치마크) 공통 겹침 기간 — 공정 비교. 3년 미만이면 warning.
- 벤치마크 = 고정 셋 + 사용자 추가.

시뮬 없이 고정비중 일별 근사(r_p = Σ w·r). 비중합 < 100% → 잔여 현금(수익 0).
비중합 > 100% → 합으로 정규화(레버리지 방지). 달력은 종목 합집합 + ffill — 한 시장 휴장일은
보합(0%)으로 들어가며 모든 점에 동일 적용이라 상대 비교는 보존된다.
"""
import numpy as np
import pandas as pd

DEFAULT_BENCHMARKS = [
    {"code": "SPY",    "name": "SPY (S&P500)"},
    {"code": "QQQ",    "name": "QQQ (나스닥100)"},
    {"code": "GLD",    "name": "GLD (금)"},
    {"code": "069500", "name": "KODEX 200"},
    {"code": "TLT",    "name": "TLT (미국 장기채)"},
]

MIN_YEARS_WARN = 3.0
_LOAD_START = "2000-01-01"


def _load_series(loader, code, data_end):
    """code → (close, dividend) Series (date index). 실패 시 None."""
    try:
        df = loader.get_price(code, _LOAD_START, data_end)
        if df is None or len(df) == 0:
            return None
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        close = df["close"].astype(float)
        close = close[np.isfinite(close) & (close > 0)]
        if len(close) < 2:
            return None
        div = df["dividend"].astype(float) if "dividend" in df.columns else pd.Series(0.0, index=df.index)
        div = div.reindex(close.index).fillna(0.0)
        return close, div
    except Exception:
        return None


def _total_return_matrix(series_by_code):
    """합집합 달력 + ffill → 일별 총수익률(배당 재투자) DataFrame."""
    closes = pd.DataFrame({c: s[0] for c, s in series_by_code.items()}).sort_index()
    divs   = pd.DataFrame({c: s[1] for c, s in series_by_code.items()}).reindex(closes.index).fillna(0.0)
    closes_ff = closes.ffill()
    prev = closes_ff.shift(1)
    rets = (closes_ff + divs) / prev - 1.0
    return rets, closes


def _metrics(returns: pd.Series):
    """일별 수익률 → {cagr, vol, sharpe}. 표본 부족/이상치면 None."""
    r = returns.dropna()
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 20:
        return None
    growth = float((1.0 + r).prod())
    if growth <= 0:
        return None
    years = n / 252.0
    cagr = growth ** (1.0 / years) - 1.0
    std = float(r.std())
    if std < 1e-12:           # 상수 수익률 — 부동소수 잔차 std로 sharpe 폭주 방지
        std = 0.0
    vol = std * np.sqrt(252.0)
    sharpe = float(r.mean() / std * np.sqrt(252.0)) if std > 0 else 0.0
    return {"cagr": round(cagr, 6), "vol": round(vol, 6), "sharpe": round(sharpe, 4)}


def _metrics_full(returns: pd.Series, spy_returns=None, div_yield=None):
    """일별 수익률 → 확장 지표. _metrics(cagr/vol/sharpe) + mdd·sortino·연최고/최저·승률·베타."""
    base = _metrics(returns)
    if not base:
        return None
    r = returns.dropna()
    r = r[np.isfinite(r)]

    cum = (1.0 + r).cumprod()
    mdd = float((cum / cum.cummax() - 1.0).min())   # 음수

    downside = r[r < 0]
    dstd = float(downside.std()) if len(downside) > 1 else 0.0
    sortino = float(r.mean() / dstd * np.sqrt(252.0)) if dstd > 0 else 0.0

    yearly = (1.0 + r).groupby(r.index.year).prod() - 1.0
    best_year  = float(yearly.max()) if len(yearly) else None
    worst_year = float(yearly.min()) if len(yearly) else None

    monthly = (1.0 + r).groupby([r.index.year, r.index.month]).prod() - 1.0
    win_rate = float((monthly > 0).mean()) if len(monthly) else None

    beta = None
    if spy_returns is not None:
        aligned = pd.concat([r, spy_returns], axis=1, join="inner").dropna()
        if len(aligned) > 20:
            sv = float(aligned.iloc[:, 1].var())
            if sv > 0:
                beta = float(aligned.iloc[:, 0].cov(aligned.iloc[:, 1]) / sv)

    return {
        **base,
        "mdd":        round(mdd, 6),
        "sortino":    round(sortino, 4),
        "div_yield":  round(float(div_yield or 0.0), 6),
        "best_year":  round(best_year, 6)  if best_year  is not None else None,
        "worst_year": round(worst_year, 6) if worst_year is not None else None,
        "win_rate":   round(win_rate, 4)   if win_rate   is not None else None,
        "beta":       round(beta, 4)       if beta       is not None else None,
    }


def _annual_risk_return(daily_r):
    """일별 수익률 → 연도별 {year, ret, vol, mdd}. 좌측 겹침 라인용(공통기간 기준)."""
    r = daily_r.dropna()
    r = r[np.isfinite(r)]
    if not len(r):
        return []
    out = []
    for yr, g in r.groupby(r.index.year):
        if len(g) < 5:
            continue
        ret = float((1.0 + g).prod() - 1.0)
        vol = float(g.std() * np.sqrt(252.0)) if len(g) > 1 else 0.0
        cum = (1.0 + g).cumprod()
        mdd = float((cum / cum.cummax() - 1.0).min())
        out.append({"year": int(yr), "ret": round(ret, 6), "vol": round(vol, 6), "mdd": round(mdd, 6)})
    return out


def _annual_dividends(weights, series, start, end):
    """포폴 연도별 배당: dyield(연 배당수익률) + dindex(첫해=100 정규화 배당액 흐름).
       weights={code:w}. 배당성장률·배당 아코디언 라인용."""
    years = list(range(start.year, end.year + 1))
    dyield, damt = {}, {}
    for code, w in weights.items():
        s = series.get(code)
        if not s:
            continue
        close, div = s
        for y in years:
            ys, ye = pd.Timestamp(y, 1, 1), pd.Timestamp(y, 12, 31)
            dsum = float(div[(div.index >= ys) & (div.index <= ye)].sum())
            yc = close[(close.index >= ys) & (close.index <= ye)]
            if not len(yc):
                continue
            px_end = float(yc.iloc[-1])
            if px_end > 0:
                dyield[y] = dyield.get(y, 0.0) + w * (dsum / px_end)   # 연 배당수익률
            # 정규화 배당액 = 주당배당 / 첫 종가(있는 종목) → 비교가능 흐름
            px0 = float(close.iloc[0]) if len(close) else 0.0
            if px0 > 0:
                damt[y] = damt.get(y, 0.0) + w * (dsum / px0)
    out = []
    for y in years:
        if y in dyield or y in damt:
            out.append({"year": int(y), "dyield": round(dyield.get(y, 0.0), 6), "dindex": round(damt.get(y, 0.0), 6)})
    return out


def _dividend_growth(annual_div):
    """연배당액(dindex) → {cagr, yoy:[{year, growth}]}. 마지막 해는 미수령 가능성 있어 그대로."""
    pts = [(d["year"], d["dindex"]) for d in (annual_div or []) if d.get("dindex", 0) > 0]
    yoy = []
    for i in range(1, len(pts)):
        prev = pts[i - 1][1]
        if prev > 0:
            yoy.append({"year": pts[i][0], "growth": round(pts[i][1] / prev - 1.0, 4)})
    cagr = None
    if len(pts) >= 2:
        y0, v0 = pts[0]; y1, v1 = pts[-1]
        span = y1 - y0
        if span >= 1 and v0 > 0:
            cagr = round((v1 / v0) ** (1.0 / span) - 1.0, 4)
    return {"cagr": cagr, "yoy": yoy}


def _rolling_return_table(tickers):
    """전체기간·거치식·배당재투자 TR 인덱스 기반 수익률 롤링 분포(P2 엔진 재사용, 결정#7)."""
    try:
        from modules.tr_index import build_portfolio_tr_index
        from modules import rolling
        pts = build_portfolio_tr_index(tickers)
        if len(pts) < 13:
            return None
        return {
            "horizons": rolling.DEFAULT_HORIZONS,
            "horizon_table": {str(h): v for h, v in rolling.horizon_table(pts).items()},
            "syn_overall": round(sum(1 for _d, _v, s in pts if s) / len(pts), 4),
        }
    except Exception:
        return None


def compute_comparison(portfolios, benchmarks, loader, data_end=None):
    """포트폴리오 비교 탭 — 선택 포폴 + 벤치마크의 11지표.

    반환: {items:[{kind,name,code?, cagr,vol,sharpe,mdd,sortino,div_yield,
                   best_year,worst_year,win_rate,beta}], period, skipped}
    베타 기준 = SPY(표시 여부와 무관하게 로드).
    """
    data_end = data_end or pd.Timestamp.today().strftime("%Y-%m-%d")

    port_weights = []
    for p in portfolios:
        weights = _portfolio_weights(p.get("tickers") or [])
        if weights:
            port_weights.append((p.get("name") or "포트폴리오", weights))

    bench_list, seen = [], set()
    for b in benchmarks:
        code = str(b.get("code") or "").strip()
        if code and code not in seen:
            seen.add(code)
            bench_list.append({"code": code, "name": b.get("name") or code})

    needed = ({c for _, w in port_weights for c in w}
              | {b["code"] for b in bench_list} | {"SPY"})   # SPY = 베타 기준
    if not needed:
        return {"items": [], "period": None, "skipped": []}

    series, skipped = {}, []
    for code in sorted(needed):
        s = _load_series(loader, code, data_end)
        if s is None:
            if code != "SPY":
                skipped.append(code)
        else:
            series[code] = s

    port_weights = [(n, w) for n, w in port_weights if all(c in series for c in w)]
    bench_list   = [b for b in bench_list if b["code"] in series]
    used = ({c for _, w in port_weights for c in w}
            | {b["code"] for b in bench_list} | ({"SPY"} if "SPY" in series else set()))
    series = {c: s for c, s in series.items() if c in used}
    if not series:
        return {"items": [], "period": None, "skipped": skipped}

    rets, closes = _total_return_matrix(series)

    starts = [closes[c].first_valid_index() for c in series]
    ends   = [closes[c].last_valid_index() for c in series]
    common_start, common_end = max(starts), min(ends)
    if common_start >= common_end:
        return {"items": [], "period": None, "skipped": skipped,
                "error": "공통 겹침 기간이 없습니다. 데이터 기간이 겹치지 않는 종목이 섞여 있어요."}
    rets_c = rets.loc[(rets.index > common_start) & (rets.index <= common_end)]
    spy_r = rets_c["SPY"] if "SPY" in rets_c.columns else None

    # 종목별 최근 1년 배당수익률 = 직전 1년 배당합 / 마지막 종가
    yld = {}
    for code, (close, div) in series.items():
        lc = close.dropna()
        if not len(lc):
            yld[code] = 0.0
            continue
        last_dt, last_px = lc.index[-1], float(lc.iloc[-1])
        d1 = float(div[(div.index > last_dt - pd.DateOffset(years=1)) & (div.index <= last_dt)].sum())
        yld[code] = (d1 / last_px) if last_px > 0 else 0.0

    items = []
    for name, weights in port_weights:
        pr = sum(rets_c[c] * w for c, w in weights.items())
        dy = sum(yld.get(c, 0.0) * w for c, w in weights.items())
        m = _metrics_full(pr, spy_r, dy)
        if m:
            annual = _annual_risk_return(pr)
            div_y = _annual_dividends(weights, series, common_start, common_end)
            tk = [{"code": c, "weight": w * 100.0} for c, w in weights.items()]
            items.append({"kind": "portfolio", "name": name, **m,
                          "annual": annual, "annual_div": div_y,
                          "divgrowth": _dividend_growth(div_y),
                          "rolling_return": _rolling_return_table(tk)})
    for b in bench_list:
        m = _metrics_full(rets_c[b["code"]], spy_r, yld.get(b["code"], 0.0))
        if m:
            annual = _annual_risk_return(rets_c[b["code"]])
            div_y = _annual_dividends({b["code"]: 1.0}, series, common_start, common_end)
            items.append({"kind": "benchmark", "name": b["name"], "code": b["code"], **m,
                          "annual": annual, "annual_div": div_y,
                          "divgrowth": _dividend_growth(div_y),
                          "rolling_return": _rolling_return_table([{"code": b["code"], "weight": 100.0}])})

    years = round((common_end - common_start).days / 365.25, 2)
    period = {
        "start": str(common_start.date()), "end": str(common_end.date()), "years": years,
        "warning": (f"공통 기간이 {years}년으로 짧아요({MIN_YEARS_WARN:.0f}년 미만) — 지표 신뢰도가 낮을 수 있어요."
                    if years < MIN_YEARS_WARN else None),
    }
    return {"items": items, "period": period, "skipped": skipped}


def _portfolio_weights(tickers):
    """[{code, weight(%)}] → {code: 유효비중}. 합>100 정규화, 합<100 잔여 현금."""
    w = {}
    for t in tickers:
        code = t.get("code")
        if not code:
            continue
        w[code] = w.get(code, 0.0) + max(0.0, float(t.get("weight", 0) or 0))
    total = sum(w.values())
    if total <= 0:
        return {}
    scale = 100.0 if total <= 100.0 else total
    return {c: v / scale for c, v in w.items()}


def compute_risk_return(portfolios, benchmarks, loader, data_end=None):
    """산점도 데이터 산출.

    portfolios: [{name, tickers:[{code,name,weight(%)}]}] (saved_portfolios 형식)
    benchmarks: [{code, name}]
    loader:     get_price(code, start, end) 제공 객체 (DataEngine)
    반환: {points, period:{start,end,years,warning}, skipped:[code]}
    """
    data_end = data_end or pd.Timestamp.today().strftime("%Y-%m-%d")

    port_weights = []
    for p in portfolios:
        weights = _portfolio_weights(p.get("tickers") or [])
        if weights:
            port_weights.append((p.get("name") or "포트폴리오", weights))

    bench_list = []
    seen = set()
    for b in benchmarks:
        code = str(b.get("code") or "").strip()
        if code and code not in seen:
            seen.add(code)
            bench_list.append({"code": code, "name": b.get("name") or code})

    needed = {c for _, w in port_weights for c in w} | {b["code"] for b in bench_list}
    if not needed:
        return {"points": [], "period": None, "skipped": []}

    series, skipped = {}, []
    for code in sorted(needed):
        s = _load_series(loader, code, data_end)
        if s is None:
            skipped.append(code)
        else:
            series[code] = s

    # 데이터 없는 종목을 쓰는 포트폴리오/벤치마크는 제외(부분 데이터로 왜곡 방지).
    port_weights = [(n, w) for n, w in port_weights if all(c in series for c in w)]
    bench_list = [b for b in bench_list if b["code"] in series]
    used = {c for _, w in port_weights for c in w} | {b["code"] for b in bench_list}
    series = {c: s for c, s in series.items() if c in used}
    if not series:
        return {"points": [], "period": None, "skipped": skipped}

    rets, closes = _total_return_matrix(series)

    # 공통 겹침 기간 — 전 종목 데이터가 모두 존재하는 구간(오너 결정).
    starts = [closes[c].first_valid_index() for c in series]
    ends   = [closes[c].last_valid_index() for c in series]
    common_start, common_end = max(starts), min(ends)
    if common_start >= common_end:
        return {"points": [], "period": None, "skipped": skipped,
                "error": "공통 겹침 기간이 없습니다. 데이터 기간이 겹치지 않는 종목이 섞여 있어요."}
    rets = rets.loc[(rets.index > common_start) & (rets.index <= common_end)]

    points = []
    for name, weights in port_weights:
        pr = sum(rets[c] * w for c, w in weights.items())  # 잔여 현금 = 수익 0이라 그냥 합
        m = _metrics(pr)
        if m:
            points.append({"kind": "portfolio", "name": name, **m})
    for b in bench_list:
        m = _metrics(rets[b["code"]])
        if m:
            points.append({"kind": "benchmark", "name": b["name"], "code": b["code"], **m})

    years = round((common_end - common_start).days / 365.25, 2)
    period = {
        "start": str(common_start.date()),
        "end":   str(common_end.date()),
        "years": years,
        "warning": (f"공통 기간이 {years}년으로 짧아요({MIN_YEARS_WARN:.0f}년 미만) — 지표 신뢰도가 낮을 수 있어요."
                    if years < MIN_YEARS_WARN else None),
    }
    return {"points": points, "period": period, "skipped": skipped}
