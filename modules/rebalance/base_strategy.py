from typing import Dict
from modules.core.portfolio import Portfolio


class BaseRebalanceStrategy:

    def __init__(self, target_weights: Dict[str, float]):

        self.target_weights = target_weights

    def generate_orders(

        self,

        portfolio: Portfolio,

        price_dict: Dict[str, float],

    ) -> Dict[str, float]:

        orders = {}

        total_value = portfolio.total_value(price_dict)

        if total_value == 0:
            return orders

        # -----------------------------
        # CASH target 존재 여부
        # -----------------------------

        include_cash = "CASH" in self.target_weights

        current_weights = portfolio.current_weights(

            price_dict,

            include_cash=include_cash
        )

        for ticker, target_weight in self.target_weights.items():

            if ticker == "CASH":
                continue

            current_weight = current_weights.get(ticker, 0.0)

            weight_diff = target_weight - current_weight

            target_value_diff = weight_diff * total_value

            orders[ticker] = target_value_diff

        return orders