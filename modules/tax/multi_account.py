"""
modules/tax/multi_account.py
────────────────────────────────────────────────────────────────────────────────
복수 계좌 시뮬레이션 오케스트레이터

각 계좌를 독립적으로 시뮬레이션 후 합산.
세전 / 세후 두 버전을 병렬로 실행 후 캐싱.
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
from typing import Callable

from modules.tax.base_tax     import TaxEngine
from modules.tax.account_tax  import TaxedDividendEngine, check_contribution_limits


def _run_single_account(args: tuple):
    """워커 함수 (multiprocessing용, module-level)."""
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
    from modules.tax.base_tax                   import TaxEngine
    from modules.tax.account_tax                import TaxedDividendEngine

    (
        account,          # dict: type, initial_capital, monthly_contribution, tickers, weights
        strategy_dict,
        data_start,
        data_end,
        dividend_mode,
        rebal_freq,
        drift_threshold,
        user_settings,
        apply_tax,
        price_data,
        dates,
    ) = args

    try:
        account_type = account.get("type", "위탁")
        tickers      = account.get("tickers")     or list(strategy_dict["target_weights"])
        weights      = account.get("weights")     or strategy_dict["target_weights"]
        initial      = float(account.get("initial_capital", 0))
        monthly      = float(account.get("monthly_contribution", 0))

        # 계좌별 투자 제약 검증 (세금 적용 시)
        if apply_tax:
            from modules.tax.account_tax import validate_account_portfolio
            _te = TaxEngine(user_settings)
            _check = validate_account_portfolio(account_type, tickers, weights, _te)
            if not _check["valid"]:
                return {
                    "account_type": account_type,
                    "error":        True,
                    "violations":   _check["violations"],
                    "disclaimer":   _check.get("disclaimer"),
                }

        strategy = PeriodicRebalance(
            target_weights      = weights,
            rebalance_frequency = rebal_freq,
            drift_threshold     = drift_threshold,
        )
        config = SimulationConfig(
            start_date           = data_start,
            end_date             = data_end,
            tickers              = tickers,
            target_weights       = weights,
            initial_capital      = initial,
            monthly_contribution = monthly,
            withdrawal_amount    = 0,
            dividend_mode        = dividend_mode,
            rebalance_frequency  = rebal_freq,
            inflation            = 0.0,
        )

        # 배당 엔진 선택
        base_div_engine = DividendEngine()
        if apply_tax:
            tax_engine  = TaxEngine(user_settings)
            div_engine  = TaxedDividendEngine(base_div_engine, tax_engine, account_type)
        else:
            div_engine  = base_div_engine
            tax_engine  = None

        portfolio = Portfolio(initial)
        loop = SimulationLoop(
            div_engine, ContributionEngine(), WithdrawalEngine(),
            OrderExecutor(), CashAllocator()
        )
        recorder = HistoryRecorder()

        # price_data 슬라이싱
        from pandas import Timestamp
        s_ts, e_ts = Timestamp(data_start), Timestamp(data_end)
        sliced_dates = [d for d in dates if s_ts <= d <= e_ts]
        sliced_data  = {
            t: df.loc[(df.index >= s_ts) & (df.index <= e_ts)]
            for t, df in price_data.items()
        }

        loop.run(portfolio, strategy, config, sliced_data, sliced_dates, recorder)
        history_df = recorder.to_dataframe()

        if history_df.empty:
            return None

        end_value       = float(history_df["portfolio_value"].iloc[-1])
        # 월 기준 납입원금: 영업일 수 ÷ 21 → 월 수로 변환 후 계산
        n_months        = round(len(history_df) / 21)
        total_contrib   = initial + monthly * n_months

        # 수령 시 세금 (세금 ON인 경우)
        after_tax_end = end_value
        if apply_tax and tax_engine:
            after_tax_end = tax_engine.after_tax_withdrawal(
                end_value,
                account_type,
                total_contrib,
                age = user_settings.get("age", 40),
            )

        # 세액공제 환급 계산 (연금저축/IRP)
        annual_deduction = 0.0
        if apply_tax and account_type in ("연금저축", "IRP"):
            te = TaxEngine(user_settings)
            pension_annual = monthly * 12 if account_type == "연금저축" else 0
            irp_annual     = monthly * 12 if account_type == "IRP"     else 0
            annual_deduction = te.annual_tax_deduction(pension_annual, irp_annual)

        years            = len(history_df) / 252
        total_deduction  = annual_deduction * years

        return {
            "account_type":    account_type,
            "end_value":       end_value,
            "after_tax_end":   after_tax_end,
            "total_contrib":   total_contrib,
            "total_deduction": total_deduction,
            "history":         history_df,
            "apply_tax":       apply_tax,
        }

    except Exception as e:
        import traceback; traceback.print_exc()
        return None


# ── 전역 price_data 캐시 (워커 초기화용) ─────────────────────
_w_price_data = {}
_w_dates      = []


def _init_worker(price_data, dates):
    global _w_price_data, _w_dates
    _w_price_data = price_data
    _w_dates      = dates


def _run_account_worker(args_no_data):
    """price_data를 전역에서 가져오는 워커."""
    return _run_single_account((*args_no_data, _w_price_data, _w_dates))


class MultiAccountSimulator:
    """
    복수 계좌 시뮬레이션 + 세전/세후 병렬 실행.

    사용법:
        sim = MultiAccountSimulator(portfolio_engine)
        result = sim.run(
            accounts      = [
                {"type": "연금저축", "initial_capital": 5_000_000, "monthly_contribution": 500_000},
                {"type": "위탁",    "initial_capital": 20_000_000, "monthly_contribution": 1_000_000},
            ],
            tickers       = ["SPY"],
            weights       = {"SPY": 1.0},
            data_start    = "2010-01-01",
            data_end      = "2030-01-01",
            user_settings = {"earned_income": 50_000_000, "age": 40},
        )
    """

    def __init__(self, portfolio_engine):
        self.portfolio_engine = portfolio_engine

    def run(
        self,
        accounts:      list[dict],
        tickers:       list[str],
        weights:       dict,
        data_start:    str,
        data_end:      str,
        dividend_mode: str  = "reinvest",
        rebal_mode:    str  = "none",
        user_settings: dict | None = None,
        deduction_reinvest: bool        = True,
        deduction_account:  str | None  = None,
    ) -> dict:
        """
        세전/세후 두 버전 병렬 실행 후 결과 반환.

        Parameters
        ----------
        accounts            : 계좌 목록 (type, initial_capital, monthly_contribution)
        tickers/weights     : 공통 포트폴리오 (계좌별 미지정 시 사용)
        deduction_reinvest  : 세액공제 환급금을 재투자할지 여부
        deduction_account   : 환급금 재투자 계좌 ('위탁', '연금저축' 등)
        """
        if user_settings is None:
            user_settings = {}

        rebal_freq      = None if rebal_mode == "none" else rebal_mode
        drift_threshold = 0.05 if rebal_mode == "band" else None

        strategy_dict = {
            "target_weights":      weights,
            "rebalance_frequency": rebal_freq,
            "drift_threshold":     drift_threshold,
        }

        # 경고 검증
        warnings = check_contribution_limits(accounts)

        # price data 로드
        price_data, dates = self.portfolio_engine.price_loader.load(
            tickers, data_start, data_end
        )

        # 세전 + 세후 task 목록 생성
        tasks_before, tasks_after = [], []
        for account in accounts:
            base_args = (
                account, strategy_dict,
                data_start, data_end,
                dividend_mode, rebal_freq, drift_threshold,
                user_settings,
            )
            tasks_before.append((*base_args, False))  # apply_tax=False
            tasks_after.append( (*base_args, True))   # apply_tax=True

        all_tasks = tasks_before + tasks_after

        # 병렬 실행
        from multiprocessing import Pool
        N_WORKERS = min(os.cpu_count() or 2, 6)
        try:
            with Pool(N_WORKERS, _init_worker, (price_data, dates)) as pool:
                all_results = pool.map(_run_account_worker, all_tasks)
        except Exception:
            _init_worker(price_data, dates)
            all_results = [_run_account_worker(t) for t in all_tasks]

        n = len(accounts)
        before_results = [r for r in all_results[:n] if r is not None]
        after_results  = [r for r in all_results[n:] if r is not None]

        return {
            "before": self._combine(before_results),
            "after":  self._combine(after_results, deduction_reinvest),
            "warnings": warnings,
            "n_accounts": len(accounts),
        }

    def _combine(self, results: list[dict], include_deduction: bool = False) -> dict:
        if not results:
            return {"total_end_value": 0, "breakdown": [], "metrics": {}}

        total_end   = sum(r["after_tax_end"] for r in results)
        total_ded   = sum(r["total_deduction"] for r in results) if include_deduction else 0
        total_final = total_end + total_ded
        total_inv   = sum(r["total_contrib"] for r in results)

        breakdown = [
            {
                "account_type":    r["account_type"],
                "end_value":       round(r["end_value"]),
                "after_tax_end":   round(r["after_tax_end"]),
                "total_contrib":   round(r["total_contrib"]),
                "total_deduction": round(r["total_deduction"]),
            }
            for r in results
        ]

        # 합산 history (포트폴리오 가치 합계)
        combined_history = self._merge_histories(results)

        return {
            "total_end_value":       round(total_end),
            "total_deduction":       round(total_ded),
            "grand_total":           round(total_final),
            "total_invested":        round(total_inv),
            "total_return":          round((total_end / total_inv - 1) * 100, 2) if total_inv > 0 else 0,
            "breakdown":             breakdown,
            "history":               combined_history,
        }

    def _merge_histories(self, results: list[dict]) -> list[dict]:
        """계좌별 history를 날짜 기준으로 합산."""
        if not results:
            return []

        # 모든 history를 날짜→가치 dict로 변환 후 합산
        date_values: dict = {}
        for r in results:
            h = r.get("history")
            if h is None or h.empty:
                continue
            for _, row in h.iterrows():
                d = str(row["date"])[:10]
                date_values[d] = date_values.get(d, 0) + float(row["portfolio_value"])

        return [
            {"date": d, "portfolio_value": round(v)}
            for d, v in sorted(date_values.items())
        ][::max(1, len(date_values) // 500)]  # 최대 500포인트