"""대가 시점별(point-in-time) NAV 곡선 사전계산 — Flask-free 공용 모듈.

guru_holdings.db의 분기별 13F 상위 보유(비중)를 **공시일(filed)에 리밸런싱한 셈**으로
이어붙여 대가당 하나의 일간 총수익 지수(시작=100)를 만들고, price_daily.db의
`guru_nav` 테이블에 저장한다. 비교/겹쳐보기는 티커 수십 개 대신 이 곡선 1줄만 읽는다.

규칙:
- 세그먼트 k = filed(k) ~ 다음 filed(k+1) 전일. 그 구간 비중 = period(k) 상위
  TOP_N 매핑 종목을 비중합으로 재정규화(13F 전체 대비 비중 → 상위 N 내 비율).
- 공시일 리밸런싱 = 실제 추종자가 알 수 있는 시점(45일 공시 지연 반영, 미래정보 없음).
- 데이터 없는 종목/날은 그날 있는 종목끼리 재정규화(tr_index와 동일 철학).
- 재계산은 cik별 DELETE 후 INSERT — idempotent, 매일 전체 재빌드해도 안전.
"""
from __future__ import annotations

import os
import sqlite3

TOP_N = 10   # 세그먼트당 사용 상위 종목 수 — UI 보유표·기존 비교와 동일 규모

_GURU_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "data", "meta", "guru_holdings.db")


def _price_conn():
    from modules.price_loader import DB_PATH
    con = sqlite3.connect(str(DB_PATH))
    con.execute(
        "CREATE TABLE IF NOT EXISTS guru_nav ("
        " cik TEXT, date TEXT, value REAL, PRIMARY KEY (cik, date))"
    )
    return con


def _segments(cik):
    """cik → [(filed, [(ticker, w_norm), ...]), ...] filed 오름차순.
       w_norm = 상위 TOP_N 매핑 종목의 비중을 그들 합으로 재정규화."""
    con = sqlite3.connect(_GURU_DB)
    con.row_factory = sqlite3.Row
    filings = con.execute(
        "SELECT period, filed FROM filings WHERE cik=? ORDER BY filed", (cik,)
    ).fetchall()
    segs = []
    for f in filings:
        rows = con.execute(
            "SELECT ticker, weight FROM holdings "
            "WHERE cik=? AND period=? AND ticker IS NOT NULL AND weight>0 "
            "ORDER BY rank LIMIT ?", (cik, f["period"], TOP_N)
        ).fetchall()
        wsum = sum(r["weight"] for r in rows)
        if not rows or wsum <= 0:
            continue
        segs.append((f["filed"], [(r["ticker"].upper(), r["weight"] / wsum) for r in rows]))
    con.close()
    return segs


def build_guru_nav(cik, price_conn):
    """cik → [[date, value], ...] (시작=100). 데이터 부족 시 []."""
    import pandas as pd
    from modules.tr_index import ticker_tr_series

    segs = _segments(cik)
    if not segs:
        return []
    all_codes = sorted({c for _, ws in segs for c, _ in ws})
    trs = {}
    for code in all_codes:
        m, _syn = ticker_tr_series(price_conn, code)
        if m:
            trs[code] = pd.Series(m)
    if not trs:
        return []
    closes = pd.DataFrame(trs).sort_index()
    # fill_method=None 필수 — NULL홀 pad 시 가짜 점프(tr_index docstring 불변식)
    rets = closes.pct_change(fill_method=None)

    dates = closes.index          # 'YYYY-MM-DD' 문자열 — 사전순 = 시간순
    # 규약: 첫 공시일 종가 매수 = 시작 100. 세그먼트 k의 비중은 (filed_k, filed_{k+1}]
    # 구간 수익에 적용 — 리밸런싱 당일 수익은 직전 비중 몫(종가 리밸런싱).
    start_dates = dates[dates >= segs[0][0]]
    if len(start_dates) == 0:
        return []
    nav_dates, nav_vals = [start_dates[0]], [100.0]
    nav = 100.0
    for k, (filed, weights) in enumerate(segs):
        seg_end = segs[k + 1][0] if k + 1 < len(segs) else None
        mask = (dates > filed) if seg_end is None else ((dates > filed) & (dates <= seg_end))
        seg_dates = dates[mask]
        if len(seg_dates) == 0:
            continue
        w = pd.Series({c: v for c, v in weights if c in rets.columns}, dtype=float)
        if w.empty:
            continue
        r = rets.loc[seg_dates, w.index]
        avail = r.notna().mul(w, axis=1).sum(axis=1)              # 그날 존재 종목 비중합
        port = r.mul(w, axis=1).sum(axis=1).div(avail.replace(0.0, pd.NA)).fillna(0.0)
        for d, pr in port.items():
            if d <= nav_dates[-1]:
                continue
            nav *= (1.0 + float(pr))
            nav_dates.append(d)
            nav_vals.append(nav)
    return [[d, round(v, 4)] for d, v in zip(nav_dates, nav_vals)]


def rebuild_all(price_conn=None, warm=None):
    """전 대가 NAV 재계산 → guru_nav 저장. 반환 {slug: rows}.
       warm: callable(code) — 계산 전 종목 가격 적재 훅(beat에서 ensure_full_history)."""
    con_g = sqlite3.connect(_GURU_DB)
    con_g.row_factory = sqlite3.Row
    gurus = con_g.execute("SELECT cik, slug FROM gurus WHERE stale=0").fetchall()
    con_g.close()

    own = price_conn is None
    pc = price_conn or _price_conn()
    try:
        pc.execute(
            "CREATE TABLE IF NOT EXISTS guru_nav ("
            " cik TEXT, date TEXT, value REAL, PRIMARY KEY (cik, date))"
        )
        out = {}
        for g in gurus:
            if warm is not None:
                for code in sorted({c for _, ws in _segments(g["cik"]) for c, _w in ws}):
                    try:
                        warm(code)
                    except Exception:
                        pass
            pts = build_guru_nav(g["cik"], pc)
            pc.execute("DELETE FROM guru_nav WHERE cik=?", (g["cik"],))
            if pts:
                pc.executemany(
                    "INSERT INTO guru_nav (cik, date, value) VALUES (?,?,?)",
                    [(g["cik"], d, v) for d, v in pts],
                )
            pc.commit()
            out[g["slug"]] = len(pts)
        return out
    finally:
        if own:
            pc.close()


def load_nav(slug_or_cik):
    """저장된 NAV 곡선 → [[date, value], ...]. 없으면 []. 서빙(비교/겹쳐보기)용."""
    cik = slug_or_cik
    if not str(slug_or_cik).isdigit():
        con_g = sqlite3.connect(_GURU_DB)
        row = con_g.execute("SELECT cik FROM gurus WHERE slug=?", (slug_or_cik,)).fetchone()
        con_g.close()
        if not row:
            return []
        cik = row[0]
    try:
        pc = _price_conn()
        rows = pc.execute(
            "SELECT date, value FROM guru_nav WHERE cik=? ORDER BY date", (cik,)
        ).fetchall()
        pc.close()
        return [[d, v] for d, v in rows]
    except Exception:
        return []
