"""
modules/simulation/multi_account_loop.py
G1 다중 계좌 통합 시간 루프.

한 시나리오 안에서 여러 계좌 포트폴리오를 같은 날짜축으로 동시에 운용한다.
G1에서는 transfers_enabled=False만 지원하며, 계좌 간 이동 단계는 생략한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class MultiAccountRunResult:
    combined_history_df: pd.DataFrame
    combined_end_value: float
    account_results: list[dict[str, Any]]


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
    ) -> MultiAccountRunResult:
        if self.transfers_enabled:
            raise NotImplementedError("G1은 transfers_enabled=False만 지원합니다.")
        if not accounts:
            raise ValueError("계좌가 없습니다.")
        if not dates:
            raise ValueError("시뮬레이션 날짜가 없습니다.")

        user_settings = user_settings or {}
        runtimes = [
            self._build_runtime(i, account, tax_enabled, user_settings, dates)
            for i, account in enumerate(accounts)
        ]

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

            for rt in runtimes:
                price_dict = self._price_dict_for_account(
                    rt["config"].tickers, price_array, valid_index, i, date
                )
                if not price_dict:
                    continue

                dividend_by_ticker, cash_flow = self._step_account(rt, price_data, price_dict, date)
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
        )

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

    def _step_account(self, rt: dict[str, Any], price_data, price_dict, date) -> tuple[dict, float]:
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
