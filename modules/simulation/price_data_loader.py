import pandas as pd


class PriceDataLoader:

    def __init__(self, loader):
        self.loader = loader

    def load(self, tickers, start_date, end_date):

        price_data = {}

        for ticker in tickers:

            df = self.loader.get_price(
                ticker,
                start_date,
                end_date
            )

            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")

            price_data[ticker] = df

        all_dates = set()

        for df in price_data.values():
            all_dates.update(df.index)

        dates = sorted(all_dates)

        return price_data, dates