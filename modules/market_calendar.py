# -*- coding: utf-8 -*-
"""
증시 캘린더 (읽기 전용): 경제지표 발표일(FRED) + 종목 실적·배당일(yfinance).

- econ_events: 주요 미국 지표 발표 일정 (FRED /fred/release/dates, 향후 포함).
- symbol_events: 종목별 다음 실적 발표일 + 배당락일 (yfinance Ticker.calendar).
캐시 = 날짜 단위 메모리(하루 1회 갱신).
"""
import datetime
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
FRED_KEY_FILE = BASE / "data" / "meta" / "fred_api_key.txt"

# FRED release_id → 표시명 (주요 지표만 큐레이션)
CAL_RELEASES = {
    10: "🇺🇸 소비자물가 CPI",
    46: "🇺🇸 생산자물가 PPI",
    50: "🇺🇸 고용보고서(비농업)",
    53: "🇺🇸 GDP",
    54: "🇺🇸 개인소득·PCE",
    9:  "🇺🇸 소매판매",
    13: "🇺🇸 산업생산",
    192: "🇺🇸 JOLTS 구인",
    # FOMC(101)는 FRED 릴리스가 매 영업일 갱신일을 반환 → 회의일 아님, 제외.
}

_econ_cache = {}    # {today: [events]}
_earn_cache = {}    # {(code, today): [events]}
_div_cache = {}     # {(codes_key, today): [events]}


def _fred_key():
    import os
    return os.environ.get("FRED_API_KEY") or (FRED_KEY_FILE.read_text().strip() if FRED_KEY_FILE.exists() else "")


def econ_events():
    """주요 지표 발표일 (과거 ~45일 + 향후 ~150일, 실제 발표일만). 캐시(일 단위)."""
    today = datetime.date.today()
    tk = today.isoformat()
    if tk in _econ_cache:
        return _econ_cache[tk]
    key = _fred_key()
    rt_start = (today - datetime.timedelta(days=45)).isoformat()
    rt_end = (today + datetime.timedelta(days=150)).isoformat()
    out = []
    for rid, label in CAL_RELEASES.items():
        try:
            r = requests.get("https://api.stlouisfed.org/fred/release/dates",
                             params={"release_id": rid, "api_key": key, "file_type": "json",
                                     "realtime_start": rt_start, "realtime_end": rt_end,
                                     "sort_order": "asc", "include_release_dates_with_no_data": "true",
                                     "limit": 200},
                             timeout=20).json()
            for d in r.get("release_dates", []):
                out.append({"date": d["date"], "type": "econ", "title": label})
        except Exception:
            continue
    _econ_cache.clear()
    _econ_cache[tk] = out
    return out


def _yf_stock(code):
    """앱 코드 → yfinance 심볼(주식만). ETF/지수/금/크립토/KR ETF → None(실적 없음)."""
    c = code.upper()
    if c.startswith("^") or c == "KRX_GOLD" or c.endswith("=F") or c.endswith("=X") or "-" in c:
        return None
    if c.isdigit():           # 국내(주식/ETF 구분 불가) — 실적은 스킵(배당은 엔진이 처리)
        return None
    return c


def earnings_events(code):
    """미국 개별주 실적 발표일 (yfinance). ETF/지수 등은 없음. 캐시(일 단위)."""
    tk = datetime.date.today().isoformat()
    ck = (code, tk)
    if ck in _earn_cache:
        return _earn_cache[ck]
    sym = _yf_stock(code)
    out = []
    if sym:
        try:
            import yfinance as yf
            cal = yf.Ticker(sym).calendar or {}
            ed = cal.get("Earnings Date")
            if isinstance(ed, list) and ed:
                ed = ed[0]
            if ed:
                out.append({"date": ed.isoformat() if hasattr(ed, "isoformat") else str(ed),
                            "type": "earnings", "title": f"{code} 실적발표", "symbol": code})
        except Exception:
            pass
    _earn_cache[ck] = out
    return out


def dividend_events(loader, codes):
    """배당락일 (앱 배당엔진 = corporate_actions 이력 + 투영). ETF·월배당 포함. 캐시(일 단위)."""
    tk = datetime.date.today().isoformat()
    key = (tuple(sorted(codes)), tk)
    if key in _div_cache:
        return _div_cache[key]
    out = []
    try:
        from modules import dividend_history as DH
        res = DH.build_dividend_chart(loader, [{"code": c, "quantity": 1} for c in codes])
        floor = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
        for y in res.get("events", {}):
            for e in res["events"][y]:
                d = e.get("date")
                if not d or d < floor:
                    continue
                pred = bool(e.get("predicted")) or (d > tk)
                out.append({"date": d, "type": "dividend", "symbol": e.get("code"),
                            "title": f"{e.get('code')} 배당락" + (" (예상)" if pred else "")})
    except Exception:
        pass
    _div_cache[key] = out
    return out


def events_for(codes, loader=None):
    """경제지표(공개) + 실적(개별주, yfinance) + 배당락(배당엔진) 합본."""
    out = list(econ_events())
    codes = list(dict.fromkeys(codes or []))
    for c in codes:
        out.extend(earnings_events(c))
    if loader is not None and codes:
        out.extend(dividend_events(loader, codes))
    seen, uniq = set(), []
    for e in out:
        k = (e["date"], e["type"], e["title"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)
    return uniq
