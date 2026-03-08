import pandas as pd
import numpy as np
from dateutil.relativedelta import relativedelta


class EngineRollingAnalyzer:
    """
    Engine-based rolling scenario analyzer

    PortfolioEngine을 반복 실행하여
    terminal wealth / dividend distribution을 생성한다.
    """

    def __init__(
        self,
        engine,
        strategy,
        tickers,
        start_date,
        end_date,
        horizon_years,
        initial_capital=0,
        monthly_contribution=0,
        dividend_mode="reinvest",
    ):

        self.engine = engine
        self.strategy = strategy
        self.tickers = tickers

        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)

        self.horizon_years = horizon_years

        self.initial_capital = initial_capital
        self.monthly_contribution = monthly_contribution

        # ---------------------------------
        # 사용자 선택 배당 처리 방식
        # ---------------------------------

        allowed_modes = ["reinvest", "cash", "withdraw"]

        if dividend_mode not in allowed_modes:
            raise ValueError(
                f"Invalid dividend_mode: {dividend_mode}. "
                f"Allowed: {allowed_modes}"
            )

        self.dividend_mode = dividend_mode

    # -------------------------------------------------
    # main
    # -------------------------------------------------

    def run(self):

        wealth_distribution = []
        dividend_distribution = []

        current_start = self.start_date

        while True:

            scenario_end = current_start + relativedelta(years=self.horizon_years)

            if scenario_end > self.end_date:
                break

            result = self.engine.run_simulation(

                tickers=self.tickers,

                start_date=current_start.strftime("%Y-%m-%d"),
                end_date=scenario_end.strftime("%Y-%m-%d"),

                initial_capital=self.initial_capital,

                strategy=self.strategy,

                monthly_contribution=self.monthly_contribution,

                dividend_mode=self.dividend_mode
            )

            history = result["history"]

            # ---------------------------------------------
            # terminal wealth
            # ---------------------------------------------

            final_value = history["portfolio_value"].iloc[-1]

            invested_capital = (
                self.initial_capital
                + self.monthly_contribution * self.horizon_years * 12
            )

            if invested_capital > 0:

                wealth_multiple = final_value / invested_capital

                wealth_distribution.append(wealth_multiple)

            # ---------------------------------------------
            # dividend distribution
            # ---------------------------------------------

            if "dividend_income" in history.columns:

                total_dividend = history["dividend_income"].sum()

                if invested_capital > 0:

                    dividend_yield = total_dividend / invested_capital

                    dividend_distribution.append(dividend_yield)

            # ---------------------------------------------
            # next scenario
            # ---------------------------------------------

            current_start += relativedelta(months=1)

        wealth_distribution = np.array(wealth_distribution)
        dividend_distribution = np.array(dividend_distribution)

        return {

            "wealth_distribution": wealth_distribution,

            "dividend_distribution": dividend_distribution,

            "scenario_count": len(wealth_distribution)

        }