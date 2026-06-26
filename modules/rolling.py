"""롤링 분석 공용 엔진 — 총수익 인덱스(시작=100류) 시계열에서 롤링/분포/낙폭 통계 산출.

순수함수·결정론. 분석탭(backtest)·비교탭(risk_return) 공용. 입력은 일별 인덱스 포인트
([[date, value], ...] 또는 [[date, value, syn], ...]) 또는 pandas Series.

설계: 롤링은 월말(month-end) 리샘플 기준(스텝=1개월) — 일별 불필요·비용↓·시각 충분.
horizon은 연단위(1·3·5·10·15·20년). 손실확률 = 그 horizon 윈도우 중 총수익 음수 비율.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_HORIZONS = [1, 3, 5, 10, 15, 20]
DEFAULT_PCTS = [0, 25, 75, 100]   # 오차막대 기본(최저·p25·p75·최고). 사용자 변경 가능.


def _to_series(points) -> pd.Series:
    """points → 정렬된 float Series(date index). syn(3번째)은 무시."""
    if isinstance(points, pd.Series):
        s = points.dropna()
    else:
        s = pd.Series({p[0]: p[1] for p in points if p[1] is not None})
    if s.empty:
        return s
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _syn_series(points) -> pd.Series | None:
    """points 3번째(syn) → bool Series. 없으면 None."""
    if isinstance(points, pd.Series) or not points:
        return None
    if len(points[0]) < 3:
        return None
    s = pd.Series({p[0]: bool(p[2]) for p in points})
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def monthly_index(points) -> pd.Series:
    """월말 인덱스값(롤링 기준). 빈 시리즈면 그대로."""
    s = _to_series(points)
    if s.empty:
        return s
    return s.resample("ME").last().dropna()


def rolling_cagr(points, years: int):
    """직전 `years`년 CAGR 월별 시계열 → [[YYYY-MM-DD, cagr(소수)], ...].
       표본(월말값) 부족하면 []."""
    m = monthly_index(points)
    if len(m) < years * 12 + 1:
        return []
    shifted = m.shift(years * 12)
    cagr = (m / shifted) ** (1.0 / years) - 1.0
    cagr = cagr.dropna()
    return [[d.strftime("%Y-%m-%d"), round(float(v), 6)] for d, v in cagr.items()]


def _pct(arr: np.ndarray, p: float) -> float:
    return float(np.percentile(arr, p)) if arr.size else 0.0


def horizon_table(points, horizons=None, percentiles=None):
    """horizon별 롤링 총수익(=CAGR) 분포 통계.
       반환: {h: {n, loss_prob, median, syn_frac, pcts:{p값:cagr}}}.
       n<3이면 표본부족(요약은 주되 UI서 회색 처리 판단)."""
    horizons = horizons or DEFAULT_HORIZONS
    percentiles = percentiles if percentiles is not None else DEFAULT_PCTS
    m = monthly_index(points)
    syn = _syn_series(points)
    syn_m = None
    if syn is not None and not syn.empty:
        # 월말 기준 syn(그 달에 합성 섞였나) — 월내 any
        syn_m = syn.resample("ME").max().reindex(m.index).fillna(False).astype(bool)

    out = {}
    for h in horizons:
        need = h * 12
        if len(m) < need + 1:
            out[h] = {"n": 0, "loss_prob": None, "median": None, "syn_frac": None, "pcts": {}}
            continue
        shifted = m.shift(need)
        cagr = ((m / shifted) ** (1.0 / h) - 1.0).dropna()
        arr = cagr.values.astype(float)
        n = arr.size
        # 윈도우별 합성 의존도 — 끝점이 syn인 비율(근사)
        syn_frac = None
        if syn_m is not None:
            ends = syn_m.reindex(cagr.index).fillna(False)
            syn_frac = round(float(ends.mean()), 4) if n else None
        out[h] = {
            "n": int(n),
            "loss_prob": round(float((arr < 0).mean()), 4) if n else None,
            "median": round(float(np.median(arr)), 6) if n else None,
            "syn_frac": syn_frac,
            "pcts": {str(p): round(_pct(arr, p), 6) for p in percentiles} if n else {},
        }
    return out


def drawdown(points):
    """낙폭(underwater) + 최대낙폭·회복·최장 침수기간.
       반환: {underwater:[[date, dd(음수)], ...], max_dd, max_dd_date,
              recovery_date, recovery_days(저점→회복), longest_underwater_days}."""
    s = _to_series(points)
    if len(s) < 2:
        return {"underwater": [], "max_dd": 0.0, "max_dd_date": None,
                "recovery_date": None, "recovery_days": None, "longest_underwater_days": None}
    peak = s.cummax()
    dd = s / peak - 1.0
    under = [[d.strftime("%Y-%m-%d"), round(float(v), 6)] for d, v in dd.items()]
    max_dd = float(dd.min())
    trough_date = dd.idxmin()
    peak_val = float(peak.loc[trough_date])
    # 저점 이후 첫 회복(peak 회복)
    after = s.loc[trough_date:]
    rec = after[after >= peak_val]
    recovery_date = rec.index[0] if len(rec) else None
    recovery_days = int((recovery_date - trough_date).days) if recovery_date is not None else None
    # 최장 침수기간(낙폭<0 연속 구간 최대 일수)
    longest = 0
    cur_start = None
    prev = None
    for d, v in dd.items():
        if v < -1e-9:
            if cur_start is None:
                cur_start = prev if prev is not None else d
        else:
            if cur_start is not None:
                longest = max(longest, int((d - cur_start).days))
                cur_start = None
        prev = d
    if cur_start is not None:
        longest = max(longest, int((dd.index[-1] - cur_start).days))
    return {
        "underwater": under,
        "max_dd": round(max_dd, 6),
        "max_dd_date": trough_date.strftime("%Y-%m-%d"),
        "recovery_date": recovery_date.strftime("%Y-%m-%d") if recovery_date is not None else None,
        "recovery_days": recovery_days,
        "longest_underwater_days": longest,
    }


def real_adjust(points, infl: float = 0.02):
    """인플레 반영 실질 인덱스 — 명목값을 시작일 기준 누적물가로 할인.
       infl=연 물가상승률(기본 2%). 반환=points와 같은 형식([date, real_value(, syn)])."""
    s = _to_series(points)
    if s.empty:
        return []
    t0 = s.index[0]
    days = (s.index - t0).days.values.astype(float)
    deflator = (1.0 + infl) ** (days / 365.25)
    real = s.values / deflator
    syn = _syn_series(points)
    out = []
    for i, (d, _v) in enumerate(s.items()):
        row = [d.strftime("%Y-%m-%d"), round(float(real[i]), 6)]
        if syn is not None:
            row.append(int(bool(syn.get(d, False))))
        out.append(row)
    return out
