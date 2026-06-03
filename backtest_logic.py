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


def _run_multi_account_backtest_logic(body: dict, progress_callback=None) -> dict:
    """백테스트 멀티계좌 — 단일 역사윈도우(start~end) 1회 실행(롤링 아님).

    MultiAccountSimulationLoop을 1회 돌려 combined + 계좌별 결과를 surface.
    투자계산기 멀티계좌(_run_multi_account_calculator_logic)와 입력 스키마·세금 정책 동일,
    차이는 롤링 분포 대신 단일 윈도우 시계열.
    """
    import pandas as _pd
    from modules.simulation.multi_account_loop import MultiAccountSimulationLoop
    from modules.tax.account_tax import DistributionPolicy
    from modules.multi_account_common import (
        normalize_multi_accounts, validate_initial_capital_limits,
        build_loop_accounts, build_savings_summary,
    )

    portfolio_engine = _get_portfolio_engine()
    accounts      = normalize_multi_accounts(body)
    start_date    = body['start_date']
    end_date      = body['end_date']
    tax_enabled   = bool(body.get('tax_enabled', False))
    user_settings = body.get('user_settings', {})
    gain_harvesting = bool(body.get('gain_harvesting', False))

    init_errors = validate_initial_capital_limits(accounts)
    if init_errors:
        raise ValueError({'error': 'initial_capital_limit', 'violations': init_errors})

    all_tickers: list[str] = []
    for a in accounts:
        a['gain_harvesting'] = gain_harvesting and a['type'] == '위탁'
        for t in a['tickers']:
            if t['code'] not in all_tickers:
                all_tickers.append(t['code'])

    # 계좌별 종목 규제 검증(ISA US_DIRECT 불가·KRX_GOLD 위탁전용 등)
    if tax_enabled:
        from modules.tax.base_tax    import TaxEngine
        from modules.tax.account_tax import validate_account_portfolio
        te = TaxEngine(user_settings)
        for a in accounts:
            w = {t['code']: t['weight'] for t in a['tickers']}
            chk = validate_account_portfolio(a['type'], [t['code'] for t in a['tickers']], w, te)
            if not chk['valid']:
                raise ValueError({
                    'error': 'account_restrictions',
                    'violations': chk['violations'],
                    'disclaimer': chk.get('disclaimer'),
                })

    distribution_policy = DistributionPolicy.from_dict(body.get('distribution_policy'))
    manual_comprehensive_years = set(int(y) for y in (body.get('manual_comprehensive_years') or []))
    reinvest_tax_credit = bool(body.get('reinvest_tax_credit', False))
    has_pension = any(a['type'] in ('연금저축', 'IRP') for a in accounts)
    transfers_enabled = (
        distribution_policy is not None
        or any(a.get('isa_renewal') for a in accounts)
        or (tax_enabled and has_pension)
    )

    price_data, dates = portfolio_engine.price_loader.load(all_tickers, start_date, end_date)
    if not dates:
        raise ValueError("백테스트 기간에 가격 데이터가 없습니다. 종목·기간을 확인하세요.")

    loop_accounts = build_loop_accounts(
        accounts, start_date, end_date,
        default_dividend_mode=body.get('dividend_mode', 'reinvest'),
    )
    result = MultiAccountSimulationLoop(transfers_enabled=transfers_enabled).run(
        accounts=loop_accounts,
        price_data=price_data,
        dates=dates,
        tax_enabled=tax_enabled,
        user_settings=user_settings,
        distribution_policy=distribution_policy,
        manual_comprehensive_years=manual_comprehensive_years,
        reinvest_tax_credit=reinvest_tax_credit,
        progress_callback=progress_callback,
    )

    hist = result.combined_history_df
    if hist.empty:
        raise ValueError("시뮬레이션 결과가 없습니다. 종목·기간을 확인하세요.")

    total_initial = sum(float(a.get('initial_capital', 0.0)) for a in accounts)
    total_monthly = sum(float(a.get('monthly_contribution', 0.0)) for a in accounts)
    end_value     = float(result.combined_end_value)
    pv            = hist['portfolio_value']
    years         = len(hist) / 252
    total_invested = total_initial + total_monthly * years * 12
    total_return  = (end_value / total_invested - 1) if total_invested > 0 else 0
    cagr          = (end_value / total_invested) ** (1 / years) - 1 if years > 0 and total_invested > 0 else 0
    cummax        = pv.cummax()
    mdd           = float(((pv - cummax) / cummax).min())
    daily_ret     = pv.pct_change().dropna()
    sharpe        = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    total_div     = float(hist['dividend_income'].sum()) if 'dividend_income' in hist.columns else 0

    h = hist.copy()
    h['drawdown']       = (pv - cummax) / cummax
    h['total_invested'] = total_initial + total_monthly * np.arange(len(h)) / 21
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

    h2 = hist.copy()
    h2['year'] = _pd.to_datetime(h2['date']).dt.year
    annual_returns = []
    for yr, grp in h2.groupby('year'):
        s = float(grp['portfolio_value'].iloc[0])
        e = float(grp['portfolio_value'].iloc[-1])
        if s > 0:
            annual_returns.append({'year': int(yr), 'return': round((e / s - 1), 4)})

    # 계좌별 분해
    accounts_out = [
        {
            'account_id':     ar['account_id'],
            'type':           ar['type'],
            'end_value':      round(float(ar['end_value'])),
            'raw_end_value':  round(float(ar['raw_end_value'])),
            'tax_paid':       round(float(ar.get('tax_paid', 0.0))),
        }
        for ar in result.account_results
    ]

    # 절세액 요약(세금 ON일 때만) — account_results에서 구성
    savings = None
    if tax_enabled:
        per_account = [
            {
                'account_id':            ar['account_id'],
                'type':                  ar['type'],
                'brokerage_assumed_tax': float(ar.get('brokerage_assumed_tax', 0.0)),
                'actual_tax':            float(ar.get('tax_paid', 0.0)),
                'tax_saving':            float(ar.get('tax_saving', 0.0)),
                'gain_harvest_saving':   float(ar.get('gain_harvest_saving', 0.0)),
            }
            for ar in result.account_results
        ]
        savings_raw = {
            'accounts': per_account,
            'combined': {
                'brokerage_assumed_tax': sum(a['brokerage_assumed_tax'] for a in per_account),
                'actual_tax':            sum(a['actual_tax'] for a in per_account),
                'tax_saving':            sum(a['tax_saving'] for a in per_account),
            },
        }
        savings = build_savings_summary(savings_raw)

    return {
        'multi_account':  True,
        'tax_enabled':    tax_enabled,
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
        'accounts':       accounts_out,
        'savings':        savings,
        'g2': {
            'transfer_log':                  result.transfer_log,
            'comprehensive_years':           list(result.comprehensive_years),
            'annual_deduction_credit':       round(float(result.annual_deduction_credit)),
            'pension_transfer_credit_total': round(float(result.pension_transfer_credit_total)),
        },
        'financial_income_by_year': {
            int(y): round(v) for y, v in (result.financial_income_by_year or {}).items()
        },
    }


def run_backtest_logic(body: dict, progress_callback=None) -> dict:
    # 멀티계좌(accounts 배열) → 단일윈도우 멀티계좌 경로. 단일계좌(legacy 필드) → 기존 경로.
    if body.get('accounts'):
        return _run_multi_account_backtest_logic(body, progress_callback)

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

    # ── 가상 데이터 옵트인 ────────────────────────────────────────────────
    use_synthetic = bool(body.get('use_synthetic', False))
    _prep_meta: dict = {}

    if use_synthetic:
        from modules.data_preparation import prepare_scenario_data
        _prep_meta = prepare_scenario_data(
            tickers          = tickers,
            requested_start  = start_date,
            data_end         = end_date,
            allow_backfill   = True,
            allow_synthetic  = True,
            purpose          = "backtest",
        )
    # ── 가격 로드 ──────────────────────────────────────────────────────────
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

    history_df                 = result.history_df
    end_value                  = result.end_value
    kr_foreign_unrealized_gain = getattr(result, 'kr_foreign_unrealized_gain', 0.0)
    financial_income_by_year   = getattr(result, 'financial_income_by_year', None) or {}
    comprehensive_years        = list(getattr(result, 'comprehensive_years', ()) or ())

    # Phase 2e/2f: 분할매도 절세 계획 (KR_FOREIGN > 2천만 시)
    # other_financial_income은 Phase 2f 자동산출(직전 완료년도 gross 배당·이자) — 수동입력 대체.
    split_sale_plan = None
    if tax_enabled and kr_foreign_unrealized_gain > 20_000_000:
        from modules.tax.split_sale_planner import compute_split_sale_plan, recurring_financial_income
        split_sale_plan = compute_split_sale_plan(
            kr_foreign_gain        = kr_foreign_unrealized_gain,
            earned_income          = user_settings.get("earned_income", 0),
            other_financial_income = recurring_financial_income(financial_income_by_year),
        )

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
        'tax_enabled':    tax_enabled,
        'account_type':   account_type if tax_enabled else None,
        'used_synthetic': _prep_meta.get('used_synthetic', False),
        'synthetic_info': _prep_meta.get('synthetic_info', {}),
        'backfilled':     _prep_meta.get('backfilled', []),
        'warnings':       _prep_meta.get('warnings', []),
        'data_confidence': _prep_meta.get('data_confidence', 'actual'),
        'kr_foreign_unrealized_gain': round(kr_foreign_unrealized_gain),
        'split_sale_plan': split_sale_plan,
        'comprehensive_years': comprehensive_years,
        'financial_income_by_year': {int(y): round(v) for y, v in financial_income_by_year.items()},
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
