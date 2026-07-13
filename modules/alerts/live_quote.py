# -*- coding: utf-8 -*-
"""알림용 경량 라이브 시세 (알림 교통정리 2026-07-02).

기존 문제: 알림이 price_daily 일봉만 봤는데 당일봉은 하루 첫 조회 스냅샷으로 박제
(INSERT OR IGNORE + 트레일링 스킵 가드) → 장중 변동 감지 불가. 또한 확정 종가가
밤에 뒤늦게 DB에 들어와 "어제의 등락"으로 엉뚱한 시간(22:30 등)에 발화.

소스:
  지수/선물/FX/금현물 → index_ohlc 최근 2봉 (refresh_index_ohlc beat가 장중 30분마다
                        당일봉 upsert → ≤30분 지연 준라이브. 코스피 커버)
  주식/ETF/크립토     → yfinance 5d 직접 조회 (마지막 봉 = 장중 현재가).
                        프로세스 내 TTL 캐시 10분 — beat 15분 주기라 회당 1콜.

반환: {"cur", "prev", "cur_is_today"} 또는 None — 실패 시 호출측이 일봉 폴백.
cur_is_today: 마지막 봉이 오늘(UTC 날짜) 것인지. 장중 게이팅 하에서는 각 시장의
로컬 날짜 == UTC 날짜(KR 00:00-06:30Z = KST 같은 날, US 13:30-20:00Z = ET 같은 날)라
UTC 날짜 비교로 충분. daily_pct 장중 평가는 cur_is_today=True일 때만 발화시켜
"어제 등락" 오발화를 차단한다.
테스트(FakeLoader)는 index_conn 없음 + yf 미도달 경로로 자연 폴백된다.
"""
import time
from datetime import datetime

_CACHE: dict = {}          # code -> (fetched_ts, data)
_TTL = 600                 # 10분


def is_index_like(code: str) -> bool:
    """index_ohlc 경유 대상 — 지수·금현물만. 환율(=X)·선물(=F)은 24시간 거래라
    장중에만 도는 refresh beat의 index_ohlc가 아니라 yf 직접(상시 신선)으로 간다
    (2026-07-02 자산군 커버 수정)."""
    code = str(code).upper()
    if code.startswith("^") or code == "KRX_GOLD" or "/" in code:
        return True
    from modules.market_alias import INDEX_POINT_CODES   # 000300.SS·TPX.F 등 비^ 지수
    return code in INDEX_POINT_CODES


def _yf_symbol(code: str) -> str:
    """yfinance 심볼 변환 — KR 6자리는 .KS, US 점 티커는 하이픈, USD/KRW 계열은 KRW=X."""
    code = str(code).upper()
    if code == "USD/KRW":
        return "KRW=X"
    if code.isdigit() or (len(code) == 6 and code[:1].isdigit()):
        return f"{code}.KS"
    if "=" in code:                     # KRW=X, GC=F 등은 yf 심볼 그대로
        return code
    if "." in code and not code.endswith((".KS", ".KQ")):
        return code.replace(".", "-")   # BRK.B -> BRK-B
    return code


def _pack(cur, prev, last_date_str):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return {"cur": float(cur), "prev": float(prev),
            "cur_is_today": str(last_date_str)[:10] == today}


def _from_index_ohlc(loader, code: str):
    conn = getattr(loader, "index_conn", None)
    if conn is None:
        return None
    db_code = "USD/KRW" if code == "KRW=X" else code
    try:
        rows = conn.execute(
            "SELECT date, close FROM index_ohlc WHERE code=? AND close IS NOT NULL ORDER BY date DESC LIMIT 2",
            (code,)).fetchall()
    except Exception:
        rows = []
    if len(rows) < 2:
        try:
            rows = conn.execute(
                "SELECT date, close FROM index_daily WHERE code=? AND close IS NOT NULL ORDER BY date DESC LIMIT 2",
                (db_code,)).fetchall()
        except Exception:
            return None
    if len(rows) < 2 or rows[0][1] is None or rows[1][1] is None:
        return None
    return _pack(rows[0][1], rows[1][1], rows[0][0])


def _from_yf(code: str):
    try:
        import yfinance as yf
        hist = yf.Ticker(_yf_symbol(code)).history(period="5d")
        closes = hist["Close"].dropna() if hist is not None and not hist.empty else None
        if closes is None or len(closes) < 2:
            return None
        last_date = closes.index[-1]
        d = last_date.strftime("%Y-%m-%d") if hasattr(last_date, "strftime") else str(last_date)
        return _pack(closes.iloc[-1], closes.iloc[-2], d)
    except Exception:
        return None


def get_live_price(loader, code: str):
    """{"cur","prev","cur_is_today"} 또는 None. 프로세스 내 10분 캐시."""
    code = str(code).upper()
    hit = _CACHE.get(code)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    data = _from_index_ohlc(loader, code) if is_index_like(code) else _from_yf(code)
    if data is not None:
        _CACHE[code] = (time.time(), data)
    return data
