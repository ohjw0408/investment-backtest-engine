class SimulationLoop:

    def __init__(
        self,
        dividend_engine,
        contribution_engine,
        withdrawal_engine,
        executor,
        cash_allocator,
    ):

        self.dividend_engine     = dividend_engine
        self.contribution_engine = contribution_engine
        self.withdrawal_engine   = withdrawal_engine
        self.executor            = executor
        self.cash_allocator      = cash_allocator

    def run(
        self,
        portfolio,
        strategy,
        config,
        price_data,
        dates,
        recorder,
        record_history=True   # 🔥 추가
    ):

        last_month             = None
        last_withdrawal_month  = (dates[0].year, dates[0].month) if dates else None
        elapsed_months         = 0
        last_inflation_month   = None
        is_first_day           = True
        self._last_cf_month    = None
        self._initial_capital_cf = 0.0

        # 🔥 1️⃣ price numpy 캐싱 (핵심 최적화)
        price_array = {}
        valid_index = {}

        for ticker in config.tickers:
            df = price_data[ticker]
            price_array[ticker] = df["close"].values
            valid_index[ticker] = df.index

        # 🔥 메인 루프
        for i, date in enumerate(dates):

            price_dict = {}

            # 🔥 2️⃣ pandas loc → numpy 접근
            for ticker in config.tickers:

                if date not in valid_index[ticker]:
                    continue

                price = price_array[ticker][i]
                price_dict[ticker] = price

            if not price_dict:
                continue

            # ── 인플레이션 월 계산 ─────────────────────
            current_month = (date.year, date.month)
            if last_inflation_month is None:
                last_inflation_month = current_month
            elif current_month != last_inflation_month:
                elapsed_months += 1
                last_inflation_month = current_month

            # ── 첫날 초기 매수 ─────────────────────────
            if is_first_day:
                is_first_day = False
                self._initial_capital_cf = getattr(config, "initial_capital", 0.0)

                cash_target = config.target_weights.get("CASH", 0)
                if cash_target == 0 and portfolio.cash > 0:
                    self.cash_allocator.allocate_cash(
                        portfolio,
                        price_dict,
                        config.target_weights
                    )

            # ── dividend ─────────────────────────────
            dividend_by_ticker = self.dividend_engine.process(
                portfolio,
                price_data,
                price_dict,
                date,
                config.dividend_mode
            )

            dividend_total = sum(dividend_by_ticker.values())
            if config.dividend_mode == "withdraw" and dividend_total > 0:
                portfolio.cash -= dividend_total

            # ── contribution ─────────────────────────
            last_month = self.contribution_engine.process(
                portfolio,
                config.monthly_contribution,
                date,
                last_month
            )

            # ── contribution sweep ───────────────────
            if config.monthly_contribution > 0:
                cash_target = config.target_weights.get("CASH", 0)
                if cash_target == 0:
                    self.cash_allocator.allocate_cash(
                        portfolio,
                        price_dict,
                        config.target_weights
                    )

            # ── withdrawal ───────────────────────────
            inflation = getattr(config, "inflation", 0.0)

            last_withdrawal_month = self.withdrawal_engine.process(
                portfolio,
                config.withdrawal_amount,
                price_dict,
                config.target_weights,
                date=date,
                last_month=last_withdrawal_month,
                elapsed_months=elapsed_months,
                inflation=inflation,
            )

            # ── rebalance ────────────────────────────
            if strategy.should_rebalance(date, portfolio, price_dict):
                orders = strategy.generate_orders(portfolio, price_dict)
                self.executor.execute_orders(portfolio, orders, price_dict)

            # ── dividend sweep ───────────────────────
            if config.dividend_mode in ("reinvest", "withdraw") and config.withdrawal_amount == 0:
                cash_target = config.target_weights.get("CASH", 0)
                if cash_target == 0:
                    self.cash_allocator.allocate_cash(
                        portfolio,
                        price_dict,
                        config.target_weights
                    )

            # ── cash flow 기록 ───────────────────────
            current_month_key = (date.year, date.month)

            if current_month_key != getattr(self, "_last_cf_month", None):
                self._last_cf_month = current_month_key

                cash_flow = config.monthly_contribution - config.withdrawal_amount

                initial_cf = getattr(self, "_initial_capital_cf", 0.0)
                if initial_cf > 0:
                    cash_flow += initial_cf
                    self._initial_capital_cf = 0.0
            else:
                cash_flow = 0.0

            # 🔥 3️⃣ recorder 옵션화
            if record_history:
                recorder.record(
                    date,
                    portfolio,
                    price_dict,
                    config.tickers,
                    dividend_by_ticker,
                    cash_flow=cash_flow,
                )