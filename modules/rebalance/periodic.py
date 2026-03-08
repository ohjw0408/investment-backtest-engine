from modules.rebalance.base_strategy import BaseRebalanceStrategy


class PeriodicRebalance(BaseRebalanceStrategy):

    def __init__(

        self,
        target_weights,
        rebalance_frequency="monthly",
        drift_threshold=None

    ):

        super().__init__(target_weights)

        self.rebalance_frequency = rebalance_frequency
        self.drift_threshold = drift_threshold

        self.last_rebalance = None

    def should_rebalance(

        self,
        date,
        portfolio,
        price_dict

    ):

        # -----------------------------
        # 최초 투자
        # -----------------------------

        if self.last_rebalance is None:

            self.last_rebalance = date
            return True

        # -----------------------------
        # Band rebalance
        # -----------------------------

        if self.drift_threshold is not None:

            current_weights = portfolio.current_weights(
                price_dict,
                include_cash=False
            )

            for ticker, target_weight in self.target_weights.items():

                if ticker == "CASH":
                    continue

                current_weight = current_weights.get(ticker, 0)

                drift = abs(current_weight - target_weight)

                if drift > self.drift_threshold:
                    return True

        # -----------------------------
        # Periodic rebalance
        # -----------------------------

        if self.rebalance_frequency is None:
            return False

        if self.rebalance_frequency == "monthly":

            if date.month != self.last_rebalance.month:

                self.last_rebalance = date
                return True

        elif self.rebalance_frequency == "quarterly":

            if (
                date.month != self.last_rebalance.month
                and date.month % 3 == 1
            ):

                self.last_rebalance = date
                return True

        elif self.rebalance_frequency == "yearly":

            if date.year != self.last_rebalance.year:

                self.last_rebalance = date
                return True

        return False