from modules.core.portfolio import Portfolio
from modules.price_loader import PriceLoader
from modules.execution.order_executor import OrderExecutor
from modules.execution.cash_allocator import CashAllocator
from modules.config.simulation_config import SimulationConfig

from modules.simulation.dividend_engine import DividendEngine
from modules.simulation.contribution_engine import ContributionEngine
from modules.simulation.withdrawal_engine import WithdrawalEngine

from modules.simulation.price_data_loader import PriceDataLoader
from modules.simulation.history_recorder import HistoryRecorder
from modules.simulation.simulation_loop import SimulationLoop


class PortfolioEngine:

    def __init__(self, loader=None):

        if loader is None:
            loader = PriceLoader()

        self.loader = loader

        self.executor = OrderExecutor()
        self.cash_allocator = CashAllocator()

        self.dividend_engine = DividendEngine()
        self.contribution_engine = ContributionEngine()
        self.withdrawal_engine = WithdrawalEngine()

        self.price_loader = PriceDataLoader(self.loader)

        self.simulation_loop = SimulationLoop(
            self.dividend_engine,
            self.contribution_engine,
            self.withdrawal_engine,
            self.executor,
            self.cash_allocator
        )

        # 🔥 핵심: price cache
        self._price_cache = {}

    # -------------------------------------------------
    # 핵심 실행
    # -------------------------------------------------

    def run(self, config: SimulationConfig, strategy):

        portfolio = Portfolio(config.initial_capital)

        # 🔥 캐시 key
        key = (
            tuple(config.tickers),
            config.start_date,
            config.end_date
        )

        # 🔥 캐시 사용
        if key not in self._price_cache:
            price_data, dates = self.price_loader.load(
                config.tickers,
                config.start_date,
                config.end_date
            )
            self._price_cache[key] = (price_data, dates)
        else:
            price_data, dates = self._price_cache[key]

        # 🔒 안전: copy로 완전 동일성 보장
        price_data = price_data.copy()

        recorder = HistoryRecorder()

        self.simulation_loop.run(
            portfolio,
            strategy,
            config,
            price_data,
            dates,
            recorder
        )

        history_df = recorder.to_dataframe()

        return {
            "history":     history_df,
            "final_value": history_df["portfolio_value"].iloc[-1],
            "portfolio":   portfolio
        }

    # -------------------------------------------------
    # 편의 함수
    # -------------------------------------------------

    def run_simulation(

        self,
        tickers,
        start_date,
        end_date,
        initial_capital,
        strategy,
        monthly_contribution = 0,
        withdrawal_amount    = 0,
        dividend_mode        = "reinvest",
        inflation            = 0.0,

    ):

        config = SimulationConfig(

            start_date           = start_date,
            end_date             = end_date,
            tickers              = tickers,
            target_weights       = strategy.target_weights,
            initial_capital      = initial_capital,
            monthly_contribution = monthly_contribution,
            withdrawal_amount    = withdrawal_amount,
            dividend_mode        = dividend_mode,
            rebalance_frequency  = strategy.rebalance_frequency,
            inflation            = inflation,
        )

        return self.run(config, strategy)