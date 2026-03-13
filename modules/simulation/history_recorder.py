import pandas as pd


class HistoryRecorder:

    def __init__(self):
        self.history = []

    def record(
        self,
        date,
        portfolio,
        price_dict,
        tickers,
        dividend_by_ticker,
        cash_flow: float = 0.0,   # ✅ 추가: 납입(+) / 인출(-), TWR/MWR 계산용
    ):

        total_value = portfolio.total_value(price_dict)
        cash        = portfolio.cash
        asset_value = total_value - cash

        total_dividend = sum(dividend_by_ticker.values())

        row = {
            "date":             date,
            "portfolio_value":  total_value,
            "asset_value":      asset_value,
            "cash":             cash,
            "dividend_income":  total_dividend,
            "cash_flow":        cash_flow,   # ✅ 추가
        }

        for ticker in tickers:

            if ticker in portfolio.positions:
                price    = price_dict.get(ticker, 0)
                position = portfolio.positions[ticker]
                value    = position.market_value(price)
                quantity = position.quantity
            else:
                value    = 0
                quantity = 0

            row[f"{ticker}_value"]    = value
            row[f"{ticker}_quantity"] = quantity
            row[f"{ticker}_dividend"] = dividend_by_ticker.get(ticker, 0)

            if total_value > 0:
                row[f"{ticker}_weight"] = value / total_value
            else:
                row[f"{ticker}_weight"] = 0

        self.history.append(row)

    def to_dataframe(self):
        df = pd.DataFrame(self.history)
        df = df.sort_values("date").reset_index(drop=True)
        return df