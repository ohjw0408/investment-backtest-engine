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

    if tax_engine is not None:
        pf = TaxTrackedPortfolio(value)
        executor = TaxedOrderExecutor(tax_engine, atype, session=session)
        div_engine = _make_taxed_dividend_engine(tax_engine, atype, session)
    else:
        pf = Portfolio(value)
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

        # 계좌별 배당
        for rt in runtimes:
            rt["div_engine"].process(
                rt["portfolio"], price_data, price_dict, date, dividend_mode
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
    for rt in runtimes:
        ev = rt["portfolio"].total_value(last_price)
        per_account.append({
            "account_id": rt["account_id"], "type": rt["type"],
            "end_value": round(ev, 2),
        })
        combined += ev

    return {
        "success":            success,
        "fail_month":         fail_month,
        "combined_end_value": round(combined, 2),
        "per_account":        per_account,
        "total_pension_tax":  round(total_pension_tax, 2),
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


def _synthetic_household_window(
    accounts, ticker_stats, withdrawal_years, monthly_net, rng,
    *, tax_engine, withdrawal_start_age, inflation, dividend_mode,
) -> dict:
    """티커별 GBM(Student-t) 합성 월가격 경로 생성 → simulate_household_window 1회.

    종목 간 상관은 독립 근사(단일 합성도 미모델링). 합성 구간 배당 0.
    드레인 순서·연금세·취득가·리밸은 simulate_household_window가 그대로 처리.
    """
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
        ticker_stats = {
            t: _ticker_return_stats(df["close"].values)
            for t, df in price_data.items()
        }
        for i in range(n_needed):
            rng = np.random.default_rng(seed=1000 + i)
            try:
                case_results.append(_synthetic_household_window(
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

    return {
        "survival_rate":      round(survival_rate, 4),
        "n_windows":          len(case_results),
        "n_real":             n_real,
        "n_synthetic":        n_synthetic,
        "combined_end_value": _pct_dist(combined_vals),
        "per_account":        per_account_dist,
        "median_pension_tax": round(float(np.median(pension_taxes)), 2),
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
