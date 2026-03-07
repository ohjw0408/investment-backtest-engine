import pandas as pd

from modules.core.portfolio import Portfolio
from modules.price_loader import PriceLoader
from modules.execution.order_executor import OrderExecutor
from modules.execution.cash_allocator import CashAllocator
from modules.rebalance.periodic import PeriodicRebalance
from modules.config.simulation_config import SimulationConfig


class PortfolioEngine:

    def __init__(self):

        self.loader = PriceLoader()
        self.executor = OrderExecutor()
        self.cash_allocator = CashAllocator()

    # -------------------------------------------------
    # New API
    # -------------------------------------------------

    def run(self, config: SimulationConfig):

        portfolio = Portfolio(config.initial_capital)

        strategy = PeriodicRebalance(
            target_weights=config.target_weights,
            rebalance_frequency=config.rebalance_frequency
        )

        # -------------------------------------------------
        # 가격 데이터 로드
        # -------------------------------------------------

        price_data = {}

        for ticker in config.tickers:

            df = self.loader.get_price(
                ticker,
                config.start_date,
                config.end_date
            )

            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")

            price_data[ticker] = df

        # -------------------------------------------------
        # union calendar
        # -------------------------------------------------

        all_dates = set()

        for df in price_data.values():
            all_dates.update(df.index)

        dates = sorted(all_dates)

        history = []

        last_month = None

        # -------------------------------------------------
        # simulation loop
        # -------------------------------------------------

        for date in dates:

            price_dict = {}

            for ticker in config.tickers:

                if date not in price_data[ticker].index:
                    continue

                price = price_data[ticker].loc[date, "close"]
                price_dict[ticker] = price

            if not price_dict:
                continue

            # -------------------------------------------------
            # dividend
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

                    if config.dividend_mode == "reinvest":
                        portfolio.cash += dividend_cash

                    elif config.dividend_mode == "cash":
                        portfolio.cash += dividend_cash

                    elif config.dividend_mode == "withdraw":
                        # 배당 즉시 인출
                        pass

            # -------------------------------------------------
            # monthly contribution
            # -------------------------------------------------

            if config.monthly_contribution > 0:

                if last_month != date.month:

                    portfolio.cash += config.monthly_contribution
                    last_month = date.month

            # -------------------------------------------------
            # withdrawal
            # -------------------------------------------------

            if config.withdrawal_amount > 0:

                if portfolio.cash >= config.withdrawal_amount:

                    portfolio.cash -= config.withdrawal_amount

                else:

                    needed = config.withdrawal_amount - portfolio.cash
                    portfolio.cash = 0

                    for ticker, position in portfolio.positions.items():

                        if ticker not in price_dict:
                            continue

                        price = price_dict[ticker]

                        value = position.market_value(price)

                        if value <= 0:
                            continue

                        sell_qty = int(min(value, needed) / price)

                        if sell_qty <= 0:
                            continue

                        portfolio.sell(ticker, sell_qty, price)

                        needed -= sell_qty * price

                        if needed <= 0:
                            break

            # -------------------------------------------------
            # rebalance
            # -------------------------------------------------

            if strategy.should_rebalance(
                date,
                portfolio,
                price_dict
            ):

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
            # cash sweep
            # -------------------------------------------------

            cash_target = config.target_weights.get("CASH", 0)

            if cash_target == 0 and config.dividend_mode in ["reinvest", "withdraw"]:

                self.cash_allocator.allocate_cash(
                    portfolio,
                    price_dict,
                    config.target_weights
                )

            # -------------------------------------------------
            # history
            # -------------------------------------------------

            total_value = portfolio.total_value(price_dict)

            row = {
                "date": date,
                "portfolio_value": total_value,
                "cash": portfolio.cash,
                "dividend_income": daily_dividend
            }

            for ticker in config.tickers:

                if ticker in portfolio.positions:

                    price = price_dict.get(ticker, 0)
                    value = portfolio.positions[ticker].market_value(price)

                else:
                    value = 0

                row[f"{ticker}_value"] = value

                if total_value > 0:
                    row[f"{ticker}_weight"] = value / total_value
                else:
                    row[f"{ticker}_weight"] = 0

            history.append(row)

        history_df = pd.DataFrame(history)

        return {
            "history": history_df,
            "final_value": history_df["portfolio_value"].iloc[-1]
        }

    # -------------------------------------------------
    # backward compatibility
    # -------------------------------------------------

    def run_simulation(

        self,
        tickers,
        start_date,
        end_date,
        initial_capital,
        strategy=None,
        monthly_contribution=0,
        withdrawal_amount=0,
        dividend_mode="reinvest"

    ):

        if strategy:

            target_weights = strategy.target_weights
            rebalance_frequency = strategy.rebalance_frequency

        else:

            target_weights = {}
            rebalance_frequency = "monthly"

        config = SimulationConfig(

            start_date=start_date,
            end_date=end_date,
            tickers=tickers,
            target_weights=target_weights,
            initial_capital=initial_capital,
            monthly_contribution=monthly_contribution,
            withdrawal_amount=withdrawal_amount,
            dividend_mode=dividend_mode,
            rebalance_frequency=rebalance_frequency
        )

        return self.run(config)