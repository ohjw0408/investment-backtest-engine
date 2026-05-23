"""
modules/simulation/taxable_runner.py
세금 포함 시뮬레이션 단일 진입점.

모든 *_logic.py가 공유하는 "컴포넌트 조립 → 루프 실행 → 청산세 적용" 파이프라인.
"""
from dataclasses import dataclass

import pandas as pd


@dataclass
class RunResult:
    history_df: pd.DataFrame
    end_value: float  # 청산세 적용 후 최종 자산


class TaxableSimulationRunner:

    def run(
        self,
        config,
        price_data: dict,
        dates,
        strategy,
        tax_enabled: bool = False,
        account_type: str = '위탁',
        user_settings: dict = None,
        tax_engine=None,
        gain_harvesting: bool = False,
        progress_callback=None,
    ) -> RunResult:
        from modules.core.portfolio                  import Portfolio
        from modules.execution.order_executor        import OrderExecutor
        from modules.execution.cash_allocator        import CashAllocator
        from modules.simulation.dividend_engine      import DividendEngine
        from modules.simulation.contribution_engine  import ContributionEngine
        from modules.simulation.withdrawal_engine    import WithdrawalEngine
        from modules.simulation.history_recorder     import HistoryRecorder
        from modules.simulation.simulation_loop      import SimulationLoop

        user_settings = user_settings or {}

        if tax_enabled:
            if tax_engine is None:
                from modules.tax.base_tax import TaxEngine
                tax_engine = TaxEngine(user_settings)
            from modules.tax.account_tax           import TaxedDividendEngine
            from modules.execution.order_executor  import TaxedOrderExecutor
            from modules.core.portfolio            import TaxTrackedPortfolio
            div_engine  = TaxedDividendEngine(DividendEngine(), tax_engine, account_type)
            exec_engine = TaxedOrderExecutor(tax_engine, account_type,
                                             gain_harvesting=gain_harvesting)
            portfolio   = TaxTrackedPortfolio(config.initial_capital)
        else:
            tax_engine  = None
            div_engine  = DividendEngine()
            exec_engine = OrderExecutor()
            portfolio   = Portfolio(config.initial_capital)

        loop     = SimulationLoop(div_engine, ContributionEngine(), WithdrawalEngine(),
                                  exec_engine, CashAllocator())
        recorder = HistoryRecorder()
        loop.run(portfolio, strategy, config, price_data, dates, recorder,
                 progress_callback=progress_callback)
        history_df = recorder.to_dataframe()

        if history_df.empty:
            raise ValueError("시뮬레이션 결과가 없습니다. 날짜 범위나 종목을 확인해주세요.")

        years          = len(history_df) / 252
        total_invested = config.initial_capital + config.monthly_contribution * years * 12
        end_value      = float(history_df['portfolio_value'].iloc[-1])

        if tax_enabled and tax_engine is not None:
            from modules.tax.liquidation import apply_liquidation_tax
            last_prices = {
                t: float(price_data[t]['close'].iloc[-1])
                for t in config.tickers
                if t in price_data and not price_data[t].empty
            }
            ytd_us_gains = getattr(exec_engine, '_ytd_us_gains', 0.0)
            end_value = apply_liquidation_tax(
                end_value=end_value,
                portfolio=portfolio,
                last_prices=last_prices,
                tax_engine=tax_engine,
                account_type=account_type,
                total_contribution=total_invested,
                ytd_us_realized_gains=ytd_us_gains,
                age=user_settings.get('age', 40),
            )

        return RunResult(history_df=history_df, end_value=end_value)
