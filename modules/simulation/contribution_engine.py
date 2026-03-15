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

        current_month = (date.year, date.month)

        if last_month != current_month:
            portfolio.cash += monthly_contribution
            last_month = current_month

        return last_month