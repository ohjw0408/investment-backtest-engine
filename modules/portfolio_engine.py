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

import pandas as pd


class PortfolioEngine:

    def __init__(self, loader=None):

        if loader is None:
            loader = PriceLoader()

        self.loader = loader

        self.executor        = OrderExecutor()
        self.cash_allocator  = CashAllocator()

        self.dividend_engine      = DividendEngine()
        self.contribution_engine  = ContributionEngine()
        self.withdrawal_engine    = WithdrawalEngine()

        self.price_loader = PriceDataLoader(self.loader)

        self.simulation_loop = SimulationLoop(
            self.dividend_engine,
            self.contribution_engine,
            self.withdrawal_engine,
            self.executor,
            self.cash_allocator
        )

        # 🔥 전체 범위 캐시: (tickers, data_start, data_end) → (price_data, dates)
        self._price_cache = {}

    # -------------------------------------------------
    # 전체 범위 로드 (캐시)
    # -------------------------------------------------

    def preload(self, tickers, data_start, data_end):
        """
        전체 데이터 범위를 한 번에 로드해서 캐시에 저장.
        롤링 시뮬 전에 호출하면 이후 run()에서 슬라이스만 수행.
        """
        key = (tuple(sorted(tickers)), data_start, data_end)
        if key not in self._price_cache:
            price_data, dates = self.price_loader.load(tickers, data_start, data_end)
            self._price_cache[key] = (price_data, dates)
        return key

    def clear_cache(self):
        self._price_cache.clear()

    # -------------------------------------------------
    # 핵심 실행
    # -------------------------------------------------

    def run(self, config: SimulationConfig, strategy, portfolio_class=None):

        pf_cls    = portfolio_class if portfolio_class is not None else Portfolio
        portfolio = pf_cls(config.initial_capital,
                           fee_rate=float(getattr(config, "fee_rate", 0.0) or 0.0),
                           stock_tickers=getattr(config, "stock_tickers", None))

        # 🔥 전체 범위 캐시 key (tickers + 전체 범위)
        # preload()가 먼저 호출됐으면 캐시 히트
        # 아니면 요청 범위 그대로 로드
        full_key = (tuple(sorted(config.tickers)), config.start_date, config.end_date)

        # 캐시에서 더 넓은 범위 찾기
        price_data, dates = self._find_cached_or_load(config)

        # 날짜 범위 슬라이스
        start_ts = pd.Timestamp(config.start_date)
        end_ts   = pd.Timestamp(config.end_date)

        sliced_dates = [d for d in dates if start_ts <= d <= end_ts]

        sliced_data = {}
        for ticker, df in price_data.items():
            sliced_data[ticker] = df.loc[
                (df.index >= start_ts) & (df.index <= end_ts)
            ]

        recorder = HistoryRecorder()

        self.simulation_loop.run(
            portfolio,
            strategy,
            config,
            sliced_data,
            sliced_dates,
            recorder
        )

        history_df = recorder.to_dataframe()

        # 마지막 가격 저장 (최종 청산세 계산용)
        last_prices = {}
        if sliced_dates:
            last_date = sliced_dates[-1]
            for ticker in config.tickers:
                df = sliced_data.get(ticker)
                if df is not None and not df.empty:
                    last_prices[ticker] = float(df["close"].iloc[-1])

        return {
            "history":     history_df,
            "final_value": float(history_df["portfolio_value"].iloc[-1]) if not history_df.empty else 0.0,
            "portfolio":   portfolio,
            "last_prices": last_prices,
            "total_fees":  float(getattr(portfolio, "total_fees", 0.0)),  # D4
        }

    def _find_cached_or_load(self, config):
        """
        캐시에서 요청 범위를 포함하는 데이터 찾기.
        없으면 새로 로드 후 캐시 저장.
        """
        tickers_key = tuple(sorted(config.tickers))
        start_ts    = pd.Timestamp(config.start_date)
        end_ts      = pd.Timestamp(config.end_date)

        # 캐시에서 포함 범위 검색
        for (cached_tickers, cached_start, cached_end), (price_data, dates) in self._price_cache.items():
            if (cached_tickers == tickers_key
                    and pd.Timestamp(cached_start) <= start_ts
                    and pd.Timestamp(cached_end)   >= end_ts
                    and set(config.tickers) <= set(price_data.keys())):
                return price_data, dates

        # 캐시 미스 → 로드 후 저장
        price_data, dates = self.price_loader.load(
            config.tickers,
            config.start_date,
            config.end_date
        )
        key = (tickers_key, config.start_date, config.end_date)
        self._price_cache[key] = (price_data, dates)
        return price_data, dates

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
        **kwargs,
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

        return self.run(config, strategy,
                       portfolio_class=kwargs.get("portfolio_class"))