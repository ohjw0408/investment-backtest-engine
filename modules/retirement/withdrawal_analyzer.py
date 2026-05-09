"""
withdrawal_analyzer.py - 최적화 버전
- _calc_metrics에서 get_price 호출 완전 제거 → history 데이터만으로 계산
- 롤링 케이스 부족 시 GBM + Student-t 합성 데이터로 보충 (MIN_CASES 보장)
- multiprocessing.Pool로 롤링 케이스 병렬 실행
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from typing import Callable, List, Optional


MIN_CASES    = 30
SYNTHETIC_DF = 5
N_WORKERS    = min(os.cpu_count() or 2, 6)

# ── 워커 전역 변수 ────────────────────────────────────────
_w_price_data: dict = {}
_w_dates:      list = []


def _init_wd_worker(price_data: dict, dates: list):
    global _w_price_data, _w_dates
    _w_price_data = price_data
    _w_dates      = dates


def _run_wd_case(args: tuple):
    """단일 인출 케이스 실행 워커 함수."""
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
            monthly_contribution = 0,
            withdrawal_amount    = config_dict["withdrawal_amount"],
            dividend_mode        = config_dict["dividend_mode"],
            rebalance_frequency  = strategy_dict.get("rebalance_frequency"),
            inflation            = config_dict.get("inflation", 0.0),
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
            "history":  history_df,
            "run_id":   run_id,
            "start":    start_str,
            "end":      end_str,
        }
    except Exception as e:
        return None


class WithdrawalAnalyzer:

    def __init__(
        self,
        portfolio_engine,
        tickers:            List[str],
        strategy_factory:   Callable,
        data_start:         str,
        data_end:           str,
        withdrawal_years:   int,
        monthly_withdrawal: float,
        initial_capital:    float,
        inflation:          float = 0.0,
        dividend_mode:      str   = "reinvest",
        step_months:        int   = 1,
        verbose:            bool  = False,
    ):
        self.portfolio_engine   = portfolio_engine
        self.tickers            = tickers
        self.strategy_factory   = strategy_factory
        self.data_start         = pd.Timestamp(data_start)
        self.data_end           = pd.Timestamp(data_end)
        self.withdrawal_years   = withdrawal_years
        self.monthly_withdrawal = monthly_withdrawal
        self.initial_capital    = initial_capital
        self.inflation          = inflation
        self.dividend_mode      = dividend_mode
        self.step_months        = step_months
        self.verbose            = verbose
        self._return_stats_cache: Optional[tuple] = None

    def run(self) -> dict:
        cases = self._run_rolling()
        if not cases:
            raise ValueError("롤링 케이스가 0개입니다.")
        distribution = self._fit_distribution(cases)
        success_rate = float(np.mean([c["success"] for c in cases]))
        n_real       = sum(1 for c in cases if not c.get("is_synthetic", False))
        n_synthetic  = len(cases) - n_real
        if self.verbose:
            print(f"[WithdrawalAnalyzer] 실제 {n_real}개 + 합성 {n_synthetic}개 = 총 {len(cases)}개")
            print(f"  성공률: {success_rate:.1%}")
        return {
            "cases":        cases,
            "distribution": distribution,
            "success_rate": success_rate,
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
            end = cur + relativedelta(years=self.withdrawal_years)
            if end > self.data_end:
                break
            windows.append((cur.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), run_id))
            cur    += relativedelta(months=self.step_months)
            run_id += 1

        if not windows:
            return []

        # 3. 파라미터 직렬화
        strategy_instance = self.strategy_factory()
        strategy_dict = {
            "target_weights":      strategy_instance.target_weights,
            "rebalance_frequency": getattr(strategy_instance, "rebalance_frequency", None),
            "drift_threshold":     getattr(strategy_instance, "drift_threshold", None),
        }
        config_dict = {
            "tickers":           self.tickers,
            "initial_capital":   self.initial_capital,
            "withdrawal_amount": self.monthly_withdrawal,
            "dividend_mode":     self.dividend_mode,
            "inflation":         self.inflation,
        }
        task_args = [
            (s, e, config_dict, strategy_dict, rid)
            for s, e, rid in windows
        ]

        # 4. 병렬 실행
        raw_results = self._run_parallel(task_args, full_price_data, all_dates)

        # 5. metrics 변환
        cases = []
        for res in raw_results:
            if res is None:
                continue
            start_dt = pd.Timestamp(res["start"])
            metrics  = self._calc_metrics(res["history"], start_dt, self.withdrawal_years)
            metrics["run_id"]       = res["run_id"]
            metrics["start"]        = res["start"]
            metrics["end"]          = res["end"]
            metrics["is_synthetic"] = False
            cases.append(metrics)
            if self.verbose:
                status = "✅" if metrics["success"] else "🔴"
                print(f"  {status} [{res['run_id']:03d}] {res['start'][:7]} ~ {res['end'][:7]}"
                      f"  종료자산: {metrics['end_value']:,.0f}")

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
                initializer = _init_wd_worker,
                initargs    = (full_price_data, all_dates),
            ) as pool:
                return pool.map(_run_wd_case, task_args)
        except Exception as e:
            if self.verbose:
                print(f"  [병렬화 실패 → 순차 실행] {e}")
            _init_wd_worker(full_price_data, all_dates)
            return [_run_wd_case(a) for a in task_args]

    # ════════════════════════════════════════════════════════
    # 합성 케이스 (GBM + Student-t)
    # ════════════════════════════════════════════════════════

    def _get_return_stats(self, price_data: dict) -> tuple:
        if self._return_stats_cache is not None:
            return self._return_stats_cache
        try:
            closes = price_data[self.tickers[0]]["close"].values
            if len(closes) >= 24:
                idx  = np.arange(0, len(closes), 21)
                mpx  = closes[idx]
                mret = np.diff(mpx) / np.where(mpx[:-1] > 0, mpx[:-1], 1.0)
                mret = mret[np.isfinite(mret) & (np.abs(mret) < 0.5)]
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
        n_months   = self.withdrawal_years * 12
        t_scale    = np.sqrt(SYNTHETIC_DF / (SYNTHETIC_DF - 2))
        rets       = (rng.standard_t(df=SYNTHETIC_DF, size=n_months) / t_scale) * sigma + mu
        asset      = float(self.initial_capital)
        withdrawal = float(self.monthly_withdrawal)
        pv_arr     = np.zeros(n_months + 1)
        pv_arr[0]  = asset
        depleted   = False
        depletion_m = n_months

        for i, r in enumerate(rets):
            asset = asset * (1.0 + r) - withdrawal
            if self.inflation > 0 and (i + 1) % 12 == 0:
                withdrawal *= (1.0 + self.inflation)
            if asset <= 0:
                asset = 0.0
                if not depleted:
                    depleted    = True
                    depletion_m = i + 1
                pv_arr[i + 1] = 0.0
            else:
                pv_arr[i + 1] = asset

        success         = not depleted
        end_value       = float(pv_arr[depletion_m] if depleted else pv_arr[-1])
        end_value_ratio = end_value / self.initial_capital if self.initial_capital > 0 else 0.0
        years_to_dep    = depletion_m / 12.0 if depleted else float(self.withdrawal_years)
        valid           = pv_arr[:depletion_m + 1]
        cummax          = np.maximum.accumulate(valid)
        with np.errstate(invalid="ignore", divide="ignore"):
            dd = np.where(cummax > 0, (valid - cummax) / cummax, 0.0)
        mdd = float(np.min(dd))
        mid = n_months // 2
        sequence_risk = float(np.mean(rets[:mid])) - float(np.mean(rets[mid:]))

        return {
            "success": success, "end_value": end_value,
            "end_value_ratio": end_value_ratio,
            "years_to_depletion": years_to_dep,
            "sustainable_months": int(depletion_m),
            "mdd": mdd, "total_dividend": 0.0,
            "withdrawal_coverage": 0.0, "sequence_risk": sequence_risk,
            "dividend_mdd": 0.0, "is_synthetic": True,
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

    def _calc_metrics(self, history: pd.DataFrame, start_date: pd.Timestamp, years: int) -> dict:
        pv        = history["portfolio_value"]
        end_value = float(pv.iloc[-1])
        success   = end_value > 0

        end_value_ratio    = end_value / self.initial_capital if self.initial_capital > 0 else 0.0
        years_to_depletion = float(years)
        if not success:
            zero_mask = pv <= 0
            if zero_mask.any():
                depletion_date     = pd.to_datetime(history.loc[zero_mask.idxmax(), "date"])
                years_to_depletion = (depletion_date - start_date).days / 365.25

        mdd            = float(((pv - pv.cummax()) / pv.cummax()).min())
        div_col        = "dividend_income"
        total_dividend = float(history[div_col].sum()) if div_col in history.columns else 0.0
        sustainable_months  = int(years_to_depletion * 12)
        total_withdrawal    = self.monthly_withdrawal * years * 12
        withdrawal_coverage = (total_dividend / total_withdrawal) if total_withdrawal > 0 and total_dividend > 0 else 0.0

        dividend_mdd = 0.0
        if div_col in history.columns:
            h           = history.copy()
            h["_year"]  = pd.to_datetime(h["date"]).dt.year
            h["_month"] = pd.to_datetime(h["date"]).dt.month
            full_years  = set(h.groupby("_year")["_month"].nunique()
                              .pipe(lambda s: s[s >= 12]).index)
            annual_div  = h[h["_year"].isin(full_years)].groupby("_year")[div_col].sum()
            annual_div  = annual_div[annual_div > 0]
            if len(annual_div) >= 2:
                roll_max     = annual_div.cummax()
                dividend_mdd = float(((annual_div - roll_max) / roll_max).min())

        mid = len(pv) // 2

        def _half_cagr(s):
            sv, ev = float(s.iloc[0]), float(s.iloc[-1])
            ny = len(s) / 252
            return (ev / sv) ** (1 / ny) - 1 if sv > 0 and ev > 0 and ny > 0 else 0.0

        sequence_risk = _half_cagr(pv.iloc[:mid]) - _half_cagr(pv.iloc[mid:])

        return {
            "success": success, "end_value": end_value,
            "end_value_ratio": end_value_ratio,
            "years_to_depletion": years_to_depletion,
            "sustainable_months": sustainable_months,
            "mdd": mdd, "total_dividend": total_dividend,
            "withdrawal_coverage": withdrawal_coverage,
            "sequence_risk": sequence_risk,
            "dividend_mdd": dividend_mdd,
        }

    def _fit_distribution(self, cases: List[dict]) -> dict:
        keys = [
            "end_value_ratio", "years_to_depletion", "sustainable_months",
            "mdd", "total_dividend", "withdrawal_coverage", "sequence_risk", "dividend_mdd",
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
        sv = np.array([float(c["success"]) for c in cases])
        result["success"] = {
            "mean": float(sv.mean()), "std": float(sv.std()),
            "p10": float(np.percentile(sv, 10)), "p25": float(np.percentile(sv, 25)),
            "p50": float(np.percentile(sv, 50)), "p75": float(np.percentile(sv, 75)),
            "p90": float(np.percentile(sv, 90)), "values": sv.tolist(),
        }
        return result