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
            fee_rate             = config_dict.get("fee_rate", 0.0),          # D4 거래수수료
            stock_tickers        = config_dict.get("stock_tickers"),         # D4 개별주식 매도세
        )

        # ── 세금 경로 분기 ───────────────────────────────────────
        tax_enabled    = config_dict.get("tax_enabled", False)
        account_type   = config_dict.get("account_type", "위탁")
        user_settings  = config_dict.get("user_settings", {})
        gain_harvesting = config_dict.get("gain_harvesting", False)

        if tax_enabled:
            # TaxableSimulationRunner: 배당세 + 리밸 CG세 + 청산세 적용
            from modules.simulation.taxable_runner import TaxableSimulationRunner
            runner     = TaxableSimulationRunner()
            run_result = runner.run(
                config          = config,
                price_data      = sliced_data,
                dates           = sliced_dates,
                strategy        = strategy,
                tax_enabled     = True,
                account_type    = account_type,
                user_settings   = user_settings,
                gain_harvesting = gain_harvesting,
                carried_cost_basis = config_dict.get("cost_basis"),
            )
            history_df    = run_result.history_df
            tax_end_value = run_result.end_value
            _total_fees   = float(getattr(run_result, "total_fees", 0.0))   # D4
        else:
            portfolio = Portfolio(
                config_dict["initial_capital"],
                fee_rate      = config_dict.get("fee_rate", 0.0),            # D4
                stock_tickers = config_dict.get("stock_tickers"),
            )
            loop      = SimulationLoop(
                DividendEngine(), ContributionEngine(), WithdrawalEngine(),
                OrderExecutor(), CashAllocator()
            )
            recorder = HistoryRecorder()
            loop.run(portfolio, strategy, config, sliced_data, sliced_dates, recorder)
            history_df    = recorder.to_dataframe()
            tax_end_value = float(history_df["portfolio_value"].iloc[-1]) if not history_df.empty else 0.0
            _total_fees   = float(getattr(portfolio, "total_fees", 0.0))    # D4

        return {
            "history":       history_df,
            "run_id":        run_id,
            "start":         start_str,
            "end":           end_str,
            "tax_end_value": tax_end_value,
            "total_fees":    _total_fees,                                    # D4 인출 거래수수료
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
        # 세금 파라미터 (선택)
        tax_engine                    = None,
        account_type:       str       = "위탁",
        current_age:        int       = 40,
        accumulation_years: int       = 0,
        user_settings:      dict      = None,
        gain_harvesting:    bool      = False,
        progress_callback             = None,
        cost_basis:         float     = None,
        fee_rate:           float     = 0.0,     # D4 거래수수료(인출 단계 매수·매도)
        stock_tickers                 = None,    # D4 개별주식 매도세 가산 대상
    ):
        self.portfolio_engine   = portfolio_engine
        self.fee_rate           = float(fee_rate or 0.0)
        self.stock_tickers      = stock_tickers
        self.tickers            = tickers
        self.strategy_factory   = strategy_factory
        self.data_start         = pd.Timestamp(data_start)
        self.data_end           = pd.Timestamp(data_end)
        self.withdrawal_years      = withdrawal_years
        self.monthly_withdrawal    = monthly_withdrawal
        self.tax_engine            = tax_engine
        self.account_type          = account_type
        self.user_settings         = user_settings or {}
        self.gain_harvesting       = gain_harvesting and account_type == "위탁"
        # 적립 취득가(=총납입) 인계 — 위탁 인출 매도세가 적립차익까지 과세하도록(G5-C C1).
        self.cost_basis            = cost_basis
        self.withdrawal_start_age  = current_age + accumulation_years
        self.initial_capital    = initial_capital
        self.inflation          = inflation
        self.dividend_mode      = dividend_mode
        self.step_months        = step_months
        self.verbose            = verbose
        self.progress_callback  = progress_callback
        self._return_stats_cache: Optional[tuple] = None

    def _estimate_total_cases(self) -> int:
        cur = self.data_start
        count = 0
        while True:
            end = cur + relativedelta(years=self.withdrawal_years)
            if end > self.data_end:
                break
            count += 1
            cur += relativedelta(months=self.step_months)
        return max(count, 1)

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
        result = {
            "cases":        cases,
            "distribution": distribution,
            "success_rate": success_rate,
            "n_real":       n_real,
            "n_synthetic":  n_synthetic,
            # D4 인출 거래수수료(중앙값 — 적립 total_fees와 합산해 표시).
            "total_fees":   float(np.median([c.get("total_fees", 0.0) for c in cases])) if cases else 0.0,
        }
        # 연금 세금 정보 (연금저축/IRP)
        if self.tax_engine and self.account_type in ("연금저축", "IRP"):
            result["pension_tax_info"] = self._calc_pension_tax_by_age()
        return result

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
            # GAP-RET-KRDATA: 실데이터 < 인출기간 → 실윈도우 0개 — 전량 합성 폴백.
            # 기존 MIN_CASES 패딩과 동일 GBM(실측 수익률 통계 기반), is_synthetic 마킹.
            mu, sigma = self._get_return_stats(full_price_data)
            return self._run_synthetic_cases(MIN_CASES, mu, sigma, start_id=1)

        # 3. 파라미터 직렬화
        strategy_instance = self.strategy_factory()
        strategy_dict = {
            "target_weights":      strategy_instance.target_weights,
            "rebalance_frequency": getattr(strategy_instance, "rebalance_frequency", None),
            "drift_threshold":     getattr(strategy_instance, "drift_threshold", None),
        }
        gross_withdrawal = self._calc_gross_withdrawal()
        config_dict = {
            "tickers":           self.tickers,
            "initial_capital":   self.initial_capital,
            "withdrawal_amount": gross_withdrawal,
            "dividend_mode":     self.dividend_mode,
            "inflation":         self.inflation,
            # 세금 파라미터 (워커에서 TaxableSimulationRunner 사용)
            "tax_enabled":       bool(self.tax_engine),
            "account_type":      self.account_type,
            "user_settings":     self.user_settings,
            "gain_harvesting":   self.gain_harvesting,
            "cost_basis":        self.cost_basis,
            # D4 거래수수료 — 워커에서 SimulationConfig/Portfolio에 주입.
            "fee_rate":          self.fee_rate,
            "stock_tickers":     self.stock_tickers,
        }
        task_args = [
            (s, e, config_dict, strategy_dict, rid)
            for s, e, rid in windows
        ]

        # 4. 병렬 실행 (progress_callback 있으면 imap_unordered로 케이스 단위 보고)
        import time as _t
        _start = _t.time()
        total  = len(task_args)

        if self.progress_callback:
            from multiprocessing import Pool as _Pool
            try:
                raw_results = []
                with _Pool(N_WORKERS, initializer=_init_wd_worker,
                           initargs=(full_price_data, all_dates)) as pool:
                    for completed, result in enumerate(
                            pool.imap_unordered(_run_wd_case, task_args), 1):
                        raw_results.append(result)
                        elapsed = _t.time() - _start
                        eta = elapsed / completed * (total - completed) if completed > 0 else None
                        self.progress_callback(current=completed, total=total, elapsed=elapsed)
            except Exception as e:
                if self.verbose:
                    print(f"  [병렬화 실패 → 순차 실행] {e}")
                _init_wd_worker(full_price_data, all_dates)
                raw_results = []
                for completed, a in enumerate(task_args, 1):
                    raw_results.append(_run_wd_case(a))
                    elapsed = _t.time() - _start
                    self.progress_callback(current=completed, total=total, elapsed=elapsed)
        else:
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
            metrics["total_fees"]   = float(res.get("total_fees", 0.0))     # D4
            # 세금 적용된 최종값으로 override (TaxableSimulationRunner 청산세 포함)
            if "tax_end_value" in res:
                tv = res["tax_end_value"]
                metrics["end_value"]       = tv
                metrics["end_value_ratio"] = tv / self.initial_capital if self.initial_capital > 0 else 0.0
                metrics["success"]         = tv > 0
            cases.append(metrics)
            if self.verbose:
                status = "✅" if metrics["success"] else "🔴"
                print(f"  {status} [{res['run_id']:03d}] {res['start'][:7]} ~ {res['end'][:7]}"
                      f"  종료자산: {metrics['end_value']:,.0f}")

        # 6. 합성 보충
        # [SYNTHETIC_PATH: In-Memory] WithdrawalAnalyzer._run_synthetic_cases (GBM + Student-t)
        # 롤링 케이스 < MIN_CASES 시 자동 발동. DB 기록 없음. is_synthetic=True 마킹됨.
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
        withdrawal = float(self._calc_gross_withdrawal())
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
            "total_fees": 0.0,   # D4: 합성 경로는 거래 없음 → 수수료 0
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
    def _calc_gross_withdrawal(self) -> float:
        """
        워커에게 넘길 총 인출액(gross)을 계산한다.

        연금저축/IRP의 경우 포트폴리오에서 나가는 금액은
        사용자가 실제로 수령하는 net 금액보다 크다 (세금 납부분 포함).
        나이가 올라갈수록 세율이 낮아지므로 연도별 gross를 가중 평균한다.

        위탁/ISA: 인출 중 CG세가 없으므로 net = gross.
        """
        if (
            self.tax_engine is None
            or self.account_type not in ("연금저축", "IRP")
        ):
            return self.monthly_withdrawal

        net     = self.monthly_withdrawal
        n_total = self.withdrawal_years * 12
        gross_sum = 0.0
        for month in range(n_total):
            age          = self.withdrawal_start_age + month // 12
            annual_gross = self.monthly_withdrawal * 12  # 초기 추정치로 연간 수령액 계산
            # 사적연금 분리과세(G5-C C2·오너결정): 1,500만 이하 나이별 3.3~5.5%,
            # 초과 시 전액 16.5%. 기존 pension_effective_rate(하이브리드, BUG-PENSION-1) 대체.
            tax  = self.tax_engine.pension_separate_tax_annual(annual_gross, age)
            rate = tax / annual_gross if annual_gross > 0 else 0.0
            gross_sum += net / (1.0 - rate) if rate < 1.0 else net
        return gross_sum / n_total

    def _calc_pension_tax_by_age(self) -> dict:
        """
        연금 수령 기간 중 나이별 세후 실수령액 계산.
        시뮬은 그대로 두고, 실제 수령액만 별도 계산.
        수령 나이가 바뀔 때 세율이 자동으로 3단계 전환.
        """
        gross   = self.monthly_withdrawal
        start   = self.withdrawal_start_age
        end_age = start + self.withdrawal_years
        annual  = gross * 12

        # 사적연금 분리과세(C2): 1500만 이하 나이별 3.3~5.5%, 초과 시 전구간 전액 16.5%.
        # 나이 구간별 실효세율 = pension_separate_tax_annual(연수령, 구간나이)/연수령.
        BRACKETS = [(55, 70), (70, 80), (80, 200)]
        brackets = []
        for b_start, b_end in BRACKETS:
            age_from = max(start, b_start)
            age_to   = min(end_age, b_end)
            if age_from >= age_to:
                continue
            tax  = self.tax_engine.pension_separate_tax_annual(annual, age_from)
            rate = tax / annual if annual > 0 else 0.0
            net  = gross * (1.0 - rate)
            brackets.append({
                "age_from":     age_from,
                "age_to":       age_to,
                "rate":         round(rate, 4),
                "gross_monthly": round(gross),
                "net_monthly":   round(net),
                "tax_monthly":   round(gross - net),
            })

        # 연간 1,500만 초과 체크
        threshold = 15_000_000
        over_threshold = annual > threshold

        return {
            "brackets":      brackets,
            "over_threshold": over_threshold,
            "annual_gross":   round(annual),
        }