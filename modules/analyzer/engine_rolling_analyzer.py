import numpy as np
import pandas as pd


class EngineRollingAnalyzer:

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

    def run(self):

        wealth_distribution = []
        cagr_distribution = []
        volatility_distribution = []
        max_drawdown_distribution = []

        total_dividend_distribution = []
        terminal_dividend_distribution = []
        yield_on_cost_distribution = []
        dividend_cagr_distribution = []

        current_start = self.start_date

        while True:

            scenario_end = current_start + pd.DateOffset(years=self.horizon_years)

            if scenario_end > self.end_date:
                break

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

            portfolio_series = history["portfolio_value"]

            # -------------------------------------------------
            # Wealth multiple
            # -------------------------------------------------

            end_value = portfolio_series.iloc[-1]

            monthly_points = portfolio_series.resample("ME").last()

            months = len(monthly_points)

            total_invested = (
                self.initial_capital +
                self.monthly_contribution * months
            )

            if total_invested > 0:
                wealth_multiple = end_value / total_invested
            else:
                wealth_multiple = 0

            wealth_distribution.append(wealth_multiple)

            # -------------------------------------------------
            # CAGR
            # -------------------------------------------------

            years = self.horizon_years

            if wealth_multiple > 0:
                cagr = wealth_multiple ** (1 / years) - 1
            else:
                cagr = 0

            cagr_distribution.append(cagr)

            # -------------------------------------------------
            # Volatility (DCA 제거 return)
            # -------------------------------------------------

            returns = []

            prev_value = None
            prev_month = None

            for date, value in portfolio_series.items():

                if prev_value is None:
                    prev_value = value
                    prev_month = date.month
                    continue

                contribution = 0

                if date.month != prev_month:
                    contribution = self.monthly_contribution

                r = (value - prev_value - contribution) / prev_value

                returns.append(r)

                prev_value = value
                prev_month = date.month

            returns = np.array(returns)

            if len(returns) > 0:
                volatility = returns.std() * np.sqrt(252)
            else:
                volatility = 0

            volatility_distribution.append(volatility)

            # -------------------------------------------------
            # Max Drawdown
            # -------------------------------------------------

            cummax = portfolio_series.cummax()

            drawdown = (portfolio_series - cummax) / cummax

            mdd = drawdown.min()

            max_drawdown_distribution.append(mdd)

            # -------------------------------------------------
            # Dividend
            # -------------------------------------------------

            if "dividend_income" in history.columns:

                monthly_div = history["dividend_income"].resample("ME").sum()

                total_dividend = monthly_div.sum()

                if len(monthly_div) >= 12:
                    terminal_dividend = monthly_div.iloc[-12:].sum()
                else:
                    terminal_dividend = monthly_div.sum()

            else:

                monthly_div = pd.Series(dtype=float)

                total_dividend = 0
                terminal_dividend = 0

            total_dividend_distribution.append(total_dividend)
            terminal_dividend_distribution.append(terminal_dividend)

            # -------------------------------------------------
            # Yield on Cost
            # -------------------------------------------------

            if total_invested > 0:
                yoc = terminal_dividend / total_invested
            else:
                yoc = 0

            yield_on_cost_distribution.append(yoc)

            # -------------------------------------------------
            # Dividend CAGR (DCA 보정)
            # -------------------------------------------------

            if len(monthly_div) >= 12:

                months = len(monthly_div)

                invested_capital = (
                    self.initial_capital +
                    np.arange(1, months + 1) * self.monthly_contribution
                )

                ttm_div = monthly_div.rolling(12).sum()

                yield_series = ttm_div / invested_capital

                yield_series = yield_series.dropna()

                # 🔧 초기 TTM 안정화 구간 제거 (추가된 한 줄)
                yield_series = yield_series.iloc[12:]

                if len(yield_series) > 1:

                    first_yield = yield_series.iloc[0]
                    last_yield = yield_series.iloc[-1]

                    if first_yield > 0 and last_yield > 0:

                        dividend_cagr = (
                            (last_yield / first_yield) ** (1 / years) - 1
                        )

                    else:

                        dividend_cagr = 0

                else:

                    dividend_cagr = 0

            else:

                dividend_cagr = 0

            dividend_cagr_distribution.append(dividend_cagr)

            # -------------------------------------------------

            current_start = current_start + pd.DateOffset(months=1)

        # -------------------------------------------------

        wealth_distribution = np.array(wealth_distribution)
        cagr_distribution = np.array(cagr_distribution)
        volatility_distribution = np.array(volatility_distribution)
        max_drawdown_distribution = np.array(max_drawdown_distribution)

        total_dividend_distribution = np.array(total_dividend_distribution)
        terminal_dividend_distribution = np.array(terminal_dividend_distribution)
        yield_on_cost_distribution = np.array(yield_on_cost_distribution)
        dividend_cagr_distribution = np.array(dividend_cagr_distribution)

        return {

            "scenario_count": len(wealth_distribution),

            "wealth_distribution": wealth_distribution,
            "cagr_distribution": cagr_distribution,
            "volatility_distribution": volatility_distribution,
            "max_drawdown_distribution": max_drawdown_distribution,

            "total_dividend_distribution": total_dividend_distribution,
            "terminal_dividend_distribution": terminal_dividend_distribution,
            "yield_on_cost_distribution": yield_on_cost_distribution,
            "dividend_cagr_distribution": dividend_cagr_distribution
        }