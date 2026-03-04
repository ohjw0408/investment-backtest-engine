from typing import Dict
from modules.core.portfolio import Portfolio


class OrderExecutor:
    """
    주문 실행 엔진
    value 기반 주문을 실제 거래로 변환
    """

    def execute_orders(
        self,
        portfolio: Portfolio,
        orders: Dict[str, float],
        price_dict: Dict[str, float],
    ) -> None:

        if not orders:
            return

        # -----------------------------
        # 1️⃣ 먼저 매도 실행
        # -----------------------------
        for ticker, value in orders.items():

            if ticker == "CASH" or value >= 0:
                continue

            if ticker not in price_dict:
                continue

            price = price_dict[ticker]
            if price <= 0:
                continue

            position = portfolio.get_position(ticker)

            quantity = abs(value) / price

            # 보유량 초과 방지
            quantity = min(quantity, position.quantity)

            if quantity <= 0:
                continue

            portfolio.sell(ticker, quantity, price)

        # -----------------------------
        # 2️⃣ 그 다음 매수 실행
        # -----------------------------
        for ticker, value in orders.items():

            if ticker == "CASH" or value <= 0:
                continue

            if ticker not in price_dict:
                continue

            price = price_dict[ticker]
            if price <= 0:
                continue

            quantity = value / price

            if quantity <= 0:
                continue

            # 현금 초과 방지
            max_affordable = portfolio.cash / price
            quantity = min(quantity, max_affordable)

            if quantity <= 0:
                continue

            portfolio.buy(ticker, quantity, price)