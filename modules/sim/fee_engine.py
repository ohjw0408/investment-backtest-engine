"""
fee_engine.py
거래 수수료 계산 엔진
"""
from __future__ import annotations


class FeeEngine:
    """
    거래 수수료 계산

    사용법:
        engine = FeeEngine(buy_rate=0.00015, sell_rate=0.00015)
        fee = engine.calc_buy_fee(amount)
    """

    def __init__(
        self,
        buy_rate:  float = 0.00015,   # 매수 수수료율 (기본 0.015%)
        sell_rate: float = 0.00015,   # 매도 수수료율 (기본 0.015%)
        tax_rate:  float = 0.0,       # 거래세 (국내 주식 0.18%, ETF 0%)
        min_fee:   float = 0.0,       # 최소 수수료
    ):
        self.buy_rate  = buy_rate
        self.sell_rate = sell_rate
        self.tax_rate  = tax_rate
        self.min_fee   = min_fee

    def calc_buy_fee(self, amount: float) -> float:
        return max(self.min_fee, amount * self.buy_rate)

    def calc_sell_fee(self, amount: float) -> float:
        return max(self.min_fee, amount * (self.sell_rate + self.tax_rate))

    def calc_monthly_fee(self, monthly: float) -> float:
        """월 적립 매수 수수료"""
        return self.calc_buy_fee(monthly)


def build_stock_tickers(codes) -> set:
    """국내 개별주식(is_etf=0, country=KR) 코드 집합 — 매도 거래세 0.18% 대상(D4).

    ETF·미국종목은 제외(증권거래세 비대상). symbol_master.db 조회, 실패 시 빈 set(무가산).
    """
    codes = [c for c in (codes or []) if c]
    if not codes:
        return set()
    import sqlite3
    try:
        from config import SYMBOL_DB_PATH
    except Exception:
        return set()
    try:
        conn = sqlite3.connect(SYMBOL_DB_PATH)
        qs = ",".join("?" * len(codes))
        rows = conn.execute(
            f"SELECT code FROM symbols WHERE is_etf=0 AND country='KR' AND code IN ({qs})",
            list(codes),
        ).fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception:
        return set()


# 증권사별 프리셋
class FeePresets:
    ZERO     = FeeEngine(0, 0, 0)                    # 수수료 없음
    KIS_ETF  = FeeEngine(0.00015, 0.00015, 0.0)      # 한투 ETF
    KIS_KR   = FeeEngine(0.00015, 0.00015, 0.0018)   # 한투 국내주식
    KIWOOM   = FeeEngine(0.00015, 0.00015, 0.0)      # 키움