class Position:
    """
    개별 자산 보유 상태 객체
    수량 기반 추적을 위한 최소 단위
    """

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.quantity = 0.0
        self.avg_price = 0.0
        self.realized_pnl = 0.0

    # -------------------------
    # 현재 평가 금액
    # -------------------------
    def market_value(self, current_price: float) -> float:
        return self.quantity * current_price

    # -------------------------
    # 매수
    # -------------------------
    def buy(self, quantity: float, price: float):
        if quantity <= 0:
            return

        total_cost = self.avg_price * self.quantity
        new_cost = price * quantity

        total_quantity = self.quantity + quantity

        if total_quantity > 0:
            self.avg_price = (total_cost + new_cost) / total_quantity

        self.quantity = total_quantity

    # -------------------------
    # 매도
    # -------------------------
    def sell(self, quantity: float, price: float):
        if quantity <= 0:
            return

        if quantity > self.quantity:
            raise ValueError("보유 수량보다 많이 매도할 수 없습니다.")

        pnl = (price - self.avg_price) * quantity
        self.realized_pnl += pnl

        self.quantity -= quantity

        if self.quantity == 0:
            self.avg_price = 0.0

    # -------------------------
    # 미실현 손익
    # -------------------------
    def unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.avg_price) * self.quantity

    # -------------------------
    # 현재 상태 요약
    # -------------------------
    def summary(self, current_price: float) -> dict:
        return {
            "ticker": self.ticker,
            "quantity": self.quantity,
            "avg_price": self.avg_price,
            "market_value": self.market_value(current_price),
            "unrealized_pnl": self.unrealized_pnl(current_price),
            "realized_pnl": self.realized_pnl,
        }
