"""
withdrawal_analyzer.py
────────────────────────────────────────────────────────────────────────────────
인출기 롤링 시뮬 → 각 케이스별 지표 추출 → 분포 피팅

역할:
    - n년 롤링 윈도우로 인출 시뮬 반복
    - 초기자산 1원 기준으로 정규화 → 어떤 축적 결과와도 합성 가능
    - 케이스별 생존율, 고갈시점, 종료자산 배수, MDD 계산
    - 지표별 분포 피팅 → retirement_planner에서 축적 분포와 합성

사용 예시:
    analyzer = WithdrawalAnalyzer(
        portfolio_engine   = PortfolioEngine(),
        tickers            = ["SCHD", "QQQ"],
        strategy_factory   = lambda: PeriodicRebalance(...),
        data_start         = "2012-01-01",
        data_end           = "2026-01-01",
        withdrawal_years   = 30,
        monthly_withdrawal = 3_000_000,
        initial_capital    = 100_000_000,   # 정규화 기준 자본
        inflation          = 0.02,
        dividend_mode      = "reinvest",
        step_months        = 1,
    )
    result = analyzer.run()
────────────────────────────────────────────────────────────────────────────────
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
        initial_capital:    float,        # 정규화 기준 자본 (축적 중앙값 등)
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

    # ════════════════════════════════════════════════════════
    # 메인 실행
    # ════════════════════════════════════════════════════════

    def run(self) -> dict:
        """
        Returns
        -------
        dict
            cases        : 케이스별 원시 지표 리스트
            distribution : 지표별 분포 통계
            success_rate : 전체 성공률
        """
        cases = self._run_rolling()

        if not cases:
            raise ValueError("롤링 케이스가 0개입니다. data_start/data_end/withdrawal_years 확인 필요.")

        distribution = self._fit_distribution(cases)
        success_rate = np.mean([c["success"] for c in cases])

        if self.verbose:
            n = len(cases)
            print(f"[WithdrawalAnalyzer] {n}개 케이스 완료")
            print(f"  성공률:              {success_rate:.1%}")
            print(f"  종료자산 배수 중앙값: {distribution['end_value_ratio']['p50']:.2f}x")

        return {
            "cases":        cases,
            "distribution": distribution,
            "success_rate": float(success_rate),
        }

    # ════════════════════════════════════════════════════════
    # 롤링 시뮬
    # ════════════════════════════════════════════════════════

    def _run_rolling(self) -> List[dict]:
        cases  = []
        cur    = self.data_start
        run_id = 1

        while True:
            end = cur + relativedelta(years=self.withdrawal_years)
            if end > self.data_end:
                break

            strategy = self.strategy_factory()

            result = self.portfolio_engine.run_simulation(
                tickers           = self.tickers,
                start_date        = cur.strftime("%Y-%m-%d"),
                end_date          = end.strftime("%Y-%m-%d"),
                initial_capital   = self.initial_capital,
                withdrawal_amount = self.monthly_withdrawal,
                strategy          = strategy,
                dividend_mode     = self.dividend_mode,
                inflation         = self.inflation,
            )

            metrics = self._calc_metrics(
                history     = result["history"],
                start_date  = cur,
                years       = self.withdrawal_years,
            )
            metrics["run_id"] = run_id
            metrics["start"]  = cur.strftime("%Y-%m-%d")
            metrics["end"]    = end.strftime("%Y-%m-%d")

            cases.append(metrics)

            if self.verbose:
                status = "✅" if metrics["success"] else "🔴"
                print(f"  {status} [{run_id:03d}] {cur.strftime('%Y-%m')} ~ {end.strftime('%Y-%m')}"
                      f"  종료자산: {metrics['end_value']:,.0f}"
                      f"  배수: {metrics['end_value_ratio']:.2f}x")

            cur += relativedelta(months=self.step_months)
            run_id += 1

        return cases

    # ════════════════════════════════════════════════════════
    # 케이스별 지표 계산
    # ════════════════════════════════════════════════════════

    def _calc_metrics(
        self,
        history:    pd.DataFrame,
        start_date: pd.Timestamp,
        years:      int,
    ) -> dict:

        pv        = history["portfolio_value"]
        end_value = float(pv.iloc[-1])
        success   = end_value > 0

        # ── 종료자산 배수 (초기자본 대비) ─────────────────────
        # 초기자본 1원 기준으로 정규화 → 어떤 축적 결과와도 합성 가능
        end_value_ratio = end_value / self.initial_capital if self.initial_capital > 0 else 0.0

        # ── 고갈 시점 (연 단위) ───────────────────────────────
        years_to_depletion = float(years)  # 기본값: 전 기간 생존
        if not success:
            zero_mask = pv <= 0
            if zero_mask.any():
                depletion_idx  = zero_mask.idxmax()
                depletion_date = pd.to_datetime(history.loc[depletion_idx, "date"])
                days           = (depletion_date - start_date).days
                years_to_depletion = days / 365.25

        # ── MDD ──────────────────────────────────────────────
        roll_max = pv.cummax()
        drawdown = (pv - roll_max) / roll_max
        mdd      = float(drawdown.min())

        # ── 총 배당 ───────────────────────────────────────────
        div_col        = "dividend_income"
        total_dividend = float(history[div_col].sum()) if div_col in history.columns else 0.0

        # ── 인출 지속 가능 월수 ───────────────────────────────
        sustainable_months = int(years_to_depletion * 12)

        # ── Withdrawal Coverage Ratio ─────────────────────────
        # 배당 수입만으로 인출액의 몇 %를 충당하는지
        # 1.0 = 배당만으로 생활비 100% 충당 (이상적인 은퇴 상태)
        total_withdrawal = self.monthly_withdrawal * years * 12
        if total_withdrawal > 0 and total_dividend > 0:
            withdrawal_coverage = total_dividend / total_withdrawal
        else:
            withdrawal_coverage = 0.0

        # ── 배당 MDD (DPS 기반, 연간 집계) ─────────────────────
        # 분기별은 계절성 노이즈가 커서 연간으로 집계
        # 완전한 연도만 사용 (부분 연도 제외)
        dividend_mdd = 0.0
        if div_col in history.columns:
            _start_dt = pd.to_datetime(history["date"].iloc[0])
            _end_dt   = pd.to_datetime(history["date"].iloc[-1])
            _loader   = self.portfolio_engine.loader

            try:
                _s = self.strategy_factory()
                _tw = _s.target_weights
            except Exception:
                _tw = {t: 1.0 / len(self.tickers) for t in self.tickers}

            # 완전한 연도 파악 (12개월 거래일 있는 해)
            _ref_raw = _loader.get_price(
                self.tickers[0],
                _start_dt.strftime("%Y-%m-%d"),
                _end_dt.strftime("%Y-%m-%d"),
            )
            _ref_raw["year"]  = pd.to_datetime(_ref_raw["date"]).dt.year
            _ref_raw["month"] = pd.to_datetime(_ref_raw["date"]).dt.month
            _months_in_db     = _ref_raw.groupby("year")["month"].nunique()
            _full_years       = set(_months_in_db[_months_in_db >= 12].index)

            _annual_dps = {}
            for _ticker in self.tickers:
                _raw = _loader.get_price(
                    _ticker,
                    _start_dt.strftime("%Y-%m-%d"),
                    _end_dt.strftime("%Y-%m-%d"),
                )
                _raw = _raw[_raw["dividend"] > 0].copy()
                _raw["year"] = pd.to_datetime(_raw["date"]).dt.year
                for _yr, _grp in _raw.groupby("year"):
                    if _yr not in _full_years:
                        continue
                    _annual_dps.setdefault(_yr, 0.0)
                    _annual_dps[_yr] += _tw.get(_ticker, 0) * _grp["dividend"].sum()

            if len(_annual_dps) >= 2:
                _adps = pd.Series(_annual_dps).sort_index()
                _adps = _adps[_adps > 0]
                if len(_adps) >= 2:
                    _roll_max = _adps.cummax()
                    _drawdown = (_adps - _roll_max) / _roll_max
                    dividend_mdd = float(_drawdown.min())

        # ── Sequence of Return Risk ───────────────────────────
        # 은퇴 초반(전반부) vs 후반부 수익률 비교
        # 초반 폭락이 치명적인 이유: 원금이 클 때 손실 발생
        # 지표: 전반부 CAGR - 후반부 CAGR (음수일수록 위험)
        n_days    = len(pv)
        mid       = n_days // 2
        pv_first  = pv.iloc[:mid]
        pv_second = pv.iloc[mid:]

        def _half_cagr(series):
            s, e = float(series.iloc[0]), float(series.iloc[-1])
            n_y  = len(series) / 252
            if s > 0 and e > 0 and n_y > 0:
                return (e / s) ** (1 / n_y) - 1
            return 0.0

        first_half_cagr  = _half_cagr(pv_first)
        second_half_cagr = _half_cagr(pv_second)
        # 양수: 후반이 더 좋음(안전), 음수: 초반이 더 나쁨(위험)
        sequence_risk = first_half_cagr - second_half_cagr

        return {
            "success":              success,
            "end_value":            end_value,
            "end_value_ratio":      end_value_ratio,
            "years_to_depletion":   years_to_depletion,
            "sustainable_months":   sustainable_months,
            "mdd":                  mdd,
            "total_dividend":       total_dividend,
            "withdrawal_coverage":  withdrawal_coverage,
            "sequence_risk":        sequence_risk,
            "dividend_mdd":         dividend_mdd,
        }

    # ════════════════════════════════════════════════════════
    # 분포 피팅
    # ════════════════════════════════════════════════════════

    def _fit_distribution(self, cases: List[dict]) -> dict:
        """
        각 지표별 정규분포 피팅 + percentile 계산.
        end_value_ratio가 핵심 — retirement_planner에서 축적 분포와 곱해서 합성.
        """
        metrics = [
            "end_value_ratio",
            "years_to_depletion",
            "sustainable_months",
            "mdd",
            "total_dividend",
            "withdrawal_coverage",
            "sequence_risk",
            "dividend_mdd",
        ]
        result = {}

        for key in metrics:
            values    = np.array([c[key] for c in cases])
            mu    = float(np.mean(values))
            sigma = float(np.std(values))

            result[key] = {
                "mean":   float(mu),
                "std":    float(sigma),
                "p10":    float(np.percentile(values, 10)),
                "p25":    float(np.percentile(values, 25)),
                "p50":    float(np.percentile(values, 50)),
                "p75":    float(np.percentile(values, 75)),
                "p90":    float(np.percentile(values, 90)),
                "values": values.tolist(),
            }

        # 성공률 분포 (베르누이 → 이항)
        success_values = np.array([float(c["success"]) for c in cases])
        result["success"] = {
            "mean":   float(success_values.mean()),
            "std":    float(success_values.std()),
            "p10":    float(np.percentile(success_values, 10)),
            "p25":    float(np.percentile(success_values, 25)),
            "p50":    float(np.percentile(success_values, 50)),
            "p75":    float(np.percentile(success_values, 75)),
            "p90":    float(np.percentile(success_values, 90)),
            "values": success_values.tolist(),
        }

        return result