import pandas as pd
import numpy as np


class RollingScenarioAnalyzer:
    """
    Rolling historical scenario analyzer

    PortfolioEngine이 생성한 history 데이터를 이용해
    투자 기간별 terminal wealth / dividend yield 분포를 계산한다.
    """

    def __init__(self, years: int):

        self.years = years
        self.horizon = years * 12  # monthly 기준

    # -------------------------------------------------
    # main
    # -------------------------------------------------

    def analyze(self, history: pd.DataFrame):

        df = history.copy()

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

        # ---------------------------------------------
        # monthly portfolio value
        # ---------------------------------------------

        monthly_value = df["portfolio_value"].resample("ME").last()

        # ---------------------------------------------
        # monthly dividend
        # ---------------------------------------------

        if "dividend_income" in df.columns:
            monthly_dividend = df["dividend_income"].resample("ME").sum()
        else:
            monthly_dividend = pd.Series(0, index=monthly_value.index)

        wealth_distribution = []
        dividend_yield_distribution = []

        n = len(monthly_value)

        # ---------------------------------------------
        # rolling window
        # ---------------------------------------------

        for start in range(n - self.horizon):

            end = start + self.horizon

            start_value = monthly_value.iloc[start]
            end_value = monthly_value.iloc[end]

            # -------------------------
            # wealth multiple
            # -------------------------

            if start_value > 0:
                wealth_multiple = end_value / start_value
            else:
                continue

            # -------------------------
            # dividend yield
            # -------------------------

            dividend_total = monthly_dividend.iloc[start:end].sum()

            if end_value > 0:
                dividend_yield = dividend_total / end_value
            else:
                dividend_yield = 0

            wealth_distribution.append(wealth_multiple)
            dividend_yield_distribution.append(dividend_yield)

        wealth_distribution = np.array(wealth_distribution)
        dividend_yield_distribution = np.array(dividend_yield_distribution)

        return {

            "wealth_distribution": wealth_distribution,

            "dividend_distribution": dividend_yield_distribution

        }