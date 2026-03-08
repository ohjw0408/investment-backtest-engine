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
        dividend_income
    ):

        total_value = portfolio.total_value(price_dict)

        row = {
            "date": date,
            "portfolio_value": total_value,
            "cash": portfolio.cash,
            "dividend_income": dividend_income
        }

        for ticker in tickers:

            if ticker in portfolio.positions:

                price = price_dict.get(ticker, 0)
                value = portfolio.positions[ticker].market_value(price)

            else:
                value = 0

            row[f"{ticker}_value"] = value

            if total_value > 0:
                row[f"{ticker}_weight"] = value / total_value
            else:
                row[f"{ticker}_weight"] = 0

        self.history.append(row)

    def to_dataframe(self):
        return pd.DataFrame(self.history)