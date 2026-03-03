import yfinance as yf
import pandas as pd
import os


class DataEngine:
    def __init__(self, start_date="1950-01-01"):
        self.start_date = start_date
        self.base_path = "data"

        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)

    def get_symbol_data(self, ticker):
        """로컬 캐시 확인 후 없으면 yfinance로 다운로드"""

        file_path = os.path.join(self.base_path, f"{ticker}.csv")

        # 로컬 캐시
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path, index_col=0, parse_dates=True)
                if "Close" in df.columns:
                    return df["Close"]
            except:
                pass

        # 다운로드
        try:
            df = yf.download(
                ticker,
                start=self.start_date,
                auto_adjust=True,
                progress=False
            )

            if not df.empty:
                df.to_csv(file_path)
                return df["Close"]

        except Exception as e:
            print(f"Error fetching {ticker}: {e}")

        return pd.Series(dtype=float)