"""
retirement_logic.py
은퇴 설계 엔드포인트의 핵심 로직 — app.py / tasks.py 양쪽에서 import 가능한 독립 모듈.
"""

import datetime
from pathlib import Path
from dateutil.relativedelta import relativedelta

PRICE_DB_PATH = Path(__file__).parent / "data" / "price_cache" / "price_daily.db"

_portfolio_engine = None


def _get_portfolio_engine():
    global _portfolio_engine
    if _portfolio_engine is None:
        from modules.portfolio_engine import PortfolioEngine
        _portfolio_engine = PortfolioEngine()
    return _portfolio_engine


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


# 멀티계좌 입력 정규화·검증·결과 헬퍼는 공통 모듈에서 공유(투자계산기·백테스트와 동일, G5).
from modules.multi_account_common import (
    normalize_multi_accounts as _normalize_multi_accounts,
    validate_initial_capital_limits as _validate_initial_capital_limits,
    build_savings_summary as _build_savings_summary,
)


def _run_multi_account_retirement_logic(body: dict, progress_callback=None) -> dict:
    """은퇴 적립단계 멀티계좌 (G5-B) — 롤링 멀티계좌 적립.

    투자계산기 멀티계좌(_run_multi_account_calculator_logic)와 동일 엔진(MultiAccountAnalyzer).
    차이: years=accumulation_years, 데이터 준비=prepare_scenario_data(은퇴 관례).

    ⚠️ 인출투영(생존율)은 G5-C로 연기 — 단일경로(run_retirement_logic)는 RetirementPlanner로
    인출까지 하지만, 멀티계좌 인출(계좌별 디큐뮬레이션+연금소득세)은 G5-C가 구현한다.
    그 사이 멀티 적립 결과는 인출 필드를 pending(None)으로 두고 반환한다.
    """
    from modules.retirement.multi_account_analyzer import MultiAccountAnalyzer
    from modules.tax.account_tax import DistributionPolicy
    from modules.data_preparation import prepare_scenario_data

    portfolio_engine = _get_portfolio_engine()
    accounts         = _normalize_multi_accounts(body)
    years            = int(body['accumulation_years'])
    dividend_mode    = body.get('dividend_mode', 'reinvest')
    tax_enabled      = bool(body.get('tax_enabled', False))
    user_settings    = body.get('user_settings', {})
    gain_harvesting  = bool(body.get('gain_harvesting', False))

    # G2/G3/G4: 자금이동 정책·풍차·금종세·세액공제 재투자 (없으면 G1 동작 그대로).
    distribution_policy = DistributionPolicy.from_dict(body.get('distribution_policy'))
    manual_comprehensive_years = set(
        int(y) for y in (body.get('manual_comprehensive_years') or [])
    )
    reinvest_tax_credit = bool(body.get('reinvest_tax_credit', False))
    has_pension = any(a['type'] in ('연금저축', 'IRP') for a in accounts)
    transfers_enabled = (
        distribution_policy is not None
        or any(a.get('isa_renewal') for a in accounts)
        or (tax_enabled and has_pension)
    )

    all_tickers: list[str] = []
    for account in accounts:
        account['gain_harvesting'] = gain_harvesting and account['type'] == '위탁'
        for ticker in account['tickers']:
            if ticker['code'] not in all_tickers:
                all_tickers.append(ticker['code'])

    usdkrw_start = portfolio_engine.loader.USD_KRW_START
    data_end     = datetime.date.today().strftime('%Y-%m-%d')
    for ticker in all_tickers:
        try:
            portfolio_engine.loader.get_price(ticker, usdkrw_start, data_end)
        except Exception as e:
            print(f"[retirement] {ticker} 데이터 로드 오류: {e}")

    use_synthetic = bool(body.get('use_synthetic', False))
    prep = prepare_scenario_data(
        tickers          = all_tickers,
        required_years   = years,
        data_end         = data_end,
        step_months      = 3,
        allow_backfill   = True,
        allow_synthetic  = use_synthetic,
        purpose          = "retirement_multi_account",
        price_db_path    = PRICE_DB_PATH,
    )
    data_start     = prep["effective_start"]
    synthetic_info = prep.get("synthetic_info", {})
    backfilled     = prep.get("backfilled", [])

    if not use_synthetic:
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

    import json as _json
    import statistics as _stats
    tax_engine = None
    if tax_enabled:
        from modules.tax.base_tax import TaxEngine
        from modules.tax.account_tax import (
            check_contribution_limits,
            validate_account_portfolio,
            validate_isa_contribution,
        )
        tax_engine = TaxEngine(user_settings)
        # 초기자본 연한도 하드체크(전 경우) — 초기자본은 라우팅 대상 아님(실제 입금).
        _init_errors = _validate_initial_capital_limits(accounts)
        if _init_errors:
            raise ValueError(_json.dumps({
                'error': 'initial_capital_limit',
                'violations': _init_errors,
            }, ensure_ascii=False))
        for idx, account in enumerate(accounts):
            account_type   = account['type']
            ticker_codes   = [t['code'] for t in account['tickers']]
            target_weights = {t['code']: t['weight'] for t in account['tickers']}
            if account_type != '위탁':
                _check = validate_account_portfolio(account_type, ticker_codes, target_weights, tax_engine)
                if not _check['valid']:
                    raise ValueError(_json.dumps({
                        'error': 'account_restrictions',
                        'violations': [f"계좌 {idx + 1}: {v}" for v in _check['violations']],
                        'disclaimer': _check.get('disclaimer'),
                    }, ensure_ascii=False))
            # transfers ON(G2)이면 ISA 연한도 초과분을 엔진이 분배정책대로 라우팅 → 하드거부 스킵.
            if account_type == 'ISA' and not transfers_enabled:
                _isa_errors = validate_isa_contribution(
                    account['initial_capital'], account['monthly_contribution'],
                )
                if _isa_errors:
                    raise ValueError(_json.dumps({
                        'error': 'isa_contribution_limit',
                        'violations': [f"계좌 {idx + 1}: {v}" for v in _isa_errors],
                    }, ensure_ascii=False))
    else:
        from modules.tax.account_tax import check_contribution_limits

    # transfers ON(G2)이면 ISA 1억 한도·초과 라우팅을 엔진(tracker)이 동적 처리.
    # 정적 contribution_end_months cap은 G1(transfers OFF)에서만 적용(BUG-4).
    isa_cap_accounts = []
    _ISA_TOTAL_LIMIT = 100_000_000
    for idx, account in enumerate(accounts):
        if account['type'] != 'ISA' or transfers_enabled:
            continue
        planned_total = account['initial_capital'] + account['monthly_contribution'] * 12 * years
        if planned_total > _ISA_TOTAL_LIMIT:
            remaining = max(0.0, _ISA_TOTAL_LIMIT - account['initial_capital'])
            stop_months = (
                int(remaining / account['monthly_contribution'])
                if account['monthly_contribution'] > 0 else years * 12
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
        {'type': a['type'], 'monthly_contribution': a['monthly_contribution']}
        for a in accounts
    ])

    analyzer = MultiAccountAnalyzer(
        portfolio_engine           = portfolio_engine,
        accounts                   = accounts,
        data_start                 = data_start,
        data_end                   = data_end,
        accumulation_years         = years,
        dividend_mode              = dividend_mode,
        step_months                = 3,
        tax_enabled                = tax_enabled,
        user_settings              = user_settings,
        progress_callback          = progress_callback,
        use_synthetic              = use_synthetic,
        div_start                  = div_start,
        transfers_enabled          = transfers_enabled,
        distribution_policy        = distribution_policy,
        manual_comprehensive_years = manual_comprehensive_years,
        reinvest_tax_credit        = reinvest_tax_credit,
        apply_final_liquidation    = False,  # 은퇴: 절대 일괄청산 금지 → 무청산 인계(인출단계서 과세).
    )
    result = analyzer.run()
    distribution = result['combined']['distribution']

    if div_start:
        distribution['div_data_start']    = div_start
        distribution['div_cases_count']   = len(result['cases'])
    else:
        distribution['no_dividend'] = True

    # 적립 요약 (RetirementPlanner._summarize_accumulation와 동일 키 — 인출투영 인계용).
    accumulation_summary = {
        'end_value': {p: distribution['end_value'][p] for p in ('p10', 'p25', 'p50', 'p75', 'p90')},
        'cagr':      {p: distribution['cagr'][p] for p in ('p10', 'p50', 'p90')},
        'mdd':       {'p50': distribution['mdd']['p50']},
        'sharpe':    {'p50': distribution['sharpe']['p50']},
        'dividend_cagr': {'p50': distribution['dividend_cagr']['p50']},
    }

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
            'comprehensive_years':     c.get('comprehensive_years', []),
            'annual_deduction_credit': round(c.get('annual_deduction_credit', 0)),
            'pension_transfer_credit': round(c.get('pension_transfer_credit', 0)),
            'transfer_count':          len(c.get('transfer_log', []) or []),
        }
        for c in result['cases']
    ]

    if len(isa_cap_accounts) == 1:
        isa_cap_info = isa_cap_accounts[0]
    elif isa_cap_accounts:
        isa_cap_info = {'capped': True, 'accounts': isa_cap_accounts}
    else:
        isa_cap_info = None

    # G2/G3/G4 대표 요약 — 종료값 중앙값 케이스 기준(transfers OFF면 enabled=False).
    g2_summary = {'enabled': transfers_enabled}
    if transfers_enabled and result['cases']:
        rep = sorted(result['cases'], key=lambda c: c['end_value'])[len(result['cases']) // 2]
        g2_summary.update({
            'representative_run_id':   rep['run_id'],
            'comprehensive_years':     rep.get('comprehensive_years', []),
            'annual_deduction_credit': round(rep.get('annual_deduction_credit', 0)),
            'pension_transfer_credit': round(rep.get('pension_transfer_credit', 0)),
            'transfer_log':            rep.get('transfer_log', []),
        })

    savings_summary = _build_savings_summary(result.get('savings') or {})

    # 분할매도 패널 (위탁 + KR_FOREIGN 청산이익 중앙값 > 2천만) — 단일경로와 동일 로직.
    split_sale_plan = None
    comprehensive_flag = any(c.get('comprehensive_years') for c in result['cases'])
    if any(a.get('type') == '위탁' for a in accounts):
        _krf = [c.get('kr_foreign_unrealized_gain', 0.0) or 0.0 for c in result['cases']]
        _krf = [g for g in _krf if g > 0]
        if _krf and _stats.median(_krf) > 20_000_000:
            from modules.tax.split_sale_planner import (
                compute_split_sale_plan, recurring_financial_income,
            )
            _fin_years = next(
                (c.get('financial_income_by_year') for c in result['cases']
                 if c.get('financial_income_by_year')), {},
            )
            split_sale_plan = compute_split_sale_plan(
                kr_foreign_gain        = _stats.median(_krf),
                earned_income          = user_settings.get('earned_income', 0),
                other_financial_income = recurring_financial_income(_fin_years),
            )

    # ── G5-C C3: 가구 인출 분석 (생존율) ──────────────────────────────
    # 적립 분포 11분위 샘플 → 계좌별 동일분위 시작값 → 가구 디큐뮬레이션 롤링 → 합성 생존율.
    from modules.retirement.multi_account_withdrawal import analyze_household_samples
    monthly_withdrawal   = float(body.get('monthly_withdrawal', 0) or 0)
    withdrawal_years     = int(body.get('withdrawal_years', 0) or 0)
    wd_inflation         = float(body.get('inflation', 0.02))
    target_percentile    = float(body.get('target_percentile', 0.90))
    withdrawal_start_age = int(user_settings.get('age', 40)) + years

    wd_report = None
    if monthly_withdrawal > 0 and withdrawal_years > 0 and result['cases']:
        per_account_values = []
        account_specs = []
        for idx, account in enumerate(accounts):
            vals = []
            for c in result['cases']:
                for a in c.get('accounts', []):
                    if a['account_id'] == idx:
                        vals.append(a['end_value'])
                        break
            per_account_values.append(vals or [0.0])
            account_specs.append({
                'account_id':     idx,
                'type':           account['type'],
                'target_weights': {t['code']: t['weight'] for t in account['tickers']},
                'cost_basis':     (account['initial_capital']
                                   + account['monthly_contribution'] * 12 * years)
                                  if tax_enabled else None,
                'rebal_mode':     account.get('rebal_mode', 'none'),
                'band_width':     float(account.get('band_width', 0.05)),
            })
        # 인출 투영용 범위 — 적립 prep과 별도로 인출기간 기준 준비(GAP-RET-KRDATA).
        wd_prep = prepare_scenario_data(
            tickers          = all_tickers,
            required_years   = withdrawal_years,
            data_end         = data_end,
            step_months      = 6,
            allow_backfill   = True,
            allow_synthetic  = use_synthetic,
            purpose          = "retirement_withdrawal",
            price_db_path    = PRICE_DB_PATH,
        )
        wd_data_start = min(data_start, wd_prep["effective_start"])
        wd_price_data, wd_dates = portfolio_engine.price_loader.load(
            all_tickers, wd_data_start, data_end,
        )
        wd_report = analyze_household_samples(
            account_specs, per_account_values,
            wd_price_data, wd_dates, wd_data_start, data_end,
            withdrawal_years, monthly_withdrawal,
            tax_engine=tax_engine if tax_enabled else None,
            withdrawal_start_age=withdrawal_start_age,
            inflation=wd_inflation, dividend_mode=dividend_mode,
            step_months=6, target_percentile=target_percentile,
        )

    return {
        'multi_account': {
            'enabled': True,
            'accounts': [
                {
                    'account_id':   a['account_id'],
                    'type':         a['type'],
                    'distribution': a['distribution'],
                }
                for a in result['accounts']
            ],
            'contribution_warnings': contribution_warnings,
        },
        'cases':                cases_summary,
        'acc_cases_count':      len(cases_summary),
        'acc_values':           [round(c['end_value']) for c in result['cases']],
        'distribution':         distribution,
        'accumulation_summary': accumulation_summary,
        'savings':              savings_summary,
        'g2':                   g2_summary,
        'split_sale_plan':      split_sale_plan,
        'comprehensive_flag':   comprehensive_flag,
        'isa_cap_info':         isa_cap_info,
        'data_start':           data_start,
        'synthetic_info':       synthetic_info,
        'backfilled':           backfilled,
        'tax_enabled':          tax_enabled,
        # ── G5-C C3: 가구 인출 분석 (생존율) ────────────────────────────
        'withdrawal_pending':   wd_report is None,
        'sample_results':       wd_report['sample_results'] if wd_report else [],
        'combined_summary':     wd_report['combined_summary'] if wd_report else None,
        'message':              wd_report['message'] if wd_report else {
            'text': "월 인출액·인출 기간을 입력하면 가구 인출 생존율을 분석합니다.",
            'survival_rate': None,
            'is_safe': None,
        },
    }


def run_retirement_logic(body: dict, progress_callback=None) -> dict:
    # 멀티계좌(accounts 2개 이상) → 적립단계 멀티경로(인출투영은 G5-C). 단일계좌 → 기존 경로.
    if len(body.get('accounts') or []) > 1:
        return _run_multi_account_retirement_logic(body, progress_callback)

    import time
    from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
    from modules.retirement.retirement_planner import RetirementPlanner
    from modules.data_preparation import prepare_scenario_data

    portfolio_engine = _get_portfolio_engine()

    tickers_input  = body['tickers']
    ticker_codes   = [t['code'] for t in tickers_input]
    target_weights = {t['code']: t['weight'] for t in tickers_input}

    initial_capital      = float(body['initial_capital'])
    monthly_contribution = float(body['monthly_contribution'])
    accumulation_years   = int(body['accumulation_years'])
    dividend_mode        = body.get('dividend_mode', 'reinvest')
    rebal_mode           = body.get('rebal_mode', 'none')
    monthly_withdrawal   = float(body['monthly_withdrawal'])
    withdrawal_years     = int(body['withdrawal_years'])
    inflation            = float(body.get('inflation', 0.02))
    target_percentile    = float(body.get('target_percentile', 0.90))

    strategy_factory = _make_strategy_factory(target_weights, rebal_mode)
    data_end         = datetime.date.today().strftime('%Y-%m-%d')

    # 신규 미조회 종목은 BackfillEngine 실행 전 실데이터 확보 필요
    # (BackfillEngine은 실데이터가 이미 있는 ETF의 상장 이전 구간만 백필함)
    _usdkrw_start = portfolio_engine.loader.USD_KRW_START
    for _ticker in ticker_codes:
        try:
            portfolio_engine.loader.get_price(_ticker, _usdkrw_start, data_end)
        except Exception as _e:
            print(f"[retirement] {_ticker} 데이터 로드 오류: {_e}")

    use_synthetic = bool(body.get('use_synthetic', False))
    prep = prepare_scenario_data(
        tickers          = ticker_codes,
        required_years   = accumulation_years,
        data_end         = data_end,
        step_months      = 3,
        allow_backfill   = True,
        allow_synthetic  = use_synthetic,
        purpose          = "retirement",
        price_db_path    = PRICE_DB_PATH,
    )

    data_start     = prep["effective_start"]
    synthetic_info = prep["synthetic_info"]
    backfilled     = prep["backfilled"]

    # 인출 투영용 범위 — 적립(years) 기준 prep과 별도로 인출기간 기준으로 준비.
    # (GAP-RET-KRDATA: 인출 N년 윈도우 요구가 데이터 준비에 전달되지 않아 윈도우 0개 하드에러.)
    # 적립 prep을 늘리지 않는 이유: 적립 케이스 수가 범위에 비례해 폭증(성능).
    wd_data_start = data_start
    if monthly_withdrawal > 0 and withdrawal_years > 0:
        wd_prep = prepare_scenario_data(
            tickers          = ticker_codes,
            required_years   = withdrawal_years,
            data_end         = data_end,
            step_months      = 6,
            allow_backfill   = True,
            allow_synthetic  = use_synthetic,
            purpose          = "retirement_withdrawal",
            price_db_path    = PRICE_DB_PATH,
        )
        wd_data_start = min(data_start, wd_prep["effective_start"])

    div_starts = [_get_dividend_start(portfolio_engine, t) for t in ticker_codes]
    div_starts = [d for d in div_starts if d]
    div_start  = max(div_starts) if div_starts else None

    tax_enabled        = body.get('tax_enabled', False)
    account_type       = body.get('account_type', '위탁')
    user_settings      = body.get('user_settings', {})
    isa_renewal        = body.get('isa_renewal', False)
    gain_harvesting    = body.get('gain_harvesting', False)
    pension_start_age  = int(body.get('pension_start_age', 65))
    # pension_start_age를 user_settings에 주입 → TaxEngine.pension_age 반영
    if pension_start_age and account_type in ('연금저축', 'IRP'):
        user_settings = dict(user_settings)
        user_settings['pension_age'] = pension_start_age
    ret_tax_engine  = None
    if tax_enabled:
        from modules.tax.base_tax import TaxEngine
        ret_tax_engine = TaxEngine(user_settings)

    # ── 계좌 유형 규제 검증 ─────────────────────────────────────────
    import json as _json
    if tax_enabled and account_type != '위탁':
        from modules.tax.account_tax import validate_account_portfolio
        _te = ret_tax_engine or __import__('modules.tax.base_tax', fromlist=['TaxEngine']).TaxEngine(user_settings)
        _check = validate_account_portfolio(account_type, ticker_codes, target_weights, _te)
        if not _check['valid']:
            raise ValueError(_json.dumps({
                'error': 'account_restrictions',
                'violations': _check['violations'],
                'disclaimer': _check.get('disclaimer'),
            }, ensure_ascii=False))

    if tax_enabled and account_type == 'ISA':
        if isa_renewal:
            raise ValueError(_json.dumps({
                'error': 'isa_windmill_disabled',
                'violations': [
                    "ISA 풍차돌리기를 지원하지 않습니다. "
                    "ISA 만기 후 수령액은 연간 납입 한도(2,000만원)를 대부분 초과하여 "
                    "재납입이 불가합니다. ISA 계좌를 일반 모드로 선택하거나 위탁 계좌를 이용하세요."
                ],
            }, ensure_ascii=False))

        from modules.tax.account_tax import validate_isa_contribution
        _isa_errors = validate_isa_contribution(initial_capital, monthly_contribution)
        if _isa_errors:
            raise ValueError(_json.dumps({
                'error': 'isa_contribution_limit',
                'violations': _isa_errors,
            }, ensure_ascii=False))

        _ISA_TOTAL_LIMIT = 100_000_000
        _planned_total = initial_capital + monthly_contribution * 12 * accumulation_years
        _isa_cap_info = None
        if _planned_total > _ISA_TOTAL_LIMIT:
            _remaining = max(0.0, _ISA_TOTAL_LIMIT - initial_capital)
            _stop_months = int(_remaining / monthly_contribution) if monthly_contribution > 0 else accumulation_years * 12
            _isa_cap_info = {
                'capped': True,
                'original_total': round(_planned_total),
                'capped_total': _ISA_TOTAL_LIMIT,
                'original_monthly': round(monthly_contribution),
                'stop_months': _stop_months,
                'stop_years': _stop_months // 12,
                'stop_months_remainder': _stop_months % 12,
            }
            # monthly_contribution 변경 안 함 — AccumulationAnalyzer에 contribution_end_months로 전달
    else:
        _isa_cap_info = None

    # AccumulationAnalyzer 진행률 0→50% 스케일링
    _acc_start = time.time()
    def acc_progress(current, total, elapsed):
        if progress_callback:
            scaled_pct = current / total * 50  # 0~50%
            progress_callback(
                current=round(scaled_pct),
                total=100,
                elapsed=elapsed,
            )

    acc_analyzer = AccumulationAnalyzer(
        portfolio_engine        = portfolio_engine,
        tickers                 = ticker_codes,
        strategy_factory        = strategy_factory,
        data_start              = data_start,
        data_end                = data_end,
        accumulation_years      = accumulation_years,
        monthly_contribution    = monthly_contribution,
        initial_capital         = initial_capital,
        dividend_mode           = dividend_mode,
        step_months             = 3,
        verbose                 = False,
        div_start               = div_start,
        tax_engine              = ret_tax_engine,
        account_type            = account_type,
        isa_renewal             = isa_renewal,
        gain_harvesting         = gain_harvesting,
        progress_callback       = acc_progress,
        use_synthetic           = use_synthetic,
        synthetic_params        = synthetic_info if use_synthetic else {},
        contribution_end_months = _isa_cap_info['stop_months'] if _isa_cap_info else None,
        apply_final_liquidation = False,  # 은퇴: 절대 일괄청산 금지 → 무청산 인계(인출단계서 과세).
    )
    acc_result = acc_analyzer.run()

    # 인출 분석 전 50% 알림
    if progress_callback:
        progress_callback(current=50, total=100, elapsed=time.time() - _acc_start)

    # 인출 과세 배선 (G5-C C1): 은퇴는 적립 무청산 인계 → 인출하면서 과세해야 함.
    # 기존엔 wd_config에 tax_engine이 없어 인출이 면세였음(적립끝 청산세가 유일 세금이던 모델).
    # 무청산 전환 후 인출 과세를 안 켜면 세금 0이 되므로 여기서 켠다.
    # cost_basis = 적립 총납입(결정론) → 위탁 인출 매도세가 적립차익까지 과세.
    _cost_basis = initial_capital + monthly_contribution * accumulation_years * 12
    planner = RetirementPlanner(
        acc_result         = acc_result,
        wd_config          = {
            "portfolio_engine":   portfolio_engine,
            "tickers":            ticker_codes,
            "strategy_factory":   strategy_factory,
            "data_start":         wd_data_start,  # 인출기간 기준 범위(GAP-RET-KRDATA)
            "data_end":           data_end,
            "withdrawal_years":   withdrawal_years,
            "dividend_mode":      dividend_mode,
            "step_months":        6,
            "tax_engine":         ret_tax_engine,
            "account_type":       account_type if tax_enabled else "위탁",
            "user_settings":      user_settings if tax_enabled else {},
            "current_age":        int(user_settings.get("age", 40)) if tax_enabled else 40,
            "accumulation_years": accumulation_years,
            "gain_harvesting":    gain_harvesting if tax_enabled else False,
        },
        monthly_withdrawal  = monthly_withdrawal,
        withdrawal_years    = withdrawal_years,
        inflation           = inflation,
        verbose             = False,
        progress_callback   = progress_callback,
        start_time          = _acc_start,
        cost_basis          = _cost_basis if tax_enabled else None,
    )
    report = planner.run(target_percentile=target_percentile)

    # 완료 100% 알림
    if progress_callback:
        progress_callback(current=100, total=100, elapsed=time.time() - _acc_start)

    # Phase 2f: 금융소득 종합과세 분할매도 패널 (적립 종료 시 위탁 KR_FOREIGN 청산이익 중앙값)
    _split_sale_plan = None
    _comprehensive_flag = False
    if tax_enabled and account_type == '위탁':
        import statistics as _stats
        _krf = [c.get('kr_foreign_unrealized_gain', 0.0) or 0.0 for c in acc_result["cases"]]
        _krf = [g for g in _krf if g > 0]
        _comprehensive_flag = any(c.get('comprehensive_years') for c in acc_result["cases"])
        if _krf:
            _median_krf = _stats.median(_krf)
            if _median_krf > 20_000_000:
                from modules.tax.split_sale_planner import (
                    compute_split_sale_plan, recurring_financial_income,
                )
                _fin_years = next(
                    (c.get('financial_income_by_year') for c in acc_result["cases"]
                     if c.get('financial_income_by_year')), {},
                )
                _split_sale_plan = compute_split_sale_plan(
                    kr_foreign_gain        = _median_krf,
                    earned_income          = user_settings.get('earned_income', 0),
                    other_financial_income = recurring_financial_income(_fin_years),
                )

    return {
        "split_sale_plan":       _split_sale_plan,
        "comprehensive_flag":    _comprehensive_flag,
        "accumulation_summary": report["accumulation_summary"],
        "sample_results": [
            {
                "percentile":      s["percentile"],
                "initial_capital": round(s["initial_capital"]),
                "success_rate":    round(s["success_rate"], 4),
                "end_value_p50":   round(s["end_value_p50"]),
                "wd_end_values":   s.get("wd_end_values", []),
            }
            for s in report["sample_results"]
        ],
        "combined_summary":  report["combined_summary"],
        "message":           report["message"],
        "acc_cases_count":   len(acc_result["cases"]),
        "acc_n_real":        acc_result.get("n_real"),
        "acc_n_synthetic":   acc_result.get("n_synthetic"),
        # 인출 투영 윈도우 구성(실측/가상) — 가상 보충 표시용(GAP-RET-KRDATA).
        "wd_n_real":      report["sample_results"][0]["wd_result"]["n_real"] if report["sample_results"] else None,
        "wd_n_synthetic": report["sample_results"][0]["wd_result"]["n_synthetic"] if report["sample_results"] else None,
        "acc_values":        [round(c["end_value"]) for c in acc_result["cases"]],
        "wd_values": [
            v
            for s in report["sample_results"]
            for v in s.get("wd_end_values", [])
        ],
        "data_start":     data_start,
        "synthetic_info": synthetic_info,
        "backfilled":     backfilled,
        "tax_enabled":    tax_enabled,
        "account_type":   account_type if tax_enabled else None,
    }


def _run_multi_account_withdrawal_logic(body: dict, progress_callback=None) -> dict:
    """은퇴 인출기(standalone) 멀티계좌 + 세금 (G5-D).

    sim(적립→인출)의 가구 디큐뮬레이션 엔진(analyze_household_withdrawal)을 인출기 탭에서도
    직접 호출한다. 적립 분포가 없으므로(인출기는 시작 목돈을 사용자가 입력) analyze_household_samples
    대신 단일 시작값으로 analyze_household_withdrawal를 부른다.
    """
    from modules.retirement.multi_account_withdrawal import analyze_household_withdrawal
    from modules.data_preparation import prepare_scenario_data

    portfolio_engine = _get_portfolio_engine()
    accounts         = _normalize_multi_accounts(body)

    withdrawal_years   = int(body['withdrawal_years'])
    monthly_withdrawal = float(body['monthly_withdrawal'])
    inflation          = float(body.get('inflation', 0.02))
    dividend_mode      = body.get('dividend_mode', 'reinvest')
    tax_enabled        = bool(body.get('tax_enabled', False))
    user_settings      = body.get('user_settings', {})
    pension_start_age  = int(body.get('pension_start_age', 65))

    all_tickers: list[str] = []
    for account in accounts:
        for ticker in account['tickers']:
            if ticker['code'] not in all_tickers:
                all_tickers.append(ticker['code'])

    data_end     = datetime.date.today().strftime('%Y-%m-%d')
    usdkrw_start = portfolio_engine.loader.USD_KRW_START
    for ticker in all_tickers:
        try:
            portfolio_engine.loader.get_price(ticker, usdkrw_start, data_end)
        except Exception as e:
            print(f"[withdrawal] {ticker} 데이터 로드 오류: {e}")

    prep = prepare_scenario_data(
        tickers          = all_tickers,
        required_years   = withdrawal_years,
        data_end         = data_end,
        step_months      = 3,
        allow_backfill   = True,
        allow_synthetic  = True,
        purpose          = "withdrawal",
        price_db_path    = PRICE_DB_PATH,
    )
    data_start = prep["effective_start"]

    tax_engine = None
    if tax_enabled:
        from modules.tax.base_tax import TaxEngine
        tax_engine = TaxEngine(user_settings)

    # 계좌별 시작 목돈 = initial_capital. 취득가 = 목돈 − 미실현차익(위탁·세금ON시 양도세 기준).
    account_specs = []
    for idx, account in enumerate(accounts):
        value      = account['initial_capital']
        unrealized = float(account.get('unrealized_gain', 0) or 0)
        if tax_enabled and account['type'] == '위탁':
            cost_basis = max(0.0, value - unrealized)
        else:
            cost_basis = None
        account_specs.append({
            'account_id':     idx,
            'type':           account['type'],
            'value':          value,
            'cost_basis':     cost_basis,
            'target_weights': {t['code']: t['weight'] for t in account['tickers']},
            'rebal_mode':     account.get('rebal_mode', 'none'),
            'band_width':     float(account.get('band_width', 0.05)),
        })

    wd_price_data, wd_dates = portfolio_engine.price_loader.load(
        all_tickers, data_start, data_end,
    )

    report = analyze_household_withdrawal(
        account_specs, wd_price_data, wd_dates, data_start, data_end,
        withdrawal_years, monthly_withdrawal,
        tax_engine=tax_engine, withdrawal_start_age=pension_start_age,
        inflation=inflation, dividend_mode=dividend_mode, step_months=3,
    )

    return {
        'multi_account': {
            'enabled': True,
            'accounts': [
                {
                    'account_id':   a['account_id'],
                    'type':         a['type'],
                    'distribution': {'end_value': a['end_value']},
                }
                for a in report['per_account']
            ],
        },
        'survival_rate': report['survival_rate'],
        'combined_summary': {
            'survival_rate':      report['survival_rate'],
            'combined_end_value': report['combined_end_value'],
        },
        'median_pension_tax': report['median_pension_tax'],
        # 절세액 3종(위탁가정·실제·절세) — 인출 페이즈(절세액 P3). 세금 OFF면 None.
        'savings':            _build_savings_summary(report.get('savings') or {}),
        'n_real':             report['n_real'],
        'n_synthetic':        report['n_synthetic'],
        'data_start':         data_start,
        'tax_enabled':        tax_enabled,
    }


def run_withdrawal_logic(body: dict, progress_callback=None) -> dict:
    # 멀티계좌(2개 이상) → 가구 디큐뮬레이션 엔진. 단일계좌 → 기존 WithdrawalAnalyzer 경로.
    if len(body.get('accounts') or []) > 1:
        return _run_multi_account_withdrawal_logic(body, progress_callback)

    from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer
    from modules.data_preparation import prepare_scenario_data

    portfolio_engine = _get_portfolio_engine()

    tickers_input  = body['tickers']
    ticker_codes   = [t['code'] for t in tickers_input]
    target_weights = {t['code']: t['weight'] for t in tickers_input}

    initial_capital    = float(body['initial_capital'])
    monthly_withdrawal = float(body['monthly_withdrawal'])
    withdrawal_years   = int(body['withdrawal_years'])
    inflation          = float(body.get('inflation', 0.02))
    dividend_mode      = body.get('dividend_mode', 'reinvest')
    rebal_mode         = body.get('rebal_mode', 'none')

    strategy_factory = _make_strategy_factory(target_weights, rebal_mode)
    data_end         = datetime.date.today().strftime('%Y-%m-%d')

    prep = prepare_scenario_data(
        tickers          = ticker_codes,
        required_years   = withdrawal_years,
        data_end         = data_end,
        step_months      = 3,
        allow_backfill   = True,
        allow_synthetic  = True,
        purpose          = "withdrawal",
        price_db_path    = PRICE_DB_PATH,
    )

    data_start = prep["effective_start"]

    tax_enabled        = body.get('tax_enabled', False)
    account_type       = body.get('account_type', '위탁')
    user_settings      = body.get('user_settings', {})
    pension_start_age  = int(body.get('pension_start_age', 65))
    if pension_start_age and account_type in ('연금저축', 'IRP'):
        user_settings = dict(user_settings)
        user_settings['pension_age'] = pension_start_age
    acc_years     = int(body.get('accumulation_years', 0))
    ret_tax_engine = None
    if tax_enabled:
        from modules.tax.base_tax import TaxEngine
        ret_tax_engine = TaxEngine(user_settings)

    wd_analyzer = WithdrawalAnalyzer(
        portfolio_engine   = portfolio_engine,
        tickers            = ticker_codes,
        strategy_factory   = strategy_factory,
        data_start         = data_start,
        data_end           = data_end,
        withdrawal_years   = withdrawal_years,
        monthly_withdrawal = monthly_withdrawal,
        initial_capital    = initial_capital,
        inflation          = inflation,
        dividend_mode      = dividend_mode,
        step_months        = 3,
        verbose            = False,
        tax_engine         = ret_tax_engine,
        account_type       = account_type if tax_enabled else "위탁",
        current_age        = user_settings.get("age", 40) if tax_enabled else 40,
        accumulation_years = acc_years,
        user_settings      = user_settings if tax_enabled else {},
        gain_harvesting    = body.get("gain_harvesting", False) if tax_enabled else False,
        progress_callback  = progress_callback,
    )
    result = wd_analyzer.run()

    dist     = result['distribution']
    end_vals = [round(c['end_value']) for c in result['cases']]

    return {
        "survival_rate": round(result['success_rate'], 4),
        "combined_summary": {
            "survival_rate": round(result['success_rate'], 4),
            "combined_end_value": {
                "p10":  round(dist['end_value_ratio']['p10'] * initial_capital),
                "p25":  round(dist['end_value_ratio']['p25'] * initial_capital),
                "p50":  round(dist['end_value_ratio']['p50'] * initial_capital),
                "p75":  round(dist['end_value_ratio']['p75'] * initial_capital),
                "p90":  round(dist['end_value_ratio']['p90'] * initial_capital),
            },
        },
        "wd_values":        end_vals,
        "data_start":       data_start,
        "n_real":           result.get("n_real"),
        "n_synthetic":      result.get("n_synthetic"),
        "pension_tax_info": result.get("pension_tax_info"),
        "tax_enabled":      tax_enabled,
        "account_type":     account_type if tax_enabled else None,
    }
