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
        record_history=True,
        progress_callback=None,
        carried_cost_basis=None,
    ):
        import time as _time

        last_month             = None
        last_withdrawal_month  = (dates[0].year, dates[0].month) if dates else None
        elapsed_months         = 0
        last_inflation_month   = None
        is_first_day           = True
        self._last_cf_month    = None
        self._initial_capital_cf = 0.0

        # 🔥 1️⃣ price numpy 캐싱 (핵심 최적화)
        price_array = {}

        for ticker in config.tickers:
            df = price_data[ticker]
            price_array[ticker] = df["close"].values

        total_dates = len(dates)
        update_step = max(1, total_dates // 20)
        _start_time = _time.time() if progress_callback else None

        # 🔥 메인 루프
        for i, date in enumerate(dates):

            price_dict = {}

            # 🔥 2️⃣ pandas loc → numpy 접근
            # 모든 종목이 union 인덱스로 reindex돼 있어 dates의 모든 i가 유효(과거 멤버십
            # 테스트 `date in df.index`는 항상 True인 死코드 → 제거, 결과 불변·per-day×종목 비용 절감).
            for ticker in config.tickers:
                price_dict[ticker] = price_array[ticker][i]

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

                # ── 적립 취득가 인계 (은퇴 인출 G5-C) ──────────────
                # day-1 매수 직후 avg_cost는 인출시작가. 인출은 적립 종료자산(gross)을
                # initial_capital로 받으므로 적립차익이 취득가에 안 잡힘 → 위탁 인출 매도가
                # 그 차익을 과세 못 함(BUG-TAX-3 위탁 잔여). carried_cost_basis(=적립 총납입)로
                # avg_cost를 비례 축소 → 첫 매도부터 (현재가−적립취득가) 차익 과세.
                # 위탁만 영향(ISA/연금은 sell_with_tax가 과세이연 → CG 0이라 무해).
                if carried_cost_basis and hasattr(portfolio, "_avg_costs") and portfolio._avg_costs:
                    invested = sum(
                        portfolio._avg_costs[t] * portfolio.positions[t].quantity
                        for t in portfolio._avg_costs
                        if t in portfolio.positions and portfolio.positions[t].quantity > 0
                    )
                    if invested > 0:
                        scale = carried_cost_basis / invested
                        for t in list(portfolio._avg_costs.keys()):
                            portfolio._avg_costs[t] *= scale

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
            _effective_monthly = (
                0.0
                if (getattr(config, 'contribution_end_months', None) is not None
                    and elapsed_months >= config.contribution_end_months)
                else config.monthly_contribution
            )
            last_month = self.contribution_engine.process(
                portfolio,
                _effective_monthly,
                date,
                last_month
            )

            # ── contribution sweep ───────────────────
            if _effective_monthly > 0:
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
                executor=self.executor,
            )

            # ── rebalance ────────────────────────────
            if strategy.should_rebalance(date, portfolio, price_dict):
                orders = strategy.generate_orders(portfolio, price_dict)
                self.executor.execute_orders(portfolio, orders, price_dict, date=date)

            # ── 12월 절세매도 (rebal_mode: none 포함, 중복 방지는 executor 내부에서) ──
            if hasattr(self.executor, "maybe_gain_harvest"):
                self.executor.maybe_gain_harvest(portfolio, price_dict, date)

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

            if progress_callback and i % update_step == 0:
                elapsed = _time.time() - _start_time
                progress_callback(current=i + 1, total=total_dates, elapsed=elapsed)