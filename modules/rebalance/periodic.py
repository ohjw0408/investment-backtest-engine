from modules.rebalance.base_strategy import BaseRebalanceStrategy


class PeriodicRebalance(BaseRebalanceStrategy):

    def __init__(

        self,

        target_weights,

        rebalance_frequency="monthly"

    ):

        super().__init__(target_weights)

        self.rebalance_frequency = rebalance_frequency

        self.last_rebalance = None

    # -------------------------------------------------
    # 리밸런싱 여부 판단
    # -------------------------------------------------

    def should_rebalance(

        self,

        date,

        portfolio,

        price_dict

    ):

        if self.last_rebalance is None:

            self.last_rebalance = date

            return True

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