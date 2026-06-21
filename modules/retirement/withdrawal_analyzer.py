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


def _effective_workers() -> int:
    """P1-1: 배포 = 2 vCPU + Celery worker concurrency=2(worker_prefetch_multiplier=1, 대기열).
    요청 병렬성은 Celery가 이미 코어 수만큼 제공 → 요청 1건 안에서 Pool을 또 띄우면 동시 2요청 시
    2(Celery)+4(Pool) 프로세스가 2코어 경합(오버서브스크립션) + full_price_data 프로세스 복제로
    4GB OOM. 따라서 **기본 = 인프로세스(1)**. SIM_MAX_WORKERS>1로 명시할 때만 Pool 사용
    (비-Celery·다코어 배치 스크립트 전용). 1이면 호출측이 인프로세스 실행."""
    env = os.environ.get("SIM_MAX_WORKERS")
    if env:
        try:
            return max(1, min(int(env), N_WORKERS))
        except ValueError:
            pass
    return 1

# ── 워커 전역 변수 ────────────────────────────────────────
_w_price_data: dict = {}
_w_dates:      list = []


def _init_wd_worker(price_data: dict, dates: list):
    global _w_price_data, _w_dates
    _w_price_data = price_data
    _w_dates      = dates


def _run_wd_case_with_data(price_data, dates, start_str, end_str, config_dict, strategy_dict, run_id):
    """인출 케이스 sim 코어 — 주어진 price_data/dates로 1회 실행.

    워커(_run_wd_case, 전역 슬라이스)와 MVN per-window 합성 경로가 공용한다.
    """
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
        from modules.simulation.taxable_runner import TaxableSimulationRunner
        runner     = TaxableSimulationRunner()
        run_result = runner.run(
            config          = config,
            price_data      = price_data,
            dates           = dates,
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
        loop.run(portfolio, strategy, config, price_data, dates, recorder)
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


def _run_wd_case(args: tuple):
    """단일 인출 케이스 실행 워커 함수(전역 _w_price_data 슬라이스 → 코어 위임)."""
    import pandas as pd
    (start_str, end_str, config_dict, strategy_dict, run_id) = args
    try:
        start_ts = pd.Timestamp(start_str)
        end_ts   = pd.Timestamp(end_str)
        sliced_dates = [d for d in _w_dates if start_ts <= d <= end_ts]
        sliced_data  = {
            ticker: df.loc[(df.index >= start_ts) & (df.index <= end_ts)]
            for ticker, df in _w_price_data.items()
        }
        return _run_wd_case_with_data(
            sliced_data, sliced_dates, start_str, end_str, config_dict, strategy_dict, run_id
        )
    except Exception:
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
        allow_synthetic:    bool      = False,   # 합성 가격·배당 로드 여부(deep history)
        mc_paths:           int       = 200,     # 몬테카를로 경로 수(SIM 11샘플은 낮게)
    ):
        self.portfolio_engine   = portfolio_engine
        self.allow_synthetic    = bool(allow_synthetic)
        self.mc_paths           = int(mc_paths)
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
            # 연차별 자산 궤적(윈도우 가로질러 p10/p50/p90, 비율) — 인출 결과창 연도별 잔여자산.
            "yearly_trajectory": self._aggregate_trajectory(cases),
        }
        # 연금 세금 정보 (연금저축/IRP)
        if self.tax_engine and self.account_type in ("연금저축", "IRP"):
            result["pension_tax_info"] = self._calc_pension_tax_by_age()
        return result

    def _aggregate_trajectory(self, cases: List[dict]) -> list:
        """케이스별 yearly_ratios를 연차별 p10/p50/p90(비율)로 집계."""
        n = self.withdrawal_years
        mat = [c.get("yearly_ratios") or [] for c in cases]
        mat = [r for r in mat if len(r) == n]
        if not mat:
            return []
        arr = np.array(mat)
        out = []
        for y in range(n):
            col = arr[:, y]
            out.append({
                "year": y + 1,
                "p50":  float(np.percentile(col, 50)),
                "values": [round(float(x), 4) for x in col],   # 프론트서 임의 percentile 밴드 계산
            })
        return out

    # ════════════════════════════════════════════════════════
    # 병렬 롤링
    # ════════════════════════════════════════════════════════

    def _run_rolling(self) -> List[dict]:
        from multiprocessing import Pool

        # 0. 파라미터 직렬화 (MVN·롤링 공용)
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

        # ── MVN 몬테카를로: 실데이터 < 인출기간이면 독립 상관 합성 경로로 (데이터 로드·윈도우보다 먼저) ──
        # 실 독립 데이터가 인출기간보다 짧으면 롤링 윈도우는 단일 합성경로 슬라이스이거나
        # 불장 suffix에 앵커돼 분포가 거짓(고갈 0·전부 높음). 종목별 mu/sigma + 상관을
        # 피팅한 독립 다변량-t 풀경로 몬테카를로로 현실적 분포(실패율·넓은 스프레드) 산출.
        # 가상데이터 체크박스와 무관 — 30년 투영은 실데이터만으론 불가.
        if self._real_data_years() < self.withdrawal_years:
            mvn = self._run_mvn_cases(config_dict, strategy_dict)
            if mvn:
                return mvn
            # MVN 실패 → 단일종목 GBM 폴백
            _fpd, _ = self.portfolio_engine.price_loader.load(
                self.tickers, self.data_start.strftime("%Y-%m-%d"),
                self.data_end.strftime("%Y-%m-%d"), allow_synthetic=self.allow_synthetic,
            )
            mu, sigma = self._get_return_stats(_fpd)
            return self._run_synthetic_cases(MIN_CASES, mu, sigma, start_id=1)

        # 1. 전체 범위 데이터 1회 로드 (allow_synthetic 시 deep 합성 가격·배당 포함)
        full_price_data, all_dates = self.portfolio_engine.price_loader.load(
            self.tickers,
            self.data_start.strftime("%Y-%m-%d"),
            self.data_end.strftime("%Y-%m-%d"),
            allow_synthetic=self.allow_synthetic,
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
            mu, sigma = self._get_return_stats(full_price_data)
            return self._run_synthetic_cases(MIN_CASES, mu, sigma, start_id=1)

        task_args = [
            (s, e, config_dict, strategy_dict, rid)
            for s, e, rid in windows
        ]

        # 4. 실행 — 기본 인프로세스 순차(P1-1, Celery concurrency가 요청 병렬성 제공).
        #    SIM_MAX_WORKERS>1 명시 시에만 Pool 병렬(비-Celery 다코어 배치용).
        import time as _t
        _start  = _t.time()
        total   = len(task_args)
        workers = _effective_workers()

        if workers <= 1:
            # Pool 생성 안 함 — full_price_data 프로세스 복제·fork·코어 경합 회피, 결과 동일.
            _init_wd_worker(full_price_data, all_dates)
            raw_results = []
            for completed, a in enumerate(task_args, 1):
                raw_results.append(_run_wd_case(a))
                if self.progress_callback:
                    self.progress_callback(current=completed, total=total,
                                           elapsed=_t.time() - _start)
        elif self.progress_callback:
            from multiprocessing import Pool as _Pool
            try:
                raw_results = []
                with _Pool(workers, initializer=_init_wd_worker,
                           initargs=(full_price_data, all_dates)) as pool:
                    for completed, result in enumerate(
                            pool.imap_unordered(_run_wd_case, task_args), 1):
                        raw_results.append(result)
                        elapsed = _t.time() - _start
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
            raw_results = self._run_parallel(task_args, full_price_data, all_dates, workers)

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
            div_yield = self._estimate_real_yield(cases)   # 실측 평균 배당수익률 → 합성에 반영
            synthetic = self._run_synthetic_cases(n_needed, mu, sigma, div_yield=div_yield, start_id=run_id)
            cases.extend(synthetic)
            if self.verbose:
                print(f"  [합성 보충] 실제 {n_real}개 부족 → 가상 {len(synthetic)}개 추가")

        return cases

    def _run_parallel(self, task_args, full_price_data, all_dates, workers=None):
        from multiprocessing import Pool
        try:
            with Pool(
                processes   = workers or N_WORKERS,
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

    def _simulate_synthetic_case(self, mu, sigma, rng, div_yield: float = 0.0) -> dict:
        n_months   = self.withdrawal_years * 12
        t_scale    = np.sqrt(SYNTHETIC_DF / (SYNTHETIC_DF - 2))
        rets       = (rng.standard_t(df=SYNTHETIC_DF, size=n_months) / t_scale) * sigma + mu
        asset      = float(self.initial_capital)
        withdrawal = float(self._calc_gross_withdrawal())
        pv_arr     = np.zeros(n_months + 1)
        pv_arr[0]  = asset
        depleted   = False
        depletion_m = n_months

        # 배당 반영(실측 케이스 평균 배당수익률 div_yield). 기본 재투자 가정 — 자산에 합산.
        monthly_yield  = max(float(div_yield or 0.0), 0.0) / 12.0
        total_dividend = 0.0
        first_year_div = 0.0

        for i, r in enumerate(rets):
            asset = asset * (1.0 + r)
            div   = asset * monthly_yield
            total_dividend += div
            if i < 12:
                first_year_div += div
            asset = asset + div - withdrawal
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

        # 연차별 자산비율(연말 시점) — 실측 경로와 동일 포맷.
        _ic = self.initial_capital if self.initial_capital > 0 else 1.0
        yearly_ratios = [
            float(pv_arr[min(y * 12, n_months)]) / _ic
            for y in range(1, self.withdrawal_years + 1)
        ]

        first_year_withdrawal = self.monthly_withdrawal * 12
        withdrawal_coverage = (first_year_div / first_year_withdrawal) if first_year_withdrawal > 0 else 0.0

        return {
            "success": success, "end_value": end_value,
            "end_value_ratio": end_value_ratio,
            "years_to_depletion": years_to_dep,
            "sustainable_months": int(depletion_m),
            "mdd": mdd, "total_dividend": total_dividend,
            "withdrawal_coverage": withdrawal_coverage, "sequence_risk": sequence_risk,
            "dividend_mdd": 0.0, "is_synthetic": True,
            "total_fees": 0.0,   # D4: 합성 경로는 거래 없음 → 수수료 0
            "yearly_ratios": yearly_ratios,
        }

    def _real_data_years(self) -> float:
        """모든 종목이 실데이터(volume>0)를 가진 구간의 연수(포트폴리오 기준 = 가장 늦은 상장)."""
        try:
            conn = self.portfolio_engine.price_loader.loader.conn
        except Exception:
            return 0.0
        starts = []
        for code in self.tickers:
            try:
                r = conn.execute(
                    "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (code,)
                ).fetchone()
                if r and r[0]:
                    starts.append(pd.Timestamp(r[0]))
            except Exception:
                pass
        if not starts:
            return 0.0
        eff_real = max(starts)
        return max(0.0, (self.data_end - eff_real).days / 365.25)

    def _run_mvn_cases(self, config_dict: dict, strategy_dict: dict) -> list:
        """풀-호라이즌 독립 상관 몬테카를로 — 실데이터 < 인출기간일 때 현실적 분포.

        estimate_joint_stats로 종목별 mu/sigma + 상관행렬을 실데이터서 피팅한 뒤,
        매 경로마다 상관 반영 다변량-t 일일수익을 인출기간 전체에 독립 생성한다
        (실 불장 suffix에 앵커하지 않음 → 실패 케이스·넓은 분포 재현). 각 경로의 합성
        가격에 종목별 실 배당수익률로 분기배당을 주입하고 인출 sim을 실행.
        joint_stats 추정 실패 시 []를 반환(호출부가 단일종목 GBM 폴백).
        """
        from dateutil.relativedelta import relativedelta
        from modules.retirement.synthetic_price_generator import (
            SYNTHETIC_DF, T_SCALE, MAX_SYNTH_MU_MONTHLY, TRADING_DAYS_PER_MONTH,
        )
        raw_loader = getattr(self.portfolio_engine.price_loader, "loader", None)
        if raw_loader is None or not hasattr(raw_loader, "get_price"):
            return []   # 로더가 get_price 미지원(테스트 페이크 등) → 호출부 단일종목 GBM 폴백
        k = len(self.tickers)

        # ── 종목별 mu/sigma + 상관 피팅 (get_price 기반 → KRX_GOLD·금현물 등 특수종목 포함) ──
        # estimate_joint_stats는 price_daily 직접쿼리라 KRX_GOLD(합성 연속 시계열) 등을 못 잡아
        # MVN이 통째 실패 → 단일종목 폴백(과대 mu·배당0). get_price는 모든 종목을 처리한다.
        _look_from = (self.data_end - relativedelta(years=25)).strftime("%Y-%m-%d")
        _end_str   = self.data_end.strftime("%Y-%m-%d")
        rets = {}
        for code in self.tickers:
            try:
                df = raw_loader.get_price(code, _look_from, _end_str, allow_synthetic=False)
                if df is None or len(df) == 0:
                    continue
                df = df.copy(); df["date"] = pd.to_datetime(df["date"])
                s = df.set_index("date")["close"].astype(float).sort_index()
                r = s.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
                r = r[r.abs() < 0.5]
                if len(r) >= 60:
                    rets[code] = r
            except Exception:
                pass
        if len(rets) < k:
            return []   # 통계 못 얻은 종목 존재 → 호출부 단일종목 폴백

        mu_raw = np.array([rets[c].mean()      for c in self.tickers], float)
        sig    = np.array([rets[c].std(ddof=1) for c in self.tickers], float)
        if not (np.all(np.isfinite(mu_raw)) and np.all(sig > 0)):
            return []
        mu_d = np.minimum(mu_raw, MAX_SYNTH_MU_MONTHLY / TRADING_DAYS_PER_MONTH)  # 일일 drift 상한

        aligned = pd.DataFrame({c: rets[c] for c in self.tickers}).dropna()
        if len(aligned) >= 120:
            corr = np.corrcoef(aligned.values, rowvar=False)
            corr = np.nan_to_num(corr, nan=0.0)
            np.fill_diagonal(corr, 1.0)
        else:
            corr = np.eye(k)                                  # 겹침 부족 → 독립 가정
        cov_d = np.outer(sig, sig) * corr
        try:
            chol = np.linalg.cholesky(cov_d + np.eye(k) * 1e-12)
        except Exception:
            # nearest-PSD: 고유값 클리핑 후 재시도
            w, V = np.linalg.eigh((cov_d + cov_d.T) / 2)
            cov_d = V @ np.diag(np.clip(w, 1e-12, None)) @ V.T
            try:
                chol = np.linalg.cholesky(cov_d + np.eye(k) * 1e-12)
            except Exception:
                chol = np.diag(sig)

        # 종목별 연 배당수익률(실데이터 기반) — 합성 가격에 분기배당 주입용.
        div_yield = self._per_ticker_div_yields()

        # 인출기간 캘린더(월말 경계 정확) — 최근 horizon 구간 영업일.
        dates = pd.bdate_range(
            start=(self.data_end - relativedelta(years=self.withdrawal_years)),
            end=self.data_end,
        )
        n_days = len(dates)
        if n_days < 60:
            return []
        t_scale = float(T_SCALE)
        start_str, end_str = dates[0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d")
        # 각 분기(3·6·9·12월) 마지막 영업일 위치 — 배당 지급일.
        q_end_pos = []
        for m in (3, 6, 9, 12):
            for y in sorted(set(dates.year)):
                sub = np.where((dates.year == y) & (dates.month == m))[0]
                if len(sub):
                    q_end_pos.append(sub[-1])

        cases = []
        for p in range(self.mc_paths):
            rng = np.random.default_rng(seed=20260620 + p)
            # 상관 반영 다변량-t 일일수익 (n_days × k)
            z   = rng.standard_t(df=SYNTHETIC_DF, size=(n_days, k)) / t_scale
            ret = z @ chol.T + mu_d                          # 일일 단순수익
            price_data = {}
            for j, code in enumerate(self.tickers):
                close = 100.0 * np.cumprod(1.0 + ret[:, j])
                dy    = max(float(div_yield.get(code, 0.0)), 0.0)
                divs  = np.zeros(n_days)
                if dy > 0:
                    for pos in q_end_pos:
                        divs[pos] = close[pos] * (dy / 4.0)
                df = pd.DataFrame({
                    "open": close, "high": close, "low": close, "close": close,
                    "volume": 1.0, "dividend": divs, "split": 1.0,
                }, index=dates)
                price_data[code] = df
            try:
                res = _run_wd_case_with_data(
                    price_data, list(dates), start_str, end_str,
                    config_dict, strategy_dict, p + 1,
                )
                if res and res.get("history") is not None and not res["history"].empty:
                    m  = self._calc_metrics(res["history"], dates[0], self.withdrawal_years)
                    tv = res["tax_end_value"]
                    m["end_value"]       = tv
                    m["end_value_ratio"] = tv / self.initial_capital if self.initial_capital > 0 else 0.0
                    m["success"]         = tv > 0
                    m["run_id"]          = p + 1
                    m["start"]           = "montecarlo"
                    m["end"]             = "montecarlo"
                    m["is_synthetic"]    = True
                    m["total_fees"]      = float(res.get("total_fees", 0.0))
                    cases.append(m)
            except Exception:
                pass
            if self.progress_callback and (p % 20 == 0):
                self.progress_callback(current=p, total=self.mc_paths, elapsed=0)

        if self.verbose:
            print(f"[WithdrawalAnalyzer] 몬테카를로 {len(cases)}/{self.mc_paths} 경로(독립 상관 합성)")
        return cases

    def _per_ticker_div_yields(self) -> dict:
        """종목별 연 배당수익률(실데이터) — ticker_stats_cache div_yield_mu 재사용."""
        out = {}
        try:
            from modules.retirement.ticker_stats_cache import TickerStatsCache
            db = self.portfolio_engine.price_loader.loader.conn
            tc = TickerStatsCache(db.execute("PRAGMA database_list").fetchone()[2])
            for code in self.tickers:
                st = tc.get_or_compute(code) or {}
                out[code] = float(st.get("div_yield_mu") or 0.0)
            tc.close()
        except Exception:
            for code in self.tickers:
                out.setdefault(code, 0.0)
        return out

    def _estimate_real_yield(self, real_cases: list) -> float:
        """실측 케이스의 연 배당수익률(초기자본 대비) 중앙값 — 합성 배당 보정용."""
        if self.initial_capital <= 0 or self.withdrawal_years <= 0:
            return 0.0
        ys = [
            c.get("total_dividend", 0.0) / (self.initial_capital * self.withdrawal_years)
            for c in real_cases if not c.get("is_synthetic", False)
        ]
        ys = [y for y in ys if y > 0]
        return float(np.median(ys)) if ys else 0.0

    def _run_synthetic_cases(self, n_needed, mu, sigma, div_yield=0.0, start_id=9000):
        results = []
        for i in range(n_needed):
            case = self._simulate_synthetic_case(
                mu, sigma, np.random.default_rng(seed=1000 + i), div_yield=div_yield,
            )
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

        # 배당 커버리지 = 은퇴 1년차 배당수입 / 1년차 인출액.
        # "월 인출 중 배당으로 충당되는 비율"의 직관적 정의(평생 합산은 재투자 성장으로 100% 초과·왜곡).
        first_year_div = 0.0
        if div_col in history.columns and not history.empty:
            _d = pd.to_datetime(history["date"])
            first_year_div = float(history.loc[_d < (start_date + pd.DateOffset(years=1)), div_col].sum())
        first_year_withdrawal = self.monthly_withdrawal * 12
        withdrawal_coverage = (first_year_div / first_year_withdrawal) if first_year_withdrawal > 0 else 0.0

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

        # 연차별 자산비율(연말 시점, 길이 = years) — 인출기 결과창 연도별 잔여자산 차트/표용.
        # 고갈 이후·데이터 부족 구간은 0. 비율은 initial_capital 기준(다운스트림서 원화 환산).
        yearly_ratios = []
        if self.initial_capital > 0:
            _h = history[["date", "portfolio_value"]].copy()
            _h["date"] = pd.to_datetime(_h["date"])
            for y in range(1, years + 1):
                _tgt = start_date + pd.DateOffset(years=y)
                _sub = _h[_h["date"] <= _tgt]
                _val = float(_sub["portfolio_value"].iloc[-1]) if not _sub.empty else 0.0
                yearly_ratios.append(max(_val, 0.0) / self.initial_capital)

        return {
            "success": success, "end_value": end_value,
            "end_value_ratio": end_value_ratio,
            "years_to_depletion": years_to_depletion,
            "sustainable_months": sustainable_months,
            "mdd": mdd, "total_dividend": total_dividend,
            "withdrawal_coverage": withdrawal_coverage,
            "sequence_risk": sequence_risk,
            "dividend_mdd": dividend_mdd,
            "yearly_ratios": yearly_ratios,
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