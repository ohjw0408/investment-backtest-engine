"""내자산 배당금 월별 차트 데이터.

과거 3년 월별 실적 + 미래 1년(현재연도) 예측. 종목별 최근 5년 배당성장률(CAGR)로 투영.

가정/규약:
- 거래내역 없음 → 과거 배당도 '현재 보유 수량을 그대로 보유했다'고 가정.
- FX: 원화 보기 = 외화 배당을 그 당시(ex-date) 환율로 원화 환산.
       외화($) 보기 = 원화 배당을 그 당시 환율로 달러 환산.
       미래 예측은 현재 환율 기준.
- 세후: 일반 계좌 = 국내 15.4% / 미국 15% 원천징수. ISA·연금저축·IRP = 운용 중 비과세(세후=세전).
"""
from datetime import datetime

import pandas as pd

PAST_YEARS      = 3       # 과거 실적 연도 수
CAGR_YEARS      = 5       # 성장률 산출에 쓰는 완료 연도 수
KR_DIV_TAX      = 0.154
US_DIV_TAX      = 0.15
EXEMPT_ACCOUNTS = {"ISA", "연금저축", "IRP"}   # 운용 중 비과세


def _fx_on(fx: pd.Series, date_str: str) -> float:
    ts = pd.Timestamp(date_str[:10])
    s  = fx[fx.index <= ts]
    return float(s.iloc[-1]) if len(s) else float(fx.iloc[-1])


def _ticker_cagr(per_year_dps: dict, base_year: int) -> float:
    """최근 CAGR_YEARS 완료연도(base_year 이하)의 주당배당 합 CAGR. 부족/이상치는 0/클램프."""
    yrs = sorted(y for y in per_year_dps if y <= base_year)[-CAGR_YEARS:]
    if len(yrs) < 2:
        return 0.0
    first, last = per_year_dps[yrs[0]], per_year_dps[yrs[-1]]
    n = yrs[-1] - yrs[0]
    if first <= 0 or n <= 0:
        return 0.0
    cagr = (last / first) ** (1.0 / n) - 1.0
    return max(-0.5, min(cagr, 1.0))   # 비정상 방지 클램프 (-50%~+100%)


def build_dividend_chart(loader, holdings) -> dict:
    cur_year   = datetime.today().year
    proj_year  = cur_year                              # 미래 1년 = 현재연도(예측)
    base_year  = cur_year - 1                          # 예측 베이스 = 직전 완료연도
    past_years = [cur_year - i for i in range(PAST_YEARS, 0, -1)]   # [Y-3, Y-2, Y-1]
    min_year   = (cur_year - PAST_YEARS) - CAGR_YEARS  # CAGR 계산용 하한

    try:
        fx = loader._load_usdkrw()
        cur_fx = float(fx.iloc[-1])
    except Exception:
        fx, cur_fx = None, 1300.0

    chart_years = past_years + [proj_year]

    def _empty():
        return {y: [0.0] * 12 for y in chart_years}

    series = {c: {t: _empty() for t in ("pretax", "posttax")} for c in ("KRW", "USD")}
    growth = {}
    has_foreign = False

    def _accumulate(year, month, native, is_kr, fx_rate, div_tax):
        if fx_rate <= 0:
            fx_rate = cur_fx
        if is_kr:
            krw, usd = native, native / fx_rate
        else:
            usd, krw = native, native * fx_rate
        i = month - 1
        series["KRW"]["pretax"][year][i]  += krw
        series["KRW"]["posttax"][year][i] += krw * (1 - div_tax)
        series["USD"]["pretax"][year][i]  += usd
        series["USD"]["posttax"][year][i] += usd * (1 - div_tax)

    conn = loader.conn
    for h in holdings:
        code = str(h.get("code", "")).split(".")[0].upper()
        qty  = float(h.get("quantity") or 0)
        if qty <= 0 or code in ("", "KRX_GOLD"):
            continue
        is_kr  = loader.is_kr_etf(code)
        if not is_kr:
            has_foreign = True
        acct   = h.get("account_type") or "일반"
        div_tax = 0.0 if acct in EXEMPT_ACCOUNTS else (KR_DIV_TAX if is_kr else US_DIV_TAX)

        rows = conn.execute(
            "SELECT date, dividend FROM corporate_actions "
            "WHERE code=? AND dividend>0 AND date>=? ORDER BY date",
            (code, f"{min_year}-01-01")
        ).fetchall()
        if not rows:
            continue

        per_year_dps = {}
        for d, dps in rows:
            y = int(d[:4])
            per_year_dps[y] = per_year_dps.get(y, 0.0) + float(dps)

        cagr = _ticker_cagr(per_year_dps, base_year)
        growth[code] = round(cagr, 4)

        for d, dps in rows:
            y, m = int(d[:4]), int(d[5:7])
            fx_rate = _fx_on(fx, d) if fx is not None else cur_fx
            if y in past_years:                                  # 과거 실적
                _accumulate(y, m, float(dps) * qty, is_kr, fx_rate, div_tax)
            if y == base_year:                                   # 미래 예측(베이스 패턴 × 성장)
                _accumulate(proj_year, m, float(dps) * qty * (1 + cagr), is_kr, cur_fx, div_tax)

    return {
        "past_years":  past_years,
        "proj_year":   proj_year,
        "series":      series,
        "growth":      growth,
        "has_foreign": has_foreign,
    }
