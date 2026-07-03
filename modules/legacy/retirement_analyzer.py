import pandas as pd
import numpy as np


class RetirementAnalyzer:

    def __init__(
        self,
        monthly_withdrawal: float,
        years: int,
        inflation: float = 0.0
    ):

        self.monthly_withdrawal = monthly_withdrawal
        self.years = years
        self.inflation = inflation

    # -------------------------------------------------
    # Retirement analysis
    # -------------------------------------------------

    def analyze(
        self,
        history: pd.DataFrame,
        initial_capital: float
    ):

        df = history.copy()

        df["date"] = pd.to_datetime(df["date"])

        df = df.set_index("date")

        # -------------------------------------------------
        # monthly portfolio value
        # -------------------------------------------------

        monthly = df["portfolio_value"].resample("ME").last()

        # -------------------------------------------------
        # monthly dividend
        # -------------------------------------------------

        if "dividend_income" in df.columns:

            dividend = df["dividend_income"].resample("ME").sum()

        else:

            dividend = pd.Series(0, index=monthly.index)

        terminal_values = []

        horizon = self.years * 12

        for start in range(len(monthly) - horizon):

            capital = initial_capital

            withdrawal = self.monthly_withdrawal

            for i in range(horizon):

                date = monthly.index[start + i]

                portfolio_value = monthly.iloc[start + i]

                dividend_income = dividend.iloc[start + i]

                # -----------------------------------------
                # return calculation
                # -----------------------------------------

                if i > 0:

                    prev_value = monthly.iloc[start + i - 1]

                    monthly_return = portfolio_value / prev_value - 1

                    capital *= (1 + monthly_return)

                # -----------------------------------------
                # dividend offsets withdrawal
                # -----------------------------------------

                net_withdrawal = withdrawal - dividend_income

                if net_withdrawal < 0:

                    net_withdrawal = 0

                capital -= net_withdrawal

                if capital <= 0:

                    capital = 0
                    break

                # -----------------------------------------
                # inflation adjustment
                # -----------------------------------------

                withdrawal *= (1 + self.inflation / 12)

            terminal_values.append(capital)

        terminal_values = np.array(terminal_values)

        success_count = np.sum(terminal_values > 0)

        success_rate = success_count / len(terminal_values)

        return {

            "success_rate": success_rate,

            "best_terminal": np.max(terminal_values),

            "median_terminal": np.median(terminal_values),

            "worst_terminal": np.min(terminal_values)

        }
