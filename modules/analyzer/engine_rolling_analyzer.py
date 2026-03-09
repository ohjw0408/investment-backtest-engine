import numpy as np
import pandas as pd


class EngineRollingAnalyzer:
    """
    PortfolioEngine 기반 Rolling Scenario Analyzer

    각 시작 시점마다 엔진을 실행하여
    wealth / dividend distribution 생성
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
        dividend_mode="reinvest"
    ):

        self.engine = engine
        self.strategy = strategy

        self.tickers = tickers

        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)

        self.horizon_years = horizon_years

        self.initial_capital = initial_capital
        self.monthly_contribution = monthly_contribution

        self.dividend_mode = dividend_mode

    # -------------------------------------------------
    # main
    # -------------------------------------------------

    def run(self):

        wealth_distribution = []
        total_dividend_distribution = []
        terminal_dividend_distribution = []

        current_start = self.start_date

        while True:

            scenario_end = current_start + pd.DateOffset(years=self.horizon_years)

            if scenario_end > self.end_date:
                break

            # ---------------------------------
            # 엔진 실행
            # ---------------------------------

            result = self.engine.run_simulation(

                tickers=self.tickers,

                start_date=current_start.strftime("%Y-%m-%d"),
                end_date=scenario_end.strftime("%Y-%m-%d"),

                initial_capital=self.initial_capital,

                monthly_contribution=self.monthly_contribution,

                strategy=self.strategy,

                dividend_mode=self.dividend_mode
            )

            history = result["history"].copy()

            history["date"] = pd.to_datetime(history["date"])
            history = history.set_index("date")

            # ---------------------------------
            # Wealth multiple 계산 (DCA 포함)
            # ---------------------------------

            end_value = history["portfolio_value"].iloc[-1]

            monthly_points = history.resample("ME").last()
            months = len(monthly_points)

            total_invested = (
                self.initial_capital +
                self.monthly_contribution * months
            )

            if total_invested <= 0:
                wealth = 0
            else:
                wealth = end_value / total_invested

            wealth_distribution.append(wealth)

            # ---------------------------------
            # Dividend 계산
            # ---------------------------------

            if "dividend_income" in history.columns:

                monthly_dividend = history["dividend_income"].resample("ME").sum()

                # 전체 기간 배당
                total_dividend = monthly_dividend.sum()

                # 마지막 12개월 배당
                if len(monthly_dividend) >= 12:
                    terminal_dividend = monthly_dividend.iloc[-12:].sum()
                else:
                    terminal_dividend = monthly_dividend.sum()

            else:

                total_dividend = 0
                terminal_dividend = 0

            total_dividend_distribution.append(total_dividend)
            terminal_dividend_distribution.append(terminal_dividend)

            # ---------------------------------
            # 다음 시작점 (1개월 이동)
            # ---------------------------------

            current_start = current_start + pd.DateOffset(months=1)

        wealth_distribution = np.array(wealth_distribution)
        total_dividend_distribution = np.array(total_dividend_distribution)
        terminal_dividend_distribution = np.array(terminal_dividend_distribution)

        return {

            "scenario_count": len(wealth_distribution),

            "wealth_distribution": wealth_distribution,

            "total_dividend_distribution": total_dividend_distribution,

            "terminal_dividend_distribution": terminal_dividend_distribution

        }