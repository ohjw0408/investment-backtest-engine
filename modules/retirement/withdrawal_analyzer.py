"""
withdrawal_analyzer.py - 최적화 버전
_calc_metrics에서 get_price 호출 완전 제거 → history 데이터만으로 계산
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from typing import Callable, List


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

    def run(self) -> dict:
        cases = self._run_rolling()
        if not cases:
            raise ValueError("롤링 케이스가 0개입니다.")
        distribution = self._fit_distribution(cases)
        success_rate = np.mean([c["success"] for c in cases])
        if self.verbose:
            print(f"[WithdrawalAnalyzer] {len(cases)}개 케이스 완료")
            print(f"  성공률: {success_rate:.1%}")
        return {"cases": cases, "distribution": distribution, "success_rate": float(success_rate)}

    def _run_rolling(self) -> List[dict]:
        cases, cur, run_id = [], self.data_start, 1
        while True:
            end = cur + relativedelta(years=self.withdrawal_years)
            if end > self.data_end:
                break
            strategy = self.strategy_factory()
            result   = self.portfolio_engine.run_simulation(
                tickers           = self.tickers,
                start_date        = cur.strftime("%Y-%m-%d"),
                end_date          = end.strftime("%Y-%m-%d"),
                initial_capital   = self.initial_capital,
                withdrawal_amount = self.monthly_withdrawal,
                strategy          = strategy,
                dividend_mode     = self.dividend_mode,
                inflation         = self.inflation,
            )
            metrics           = self._calc_metrics(result["history"], cur, self.withdrawal_years)
            metrics["run_id"] = run_id
            metrics["start"]  = cur.strftime("%Y-%m-%d")
            metrics["end"]    = end.strftime("%Y-%m-%d")
            cases.append(metrics)
            if self.verbose:
                status = "✅" if metrics["success"] else "🔴"
                print(f"  {status} [{run_id:03d}] {cur.strftime('%Y-%m')} ~ {end.strftime('%Y-%m')}"
                      f"  종료자산: {metrics['end_value']:,.0f}  배수: {metrics['end_value_ratio']:.2f}x")
            cur    += relativedelta(months=self.step_months)
            run_id += 1
        return cases

    def _calc_metrics(self, history: pd.DataFrame, start_date: pd.Timestamp, years: int) -> dict:
        pv        = history["portfolio_value"]
        end_value = float(pv.iloc[-1])
        success   = end_value > 0

        # 종료자산 배수
        end_value_ratio = end_value / self.initial_capital if self.initial_capital > 0 else 0.0

        # 고갈 시점
        years_to_depletion = float(years)
        if not success:
            zero_mask = pv <= 0
            if zero_mask.any():
                depletion_date     = pd.to_datetime(history.loc[zero_mask.idxmax(), "date"])
                years_to_depletion = (depletion_date - start_date).days / 365.25

        # MDD
        mdd = float(((pv - pv.cummax()) / pv.cummax()).min())

        # 총 배당
        div_col        = "dividend_income"
        total_dividend = float(history[div_col].sum()) if div_col in history.columns else 0.0

        # 지속 가능 월수
        sustainable_months = int(years_to_depletion * 12)

        # 배당 커버리지
        total_withdrawal    = self.monthly_withdrawal * years * 12
        withdrawal_coverage = (total_dividend / total_withdrawal) if total_withdrawal > 0 and total_dividend > 0 else 0.0

        # 배당 MDD (history에서 직접 계산)
        dividend_mdd = 0.0
        if div_col in history.columns:
            h = history.copy()
            h["_year"]  = pd.to_datetime(h["date"]).dt.year
            h["_month"] = pd.to_datetime(h["date"]).dt.month
            full_years  = set(
                h.groupby("_year")["_month"].nunique()
                .pipe(lambda s: s[s >= 12]).index
            )
            annual_div = (
                h[h["_year"].isin(full_years)]
                .groupby("_year")[div_col].sum()
            )
            annual_div = annual_div[annual_div > 0]
            if len(annual_div) >= 2:
                roll_max     = annual_div.cummax()
                dividend_mdd = float(((annual_div - roll_max) / roll_max).min())

        # Sequence of Return Risk
        mid = len(pv) // 2

        def _half_cagr(s):
            sv, ev = float(s.iloc[0]), float(s.iloc[-1])
            ny = len(s) / 252
            return (ev / sv) ** (1 / ny) - 1 if sv > 0 and ev > 0 and ny > 0 else 0.0

        sequence_risk = _half_cagr(pv.iloc[:mid]) - _half_cagr(pv.iloc[mid:])

        return {
            "success":             success,
            "end_value":           end_value,
            "end_value_ratio":     end_value_ratio,
            "years_to_depletion":  years_to_depletion,
            "sustainable_months":  sustainable_months,
            "mdd":                 mdd,
            "total_dividend":      total_dividend,
            "withdrawal_coverage": withdrawal_coverage,
            "sequence_risk":       sequence_risk,
            "dividend_mdd":        dividend_mdd,
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