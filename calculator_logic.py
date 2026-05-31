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


def _get_real_dividend_start(portfolio_engine, ticker: str):
    """실측 배당 최초일 = 실데이터(volume>0) 구간의 첫 배당.
    백필 주입 배당은 실데이터 시작 이전이므로 제외됨.
    """
    try:
        cur = portfolio_engine.loader.conn.execute(
            "SELECT MIN(ca.date) FROM corporate_actions ca "
            "WHERE ca.code=? AND ca.dividend > 0 AND ca.date >= "
            "(SELECT MIN(date) FROM price_daily WHERE code=? AND volume > 0)",
            (ticker, ticker)
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


def _normalize_multi_accounts(body: dict) -> list[dict]:
    accounts = []
    for idx, raw in enumerate(body.get('accounts') or []):
        tickers = raw.get('tickers') or []
        if not tickers:
            raise ValueError(f"계좌 {idx + 1}에 종목을 최소 1개 이상 추가해주세요.")

        normalized_tickers = []
        total_weight = 0.0
        for ticker in tickers:
            weight = float(ticker.get('weight', 0))
            total_weight += weight
            normalized_tickers.append({
                'code':   ticker['code'],
                'name':   ticker.get('name', ticker['code']),
                'badge':  ticker.get('badge', ''),
                'weight': weight,
            })
        if total_weight > 1.000001:
            raise ValueError(f"계좌 {idx + 1}의 비중 합계가 100%를 초과했습니다.")

        accounts.append({
            'type':                 raw.get('type', '위탁'),
            'initial_capital':      float(raw.get('initial_capital', 0) or 0),
            'monthly_contribution': float(raw.get('monthly_contribution', 0) or 0),
            'tickers':              normalized_tickers,
            'rebal_mode':           raw.get('rebal_mode') or body.get('rebal_mode', 'monthly'),
            'band_width':           float(raw.get('band_width', body.get('band_width', 0.05))),
            'dividend_mode':        raw.get('dividend_mode') or body.get('dividend_mode', 'reinvest'),
        })
    return accounts


def _run_multi_account_calculator_logic(body: dict, progress_callback=None) -> dict:
    from modules.retirement.multi_account_analyzer import MultiAccountAnalyzer

    portfolio_engine = _get_portfolio_engine()
    accounts         = _normalize_multi_accounts(body)
    years            = int(body['years'])
    dividend_mode    = body['dividend_mode']
    tax_enabled      = bool(body.get('tax_enabled', False))
    user_settings    = body.get('user_settings', {})
    gain_harvesting  = bool(body.get('gain_harvesting', False))

    all_tickers = []
    for account in accounts:
        account['gain_harvesting'] = gain_harvesting and account['type'] == '위탁'
        for ticker in account['tickers']:
            code = ticker['code']
            if code not in all_tickers:
                all_tickers.append(code)

    usdkrw_start = portfolio_engine.loader.USD_KRW_START
    today = datetime.date.today().strftime('%Y-%m-%d')
    for ticker in all_tickers:
        try:
            portfolio_engine.loader.get_price(ticker, usdkrw_start, today)
        except Exception as e:
            print(f"[calculator] {ticker} 데이터 로드 오류: {e}")

    price_starts = [_get_price_start(portfolio_engine, t) for t in all_tickers]
    price_starts = [d for d in price_starts if d]
    data_start = max([usdkrw_start] + price_starts) if price_starts else usdkrw_start
    data_end   = today

    use_synthetic = bool(body.get('use_synthetic', False))
    _prep_meta: dict = {}
    if use_synthetic:
        from modules.data_preparation import prepare_scenario_data
        _prep_meta = prepare_scenario_data(
            tickers          = all_tickers,
            required_years   = years,
            data_end         = data_end,
            allow_backfill   = True,
            allow_synthetic  = True,
            purpose          = "calculator_multi_account",
        )
        data_start = _prep_meta["effective_start"]
        if (_prep_meta.get("n_cases") or 0) == 0:
            actual_starts = [_get_price_start(portfolio_engine, t) for t in all_tickers]
            actual_starts = [d for d in actual_starts if d]
            oldest = min(actual_starts) if actual_starts else "알 수 없음"
            raise ValueError(
                f"가상 데이터 생성 불가: {all_tickers}의 실제 데이터가 너무 적습니다 "
                f"({oldest}부터 시작, 최소 1년 이상 필요). "
                f"더 긴 상장 역사를 가진 ETF를 사용하세요."
            )
    else:
        start_dt  = datetime.datetime.strptime(data_start, '%Y-%m-%d').date()
        max_years = (datetime.date.today() - start_dt).days // 365
        if years > max_years:
            raise ValueError(
                f"데이터 부족: {all_tickers}의 데이터는 {data_start}부터 있어서 "
                f"최대 {max_years}년 시뮬레이션이 가능합니다."
            )

    div_starts = [_get_dividend_start(portfolio_engine, t) for t in all_tickers]
    div_starts = [d for d in div_starts if d]
    div_start  = max(div_starts) if div_starts else None

    real_div_starts = [_get_real_dividend_start(portfolio_engine, t) for t in all_tickers]
    real_div_starts = [d for d in real_div_starts if d]
    div_real_start  = max(real_div_starts) if real_div_starts else None

    import json as _json
    tax_engine = None
    if tax_enabled:
        from modules.tax.base_tax import TaxEngine
        from modules.tax.account_tax import (
            check_contribution_limits,
            validate_account_portfolio,
            validate_isa_contribution,
        )
        tax_engine = TaxEngine(user_settings)
        for idx, account in enumerate(accounts):
            account_type = account['type']
            ticker_codes = [t['code'] for t in account['tickers']]
            target_weights = {t['code']: t['weight'] for t in account['tickers']}
            if account_type != '위탁':
                _check = validate_account_portfolio(account_type, ticker_codes, target_weights, tax_engine)
                if not _check['valid']:
                    raise ValueError(_json.dumps({
                        'error': 'account_restrictions',
                        'violations': [f"계좌 {idx + 1}: {v}" for v in _check['violations']],
                        'disclaimer': _check.get('disclaimer'),
                    }, ensure_ascii=False))

            if account_type == 'ISA':
                if body.get('isa_renewal', False):
                    raise ValueError(_json.dumps({
                        'error': 'isa_windmill_disabled',
                        'violations': [
                            "ISA 풍차돌리기는 다중 계좌 G2/G3의 자금이동 정책에서 다시 연결됩니다. "
                            "G1에서는 일반 ISA 계좌로 시뮬레이션하세요."
                        ],
                    }, ensure_ascii=False))
                _isa_errors = validate_isa_contribution(
                    account['initial_capital'],
                    account['monthly_contribution'],
                )
                if _isa_errors:
                    raise ValueError(_json.dumps({
                        'error': 'isa_contribution_limit',
                        'violations': [f"계좌 {idx + 1}: {v}" for v in _isa_errors],
                    }, ensure_ascii=False))
    else:
        from modules.tax.account_tax import check_contribution_limits

    isa_cap_accounts = []
    _ISA_TOTAL_LIMIT = 100_000_000
    for idx, account in enumerate(accounts):
        if account['type'] != 'ISA':
            continue
        planned_total = (
            account['initial_capital']
            + account['monthly_contribution'] * 12 * years
        )
        if planned_total > _ISA_TOTAL_LIMIT:
            remaining = max(0.0, _ISA_TOTAL_LIMIT - account['initial_capital'])
            stop_months = (
                int(remaining / account['monthly_contribution'])
                if account['monthly_contribution'] > 0
                else years * 12
            )
            account['contribution_end_months'] = stop_months
            isa_cap_accounts.append({
                'account_id': idx,
                'account_label': f"계좌 {idx + 1}",
                'capped': True,
                'original_total': round(planned_total),
                'capped_total': _ISA_TOTAL_LIMIT,
                'original_monthly': round(account['monthly_contribution']),
                'stop_months': stop_months,
                'stop_years': stop_months // 12,
                'stop_months_remainder': stop_months % 12,
            })

    contribution_warnings = check_contribution_limits([
        {
            'type': account['type'],
            'monthly_contribution': account['monthly_contribution'],
        }
        for account in accounts
    ])

    analyzer = MultiAccountAnalyzer(
        portfolio_engine      = portfolio_engine,
        accounts              = accounts,
        data_start            = data_start,
        data_end              = data_end,
        accumulation_years    = years,
        dividend_mode         = dividend_mode,
        step_months           = 3,
        tax_enabled           = tax_enabled,
        user_settings         = user_settings,
        progress_callback     = progress_callback,
        use_synthetic         = use_synthetic,
        div_start             = div_start,
    )
    result = analyzer.run()
    distribution = result['combined']['distribution']

    if div_start:
        distribution['div_data_start']     = div_start
        distribution['div_backfill_start'] = div_start
        distribution['div_real_start']     = div_real_start
        distribution['div_is_backfilled']  = bool(div_real_start and div_real_start > div_start)
        distribution['div_cases_count']    = len(result['cases'])
    else:
        distribution['no_dividend'] = True

    cases_summary = [
        {
            'run_id':    c['run_id'],
            'start':     c['start'],
            'end':       c['end'],
            'end_value': round(c['end_value']),
            'cagr':      round(c['cagr'], 4),
            'mdd':       round(c['mdd'], 4),
            'accounts': [
                {
                    'account_id': a['account_id'],
                    'type':       a['type'],
                    'end_value':  round(a['end_value']),
                    'tax_paid':   round(a.get('tax_paid', 0)),
                }
                for a in c.get('accounts', [])
            ],
        }
        for c in result['cases']
    ]

    if len(isa_cap_accounts) == 1:
        isa_cap_info = isa_cap_accounts[0]
    elif isa_cap_accounts:
        isa_cap_info = {'capped': True, 'accounts': isa_cap_accounts}
    else:
        isa_cap_info = None

    return {
        'cases':              cases_summary,
        'cases_count':        len(cases_summary),
        'distribution':       distribution,
        'multi_account':      {
            'enabled': True,
            'accounts': [
                {
                    'account_id': a['account_id'],
                    'type':       a['type'],
                    'distribution': a['distribution'],
                }
                for a in result['accounts']
            ],
            'contribution_warnings': contribution_warnings,
        },
        'isa_cap_info':       isa_cap_info,
        'used_synthetic':     _prep_meta.get('used_synthetic', False),
        'synthetic_info':     _prep_meta.get('synthetic_info', {}),
        'backfilled':         _prep_meta.get('backfilled', []),
        'warnings':           (_prep_meta.get('warnings', []) or []) + contribution_warnings,
    }


def run_calculator_logic(body: dict, progress_callback=None) -> dict:
    from modules.retirement.accumulation_analyzer import AccumulationAnalyzer

    if len(body.get('accounts') or []) > 1:
        return _run_multi_account_calculator_logic(body, progress_callback)

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
        # 가상 데이터 생성 시도했는데도 케이스 0 → 통계 계산 불가 (상장 너무 짧음)
        if (_prep_meta.get("n_cases") or 0) == 0:
            actual_starts = [_get_price_start(portfolio_engine, t) for t in ticker_codes]
            actual_starts = [d for d in actual_starts if d]
            oldest = min(actual_starts) if actual_starts else "알 수 없음"
            raise ValueError(
                f"가상 데이터 생성 불가: {ticker_codes}의 실제 데이터가 너무 적습니다 "
                f"({oldest}부터 시작, 최소 1년 이상 필요). "
                f"더 긴 상장 역사를 가진 ETF를 사용하세요."
            )
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

    real_div_starts = [_get_real_dividend_start(portfolio_engine, t) for t in ticker_codes]
    real_div_starts = [d for d in real_div_starts if d]
    div_real_start  = max(real_div_starts) if real_div_starts else None

    tax_enabled     = body.get('tax_enabled', False)
    account_type    = body.get('account_type', '위탁')
    user_settings   = body.get('user_settings', {})
    isa_renewal     = body.get('isa_renewal', False)
    gain_harvesting = body.get('gain_harvesting', False)
    tax_engine      = None
    if tax_enabled:
        from modules.tax.base_tax import TaxEngine
        tax_engine = TaxEngine(user_settings)

    # ── 계좌 유형 규제 검증 ─────────────────────────────────────────
    import json as _json
    if tax_enabled and account_type != '위탁':
        from modules.tax.account_tax import validate_account_portfolio
        _te = tax_engine or __import__('modules.tax.base_tax', fromlist=['TaxEngine']).TaxEngine(user_settings)
        _check = validate_account_portfolio(account_type, ticker_codes, target_weights, _te)
        if not _check['valid']:
            raise ValueError(_json.dumps({
                'error': 'account_restrictions',
                'violations': _check['violations'],
                'disclaimer': _check.get('disclaimer'),
            }, ensure_ascii=False))

    if tax_enabled and account_type == 'ISA':
        # ISA 풍차돌리기 차단 (만기 수령액이 연간 납입 한도 초과 → 재납입 불가)
        if isa_renewal:
            raise ValueError(_json.dumps({
                'error': 'isa_windmill_disabled',
                'violations': [
                    "ISA 풍차돌리기를 지원하지 않습니다. "
                    "ISA 만기 후 수령액은 연간 납입 한도(2,000만원)를 대부분 초과하여 "
                    "재납입이 불가합니다. ISA 계좌를 일반 모드로 선택하거나 위탁 계좌를 이용하세요."
                ],
            }, ensure_ascii=False))

        # ISA 납입 한도 하드 체크
        from modules.tax.account_tax import validate_isa_contribution
        _isa_errors = validate_isa_contribution(initial_capital, monthly_contrib)
        if _isa_errors:
            raise ValueError(_json.dumps({
                'error': 'isa_contribution_limit',
                'violations': _isa_errors,
            }, ensure_ascii=False))

        # ISA 총 납입 1억 캡
        _ISA_TOTAL_LIMIT = 100_000_000
        _planned_total = initial_capital + monthly_contrib * 12 * years
        _isa_cap_info = None
        if _planned_total > _ISA_TOTAL_LIMIT:
            _remaining = max(0.0, _ISA_TOTAL_LIMIT - initial_capital)
            _stop_months = int(_remaining / monthly_contrib) if monthly_contrib > 0 else years * 12
            _isa_cap_info = {
                'capped': True,
                'original_total': round(_planned_total),
                'capped_total': _ISA_TOTAL_LIMIT,
                'original_monthly': round(monthly_contrib),
                'stop_months': _stop_months,
                'stop_years': _stop_months // 12,
                'stop_months_remainder': _stop_months % 12,
            }
            # monthly_contrib 변경 안 함 — AccumulationAnalyzer에 contribution_end_months로 전달
    else:
        _isa_cap_info = None

    analyzer = AccumulationAnalyzer(
        portfolio_engine        = portfolio_engine,
        tickers                 = ticker_codes,
        strategy_factory        = strategy_factory,
        data_start              = data_start,
        data_end                = data_end,
        accumulation_years      = years,
        monthly_contribution    = monthly_contrib,
        initial_capital         = initial_capital,
        dividend_mode           = dividend_mode,
        step_months             = 3,
        verbose                 = False,
        div_start               = div_start,
        tax_engine              = tax_engine,
        account_type            = account_type,
        isa_renewal             = isa_renewal,
        gain_harvesting         = gain_harvesting,
        progress_callback       = progress_callback,
        use_synthetic           = use_synthetic,
        synthetic_params        = _prep_meta.get("synthetic_info", {}) if use_synthetic else {},
        contribution_end_months = _isa_cap_info['stop_months'] if _isa_cap_info else None,
    )

    result = analyzer.run()

    if div_start:
        result['distribution']['div_data_start']     = div_start
        result['distribution']['div_backfill_start'] = div_start
        result['distribution']['div_real_start']     = div_real_start
        result['distribution']['div_is_backfilled']  = bool(div_real_start and div_real_start > div_start)
        result['distribution']['div_cases_count']    = len(result['cases'])
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

    # Phase 2f: 금융소득 종합과세 분할매도 패널 (위탁 KR_FOREIGN 청산이익 case별 중앙값 기준)
    split_sale_plan = None
    comprehensive_flag = False
    if tax_enabled and account_type == '위탁':
        import statistics as _stats
        _krf = [c.get('kr_foreign_unrealized_gain', 0.0) or 0.0 for c in result['cases']]
        _krf = [g for g in _krf if g > 0]
        comprehensive_flag = any(c.get('comprehensive_years') for c in result['cases'])
        if _krf:
            _median_krf = _stats.median(_krf)
            if _median_krf > 20_000_000:
                from modules.tax.split_sale_planner import (
                    compute_split_sale_plan, recurring_financial_income,
                )
                _fin_years = next(
                    (c.get('financial_income_by_year') for c in result['cases']
                     if c.get('financial_income_by_year')), {},
                )
                split_sale_plan = compute_split_sale_plan(
                    kr_foreign_gain        = _median_krf,
                    earned_income          = user_settings.get('earned_income', 0),
                    other_financial_income = recurring_financial_income(_fin_years),
                )

    return {
        'cases':                    cases_summary,
        'cases_count':              len(cases_summary),
        'distribution':             result['distribution'],
        'distribution_early_cancel': result.get('distribution_early_cancel'),
        'isa_partial_cycle':        has_partial_isa,
        'isa_remainder_years':      years % 3 if has_partial_isa else 0,
        'isa_cap_info':             _isa_cap_info,
        'split_sale_plan':          split_sale_plan,
        'comprehensive_flag':       comprehensive_flag,
        'used_synthetic':           _prep_meta.get('used_synthetic', False),
        'synthetic_info':           _prep_meta.get('synthetic_info', {}),
        'backfilled':               _prep_meta.get('backfilled', []),
        'warnings':                 _prep_meta.get('warnings', []),
    }
