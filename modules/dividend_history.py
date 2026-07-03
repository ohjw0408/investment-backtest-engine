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


_gap_refetched = {}   # code -> date — 갭 재페치는 프로세스당 하루 1회


def _refetch_gap_dividends(conn, code, is_kr, rows, cur_year, base_year, today):
    """올해 지나간 달의 배당 저장 갭 감지 시 yfinance 재페치. 재페치 수행 여부 반환."""
    cur_months  = {int(d[5:7]) for d, _ in rows if d[:4] == str(cur_year)}
    base_months = {int(d[5:7]) for d, _ in rows if d[:4] == str(base_year)}
    gap = any(m in base_months and m not in cur_months for m in range(1, today.month))
    if not gap or _gap_refetched.get(code) == today.date():
        return False
    _gap_refetched[code] = today.date()
    try:
        import yfinance as yf
        div = yf.Ticker(f"{code}.KS" if is_kr else code).dividends
        if div is None or div.empty:
            return False
        new_rows = [(code, d.strftime("%Y-%m-%d"), float(v), 1.0)
                    for d, v in div.items() if float(v) > 0]
        # 가격 페치가 전 거래일에 dividend=0 행을 미리 깔아두므로(스플릿 기록 겸용)
        # INSERT OR IGNORE로는 갭이 영영 안 메워짐 → 0/NULL 행만 실배당값으로 갱신.
        conn.executemany(
            "INSERT INTO corporate_actions (code, date, dividend, split) VALUES (?,?,?,?) "
            "ON CONFLICT(code, date) DO UPDATE SET dividend=excluded.dividend "
            "WHERE corporate_actions.dividend IS NULL OR corporate_actions.dividend<=0",
            new_rows)
        conn.commit()
        return True
    except Exception:
        return False


def build_dividend_chart(loader, holdings):
    today      = datetime.today()
    cur_year   = today.year
    base_year  = cur_year - 1                 # 예측 베이스 = 직전 완료연도
    next_year  = cur_year + 1                 # 전체 예측 연도
    past_years = [cur_year - i for i in range(PAST_YEARS, 0, -1)]   # [Y-3, Y-2, Y-1] 실적
    # 차트 연도: 과거 3년 실적 + 현재연도(실적+예측 혼합) + 내년(전체 예측)
    chart_years = past_years + [cur_year, next_year]
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

        # 올해 '지나간 달' 배당 갭 self-heal — 작년엔 지급된 달인데 올해 그 달 행이 없으면
        # 저장 갭(INSERT OR IGNORE라 자연 복구 안 됨. 예: TLT 2026-04 누락)으로 보고
        # yfinance 배당 이력을 재페치해 없던 행만 추가한다. 종목당 하루 1회.
        if _refetch_gap_dividends(conn, code, is_kr, rows, cur_year, base_year, today):
            rows = conn.execute(
                "SELECT date, dividend FROM corporate_actions "
                "WHERE code=? AND dividend>0 AND date>=? ORDER BY date",
                (code, f"{min_year}-01-01")
            ).fetchall()

        per_year_dps = {}
        for d, dps in rows:
            per_year_dps[int(d[:4])] = per_year_dps.get(int(d[:4]), 0.0) + float(dps)
        cagr = _ticker_cagr(per_year_dps, base_year)
        growth[code] = round(cagr, 4)

        # 과거 3년 실적 + 현재연도 실적 부분
        real_months_cur = set()
        base_events = []   # 베이스(직전연도) 월/일/주당배당 — 예측 패턴 소스
        for d, dps in rows:
            y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
            if y in past_years:
                rate = _fx_on(fx, d) if fx is not None else cur_fx
                events[y].append(_event(d[:10], m, day, code, float(dps) * qty, is_kr, rate, div_tax, False))
            if y == cur_year:           # 현재연도 실데이터 부분
                rate = _fx_on(fx, d) if fx is not None else cur_fx
                events[cur_year].append(_event(d[:10], m, day, code, float(dps) * qty, is_kr, rate, div_tax, False))
                real_months_cur.add(m)
            if y == base_year:
                base_events.append((m, day, float(dps)))

        # 현재연도 예측 부분 — 실데이터 없는 달을 작년 같은 달 배당 × (1+cagr)로 채운다.
        # 단 **이번 달 이후만**: 이미 지나간 달을 '예측'으로 표시하는 건 무의미하고
        # (오너 제보 2026-07-03), 지나간 달의 진짜 갭은 위 재페치가 실데이터로 채운다.
        for m, day, dps in base_events:
            if m not in real_months_cur and m >= today.month:
                pdate = f"{cur_year}-{m:02d}-{day:02d}"
                events[cur_year].append(
                    _event(pdate, m, day, code, dps * qty * (1 + cagr), is_kr, cur_fx, div_tax, True))

        # 내년 전체 예측 — 베이스×(1+cagr)^2
        for m, day, dps in base_events:
            ndate = f"{next_year}-{m:02d}-{day:02d}"
            events[next_year].append(
                _event(ndate, m, day, code, dps * qty * (1 + cagr) ** 2, is_kr, cur_fx, div_tax, True))

    for y in events:
        events[y].sort(key=lambda e: e["date"])

    return {
        "years":            chart_years,
        "current_year":     cur_year,     # 실적+예측 혼합
        "full_proj_year":   next_year,    # 전체 예측
        "default_year":     cur_year,     # 기본 = 올해
        "growth":           growth,
        "has_foreign":      has_foreign,
        "events":           events,
    }
