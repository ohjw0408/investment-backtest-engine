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

        # ---------------------------------
        # 포트폴리오 가치 계산
        # ---------------------------------

        total_value = portfolio.total_value(price_dict)

        cash = portfolio.cash

        asset_value = total_value - cash

        # ---------------------------------
        # 기본 기록
        # ---------------------------------

        row = {
            "date": date,
            "portfolio_value": total_value,
            "asset_value": asset_value,
            "cash": cash,
            "dividend_income": dividend_income
        }

        # ---------------------------------
        # 자산별 기록
        # ---------------------------------

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

        df = pd.DataFrame(self.history)

        df = df.sort_values("date").reset_index(drop=True)

        return df