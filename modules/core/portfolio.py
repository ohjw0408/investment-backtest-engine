from typing import Dict
from modules.core.position import Position


class Portfolio:
    """
    수량 기반 포트폴리오 상태 객체
    """

    def __init__(self, initial_cash: float):
        self.cash = initial_cash
        self.positions: Dict[str, Position] = {}

    # -------------------------
    # 포지션 가져오기
    # -------------------------
    def get_position(self, ticker: str) -> Position:
        if ticker not in self.positions:
            self.positions[ticker] = Position(ticker)
        return self.positions[ticker]

    # -------------------------
    # 매수
    # -------------------------
    def buy(self, ticker: str, quantity: float, price: float):
        cost = quantity * price

        if cost > self.cash:
            raise ValueError("현금이 부족합니다.")

        position = self.get_position(ticker)
        position.buy(quantity, price)

        self.cash -= cost

    # -------------------------
    # 매도
    # -------------------------
    def sell(self, ticker: str, quantity: float, price: float):
        position = self.get_position(ticker)
        position.sell(quantity, price)

        proceeds = quantity * price
        self.cash += proceeds

    # -------------------------
    # 총 자산 가치 (현금 포함)
    # -------------------------
    def total_value(self, price_dict: Dict[str, float]) -> float:
        total = self.cash

        for ticker, position in self.positions.items():
            if ticker in price_dict:
                total += position.market_value(price_dict[ticker])

        return total

    # -------------------------
    # 현재 비중 계산
    # -------------------------
    def current_weights(
        self,
        price_dict: Dict[str, float],
        include_cash: bool = True,
    ) -> Dict[str, float]:

        weights = {}

        total = self.total_value(price_dict)

        if total == 0:
            return weights

        # 1️⃣ 자산 비중 계산
        asset_total = 0.0

        for ticker, position in self.positions.items():
            if ticker in price_dict:
                value = position.market_value(price_dict[ticker])
                asset_total += value

        for ticker, position in self.positions.items():
            if ticker in price_dict:
                value = position.market_value(price_dict[ticker])

                if include_cash:
                    weights[ticker] = value / total
                else:
                    if asset_total > 0:
                        weights[ticker] = value / asset_total

        # 2️⃣ 현금 비중 추가 (옵션)
        if include_cash:
            weights["CASH"] = self.cash / total

        return weights

    # -------------------------
    # 상태 요약
    # -------------------------
    def summary(self, price_dict: Dict[str, float]) -> dict:
        return {
            "cash": self.cash,
            "total_value": self.total_value(price_dict),
            "weights_including_cash": self.current_weights(
                price_dict, include_cash=True
            ),
            "weights_excluding_cash": self.current_weights(
                price_dict, include_cash=False
            ),
        }


class TaxTrackedPortfolio(Portfolio):
    """
    Portfolio 확장 - 평균 취득단가(avg_cost) 추적.
    세금 계산 시 실현 차익 계산에 사용.
    """

    def __init__(self, initial_cash: float):
        super().__init__(initial_cash)
        self._avg_costs: Dict[str, float] = {}

    def buy(self, ticker: str, quantity: float, price: float):
        old_pos  = self.positions.get(ticker)
        old_qty  = old_pos.quantity if old_pos else 0.0
        old_cost = self._avg_costs.get(ticker, price)
        super().buy(ticker, quantity, price)
        new_qty = old_qty + quantity
        if new_qty > 0:
            self._avg_costs[ticker] = (old_qty * old_cost + quantity * price) / new_qty

    def get_avg_cost(self, ticker: str) -> float | None:
        return self._avg_costs.get(ticker)

    def unrealized_gain(self, ticker: str, current_price: float) -> float:
        pos = self.positions.get(ticker)
        if pos is None or pos.quantity <= 0:
            return 0.0
        avg_cost = self._avg_costs.get(ticker, current_price)
        return (current_price - avg_cost) * pos.quantity