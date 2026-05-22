"""
backtest_logic.py
백테스트 엔드포인트의 핵심 로직 — app.py / tasks.py 양쪽에서 import 가능한 독립 모듈.
"""

import numpy as np

_portfolio_engine = None


def _get_portfolio_engine():
    global _portfolio_engine
    if _portfolio_engine is None:
        from modules.portfolio_engine import PortfolioEngine
        _portfolio_engine = PortfolioEngine()
    return _portfolio_engine


def run_backtest_logic(body: dict, progress_callback=None) -> dict:
    from modules.core.portfolio                 import Portfolio
    from modules.config.simulation_config       import SimulationConfig
    from modules.execution.order_executor       import OrderExecutor
    from modules.execution.cash_allocator       import CashAllocator
    from modules.simulation.dividend_engine     import DividendEngine
    from modules.simulation.contribution_engine import ContributionEngine
    from modules.simulation.withdrawal_engine   import WithdrawalEngine
    from modules.simulation.history_recorder    import HistoryRecorder
    from modules.simulation.simulation_loop     import SimulationLoop
    from modules.rebalance.periodic             import PeriodicRebalance

    portfolio_engine = _get_portfolio_engine()

    tickers    = [t['code']  for t in body['tickers']]
    weights    = {t['code']: t['weight'] for t in body['tickers']}
    start_date = body['start_date']
    end_date   = body['end_date']
    initial    = float(body.get('initial_capital', 10_000_000))
    monthly    = float(body.get('monthly_contribution', 0))
    div_mode   = body.get('dividend_mode', 'reinvest')
    rebal_mode  = body.get('rebal_mode', 'none')
    band_width  = float(body.get('band_width', 0.05))

    rebal_freq  = None if rebal_mode in ('none', 'band') else rebal_mode
    drift       = band_width if rebal_mode == 'band' else None

    strategy = PeriodicRebalance(
        target_weights      = weights,
        rebalance_frequency = rebal_freq,
        drift_threshold     = drift,
    )
    config = SimulationConfig(
        start_date           = start_date,
        end_date             = end_date,
        tickers              = tickers,
        target_weights       = weights,
        initial_capital      = initial,
        monthly_contribution = monthly,
        withdrawal_amount    = 0,
        dividend_mode        = div_mode,
        rebalance_frequency  = rebal_freq,
        inflation            = 0.0,
    )

    price_data, dates = portfolio_engine.price_loader.load(tickers, start_date, end_date)

    tax_enabled     = body.get('tax_enabled', False)
    account_type    = body.get('account_type', '위탁')
    user_settings   = body.get('user_settings', {})
    gain_harvesting = body.get('gain_harvesting', False)

    if tax_enabled and account_type != '위탁':
        from modules.tax.base_tax    import TaxEngine as _TaxEngine
        from modules.tax.account_tax import validate_account_portfolio
        _check = validate_account_portfolio(
            account_type, tickers, weights, _TaxEngine(user_settings)
        )
        if not _check['valid']:
            raise ValueError({
                'error':      'account_restrictions',
                'violations': _check['violations'],
                'disclaimer': _check.get('disclaimer'),
            })

    bt_tax_engine = None
    if tax_enabled:
        from modules.tax.base_tax    import TaxEngine
        from modules.tax.account_tax import TaxedDividendEngine
        from modules.execution.order_executor import TaxedOrderExecutor
        from modules.core.portfolio  import TaxTrackedPortfolio
        bt_tax_engine = TaxEngine(user_settings)
        div_engine    = TaxedDividendEngine(DividendEngine(), bt_tax_engine, account_type)
        exec_engine   = TaxedOrderExecutor(bt_tax_engine, account_type,
                                           gain_harvesting=gain_harvesting)
        portfolio     = TaxTrackedPortfolio(initial)
    else:
        div_engine  = DividendEngine()
        exec_engine = OrderExecutor()
        portfolio   = Portfolio(initial)

    loop     = SimulationLoop(div_engine, ContributionEngine(), WithdrawalEngine(),
                              exec_engine, CashAllocator())
    recorder = HistoryRecorder()
    loop.run(portfolio, strategy, config, price_data, dates, recorder,
             progress_callback=progress_callback)
    history_df = recorder.to_dataframe()

    if history_df.empty:
        raise ValueError("시뮬레이션 결과가 없습니다. 날짜 범위나 종목을 확인해주세요.")

    pv             = history_df['portfolio_value']
    years          = len(history_df) / 252
    total_invested = initial + monthly * years * 12
    end_value      = float(pv.iloc[-1])

    if tax_enabled and bt_tax_engine:
        if account_type == 'ISA':
            end_value = bt_tax_engine.after_tax_withdrawal(end_value, 'ISA', total_invested)
        elif account_type in ('연금저축', 'IRP'):
            end_value = bt_tax_engine.after_tax_withdrawal(
                end_value, account_type, total_invested, age=user_settings.get('age', 40))
        else:
            gain = end_value - total_invested
            if gain > 0:
                kr_foreign_gains = 0.0
                us_direct_gains  = 0.0
                for t, w in weights.items():
                    t_gain     = gain * w
                    asset_type = bt_tax_engine.classify_asset(t)
                    if asset_type == 'KR_FOREIGN':
                        kr_foreign_gains += t_gain
                    elif asset_type == 'US_DIRECT':
                        us_direct_gains  += t_gain
                total_tax = 0.0
                if kr_foreign_gains > 0:
                    total_tax += kr_foreign_gains * 0.154
                if us_direct_gains > 0:
                    total_tax += max(0.0, us_direct_gains - 2_500_000) * 0.22
                end_value -= total_tax

    total_return = (end_value / total_invested - 1) if total_invested > 0 else 0
    cagr         = (end_value / total_invested) ** (1 / years) - 1 if years > 0 and total_invested > 0 else 0
    cummax       = pv.cummax()
    mdd          = float(((pv - cummax) / cummax).min())
    daily_ret    = pv.pct_change().dropna()
    sharpe       = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    total_div    = float(history_df['dividend_income'].sum()) if 'dividend_income' in history_df.columns else 0

    h = history_df.copy()
    h['drawdown']       = (pv - cummax) / cummax
    h['total_invested'] = initial + monthly * np.arange(len(h)) / 21
    h_sampled = h.iloc[::max(1, len(h) // 500)]

    history_out = [
        {
            'date':            str(row['date'])[:10],
            'portfolio_value': round(float(row['portfolio_value'])),
            'total_invested':  round(float(row['total_invested'])),
            'drawdown':        round(float(row['drawdown']), 4),
        }
        for _, row in h_sampled.iterrows()
    ]

    import pandas as _pd
    h2 = history_df.copy()
    h2['year'] = _pd.to_datetime(h2['date']).dt.year
    annual_returns = []
    for yr, grp in h2.groupby('year'):
        s = float(grp['portfolio_value'].iloc[0])
        e = float(grp['portfolio_value'].iloc[-1])
        if s > 0:
            annual_returns.append({'year': int(yr), 'return': round((e / s - 1), 4)})

    return {
        'tax_enabled':  tax_enabled,
        'account_type': account_type if tax_enabled else None,
        'metrics': {
            'end_value':      round(end_value),
            'total_invested': round(total_invested),
            'total_return':   round(total_return, 4),
            'cagr':           round(cagr, 4),
            'mdd':            round(mdd, 4),
            'sharpe':         round(sharpe, 2),
            'total_dividend': round(total_div),
            'years':          round(years, 1),
        },
        'history':        history_out,
        'annual_returns': annual_returns,
    }
