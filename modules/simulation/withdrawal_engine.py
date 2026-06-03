import math


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
        executor=None,
    ):

        if withdrawal_amount <= 0:
            return last_month

        current_month = (date.year, date.month)

        # ✅ 월 1회만 실행
        if last_month == current_month:
            return last_month

        last_month = current_month

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
        outflow_from_sales = needed  # BUG-WD-1: 매도로 충당할 인출분(루프에서 needed가 차감되므로 보존)

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

            # ✅ ceil로 변경: 부족분 전액 매도 (잔여 현금 방지)
            sell_qty = math.ceil(min(value, needed) / price)

            if sell_qty <= 0:
                continue

            # 보유 수량 초과 방지
            position = portfolio.positions.get(ticker)
            if position is None:
                continue
            sell_qty = min(sell_qty, int(position.quantity))

            if sell_qty <= 0:
                continue

            # BUG-TAX-2: 인출 매도도 위탁 양도세 대상 → 세금 executor 경유(있으면).
            # 세금 OFF이거나 평범한 OrderExecutor면 sell_with_tax 없음 → 직접 매도.
            if executor is not None and hasattr(executor, "sell_with_tax"):
                executor.sell_with_tax(portfolio, ticker, sell_qty, price)
            else:
                portfolio.sell(ticker, sell_qty, price)
            needed -= sell_qty * price

            if needed <= 0:
                break

        # BUG-WD-1: 매도 proceeds를 cash에 주차만 하던 버그 수정 — 인출분을 실제 유출.
        # (기존엔 매도월 자산→cash 이동만 일어나 ~50% 과소인출.) CG세는 sell_with_tax가
        # 별도 차감(retiree net + 정부 세금). 자산 부족 시 0 바닥(생존 실패).
        portfolio.cash = max(0.0, portfolio.cash - outflow_from_sales)

        return last_month