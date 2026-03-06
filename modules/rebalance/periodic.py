from typing import Dict
from modules.rebalance.base_strategy import BaseRebalanceStrategy
from modules.core.portfolio import Portfolio


class PeriodicRebalance(BaseRebalanceStrategy):

    """
    리밸런싱 전략

    지원 기능
    - 월간 리밸런싱
    - 분기 리밸런싱
    - 연간 리밸런싱
    - 드리프트 리밸런싱
    - Buy & Hold (rebalance_frequency="never")
    """

    def __init__(
        self,
        target_weights: Dict[str, float],
        rebalance_frequency: str = "monthly",
        drift_threshold: float | None = None,
        include_cash: bool = False,
    ):

        super().__init__(target_weights, include_cash)

        self.rebalance_frequency = rebalance_frequency
        self.drift_threshold = drift_threshold

        self.last_rebalance = None

    # -------------------------------------------------
    # 리밸런싱 여부 판단
    # -------------------------------------------------

    def should_rebalance(self, date, portfolio: Portfolio, price_dict):

        # 첫 날은 항상 리밸런싱 (초기 매수)
        if self.last_rebalance is None:
            self.last_rebalance = date
            return True

        # Buy & Hold 모드
        if self.rebalance_frequency == "never":
            return False

        # -----------------------------
        # 주기 기반 리밸런싱
        # -----------------------------

        if self.rebalance_frequency == "monthly":
            if date.month != self.last_rebalance.month:
                self.last_rebalance = date
                return True

        elif self.rebalance_frequency == "quarterly":
            current_q = (date.month - 1) // 3
            last_q = (self.last_rebalance.month - 1) // 3

            if current_q != last_q:
                self.last_rebalance = date
                return True

        elif self.rebalance_frequency == "yearly":
            if date.year != self.last_rebalance.year:
                self.last_rebalance = date
                return True

        # -----------------------------
        # 드리프트 리밸런싱
        # -----------------------------

        if self.drift_threshold is not None:

            total_value = portfolio.total_value(price_dict)

            if total_value == 0:
                return False

            current_weights = portfolio.current_weights(
                price_dict,
                include_cash=self.include_cash
            )

            for ticker, target_weight in self.target_weights.items():

                if ticker == "CASH":
                    continue

                current_weight = current_weights.get(ticker, 0.0)

                if abs(current_weight - target_weight) > self.drift_threshold:
                    self.last_rebalance = date
                    return True

        return False

    # -------------------------------------------------
    # 주문 생성
    # -------------------------------------------------

    def generate_orders(
        self,
        portfolio: Portfolio,
        price_dict: Dict[str, float],
    ) -> Dict[str, float]:

        orders = {}

        total_value = portfolio.total_value(price_dict)

        if total_value == 0:
            return orders

        current_weights = portfolio.current_weights(
            price_dict,
            include_cash=self.include_cash
        )

        for ticker, target_weight in self.target_weights.items():

            if ticker == "CASH":
                continue

            current_weight = current_weights.get(ticker, 0.0)

            weight_diff = target_weight - current_weight

            target_value_diff = weight_diff * total_value

            orders[ticker] = target_value_diff

        return orders