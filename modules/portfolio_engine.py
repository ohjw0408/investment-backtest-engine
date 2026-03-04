import pandas as pd
import numpy as np
from typing import List, Dict, Any

from modules.price_loader import PriceLoader
from modules.execution.order_executor import OrderExecutor
from modules.core.portfolio import Portfolio


class PortfolioEngine:

    def __init__(self):
        self.loader = PriceLoader()
        self.executor = OrderExecutor()

    # -------------------------------------------------
    # Vectorized Portfolio Backtest
    # -------------------------------------------------

    def run(
        self,
        tickers: List[str],
        weights: List[float],
        start_date: str,
        end_date: str,
        initial_capital: float = 1_000_000,
        risk_free_rate: float = 0.0,
    ) -> Dict[str, Any]:

        if len(tickers) != len(weights):
            raise ValueError("tickers와 weights 길이가 다릅니다.")

        weights = np.array(weights)

        if not np.isclose(weights.sum(), 1.0):
            raise ValueError("weights 합이 1이 되어야 합니다.")

        returns_list = []

        for t in tickers:

            df = self.loader.get_price(t, start_date, end_date)

            if df.empty:
                raise ValueError(f"{t} 가격 데이터 없음")

            df["date"] = pd.to_datetime(df["date"])

            df = df.sort_values("date")

            df["daily_return"] = df["close"].pct_change().fillna(0.0)

            returns_list.append(
                df[["date", "daily_return"]].rename(
                    columns={"daily_return": t}
                )
            )

        merged = returns_list[0]

        for r in returns_list[1:]:

            merged = pd.merge(merged, r, on="date", how="inner")

        merged = merged.dropna().reset_index(drop=True)

        # 포트폴리오 수익률
        merged["portfolio_return"] = merged[tickers] @ weights

        # 개별 기여도
        for i, t in enumerate(tickers):

            merged[f"{t}_contribution"] = merged[t] * weights[i]

            merged[f"{t}_cum_contribution"] = (
                1 + merged[f"{t}_contribution"]
            ).cumprod()

        # 누적 수익률
        merged["cum_return"] = (
            1 + merged["portfolio_return"]
        ).cumprod()

        merged["portfolio_value"] = (
            initial_capital * merged["cum_return"]
        )

        # 성과 지표
        total_return = merged["cum_return"].iloc[-1] - 1

        days = (merged["date"].iloc[-1] - merged["date"].iloc[0]).days
        years = days / 365.25
        cagr = merged["cum_return"].iloc[-1] ** (1 / years) - 1

        merged["cum_max"] = merged["cum_return"].cummax()

        merged["drawdown"] = (
            merged["cum_return"] / merged["cum_max"] - 1
        )

        mdd = merged["drawdown"].min()

        volatility = (
            merged["portfolio_return"].std() * np.sqrt(252)
        )

        excess_return = cagr - risk_free_rate

        sharpe = (
            excess_return / volatility if volatility != 0 else np.nan
        )

        return {
            "tickers": tickers,
            "weights": weights.tolist(),
            "start_date": start_date,
            "end_date": end_date,
            "final_value": float(merged["portfolio_value"].iloc[-1]),
            "total_return": float(total_return),
            "cagr": float(cagr),
            "mdd": float(mdd),
            "volatility": float(volatility),
            "sharpe": float(sharpe),
            "history": merged,
        }

    # -------------------------------------------------
    # Event Driven Simulation Engine
    # -------------------------------------------------

    def run_simulation(
        self,
        tickers: List[str],
        strategy,
        start_date: str,
        end_date: str,
        initial_cash: float = 1_000_000,
    ):

        portfolio = Portfolio(initial_cash)

        price_data = {}

        for ticker in tickers:

            df = self.loader.get_price(ticker, start_date, end_date)

            if df.empty:
                raise ValueError(f"{ticker} 가격 데이터 없음")

            df["date"] = pd.to_datetime(df["date"])

            df = df.sort_values("date")

            price_data[ticker] = df[["date", "close"]]

        merged = price_data[tickers[0]].rename(
            columns={"close": tickers[0]}
        )

        for t in tickers[1:]:

            df = price_data[t].rename(columns={"close": t})

            merged = pd.merge(
                merged,
                df,
                on="date",
                how="inner"
            )

        merged = merged.sort_values("date")

        history = []

        # ---------------------------------
        # Simulation Loop
        # ---------------------------------

        for _, row in merged.iterrows():

            date = row["date"]

            price_dict = {t: row[t] for t in tickers}

            # 리밸런싱 여부 판단
            if strategy.should_rebalance(date):

                orders = strategy.generate_orders(
                    portfolio,
                    price_dict
                )

                self.executor.execute_orders(
                    portfolio,
                    orders,
                    price_dict
                )

            value = portfolio.total_value(price_dict)

            history.append(
                {
                    "date": date,
                    "portfolio_value": value,
                    "cash": portfolio.cash
                }
            )

        result = pd.DataFrame(history)

        return result