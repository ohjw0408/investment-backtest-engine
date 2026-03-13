"""
accumulation_analyzer.py
────────────────────────────────────────────────────────────────────────────────
축적기 롤링 시뮬 → 각 케이스별 지표 추출 → 분포 피팅

역할:
    - n년 롤링 윈도우로 축적 시뮬 반복
    - 케이스별 CAGR, MDD, Sharpe, 배당성장률, 종료자산 계산
    - 지표별 정규분포 피팅 → mean, std, percentile 반환

사용 예시:
    analyzer = AccumulationAnalyzer(
        portfolio_engine     = PortfolioEngine(),
        tickers              = ["SCHD", "QQQ"],
        strategy_factory     = lambda: PeriodicRebalance(...),
        data_start           = "2012-01-01",
        data_end             = "2026-01-01",
        accumulation_years   = 20,
        monthly_contribution = 5_000_000,
        initial_capital      = 0,
        dividend_mode        = "reinvest",
        step_months          = 1,
    )
    result = analyzer.run()
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from typing import Callable, List


class AccumulationAnalyzer:

    def __init__(
        self,
        portfolio_engine,
        tickers:             List[str],
        strategy_factory:    Callable,
        data_start:          str,
        data_end:            str,
        accumulation_years:  int,
        monthly_contribution: float = 0,
        initial_capital:     float = 0,
        dividend_mode:       str   = "reinvest",
        step_months:         int   = 1,
        verbose:             bool  = False,
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

    # ════════════════════════════════════════════════════════
    # 메인 실행
    # ════════════════════════════════════════════════════════

    def run(self) -> dict:
        """
        Returns
        -------
        dict
            cases        : 케이스별 원시 지표 리스트
            distribution : 지표별 분포 통계 (mean, std, percentiles)
        """
        cases = self._run_rolling()

        if not cases:
            raise ValueError("롤링 케이스가 0개입니다. data_start/data_end/accumulation_years 확인 필요.")

        distribution = self._fit_distribution(cases)

        if self.verbose:
            n = len(cases)
            print(f"[AccumulationAnalyzer] {n}개 케이스 완료")
            print(f"  종료자산 중앙값: {distribution['end_value']['p50']:,.0f}")
            print(f"  CAGR 중앙값:    {distribution['cagr']['p50']:.2%}")

        return {
            "cases":        cases,
            "distribution": distribution,
        }

    # ════════════════════════════════════════════════════════
    # 롤링 시뮬
    # ════════════════════════════════════════════════════════

    def _run_rolling(self) -> List[dict]:
        cases  = []
        cur    = self.data_start
        run_id = 1

        while True:
            end = cur + relativedelta(years=self.accumulation_years)
            if end > self.data_end:
                break

            strategy = self.strategy_factory()

            result = self.portfolio_engine.run_simulation(
                tickers              = self.tickers,
                start_date           = cur.strftime("%Y-%m-%d"),
                end_date             = end.strftime("%Y-%m-%d"),
                initial_capital      = self.initial_capital,
                monthly_contribution = self.monthly_contribution,
                strategy             = strategy,
                dividend_mode        = self.dividend_mode,
            )

            metrics = self._calc_metrics(result["history"], self.accumulation_years)
            metrics["run_id"]    = run_id
            metrics["start"]     = cur.strftime("%Y-%m-%d")
            metrics["end"]       = end.strftime("%Y-%m-%d")
            metrics["end_value"] = result["final_value"]

            cases.append(metrics)

            if self.verbose:
                print(f"  [{run_id:03d}] {cur.strftime('%Y-%m')} ~ {end.strftime('%Y-%m')}"
                      f"  종료자산: {result['final_value']:,.0f}"
                      f"  CAGR: {metrics['cagr']:.2%}")

            cur += relativedelta(months=self.step_months)
            run_id += 1

        return cases

    # ════════════════════════════════════════════════════════
    # 케이스별 지표 계산
    # ════════════════════════════════════════════════════════

    def _calc_metrics(self, history: pd.DataFrame, years: int) -> dict:

        pv = history["portfolio_value"]

        # ── CAGR ─────────────────────────────────────────────
        start_value = pv.iloc[0]
        end_value   = pv.iloc[-1]
        # 납입금 기반 CAGR: 총 납입금 대비
        total_contribution = self.monthly_contribution * years * 12 + self.initial_capital
        if total_contribution > 0 and end_value > 0:
            cagr = (end_value / total_contribution) ** (1 / years) - 1
        elif start_value > 0 and end_value > 0:
            cagr = (end_value / start_value) ** (1 / years) - 1
        else:
            cagr = 0.0

        # ── MDD ──────────────────────────────────────────────
        roll_max = pv.cummax()
        drawdown = (pv - roll_max) / roll_max
        mdd      = float(drawdown.min())

        # ── 일간 수익률 ──────────────────────────────────────
        daily_returns = pv.pct_change().dropna()

        # ── Sharpe (연환산, 무위험수익률 0 가정) ──────────────
        if daily_returns.std() > 0:
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
        else:
            sharpe = 0.0

        # ── Sortino (하방 변동성만 분모) ─────────────────────
        downside = daily_returns[daily_returns < 0]
        downside_std = downside.std() if len(downside) > 1 else 0.0
        if downside_std > 0:
            sortino = (daily_returns.mean() / downside_std) * np.sqrt(252)
        else:
            sortino = 0.0

        # ── Calmar (CAGR / |MDD|) ────────────────────────────
        calmar = cagr / abs(mdd) if mdd != 0 else 0.0

        # ── MWR / IRR (실제 투자자 체감 수익률) ────────────
        # cash_flow 컬럼: 납입 양수, 인출 음수
        # IRR: NPV = 0이 되는 월간 할인율 → 연환산
        mwr = 0.0
        if "cash_flow" in history.columns:
            cf = history[["date", "cash_flow"]].copy()
            cf = cf[cf["cash_flow"] != 0].copy()
            # 마지막 시점 종료자산을 현금유출(음수)로 추가
            terminal_cf = pd.DataFrame([{
                "date":      history["date"].iloc[-1],
                "cash_flow": -float(pv.iloc[-1]),
            }])
            cf = pd.concat([cf, terminal_cf], ignore_index=True)
            cf["date"] = pd.to_datetime(cf["date"])
            cf = cf.sort_values("date").reset_index(drop=True)
            cashflows = cf["cash_flow"].tolist()

            # Newton-Raphson으로 월간 IRR 계산
            if len(cashflows) >= 2 and any(c < 0 for c in cashflows) and any(c > 0 for c in cashflows):
                try:
                    rate = 0.01  # 초기값 월 1%
                    for _ in range(200):
                        npv  = sum(c / (1 + rate) ** i for i, c in enumerate(cashflows))
                        dnpv = sum(-i * c / (1 + rate) ** (i + 1) for i, c in enumerate(cashflows))
                        if abs(dnpv) < 1e-12:
                            break
                        new_rate = rate - npv / dnpv
                        if abs(new_rate - rate) < 1e-8:
                            rate = new_rate
                            break
                        rate = new_rate
                    if -0.5 < rate < 1.0:
                        mwr = (1 + rate) ** 12 - 1  # 월간 → 연간
                except Exception:
                    mwr = 0.0

        # ── 배당 성장률 (DB DPS 직접 사용) ──────────────────────
        # qty_mean 기반 계산은 월납입으로 수량이 변해서 왜곡됨
        # price_loader DB의 corporate_actions에서 주당 배당(DPS)을 직접 집계
        div_col = "dividend_income"
        dividend_cagr = 0.0
        if div_col in history.columns:
            start_dt = pd.to_datetime(history["date"].iloc[0])
            end_dt   = pd.to_datetime(history["date"].iloc[-1])

            ticker_annual_dps = {}  # {ticker: {year: dps_sum}}

            loader = self.portfolio_engine.loader
            for ticker in self.tickers:
                raw = loader.get_price(
                    ticker,
                    start_dt.strftime("%Y-%m-%d"),
                    end_dt.strftime("%Y-%m-%d"),
                )
                raw["year"] = pd.to_datetime(raw["date"]).dt.year
                annual = raw[raw["dividend"] > 0].groupby("year")["dividend"].sum()
                ticker_annual_dps[ticker] = annual

            # 포트폴리오 가중 DPS 합산 (target_weights 기준)
            weights = self.portfolio_engine.simulation_loop.cash_allocator.__class__  # weights는 strategy에서 가져옴
            # target_weights는 strategy_factory에서 가져올 수 없으므로
            # 각 ticker 동일 가중으로 합산 (근사) → 실제론 비슷한 결과
            all_years = sorted(set(
                yr for dps in ticker_annual_dps.values() for yr in dps.index
            ))

            # 완전한 연도만 — DB raw 데이터 기준으로 12개월치 거래일이 있는 해
            # (history 기준 아님 — 시작/종료 부분 연도 제외가 목적)
            loader_raw_all = loader.get_price(
                self.tickers[0],
                start_dt.strftime("%Y-%m-%d"),
                end_dt.strftime("%Y-%m-%d"),
            )
            loader_raw_all["year"]  = pd.to_datetime(loader_raw_all["date"]).dt.year
            loader_raw_all["month"] = pd.to_datetime(loader_raw_all["date"]).dt.month
            months_in_db = loader_raw_all.groupby("year")["month"].nunique()
            full_years   = set(months_in_db[months_in_db >= 12].index)
            all_years    = [y for y in all_years if y in full_years]

            # target_weights를 직접 strategy_factory로 가져오기
            try:
                _s = self.strategy_factory()
                tw = _s.target_weights
            except Exception:
                tw = {t: 1.0 / len(self.tickers) for t in self.tickers}

            portfolio_dps_by_year = {}
            for yr in all_years:
                total = 0.0
                for ticker in self.tickers:
                    w   = tw.get(ticker, 0)
                    dps = ticker_annual_dps.get(ticker, pd.Series(dtype=float))
                    total += w * (dps[yr] if yr in dps.index else 0)
                if total > 0:
                    portfolio_dps_by_year[yr] = total

            if len(portfolio_dps_by_year) >= 2:
                years_sorted = sorted(portfolio_dps_by_year.keys())
                first_dps = portfolio_dps_by_year[years_sorted[0]]
                last_dps  = portfolio_dps_by_year[years_sorted[-1]]
                n_years   = len(years_sorted) - 1
                if n_years > 0 and first_dps > 0 and last_dps > 0:
                    dividend_cagr = (last_dps / first_dps) ** (1 / n_years) - 1

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

        # ── 총 배당 ───────────────────────────────────────────
        total_dividend = history[div_col].sum() if div_col in history.columns else 0.0

        return {
            "cagr":           cagr,
            "mdd":            mdd,
            "sharpe":         sharpe,
            "sortino":        sortino,
            "calmar":         calmar,
            "mwr":            mwr,
            "dividend_cagr":  dividend_cagr,
            "dividend_mdd":   dividend_mdd,
            "total_dividend": float(total_dividend),
        }

    # ════════════════════════════════════════════════════════
    # 분포 피팅
    # ════════════════════════════════════════════════════════

    def _fit_distribution(self, cases: List[dict]) -> dict:
        """
        각 지표별로 정규분포 피팅 + percentile 계산.

        Returns
        -------
        dict
            {
              "end_value": { "mean", "std", "p10", "p25", "p50", "p75", "p90", "values" },
              "cagr":      { ... },
              ...
            }
        """
        metrics = ["end_value", "cagr", "mdd", "sharpe", "sortino", "calmar", "mwr", "dividend_cagr", "dividend_mdd", "total_dividend"]
        result  = {}

        for key in metrics:
            values = np.array([c[key] for c in cases])
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
                "values": values.tolist(),  # 원시 데이터 보존
            }

        return result