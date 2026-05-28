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


def run_retirement_logic(body: dict, progress_callback=None) -> dict:
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

    div_starts = [_get_dividend_start(portfolio_engine, t) for t in ticker_codes]
    div_starts = [d for d in div_starts if d]
    div_start  = max(div_starts) if div_starts else None

    tax_enabled     = body.get('tax_enabled', False)
    account_type    = body.get('account_type', '위탁')
    user_settings   = body.get('user_settings', {})
    isa_renewal     = body.get('isa_renewal', False)
    gain_harvesting = body.get('gain_harvesting', False)
    ret_tax_engine  = None
    if tax_enabled:
        from modules.tax.base_tax import TaxEngine
        ret_tax_engine = TaxEngine(user_settings)

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
        portfolio_engine     = portfolio_engine,
        tickers              = ticker_codes,
        strategy_factory     = strategy_factory,
        data_start           = data_start,
        data_end             = data_end,
        accumulation_years   = accumulation_years,
        monthly_contribution = monthly_contribution,
        initial_capital      = initial_capital,
        dividend_mode        = dividend_mode,
        step_months          = 3,
        verbose              = False,
        div_start            = div_start,
        tax_engine           = ret_tax_engine,
        account_type         = account_type,
        isa_renewal          = isa_renewal,
        gain_harvesting      = gain_harvesting,
        progress_callback    = acc_progress,
        use_synthetic        = use_synthetic,
        synthetic_params     = synthetic_info if use_synthetic else {},
    )
    acc_result = acc_analyzer.run()

    # 인출 분석 전 50% 알림
    if progress_callback:
        progress_callback(current=50, total=100, elapsed=time.time() - _acc_start)

    planner = RetirementPlanner(
        acc_result         = acc_result,
        wd_config          = {
            "portfolio_engine": portfolio_engine,
            "tickers":          ticker_codes,
            "strategy_factory": strategy_factory,
            "data_start":       data_start,
            "data_end":         data_end,
            "withdrawal_years": withdrawal_years,
            "dividend_mode":    dividend_mode,
            "step_months":      6,
        },
        monthly_withdrawal  = monthly_withdrawal,
        withdrawal_years    = withdrawal_years,
        inflation           = inflation,
        verbose             = False,
        progress_callback   = progress_callback,
        start_time          = _acc_start,
    )
    report = planner.run(target_percentile=target_percentile)

    # 완료 100% 알림
    if progress_callback:
        progress_callback(current=100, total=100, elapsed=time.time() - _acc_start)

    return {
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


def run_withdrawal_logic(body: dict, progress_callback=None) -> dict:
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

    tax_enabled   = body.get('tax_enabled', False)
    account_type  = body.get('account_type', '위탁')
    user_settings = body.get('user_settings', {})
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
