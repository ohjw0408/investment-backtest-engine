"""
modules/simulation/multi_account_loop.py
G1 다중 계좌 통합 시간 루프.

한 시나리오 안에서 여러 계좌 포트폴리오를 같은 날짜축으로 동시에 운용한다.
G1에서는 transfers_enabled=False만 지원하며, 계좌 간 이동 단계는 생략한다.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class MultiAccountRunResult:
    combined_history_df: pd.DataFrame
    combined_end_value: float
    account_results: list[dict[str, Any]]
    transfer_log: list[dict[str, Any]] = field(default_factory=list)


class MultiAccountSimulationLoop:
    """N개 계좌를 하나의 날짜 루프에서 동시에 운용하는 오케스트레이터."""

    def __init__(self, transfers_enabled: bool = False):
        self.transfers_enabled = transfers_enabled

    def run(
        self,
        accounts: list[dict[str, Any]],
        price_data: dict[str, pd.DataFrame],
        dates,
        tax_enabled: bool = False,
        user_settings: dict | None = None,
        progress_callback=None,
        record_history: bool = True,
        distribution_policy=None,
    ) -> MultiAccountRunResult:
        if not accounts:
            raise ValueError("계좌가 없습니다.")
        if not dates:
            raise ValueError("시뮬레이션 날짜가 없습니다.")

        user_settings = user_settings or {}

        # G2: 정책 목적지가 없는 계좌를 가리키면 위탁 자동 싱크(첫 ISA 미러) 생성
        if self.transfers_enabled and distribution_policy is not None:
            accounts, distribution_policy = self._ensure_sync_accounts(
                accounts, distribution_policy
            )

        runtimes = [
            self._build_runtime(i, account, tax_enabled, user_settings, dates)
            for i, account in enumerate(accounts)
        ]

        # G2 라우팅 상태(transfers OFF면 전부 미사용 → G1 동작 그대로)
        tracker = None
        account_types: dict[int, str] = {}
        transfer_log: list[dict[str, Any]] = []
        loop_last_month = None
        self._transfer_month_idx = 0
        if self.transfers_enabled:
            from modules.tax.account_tax import ContributionLimitTracker
            tracker = ContributionLimitTracker()
            tracker.touch(dates[0])
            account_types = {rt["account_id"]: rt["account_type"] for rt in runtimes}
            # 초기자본도 한도 소비(ISA 연/총)
            for rt in runtimes:
                init = float(getattr(rt["config"], "initial_capital", 0.0) or 0.0)
                if init > 0:
                    tracker.record(rt["account_id"], rt["account_type"], init)

        price_array: dict[str, Any] = {}
        valid_index: dict[str, Any] = {}
        for ticker, df in price_data.items():
            price_array[ticker] = df["close"].values
            valid_index[ticker] = df.index

        combined_rows: list[dict[str, Any]] = []
        total_dates = len(dates)
        update_step = max(1, total_dates // 20)

        import time as _time
        start_time = _time.time() if progress_callback else None

        for i, date in enumerate(dates):
            combined_value = 0.0
            combined_cash = 0.0
            combined_dividend = 0.0
            combined_cash_flow = 0.0
            active_accounts = 0
            account_values: dict[str, float] = {}

            # G2: 월 경계에서만 납입 라우팅(상한+cascade) 계산. 비경계 = 납입 0.
            injections: dict[int, float] | None = None
            if self.transfers_enabled:
                cur_m = (date.year, date.month)
                if cur_m != loop_last_month:
                    loop_last_month = cur_m
                    injections = self._compute_injections(
                        runtimes, tracker, account_types,
                        distribution_policy, date, transfer_log,
                    )
                else:
                    injections = {}

            for rt in runtimes:
                price_dict = self._price_dict_for_account(
                    rt["config"].tickers, price_array, valid_index, i, date
                )
                if not price_dict:
                    continue

                override = None
                if self.transfers_enabled:
                    override = float(injections.get(rt["account_id"], 0.0)) if injections else 0.0

                dividend_by_ticker, cash_flow = self._step_account(
                    rt, price_data, price_dict, date, contribution_override=override
                )
                portfolio = rt["portfolio"]
                total_value = float(portfolio.total_value(price_dict))

                if record_history:
                    rt["recorder"].record(
                        date,
                        portfolio,
                        price_dict,
                        rt["config"].tickers,
                        dividend_by_ticker,
                        cash_flow=cash_flow,
                    )

                active_accounts += 1
                combined_value += total_value
                combined_cash += float(portfolio.cash)
                combined_dividend += float(sum(dividend_by_ticker.values()))
                combined_cash_flow += float(cash_flow)
                account_values[f"account_{rt['account_id']}_value"] = total_value

            if record_history and active_accounts > 0:
                combined_rows.append({
                    "date": date,
                    "portfolio_value": combined_value,
                    "asset_value": combined_value - combined_cash,
                    "cash": combined_cash,
                    "dividend_income": combined_dividend,
                    "cash_flow": combined_cash_flow,
                    **account_values,
                })

            if progress_callback and i % update_step == 0:
                progress_callback(
                    current=i + 1,
                    total=total_dates,
                    elapsed=_time.time() - start_time,
                )

        account_results = [self._finalize_account(rt, price_data) for rt in runtimes]
        combined_history_df = pd.DataFrame(combined_rows)
        if not combined_history_df.empty:
            combined_history_df = combined_history_df.sort_values("date").reset_index(drop=True)

        return MultiAccountRunResult(
            combined_history_df=combined_history_df,
            combined_end_value=float(sum(r["end_value"] for r in account_results)),
            account_results=account_results,
            transfer_log=transfer_log,
        )

    def _compute_injections(
        self,
        runtimes: list[dict[str, Any]],
        tracker,
        account_types: dict[int, str],
        distribution_policy,
        date,
        transfer_log: list[dict[str, Any]],
    ) -> dict[int, float]:
        """월 경계 1회: 각 계좌의 실제 납입액 계산.

        - ISA: 연 2천만/총 1억 한도까지만 흡수. 초과분은 정책대로 cascade.
        - 연금/IRP: 합산 연 1800만 한도 내 base 납입.
        - 위탁: 무제한.
        반환 = {account_id: 이번 달 실제 주입액}
        """
        from modules.tax.account_tax import route_overflow

        idx = self._transfer_month_idx
        self._transfer_month_idx += 1
        tracker.touch(date)

        injections: dict[int, float] = defaultdict(float)
        isa_overflow_total = 0.0
        for rt in runtimes:
            config = rt["config"]
            cap_m = getattr(config, "contribution_end_months", None)
            base = (
                0.0
                if (cap_m is not None and idx >= cap_m)
                else float(config.monthly_contribution or 0.0)
            )
            if base <= 0:
                continue
            aid = rt["account_id"]
            atype = rt["account_type"]
            if atype == "ISA":
                cap = tracker.capacity(aid, "ISA")
                absorbed = min(base, cap)
                tracker.record(aid, "ISA", absorbed)
                injections[aid] += absorbed
                overflow = base - absorbed
                if overflow > 1e-9:
                    isa_overflow_total += overflow
            else:
                cap = tracker.capacity(aid, atype)
                give = min(base, cap)
                tracker.record(aid, atype, give)
                injections[aid] += give

        if isa_overflow_total > 1e-9 and distribution_policy is not None:
            allocs, leftover = route_overflow(
                isa_overflow_total, distribution_policy, tracker, account_types
            )
            for dest_id, amt in allocs:
                injections[dest_id] += amt
            transfer_log.append({
                "date": str(getattr(date, "date", lambda: date)()),
                "overflow": isa_overflow_total,
                "allocations": allocs,
                "leftover": leftover,
            })

        return dict(injections)

    def _ensure_sync_accounts(self, accounts, distribution_policy):
        """정책 목적지가 없는 계좌(account_id >= len)를 가리키면 위탁 자동 싱크 생성.

        싱크 계좌 = 첫 ISA의 종목·비중 미러(같은 전략으로 굴림), 초기·월납입 0.
        라우팅 수신액만으로 운용되어 위탁 세율이 청산 시 적용된다.
        """
        from modules.config.simulation_config import SimulationConfig
        from modules.rebalance.periodic import PeriodicRebalance
        from modules.tax.account_tax import DistributionPolicy, DistributionDestination

        accounts = list(accounts)
        isa = next((a for a in accounts if a.get("type") == "ISA"), None)
        resolved: list = []
        for dest in distribution_policy.destinations:
            if dest.account_id < len(accounts):
                resolved.append(dest)
                continue
            if isa is None:
                resolved.append(dest)  # 미러 소스 없음 → 흡수 0(존재 안 함)
                continue
            src = isa["config"]
            weights = dict(src.target_weights)
            rebal = getattr(src, "rebalance_frequency", None)
            cfg = SimulationConfig(
                start_date=src.start_date,
                end_date=src.end_date,
                tickers=list(src.tickers),
                target_weights=weights,
                initial_capital=0.0,
                monthly_contribution=0.0,
                withdrawal_amount=0,
                dividend_mode=src.dividend_mode,
                rebalance_frequency=rebal,
                inflation=0.0,
            )
            new_id = len(accounts)
            accounts.append({
                "type": "위탁",
                "config": cfg,
                "strategy": PeriodicRebalance(weights, rebalance_frequency=rebal),
                "gain_harvesting": False,
            })
            resolved.append(DistributionDestination(account_id=new_id, cap=dest.cap))

        return accounts, DistributionPolicy(destinations=resolved)

    def _build_runtime(
        self,
        account_id: int,
        account: dict[str, Any],
        tax_enabled: bool,
        user_settings: dict,
        dates,
    ) -> dict[str, Any]:
        from modules.core.portfolio import Portfolio, TaxTrackedPortfolio
        from modules.execution.cash_allocator import CashAllocator
        from modules.execution.order_executor import OrderExecutor, TaxedOrderExecutor
        from modules.simulation.contribution_engine import ContributionEngine
        from modules.simulation.dividend_engine import DividendEngine
        from modules.simulation.history_recorder import HistoryRecorder
        from modules.simulation.withdrawal_engine import WithdrawalEngine
        from modules.tax.base_tax import TaxEngine
        from modules.tax.account_tax import TaxedDividendEngine

        config = account["config"]
        account_type = account.get("type", "위탁")
        gain_harvesting = bool(account.get("gain_harvesting", False))

        if tax_enabled:
            tax_engine = account.get("tax_engine") or TaxEngine(user_settings)
            div_engine = TaxedDividendEngine(DividendEngine(), tax_engine, account_type)
            executor = TaxedOrderExecutor(
                tax_engine,
                account_type,
                gain_harvesting=gain_harvesting,
            )
            portfolio = TaxTrackedPortfolio(config.initial_capital)
        else:
            tax_engine = None
            div_engine = DividendEngine()
            executor = OrderExecutor()
            portfolio = Portfolio(config.initial_capital)

        return {
            "account_id": account_id,
            "account_type": account_type,
            "config": config,
            "strategy": account["strategy"],
            "tax_engine": tax_engine,
            "isa_years_held": int(account.get("isa_years_held", 3)),
            "dividend_engine": div_engine,
            "contribution_engine": ContributionEngine(),
            "withdrawal_engine": WithdrawalEngine(),
            "executor": executor,
            "cash_allocator": CashAllocator(),
            "portfolio": portfolio,
            "recorder": HistoryRecorder(),
            "last_month": None,
            "last_withdrawal_month": (dates[0].year, dates[0].month) if dates else None,
            "elapsed_months": 0,
            "last_inflation_month": None,
            "is_first_day": True,
            "last_cf_month": None,
            "initial_capital_cf": 0.0,
            "dividend_tax_paid": 0.0,
        }

    def _price_dict_for_account(
        self,
        tickers: list[str],
        price_array: dict[str, Any],
        valid_index: dict[str, Any],
        i: int,
        date,
    ) -> dict[str, float]:
        price_dict: dict[str, float] = {}
        for ticker in tickers:
            if ticker not in valid_index or date not in valid_index[ticker]:
                continue
            arr = price_array[ticker]
            if i >= len(arr):
                continue
            price = arr[i]
            if price is None or price != price or price <= 0:
                continue
            price_dict[ticker] = float(price)
        return price_dict

    def _step_account(
        self, rt: dict[str, Any], price_data, price_dict, date,
        contribution_override: float | None = None,
    ) -> tuple[dict, float]:
        portfolio = rt["portfolio"]
        config = rt["config"]
        strategy = rt["strategy"]

        current_month = (date.year, date.month)
        if rt["last_inflation_month"] is None:
            rt["last_inflation_month"] = current_month
        elif current_month != rt["last_inflation_month"]:
            rt["elapsed_months"] += 1
            rt["last_inflation_month"] = current_month

        if rt["is_first_day"]:
            rt["is_first_day"] = False
            rt["initial_capital_cf"] = getattr(config, "initial_capital", 0.0)
            cash_target = config.target_weights.get("CASH", 0)
            if cash_target == 0 and portfolio.cash > 0:
                rt["cash_allocator"].allocate_cash(portfolio, price_dict, config.target_weights)

        gross_dividend_by_ticker = self._gross_dividend_by_ticker(
            portfolio,
            price_data,
            date,
            taxed=hasattr(rt["dividend_engine"], "tax_engine"),
        )
        dividend_by_ticker = rt["dividend_engine"].process(
            portfolio,
            price_data,
            price_dict,
            date,
            config.dividend_mode,
        )
        if gross_dividend_by_ticker:
            dividend_tax = sum(
                max(0.0, gross - float(dividend_by_ticker.get(ticker, 0.0)))
                for ticker, gross in gross_dividend_by_ticker.items()
            )
            if dividend_tax > 0:
                portfolio.cash = max(0.0, portfolio.cash - dividend_tax)
                rt["dividend_tax_paid"] += dividend_tax
        dividend_total = sum(dividend_by_ticker.values())
        if config.dividend_mode == "withdraw" and dividend_total > 0:
            portfolio.cash -= dividend_total

        if contribution_override is not None:
            # transfers 경로: 루프가 월 경계에서 계산한 실제 납입액(상한+라우팅 반영).
            # 월 1회 게이팅은 루프가 책임지므로 ContributionEngine 우회.
            effective_monthly = float(contribution_override)
            if effective_monthly > 0:
                portfolio.cash += effective_monthly
                cash_target = config.target_weights.get("CASH", 0)
                if cash_target == 0:
                    rt["cash_allocator"].allocate_cash(portfolio, price_dict, config.target_weights)
        else:
            effective_monthly = (
                0.0
                if (
                    getattr(config, "contribution_end_months", None) is not None
                    and rt["elapsed_months"] >= config.contribution_end_months
                )
                else config.monthly_contribution
            )
            rt["last_month"] = rt["contribution_engine"].process(
                portfolio,
                effective_monthly,
                date,
                rt["last_month"],
            )
            if effective_monthly > 0:
                cash_target = config.target_weights.get("CASH", 0)
                if cash_target == 0:
                    rt["cash_allocator"].allocate_cash(portfolio, price_dict, config.target_weights)

        rt["last_withdrawal_month"] = rt["withdrawal_engine"].process(
            portfolio,
            config.withdrawal_amount,
            price_dict,
            config.target_weights,
            date=date,
            last_month=rt["last_withdrawal_month"],
            elapsed_months=rt["elapsed_months"],
            inflation=getattr(config, "inflation", 0.0),
        )

        if strategy.should_rebalance(date, portfolio, price_dict):
            orders = strategy.generate_orders(portfolio, price_dict)
            rt["executor"].execute_orders(portfolio, orders, price_dict, date=date)

        if hasattr(rt["executor"], "maybe_gain_harvest"):
            rt["executor"].maybe_gain_harvest(portfolio, price_dict, date)

        if config.dividend_mode in ("reinvest", "withdraw") and config.withdrawal_amount == 0:
            cash_target = config.target_weights.get("CASH", 0)
            if cash_target == 0:
                rt["cash_allocator"].allocate_cash(portfolio, price_dict, config.target_weights)

        if current_month != rt["last_cf_month"]:
            rt["last_cf_month"] = current_month
            cash_flow = effective_monthly - config.withdrawal_amount
            if rt["initial_capital_cf"] > 0:
                cash_flow += rt["initial_capital_cf"]
                rt["initial_capital_cf"] = 0.0
        else:
            cash_flow = 0.0

        return dividend_by_ticker, float(cash_flow)

    def _gross_dividend_by_ticker(self, portfolio, price_data, date, taxed: bool) -> dict[str, float]:
        if not taxed:
            return {}
        gross: dict[str, float] = {}
        for ticker, position in portfolio.positions.items():
            if ticker not in price_data or date not in price_data[ticker].index:
                continue
            dividend = price_data[ticker].loc[date, "dividend"]
            if dividend > 0:
                gross[ticker] = float(dividend) * float(position.quantity)
        return gross

    def _finalize_account(self, rt: dict[str, Any], price_data: dict[str, pd.DataFrame]) -> dict[str, Any]:
        history_df = rt["recorder"].to_dataframe()
        if history_df.empty:
            return {
                "account_id": rt["account_id"],
                "type": rt["account_type"],
                "history_df": history_df,
                "raw_end_value": 0.0,
                "end_value": 0.0,
                "total_contribution": 0.0,
                "tax_paid": 0.0,
            }

        config = rt["config"]
        raw_end_value = float(history_df["portfolio_value"].iloc[-1])
        positive_cash_flow = history_df.loc[history_df["cash_flow"] > 0, "cash_flow"]
        total_contribution = float(positive_cash_flow.sum())
        end_value = raw_end_value
        liquidation_tax = 0.0
        kr_foreign_unrealized_gain = 0.0

        tax_engine = rt.get("tax_engine")
        if tax_engine is not None:
            from modules.tax.liquidation import apply_liquidation_tax

            last_prices = {
                t: float(price_data[t]["close"].iloc[-1])
                for t in config.tickers
                if t in price_data and not price_data[t].empty
            }
            ytd_us_gains = getattr(rt["executor"], "_ytd_us_gains", 0.0)
            end_value = apply_liquidation_tax(
                end_value=raw_end_value,
                portfolio=rt["portfolio"],
                last_prices=last_prices,
                tax_engine=tax_engine,
                account_type=rt["account_type"],
                total_contribution=total_contribution,
                ytd_us_realized_gains=ytd_us_gains,
                age=getattr(tax_engine, "age", 40),
                isa_years_held=rt.get("isa_years_held", 3),
            )
            liquidation_tax = max(0.0, raw_end_value - end_value)
            if rt["account_type"] == "위탁" and hasattr(rt["portfolio"], "positions"):
                for ticker, pos in rt["portfolio"].positions.items():
                    if ticker in last_prices and pos.quantity > 0:
                        if tax_engine.classify_asset(ticker) == "KR_FOREIGN":
                            gain = rt["portfolio"].unrealized_gain(ticker, last_prices[ticker])
                            if gain > 0:
                                kr_foreign_unrealized_gain += gain

        dividend_tax = float(rt.get("dividend_tax_paid", 0.0))
        realized_tax = float(getattr(rt["executor"], "total_cg_tax_paid", 0.0))

        return {
            "account_id": rt["account_id"],
            "type": rt["account_type"],
            "history_df": history_df,
            "raw_end_value": raw_end_value,
            "end_value": float(end_value),
            "total_contribution": total_contribution,
            "tax_paid": dividend_tax + realized_tax + liquidation_tax,
            "dividend_tax_paid": dividend_tax,
            "realized_tax_paid": realized_tax,
            "liquidation_tax_paid": liquidation_tax,
            "kr_foreign_unrealized_gain": kr_foreign_unrealized_gain,
            "portfolio": rt["portfolio"],
        }
