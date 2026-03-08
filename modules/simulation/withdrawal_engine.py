class WithdrawalEngine:

    def process(
        self,
        portfolio,
        withdrawal_amount,
        price_dict,
        target_weights
    ):

        if withdrawal_amount <= 0:
            return

        # -----------------------------
        # cash로 해결 가능
        # -----------------------------

        if portfolio.cash >= withdrawal_amount:

            portfolio.cash -= withdrawal_amount
            return

        needed = withdrawal_amount - portfolio.cash
        portfolio.cash = 0

        # -----------------------------
        # 현재 포트 가치
        # -----------------------------

        total_value = portfolio.total_value(price_dict)

        # -----------------------------
        # overweight 계산
        # -----------------------------

        sell_candidates = []

        current_weights = portfolio.current_weights(price_dict)

        for ticker, position in portfolio.positions.items():

            if ticker not in price_dict:
                continue

            target = target_weights.get(ticker, 0)
            current = current_weights.get(ticker, 0)

            overweight = current - target

            price = price_dict[ticker]
            value = position.market_value(price)

            if value <= 0:
                continue

            sell_candidates.append((ticker, overweight, price, value))

        # -----------------------------
        # overweight 순 정렬
        # -----------------------------

        sell_candidates.sort(key=lambda x: x[1], reverse=True)

        # -----------------------------
        # 매도 실행
        # -----------------------------

        for ticker, overweight, price, value in sell_candidates:

            sell_qty = int(min(value, needed) / price)

            if sell_qty <= 0:
                continue

            portfolio.sell(ticker, sell_qty, price)

            needed -= sell_qty * price

            if needed <= 0:
                break