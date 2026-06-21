"""멀티계좌 가구 디큐뮬레이션 (G5-C C3.2).

단일 윈도우(은퇴 인출 기간 W년)를 N개 계좌 합동 시뮬레이션한다.
계좌별 배당·리밸런싱은 독립이나, 인출은 **가구 단일액**을 household_withdraw로
위탁→ISA→연금/IRP 순 소진(C3.1). 생존 = 합산 자산이 월 인출액 못 대는 첫 시점=실패(오너 Q4).

인출 페이즈는 적립과 달리 납입·계좌이동·풍차·한도가 없어 단순 → 적립 루프 대신 전용.
단일 SimulationLoop 월 흐름(배당→인출→리밸)을 멀티+가구인출로 미러.
"""
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from modules.core.portfolio import Portfolio, TaxTrackedPortfolio
from modules.execution.order_executor import OrderExecutor, TaxedOrderExecutor
from modules.execution.cash_allocator import CashAllocator
from modules.simulation.dividend_engine import DividendEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.retirement.household_withdrawal import household_withdraw

_PENSION_TYPES = ("연금저축", "IRP")
MIN_CASES_WD = 30   # 실윈도우 부족 시 이 개수까지 합성 보충 (단일 WithdrawalAnalyzer와 동일).
SYNTHETIC_DF = 5    # Student-t 자유도 (단일과 동일).


def _build_account_runtime(spec, first_price_dict, tax_engine, session):
    """계좌 1개 런타임 구성 — 시작자산으로 초기 매수 + 취득가 인계."""
    atype   = spec["type"]
    weights = spec["target_weights"]
    value   = float(spec["value"])

    # D4 거래수수료 — 계좌별 율(spec.fee_rate) + 개별주식 매도세(stock_tickers).
    _fee_rate      = float(spec.get("fee_rate", 0.0) or 0.0)
    _stock_tickers = spec.get("stock_tickers")

    if tax_engine is not None:
        pf = TaxTrackedPortfolio(value, fee_rate=_fee_rate, stock_tickers=_stock_tickers)
        executor = TaxedOrderExecutor(tax_engine, atype, session=session)
        div_engine = _make_taxed_dividend_engine(tax_engine, atype, session)
    else:
        pf = Portfolio(value, fee_rate=_fee_rate, stock_tickers=_stock_tickers)
        executor = OrderExecutor()
        div_engine = DividendEngine()

    allocator = CashAllocator()
    allocator.allocate_cash(pf, first_price_dict, weights)

    # 적립 취득가 인계(위탁 인출 매도가 적립차익까지 과세 — G5-C C1과 동일 원리).
    cost_basis = spec.get("cost_basis")
    if cost_basis and isinstance(pf, TaxTrackedPortfolio) and pf._avg_costs:
        invested = sum(
            pf._avg_costs[t] * pf.positions[t].quantity
            for t in pf._avg_costs
            if t in pf.positions and pf.positions[t].quantity > 0
        )
        if invested > 0:
            scale = cost_basis / invested
            for t in list(pf._avg_costs.keys()):
                pf._avg_costs[t] *= scale

    # 계좌별 리밸런싱 전략 — 적립(multi_account_common/MultiAccountAnalyzer)과 동일 로직.
    # none→무리밸, band→드리프트 임계, 그 외(monthly/quarterly/yearly)→주기.
    rebal_mode = spec.get("rebal_mode", "none")
    band_width = float(spec.get("band_width", 0.05))
    rebalance_frequency = None if rebal_mode in ("none", "band") else rebal_mode
    drift_threshold = band_width if rebal_mode == "band" else None

    return {
        "account_id":     spec["account_id"],
        "type":           atype,
        "portfolio":      pf,
        "executor":       executor,
        "div_engine":     div_engine,
        "allocator":      allocator,
        "strategy":       PeriodicRebalance(
            weights, rebalance_frequency=rebalance_frequency,
            drift_threshold=drift_threshold,
        ),
        "target_weights": weights,
        # 절세액(위탁 가정) 입력 — 인출 페이즈 누적(적립 _finalize_account와 동형).
        "cf_gross_div_by_class": {},
        "dividend_tax_paid":     0.0,
        "pension_tax_paid":      0.0,
    }


def _make_taxed_dividend_engine(tax_engine, atype, session):
    from modules.tax.account_tax import TaxedDividendEngine
    return TaxedDividendEngine(DividendEngine(), tax_engine, atype, session=session)


def simulate_household_window(
    accounts,
    price_data: dict,
    dates,
    monthly_net: float,
    *,
    tax_engine=None,
    withdrawal_start_age: int = 65,
    inflation: float = 0.0,
    dividend_mode: str = "reinvest",
) -> dict:
    """N계좌 합동 인출 1윈도우.

    accounts: [{account_id, type, value, cost_basis(opt), target_weights}, ...]
    반환: {success, fail_month, combined_end_value, per_account:[{account_id,type,end_value}],
           total_pension_tax}.
    """
    if not dates:
        raise ValueError("시뮬레이션 날짜가 없습니다.")

    session = None
    if tax_engine is not None:
        from modules.tax.session import TaxSessionState
        session = TaxSessionState(other_financial_income=0.0)

    price_array, valid_index = {}, {}
    for ticker, df in price_data.items():
        price_array[ticker] = df["close"].values
        valid_index[ticker] = df.index

    # 전 계좌가 필요로 하는 종목 — 초기 매수는 전부 유효가격이 있는 날부터(부분 데이터 가드).
    needed_tickers = {t for s in accounts for t in s["target_weights"] if t != "CASH"}

    runtimes = None
    last_wd_month = None
    last_infl_month = None
    elapsed_months = 0
    success = True
    fail_month = None
    total_pension_tax = 0.0

    for i, date in enumerate(dates):
        price_dict = {}
        for ticker in price_data:
            if date in valid_index[ticker]:
                px = price_array[ticker][i]
                # 리딩 NaN 가드 — 합집합 달력 reindex+ffill은 첫 행 이전을 NaN으로 남김.
                # NaN/0 가격이 초기 매수·매도에 들어가면 포트 전체가 오염된다(라이브 일시 0% 사고).
                if np.isfinite(px) and px > 0:
                    price_dict[ticker] = px
        if not price_dict:
            continue

        current_month = (date.year, date.month)
        if last_infl_month is None:
            last_infl_month = current_month
        elif current_month != last_infl_month:
            elapsed_months += 1
            last_infl_month = current_month

        # 첫 유효일: 계좌 런타임 구성(초기 매수) — 전 종목 가격 유효한 날까지 대기.
        if runtimes is None:
            if not needed_tickers.issubset(price_dict.keys()):
                continue
            runtimes = [
                _build_account_runtime(s, price_dict, tax_engine, session)
                for s in accounts
            ]
            # 단일 SimulationLoop과 정합: 첫 달은 인출 스킵(last_withdrawal_month를
            # 시작월로 초기화하는 단일 엔진과 동일 — 은퇴 시작 첫 달 무인출).
            last_wd_month = current_month

        # 계좌별 배당 — 절세액용 gross(세전) 분류별 누적 + 실제 배당세(gross−net) 누적.
        for rt in runtimes:
            gross_by_ticker = {}
            if tax_engine is not None:
                for ticker, pos in rt["portfolio"].positions.items():
                    if ticker not in price_data or date not in valid_index[ticker]:
                        continue
                    div = price_data[ticker].loc[date, "dividend"]
                    if div > 0:
                        gross_by_ticker[ticker] = float(div) * float(pos.quantity)
            net_by_ticker = rt["div_engine"].process(
                rt["portfolio"], price_data, price_dict, date, dividend_mode
            )
            if gross_by_ticker:
                cls_acc = rt["cf_gross_div_by_class"]
                for ticker, gross in gross_by_ticker.items():
                    cls = tax_engine.classify_asset(ticker)
                    cls_acc[cls] = cls_acc.get(cls, 0.0) + gross
                rt["dividend_tax_paid"] += sum(
                    max(0.0, g - float(net_by_ticker.get(t, 0.0)))
                    for t, g in gross_by_ticker.items()
                )

        # 가구 인출 — 월 1회
        if success and last_wd_month != current_month:
            last_wd_month = current_month
            net_t = monthly_net * (1 + inflation / 12) ** elapsed_months
            age = withdrawal_start_age + elapsed_months // 12
            order_accts = [
                {"account_id": rt["account_id"], "type": rt["type"],
                 "portfolio": rt["portfolio"], "executor": rt["executor"],
                 "target_weights": rt["target_weights"]}
                for rt in runtimes
            ]
            res = household_withdraw(
                order_accts, net_t, price_dict, date,
                tax_engine=tax_engine, age=age,
            )
            total_pension_tax += sum(p["pension_tax"] for p in res["per_account"])
            # 절세액용: 계좌별 연금소득세 누적(실제세금 구성요소).
            _ptax_by_id = {p["account_id"]: p["pension_tax"] for p in res["per_account"]}
            for rt in runtimes:
                rt["pension_tax_paid"] += float(_ptax_by_id.get(rt["account_id"], 0.0))
            if res["depleted"]:
                success = False
                fail_month = elapsed_months

        # 계좌별 리밸런싱
        for rt in runtimes:
            strat = rt["strategy"]
            pf = rt["portfolio"]
            if strat.should_rebalance(date, pf, price_dict):
                orders = strat.generate_orders(pf, price_dict)
                rt["executor"].execute_orders(pf, orders, price_dict, date=date)

    if runtimes is None:
        raise ValueError("유효 가격일이 없습니다.")

    last_price = {}
    last_i = len(dates) - 1
    for ticker in price_data:
        if dates[last_i] in valid_index[ticker]:
            px = price_array[ticker][last_i]
            if np.isfinite(px) and px > 0:
                last_price[ticker] = px
    # 마지막 유효(유한) 가격 폴백
    for ticker in price_data:
        if ticker not in last_price:
            arr = np.asarray(price_array[ticker], dtype=float)
            finite = arr[np.isfinite(arr) & (arr > 0)]
            last_price[ticker] = float(finite[-1]) if len(finite) else 0.0

    per_account = []
    combined = 0.0
    _total_fees = 0.0   # D4 가구 인출 거래수수료(전 계좌 합)
    for rt in runtimes:
        _total_fees += float(getattr(rt["portfolio"], "total_fees", 0.0))
        ev = rt["portfolio"].total_value(last_price)
        entry = {
            "account_id": rt["account_id"], "type": rt["type"],
            "end_value": round(ev, 2),
        }
        # 절세액 3종(위탁가정·실제·절세).
        # 위탁가정 = 세전 배당 + 실현차익(인출·리밸 매도)을 위탁 세율로.
        # ⚠ 적립(_finalize_account)과 달리 **잔여 미실현차익 미가산** — wd end_value는
        # 무청산(gross)이라 실제세금에도 청산세가 없음. 양쪽 다 제외해야 위탁 불변식(절세 0) 유지.
        # 실제 = 배당세 + 양도세(위탁 매도) + 연금소득세. 절세 = max(0, 가정 − 실제).
        if tax_engine is not None:
            from modules.tax.saving_estimate import estimate_brokerage_tax
            executor = rt["executor"]
            if hasattr(executor, "_brk_us_by_year"):
                assumed = estimate_brokerage_tax(
                    rt["cf_gross_div_by_class"],
                    executor._brk_krf_gain,
                    executor._brk_us_by_year,
                )
                actual = (
                    float(rt["dividend_tax_paid"])
                    + float(getattr(executor, "total_cg_tax_paid", 0.0))
                    + float(rt["pension_tax_paid"])
                )
                entry["brokerage_assumed_tax"] = round(assumed, 2)
                entry["actual_tax"]            = round(actual, 2)
                entry["tax_saving"]            = round(max(0.0, assumed - actual), 2)
        per_account.append(entry)
        combined += ev

    return {
        "success":            success,
        "fail_month":         fail_month,
        "combined_end_value": round(combined, 2),
        "per_account":        per_account,
        "total_pension_tax":  round(total_pension_tax, 2),
        "total_fees":         round(_total_fees, 2),   # D4
    }


def _ticker_return_stats(closes) -> tuple:
    """실 종가 → 월 (mu, sigma). 단일 WithdrawalAnalyzer._get_return_stats와 동형.
    데이터 부족 시 7%/15% 연 환산 폴백."""
    try:
        closes = np.asarray(closes, dtype=float)
        if len(closes) >= 24:
            mpx  = closes[np.arange(0, len(closes), 21)]
            mret = np.diff(mpx) / np.where(mpx[:-1] > 0, mpx[:-1], 1.0)
            mret = mret[np.isfinite(mret) & (np.abs(mret) < 0.5)]
            if len(mret) >= 12:
                mu, sigma = float(np.mean(mret)), float(np.std(mret))
                if sigma > 0 and np.isfinite(mu):
                    return mu, sigma
    except Exception:
        pass
    return 0.07 / 12, 0.15 / np.sqrt(12)


def _synthetic_household_window_gbm(
    accounts, ticker_stats, withdrawal_years, monthly_net, rng,
    *, tax_engine, withdrawal_start_age, inflation, dividend_mode,
) -> dict:
    """폴백: 종목별 독립 GBM(Student-t) 합성 월가격(상관 미모델·배당0).
    MVN 피팅 실패(_build_household_mvn 빈 dict) 시에만 사용."""
    n_months = withdrawal_years * 12
    dates = pd.date_range("2000-01-01", periods=n_months + 1, freq="MS")
    t_scale = np.sqrt(SYNTHETIC_DF / (SYNTHETIC_DF - 2))
    synth_data = {}
    for ticker, (mu, sigma) in ticker_stats.items():
        rets = (rng.standard_t(df=SYNTHETIC_DF, size=n_months) / t_scale) * sigma + mu
        closes = np.empty(n_months + 1)
        closes[0] = 100.0
        closes[1:] = 100.0 * np.cumprod(1.0 + rets)
        synth_data[ticker] = pd.DataFrame(
            {"open": closes, "high": closes, "low": closes, "close": closes,
             "volume": 1.0, "dividend": 0.0, "split": 1.0},
            index=dates,
        )
    res = simulate_household_window(
        accounts, synth_data, list(dates), monthly_net,
        tax_engine=tax_engine, withdrawal_start_age=withdrawal_start_age,
        inflation=inflation, dividend_mode=dividend_mode,
    )
    res["is_synthetic"] = True
    return res


def _build_household_mvn(price_data: dict) -> dict:
    """P2: 가구 인출 합성용 종목별 월 mu/sigma + 상관 cholesky + 연 배당수익률.

    price_data(일별 OHLCV+dividend) → 21영업일 간격 월수익으로 mu/sigma/상관 피팅.
    상관·배당이 없던 단일 GBM(_synthetic_household_window 구버전)을 대체한다.
    """
    from modules.retirement.synthetic_price_generator import MAX_SYNTH_MU_MONTHLY
    tickers = list(price_data.keys())
    mret = {}
    for t in tickers:
        c = np.asarray(price_data[t]["close"].values, float)
        if len(c) >= 24:
            mpx = c[::21]
            r = np.diff(mpx) / np.where(mpx[:-1] > 0, mpx[:-1], 1.0)
            r = r[np.isfinite(r) & (np.abs(r) < 0.5)]
            if len(r) >= 12:
                mret[t] = r
    if len(mret) < len(tickers):
        return {}                       # 일부 종목 통계 부족 → 호출부 단일 GBM 폴백

    mu  = np.array([float(np.mean(mret[t])) for t in tickers])
    sig = np.array([float(np.std(mret[t]))  for t in tickers])
    if not (np.all(np.isfinite(mu)) and np.all(sig > 0)):
        return {}
    mu = np.minimum(mu, MAX_SYNTH_MU_MONTHLY)          # 월 drift 상한

    k = len(tickers)
    L = min(len(mret[t]) for t in tickers)
    if L >= 12:
        M = np.column_stack([mret[t][-L:] for t in tickers])   # tail 정렬
        corr = np.nan_to_num(np.corrcoef(M, rowvar=False), nan=0.0)
        np.fill_diagonal(corr, 1.0)
    else:
        corr = np.eye(k)
    cov = np.outer(sig, sig) * corr
    try:
        chol = np.linalg.cholesky(cov + np.eye(k) * 1e-12)
    except Exception:
        w, V = np.linalg.eigh((cov + cov.T) / 2)
        cov = V @ np.diag(np.clip(w, 1e-12, None)) @ V.T
        try:
            chol = np.linalg.cholesky(cov + np.eye(k) * 1e-12)
        except Exception:
            chol = np.diag(sig)

    div_yield = {}
    for t in tickers:
        df = price_data[t]
        yrs = max(1.0, len(df) / 252.0)
        if "dividend" in df.columns:
            mean_close = float(df["close"].mean())
            div_yield[t] = (float(df["dividend"].sum()) / mean_close / yrs) if mean_close > 0 else 0.0
        else:
            div_yield[t] = 0.0
    return {"tickers": tickers, "mu": mu, "chol": chol, "div_yield": div_yield}


def _synthetic_household_window(
    accounts, mvn_stats, withdrawal_years, monthly_net, rng,
    *, tax_engine, withdrawal_start_age, inflation, dividend_mode,
) -> dict:
    """종목별 mu/sigma + 상관(다변량-t) 합성 월가격 경로 + 분기배당 → simulate_household_window.

    P2: 종목간 상관행렬(cholesky)과 종목별 실 배당수익률을 반영(구버전은 무상관·배당0).
    드레인 순서·연금세·취득가·리밸은 simulate_household_window가 그대로 처리.
    """
    tickers   = mvn_stats["tickers"]
    mu        = mvn_stats["mu"]
    chol      = mvn_stats["chol"]
    div_yield = mvn_stats["div_yield"]
    k = len(tickers)
    n_months = withdrawal_years * 12
    dates = pd.date_range("2000-01-01", periods=n_months + 1, freq="MS")
    t_scale = np.sqrt(SYNTHETIC_DF / (SYNTHETIC_DF - 2))

    # 상관 반영 다변량-t 월수익 (n_months × k)
    z   = rng.standard_t(df=SYNTHETIC_DF, size=(n_months, k)) / t_scale
    ret = z @ chol.T + mu

    synth_data = {}
    for j, ticker in enumerate(tickers):
        closes = np.empty(n_months + 1)
        closes[0] = 100.0
        closes[1:] = 100.0 * np.cumprod(1.0 + ret[:, j])
        dy   = max(float(div_yield.get(ticker, 0.0)), 0.0)
        divs = np.zeros(n_months + 1)
        if dy > 0:
            # 분기(매 3개월) 배당 = 그 시점 주가 × 연수익률/4
            for m in range(3, n_months + 1, 3):
                divs[m] = closes[m] * (dy / 4.0)
        synth_data[ticker] = pd.DataFrame(
            {"open": closes, "high": closes, "low": closes, "close": closes,
             "volume": 1.0, "dividend": divs, "split": 1.0},
            index=dates,
        )
    res = simulate_household_window(
        accounts, synth_data, list(dates), monthly_net,
        tax_engine=tax_engine, withdrawal_start_age=withdrawal_start_age,
        inflation=inflation, dividend_mode=dividend_mode,
    )
    res["is_synthetic"] = True
    return res


_PCTS = [10, 25, 50, 75, 90]


def _pct_dist(values: list) -> dict:
    if not values:
        return {f"p{p}": 0.0 for p in _PCTS}
    arr = np.array(values, dtype=float)
    return {f"p{p}": round(float(np.percentile(arr, p)), 2) for p in _PCTS}


def analyze_household_withdrawal(
    accounts,
    price_data: dict,
    all_dates,
    data_start,
    data_end,
    withdrawal_years: int,
    monthly_net: float,
    *,
    tax_engine=None,
    withdrawal_start_age: int = 65,
    inflation: float = 0.0,
    dividend_mode: str = "reinvest",
    step_months: int = 3,
) -> dict:
    """가구 인출 롤링 분석 — 실가격 롤링 윈도우 합동 디큐뮬레이션 → 생존율 + 분포.

    단일 WithdrawalAnalyzer의 멀티 대응. 각 윈도우는 동일 시작자산(계좌별)·다른 가격경로.
    생존율 = 윈도우 성공 비율(전 계좌 합산이 월 인출 충당한 윈도우). 합성보충 없음(실윈도우만).
    """
    data_start = pd.Timestamp(data_start)
    data_end   = pd.Timestamp(data_end)

    valid_index = {t: df.index for t, df in price_data.items()}

    windows, cur = [], data_start
    while True:
        end = cur + relativedelta(years=withdrawal_years)
        if end > data_end:
            break
        windows.append((cur, end))
        cur += relativedelta(months=step_months)
    # 실윈도우 0개(데이터 < 인출기간, GAP-RET-KRDATA)여도 raise 안 함 —
    # 아래 합성 보충이 전량 합성으로 폴백해 결과를 낸다(n_real=0, 화면에 가상 표시).

    case_results = []
    for w_start, w_end in windows:
        sliced_dates = [d for d in all_dates if w_start <= d <= w_end]
        if not sliced_dates:
            continue
        sliced_data = {
            t: df.loc[(df.index >= w_start) & (df.index <= w_end)]
            for t, df in price_data.items()
        }
        try:
            r = simulate_household_window(
                accounts, sliced_data, sliced_dates, monthly_net,
                tax_engine=tax_engine, withdrawal_start_age=withdrawal_start_age,
                inflation=inflation, dividend_mode=dividend_mode,
            )
        except ValueError:
            continue
        case_results.append(r)

    # ── 합성 보충: 실윈도우 < MIN_CASES_WD면 GBM 합성으로 패딩 (단일과 동형).
    #    실윈도우 0개면 전량 합성 폴백(GAP-RET-KRDATA) ──
    n_real = len(case_results)
    n_needed = max(0, MIN_CASES_WD - n_real)
    if n_needed > 0:
        # P2: 종목별 mu/sigma+상관+배당 MVN 우선, 실패 시 구 단일종목 GBM 폴백.
        mvn_stats = _build_household_mvn(price_data)
        ticker_stats = None
        if not mvn_stats:
            ticker_stats = {
                t: _ticker_return_stats(df["close"].values)
                for t, df in price_data.items()
            }
        for i in range(n_needed):
            rng = np.random.default_rng(seed=1000 + i)
            try:
                if mvn_stats:
                    case_results.append(_synthetic_household_window(
                        accounts, mvn_stats, withdrawal_years, monthly_net, rng,
                        tax_engine=tax_engine, withdrawal_start_age=withdrawal_start_age,
                        inflation=inflation, dividend_mode=dividend_mode,
                    ))
                else:
                    case_results.append(_synthetic_household_window_gbm(
                        accounts, ticker_stats, withdrawal_years, monthly_net, rng,
                        tax_engine=tax_engine, withdrawal_start_age=withdrawal_start_age,
                        inflation=inflation, dividend_mode=dividend_mode,
                    ))
            except Exception:
                continue
    n_synthetic = len(case_results) - n_real

    if not case_results:
        raise ValueError("롤링 윈도우가 0개입니다 (데이터 부족 — 합성 생성도 실패).")

    survival_rate = float(np.mean([1.0 if r["success"] else 0.0 for r in case_results]))
    combined_vals = [r["combined_end_value"] for r in case_results]

    n_acc = len(accounts)
    per_account_dist = []
    for k in range(n_acc):
        vals = [r["per_account"][k]["end_value"] for r in case_results]
        per_account_dist.append({
            "account_id": accounts[k]["account_id"],
            "type":       accounts[k]["type"],
            "end_value":  _pct_dist(vals),
        })

    pension_taxes = [r["total_pension_tax"] for r in case_results]

    # 절세액 요약 — 계좌별 p50 + 합산(계좌별 p50 단순합, 적립 _build_savings와 동일 규약).
    savings = None
    if tax_engine is not None and case_results and \
            "tax_saving" in case_results[0]["per_account"][0]:
        sav_accounts = []
        for k in range(n_acc):
            def _p50(field, _k=k):
                vals = [r["per_account"][_k].get(field, 0.0) for r in case_results]
                return round(float(np.median(vals)), 2)
            sav_accounts.append({
                "account_id":            accounts[k]["account_id"],
                "type":                  accounts[k]["type"],
                "brokerage_assumed_tax": _p50("brokerage_assumed_tax"),
                "actual_tax":            _p50("actual_tax"),
                "tax_saving":            _p50("tax_saving"),
                "gain_harvest_saving":   0.0,   # 인출 페이즈 GH 미지원
            })
        savings = {
            "accounts": sav_accounts,
            "combined": {
                "brokerage_assumed_tax": round(sum(a["brokerage_assumed_tax"] for a in sav_accounts), 2),
                "actual_tax":            round(sum(a["actual_tax"] for a in sav_accounts), 2),
                "tax_saving":            round(sum(a["tax_saving"] for a in sav_accounts), 2),
                "gain_harvest_saving":   0.0,
            },
        }

    return {
        "survival_rate":      round(survival_rate, 4),
        "n_windows":          len(case_results),
        "n_real":             n_real,
        "n_synthetic":        n_synthetic,
        "combined_end_value": _pct_dist(combined_vals),
        "per_account":        per_account_dist,
        "median_pension_tax": round(float(np.median(pension_taxes)), 2),
        "savings":            savings,
        "total_fees":         round(float(np.median([r.get("total_fees", 0.0) for r in case_results])), 2),  # D4
    }


# 적립 분포 샘플링 percentile (단일 RetirementPlanner와 동일).
SAMPLE_PERCENTILES = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95]


def analyze_household_samples(
    account_specs,
    per_account_values,
    price_data: dict,
    all_dates,
    data_start,
    data_end,
    withdrawal_years: int,
    monthly_withdrawal: float,
    *,
    tax_engine=None,
    withdrawal_start_age: int = 65,
    inflation: float = 0.0,
    dividend_mode: str = "reinvest",
    step_months: int = 3,
    target_percentile: float = 0.90,
) -> dict:
    """적립 분포를 11개 percentile 샘플링 → 각 가구 인출 롤링 → 합성 생존율.

    단일 RetirementPlanner의 멀티 대응. 오너결정: 멀티 인출 시작값 = 계좌별 분포의
    동일 분위 p값 합(`per_account_values[k]`의 p-percentile).

    account_specs: [{account_id, type, target_weights, cost_basis(opt)}] (value 제외)
    per_account_values: [[적립 end_value per case], ...] account_specs와 동일 순서.
    반환: {sample_results, combined_summary, message}.
    """
    sample_results = []
    wd_n_real = wd_n_synthetic = None  # 윈도우 구성은 샘플 간 동일 — 마지막 호출 값 사용
    for pct in SAMPLE_PERCENTILES:
        accounts = []
        initial_capital = 0.0
        for k, spec in enumerate(account_specs):
            value = float(np.percentile(per_account_values[k], pct))
            initial_capital += value
            accounts.append({
                "account_id":     spec["account_id"],
                "type":           spec["type"],
                "value":          value,
                "cost_basis":     spec.get("cost_basis"),
                "target_weights": spec["target_weights"],
                "rebal_mode":     spec.get("rebal_mode", "none"),
                "band_width":     spec.get("band_width", 0.05),
                "fee_rate":       spec.get("fee_rate", 0.0),       # D4
                "stock_tickers":  spec.get("stock_tickers"),       # D4
            })
        wd = analyze_household_withdrawal(
            accounts, price_data, all_dates, data_start, data_end,
            withdrawal_years, monthly_withdrawal,
            tax_engine=tax_engine, withdrawal_start_age=withdrawal_start_age,
            inflation=inflation, dividend_mode=dividend_mode, step_months=step_months,
        )
        sample_results.append({
            "percentile":      pct,
            "initial_capital": round(initial_capital),
            "success_rate":    wd["survival_rate"],
            "end_value_p50":   wd["combined_end_value"]["p50"],
            "n_windows":       wd["n_windows"],
            "total_fees":      wd.get("total_fees", 0.0),   # D4
        })
        wd_n_real, wd_n_synthetic = wd["n_real"], wd["n_synthetic"]

    success_rates = np.array([r["success_rate"] for r in sample_results])
    end_values    = np.array([r["end_value_p50"] for r in sample_results])
    survival_rate = float(np.mean(success_rates))
    target_end_value = float(np.percentile(end_values, (1 - target_percentile) * 100))

    combined_summary = {
        "survival_rate":     round(survival_rate, 4),
        "target_percentile": target_percentile,
        "target_end_value":  round(target_end_value),
        "total_withdrawal":  round(monthly_withdrawal * withdrawal_years * 12),
        "combined_end_value": {
            "mean": round(float(np.mean(end_values))),
            "std":  round(float(np.std(end_values))),
            "p10":  round(float(np.percentile(end_values, 10))),
            "p25":  round(float(np.percentile(end_values, 25))),
            "p50":  round(float(np.percentile(end_values, 50))),
            "p75":  round(float(np.percentile(end_values, 75))),
            "p90":  round(float(np.percentile(end_values, 90))),
        },
        "sample_success_rates":    success_rates.tolist(),
        "sample_initial_capitals": [r["initial_capital"] for r in sample_results],
        "n_samples":               len(sample_results),
        "total_fees":              round(float(np.median([r.get("total_fees", 0.0) for r in sample_results])), 2),  # D4

        # 인출 투영 윈도우 구성(실측/가상) — 화면에서 가상 보충 표시용(GAP-RET-KRDATA).
        "n_windows_real":          wd_n_real,
        "n_windows_synthetic":     wd_n_synthetic,
    }
    is_safe = survival_rate >= target_percentile
    return {
        "sample_results":   sample_results,
        "combined_summary": combined_summary,
        "message": {
            "survival_rate": round(survival_rate, 4),
            "is_safe":       is_safe,
            "text":          (
                f"{int(target_percentile * 100)}% 신뢰도 기준 "
                + ("인출 가능" if is_safe else "인출액 조정 권장")
                + f" (생존율 {survival_rate:.1%})"
            ),
        },
    }
