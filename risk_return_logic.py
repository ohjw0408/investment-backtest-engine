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
_DEEP_SYNTH_DAILY_JUMP_LIMIT = 0.45
# 종목별 합성손상 게이트: 합성 구간 일변동성이 실데이터 대비 이 배수를 넘거나(SHY 20×·IEF 2.9×)
# 합성 단일일 변동 최대치가 한도를 넘으면 그 종목 합성 전체를 버리고 실데이터만 쓴다(원래 안전동작).
# 정상 합성(SPY/QQQ/SCHD/GLD/TLT)은 비율 ~1.0~1.3·max ≤0.21 이라 보존된다.
_DEEP_SYNTH_VOL_RATIO = 2.5
_DEEP_SYNTH_MAXABS = 0.30
_DIV_GROWTH_LOW_BASE_FRACTION = 0.30
_DIV_GROWTH_SPIKE_LIMIT = 1.0
_DIV_MIN_ACTUAL_DAYS = 40
_DIV_FULL_YEAR_DAYS = 200


def _load_series(loader, code, data_end):
    """code → (close, dividend) Series (date index). 실패 시 None."""
    try:
        df = loader.get_price(code, _LOAD_START, data_end)
        if df is None or len(df) == 0:
            return None
        df = df.copy()
        df = _drop_corrupt_generated_tail(df)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        close = df["close"].astype(float)
        close = close[np.isfinite(close) & (close > 0)]
        if len(close) < 2:
            return None
        div = df["dividend"].astype(float) if "dividend" in df.columns else pd.Series(0.0, index=df.index)
        div = div.reindex(close.index).fillna(0.0)
        if "volume" in df.columns:
            vol = pd.to_numeric(df["volume"], errors="coerce").reindex(close.index)
            actual = (vol > 0)
        else:
            actual = pd.Series(True, index=close.index)
        return close, div, actual.astype(bool)
    except Exception:
        return None


def _drop_corrupt_generated_tail(df):
    """Drop legacy generated near-zero tails from risk-return inputs."""
    if df is None or df.empty or "volume" not in df.columns or "close" not in df.columns:
        return df
    out = df.copy()
    close = pd.to_numeric(out["close"], errors="coerce")
    vol = pd.to_numeric(out["volume"], errors="coerce")
    gen = out["volume"].isna() | (vol == 0)
    gen_close = close[gen & (close > 0)]
    if len(gen_close) < 100:
        return df
    med = float(gen_close.median())
    if med <= 0:
        return df
    p01 = float(gen_close.quantile(0.01)) / med
    p10 = float(gen_close.quantile(0.10)) / med
    if p01 < 0.02 and p10 < 0.05:
        bad = gen & (close > 0) & (close < med * 0.10)
        if bool(bad.any()):
            return out.loc[~bad].copy()
    return df


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


def _clean_deep_points(pts):
    """비교 심화용 TR 포인트 정리.

    합성/백필 구간(volume=0) 일부는 단일일 점프가 아니라 구간 전체가 손상돼 있다
    (예: SHY 합성이 실데이터 대비 변동성 20×·하루 +122%). 이런 종목은 단일일 점프 제거로는
    못 살리므로, 합성 구간 변동성이 실데이터 대비 비정상이면 그 종목 합성 전체를 버리고
    실데이터만 쓴다(원래 비교 심화의 안전동작). 정상 합성(SPY/QQQ 등)은 그대로 보존하고,
    남는 병적 단일일 점프만 추가로 반복 제거한다.
    """
    if not pts or len(pts) < 3:
        return pts or []
    df = pd.DataFrame(
        [(p[0], p[1], int(p[2]) if len(p) > 2 else 0) for p in pts],
        columns=["date", "val", "syn"],
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["val"] = pd.to_numeric(df["val"], errors="coerce")
    df = df.dropna(subset=["date", "val"]).sort_values("date")
    df = df[np.isfinite(df["val"]) & (df["val"] > 0)]
    if len(df) < 3:
        return []

    # 합성손상 게이트: 합성 일변동성이 실데이터 대비 비정상이면 합성 전체 제거 → 실데이터 폴백
    r_all = df["val"].pct_change(fill_method=None)
    syn_b = df["syn"].astype(bool)
    real_r = r_all[~syn_b].dropna()
    syn_r = r_all[syn_b].dropna()
    if len(real_r) > 30 and len(syn_r) > 30:
        rs, ss = float(real_r.std()), float(syn_r.std())
        if rs > 0 and (ss > _DEEP_SYNTH_VOL_RATIO * rs
                       or float(syn_r.abs().max()) > _DEEP_SYNTH_MAXABS):
            df = df.loc[~syn_b].copy()
            if len(df) < 3:
                return []

    for _ in range(6):
        r = df["val"].pct_change(fill_method=None)
        syn = df["syn"].astype(bool)
        bad = (r.abs() > _DEEP_SYNTH_DAILY_JUMP_LIMIT) & (syn | syn.shift(1).fillna(False))
        if not bool(bad.any()):
            break
        df = df.loc[~bad].copy()
        if len(df) < 3:
            break

    return [[d.strftime("%Y-%m-%d"), round(float(v), 4), int(bool(s))]
            for d, v, s in zip(df["date"], df["val"], df["syn"])]


def _annual_from_points(pts, actual_only=False):
    """TR 인덱스([[date,val,(syn)]]) → 연도별 {year, ret, vol, mdd}.
       각 항목 자기 가용기간 기준(공통 겹침기간 비종속). 비현실 값(|연수익|>300%)은
       데이터 글리치로 보고 그 해 제외(차트 폭주 방지)."""
    if not pts or len(pts) < 2:
        return []
    s = pd.Series({pd.Timestamp(d): v for d, v, *_ in pts}).sort_index()
    syn = pd.Series({pd.Timestamp(p[0]): (int(p[2]) if len(p) > 2 else 0) for p in pts}).reindex(s.index).fillna(0)
    r = s.pct_change().dropna()
    r = r[np.isfinite(r)]
    if not len(r):
        return []
    last_year = r.index[-1].year
    out = []
    for yr, g in r.groupby(r.index.year):
        if len(g) < 5:
            continue
        ret = float((1.0 + g).prod() - 1.0)
        if abs(ret) > 3.0:           # 300%↑ = 데이터 글리치, 그 해 스킵
            continue
        vol = float(g.std() * np.sqrt(252.0)) if len(g) > 1 else 0.0
        cum = (1.0 + g).cumprod()
        mdd = float((cum / cum.cummax() - 1.0).min())
        syn_frac = float(syn.reindex(g.index).fillna(0).mean()) if len(g) else 0.0
        partial = yr == last_year and len(g) < 230
        if actual_only and (syn_frac > 0 or partial):
            continue
        row = {
            "year": int(yr),
            "ret": round(ret, 6),
            "vol": round(vol, 6),
            "mdd": round(mdd, 6),
            "syn_frac": round(syn_frac, 4),
        }
        if partial:
            row["partial"] = True
        out.append(row)
    return out


def _item_deep(tickers):
    """항목(포폴/벤치) TR 인덱스 빌드 → (annual, rolling_return).
       추세 겹쳐보기와 같은 전체 TR 인덱스를 쓰되, 합성 구간 병적 점프만 방어한다."""
    try:
        from modules.tr_index import build_portfolio_tr_index
        from modules import rolling
        pts = build_portfolio_tr_index(tickers)
    except Exception:
        return [], None
    pts = _clean_deep_points(pts)
    annual = _annual_from_points(pts, actual_only=True)
    rr = None
    if len(pts) >= 13:
        syn_overall = sum(1 for p in pts if len(p) > 2 and p[2]) / len(pts)
        rr = {
            "horizons": rolling.DEFAULT_HORIZONS,
            "horizon_table": {str(h): v for h, v in rolling.horizon_table(pts, actual_only=True).items()},
            "syn_overall": round(float(syn_overall), 4),
        }
    return annual, rr


def _annual_dividends(weights, series):
    """포폴 연도별 배당: dyield(연 배당수익률) + dindex(첫해=100 정규화 배당액 흐름).
       weights={code:w}. 배당/성장률은 상장 전 백필·프록시 구간을 제외하고 실제 구간만 사용."""
    usable = {}
    first_years, last_years = [], []
    for code, w in weights.items():
        s = series.get(code)
        if not s or not len(s[0]):
            continue
        close, div = s[0], s[1]
        actual = s[2].reindex(close.index).fillna(False) if len(s) > 2 else pd.Series(True, index=close.index)
        actual_close = close[actual]
        if len(actual_close) < _DIV_MIN_ACTUAL_DAYS:
            continue
        usable[code] = (w, close, div, actual.astype(bool), float(actual_close.iloc[0]))
        first_years.append(int(actual_close.index[0].year))
        last_years.append(int(actual_close.index[-1].year))
    if len(usable) != len(weights):
        return []
    years = list(range(max(first_years), min(last_years) + 1))
    latest = min((v[1][v[3]].index[-1] for v in usable.values()), default=None)

    out = []
    for y in years:
        dyield = 0.0
        damt = 0.0
        partial = False
        ok = True
        for code, (w, close, div, actual, px0) in usable.items():
            ys, ye = pd.Timestamp(y, 1, 1), pd.Timestamp(y, 12, 31)
            mask = (close.index >= ys) & (close.index <= ye) & actual
            if int(mask.sum()) < _DIV_MIN_ACTUAL_DAYS:
                ok = False
                break
            if int(mask.sum()) < _DIV_FULL_YEAR_DAYS:
                partial = True
            dsum = float(div[mask].sum())
            yc = close[mask]
            px_end = float(yc.iloc[-1])
            if px_end > 0:
                dyield += w * (dsum / px_end)   # 연 배당수익률
            # 정규화 배당액 = 실제 첫 종가 기준 주당배당 흐름
            if px0 > 0:
                damt += w * (dsum / px0)
        if not ok:
            continue
        row = {"year": int(y), "dyield": round(dyield, 6), "dindex": round(damt, 6)}
        if partial or (latest is not None and y == latest.year and latest.month < 12):
            row["partial"] = True
        out.append(row)
    return out


def _dividend_growth(annual_div):
    """연배당액(dindex) → {cagr, yoy:[{year, growth}]}.

    아주 작은 첫 배당/부분연도 때문에 +2000% 같은 저베이스 스파이크가 나오면 차트 축 전체를
    망가뜨리므로 성장률 표본에서 제외한다. 배당 자체 표시는 유지하고, 성장률만 안정 구간 기준.
    """
    raw = [(d["year"], d["dindex"]) for d in (annual_div or [])
           if d.get("dindex", 0) > 0 and not d.get("partial")]
    if not raw:
        return {"cagr": None, "yoy": []}
    vals = np.array([v for _, v in raw], dtype=float)
    med = float(np.median(vals[vals > 0])) if np.any(vals > 0) else 0.0
    min_base = med * _DIV_GROWTH_LOW_BASE_FRACTION if med > 0 else 0.0
    pts = [(y, v) for y, v in raw if v >= min_base]
    yoy = []
    for i in range(1, len(pts)):
        y0, prev = pts[i - 1]
        y1, cur = pts[i]
        if prev > 0 and y1 - y0 == 1:
            growth = cur / prev - 1.0
            if abs(growth) <= _DIV_GROWTH_SPIKE_LIMIT:
                yoy.append({"year": y1, "growth": round(growth, 4)})
    cagr = None
    if len(pts) >= 2:
        y0, v0 = pts[0]; y1, v1 = pts[-1]
        span = y1 - y0
        if span >= 1 and v0 > 0:
            cagr = round((v1 / v0) ** (1.0 / span) - 1.0, 4)
    return {"cagr": cagr, "yoy": yoy}


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
    for code, s in series.items():
        close, div = s[0], s[1]
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
            tk = [{"code": c, "weight": w * 100.0} for c, w in weights.items()]
            annual, rr = _item_deep(tk)
            div_y = _annual_dividends(weights, series)
            items.append({"kind": "portfolio", "name": name, **m,
                          "annual": annual, "annual_div": div_y,
                          "divgrowth": _dividend_growth(div_y), "rolling_return": rr})
    for b in bench_list:
        m = _metrics_full(rets_c[b["code"]], spy_r, yld.get(b["code"], 0.0))
        if m:
            annual, rr = _item_deep([{"code": b["code"], "weight": 100.0}])
            div_y = _annual_dividends({b["code"]: 1.0}, series)
            items.append({"kind": "benchmark", "name": b["name"], "code": b["code"], **m,
                          "annual": annual, "annual_div": div_y,
                          "divgrowth": _dividend_growth(div_y), "rolling_return": rr})

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
