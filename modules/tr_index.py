"""포트폴리오 총수익(배당 재투자) 인덱스 빌더 — Flask-free 공용 모듈.

app.py `_ticker_series`/`_portfolio_index_series`의 검증된 코어를 워커(celery)·분석탭
롤링에서 재사용하기 위해 추출. 캐시/다운샘플/ensure_full_history 같은 웹 전용 래퍼는 빼고
순수 DB+pandas 산출만 담는다(결과는 app.py 오버레이와 동일 규격: 시작=100, [date,val,syn]).

⚠️ 불변식(깨면 가짜 점프 버그 재발):
  - `pct_change(fill_method=None)` — 기본 'pad'는 price_daily 내부 NULL홀을 forward-fill →
    구멍 닫히는 날 +수십~수백% 가짜수익 → 포폴 지수 점프(2021-06-25 버핏 버그).
  - close·dividend는 이미 분할조정(연속)이라 split 곱 금지(SCHD 2024 3:1 가짜 점프).
    배당만 재투자.
"""
from __future__ import annotations


def _conn():
    import sqlite3
    from modules.price_loader import DB_PATH
    return sqlite3.connect(str(DB_PATH))


def ticker_tr_series(conn, code, start='1900-01-01'):
    """종목별 총수익(배당 재투자) 인덱스 → (tr_map{date:value}, syn_map{date:0|1}).
       syn=1: 그 날 합성 백필(volume=0)."""
    import pandas as pd
    from modules.price_loader import _drop_isolated_price_spikes
    c = code.rsplit('.', 1)[0] if code.endswith(('.KS', '.KQ')) else code
    m, syn = {}, {}
    try:
        rows = conn.execute(
            "SELECT date, close, volume FROM price_daily WHERE code=? AND date>=? ORDER BY date",
            (c, start)).fetchall()
        if rows:
            dfx = _drop_isolated_price_spikes(pd.DataFrame(rows, columns=['date', 'close', 'volume']))
            act = conn.execute(
                "SELECT date, dividend FROM corporate_actions WHERE code=? AND date>=?",
                (c, start)).fetchall()
            divm = {a[0]: (float(a[1]) if a[1] else 0.0) for a in act}
            prev_close = None
            tr = None
            for r in dfx.itertuples():
                if not (r.close and float(r.close) > 0):
                    continue
                close = float(r.close)
                dv = divm.get(r.date, 0.0) or 0.0
                if prev_close is None:
                    tr = close
                else:
                    tr = tr * (close + dv) / prev_close   # 배당 재투자
                m[r.date] = tr
                syn[r.date] = 1 if (r.volume is None or float(r.volume) == 0) else 0
                prev_close = close
    except Exception:
        pass
    return m, syn


def build_portfolio_tr_index(tickers, conn=None, start='1900-01-01'):
    """포트폴리오(비중 고정) 총수익 정규화 지수(시작=100) 일별 시계열.
       반환 = [[date, value, syn], ...]. start=가용 전체기간(기본).
       빈 입력/데이터 없으면 []."""
    import pandas as pd
    wsum = sum(float(t.get('weight') or 0) for t in tickers) or 1.0
    valid = []
    for t in tickers:
        code = str(t.get('code') or '').upper()
        w = float(t.get('weight') or 0) / wsum
        if w > 0 and code:
            valid.append((code, w))
    if not valid:
        return []

    own = conn is None
    if own:
        conn = _conn()
    series = {}
    try:
        for code, w in valid:
            m, syn = ticker_tr_series(conn, code, start)
            if m:
                series[code] = (w, m, syn)
    finally:
        if own:
            conn.close()
    if not series:
        return []

    closes = pd.DataFrame({c: pd.Series(m) for c, (w, m, syn) in series.items()}).sort_index()
    if len(closes.index) < 2:
        return []
    weights = pd.Series({c: w for c, (w, m, syn) in series.items()}, dtype=float)
    # fill_method=None 필수(불변식 — 모듈 docstring 참고).
    rets = closes.pct_change(fill_method=None)
    wrow = rets.notna().mul(weights, axis=1)
    port_ret = rets.mul(weights, axis=1).sum(axis=1).div(wrow.sum(axis=1).replace(0.0, pd.NA)).fillna(0.0)
    idx = (1.0 + port_ret).cumprod() * 100.0
    syn_df = pd.DataFrame({c: pd.Series(syn) for c, (w, m, syn) in series.items()}).reindex(closes.index)
    present = closes.notna()
    any_syn = (syn_df.fillna(0).astype(bool) & present).any(axis=1)
    partial = present.sum(axis=1) < len(series)
    synflag = (any_syn | partial)
    return [[d, round(float(v), 4), int(bool(s))]
            for d, v, s in zip(closes.index, idx.values, synflag.values)]
