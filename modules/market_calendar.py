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
    101: "🇺🇸 FOMC",
}

_econ_cache = {}    # {today: [events]}
_sym_cache = {}     # {(code, today): [events]}


def _fred_key():
    import os
    return os.environ.get("FRED_API_KEY") or (FRED_KEY_FILE.read_text().strip() if FRED_KEY_FILE.exists() else "")


def econ_events():
    """향후~과거 1년 주요 지표 발표일. 캐시(일 단위)."""
    today = datetime.date.today().isoformat()
    if today in _econ_cache:
        return _econ_cache[today]
    key = _fred_key()
    start = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
    out = []
    for rid, label in CAL_RELEASES.items():
        try:
            r = requests.get("https://api.stlouisfed.org/fred/release/dates",
                             params={"release_id": rid, "api_key": key, "file_type": "json",
                                     "realtime_start": start, "sort_order": "asc",
                                     "include_release_dates_with_no_data": "true", "limit": 400},
                             timeout=20).json()
            for d in r.get("release_dates", []):
                out.append({"date": d["date"], "type": "econ", "title": label})
        except Exception:
            continue
    _econ_cache.clear()
    _econ_cache[today] = out
    return out


def _yf_symbol(code):
    """앱 코드 → yfinance 심볼. KR 6자리 → .KS, 지수/금/크립토 제외."""
    c = code.upper()
    if c.startswith("^") or c == "KRX_GOLD" or c.endswith("=F") or c.endswith("=X") or "-" in c:
        return None
    if c.isdigit() and len(c) == 6:
        return c + ".KS"
    return c


def symbol_events(code):
    """종목 다음 실적 발표일 + 배당락일. 캐시(일 단위)."""
    today = datetime.date.today().isoformat()
    ck = (code, today)
    if ck in _sym_cache:
        return _sym_cache[ck]
    sym = _yf_symbol(code)
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
            xd = cal.get("Ex-Dividend Date")
            if xd:
                out.append({"date": xd.isoformat() if hasattr(xd, "isoformat") else str(xd),
                            "type": "dividend", "title": f"{code} 배당락", "symbol": code})
        except Exception:
            pass
    _sym_cache[ck] = out
    return out


def events_for(codes):
    """경제지표(공개) + 종목 이벤트(codes) 합본."""
    out = list(econ_events())
    seen = set()
    for c in codes or []:
        if c in seen:
            continue
        seen.add(c)
        out.extend(symbol_events(c))
    return out
