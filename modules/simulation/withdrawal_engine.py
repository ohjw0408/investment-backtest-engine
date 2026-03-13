class WithdrawalEngine:

    def process(
        self,
        portfolio,
        withdrawal_amount,
        price_dict,
        target_weights,
        date,
        last_month,
        elapsed_months: int = 0,
        inflation: float = 0.0,
    ):
        """
        월 1회만 인출 실행 (ContributionEngine과 동일 패턴).

        Parameters
        ----------
        date           : 현재 날짜
        last_month     : 직전 인출 월 (중복 방지)
        elapsed_months : 시뮬 시작 시점으로부터 경과한 월수 (인플레이션용)
        inflation      : 연간 인플레이션율 (예: 0.02 = 2%)
        """

        if withdrawal_amount <= 0:
            return last_month

        # ✅ 월 1회만 실행
        if last_month == date.month:
            return last_month

        last_month = date.month

        # ✅ 인플레이션 반영
        if inflation > 0 and elapsed_months > 0:
            withdrawal_amount *= (1 + inflation / 12) ** elapsed_months

        # -----------------------------
        # cash로 해결 가능
        # -----------------------------

        if portfolio.cash >= withdrawal_amount:
            portfolio.cash -= withdrawal_amount
            return last_month

        needed = withdrawal_amount - portfolio.cash
        portfolio.cash = 0

        # -----------------------------
        # overweight 순으로 매도
        # -----------------------------

        current_weights = portfolio.current_weights(price_dict)

        sell_candidates = []

        for ticker, position in portfolio.positions.items():

            if ticker not in price_dict:
                continue

            target     = target_weights.get(ticker, 0)
            current    = current_weights.get(ticker, 0)
            overweight = current - target
            price      = price_dict[ticker]
            value      = position.market_value(price)

            if value <= 0:
                continue

            sell_candidates.append((ticker, overweight, price, value))

        sell_candidates.sort(key=lambda x: x[1], reverse=True)

        for ticker, overweight, price, value in sell_candidates:

            sell_qty = int(min(value, needed) / price)

            if sell_qty <= 0:
                continue

            portfolio.sell(ticker, sell_qty, price)
            needed -= sell_qty * price

            if needed <= 0:
                break

        return last_month