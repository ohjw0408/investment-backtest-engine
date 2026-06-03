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
    kr_foreign_unrealized_gain: float = 0.0  # 청산 시 KR_FOREIGN 미실현 이익 (Phase 2e 패널용)
    # Phase 2f: 연도별 종합과세 트래킹
    financial_income_by_year: dict = None      # year → 그 해 위탁 금융소득(외부+배당+청산차익)
    comprehensive_years: tuple = ()            # 금융소득 종합과세 대상 연도(>2천만)


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
        isa_years_held: int = 3,
        apply_final_liquidation: bool = True,
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
            from modules.tax.session                import TaxSessionState
            other_financial_income = float(user_settings.get("other_financial_income", 0.0) or 0.0)
            # 공유 세션 — 배당·중간실현·청산을 한 금융소득 풀로 합산(종합과세 정확도).
            tax_session = TaxSessionState(other_financial_income=other_financial_income)
            div_engine  = TaxedDividendEngine(DividendEngine(), tax_engine, account_type,
                                              other_financial_income=other_financial_income,
                                              session=tax_session)
            exec_engine = TaxedOrderExecutor(tax_engine, account_type,
                                             gain_harvesting=gain_harvesting,
                                             session=tax_session)
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

        kr_foreign_unrealized_gain = 0.0
        financial_income_by_year = {}
        comprehensive_years = ()
        if tax_enabled and tax_engine is not None:
            from modules.tax.liquidation import apply_liquidation_tax
            last_prices = {
                t: float(price_data[t]['close'].iloc[-1])
                for t in config.tickers
                if t in price_data and not price_data[t].empty
            }
            # KR_FOREIGN 청산 미실현 이익 집계 (종합과세 합산 + 분할매도 패널용) — 청산 전 산출
            if account_type == "위탁" and hasattr(portfolio, 'positions'):
                for ticker, pos in portfolio.positions.items():
                    if ticker in last_prices and pos.quantity > 0:
                        if tax_engine.classify_asset(ticker) == "KR_FOREIGN":
                            gain = portfolio.unrealized_gain(ticker, last_prices[ticker])
                            if gain > 0:
                                kr_foreign_unrealized_gain += gain

            # 은퇴 적립은 무청산 인계(apply_final_liquidation=False) — 끝에 안 판다(gross).
            # 적립기 중간세(배당·리밸)는 루프에서 이미 처리됨. 최종 청산만 스킵.
            if apply_final_liquidation:
                # 청산 연도 기 발생 금융소득(외부 + 위탁 배당 + KR_FOREIGN 중간실현) — 청산이익 합산 종합과세
                ytd_financial_income = tax_session.ytd_financial_income
                ytd_us_gains = tax_session.ytd_us_realized_gains
                end_value = apply_liquidation_tax(
                    end_value=end_value,
                    portfolio=portfolio,
                    last_prices=last_prices,
                    tax_engine=tax_engine,
                    account_type=account_type,
                    total_contribution=total_invested,
                    ytd_us_realized_gains=ytd_us_gains,
                    age=user_settings.get('age', 40),
                    isa_years_held=isa_years_held,
                    ytd_financial_income=ytd_financial_income,
                )
                # 연도별 종합과세 트래킹 (마지막 연도에 청산 KR_FOREIGN 미실현차익 가산)
                financial_income_by_year = tax_session.finalize(
                    extra_final_year_income=kr_foreign_unrealized_gain
                )
            else:
                # 무청산: end_value=gross. 미실현차익은 인출단계로 인계(여기서 실현 안 함).
                financial_income_by_year = tax_session.finalize()
            threshold = getattr(tax_engine, 'DIVIDEND_THRESHOLD', 20_000_000)
            comprehensive_years = tuple(
                sorted(y for y, inc in financial_income_by_year.items() if inc > threshold)
            )

        return RunResult(
            history_df=history_df,
            end_value=end_value,
            kr_foreign_unrealized_gain=kr_foreign_unrealized_gain,
            financial_income_by_year=financial_income_by_year,
            comprehensive_years=comprehensive_years,
        )
