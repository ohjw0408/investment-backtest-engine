from dataclasses import dataclass
from typing import List, Dict


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