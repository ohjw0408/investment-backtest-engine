from typing import Dict
from modules.core.portfolio import Portfolio


class OrderExecutor:
    """
    주문 실행 엔진

    RebalanceStrategy가 생성한
    value 기반 주문을 실제 거래로 변환한다.

    역할:
    - value → quantity 변환
    - 매도 → 매수 순서 실행
    - Portfolio 상태 업데이트

    하지 않는 것:
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

        # -----------------------------
        # 1️⃣ 먼저 매도 실행
        # -----------------------------
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

            # 🔥 정수 주식
            quantity = int(abs(value) / price)

            if quantity <= 0:
                continue

            portfolio.sell(ticker, quantity, price)

        # -----------------------------
        # 2️⃣ 그 다음 매수 실행
        # -----------------------------
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

            # 🔥 정수 주식
            quantity = int(value / price)

            if quantity <= 0:
                continue

            try:
                portfolio.buy(ticker, quantity, price)

            except ValueError:
                # 현금 부족 시 주문 무시
                continue