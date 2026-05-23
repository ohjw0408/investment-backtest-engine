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

    sim = DividendSimulator(
        loader       = portfolio_engine.loader,
        tickers      = ticker_codes,
        weights      = target_weights,
        div_mode     = body.get('dividend_mode', 'reinvest'),
        step_months  = 3,
        rebal_mode   = body.get('rebal_mode', 'none'),
        band_width   = float(body.get('band_width', 0.05)),
        tax_engine   = tax_engine,
        account_type = account_type,
    )

    seed_cfg    = body.get('seed',    {"center": 0,      "step": 0, "n": 0, "mode": "fixed"})
    monthly_cfg = body.get('monthly', {"center": 500000, "step": 0, "n": 0, "mode": "fixed"})
    years_cfg   = body.get('years',   {"center": 20,     "step": 0, "n": 0, "mode": "fixed"})

    return sim.run_scenario(
        target_monthly_div = float(body['target_monthly_div']),
        probability        = float(body.get('probability', 0.90)),
        seed_cfg           = seed_cfg,
        monthly_cfg        = monthly_cfg,
        years_cfg          = years_cfg,
        progress_callback  = progress_callback,
        cancel_check       = cancel_check,
    )
