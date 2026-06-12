"""
dividend_logic.py
배당금 시나리오 엔드포인트의 핵심 로직 — app.py / tasks.py 양쪽에서 import 가능한 독립 모듈.
"""

_portfolio_engine = None


def _get_portfolio_engine():
    global _portfolio_engine
    if _portfolio_engine is None:
        from modules.portfolio_engine import PortfolioEngine
        _portfolio_engine = PortfolioEngine()
    return _portfolio_engine


def run_dividend_scenario_logic(body: dict, progress_callback=None, cancel_check=None) -> dict:
    from modules.dividend_simulator import DividendSimulator
    from modules.tax.base_tax import TaxEngine

    portfolio_engine = _get_portfolio_engine()

    # ── 멀티계좌 분기 (G5-E): accounts 2개 이상이면 멀티 시뮬레이터 ──
    if len(body.get('accounts') or []) > 1:
        return _run_multi_dividend_logic(body, progress_callback, cancel_check)

    tickers_input  = body['tickers']
    ticker_codes   = [t['code'] for t in tickers_input]
    target_weights = {t['code']: t['weight'] for t in tickers_input}

    # 프론트: account_type='none' → 세금 OFF, 그 외 → ON
    _raw_account = body.get('account_type', 'none')
    tax_enabled  = _raw_account not in ('none', '', None)

    # 프론트 account_type 값(general/isa/pension) → 백엔드 한글 값 매핑
    _ACCOUNT_MAP = {
        'general': '위탁',
        'isa':     'ISA',
        'pension': '연금저축',
        'irp':     'IRP',
        '위탁': '위탁', 'ISA': 'ISA', '연금저축': '연금저축', 'IRP': 'IRP',
    }
    account_type = _ACCOUNT_MAP.get(_raw_account, '위탁')

    user_settings = body.get('user_settings') or {
        'earned_income': body.get('earned_income', 50_000_000),
        'isa_type':      body.get('isa_type', 'general'),
        'age':           body.get('age', 40),
    }
    tax_engine = TaxEngine(user_settings) if tax_enabled else None

    # ── 계좌 유형 규제 검증 ─────────────────────────────────────────
    import json as _json
    if tax_enabled and account_type != '위탁':
        from modules.tax.account_tax import validate_account_portfolio
        _te = tax_engine or TaxEngine(user_settings)
        _check = validate_account_portfolio(account_type, ticker_codes, target_weights, _te)
        if not _check['valid']:
            raise ValueError(_json.dumps({
                'error': 'account_restrictions',
                'violations': _check['violations'],
                'disclaimer': _check.get('disclaimer'),
            }, ensure_ascii=False))

    if tax_enabled and account_type == 'ISA':
        from modules.tax.account_tax import validate_isa_contribution
        _seed_initial  = float((body.get('seed') or {}).get('center', 0))
        _monthly_val   = float((body.get('monthly') or {}).get('center', 0))
        _isa_errors = validate_isa_contribution(_seed_initial, _monthly_val)
        if _isa_errors:
            raise ValueError(_json.dumps({
                'error': 'isa_contribution_limit',
                'violations': _isa_errors,
            }, ensure_ascii=False))

    _isa_limit = 100_000_000 if (tax_enabled and account_type == 'ISA') else None

    sim = DividendSimulator(
        loader           = portfolio_engine.loader,
        tickers          = ticker_codes,
        weights          = target_weights,
        div_mode         = body.get('dividend_mode', 'reinvest'),
        step_months      = 3,
        rebal_mode       = body.get('rebal_mode', 'none'),
        band_width       = float(body.get('band_width', 0.05)),
        tax_engine       = tax_engine,
        account_type     = account_type,
        isa_total_limit  = _isa_limit,
    )

    seed_cfg    = body.get('seed',    {"center": 0,      "step": 0, "n": 0, "mode": "fixed"})
    monthly_cfg = body.get('monthly', {"center": 500000, "step": 0, "n": 0, "mode": "fixed"})
    years_cfg   = body.get('years',   {"center": 20,     "step": 0, "n": 0, "mode": "fixed"})

    response = sim.run_scenario(
        target_monthly_div = float(body['target_monthly_div']),
        probability        = float(body.get('probability', 0.50)),
        seed_cfg           = seed_cfg,
        monthly_cfg        = monthly_cfg,
        years_cfg          = years_cfg,
        progress_callback  = progress_callback,
        cancel_check       = cancel_check,
    )

    # ── 절세액 3종 (P4) — 대표 콤보(역산이면 solved 값) 기준 p50. 세금 ON일 때만. ──
    if tax_enabled and isinstance(response, dict) and not response.get('error'):
        try:
            _res = response.get('result') or {}
            _seed    = float(_res.get('solved_seed',    seed_cfg.get('center', 0)) or 0)
            _monthly = float(_res.get('solved_monthly', monthly_cfg.get('center', 0)) or 0)
            _years   = int(_res.get('solved_years',     years_cfg.get('center', 20)) or 20)
            response['savings'] = sim.get_savings_summary(_seed, _monthly, _years)
            response['savings_account_type'] = account_type
        except Exception:
            response['savings'] = None   # 절세 표시는 부가 정보 — 본 결과를 막지 않는다

    return response


def _run_multi_dividend_logic(body: dict, progress_callback=None, cancel_check=None) -> dict:
    """배당탭 멀티계좌 (G5-E). 역산 변수 = 계좌 1 시드/월납(오너 결정), G2 풀 라우팅.

    계좌 1 = 상단 입력(시드/월납/종목) — 다른 탭과 동일 규약. body.accounts[0]가 그 값.
    """
    import json as _json
    from modules.dividend_multi import MultiDividendSimulator
    from modules.multi_account_common import (
        normalize_multi_accounts, validate_initial_capital_limits,
    )
    from modules.tax.account_tax import DistributionPolicy

    portfolio_engine = _get_portfolio_engine()
    accounts = normalize_multi_accounts(body)
    tax_enabled = bool(body.get('tax_enabled', False))
    user_settings = body.get('user_settings') or {}

    init_errors = validate_initial_capital_limits(accounts)
    if init_errors:
        raise ValueError(_json.dumps(
            {'error': 'initial_capital_limit', 'violations': init_errors},
            ensure_ascii=False))

    if tax_enabled:
        from modules.tax.base_tax import TaxEngine
        from modules.tax.account_tax import validate_account_portfolio
        te = TaxEngine(user_settings)
        for a in accounts:
            w = {t['code']: t['weight'] for t in a['tickers']}
            chk = validate_account_portfolio(
                a['type'], [t['code'] for t in a['tickers']], w, te)
            if not chk['valid']:
                raise ValueError(_json.dumps({
                    'error': 'account_restrictions',
                    'violations': chk['violations'],
                    'disclaimer': chk.get('disclaimer'),
                }, ensure_ascii=False))

    distribution_policy = DistributionPolicy.from_dict(body.get('distribution_policy'))

    sim = MultiDividendSimulator(
        loader=portfolio_engine.loader,
        accounts=accounts,
        div_mode=body.get('dividend_mode', 'reinvest'),
        step_months=3,
        tax_enabled=tax_enabled,
        user_settings=user_settings,
        distribution_policy=distribution_policy,
        reinvest_tax_credit=bool(body.get('reinvest_tax_credit', False)),
    )

    seed_cfg    = body.get('seed',    {"center": 0,      "step": 0, "n": 0, "mode": "fixed"})
    monthly_cfg = body.get('monthly', {"center": 500000, "step": 0, "n": 0, "mode": "fixed"})
    years_cfg   = body.get('years',   {"center": 20,     "step": 0, "n": 0, "mode": "fixed"})

    response = sim.run_scenario(
        target_monthly_div = float(body['target_monthly_div']),
        probability        = float(body.get('probability', 0.50)),
        seed_cfg           = seed_cfg,
        monthly_cfg        = monthly_cfg,
        years_cfg          = years_cfg,
        progress_callback  = progress_callback,
        cancel_check       = cancel_check,
    )

    if tax_enabled and isinstance(response, dict) and not response.get('error'):
        try:
            _res = response.get('result') or {}
            _seed    = float(_res.get('solved_seed',    seed_cfg.get('center', 0)) or 0)
            _monthly = float(_res.get('solved_monthly', monthly_cfg.get('center', 0)) or 0)
            _years   = int(_res.get('solved_years',     years_cfg.get('center', 20)) or 20)
            response['savings'] = sim.get_savings_summary(_seed, _monthly, _years)
            response['savings_account_type'] = '멀티계좌'
        except Exception:
            response['savings'] = None
    response['multi_account'] = {'enabled': True, 'n_accounts': len(accounts)}
    return response
