"""
accumulation_analyzer.py - 최적화 버전
_calc_metrics에서 get_price 호출 완전 제거 → history 데이터만으로 계산
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from typing import Callable, List, Optional


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

    def run(self) -> dict:
        cases = self._run_rolling()
        if not cases:
            raise ValueError("롤링 케이스가 0개입니다.")
        distribution = self._fit_distribution(cases)
        if self.verbose:
            print(f"[AccumulationAnalyzer] {len(cases)}개 케이스 완료")
            print(f"  종료자산 중앙값: {distribution['end_value']['p50']:,.0f}")
            print(f"  CAGR 중앙값:    {distribution['cagr']['p50']:.2%}")
        return {"cases": cases, "distribution": distribution}

    def _run_rolling(self) -> List[dict]:
        cases, cur, run_id = [], self.data_start, 1
        while True:
            end = cur + relativedelta(years=self.accumulation_years)
            if end > self.data_end:
                break
            strategy = self.strategy_factory()
            result   = self.portfolio_engine.run_simulation(
                tickers              = self.tickers,
                start_date           = cur.strftime("%Y-%m-%d"),
                end_date             = end.strftime("%Y-%m-%d"),
                initial_capital      = self.initial_capital,
                monthly_contribution = self.monthly_contribution,
                strategy             = strategy,
                dividend_mode        = self.dividend_mode,
            )
            metrics              = self._calc_metrics(result["history"], self.accumulation_years)
            metrics["run_id"]    = run_id
            metrics["start"]     = cur.strftime("%Y-%m-%d")
            metrics["end"]       = end.strftime("%Y-%m-%d")
            metrics["end_value"] = result["final_value"]
            cases.append(metrics)
            if self.verbose:
                print(f"  [{run_id:03d}] {cur.strftime('%Y-%m')} ~ {end.strftime('%Y-%m')}"
                      f"  종료자산: {result['final_value']:,.0f}  CAGR: {metrics['cagr']:.2%}")
            cur    += relativedelta(months=self.step_months)
            run_id += 1
        return cases

    def _calc_metrics(self, history: pd.DataFrame, years: int) -> dict:
        pv = history["portfolio_value"]

        # 원금 (총 납입액)
        total_contribution = self.monthly_contribution * years * 12 + self.initial_capital

        end_value   = pv.iloc[-1]
        start_value = pv.iloc[0]

        # MDD
        mdd = float(((pv - pv.cummax()) / pv.cummax()).min())

        # 일간 수익률 (납입일 제거)
        daily_returns = pv.pct_change().dropna()
        if "cash_flow" in history.columns:
            contrib_dates = set(
                pd.to_datetime(history.loc[history["cash_flow"] > 0, "date"]).dt.normalize().tolist()
            )
            date_idx = pd.to_datetime(history.loc[daily_returns.index, "date"]).dt.normalize()
            daily_returns = daily_returns[(~date_idx.isin(contrib_dates)).values]

        # Sharpe / Sortino
        std = daily_returns.std()
        sharpe  = (daily_returns.mean() / std * np.sqrt(252)) if std > 0 else 0.0
        dstd    = daily_returns[daily_returns < 0].std()
        sortino = (daily_returns.mean() / dstd * np.sqrt(252)) if (dstd and dstd > 0) else 0.0

        # MWR (IRR) - 월납 타이밍을 정확히 반영한 수익률
        mwr = 0.0
        if "cash_flow" in history.columns:
            cf = history.loc[history["cash_flow"] != 0, ["date", "cash_flow"]].copy()
            cf = pd.concat([cf, pd.DataFrame([{"date": history["date"].iloc[-1], "cash_flow": float(pv.iloc[-1])}])],
                           ignore_index=True)
            cf["date"] = pd.to_datetime(cf["date"])
            cf = cf.sort_values("date").reset_index(drop=True)
            cfs = [-c for c in cf["cash_flow"].iloc[:-1].tolist()] + [float(cf["cash_flow"].iloc[-1])]
            if len(cfs) >= 2 and any(c < 0 for c in cfs) and any(c > 0 for c in cfs):
                try:
                    rate = 0.01
                    for _ in range(200):
                        npv  = sum(c / (1 + rate) ** i for i, c in enumerate(cfs))
                        dnpv = sum(-i * c / (1 + rate) ** (i + 1) for i, c in enumerate(cfs))
                        if abs(dnpv) < 1e-12: break
                        nr = rate - npv / dnpv
                        if abs(nr - rate) < 1e-8:
                            rate = nr; break
                        rate = nr
                    if -0.9 < rate < 10.0:
                        mwr = (1 + rate) ** 12 - 1
                except Exception:
                    mwr = 0.0

        # CAGR = MWR (IRR) 사용 - 월납 타이밍 정확히 반영
        # 단, cash_flow 없거나 MWR 계산 실패 시 단순 CAGR 사용
        if mwr != 0.0:
            cagr = mwr
        elif total_contribution > 0 and end_value > 0:
            cagr = (end_value / total_contribution) ** (1 / years) - 1
        elif start_value > 0 and end_value > 0:
            cagr = (end_value / start_value) ** (1 / years) - 1
        else:
            cagr = 0.0

        calmar = cagr / abs(mdd) if mdd != 0 else 0.0

        # 배당 계산 (div_start 이후 구간만)
        div_col             = "dividend_income"
        dividend_cagr       = 0.0
        dividend_mdd        = 0.0
        total_dividend      = 0.0
        last_year_dividend  = 0.0   # 마지막 연도 연간 배당금
        dividend_yield_on_cost = 0.0  # 마지막 연도 배당금 / 원금

        if div_col in history.columns:
            h = history.copy()
            h["_date"] = pd.to_datetime(h["date"])

            if self.div_start is not None:
                h_div = h[h["_date"] >= self.div_start]
            else:
                h_div = h

            # total_dividend는 절대액 그대로
            total_dividend = float(h_div[div_col].sum())

            h_div = h_div.copy()
            h_div["_year"]  = h_div["_date"].dt.year
            h_div["_month"] = h_div["_date"].dt.month

            # 완전한 연도만
            full_years = set(
                h_div.groupby("_year")["_month"].nunique()
                .pipe(lambda s: s[s >= 12]).index
            )

            h_full = h_div[h_div["_year"].isin(full_years)]

            if not h_full.empty:
                annual_div_abs = h_full.groupby("_year")[div_col].sum()
                qty_cols       = [c for c in h_full.columns if c.endswith("_quantity")]

                if qty_cols:
                    annual_avg_qty = h_full.groupby("_year")[qty_cols].mean().sum(axis=1)
                    valid          = annual_avg_qty[annual_avg_qty > 0].index
                    annual_div_abs = annual_div_abs[annual_div_abs.index.isin(valid)]
                    annual_avg_qty = annual_avg_qty[annual_avg_qty.index.isin(valid)]

                    # 주당 배당금(DPS) 성장률
                    annual_dps = annual_div_abs / annual_avg_qty
                    annual_dps = annual_dps[annual_dps > 0]

                    if len(annual_dps) >= 2:
                        n_y = len(annual_dps) - 1
                        if annual_dps.iloc[0] > 0 and n_y > 0:
                            dividend_cagr = (annual_dps.iloc[-1] / annual_dps.iloc[0]) ** (1 / n_y) - 1
                        roll_max     = annual_dps.cummax()
                        dividend_mdd = float(((annual_dps - roll_max) / roll_max).min())

                    # 마지막 연도 연간 배당금
                    if len(annual_div_abs) > 0:
                        last_year_dividend = float(annual_div_abs.iloc[-1])

                else:
                    # 수량 컬럼 없으면 배당수익률로 fallback
                    annual_pv_mean = h_full.groupby("_year")["portfolio_value"].mean()
                    annual_yield   = annual_div_abs / annual_pv_mean
                    annual_yield   = annual_yield[annual_yield > 0]

                    if len(annual_yield) >= 2:
                        n_y = len(annual_yield) - 1
                        if annual_yield.iloc[0] > 0 and n_y > 0:
                            dividend_cagr = (annual_yield.iloc[-1] / annual_yield.iloc[0]) ** (1 / n_y) - 1
                        roll_max     = annual_yield.cummax()
                        dividend_mdd = float(((annual_yield - roll_max) / roll_max).min())

                    if len(annual_div_abs) > 0:
                        last_year_dividend = float(annual_div_abs.iloc[-1])

                # 배당률 (원금 기준) = 마지막 연도 배당금 / 총 납입액
                if total_contribution > 0 and last_year_dividend > 0:
                    dividend_yield_on_cost = last_year_dividend / total_contribution

        return {
            "cagr":                    cagr,
            "mdd":                     mdd,
            "sharpe":                  sharpe,
            "sortino":                 sortino,
            "calmar":                  calmar,
            "mwr":                     mwr,
            "dividend_cagr":           dividend_cagr,
            "dividend_mdd":            dividend_mdd,
            "total_dividend":          total_dividend,
            "last_year_dividend":      last_year_dividend,       # 마지막 연도 배당금
            "dividend_yield_on_cost":  dividend_yield_on_cost,   # 배당률 (원금 기준)
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