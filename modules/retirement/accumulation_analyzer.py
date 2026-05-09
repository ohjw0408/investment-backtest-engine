"""
accumulation_analyzer.py - 최적화 버전
- _calc_metrics에서 get_price 호출 완전 제거 → history 데이터만으로 계산
- 롤링 케이스 부족 시 GBM + Student-t 합성 데이터로 보충 (MIN_CASES 보장)
- multiprocessing.Pool로 롤링 케이스 병렬 실행
  전체 price_data를 워커에 1회만 전송, 각 케이스는 슬라이스만 수행
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from typing import Callable, List, Optional


MIN_CASES    = 30
SYNTHETIC_DF = 5
N_WORKERS    = min(os.cpu_count() or 2, 8)

# ── 워커 전역 변수 (프로세스당 1회 초기화) ──────────────────
_w_price_data: dict = {}
_w_dates:      list = []


def _init_worker(price_data: dict, dates: list):
    global _w_price_data, _w_dates
    _w_price_data = price_data
    _w_dates      = dates


def _run_acc_case(args: tuple):
    """단일 축적 케이스 실행 워커 함수 (module-level, picklable)."""
    import pandas as pd
    from modules.core.portfolio                 import Portfolio
    from modules.config.simulation_config       import SimulationConfig
    from modules.execution.order_executor       import OrderExecutor
    from modules.execution.cash_allocator       import CashAllocator
    from modules.simulation.dividend_engine     import DividendEngine
    from modules.simulation.contribution_engine import ContributionEngine
    from modules.simulation.withdrawal_engine   import WithdrawalEngine
    from modules.simulation.history_recorder    import HistoryRecorder
    from modules.simulation.simulation_loop     import SimulationLoop
    from modules.rebalance.periodic             import PeriodicRebalance

    (start_str, end_str, config_dict, strategy_dict, run_id) = args

    try:
        start_ts = pd.Timestamp(start_str)
        end_ts   = pd.Timestamp(end_str)

        sliced_dates = [d for d in _w_dates if start_ts <= d <= end_ts]
        sliced_data  = {
            ticker: df.loc[(df.index >= start_ts) & (df.index <= end_ts)]
            for ticker, df in _w_price_data.items()
        }

        strategy = PeriodicRebalance(
            target_weights      = strategy_dict["target_weights"],
            rebalance_frequency = strategy_dict.get("rebalance_frequency"),
            drift_threshold     = strategy_dict.get("drift_threshold"),
        )
        config = SimulationConfig(
            start_date           = start_str,
            end_date             = end_str,
            tickers              = config_dict["tickers"],
            target_weights       = strategy_dict["target_weights"],
            initial_capital      = config_dict["initial_capital"],
            monthly_contribution = config_dict["monthly_contribution"],
            withdrawal_amount    = 0,
            dividend_mode        = config_dict["dividend_mode"],
            rebalance_frequency  = strategy_dict.get("rebalance_frequency"),
            inflation            = 0.0,
        )
        portfolio = Portfolio(config_dict["initial_capital"])
        loop      = SimulationLoop(
            DividendEngine(), ContributionEngine(), WithdrawalEngine(),
            OrderExecutor(), CashAllocator()
        )
        recorder = HistoryRecorder()
        loop.run(portfolio, strategy, config, sliced_data, sliced_dates, recorder)
        history_df = recorder.to_dataframe()

        return {
            "history":     history_df,
            "final_value": float(history_df["portfolio_value"].iloc[-1]),
            "run_id":      run_id,
            "start":       start_str,
            "end":         end_str,
        }
    except Exception as e:
        return None


class AccumulationAnalyzer:

    def __init__(
        self,
        portfolio_engine,
        tickers:              List[str],
        strategy_factory:     Callable,
        data_start:           str,
        data_end:             str,
        accumulation_years:   int,
        monthly_contribution: float = 0,
        initial_capital:      float = 0,
        dividend_mode:        str   = "reinvest",
        step_months:          int   = 1,
        verbose:              bool  = False,
        div_start:            Optional[str] = None,
    ):
        self.portfolio_engine      = portfolio_engine
        self.tickers               = tickers
        self.strategy_factory      = strategy_factory
        self.data_start            = pd.Timestamp(data_start)
        self.data_end              = pd.Timestamp(data_end)
        self.accumulation_years    = accumulation_years
        self.monthly_contribution  = monthly_contribution
        self.initial_capital       = initial_capital
        self.dividend_mode         = dividend_mode
        self.step_months           = step_months
        self.verbose               = verbose
        self.div_start             = pd.Timestamp(div_start) if div_start else None
        self._return_stats_cache: Optional[tuple] = None

    def run(self) -> dict:
        cases = self._run_rolling()
        if not cases:
            raise ValueError("롤링 케이스가 0개입니다.")
        distribution = self._fit_distribution(cases)
        n_real      = sum(1 for c in cases if not c.get("is_synthetic", False))
        n_synthetic = len(cases) - n_real
        if self.verbose:
            print(f"[AccumulationAnalyzer] 실제 {n_real}개 + 합성 {n_synthetic}개 = 총 {len(cases)}개")
            print(f"  종료자산 중앙값: {distribution['end_value']['p50']:,.0f}")
            print(f"  CAGR 중앙값:    {distribution['cagr']['p50']:.2%}")
        return {
            "cases":        cases,
            "distribution": distribution,
            "n_real":       n_real,
            "n_synthetic":  n_synthetic,
        }

    # ════════════════════════════════════════════════════════
    # 병렬 롤링
    # ════════════════════════════════════════════════════════

    def _run_rolling(self) -> List[dict]:
        from multiprocessing import Pool

        # 1. 전체 범위 데이터 1회 로드
        full_price_data, all_dates = self.portfolio_engine.price_loader.load(
            self.tickers,
            self.data_start.strftime("%Y-%m-%d"),
            self.data_end.strftime("%Y-%m-%d"),
        )

        # 2. 윈도우 목록
        windows, cur, run_id = [], self.data_start, 1
        while True:
            end = cur + relativedelta(years=self.accumulation_years)
            if end > self.data_end:
                break
            windows.append((cur.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), run_id))
            cur    += relativedelta(months=self.step_months)
            run_id += 1

        if not windows:
            return []

        # 3. 직렬화 가능한 파라미터 추출
        strategy_instance = self.strategy_factory()
        strategy_dict = {
            "target_weights":      strategy_instance.target_weights,
            "rebalance_frequency": getattr(strategy_instance, "rebalance_frequency", None),
            "drift_threshold":     getattr(strategy_instance, "drift_threshold", None),
        }
        config_dict = {
            "tickers":              self.tickers,
            "initial_capital":      self.initial_capital,
            "monthly_contribution": self.monthly_contribution,
            "dividend_mode":        self.dividend_mode,
        }
        task_args = [
            (s, e, config_dict, strategy_dict, rid)
            for s, e, rid in windows
        ]

        # 4. 병렬 실행 (실패 시 순차 fallback)
        raw_results = self._run_parallel(task_args, full_price_data, all_dates)

        # 5. metrics 변환
        cases = []
        for res in raw_results:
            if res is None:
                continue
            metrics                 = self._calc_metrics(res["history"], self.accumulation_years)
            metrics["run_id"]       = res["run_id"]
            metrics["start"]        = res["start"]
            metrics["end"]          = res["end"]
            metrics["end_value"]    = res["final_value"]
            metrics["is_synthetic"] = False
            cases.append(metrics)
            if self.verbose:
                print(f"  [{res['run_id']:03d}] {res['start'][:7]} ~ {res['end'][:7]}"
                      f"  종료자산: {res['final_value']:,.0f}")

        # 6. 합성 보충
        n_real   = len(cases)
        n_needed = max(0, MIN_CASES - n_real)
        if n_needed > 0:
            mu, sigma = self._get_return_stats(full_price_data)
            synthetic = self._run_synthetic_cases(n_needed, mu, sigma, start_id=run_id)
            cases.extend(synthetic)
            if self.verbose:
                print(f"  [합성 보충] 실제 {n_real}개 부족 → 가상 {len(synthetic)}개 추가")

        return cases

    def _run_parallel(self, task_args, full_price_data, all_dates):
        from multiprocessing import Pool
        try:
            with Pool(
                processes   = N_WORKERS,
                initializer = _init_worker,
                initargs    = (full_price_data, all_dates),
            ) as pool:
                return pool.map(_run_acc_case, task_args)
        except Exception as e:
            if self.verbose:
                print(f"  [병렬화 실패 → 순차 실행] {e}")
            _init_worker(full_price_data, all_dates)
            return [_run_acc_case(a) for a in task_args]

    # ════════════════════════════════════════════════════════
    # 합성 케이스 (GBM + Student-t)
    # ════════════════════════════════════════════════════════

    def _get_return_stats(self, price_data: dict) -> tuple:
        if self._return_stats_cache is not None:
            return self._return_stats_cache
        try:
            closes = price_data[self.tickers[0]]["close"].values
            if len(closes) >= 24:
                idx     = np.arange(0, len(closes), 21)
                mpx     = closes[idx]
                mret    = np.diff(mpx) / np.where(mpx[:-1] > 0, mpx[:-1], 1.0)
                mret    = mret[np.isfinite(mret) & (np.abs(mret) < 0.5)]
                if len(mret) >= 12:
                    mu, sigma = float(np.mean(mret)), float(np.std(mret))
                    if sigma > 0 and np.isfinite(mu):
                        self._return_stats_cache = (mu, sigma)
                        return mu, sigma
        except Exception:
            pass
        mu, sigma = 0.07 / 12, 0.15 / np.sqrt(12)
        self._return_stats_cache = (mu, sigma)
        return mu, sigma

    def _simulate_synthetic_case(self, mu, sigma, rng) -> dict:
        n_months = self.accumulation_years * 12
        t_scale  = np.sqrt(SYNTHETIC_DF / (SYNTHETIC_DF - 2))
        rets     = (rng.standard_t(df=SYNTHETIC_DF, size=n_months) / t_scale) * sigma + mu
        asset    = float(self.initial_capital)
        pv_arr   = np.empty(n_months + 1)
        pv_arr[0] = asset
        for i, r in enumerate(rets):
            asset = max(0.0, asset * (1.0 + r) + self.monthly_contribution)
            pv_arr[i + 1] = asset
        end_value = float(pv_arr[-1])
        total_inv = self.initial_capital + self.monthly_contribution * n_months
        cagr   = (end_value / total_inv) ** (1.0 / self.accumulation_years) - 1.0 if total_inv > 0 and end_value > 0 else 0.0
        cummax = np.maximum.accumulate(pv_arr)
        with np.errstate(invalid="ignore", divide="ignore"):
            dd = np.where(cummax > 0, (pv_arr - cummax) / cummax, 0.0)
        mdd    = float(np.min(dd))
        calmar = cagr / abs(mdd) if mdd != 0 else 0.0
        return {
            "end_value": end_value, "cagr": cagr, "mdd": mdd,
            "sharpe": 0.0, "sortino": 0.0, "calmar": calmar, "mwr": cagr,
            "dividend_cagr": 0.0, "dividend_mdd": 0.0, "total_dividend": 0.0,
            "last_year_dividend": 0.0, "dividend_yield_on_cost": 0.0,
            "is_synthetic": True,
        }

    def _run_synthetic_cases(self, n_needed, mu, sigma, start_id=9000):
        results = []
        for i in range(n_needed):
            case           = self._simulate_synthetic_case(mu, sigma, np.random.default_rng(seed=1000 + i))
            case["run_id"] = start_id + i
            case["start"]  = "synthetic"
            case["end"]    = "synthetic"
            results.append(case)
        return results

    # ════════════════════════════════════════════════════════
    # 지표 계산 (기존 로직 유지)
    # ════════════════════════════════════════════════════════

    def _calc_metrics(self, history: pd.DataFrame, years: int) -> dict:
        pv = history["portfolio_value"]
        total_contribution = self.monthly_contribution * years * 12 + self.initial_capital
        end_value   = pv.iloc[-1]
        start_value = pv.iloc[0]
        mdd = float(((pv - pv.cummax()) / pv.cummax()).min())

        daily_returns = pv.pct_change().dropna()
        if "cash_flow" in history.columns:
            contrib_dates = set(
                pd.to_datetime(history.loc[history["cash_flow"] > 0, "date"]).dt.normalize().tolist()
            )
            date_idx      = pd.to_datetime(history.loc[daily_returns.index, "date"]).dt.normalize()
            daily_returns = daily_returns[(~date_idx.isin(contrib_dates)).values]

        std     = daily_returns.std()
        sharpe  = (daily_returns.mean() / std * np.sqrt(252)) if std > 0 else 0.0
        dstd    = daily_returns[daily_returns < 0].std()
        sortino = (daily_returns.mean() / dstd * np.sqrt(252)) if (dstd and dstd > 0) else 0.0

        mwr = 0.0
        if "cash_flow" in history.columns:
            cf = history.loc[history["cash_flow"] != 0, ["date", "cash_flow"]].copy()
            cf = pd.concat([cf, pd.DataFrame([{"date": history["date"].iloc[-1],
                                               "cash_flow": float(pv.iloc[-1])}])], ignore_index=True)
            cf["date"] = pd.to_datetime(cf["date"])
            cf         = cf.sort_values("date").reset_index(drop=True)
            cfs        = [-c for c in cf["cash_flow"].iloc[:-1].tolist()] + [float(cf["cash_flow"].iloc[-1])]
            if len(cfs) >= 2 and any(c < 0 for c in cfs) and any(c > 0 for c in cfs):
                try:
                    rate = 0.01
                    for _ in range(200):
                        npv  = sum(c / (1 + rate) ** i for i, c in enumerate(cfs))
                        dnpv = sum(-i * c / (1 + rate) ** (i + 1) for i, c in enumerate(cfs))
                        if abs(dnpv) < 1e-12: break
                        nr = rate - npv / dnpv
                        if abs(nr - rate) < 1e-8: rate = nr; break
                        rate = nr
                    if -0.9 < rate < 10.0:
                        mwr = (1 + rate) ** 12 - 1
                except Exception:
                    mwr = 0.0

        if mwr != 0.0 and self.monthly_contribution > 0:
            cagr = mwr
        elif total_contribution > 0 and end_value > 0:
            cagr = (end_value / total_contribution) ** (1 / years) - 1
        elif start_value > 0 and end_value > 0:
            cagr = (end_value / start_value) ** (1 / years) - 1
        else:
            cagr = 0.0

        calmar = cagr / abs(mdd) if mdd != 0 else 0.0

        div_col                = "dividend_income"
        dividend_cagr          = 0.0
        dividend_mdd           = 0.0
        total_dividend         = 0.0
        last_year_dividend     = 0.0
        dividend_yield_on_cost = 0.0

        if div_col in history.columns:
            h          = history.copy()
            h["_date"] = pd.to_datetime(h["date"])
            h_div      = h[h["_date"] >= self.div_start] if self.div_start is not None else h
            total_dividend = float(h_div[div_col].sum())
            h_div          = h_div.copy()
            h_div["_year"] = h_div["_date"].dt.year
            h_div["_month"]= h_div["_date"].dt.month
            full_years     = set(h_div.groupby("_year")["_month"].nunique()
                                 .pipe(lambda s: s[s >= 12]).index)
            h_full         = h_div[h_div["_year"].isin(full_years)]
            if not h_full.empty:
                annual_div_abs = h_full.groupby("_year")[div_col].sum()
                qty_cols       = [c for c in h_full.columns if c.endswith("_quantity")]
                if qty_cols:
                    annual_avg_qty = h_full.groupby("_year")[qty_cols].mean().sum(axis=1)
                    valid          = annual_avg_qty[annual_avg_qty > 0].index
                    annual_div_abs = annual_div_abs[annual_div_abs.index.isin(valid)]
                    annual_avg_qty = annual_avg_qty[annual_avg_qty.index.isin(valid)]
                    annual_dps     = annual_div_abs / annual_avg_qty
                    annual_dps     = annual_dps[annual_dps > 0]
                    if len(annual_dps) >= 2:
                        n_y = len(annual_dps) - 1
                        if annual_dps.iloc[0] > 0 and n_y > 0:
                            dividend_cagr = (annual_dps.iloc[-1] / annual_dps.iloc[0]) ** (1 / n_y) - 1
                        roll_max = annual_dps.cummax()
                        dividend_mdd = float(((annual_dps - roll_max) / roll_max).min())
                    if len(annual_div_abs) > 0:
                        last_year_dividend = float(annual_div_abs.iloc[-1])
                else:
                    annual_pv_mean = h_full.groupby("_year")["portfolio_value"].mean()
                    annual_yield   = annual_div_abs / annual_pv_mean
                    annual_yield   = annual_yield[annual_yield > 0]
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
            "cagr": cagr, "mdd": mdd, "sharpe": sharpe, "sortino": sortino,
            "calmar": calmar, "mwr": mwr, "dividend_cagr": dividend_cagr,
            "dividend_mdd": dividend_mdd, "total_dividend": total_dividend,
            "last_year_dividend": last_year_dividend,
            "dividend_yield_on_cost": dividend_yield_on_cost,
        }

    def _fit_distribution(self, cases: List[dict]) -> dict:
        keys = [
            "end_value", "cagr", "mdd", "sharpe", "sortino",
            "calmar", "mwr", "dividend_cagr", "dividend_mdd",
            "total_dividend", "last_year_dividend", "dividend_yield_on_cost",
        ]
        result = {}
        for key in keys:
            v = np.array([c[key] for c in cases])
            result[key] = {
                "mean": float(np.mean(v)), "std": float(np.std(v)),
                "p10":  float(np.percentile(v, 10)),
                "p25":  float(np.percentile(v, 25)),
                "p50":  float(np.percentile(v, 50)),
                "p75":  float(np.percentile(v, 75)),
                "p90":  float(np.percentile(v, 90)),
                "values": v.tolist(),
            }
        return result