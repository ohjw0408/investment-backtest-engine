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

        # 모든 티커의 날짜 합집합
        all_dates = set()
        for df in price_data.values():
            all_dates.update(df.index)
        dates = sorted(all_dates)

        # ✅ 합집합 날짜 기준으로 reindex 후 ffill
        # 한 티커에 없는 날짜는 직전 유효값으로 채움
        # dividend/split은 0/1로 채워야 중복 계산 방지
        full_index = pd.DatetimeIndex(dates)
        for ticker in tickers:
            df = price_data[ticker].reindex(full_index)
            # 가격 컬럼은 ffill
            price_cols = ["open", "high", "low", "close", "volume"]
            df[price_cols] = df[price_cols].ffill()
            # 배당/분할은 없는 날 0/1로 채움 (ffill하면 중복 계산됨)
            if "dividend" in df.columns:
                df["dividend"] = df["dividend"].fillna(0)
            if "split" in df.columns:
                df["split"] = df["split"].fillna(1)
            price_data[ticker] = df

        return price_data, dates