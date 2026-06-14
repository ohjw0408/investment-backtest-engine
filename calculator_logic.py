"""
calculator_logic.py
/api/calculator/run 의 핵심 로직 — app.py / tasks.py 양쪽에서 import 가능한 독립 모듈.
"""

import datetime
import sqlite3
from dateutil.relativedelta import relativedelta

_portfolio_engine = None


def _get_portfolio_engine():
    global _portfolio_engine
    if _portfolio_engine is None:
        from modules.portfolio_engine import PortfolioEngine
        _portfolio_engine = PortfolioEngine()
    return _portfolio_engine


def _get_price_start(portfolio_engine, ticker: str):
    # KRX 금현물은 price_daily가 아닌 연속 시계열(index_master 기반) → 그 시작일 사용.
    if ticker == "KRX_GOLD":
        try:
            s = portfolio_engine.loader._build_krx_gold_series()
            return s.index.min().strftime("%Y-%m-%d")
        except Exception:
            return None
    try:
        cur = portfolio_engine.loader.conn.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=?", (ticker,)
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def _get_real_price_start(portfolio_engine, ticker: str):
    try:
        cur = portfolio_engine.loader.conn.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=? AND volume > 0",
            (ticker,),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def _get_symbol_proxy_label(ticker: str):
    try:
        from pathlib import Path
        db = Path(__file__).resolve().parent / "data" / "meta" / "symbol_master.db"
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT index_name, category FROM symbols WHERE code=?",
                (ticker,),
            ).fetchone()
        if not row:
            return None
        index_name, category = row
        try:
            from modules.backfill_engine import INDEX_MAP, US_CATEGORY_MAP
            return INDEX_MAP.get(index_name) or US_CATEGORY_MAP.get(category) or index_name or category
        except Exception:
            return index_name or category
    except Exception:
        return None


def _get_price_source_summary(portfolio_engine, ticker: str):
    try:
        rows = portfolio_engine.loader.conn.execute(
            """
            SELECT source_type, source_code, confidence, COUNT(*), MIN(date), MAX(date)
            FROM price_daily_source
            WHERE code=?
            GROUP BY source_type, source_code, confidence
            ORDER BY COUNT(*) DESC
            """,
            (ticker,),
        ).fetchall()
        return [
            {
                "source_type": r[0],
                "source_code": r[1],
                "confidence": r[2],
                "rows": int(r[3] or 0),
                "date_from": r[4],
                "date_to": r[5],
            }
            for r in rows
        ]
    except Exception:
        return []


def _build_price_provenance(portfolio_engine, tickers, data_start, cases):
    total_cases = len(cases)
    real_starts = [_get_real_price_start(portfolio_engine, t) for t in tickers]
    real_starts = [d for d in real_starts if d]
    all_real_start = max(real_starts) if real_starts else None

    actual_cases = 0
    if all_real_start:
        actual_cases = sum(1 for c in cases if str(c.get("start", "")) >= all_real_start)
    backfilled_cases = max(0, total_cases - actual_cases)

    ticker_info = []
    for ticker in tickers:
        price_start = _get_price_start(portfolio_engine, ticker)
        real_start = _get_real_price_start(portfolio_engine, ticker)
        sources = _get_price_source_summary(portfolio_engine, ticker)
        proxy_label = None
        for src in sources:
            if src.get("source_type") != "actual" and src.get("source_code"):
                proxy_label = src["source_code"]
                break
        if proxy_label is None:
            proxy_label = _get_symbol_proxy_label(ticker)

        ticker_info.append({
            "code": ticker,
            "data_start": price_start,
            "real_start": real_start,
            "is_backfilled": bool(real_start and price_start and real_start > price_start),
            "proxy": proxy_label,
            "sources": sources[:5],
        })

    return {
        "data_start": data_start,
        "real_start": all_real_start,
        "total_cases": total_cases,
        "actual_cases": actual_cases,
        "backfilled_cases": backfilled_cases,
        "is_backfilled": backfilled_cases > 0,
        "tickers": ticker_info,
    }


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


# 멀티계좌 입력 정규화·검증·결과 헬퍼는 공통 모듈에서 공유(백테스트·은퇴 복제, G5).
from modules.multi_account_common import (
    normalize_multi_accounts as _normalize_multi_accounts,
    build_savings_summary as _build_savings_summary,
)


def _build_fan(cases: list, years: int) -> dict | None:
    """경험적 부채꼴 — 각 롤링 윈도우의 연차 궤적(_yearly)에서 시점별 퍼센틸 그리드 산출.

    p1~p99 × (years+1) 그리드를 클라에 보내면 슬라이더가 서버 재호출 없이 임의 밴드를
    즉시 그린다. 미래 예측 신규 없음 — 있는 데이터를 시작점 정렬로 겹친 것.
    """
    import numpy as np
    trajs = [c.get('_yearly') for c in cases
             if c.get('_yearly') and len(c['_yearly']) == years + 1]
    if len(trajs) < 5:        # 표본 부족이면 부채꼴 생략
        return None
    arr = np.asarray(trajs, dtype=float)          # [N, years+1]
    pct = list(range(1, 100))                     # p1..p99
    grid = np.percentile(arr, pct, axis=0)        # [99, years+1]
    return {
        'axis':        list(range(0, years + 1)),         # 0~N 연차
        'percentiles': pct,
        'bands':       np.round(grid).tolist(),           # bands[i] = pct[i] 시점별 값
        'n':           len(trajs),
    }


def _run_multi_account_calculator_logic(body: dict, progress_callback=None) -> dict:
    from modules.retirement.multi_account_analyzer import MultiAccountAnalyzer

    from modules.tax.account_tax import DistributionPolicy

    portfolio_engine = _get_portfolio_engine()
    accounts         = _normalize_multi_accounts(body)
    years            = int(body['years'])
    dividend_mode    = body['dividend_mode']
    tax_enabled      = bool(body.get('tax_enabled', False))
    user_settings    = body.get('user_settings', {})
    gain_harvesting  = bool(body.get('gain_harvesting', False))

    # G2/G3/G4: 자금이동 정책·풍차·금종세·세액공제 재투자 (없으면 G1 동작 그대로)
    distribution_policy = DistributionPolicy.from_dict(body.get('distribution_policy'))
    manual_comprehensive_years = set(
        int(y) for y in (body.get('manual_comprehensive_years') or [])
    )
    reinvest_tax_credit = bool(body.get('reinvest_tax_credit', False))
    # transfers ON 조건: 분배정책 OR ISA풍차 OR (세금ON & 연금/IRP 존재 → 연납입공제 산출).
    # 한도 내 연금/IRP는 transfers ON/OFF 종료값 동일(test_l9_pension_transfers_equivalence)
    # 이므로 순수 연금/IRP에 켜도 안전 — 공제만 추가 산출.
    has_pension = any(a['type'] in ('연금저축', 'IRP') for a in accounts)
    transfers_enabled = (
        distribution_policy is not None
        or any(a.get('isa_renewal') for a in accounts)
        or (tax_enabled and has_pension)
    )

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
    _limit_warnings: list = []
    if tax_enabled:
        from modules.tax.base_tax import TaxEngine
        from modules.tax.account_tax import (
            check_contribution_limits,
            validate_account_portfolio,
        )
        tax_engine = TaxEngine(user_settings)
        # 한도 soft 경고(2026-06-13 오너 결정) — 초기·월납 위반 전수 수집 후 진행 확인.
        # transfers ON(G2)이면 월납 초과분은 라우팅이 합법 처리 → 초기자본만 경고 대상.
        from modules.multi_account_common import enforce_contribution_limits
        _limit_warnings = enforce_contribution_limits(
            body, accounts, routing_enabled=transfers_enabled)
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
    else:
        from modules.tax.account_tax import check_contribution_limits

    # transfers ON(G2)이면 ISA 1억 한도·초과 라우팅을 엔진(tracker)이 동적 처리.
    # 정적 contribution_end_months cap은 G1(transfers OFF)에서만 적용(BUG-4).
    isa_cap_accounts = []
    _ISA_TOTAL_LIMIT = 100_000_000
    for idx, account in enumerate(accounts):
        if account['type'] != 'ISA' or transfers_enabled:
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

    # D4 거래수수료 — 개별주식 매도 거래세용 종목 집합(계좌 전체 종목 기준).
    from modules.sim.fee_engine import build_stock_tickers
    _fee_codes = {t['code'] for a in accounts for t in a['tickers']}
    _stock_tickers = build_stock_tickers(_fee_codes) if body.get('fee_enabled') else None

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
        transfers_enabled         = transfers_enabled,
        distribution_policy       = distribution_policy,
        manual_comprehensive_years = manual_comprehensive_years,
        reinvest_tax_credit       = reinvest_tax_credit,
        stock_tickers             = _stock_tickers,
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
            # G2/G3/G4 윈도우별 결과 (transfers OFF면 비어있음)
            'comprehensive_years':     c.get('comprehensive_years', []),
            'annual_deduction_credit': round(c.get('annual_deduction_credit', 0)),
            'pension_transfer_credit': round(c.get('pension_transfer_credit', 0)),
            'transfer_count':          len(c.get('transfer_log', []) or []),
        }
        for c in result['cases']
    ]
    price_provenance = _build_price_provenance(
        portfolio_engine,
        all_tickers,
        data_start,
        cases_summary,
    )

    if len(isa_cap_accounts) == 1:
        isa_cap_info = isa_cap_accounts[0]
    elif isa_cap_accounts:
        isa_cap_info = {'capped': True, 'accounts': isa_cap_accounts}
    else:
        isa_cap_info = None

    # G2/G3/G4 대표 요약 — 종료값 중앙값 케이스 기준(transfers OFF면 enabled=False)
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

    # 절세액 표시(3종 + GH) — 계좌별 p50 + 합산.
    savings_summary = _build_savings_summary(result.get('savings') or {})

    # 분할매도 패널 (위탁 계좌 + KR_FOREIGN 청산이익 중앙값 > 2천만) — 단일경로와 동일 로직.
    split_sale_plan = None
    comprehensive_flag = any(c.get('comprehensive_years') for c in result['cases'])
    if any(a.get('type') == '위탁' for a in accounts):
        import statistics as _stats
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

    return {
        'cases':              cases_summary,
        'cases_count':        len(cases_summary),
        'distribution':       distribution,
        'g2':                 g2_summary,
        'savings':            savings_summary,
        'limit_warnings':     _limit_warnings or None,
        'total_fees':         (distribution.get('total_fees', {}).get('p50', 0.0)
                               if body.get('fee_enabled') else None),   # D4 총 수수료(중앙값)
        'split_sale_plan':    split_sale_plan,
        'comprehensive_flag': comprehensive_flag,
        'price_provenance':   price_provenance,
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
        'fan':                _build_fan(result['cases'], years),
        'used_synthetic':     _prep_meta.get('used_synthetic', False),
        'synthetic_info':     _prep_meta.get('synthetic_info', {}),
        'backfilled':         _prep_meta.get('backfilled', []),
        'warnings':           (_prep_meta.get('warnings', []) or []) + contribution_warnings,
    }


def run_calculator_logic(body: dict, progress_callback=None) -> dict:
    from modules.retirement.accumulation_analyzer import AccumulationAnalyzer

    accts = body.get('accounts') or []
    if len(accts) > 1:
        return _run_multi_account_calculator_logic(body, progress_callback)

    # BUG-SAVE-1 (A): 세금 ON 단일계좌도 멀티경로로 → 절세액(savings) 산출.
    # 단일경로(AccumulationAnalyzer)는 savings를 안 만들어 절세 패널이 안 떴음.
    # 세금 OFF는 절세 무의미 → 단일경로 유지.
    if bool(body.get('tax_enabled', False)) and not accts:
        nb = dict(body)
        primary = {
            'type':                 body.get('account_type', '위탁'),
            'initial_capital':      body.get('initial_capital', 0),
            'monthly_contribution': body.get('monthly_contribution', 0),
            'tickers':              body.get('tickers', []),
            'rebal_mode':           body.get('rebal_mode'),
            'band_width':           body.get('band_width', 0.05),
            'dividend_mode':        body.get('dividend_mode'),
            'isa_renewal':          body.get('isa_renewal', False),
        }
        # 단일 풍차 ISA: 만기 목돈이 연 2천만 한도를 초과해 단일계좌론 전액 재입금 불가.
        # → 같은 종목·비중의 위탁계좌(초기0·월0)를 자동 생성하고 한도 초과분을 위탁으로
        #   라우팅(분배정책)해 풍차를 정상 작동시킨다. 결과창에 안내문구 표시.
        auto_brokerage = False
        if body.get('account_type') == 'ISA' and bool(body.get('isa_renewal', False)):
            mirror = dict(primary)
            mirror.update({'type': '위탁', 'initial_capital': 0,
                           'monthly_contribution': 0, 'isa_renewal': False})
            nb['accounts'] = [primary, mirror]
            nb['distribution_policy'] = {'destinations': [{'account_id': 0},
                                                          {'account_id': 1}]}
            auto_brokerage = True
        else:
            nb['accounts'] = [primary]
        res = _run_multi_account_calculator_logic(nb, progress_callback)
        if auto_brokerage:
            res['windmill_auto_brokerage'] = True
        return res

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

    # 한도 soft 경고(2026-06-13 오너 결정) — ISA·연금/IRP 초기·월납 위반 수집 후 진행 확인.
    _limit_warnings: list = []
    if tax_enabled:
        from modules.multi_account_common import enforce_contribution_limits
        _limit_warnings = enforce_contribution_limits(body, [{
            'type': account_type,
            'initial_capital': initial_capital,
            'monthly_contribution': monthly_contrib,
        }])

    from modules.sim.fee_engine import build_stock_tickers
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
        fee_rate                = (float(body.get('fee_rate', 0) or 0) if body.get('fee_enabled') else 0.0),
        stock_tickers           = (build_stock_tickers(ticker_codes) if body.get('fee_enabled') else None),
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
    price_provenance = _build_price_provenance(
        portfolio_engine,
        ticker_codes,
        data_start,
        cases_summary,
    )

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
        'price_provenance':         price_provenance,
        'isa_partial_cycle':        has_partial_isa,
        'isa_remainder_years':      years % 3 if has_partial_isa else 0,
        'isa_cap_info':             _isa_cap_info,
        'limit_warnings':           _limit_warnings or None,
        'total_fees':               (result['distribution'].get('total_fees', {}).get('p50', 0.0)
                                     if body.get('fee_enabled') else None),   # D4 총 수수료(중앙값)
        'split_sale_plan':          split_sale_plan,
        'comprehensive_flag':       comprehensive_flag,
        'fan':                      _build_fan(result['cases'], years),
        'used_synthetic':           _prep_meta.get('used_synthetic', False),
        'synthetic_info':           _prep_meta.get('synthetic_info', {}),
        'backfilled':               _prep_meta.get('backfilled', []),
        'warnings':                 _prep_meta.get('warnings', []),
    }
