import pandas as pd
from typing import List, Dict, Any

from modules.price_loader import PriceLoader
from modules.core.portfolio import Portfolio
from modules.execution.order_executor import OrderExecutor


class PortfolioEngine:

    def __init__(self):

        self.loader = PriceLoader()
        self.executor = OrderExecutor()

    # -------------------------------------------------
    # 메인 시뮬레이션
    # -------------------------------------------------

    def run_simulation(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        strategy,
        initial_capital: float = 1_000_000,
        reinvest_dividend: bool = True
    ) -> Dict[str, Any]:

        portfolio = Portfolio(initial_cash=initial_capital)

        # -------------------------------------------------
        # 가격 데이터 로드
        # -------------------------------------------------

        price_data = {}

        for ticker in tickers:

            df = self.loader.get_price(ticker, start_date, end_date)

            if df.empty:
                raise ValueError(f"{ticker} 가격 데이터 없음")

            df = df.copy()
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")

            price_data[ticker] = df.set_index("date")

        # -------------------------------------------------
        # 공통 날짜
        # -------------------------------------------------

        dates = price_data[tickers[0]].index

        history = []

        # -------------------------------------------------
        # Daily Simulation Loop
        # -------------------------------------------------

        for date in dates:

            price_dict = {}

            for ticker in tickers:

                if date not in price_data[ticker].index:
                    continue

                price = price_data[ticker].loc[date, "close"]

                price_dict[ticker] = price

            # -------------------------------------------------
            # 배당 처리
            # -------------------------------------------------

            daily_dividend = 0

            for ticker, position in portfolio.positions.items():

                if ticker not in price_data:
                    continue

                if date not in price_data[ticker].index:
                    continue

                dividend = price_data[ticker].loc[date, "dividend"]

                if dividend > 0:

                    dividend_cash = dividend * position.quantity

                    daily_dividend += dividend_cash

                    if reinvest_dividend:

                        price = price_dict[ticker]

                        quantity = dividend_cash / price

                        position.buy(quantity, price)

                    else:

                        portfolio.cash += dividend_cash

            # -------------------------------------------------
            # 리밸런싱
            # -------------------------------------------------

            if strategy is not None and strategy.should_rebalance(date, portfolio, price_dict):

                orders = strategy.generate_orders(
                    portfolio,
                    price_dict
                )

                self.executor.execute_orders(
                    portfolio,
                    orders,
                    price_dict
                )

            # -------------------------------------------------
            # 포트폴리오 가치 계산
            # -------------------------------------------------

            total_value = portfolio.total_value(price_dict)

            # -------------------------------------------------
            # history 기록
            # -------------------------------------------------

            row = {
                "date": date,
                "portfolio_value": total_value,
                "cash": portfolio.cash,
                "dividend_income": daily_dividend
            }

            for ticker, position in portfolio.positions.items():

                if ticker not in price_dict:
                    continue

                price = price_dict[ticker]

                value = position.market_value(price)

                row[f"{ticker}_value"] = value
                row[f"{ticker}_weight"] = (
                    value / total_value if total_value > 0 else 0
                )

            history.append(row)

        # -------------------------------------------------
        # DataFrame 변환
        # -------------------------------------------------

        history_df = pd.DataFrame(history)

        # -------------------------------------------------
        # 성과 계산
        # -------------------------------------------------

        total_return = (
            history_df["portfolio_value"].iloc[-1] / initial_capital - 1
        )

        return {
            "history": history_df,
            "final_value": history_df["portfolio_value"].iloc[-1],
            "total_return": total_return
        }
