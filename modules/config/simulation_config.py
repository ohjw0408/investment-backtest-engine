from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set


@dataclass
class SimulationConfig:

    # -----------------------------
    # 기간
    # -----------------------------

    start_date: str
    end_date: str

    # -----------------------------
    # 자산
    # -----------------------------

    tickers: List[str]
    target_weights: Dict[str, float]

    # -----------------------------
    # 자본
    # -----------------------------

    initial_capital: float

    monthly_contribution: float = 0

    contribution_end_months: Optional[int] = None

    withdrawal_amount: float = 0

    # -----------------------------
    # 배당 처리
    # -----------------------------

    dividend_mode: str = "reinvest"
    # options:
    # reinvest
    # cash
    # withdraw

    # -----------------------------
    # 리밸런싱
    # -----------------------------

    rebalance_frequency: str = "monthly"

    # -----------------------------
    # 인플레이션
    # -----------------------------

    inflation: float = 0.0
    # 연간 인플레이션율 (예: 0.02 = 2%)
    # WithdrawalEngine이 매달 인출액을 조정하는 데 사용

    # -----------------------------
    # 거래수수료 (D4, 2026-06-13)
    # -----------------------------

    fee_rate: float = 0.0                          # 통합 매수=매도 수수료율 (0 = opt-out)
    stock_tickers: Optional[Set[str]] = None       # 개별주식(is_etf=0) → 매도 거래세 가산