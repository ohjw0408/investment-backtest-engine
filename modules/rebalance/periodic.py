from typing import Dict
from modules.rebalance.base_strategy import BaseRebalanceStrategy
from modules.core.portfolio import Portfolio


class PeriodicRebalance(BaseRebalanceStrategy):
    """
    단순 목표 비중 리밸런싱
    """

    def __init__(self, target_weights: Dict[str, float], include_cash: bool = True):
        super().__init__(target_weights, include_cash)
        self.last_rebalance = None

    # -------------------------------------------------
    # 리밸런싱 여부 판단
    # -------------------------------------------------
    def should_rebalance(self, date):

        # 첫 날은 항상 리밸런싱
        if self.last_rebalance is None:
            self.last_rebalance = date
            return True

        # 예시: 월 단위 리밸런싱
        if date.month != self.last_rebalance.month:
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