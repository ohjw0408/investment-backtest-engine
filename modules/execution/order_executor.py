from typing import Dict
from modules.core.portfolio import Portfolio


class OrderExecutor:
    """
    주문 실행 엔진

    RebalanceStrategy가 생성한
    value 기반 주문을 실제 거래로 변환한다.

    역할
    - value → quantity 변환
    - 매도 → 매수 순서 실행
    - Portfolio 상태 업데이트

    하지 않는 것
    - 전략 판단
    - 세금 계산
    - 거래 비용 계산
    """

    def execute_orders(
        self,
        portfolio: Portfolio,
        orders: Dict[str, float],
        price_dict: Dict[str, float],
    ) -> None:

        if not orders:
            return

        # ---------------------------------
        # 1️⃣ 먼저 매도 실행
        # ---------------------------------

        for ticker, value in orders.items():

            if ticker == "CASH":
                continue

            if value >= 0:
                continue

            if ticker not in price_dict:
                continue

            price = price_dict[ticker]

            if price <= 0:
                continue

            quantity = abs(value) / price

            position = portfolio.get_position(ticker)

            # 보유량 초과 매도 방지
            quantity = min(quantity, position.quantity)

            if quantity <= 0:
                continue

            portfolio.sell(ticker, quantity, price)

        # ---------------------------------
        # 2️⃣ 그 다음 매수 실행
        # ---------------------------------

        for ticker, value in orders.items():

            if ticker == "CASH":
                continue

            if value <= 0:
                continue

            if ticker not in price_dict:
                continue

            price = price_dict[ticker]

            if price <= 0:
                continue

            quantity = value / price

            # 현금 기반 최대 수량 계산
            max_quantity = portfolio.cash / price

            # float 오차 방지
            quantity = min(quantity, max_quantity * 0.999)

            if quantity <= 0:
                continue

            portfolio.buy(ticker, quantity, price)