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


def econ_events(ids=None):
    """주요 지표 발표일 (과거 ~45일 + 향후 ~150일). ids=허용 release_id set(None=전체)."""
    all_ev = _econ_events_all()
    if ids is None:
        return all_ev
    ids = set(ids)
    return [e for e in all_ev if e.get("rid") in ids]


def _econ_events_all():
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
                out.append({"date": d["date"], "type": "econ", "title": label, "rid": rid})
        except Exception:
            continue
    _econ_cache.clear()
    _econ_cache[tk] = out
    return out


def _yf_stock(code):
    """앱 코드 → yfinance 심볼(실적용). 지수/금/크립토 → None. KR 6자리 → .KS(폴백 .KQ)."""
    c = code.upper()
    if c.startswith("^") or c == "KRX_GOLD" or c.endswith("=F") or c.endswith("=X") or "-" in c:
        return None
    if c.isdigit() and len(c) == 6:
        return c + ".KS"
    return c


def earnings_events(code, name=None):
    """개별주 실적 발표일 (yfinance, 과거+미래 분기). ETF/지수 없음. 캐시(일 단위)."""
    label = name or code
    tk = datetime.date.today().isoformat()
    ck = (code, tk)
    if ck in _earn_cache:
        return [{**e, "title": f"{label} 실적발표"} for e in _earn_cache[ck]]
    sym = _yf_stock(code)
    out = []
    if sym:
        floor = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
        import yfinance as yf
        # KR은 .KS 먼저, 비면 .KQ(코스닥) 폴백
        syms = [sym, sym[:-3] + ".KQ"] if sym.endswith(".KS") else [sym]
        for s in syms:
            try:
                ed = yf.Ticker(s).get_earnings_dates(limit=16)
            except Exception:
                ed = None
            if ed is not None and len(ed.index):
                for idx in ed.index:
                    d = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
                    if d >= floor:
                        out.append({"date": d, "type": "earnings", "title": f"{label} 실적발표", "symbol": code})
                break
        # 중복 날짜 제거
        seen, uq = set(), []
        for e in out:
            if e["date"] in seen:
                continue
            seen.add(e["date"]); uq.append(e)
        out = uq
    _earn_cache[ck] = out
    return out


def dividend_events(loader, codes, names=None):
    """배당락일 (앱 배당엔진 = corporate_actions 이력 + 투영). ETF·월배당 포함. 캐시(일 단위)."""
    names = names or {}
    tk = datetime.date.today().isoformat()
    key = (tuple(sorted(codes)), tk)
    if key in _div_cache:
        return [{**e, "title": f"{names.get(e['symbol'], e['symbol'])} 배당락"
                 + (" (예상)" if "(예상)" in e["title"] else "")} for e in _div_cache[key]]
    out = []
    # 배당 대상만(지수/환율/원자재선물/크립토/KRX금 제외) — 비대상 코드가 엔진을 깨뜨림
    dcodes = [c for c in codes if not (c.startswith("^") or c.upper() == "KRX_GOLD"
              or c.endswith("=X") or c.endswith("=F") or "-" in c)]
    if not dcodes:
        _div_cache[key] = out
        return out
    try:
        from modules import dividend_history as DH
        res = DH.build_dividend_chart(loader, [{"code": c, "quantity": 1} for c in dcodes])
        floor = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
        for y in res.get("events", {}):
            for e in res["events"][y]:
                d = e.get("date")
                if not d or d < floor:
                    continue
                pred = bool(e.get("predicted")) or (d > tk)
                code = e.get("code")
                out.append({"date": d, "type": "dividend", "symbol": code,
                            "title": f"{names.get(code, code)} 배당락" + (" (예상)" if pred else "")})
    except Exception:
        pass
    _div_cache[key] = out
    return out


def events_for(codes, loader=None, econ_ids=None, show_earnings=True, show_dividend=True, names=None):
    """경제지표 + 실적(개별주) + 배당락(배당엔진). 종목명(names) 적용. config로 필터."""
    out = list(econ_events(econ_ids))
    codes = list(dict.fromkeys(codes or []))
    names = dict(names or {})
    if codes:
        try:
            from modules.dividend_history import _load_names
            loaded = _load_names(codes)
            for c in codes:
                if not names.get(c):
                    nm = loaded.get(c.upper())
                    if nm:
                        names[c] = nm
        except Exception:
            pass
    if show_earnings:
        for c in codes:
            out.extend(earnings_events(c, names.get(c)))
    if show_dividend and loader is not None and codes:
        out.extend(dividend_events(loader, codes, names))
    seen, uniq = set(), []
    for e in out:
        k = (e["date"], e["type"], e["title"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)
    return uniq
