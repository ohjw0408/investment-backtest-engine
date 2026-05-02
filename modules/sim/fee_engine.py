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


# 증권사별 프리셋
class FeePresets:
    ZERO     = FeeEngine(0, 0, 0)                    # 수수료 없음
    KIS_ETF  = FeeEngine(0.00015, 0.00015, 0.0)      # 한투 ETF
    KIS_KR   = FeeEngine(0.00015, 0.00015, 0.0018)   # 한투 국내주식
    KIWOOM   = FeeEngine(0.00015, 0.00015, 0.0)      # 키움