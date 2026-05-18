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


def run_dividend_scenario_logic(body: dict, progress_callback=None) -> dict:
    from modules.dividend_simulator import DividendSimulator

    portfolio_engine = _get_portfolio_engine()

    tickers_input  = body['tickers']
    ticker_codes   = [t['code'] for t in tickers_input]
    target_weights = {t['code']: t['weight'] for t in tickers_input}

    sim = DividendSimulator(
        loader      = portfolio_engine.loader,
        tickers     = ticker_codes,
        weights     = target_weights,
        div_mode    = body.get('dividend_mode', 'reinvest'),
        step_months = 3,
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
    )
