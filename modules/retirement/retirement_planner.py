"""
retirement_planner.py
────────────────────────────────────────────────────────────────────────────────
축적 분포 → 11개 percentile 샘플링 → 각각 인출 시뮬 → 정확한 생존율 계산

역할:
    - AccumulationAnalyzer 결과에서 end_value 분포 추출
    - p5, p10, p20, p30, p40, p50, p60, p70, p80, p90, p95 샘플링
    - 각 샘플을 initial_capital로 WithdrawalAnalyzer 실행
    - 케이스별 실제 성공/실패 집계 → 정확한 생존율 계산

사용 예시:
    planner = RetirementPlanner(
        acc_result  = accumulation_analyzer.run(),
        wd_config   = {
            "portfolio_engine":   engine,
            "tickers":            ["SCHD", "QQQ"],
            "strategy_factory":   make_strategy,
            "data_start":         "2012-01-01",
            "data_end":           "2026-01-01",
            "withdrawal_years":   20,
            "monthly_withdrawal": 3_000_000,
            "inflation":          0.02,
            "dividend_mode":      "reinvest",
            "step_months":        6,
        },
        monthly_withdrawal = 3_000_000,
        withdrawal_years   = 20,
    )
    report = planner.run(target_percentile=0.90)
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import numpy as np
from typing import Optional

from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer


# 축적 분포 샘플링 percentile 목록
SAMPLE_PERCENTILES = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95]


class RetirementPlanner:

    def __init__(
        self,
        acc_result:         dict,   # AccumulationAnalyzer.run() 반환값
        wd_config:          dict,   # WithdrawalAnalyzer 생성 파라미터 (initial_capital 제외)
        monthly_withdrawal: float,
        withdrawal_years:   int,
        inflation:          float = 0.0,
        verbose:            bool  = False,
    ):
        self.acc_result         = acc_result
        self.wd_config          = wd_config
        self.monthly_withdrawal = monthly_withdrawal
        self.withdrawal_years   = withdrawal_years
        self.inflation          = inflation
        self.verbose            = verbose

    # ════════════════════════════════════════════════════════
    # 메인 실행
    # ════════════════════════════════════════════════════════

    def run(self, target_percentile: float = 0.90) -> dict:
        """
        Parameters
        ----------
        target_percentile : float
            목표 생존 확률 (예: 0.90 = "90% 확률로 고갈 안 됨")

        Returns
        -------
        dict
            accumulation_summary : 축적기 요약
            sample_results       : percentile별 인출 시뮬 결과
            combined_summary     : 합성 최종 요약
            message              : 사람이 읽을 수 있는 결론 메시지
        """
        acc_summary    = self._summarize_accumulation()
        sample_results = self._run_withdrawal_samples()
        combined       = self._combine(sample_results, target_percentile)
        message        = self._build_message(acc_summary, combined, target_percentile)

        return {
            "accumulation_summary": acc_summary,
            "sample_results":       sample_results,
            "combined_summary":     combined,
            "message":              message,
        }

    # ════════════════════════════════════════════════════════
    # 축적기 요약
    # ════════════════════════════════════════════════════════

    def _summarize_accumulation(self) -> dict:
        dist = self.acc_result["distribution"]

        return {
            "end_value": {
                "p10": dist["end_value"]["p10"],
                "p25": dist["end_value"]["p25"],
                "p50": dist["end_value"]["p50"],
                "p75": dist["end_value"]["p75"],
                "p90": dist["end_value"]["p90"],
            },
            "cagr": {
                "p10": dist["cagr"]["p10"],
                "p50": dist["cagr"]["p50"],
                "p90": dist["cagr"]["p90"],
            },
            "mdd": {
                "p50": dist["mdd"]["p50"],
            },
            "sharpe": {
                "p50": dist["sharpe"]["p50"],
            },
            "dividend_cagr": {
                "p50": dist["dividend_cagr"]["p50"],
            },
        }

    # ════════════════════════════════════════════════════════
    # 11개 percentile 샘플링 → 각각 WithdrawalAnalyzer 실행
    # ════════════════════════════════════════════════════════

    def _run_withdrawal_samples(self) -> list:
        """
        축적 end_value 분포에서 11개 percentile 샘플링.
        각 샘플을 initial_capital로 WithdrawalAnalyzer 실행.

        Returns
        -------
        list of dict
            percentile, initial_capital, success_rate, end_value_ratio, wd_result
        """
        acc_values = np.array(self.acc_result["distribution"]["end_value"]["values"])
        results    = []

        for pct in SAMPLE_PERCENTILES:
            initial_capital = float(np.percentile(acc_values, pct))

            if self.verbose:
                print(f"  [샘플 p{pct:02d}] initial_capital={initial_capital:,.0f}")

            wd_analyzer = WithdrawalAnalyzer(
                **{
                    **self.wd_config,
                    "initial_capital":   initial_capital,
                    "monthly_withdrawal": self.monthly_withdrawal,
                    "withdrawal_years":   self.withdrawal_years,
                    "inflation":          self.inflation,
                    "verbose":            False,
                }
            )
            wd_result = wd_analyzer.run()

            results.append({
                "percentile":      pct,
                "initial_capital": initial_capital,
                "success_rate":    wd_result["success_rate"],
                "end_value_ratio": wd_result["distribution"]["end_value_ratio"]["p50"],
                "end_value_p50":   initial_capital * wd_result["distribution"]["end_value_ratio"]["p50"],
                "wd_result":       wd_result,
            })

            if self.verbose:
                print(f"         성공률={wd_result['success_rate']:.1%}  "
                      f"종료자산={initial_capital * wd_result['distribution']['end_value_ratio']['p50']:,.0f}")

        return results

    # ════════════════════════════════════════════════════════
    # 합성: 샘플별 결과 → 전체 생존율 + 종료자산 분포
    # ════════════════════════════════════════════════════════

    def _combine(self, sample_results: list, target_percentile: float) -> dict:
        """
        11개 샘플 결과를 균등 가중으로 합산.

        생존율: 각 샘플의 success_rate 평균
        종료자산 분포: 각 샘플의 end_value_p50을 분포로 구성
        """
        success_rates  = np.array([r["success_rate"]  for r in sample_results])
        end_values     = np.array([r["end_value_p50"] for r in sample_results])
        initial_caps   = np.array([r["initial_capital"] for r in sample_results])

        # 균등 가중 생존율
        survival_rate = float(np.mean(success_rates))

        # 종료자산 분포
        mu    = float(np.mean(end_values))
        sigma = float(np.std(end_values))

        # target_percentile에 해당하는 종료자산
        # 낮은 percentile = 보수적 추정
        target_end_value = float(np.percentile(end_values, (1 - target_percentile) * 100))

        total_withdrawal = self.monthly_withdrawal * self.withdrawal_years * 12

        return {
            "survival_rate":     survival_rate,
            "target_percentile": target_percentile,
            "target_end_value":  target_end_value,
            "total_withdrawal":  total_withdrawal,
            "combined_end_value": {
                "mean": mu,
                "std":  sigma,
                "p10":  float(np.percentile(end_values, 10)),
                "p25":  float(np.percentile(end_values, 25)),
                "p50":  float(np.percentile(end_values, 50)),
                "p75":  float(np.percentile(end_values, 75)),
                "p90":  float(np.percentile(end_values, 90)),
            },
            "sample_success_rates":   success_rates.tolist(),
            "sample_initial_capitals": initial_caps.tolist(),
            "n_samples":              len(sample_results),
            "n_combined_cases":       len(sample_results),
        }

    # ════════════════════════════════════════════════════════
    # 메시지 생성
    # ════════════════════════════════════════════════════════

    def _build_message(
        self,
        acc_summary:       dict,
        combined:          dict,
        target_percentile: float,
    ) -> dict:

        pct      = int(target_percentile * 100)
        survival = combined["survival_rate"]
        p50      = combined["combined_end_value"]["p50"]
        p10      = combined["combined_end_value"]["p10"]
        target_v = combined["target_end_value"]
        wd_years = self.withdrawal_years
        monthly  = self.monthly_withdrawal

        acc_p50  = acc_summary["end_value"]["p50"]
        acc_p10  = acc_summary["end_value"]["p10"]
        acc_cagr = acc_summary["cagr"]["p50"]

        lines = [
            f"── 축적기 ──────────────────────────────────",
            f"  적립 후 자산 중앙값:  {acc_p50:>15,.0f}원",
            f"  적립 후 자산 p10:    {acc_p10:>15,.0f}원",
            f"  CAGR 중앙값:         {acc_cagr:>14.2%}",
            f"",
            f"── 인출기 ({wd_years}년, 월 {monthly:,.0f}원) ──────────────",
            f"  11개 시나리오 생존율:",
        ]

        # 샘플별 성공률 출력
        for i, (cap, sr) in enumerate(zip(
            combined["sample_initial_capitals"],
            combined["sample_success_rates"],
        )):
            pct_label = SAMPLE_PERCENTILES[i]
            lines.append(f"    p{pct_label:02d} ({cap:>12,.0f}원) → {sr:.1%}")

        lines += [
            f"",
            f"── 합성 결과 ───────────────────────────────",
            f"  전체 생존 확률:      {survival:>14.1%}",
            f"  종료자산 중앙값:     {p50:>15,.0f}원",
            f"  종료자산 p10:        {p10:>15,.0f}원",
            f"",
            f"── {pct}% 신뢰 구간 ──────────────────────────",
            f"  {pct}% 확률로 {wd_years}년 후 자산:  {target_v:>12,.0f}원 이상",
        ]

        if survival >= target_percentile:
            lines.append(f"  ✅ {pct}% 신뢰도로 {wd_years}년간 월 {monthly:,.0f}원 인출 가능")
        else:
            shortfall = target_percentile - survival
            lines.append(f"  ⚠️  목표 신뢰도 {pct}%에 {shortfall:.1%} 부족")
            lines.append(f"     월 인출액을 줄이거나 적립 기간을 늘리는 것을 권장합니다")

        return {
            "text":          "\n".join(lines),
            "survival_rate": survival,
            "is_safe":       survival >= target_percentile,
        }