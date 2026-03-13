import numpy as np
import pandas as pd


class EngineRollingAnalyzer:

    def __init__(
        self,
        engine,
        strategy_factory,
        tickers,
        start_date,
        end_date,
        horizon_years,
        initial_capital=0,
        monthly_contribution=0,
        dividend_mode="reinvest"
    ):

        self.engine = engine
        self.strategy_factory = strategy_factory
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

            # ✅ 매 회차마다 전략 객체 새로 생성
            strategy = self.strategy_factory()

            result = self.engine.run_simulation(

                tickers=self.tickers,
                start_date=current_start.strftime("%Y-%m-%d"),
                end_date=scenario_end.strftime("%Y-%m-%d"),

                initial_capital=self.initial_capital,
                monthly_contribution=self.monthly_contribution,

                strategy=strategy,
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
            # Volatility (월간 수익률 기반)
            # -------------------------------------------------

            monthly_points = portfolio_series.resample("ME").last()

            if self.monthly_contribution > 0:
                prev_values = monthly_points.shift(1)
                adjusted = monthly_points - self.monthly_contribution
                monthly_returns = (adjusted / prev_values - 1).dropna()
            else:
                monthly_returns = monthly_points.pct_change().dropna()

            if len(monthly_returns) > 0:
                volatility = monthly_returns.std() * np.sqrt(12)
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
            # Dividend (합산)
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
            # ✅ Dividend CAGR — DPS 기반 (수량 증가 효과 제거)
            #
            # 각 종목별로:
            #   DPS(t) = ticker_dividend(t) / ticker_quantity(t)
            # 연간 DPS 합산 후 CAGR 계산
            # -------------------------------------------------

            dividend_cagr = self._calc_dividend_cagr(history)

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

    # -------------------------------------------------
    # DPS 기반 Dividend CAGR 계산
    # -------------------------------------------------

    def _calc_dividend_cagr(self, history: pd.DataFrame) -> float:
        """
        종목별 DPS(주당배당금) 기반 가중평균으로 배당 성장률 계산.

        각 배당 발생일마다:
            weighted_DPS(t) = Σ ( ticker_weight(t) × ticker_DPS(t) )
            ticker_DPS(t)   = ticker_dividend(t) / ticker_quantity(t)

        연간 weighted_DPS 합산 후:
            CAGR = (마지막해 DPS / 첫해 DPS) ^ (1/n) - 1
        """

        # 배당 발생한 날 전체 수집 (어느 종목이든 배당 있는 날)
        div_cols = [f"{t}_dividend" for t in self.tickers
                    if f"{t}_dividend" in history.columns]

        if not div_cols:
            return 0.0

        any_div_mask = history[div_cols].sum(axis=1) > 0
        div_days = history[any_div_mask].copy()

        if len(div_days) == 0:
            return 0.0

        weighted_dps_series = pd.Series(0.0, index=div_days.index)

        for ticker in self.tickers:

            div_col    = f"{ticker}_dividend"
            qty_col    = f"{ticker}_quantity"
            weight_col = f"{ticker}_weight"

            if div_col not in history.columns:
                continue
            if qty_col not in history.columns:
                continue
            if weight_col not in history.columns:
                continue

            div     = div_days[div_col]
            qty     = div_days[qty_col]
            weight  = div_days[weight_col]

            # 배당 발생 + 수량 > 0 인 날만 유효
            valid = (div > 0) & (qty > 0)

            dps = pd.Series(0.0, index=div_days.index)
            dps[valid] = div[valid] / qty[valid]

            weighted_dps_series += weight * dps

        # 연간 weighted DPS 합산
        yearly_dps = weighted_dps_series.resample("YE").sum()
        yearly_dps = yearly_dps[yearly_dps > 0]

        # ✅ 첫해/마지막해 무조건 제거
        # 윈도우 시작/종료가 1월이 아니면 첫해·마지막해 배당이 불완전함
        # (예: 4월 시작이면 첫해는 4~12월 배당만 잡힘)
        if len(yearly_dps) > 2:
            yearly_dps = yearly_dps.iloc[1:-1]

        if len(yearly_dps) < 2:
            return 0.0

        first_dps = yearly_dps.iloc[0]
        last_dps  = yearly_dps.iloc[-1]
        n         = len(yearly_dps) - 1

        if first_dps <= 0:
            return 0.0

        return float((last_dps / first_dps) ** (1 / n) - 1)