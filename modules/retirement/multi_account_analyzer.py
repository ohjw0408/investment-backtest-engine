"""
modules/retirement/multi_account_analyzer.py
Track G G1 다중 계좌 롤링 분석기.

동일한 롤링 윈도우마다 MultiAccountSimulationLoop를 한 번 실행하고,
계좌별 종료값을 시나리오 단위로 합산한 뒤 분포를 계산한다.
"""

from __future__ import annotations

from typing import Callable, Any

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta


def calc_metrics_from_history(
    history: pd.DataFrame,
    years: int,
    initial_capital: float,
    monthly_contribution: float,
    div_start: str | pd.Timestamp | None = None,
) -> dict:
    """AccumulationAnalyzer._calc_metrics와 같은 지표를 history 기반으로 계산."""
    pv = history["portfolio_value"]
    total_contribution = monthly_contribution * years * 12 + initial_capital
    end_value = float(pv.iloc[-1])
    start_value = float(pv.iloc[0])

    mdd = float(((pv - pv.cummax()) / pv.cummax()).min())

    daily_returns = pv.pct_change().dropna()
    if "cash_flow" in history.columns:
        contrib_dates = set(
            pd.to_datetime(history.loc[history["cash_flow"] > 0, "date"]).dt.normalize().tolist()
        )
        date_idx = pd.to_datetime(history.loc[daily_returns.index, "date"]).dt.normalize()
        daily_returns = daily_returns[(~date_idx.isin(contrib_dates)).values]

    std = daily_returns.std()
    sharpe = (daily_returns.mean() / std * np.sqrt(252)) if std > 0 else 0.0
    dstd = daily_returns[daily_returns < 0].std()
    sortino = (daily_returns.mean() / dstd * np.sqrt(252)) if (dstd and dstd > 0) else 0.0

    mwr = 0.0
    if "cash_flow" in history.columns:
        cf = history.loc[history["cash_flow"] != 0, ["date", "cash_flow"]].copy()
        cf = pd.concat(
            [cf, pd.DataFrame([{"date": history["date"].iloc[-1], "cash_flow": end_value}])],
            ignore_index=True,
        )
        cf["date"] = pd.to_datetime(cf["date"])
        cf = cf.sort_values("date").reset_index(drop=True)
        cfs = [-c for c in cf["cash_flow"].iloc[:-1].tolist()] + [float(cf["cash_flow"].iloc[-1])]
        if len(cfs) >= 2 and any(c < 0 for c in cfs) and any(c > 0 for c in cfs):
            try:
                rate = 0.01
                for _ in range(200):
                    npv = sum(c / (1 + rate) ** i for i, c in enumerate(cfs))
                    dnpv = sum(-i * c / (1 + rate) ** (i + 1) for i, c in enumerate(cfs))
                    if abs(dnpv) < 1e-12:
                        break
                    nr = rate - npv / dnpv
                    if abs(nr - rate) < 1e-8:
                        rate = nr
                        break
                    rate = nr
                if -0.9 < rate < 10.0:
                    mwr = (1 + rate) ** 12 - 1
            except Exception:
                mwr = 0.0

    if mwr != 0.0:
        cagr = mwr
    elif total_contribution > 0 and end_value > 0:
        cagr = (end_value / total_contribution) ** (1 / years) - 1
    elif start_value > 0 and end_value > 0:
        cagr = (end_value / start_value) ** (1 / years) - 1
    else:
        cagr = 0.0

    calmar = cagr / abs(mdd) if mdd != 0 else 0.0

    dividend_cagr = 0.0
    dividend_mdd = 0.0
    total_dividend = 0.0
    last_year_dividend = 0.0
    dividend_yield_on_cost = 0.0

    if "dividend_income" in history.columns:
        h = history.copy()
        h["_date"] = pd.to_datetime(h["date"])
        if div_start is not None:
            h = h[h["_date"] >= pd.Timestamp(div_start)]

        total_dividend = float(h["dividend_income"].sum())
        h = h.copy()
        h["_year"] = h["_date"].dt.year
        h["_month"] = h["_date"].dt.month
        full_years = set(
            h.groupby("_year")["_month"].nunique()
            .pipe(lambda s: s[s >= 12]).index
        )
        h_full = h[h["_year"].isin(full_years)]

        if not h_full.empty:
            annual_div_abs = h_full.groupby("_year")["dividend_income"].sum()
            qty_cols = [c for c in h_full.columns if c.endswith("_quantity")]
            if qty_cols:
                annual_avg_qty = h_full.groupby("_year")[qty_cols].mean().sum(axis=1)
                valid = annual_avg_qty[annual_avg_qty > 0].index
                annual_div_abs = annual_div_abs[annual_div_abs.index.isin(valid)]
                annual_avg_qty = annual_avg_qty[annual_avg_qty.index.isin(valid)]
                annual_dps = (annual_div_abs / annual_avg_qty)
                annual_dps = annual_dps[annual_dps > 0]
                if len(annual_dps) >= 2:
                    n_y = len(annual_dps) - 1
                    if annual_dps.iloc[0] > 0 and n_y > 0:
                        dividend_cagr = (annual_dps.iloc[-1] / annual_dps.iloc[0]) ** (1 / n_y) - 1
                    roll_max = annual_dps.cummax()
                    dividend_mdd = float(((annual_dps - roll_max) / roll_max).min())
            else:
                annual_pv_mean = h_full.groupby("_year")["portfolio_value"].mean()
                annual_yield = annual_div_abs / annual_pv_mean
                annual_yield = annual_yield[annual_yield > 0]
                if len(annual_yield) >= 2:
                    n_y = len(annual_yield) - 1
                    if annual_yield.iloc[0] > 0 and n_y > 0:
                        dividend_cagr = (annual_yield.iloc[-1] / annual_yield.iloc[0]) ** (1 / n_y) - 1
                    roll_max = annual_yield.cummax()
                    dividend_mdd = float(((annual_yield - roll_max) / roll_max).min())

            if len(annual_div_abs) > 0:
                last_year_dividend = float(annual_div_abs.iloc[-1])
            if total_contribution > 0 and last_year_dividend > 0:
                dividend_yield_on_cost = last_year_dividend / total_contribution

    return {
        "cagr": cagr,
        "mdd": mdd,
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "calmar": float(calmar),
        "mwr": float(mwr),
        "dividend_cagr": float(dividend_cagr),
        "dividend_mdd": float(dividend_mdd),
        "total_dividend": float(total_dividend),
        "last_year_dividend": float(last_year_dividend),
        "dividend_yield_on_cost": float(dividend_yield_on_cost),
    }


class MultiAccountAnalyzer:
    def __init__(
        self,
        portfolio_engine,
        accounts: list[dict[str, Any]],
        data_start: str,
        data_end: str,
        accumulation_years: int,
        dividend_mode: str = "reinvest",
        step_months: int = 1,
        tax_enabled: bool = False,
        user_settings: dict | None = None,
        progress_callback=None,
        price_provider: Callable | None = None,
        use_synthetic: bool = False,
        div_start: str | None = None,
    ):
        self.portfolio_engine = portfolio_engine
        self.accounts = accounts
        self.data_start = pd.Timestamp(data_start)
        self.data_end = pd.Timestamp(data_end)
        self.accumulation_years = accumulation_years
        self.dividend_mode = dividend_mode
        self.step_months = step_months
        self.tax_enabled = tax_enabled
        self.user_settings = user_settings or {}
        self.progress_callback = progress_callback
        self.price_provider = price_provider
        self.use_synthetic = use_synthetic
        self.div_start = div_start

    def run(self) -> dict:
        cases = self._run_rolling()
        if not cases:
            raise ValueError("롤링 케이스가 0개입니다.")

        combined_distribution = self._fit_distribution(cases)
        account_outputs = []
        for idx, account in enumerate(self.accounts):
            account_cases = [c["accounts"][idx] for c in cases if len(c.get("accounts", [])) > idx]
            account_outputs.append({
                "account_id": idx,
                "type": account.get("type", "위탁"),
                "distribution": self._fit_distribution(account_cases) if account_cases else {},
                "cases": account_cases,
            })

        combined = dict(combined_distribution["end_value"])
        combined["distribution"] = combined_distribution
        combined["cases"] = cases

        return {
            "combined": combined,
            "accounts": account_outputs,
            "cases": cases,
            "cases_count": len(cases),
        }

    def _estimate_total_cases(self) -> int:
        cur = self.data_start
        count = 0
        while True:
            end = cur + relativedelta(years=self.accumulation_years)
            if end > self.data_end:
                break
            count += 1
            cur += relativedelta(months=self.step_months)
        return max(count, 1)

    def _run_rolling(self) -> list[dict[str, Any]]:
        import time
        from modules.config.simulation_config import SimulationConfig
        from modules.rebalance.periodic import PeriodicRebalance
        from modules.simulation.multi_account_loop import MultiAccountSimulationLoop

        total_cases = self._estimate_total_cases() if self.progress_callback else 0
        start_time = time.time()
        cases: list[dict[str, Any]] = []
        cur = self.data_start
        run_id = 1

        while True:
            end = cur + relativedelta(years=self.accumulation_years)
            if end > self.data_end:
                break

            all_tickers = self._all_tickers()
            try:
                price_data, dates = self._load_prices(
                    all_tickers,
                    cur.strftime("%Y-%m-%d"),
                    end.strftime("%Y-%m-%d"),
                )
            except Exception:
                cur += relativedelta(months=self.step_months)
                run_id += 1
                continue

            loop_accounts = []
            for account in self.accounts:
                tickers = [t["code"] for t in account["tickers"]]
                weights = {t["code"]: float(t["weight"]) for t in account["tickers"]}
                rebal_mode = account.get("rebal_mode", "monthly")
                band_width = float(account.get("band_width", 0.05))
                rebalance_frequency = None if rebal_mode in ("none", "band") else rebal_mode
                drift_threshold = band_width if rebal_mode == "band" else None
                strategy = PeriodicRebalance(
                    target_weights=weights,
                    rebalance_frequency=rebalance_frequency,
                    drift_threshold=drift_threshold,
                )
                config = SimulationConfig(
                    start_date=cur.strftime("%Y-%m-%d"),
                    end_date=end.strftime("%Y-%m-%d"),
                    tickers=tickers,
                    target_weights=weights,
                    initial_capital=float(account.get("initial_capital", 0.0)),
                    monthly_contribution=float(account.get("monthly_contribution", 0.0)),
                    contribution_end_months=account.get("contribution_end_months"),
                    withdrawal_amount=0,
                    dividend_mode=account.get("dividend_mode", self.dividend_mode),
                    rebalance_frequency=rebalance_frequency,
                    inflation=0.0,
                )
                loop_accounts.append({
                    "type": account.get("type", "위탁"),
                    "config": config,
                    "strategy": strategy,
                    "gain_harvesting": account.get("gain_harvesting", False),
                    "isa_years_held": account.get("isa_years_held", 3),
                })

            run_result = MultiAccountSimulationLoop(transfers_enabled=False).run(
                accounts=loop_accounts,
                price_data=price_data,
                dates=dates,
                tax_enabled=self.tax_enabled,
                user_settings=self.user_settings,
            )

            history_df = run_result.combined_history_df
            if history_df.empty:
                cur += relativedelta(months=self.step_months)
                run_id += 1
                continue

            total_initial = sum(float(a.get("initial_capital", 0.0)) for a in self.accounts)
            total_monthly = sum(float(a.get("monthly_contribution", 0.0)) for a in self.accounts)
            metrics = calc_metrics_from_history(
                history_df,
                self.accumulation_years,
                total_initial,
                total_monthly,
                self.div_start,
            )
            raw_final = float(history_df["portfolio_value"].iloc[-1])
            final_value = float(run_result.combined_end_value)
            metrics["run_id"] = run_id
            metrics["start"] = cur.strftime("%Y-%m-%d")
            metrics["end"] = end.strftime("%Y-%m-%d")
            metrics["end_value"] = final_value
            metrics["raw_end_value"] = raw_final
            if final_value != raw_final:
                positive_cf = history_df.loc[history_df["cash_flow"] > 0, "cash_flow"].sum()
                if positive_cf > 0 and final_value > 0 and self.accumulation_years > 0:
                    metrics["cagr"] = (final_value / positive_cf) ** (1.0 / self.accumulation_years) - 1

            account_cases = []
            for account_result, source_account in zip(run_result.account_results, self.accounts):
                account_history = account_result["history_df"]
                account_metrics = calc_metrics_from_history(
                    account_history,
                    self.accumulation_years,
                    float(source_account.get("initial_capital", 0.0)),
                    float(source_account.get("monthly_contribution", 0.0)),
                    self.div_start,
                )
                account_metrics["account_id"] = account_result["account_id"]
                account_metrics["type"] = account_result["type"]
                account_metrics["end_value"] = float(account_result["end_value"])
                account_metrics["raw_end_value"] = float(account_result["raw_end_value"])
                account_metrics["tax_paid"] = float(account_result["tax_paid"])
                account_cases.append(account_metrics)

            metrics["accounts"] = account_cases
            cases.append(metrics)

            if self.progress_callback:
                self.progress_callback(
                    current=run_id,
                    total=total_cases,
                    elapsed=time.time() - start_time,
                )

            cur += relativedelta(months=self.step_months)
            run_id += 1

        return cases

    def _all_tickers(self) -> list[str]:
        seen = []
        for account in self.accounts:
            for ticker in account["tickers"]:
                code = ticker["code"]
                if code not in seen:
                    seen.append(code)
        return seen

    def _load_prices(self, tickers: list[str], start_date: str, end_date: str):
        if self.price_provider is not None:
            return self.price_provider(
                tickers,
                start_date,
                end_date,
                allow_synthetic=self.use_synthetic,
            )
        return self.portfolio_engine.price_loader.load(
            tickers,
            start_date,
            end_date,
            allow_synthetic=self.use_synthetic,
        )

    def _fit_distribution(self, cases: list[dict[str, Any]]) -> dict:
        keys = [
            "end_value", "cagr", "mdd", "sharpe", "sortino",
            "calmar", "mwr", "dividend_cagr", "dividend_mdd",
            "total_dividend", "last_year_dividend", "dividend_yield_on_cost",
        ]
        result = {}
        for key in keys:
            v = np.array([c.get(key, 0.0) for c in cases], dtype=float)
            result[key] = {
                "mean": float(np.mean(v)),
                "std": float(np.std(v)),
                "p10": float(np.percentile(v, 10)),
                "p25": float(np.percentile(v, 25)),
                "p50": float(np.percentile(v, 50)),
                "p75": float(np.percentile(v, 75)),
                "p90": float(np.percentile(v, 90)),
                "values": v.tolist(),
            }
        return result
