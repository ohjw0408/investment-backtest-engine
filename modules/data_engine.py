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
        """로컬 캐시 확인 후 없으면 다운로드"""

        file_path = os.path.join(self.base_path, f"{ticker}.csv")

        # -------------------------------------------------
        # 1️⃣ 캐시 존재하면 로드
        # -------------------------------------------------
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path)

                # 날짜 정리
                df["Date"] = pd.to_datetime(df["Date"])

                df = df.set_index("Date")

                # 숫자형 강제 변환
                df["Close"] = pd.to_numeric(df["Close"], errors="coerce")

                return df["Close"].dropna()

            except Exception as e:
                print("Cache read error:", e)

        # -------------------------------------------------
        # 2️⃣ 다운로드
        # -------------------------------------------------
        try:
            df = yf.download(
                ticker,
                start=self.start_date,
                auto_adjust=True,
                progress=False
            )

            if not df.empty:

                # 저장 전에 Date 컬럼 생성
                df_reset = df.reset_index()

                df_reset.to_csv(file_path, index=False)

                return df["Close"]

        except Exception as e:
            print(f"Error fetching {ticker}: {e}")

        return pd.Series(dtype=float)