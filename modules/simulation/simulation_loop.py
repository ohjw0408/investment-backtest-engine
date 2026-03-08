class SimulationLoop:

    def __init__(
        self,
        dividend_engine,
        contribution_engine,
        withdrawal_engine,
        executor,
        cash_allocator,
    ):

        self.dividend_engine = dividend_engine
        self.contribution_engine = contribution_engine
        self.withdrawal_engine = withdrawal_engine
        self.executor = executor
        self.cash_allocator = cash_allocator

    def run(
        self,
        portfolio,
        strategy,
        config,
        price_data,
        dates,
        recorder
    ):

        last_month = None

        for date in dates:

            price_dict = {}

            for ticker in config.tickers:

                if date not in price_data[ticker].index:
                    continue

                price = price_data[ticker].loc[date, "close"]
                price_dict[ticker] = price

            if not price_dict:
                continue

            # dividend
            daily_dividend = self.dividend_engine.process(
                portfolio,
                price_data,
                price_dict,
                date,
                config.dividend_mode
            )

            # contribution
            last_month = self.contribution_engine.process(
                portfolio,
                config.monthly_contribution,
                date,
                last_month
            )

            # withdrawal
            self.withdrawal_engine.process(
                portfolio,
                config.withdrawal_amount,
                price_dict,
                config.target_weights
            )

            # rebalance
            if strategy.should_rebalance(
                date,
                portfolio,
                price_dict
            ):

                orders = strategy.generate_orders(
                    portfolio,
                    price_dict
                )

                self.executor.execute_orders(
                    portfolio,
                    orders,
                    price_dict
                )

            # cash sweep
            cash_target = config.target_weights.get("CASH", 0)

            if cash_target == 0 and config.dividend_mode in ["reinvest", "withdraw"]:

                self.cash_allocator.allocate_cash(
                    portfolio,
                    price_dict,
                    config.target_weights
                )

            recorder.record(
                date,
                portfolio,
                price_dict,
                config.tickers,
                daily_dividend
            )