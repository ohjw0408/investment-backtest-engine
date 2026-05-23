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
    import pandas as _pd
    from modules.simulation.taxable_runner  import TaxableSimulationRunner
    from modules.config.simulation_config   import SimulationConfig
    from modules.rebalance.periodic         import PeriodicRebalance

    portfolio_engine = _get_portfolio_engine()

    tickers    = [t['code']  for t in body['tickers']]
    weights    = {t['code']: t['weight'] for t in body['tickers']}
    start_date = body['start_date']
    end_date   = body['end_date']
    initial    = float(body.get('initial_capital', 10_000_000))
    monthly    = float(body.get('monthly_contribution', 0))
    div_mode   = body.get('dividend_mode', 'reinvest')
    rebal_mode = body.get('rebal_mode', 'none')
    band_width = float(body.get('band_width', 0.05))

    rebal_freq = None if rebal_mode in ('none', 'band') else rebal_mode
    drift      = band_width if rebal_mode == 'band' else None

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

    price_data, dates = portfolio_engine.price_loader.load(tickers, start_date, end_date)

    runner = TaxableSimulationRunner()
    result = runner.run(
        config           = config,
        price_data       = price_data,
        dates            = dates,
        strategy         = strategy,
        tax_enabled      = tax_enabled,
        account_type     = account_type,
        user_settings    = user_settings,
        gain_harvesting  = gain_harvesting,
        progress_callback= progress_callback,
    )

    history_df = result.history_df
    end_value  = result.end_value

    pv             = history_df['portfolio_value']
    years          = len(history_df) / 252
    total_invested = initial + monthly * years * 12
    total_return   = (end_value / total_invested - 1) if total_invested > 0 else 0
    cagr           = (end_value / total_invested) ** (1 / years) - 1 if years > 0 and total_invested > 0 else 0
    cummax         = pv.cummax()
    mdd            = float(((pv - cummax) / cummax).min())
    daily_ret      = pv.pct_change().dropna()
    sharpe         = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    total_div      = float(history_df['dividend_income'].sum()) if 'dividend_income' in history_df.columns else 0

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
