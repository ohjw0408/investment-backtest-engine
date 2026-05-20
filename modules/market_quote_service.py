"""
market_quote_service.py
────────────────────────────────────────────────────────
실시간 시장 지수 조회 서비스.

DataEngine(백테스팅 전용)과 분리. yfinance에서 직접 조회하고
Redis(db=1)에 TTL 캐시를 둬서 만료 전까지 재조회 없음.
사용자 요청이 없으면 yfinance 호출 없음 (no proactive refresh).
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import redis
import yfinance as yf

TTL_SECONDS = 4 * 3600  # 기본 4시간 (장외 시간)

YF_TICKERS = [
    {"id": "sp500",  "name": "S&P 500",      "tag": "S&P",    "ticker": "^GSPC", "prefix": "",  "fmt": "int"},
    {"id": "nasdaq", "name": "NASDAQ",         "tag": "NASDAQ", "ticker": "^IXIC", "prefix": "",  "fmt": "int"},
    {"id": "kospi",  "name": "코스피 (KOSPI)", "tag": "KOSPI",  "ticker": "^KS11", "prefix": "",  "fmt": "int"},
    {"id": "gold",   "name": "금 (국제)",      "tag": "USD/oz", "ticker": "GC=F",  "prefix": "$", "fmt": "float"},
    {"id": "usdkrw", "name": "환율",           "tag": "USD/KRW","ticker": "KRW=X", "prefix": "₩", "fmt": "float"},
]

DISPLAY_ORDER = ["sp500", "nasdaq", "kospi", "gold", "krx_gold", "usdkrw"]


class MarketQuoteService:

    def __init__(self, index_db_path=None, redis_host="localhost", redis_port=6379):
        self._index_db_path = Path(index_db_path) if index_db_path else None
        try:
            self._redis = redis.Redis(
                host=redis_host, port=redis_port,
                db=1,                     # Celery는 db=0 사용
                decode_responses=True,
                socket_connect_timeout=2,
            )
            self._redis.ping()
            self._redis_ok = True
        except Exception as e:
            print(f"[MarketQuoteService] Redis 연결 실패, 캐시 비활성화: {e}")
            self._redis = None
            self._redis_ok = False

    # ── Smart TTL ────────────────────────────────────────

    @staticmethod
    def _get_ttl() -> int:
        """미국 정규장 (UTC 13:30~20:00, 월~금) → 15분, 나머지 → 4시간."""
        now = datetime.utcnow()
        if now.weekday() >= 5:  # 토,일
            return TTL_SECONDS
        now_min = now.hour * 60 + now.minute
        if 13 * 60 + 30 <= now_min <= 20 * 60:
            return 15 * 60
        return TTL_SECONDS

    # ── 캐시 helpers ─────────────────────────────────────

    def _get(self, key: str):
        if not self._redis_ok:
            return None
        try:
            raw = self._redis.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def _set(self, key: str, data: dict, ttl: int = TTL_SECONDS):
        if not self._redis_ok:
            return
        try:
            self._redis.setex(key, ttl, json.dumps(data, ensure_ascii=False))
        except Exception:
            pass

    # ── yfinance 단일 티커 조회 ───────────────────────────

    def _fetch_yf(self, info: dict):
        hist = yf.Ticker(info["ticker"]).history(period="1mo")
        if hist.empty or len(hist) < 2:
            return None
        closes  = hist["Close"]
        current = float(closes.iloc[-1])
        prev    = float(closes.iloc[-2])
        change  = round((current - prev) / prev * 100, 2)
        spark   = [round(float(v), 2) for v in closes.iloc[-20:].tolist()]
        value_str = (
            f"{info['prefix']}{current:,.0f}"
            if info["fmt"] == "int"
            else f"{info['prefix']}{current:,.2f}"
        )
        return {
            "id":         info["id"],
            "name":       info["name"],
            "tag":        info["tag"],
            "value":      value_str,
            "change":     f"{'+' if change >= 0 else ''}{change}%",
            "up":         change >= 0,
            "spark":      spark,
            "fetched_at": datetime.utcnow().isoformat(),
        }

    # ── KRX 금현물 조회 ───────────────────────────────────

    def _fetch_krx_gold(self):
        if not self._index_db_path or not self._index_db_path.exists():
            return None
        try:
            conn = sqlite3.connect(str(self._index_db_path))
            rows = conn.execute(
                "SELECT date, close FROM index_daily "
                "WHERE code='KRX_GOLD' ORDER BY date DESC LIMIT 2"
            ).fetchall()
            conn.close()

            if not rows:
                return self._try_krx_api()

            last_date = datetime.strptime(rows[0][0], "%Y-%m-%d").date()
            stale     = (datetime.now().date() - last_date).days > 5

            if stale:
                fresh = self._try_krx_api()
                if fresh:
                    return fresh

            if len(rows) < 2:
                return None

            cur_price  = float(rows[0][1])
            prev_price = float(rows[1][1])
            change     = round((cur_price - prev_price) / prev_price * 100, 2)

            conn2 = sqlite3.connect(str(self._index_db_path))
            spark_rows = conn2.execute(
                "SELECT close FROM index_daily "
                "WHERE code='KRX_GOLD' ORDER BY date DESC LIMIT 20"
            ).fetchall()
            conn2.close()
            spark = [round(float(r[0]), 0) for r in reversed(spark_rows)]

            return {
                "id":     "krx_gold",
                "name":   "금 (KRX 현물)",
                "tag":    "원/g",
                "value":  f"₩{cur_price:,.0f}",
                "change": f"{'+' if change >= 0 else ''}{change}%",
                "up":     change >= 0,
                "spark":  spark,
                "note":   rows[0][0],
            }
        except Exception as e:
            print(f"[MarketQuoteService] KRX_GOLD 오류: {e}")
            return None

    def _try_krx_api(self):
        try:
            from modules.krx.krx_client import KRXClient
            df = KRXClient().get_gold_price()
            if not df.empty and float(df.iloc[0]["close"]) > 0:
                p = float(df.iloc[0]["close"])
                return {
                    "id":     "krx_gold",
                    "name":   "금 (KRX 현물)",
                    "tag":    "원/g",
                    "value":  f"₩{p:,.0f}",
                    "change": "—",
                    "up":     True,
                    "spark":  [],
                }
        except Exception as e:
            print(f"[MarketQuoteService] KRX API 오류: {e}")
        return None

    # ── 퍼블릭 API ───────────────────────────────────────

    def get_quote(self, ticker_id: str) -> dict | None:
        """단일 티커 조회 (캐시 우선)."""
        cached = self._get(f"mq:{ticker_id}")
        if cached:
            return cached

        # yfinance 티커 찾기
        info = next((t for t in YF_TICKERS if t["id"] == ticker_id), None)
        if info:
            try:
                data = self._fetch_yf(info)
                if data:
                    self._set(f"mq:{ticker_id}", data)
                    return data
            except Exception as e:
                print(f"[MarketQuoteService] {ticker_id} fetch 오류: {e}")

        if ticker_id == "krx_gold":
            data = self._fetch_krx_gold()
            if data:
                self._set("mq:krx_gold", data, self._get_ttl())
            return data

        return None

    def get_all(self) -> list[dict]:
        """전체 시장 지수 반환. 표시 순서 보장."""
        result_map = {}

        for info in YF_TICKERS:
            key    = f"mq:{info['id']}"
            cached = self._get(key)
            if cached:
                result_map[info["id"]] = cached
                continue
            try:
                data = self._fetch_yf(info)
                if data:
                    self._set(key, data, self._get_ttl())
                    result_map[info["id"]] = data
            except Exception as e:
                print(f"[MarketQuoteService] {info['id']} 오류: {e}")

        # KRX 금현물
        krx = self._get("mq:krx_gold")
        if not krx:
            krx = self._fetch_krx_gold()
            if krx:
                self._set("mq:krx_gold", krx, self._get_ttl())
        if krx:
            result_map["krx_gold"] = krx

        return [result_map[id_] for id_ in DISPLAY_ORDER if id_ in result_map]
