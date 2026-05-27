"""
calculator_logic.py
/api/calculator/run 의 핵심 로직 — app.py / tasks.py 양쪽에서 import 가능한 독립 모듈.
"""

import datetime
from dateutil.relativedelta import relativedelta

_portfolio_engine = None


def _get_portfolio_engine():
    global _portfolio_engine
    if _portfolio_engine is None:
        from modules.portfolio_engine import PortfolioEngine
        _portfolio_engine = PortfolioEngine()
    return _portfolio_engine


def _get_price_start(portfolio_engine, ticker: str):
    try:
        cur = portfolio_engine.loader.conn.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=?", (ticker,)
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def _get_dividend_start(portfolio_engine, ticker: str):
    try:
        cur = portfolio_engine.loader.conn.execute(
            "SELECT MIN(date) FROM corporate_actions WHERE code=? AND dividend > 0",
            (ticker,)
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def _make_strategy_factory(target_weights, rebal_mode, band_width=0.05):
    from modules.rebalance.periodic import PeriodicRebalance
    if rebal_mode == 'none':
        rebalance_frequency = None
        drift_threshold     = None
    elif rebal_mode == 'band':
        rebalance_frequency = None
        drift_threshold     = band_width
    else:
        rebalance_frequency = rebal_mode
        drift_threshold     = None

    def strategy_factory():
        return PeriodicRebalance(
            target_weights      = target_weights,
            rebalance_frequency = rebalance_frequency,
            drift_threshold     = drift_threshold,
        )
    return strategy_factory


def run_calculator_logic(body: dict, progress_callback=None) -> dict:
    from modules.retirement.accumulation_analyzer import AccumulationAnalyzer

    portfolio_engine = _get_portfolio_engine()

    tickers_input    = body['tickers']
    initial_capital  = float(body['initial_capital'])
    monthly_contrib  = float(body['monthly_contribution'])
    years            = int(body['years'])
    rebal_mode       = body['rebal_mode']
    band_width       = float(body.get('band_width', 0.05))
    dividend_mode    = body['dividend_mode']

    ticker_codes   = [t['code'] for t in tickers_input]
    target_weights = {t['code']: t['weight'] for t in tickers_input}

    strategy_factory = _make_strategy_factory(target_weights, rebal_mode, band_width)

    usdkrw_start = portfolio_engine.loader.USD_KRW_START

    for ticker in ticker_codes:
        try:
            portfolio_engine.loader.get_price(
                ticker,
                usdkrw_start,
                datetime.date.today().strftime('%Y-%m-%d')
            )
        except Exception as e:
            print(f"[calculator] {ticker} 데이터 로드 오류: {e}")

    price_starts = [_get_price_start(portfolio_engine, t) for t in ticker_codes]
    price_starts = [d for d in price_starts if d]

    data_start = max([usdkrw_start] + price_starts) if price_starts else usdkrw_start
    data_end   = datetime.date.today().strftime('%Y-%m-%d')

    # ── 가상 데이터 옵트인 ────────────────────────────────────────────
    use_synthetic    = bool(body.get('use_synthetic', False))
    _prep_meta: dict = {}  # ScenarioDataPreparer 결과 (used_synthetic, warnings 등)

    if use_synthetic:
        from modules.data_preparation import prepare_scenario_data
        _prep_meta = prepare_scenario_data(
            tickers        = ticker_codes,
            required_years = years,
            data_end       = data_end,
            allow_backfill = True,
            allow_synthetic = True,
            purpose        = "calculator",
        )
        data_start = _prep_meta["effective_start"]
    # ── 데이터 부족 검사 (use_synthetic=False 시 기존 동작 유지) ───────
    else:
        start_dt  = datetime.datetime.strptime(data_start, '%Y-%m-%d').date()
        max_years = (datetime.date.today() - start_dt).days // 365
        if years > max_years:
            raise ValueError(
                f"데이터 부족: {ticker_codes}의 데이터는 {data_start}부터 있어서 "
                f"최대 {max_years}년 시뮬레이션이 가능합니다."
            )

    div_starts = [_get_dividend_start(portfolio_engine, t) for t in ticker_codes]
    div_starts = [d for d in div_starts if d]
    div_start  = max(div_starts) if div_starts else None

    tax_enabled     = body.get('tax_enabled', False)
    account_type    = body.get('account_type', '위탁')
    user_settings   = body.get('user_settings', {})
    isa_renewal     = body.get('isa_renewal', False)
    gain_harvesting = body.get('gain_harvesting', False)
    tax_engine      = None
    if tax_enabled:
        from modules.tax.base_tax import TaxEngine
        tax_engine = TaxEngine(user_settings)

    analyzer = AccumulationAnalyzer(
        portfolio_engine     = portfolio_engine,
        tickers              = ticker_codes,
        strategy_factory     = strategy_factory,
        data_start           = data_start,
        data_end             = data_end,
        accumulation_years   = years,
        monthly_contribution = monthly_contrib,
        initial_capital      = initial_capital,
        dividend_mode        = dividend_mode,
        step_months          = 3,
        verbose              = False,
        div_start            = div_start,
        tax_engine           = tax_engine,
        account_type         = account_type,
        isa_renewal          = isa_renewal,
        gain_harvesting      = gain_harvesting,
        progress_callback    = progress_callback,
    )

    result = analyzer.run()

    if div_start:
        result['distribution']['div_data_start']  = div_start
        result['distribution']['div_cases_count'] = len(result['cases'])
    else:
        result['distribution']['no_dividend'] = True

    cases_summary = [
        {
            'run_id':    c['run_id'],
            'start':     c['start'],
            'end':       c['end'],
            'end_value': round(c['end_value']),
            'end_value_early_cancel': round(c['end_value_early_cancel'])
                if 'end_value_early_cancel' in c else None,
            'cagr':      round(c['cagr'], 4),
            'mdd':       round(c['mdd'], 4),
        }
        for c in result['cases']
    ]

    has_partial_isa = result.get('distribution_early_cancel') is not None

    return {
        'cases':                    cases_summary,
        'cases_count':              len(cases_summary),
        'distribution':             result['distribution'],
        'distribution_early_cancel': result.get('distribution_early_cancel'),
        'isa_partial_cycle':        has_partial_isa,
        'isa_remainder_years':      years % 3 if has_partial_isa else 0,
        'used_synthetic':           _prep_meta.get('used_synthetic', False),
        'synthetic_info':           _prep_meta.get('synthetic_info', {}),
        'backfilled':               _prep_meta.get('backfilled', []),
        'warnings':                 _prep_meta.get('warnings', []),
    }
