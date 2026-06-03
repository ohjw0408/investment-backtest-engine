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

    return {
        "account_id":     spec["account_id"],
        "type":           atype,
        "portfolio":      pf,
        "executor":       executor,
        "div_engine":     div_engine,
        "allocator":      allocator,
        "strategy":       PeriodicRebalance(weights, rebalance_frequency=None),
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
                price_dict[ticker] = price_array[ticker][i]
        if not price_dict:
            continue

        current_month = (date.year, date.month)
        if last_infl_month is None:
            last_infl_month = current_month
        elif current_month != last_infl_month:
            elapsed_months += 1
            last_infl_month = current_month

        # 첫 유효일: 계좌 런타임 구성(초기 매수)
        if runtimes is None:
            runtimes = [
                _build_account_runtime(s, price_dict, tax_engine, session)
                for s in accounts
            ]

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
            last_price[ticker] = price_array[ticker][last_i]
    # 마지막 유효 가격 폴백
    for ticker in price_data:
        if ticker not in last_price:
            last_price[ticker] = price_array[ticker][-1]

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
    if not windows:
        raise ValueError("롤링 윈도우가 0개입니다 (데이터 부족).")

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

    if not case_results:
        raise ValueError("유효 윈도우가 0개입니다.")

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
