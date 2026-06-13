"""내자산 배당금 차트 데이터 — 이벤트 기반.

연도별 배당 이벤트(날짜·종목·금액 4변형)를 반환하면 프론트가 막대·드릴다운·캘린더를 파생한다.

과거 PAST_YEARS년 실적 + 미래 1년(현재연도) 예측. 종목별 최근 5년 배당 CAGR로 투영.

가정/규약:
- 거래내역 없음 → 과거 배당도 '현재 보유 수량을 그대로 보유'했다고 가정.
- FX: 원화 = 외화배당 × ex-date 환율, 외화($) = 원화배당 ÷ ex-date 환율. 미래 예측은 현재 환율.
- 세후: 일반 계좌 = 국내 15.4% / 미국 15%. ISA·연금저축·IRP = 운용 중 비과세(세후=세전).
"""
import sqlite3
from datetime import datetime

import pandas as pd

from config import SYMBOL_DB_PATH

PAST_YEARS      = 3
CAGR_YEARS      = 5
KR_DIV_TAX      = 0.154
US_DIV_TAX      = 0.15
EXEMPT_ACCOUNTS = {"ISA", "연금저축", "IRP"}


def _fx_on(fx, date_str):
    ts = pd.Timestamp(date_str[:10])
    s  = fx[fx.index <= ts]
    return float(s.iloc[-1]) if len(s) else float(fx.iloc[-1])


def _ticker_cagr(per_year_dps, base_year):
    yrs = sorted(y for y in per_year_dps if y <= base_year)[-CAGR_YEARS:]
    if len(yrs) < 2:
        return 0.0
    first, last = per_year_dps[yrs[0]], per_year_dps[yrs[-1]]
    n = yrs[-1] - yrs[0]
    if first <= 0 or n <= 0:
        return 0.0
    return max(-0.5, min((last / first) ** (1.0 / n) - 1.0, 1.0))


def _load_names(codes):
    names = {}
    try:
        c = sqlite3.connect(SYMBOL_DB_PATH)
        qs = ",".join("?" * len(codes))
        for code, name in c.execute(
            f"SELECT code, name FROM symbols WHERE code IN ({qs})", list(codes)
        ).fetchall():
            names[str(code).upper()] = name
        c.close()
    except Exception:
        pass
    return names


def build_dividend_chart(loader, holdings):
    cur_year   = datetime.today().year
    proj_year  = cur_year
    base_year  = cur_year - 1
    past_years = [cur_year - i for i in range(PAST_YEARS, 0, -1)]
    chart_years = past_years + [proj_year]
    min_year   = (cur_year - PAST_YEARS) - CAGR_YEARS

    try:
        fx = loader._load_usdkrw()
        cur_fx = float(fx.iloc[-1])
    except Exception:
        fx, cur_fx = None, 1300.0

    codes = {str(h.get("code", "")).split(".")[0].upper() for h in holdings}
    names = _load_names(codes) if codes else {}

    events = {y: [] for y in chart_years}
    growth = {}
    has_foreign = False

    def _event(date, month, day, code, native, is_kr, fx_rate, div_tax, projected):
        if fx_rate <= 0:
            fx_rate = cur_fx
        if is_kr:
            krw, usd = native, native / fx_rate
        else:
            usd, krw = native, native * fx_rate
        return {
            "date": date, "month": month, "day": day,
            "code": code, "name": names.get(code, code),
            "krw_pre": round(krw, 2),  "krw_post": round(krw * (1 - div_tax), 2),
            "usd_pre": round(usd, 4),  "usd_post": round(usd * (1 - div_tax), 4),
            "projected": projected,
        }

    conn = loader.conn
    for h in holdings:
        code = str(h.get("code", "")).split(".")[0].upper()
        qty  = float(h.get("quantity") or 0)
        if qty <= 0 or code in ("", "KRX_GOLD"):
            continue
        is_kr   = loader.is_kr_etf(code)
        if not is_kr:
            has_foreign = True
        acct    = h.get("account_type") or "일반"
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
            per_year_dps[int(d[:4])] = per_year_dps.get(int(d[:4]), 0.0) + float(dps)
        cagr = _ticker_cagr(per_year_dps, base_year)
        growth[code] = round(cagr, 4)

        for d, dps in rows:
            y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
            if y in past_years:
                rate = _fx_on(fx, d) if fx is not None else cur_fx
                events[y].append(_event(d[:10], m, day, code, float(dps) * qty, is_kr, rate, div_tax, False))
            if y == base_year:
                pdate = f"{proj_year}-{m:02d}-{day:02d}"
                events[proj_year].append(
                    _event(pdate, m, day, code, float(dps) * qty * (1 + cagr), is_kr, cur_fx, div_tax, True))

    for y in events:
        events[y].sort(key=lambda e: e["date"])

    return {
        "years":       chart_years,
        "proj_year":   proj_year,
        "default_year": base_year,     # 기본 = 직전 완료연도(실데이터)
        "growth":      growth,
        "has_foreign": has_foreign,
        "events":      events,
    }
