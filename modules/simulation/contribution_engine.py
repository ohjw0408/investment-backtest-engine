class ContributionEngine:

    def process(
        self,
        portfolio,
        monthly_contribution,
        date,
        last_month
    ):

        if monthly_contribution <= 0:
            return last_month

        if last_month != date.month:

            portfolio.cash += monthly_contribution
            last_month = date.month

        return last_month