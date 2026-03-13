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
        recorder
    ):

        last_month             = None
        # 첫 달을 시작 월로 초기화 → 첫날 인출 방지, 두 번째 달부터 인출
        last_withdrawal_month  = dates[0].month if dates else None
        elapsed_months         = 0
        last_inflation_month   = None
        is_first_day           = True

        for date in dates:

            price_dict = {}

            for ticker in config.tickers:

                if date not in price_data[ticker].index:
                    continue

                price = price_data[ticker].loc[date, "close"]
                price_dict[ticker] = price

            if not price_dict:
                continue

            # ── 인플레이션 경과 월수 추적 ─────────────────────
            current_month = (date.year, date.month)
            if last_inflation_month is None:
                last_inflation_month = current_month
            elif current_month != last_inflation_month:
                elapsed_months      += 1
                last_inflation_month = current_month

            # ── 첫날: 초기 현금을 주식으로 매수 ──────────────
            if is_first_day:
                is_first_day = False
                cash_target  = config.target_weights.get("CASH", 0)
                if cash_target == 0 and portfolio.cash > 0:
                    self.cash_allocator.allocate_cash(
                        portfolio,
                        price_dict,
                        config.target_weights
                    )

            # ── dividend ──────────────────────────────────────
            dividend_by_ticker = self.dividend_engine.process(
                portfolio,
                price_data,
                price_dict,
                date,
                config.dividend_mode
            )

            # ── contribution (월 1회) ─────────────────────────
            last_month = self.contribution_engine.process(
                portfolio,
                config.monthly_contribution,
                date,
                last_month
            )

            # ── contribution cash sweep ───────────────────────
            if config.monthly_contribution > 0:
                cash_target = config.target_weights.get("CASH", 0)
                if cash_target == 0:
                    self.cash_allocator.allocate_cash(
                        portfolio,
                        price_dict,
                        config.target_weights
                    )

            # ── withdrawal (월 1회 + 인플레이션 반영) ──────────
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

            # ── rebalance ─────────────────────────────────────
            if strategy.should_rebalance(date, portfolio, price_dict):
                orders = strategy.generate_orders(portfolio, price_dict)
                self.executor.execute_orders(portfolio, orders, price_dict)

            # ── dividend reinvest cash sweep ──────────────────
            # withdrawal 모드가 아닐 때만 배당 재투자
            if config.dividend_mode == "reinvest" and config.withdrawal_amount == 0:
                cash_target = config.target_weights.get("CASH", 0)
                if cash_target == 0:
                    self.cash_allocator.allocate_cash(
                        portfolio,
                        price_dict,
                        config.target_weights
                    )

            # ── 현금흐름 기록 (TWR/MWR 계산용) ──────────────
            # 납입은 양수, 인출은 음수, 월 1회만 기록
            current_month_key = (date.year, date.month)
            if current_month_key != getattr(self, "_last_cf_month", None):
                self._last_cf_month = current_month_key
                cash_flow = config.monthly_contribution - config.withdrawal_amount
            else:
                cash_flow = 0.0

            recorder.record(
                date,
                portfolio,
                price_dict,
                config.tickers,
                dividend_by_ticker,
                cash_flow=cash_flow,
            )