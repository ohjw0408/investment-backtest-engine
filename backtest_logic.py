"""
backtest_logic.py
백테스트 엔드포인트의 핵심 로직 — app.py / tasks.py 양쪽에서 import 가능한 독립 모듈.
"""

import numpy as np

_portfolio_engine = None


def _annual_returns_from_index(years_arr, idx):
    """TWR 지수 기준 연도별 수익률 = 그 해 마지막날 / 전년 마지막날 - 1."""
    out = []
    for yr in dict.fromkeys(np.asarray(years_arr).tolist()):
        pos  = np.flatnonzero(years_arr == yr)
        base = idx[pos[0] - 1] if pos[0] > 0 else idx[pos[0]]
        if base > 0:
            out.append({'year': int(yr), 'return': round(float(idx[pos[-1]] / base - 1), 4)})
    return out


def compute_rolling_analysis(tickers, infl=0.02):
    """분석탭 심화(P2) — 전체기간·거치식·배당재투자 TR 인덱스 기반 롤링/분포/낙폭.
       결정#7: 사용자의 적립·세금·리밸·선택구간과 무관한 통계 관점("언제 시작했든").
       실질(인플레) 전환은 CAGR 디플레이트로 프런트에서 처리(infl만 전달).
       반환 None = 표본 부족(1년 미만). 그 외 dict."""
    from modules.tr_index import build_portfolio_tr_index
    from modules import rolling
    pts = build_portfolio_tr_index(tickers)
    if len(pts) < 13:   # 월말 13점(1년) 미만이면 의미 없음
        return None
    return {
        'horizons': rolling.DEFAULT_HORIZONS,
        'percentiles': rolling.DEFAULT_PCTS,
        'horizon_table': {str(h): v for h, v in rolling.horizon_table(pts).items()},
        'rolling_cagr': {str(h): rolling.rolling_cagr(pts, h) for h in (1, 3, 5, 10)},
        'infl': infl,
        'syn_overall': round(sum(1 for _d, _v, s in pts if s) / len(pts), 4),
    }


def _perf_block(hist, end_value, initial, monthly):
    """metrics·history·annual_* 공통 산출 — 단일계좌/멀티계좌 동일 규칙.

    수익률성 지표(연간수익률·MDD·낙폭·Sharpe)는 전부 TWR 지수 기준.
    잔고(portfolio_value) 기준으로 재면 적립금이 수익으로 잡힌다.
    CAGR은 적립식이면 금액가중(MWR) — "내 납입금이 연 몇 %로 굴러갔나".
    """
    import pandas as _pd
    from modules.perf_metrics import twr_index, max_drawdown, monthly_flows, mwr

    pv    = hist['portfolio_value']
    years = len(hist) / 252
    cf    = hist['cash_flow'] if 'cash_flow' in hist.columns else None
    dates = _pd.to_datetime(hist['date'])

    # 총 납입금 = 실제 기록된 납입 합계(근사식 initial + monthly*years*12 대체)
    total_invested = (
        float(cf[cf > 0].sum()) if cf is not None
        else initial + monthly * years * 12
    )
    total_return = (end_value / total_invested - 1) if total_invested > 0 else 0

    idx, tw_ret = twr_index(pv, cf)
    mdd    = max_drawdown(idx)
    sharpe = (
        float(tw_ret.mean() / tw_ret.std() * np.sqrt(252))
        if len(tw_ret) and tw_ret.std() > 0 else 0.0
    )

    # CAGR — 월별 순납입 시계열로 IRR. 실패(데이터 부족 등) 시 단순 연환산 폴백.
    cagr = mwr(monthly_flows(dates, cf), end_value) if cf is not None else None
    if cagr is None:
        cagr = ((end_value / total_invested) ** (1 / years) - 1
                if years > 0 and total_invested > 0 else 0)

    total_div = float(hist['dividend_income'].sum()) if 'dividend_income' in hist.columns else 0

    h = hist.copy()
    h['drawdown']       = idx / np.maximum.accumulate(idx) - 1.0
    h['total_invested'] = (cf.clip(lower=0).cumsum() if cf is not None
                           else initial + monthly * np.arange(len(h)) / 21)
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

    annual_returns   = _annual_returns_from_index(dates.dt.year.to_numpy(), idx)
    annual_dividends = []
    if 'dividend_income' in hist.columns:
        for yr, grp in hist.groupby(dates.dt.year):
            annual_dividends.append({'year': int(yr), 'dividend': round(float(grp['dividend_income'].sum()))})

    return {
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
        'history':          history_out,
        'annual_returns':   annual_returns,
        'annual_dividends': annual_dividends,
    }


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
    from modules.simulation.multi_account_loop import MultiAccountSimulationLoop
    from modules.tax.account_tax import DistributionPolicy
    from modules.multi_account_common import (
        normalize_multi_accounts, enforce_contribution_limits,
        build_loop_accounts, build_savings_summary,
    )

    portfolio_engine = _get_portfolio_engine()
    accounts      = normalize_multi_accounts(body)
    start_date    = body['start_date']
    end_date      = body['end_date']
    tax_enabled   = bool(body.get('tax_enabled', False))
    user_settings = body.get('user_settings', {})
    gain_harvesting = bool(body.get('gain_harvesting', False))

    # 한도 soft 경고(2026-06-13): 위반 시 진행 확인, 강행 시 limit_warnings 동봉
    limit_warnings = enforce_contribution_limits(
        body, accounts, routing_enabled=body.get('distribution_policy') is not None)

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
    # D4 거래수수료 — 개별주식 매도 거래세용 종목 집합.
    from modules.sim.fee_engine import build_stock_tickers
    _stock_tickers = build_stock_tickers(all_tickers) if body.get('fee_enabled') else None
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
        stock_tickers=_stock_tickers,
    )

    hist = result.combined_history_df
    if hist.empty:
        raise ValueError("시뮬레이션 결과가 없습니다. 종목·기간을 확인하세요.")

    total_initial = sum(float(a.get('initial_capital', 0.0)) for a in accounts)
    total_monthly = sum(float(a.get('monthly_contribution', 0.0)) for a in accounts)
    end_value     = float(result.combined_end_value)
    perf          = _perf_block(hist, end_value, total_initial, total_monthly)

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

    # 롤링용 통합 비중(P2) — 계좌 자본가중으로 종목 비중 합산(전체기간 거치식 관점)
    _roll_w = {}
    for a in accounts:
        cap = float(a.get('initial_capital', 0.0)) or 1.0
        tw = sum(float(t['weight']) for t in a['tickers']) or 1.0
        for t in a['tickers']:
            _roll_w[t['code']] = _roll_w.get(t['code'], 0.0) + cap * float(t['weight']) / tw
    _roll_tickers = [{'code': c, 'weight': w} for c, w in _roll_w.items()]

    return {
        'multi_account':  True,
        'limit_warnings': limit_warnings or None,
        'total_fees':     (float(getattr(result, 'total_fees', 0.0)) if body.get('fee_enabled') else None),  # D4
        'tax_enabled':    tax_enabled,
        'metrics':        perf['metrics'],
        'history':        perf['history'],
        'annual_returns': perf['annual_returns'],
        'annual_dividends': perf['annual_dividends'],
        'rolling':         compute_rolling_analysis(_roll_tickers),
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


def _guru_pit_schedule(slug, start_date, end_date, loader):
    """대가 슬러그 → 시점별 비중 스케줄. 재현 불가하면 None(호출측이 고정비중으로 폴백).

    반환 {schedule, tickers, start_date, segments, first_filed}.
    - 가격 없는 종목은 **세그먼트별로** 제외하고 재정규화(시뮬레이터 NaN 방지)
    - 요청 구간 밖 세그먼트는 잘라내되, 시작일 직전 것 하나는 시작 비중으로 남긴다
    - 첫 공시일보다 이른 시작일은 첫 공시일로 당긴다(그 전엔 공시 자체가 없음)
    """
    try:
        from modules.gurus import nav as guru_nav
    except Exception:
        return None

    codes = guru_nav.schedule_codes(slug)
    if not codes:
        return None

    coverage = {}
    for code in codes:
        try:
            lo, hi = loader.get_date_range_in_db(code)
        except Exception:
            lo = hi = None
        if lo:
            coverage[code] = (lo, hi or lo)

    full = guru_nav.weight_schedule(slug, coverage=coverage)
    if not full:
        return None

    segs   = [s for s in full if s[0] <= end_date]
    before = [s for s in segs if s[0] <= start_date]
    after  = [s for s in segs if s[0] >  start_date]
    segs   = ([before[-1]] if before else []) + after
    if not segs:
        return None

    # 가격이 없어 빠진 몫 — 재정규화로 조용히 메우면 안 되므로 UI에 그대로 넘긴다.
    raw = dict(guru_nav._segments(guru_nav._resolve_cik(slug)))
    kept = [sum(w for c, w in raw.get(filed, []) if c in ws) for filed, ws in segs]
    covered_ratio = round(sum(kept) / len(kept), 4) if kept else 0.0

    return {
        'schedule':      segs,
        'tickers':       sorted({c for _, w in segs for c in w}),
        'start_date':    max(start_date, segs[0][0]),
        'segments':      len(segs),
        'first_filed':   full[0][0],
        'covered_ratio': covered_ratio,
    }


def run_backtest_logic(body: dict, progress_callback=None) -> dict:
    # 멀티계좌(accounts 배열) → 단일윈도우 멀티계좌 경로. 단일계좌(legacy 필드) → 기존 경로.
    if body.get('accounts'):
        return _run_multi_account_backtest_logic(body, progress_callback)

    from modules.sim.fee_engine import build_stock_tickers
    from modules.simulation.taxable_runner  import TaxableSimulationRunner
    from modules.config.simulation_config   import SimulationConfig
    from modules.rebalance.periodic         import PeriodicRebalance
    from modules.rebalance.scheduled        import ScheduledRebalance

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

    # ── 투자대가 시점별(point-in-time) 재현 ────────────────────────────────
    # body['guru'] = 대가 슬러그. 오면 "오늘 비중을 과거에 소급"하는 대신
    # 분기 13F 공시일마다 그때의 실제 보유로 갈아끼운다(비교탭 NAV와 같은 세그먼트).
    guru_slug = str(body.get('guru') or '').strip()
    guru_pit  = None
    if guru_slug:
        guru_pit = _guru_pit_schedule(
            guru_slug, start_date, end_date, portfolio_engine.loader)
    if guru_pit:
        start_date = guru_pit['start_date']
        tickers    = guru_pit['tickers']
        weights    = {}   # ScheduledRebalance가 제자리로 채움 — config와 같은 객체 공유
        strategy   = ScheduledRebalance(guru_pit['schedule'], weights)
        rebal_freq = None   # 리밸런싱 시점 = 공시일. 주기 리밸은 쓰지 않음
        drift      = None
    else:
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
        fee_rate             = (float(body.get('fee_rate', 0) or 0) if body.get('fee_enabled') else 0.0),
        stock_tickers        = (build_stock_tickers(tickers) if body.get('fee_enabled') else None),
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

    # 한도 soft 경고(2026-06-13): 단일계좌 ISA/연금/IRP 초기·월납
    limit_warnings = []
    if tax_enabled:
        from modules.multi_account_common import enforce_contribution_limits
        limit_warnings = enforce_contribution_limits(body, [{
            'type': account_type,
            'initial_capital': initial,
            'monthly_contribution': monthly,
        }])

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

    perf = _perf_block(history_df, end_value, initial, monthly)

    return {
        'tax_enabled':    tax_enabled,
        # 시점별 재현 여부 — UI가 "고정 비중"과 구분해 표기(무엇을 돌렸는지 숨기지 않는다)
        'guru_pit':       ({'slug': guru_slug, 'segments': guru_pit['segments'],
                            'start_date': guru_pit['start_date'],
                            'first_filed': guru_pit['first_filed'],
                            'covered_ratio': guru_pit['covered_ratio']}
                           if guru_pit else None),
        'limit_warnings': limit_warnings or None,
        'total_fees':     (float(getattr(result, 'total_fees', 0.0)) if body.get('fee_enabled') else None),  # D4
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
        'metrics':        perf['metrics'],
        'history':        perf['history'],
        'annual_returns': perf['annual_returns'],
        'annual_dividends': perf['annual_dividends'],
        'rolling':         compute_rolling_analysis(body['tickers']),
    }
