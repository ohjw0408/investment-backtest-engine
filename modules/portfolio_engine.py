import pandas as pd

from modules.price_loader import PriceLoader
from modules.execution.order_executor import OrderExecutor
from modules.core.portfolio import Portfolio


class PortfolioEngine:
    """
    포트폴리오 시뮬레이션 엔진

    역할
    - 가격 데이터 로드
    - 전략(strategy) 실행
    - 주문 실행(OrderExecutor)
    - 포트폴리오 가치 계산
    """

    def __init__(self):

        self.loader = PriceLoader()
        self.executor = OrderExecutor()

    # -------------------------------------------------
    # 메인 시뮬레이션 함수
    # -------------------------------------------------
    def run_simulation(
        self,
        tickers,
        start_date,
        end_date,
        strategy,
        initial_capital=1_000_000,
    ):

        portfolio = Portfolio(initial_capital)

        # -----------------------------
        # 가격 데이터 로드
        # -----------------------------
        price_data = {}

        for ticker in tickers:

            df = self.loader.get_price(
                ticker,
                start_date,
                end_date
            )

            if df.empty:
                raise ValueError(f"{ticker} 가격 데이터 없음")

            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")

            price_data[ticker] = df

        # -----------------------------
        # 날짜 기준 데이터 병합
        # -----------------------------
        merged = None

        for ticker, df in price_data.items():

            tmp = df[["date", "close"]].rename(
                columns={"close": ticker}
            )

            if merged is None:
                merged = tmp
            else:
                merged = pd.merge(
                    merged,
                    tmp,
                    on="date",
                    how="inner"
                )

        merged = merged.sort_values("date").reset_index(drop=True)

        # -----------------------------
        # 시뮬레이션 결과 저장
        # -----------------------------
        history = []

        # -----------------------------
        # 메인 루프
        # -----------------------------
        for _, row in merged.iterrows():

            date = row["date"]

            price_dict = {
                ticker: row[ticker]
                for ticker in tickers
            }

            # -----------------------------
            # 리밸런싱 여부 판단
            # -----------------------------
            if strategy.should_rebalance(date):

                orders = strategy.generate_orders(
                    portfolio,
                    price_dict,
                )

                self.executor.execute_orders(
                    portfolio,
                    orders,
                    price_dict,
                )

            # -----------------------------
            # 포트폴리오 가치 계산
            # -----------------------------
            value = portfolio.total_value(price_dict)

            history.append(
                {
                    "date": date,
                    "portfolio_value": value,
                    "cash": portfolio.cash,
                }
            )

        history_df = pd.DataFrame(history)

        # -----------------------------
        # 총 수익률 계산
        # -----------------------------
        total_return = (
            history_df["portfolio_value"].iloc[-1]
            / history_df["portfolio_value"].iloc[0]
            - 1
        )

        return {
            "history": history_df,
            "total_return": total_return,
        }
