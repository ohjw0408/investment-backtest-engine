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


# use_synthetic=True 시 롤링 케이스를 이 개수까지 윈도우별 독립 합성으로 보충한다.
# (체크박스 OFF면 보충 없음 — 순수 실데이터 롤링)
TARGET_SYNTHETIC_CASES = 40


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
    # 초기 일시금만 있는 경우에는 IRR을 월수익률처럼 연율화하면 왜곡된다.
    if monthly_contribution > 0 and "cash_flow" in history.columns:
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
    if monthly_contribution > 0 and "cash_flow" in history.columns:
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

    if not np.isfinite(mwr):
        mwr = 0.0   # IRR 발산(내부이동만 받은 계좌 등) → 0 처리(JSON Infinity 방지)

    if mwr != 0.0:
        cagr = mwr
    elif total_contribution > 0 and end_value > 0:
        cagr = (end_value / total_contribution) ** (1 / years) - 1
    elif start_value > 0 and end_value > 0:
        cagr = (end_value / start_value) ** (1 / years) - 1
    else:
        cagr = 0.0

    if not np.isfinite(cagr):
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
        transfers_enabled: bool = False,
        distribution_policy=None,
        manual_comprehensive_years=None,
        reinvest_tax_credit: bool = False,
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
        self.transfers_enabled = transfers_enabled
        self.distribution_policy = distribution_policy
        self.manual_comprehensive_years = set(manual_comprehensive_years or ())
        self.reinvest_tax_credit = bool(reinvest_tax_credit)
        self._synth_params: dict = {}

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
            "savings": self._build_savings(account_outputs),
        }

    def _build_savings(self, account_outputs: list[dict]) -> dict:
        """절세액 표시(3종): 위탁가정세금·실제세금·절세액.

        계좌별 = 케이스 분포의 p50(중앙값). 합산 = 계좌별 p50의 단순합(화면 일치).
        """
        per_account = []
        for ao in account_outputs:
            dist = ao.get("distribution", {})
            per_account.append({
                "account_id": ao["account_id"],
                "type": ao["type"],
                "brokerage_assumed_tax": float(dist.get("brokerage_assumed_tax", {}).get("p50", 0.0)),
                "actual_tax": float(dist.get("tax_paid", {}).get("p50", 0.0)),
                "tax_saving": float(dist.get("tax_saving", {}).get("p50", 0.0)),
                "gain_harvest_saving": float(dist.get("gain_harvest_saving", {}).get("p50", 0.0)),
            })
        combined = {
            "brokerage_assumed_tax": float(sum(a["brokerage_assumed_tax"] for a in per_account)),
            "actual_tax": float(sum(a["actual_tax"] for a in per_account)),
            "tax_saving": float(sum(a["tax_saving"] for a in per_account)),
            "gain_harvest_saving": float(sum(a["gain_harvest_saving"] for a in per_account)),
        }
        return {"accounts": per_account, "combined": combined}

    def _estimate_total_cases(self, start=None) -> int:
        cur = start if start is not None else self.data_start
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

        # use_synthetic=True면 윈도우별 독립 합성으로 TARGET_SYNTHETIC_CASES까지 보충.
        # 실데이터 시작 이전으로 롤링 시작점을 앞당겨 추가 윈도우를 만든다(합성 prefix + 실 suffix).
        self._synth_params = self._build_synth_params() if self.use_synthetic else {}
        if self._synth_params:
            extended = (
                self.data_end
                - relativedelta(years=self.accumulation_years)
                - relativedelta(months=TARGET_SYNTHETIC_CASES * self.step_months)
            )
            roll_start = min(self.data_start, extended)
        else:
            roll_start = self.data_start

        total_cases = self._estimate_total_cases(roll_start) if self.progress_callback else 0
        start_time = time.time()
        cases: list[dict[str, Any]] = []
        cur = roll_start
        run_id = 1

        while True:
            end = cur + relativedelta(years=self.accumulation_years)
            if end > self.data_end:
                break

            all_tickers = self._all_tickers()
            try:
                if self._synth_params and cur < self.data_start:
                    price_data, dates = self._load_window_synthetic(all_tickers, cur, end)
                else:
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
                    "isa_renewal": account.get("isa_renewal", False),
                })

            run_result = MultiAccountSimulationLoop(
                transfers_enabled=self.transfers_enabled,
            ).run(
                accounts=loop_accounts,
                price_data=price_data,
                dates=dates,
                tax_enabled=self.tax_enabled,
                user_settings=self.user_settings,
                distribution_policy=self.distribution_policy,
                manual_comprehensive_years=self.manual_comprehensive_years,
                reinvest_tax_credit=self.reinvest_tax_credit,
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
            # G2/G3/G4 결과 surfacing (윈도우별)
            metrics["transfer_log"] = run_result.transfer_log
            metrics["comprehensive_years"] = list(run_result.comprehensive_years)
            metrics["annual_deduction_credit"] = float(run_result.annual_deduction_credit)
            metrics["pension_transfer_credit"] = float(run_result.pension_transfer_credit_total)
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
                # 절세액(위탁 가정): 케이스별 계좌 위탁가정세금·절세액 surfacing.
                account_metrics["brokerage_assumed_tax"] = float(
                    account_result.get("brokerage_assumed_tax", 0.0)
                )
                account_metrics["tax_saving"] = float(account_result.get("tax_saving", 0.0))
                account_metrics["gain_harvest_saving"] = float(
                    account_result.get("gain_harvest_saving", 0.0)
                )
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

    def _build_synth_params(self) -> dict:
        """use_synthetic 보충용 종목별 GBM 파라미터. 주입 로더 경로는 제외."""
        if self.price_provider is not None:
            return {}
        from modules.retirement.synthetic_price_generator import build_window_synth_params
        return build_window_synth_params(self.portfolio_engine, self._all_tickers())

    def _load_window_synthetic(self, tickers, window_start, window_end):
        """윈도우별 독립 GBM(Student-t) 합성 prefix + 실 suffix.
        단일 합성 경로를 슬라이싱하는 아티팩트를 피해 윈도우마다 독립 시드를 쓴다.
        반환 포맷은 PriceDataLoader.load와 동일 (price_data dict, dates)."""
        from modules.retirement.synthetic_price_generator import (
            SYNTHETIC_DF, T_SCALE, TRADING_DAYS_PER_MONTH,
        )
        raw_loader = self.portfolio_engine.price_loader.loader
        ws = window_start.strftime("%Y-%m-%d")
        we = window_end.strftime("%Y-%m-%d")
        combined: dict = {}
        all_dates: set = set()

        for code in tickers:
            params = self._synth_params.get(code)
            if params is None:
                df = raw_loader.get_price(code, ws, we, allow_synthetic=True)
                df["date"] = pd.to_datetime(df["date"]); df = df.set_index("date")
                combined[code] = df; all_dates.update(df.index)
                continue

            actual_start_dt = pd.Timestamp(params["actual_start"])
            mu_d  = float(params["mu_monthly"]) / TRADING_DAYS_PER_MONTH
            sig_d = float(params["sigma_monthly"]) / np.sqrt(TRADING_DAYS_PER_MONTH)
            anchor = float(params["anchor_price"])

            if window_start >= actual_start_dt:
                df = raw_loader.get_price(code, ws, we, allow_synthetic=False)
                df["date"] = pd.to_datetime(df["date"]); df = df.set_index("date")
                combined[code] = df; all_dates.update(df.index)
                continue

            synth_end = min(actual_start_dt - pd.Timedelta(days=1), window_end)
            bdays = pd.bdate_range(start=window_start, end=synth_end)
            synth_df = None
            if len(bdays) > 0:
                seed = abs(hash(code + ws)) % (2 ** 31)
                n = len(bdays)
                rng = np.random.default_rng(seed=seed)
                rets = (rng.standard_t(df=SYNTHETIC_DF, size=n) / T_SCALE) * sig_d + mu_d
                prices = np.empty(n)
                prices[-1] = anchor / (1.0 + rets[-1])
                for i in range(n - 2, -1, -1):
                    prices[i] = prices[i + 1] / (1.0 + rets[i])
                    if prices[i] <= 0:
                        prices[i] = prices[i + 1] * 0.99
                synth_df = pd.DataFrame(
                    {"open": prices, "high": prices, "low": prices, "close": prices,
                     "volume": np.zeros(n), "dividend": np.zeros(n), "split": np.ones(n)},
                    index=pd.DatetimeIndex(bdays),
                )
                synth_df.index.name = "date"

            if window_end >= actual_start_dt:
                real_df = raw_loader.get_price(code, params["actual_start"], we, allow_synthetic=False)
                real_df["date"] = pd.to_datetime(real_df["date"]); real_df = real_df.set_index("date")
                for col in ["open", "high", "low", "close", "volume", "dividend", "split"]:
                    if col not in real_df.columns:
                        real_df[col] = 0.0 if col != "split" else 1.0
                if synth_df is not None and not synth_df.empty:
                    df = pd.concat([synth_df, real_df], axis=0)
                    df = df[~df.index.duplicated(keep="last")].sort_index()
                else:
                    df = real_df
            else:
                df = synth_df if synth_df is not None else pd.DataFrame()

            if df is not None and not df.empty:
                combined[code] = df; all_dates.update(df.index)

        if not combined:
            return {}, []
        dates = sorted(all_dates)
        full_index = pd.DatetimeIndex(dates)
        for code in tickers:
            if code not in combined:
                continue
            df = combined[code].reindex(full_index)
            df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].ffill()
            if "dividend" in df.columns:
                df["dividend"] = df["dividend"].fillna(0)
            if "split" in df.columns:
                df["split"] = df["split"].fillna(1)
            combined[code] = df
        return combined, dates

    def _fit_distribution(self, cases: list[dict[str, Any]]) -> dict:
        keys = [
            "end_value", "cagr", "mdd", "sharpe", "sortino",
            "calmar", "mwr", "dividend_cagr", "dividend_mdd",
            "total_dividend", "last_year_dividend", "dividend_yield_on_cost",
            "tax_paid", "brokerage_assumed_tax", "tax_saving", "gain_harvest_saving",
        ]
        result = {}
        for key in keys:
            v = np.array([c.get(key, 0.0) for c in cases], dtype=float)
            v = np.where(np.isfinite(v), v, 0.0)   # inf/nan 제거(JSON 직렬화 안전)
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
