from typing import Dict
from modules.rebalance.base_strategy import BaseRebalanceStrategy
from modules.core.portfolio import Portfolio


class PeriodicRebalance(BaseRebalanceStrategy):
    """
    단순 목표 비중 리밸런싱
    """

    def generate_orders(
        self,
        portfolio: Portfolio,
        price_dict: Dict[str, float],
    ) -> Dict[str, float]:

        orders = {}

        total_value = portfolio.total_value(price_dict)

        if total_value == 0:
            return orders

        # 현재 비중
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
