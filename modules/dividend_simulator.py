"""
dividend_simulator.py
배당금 목표 역산 전용 경량 시뮬레이터
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional, List, Dict


class DividendSimulator:

    def __init__(self, loader, tickers, weights, div_mode="reinvest", step_months=3):
        self.loader      = loader
        self.tickers     = tickers
        self.weights     = weights
        self.div_mode    = div_mode
        self.step_months = step_months
        self._price_cache: Dict[str, pd.DataFrame] = {}
        self._sim_cache:   Dict[str, List[float]]   = {}  # (seed, monthly, years) 캐시

    def _load(self, ticker: str) -> pd.DataFrame:
        if ticker in self._price_cache:
            return self._price_cache[ticker]
        today = pd.Timestamp.today().strftime("%Y-%m-%d")
        df = self.loader.get_price(ticker, self.loader.USD_KRW_START, today)
        if df.empty:
            self._price_cache[ticker] = pd.DataFrame()
            return pd.DataFrame()
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df[["close", "dividend"]].copy()
        df["dividend"] = df["dividend"].fillna(0)
        self._price_cache[ticker] = df
        return df

    def _get_actual_start(self) -> Optional[str]:
        starts = []
        for t in self.tickers:
            df = self._load(t)
            if not df.empty:
                starts.append(df.index.min())
        return max(starts).strftime("%Y-%m-%d") if starts else None

    def _simulate_one(self, seed, monthly, years, start_date) -> float:
        start = pd.Timestamp(start_date)
        end   = start + pd.DateOffset(years=years)

        data = {}
        for t in self.tickers:
            df = self._load(t)
            if df.empty:
                return 0.0
            sliced = df.loc[start:end]
            if sliced.empty:
                return 0.0
            data[t] = sliced

        # 월별 날짜 + 월 시작일 미리 계산 (매 루프마다 계산 방지)
        months = pd.date_range(start, end, freq="ME")
        month_starts = months - pd.offsets.MonthBegin(1)

        quantities = {t: 0.0 for t in self.tickers}

        if seed > 0:
            for t in self.tickers:
                price = float(data[t]["close"].iloc[0])
                if price > 0:
                    quantities[t] += (seed * self.weights[t]) / price

        paid_div_dates = {t: set() for t in self.tickers}
        last_year_start = end - pd.DateOffset(years=1)
        last_year_div   = 0.0

        # 배당 데이터 미리 numpy 배열로 변환 (iterrows 대신 itertuples)
        div_data = {}
        for t in self.tickers:
            df = data[t]
            div_df = df[df["dividend"] > 0]
            div_data[t] = list(div_df.itertuples())  # iterrows보다 3~5배 빠름

        for month_end, month_start_d in zip(months, month_starts):
            # 월 적립 매수 (기존 로직 그대로, loc 슬라이싱만 searchsorted로 교체)
            if monthly > 0:
                for t in self.tickers:
                    close_series = data[t]["close"]
                    idx = close_series.index.searchsorted(month_end, side='right') - 1
                    if idx >= 0:
                        price = float(close_series.iloc[idx])
                        if price > 0:
                            quantities[t] += (monthly * self.weights[t]) / price

            # 배당 처리 (기존 로직 그대로, itertuples로 교체)
            for t in self.tickers:
                for row in div_data[t]:
                    div_date = row.Index
                    if div_date < month_start_d or div_date > month_end:
                        continue
                    if div_date in paid_div_dates[t]:
                        continue
                    paid_div_dates[t].add(div_date)
                    div_total = quantities[t] * float(row.dividend)
                    if div_total <= 0:
                        continue
                    if div_date >= last_year_start:
                        last_year_div += div_total
                    if self.div_mode == "reinvest":
                        price = float(row.close)
                        if price > 0:
                            quantities[t] += div_total / price

        return last_year_div

    MIN_CASES = 30  # 롤링 케이스 최소 보장 개수

    def _calc_div_stats(self) -> dict:
        """
        실제 배당 데이터에서 배당률/성장률 분포 계산
        배당률 = 분기 DPS / 주가 (환율 중립)
        """
        stats = {}
        for t in self.tickers:
            df = self._load(t)
            if df.empty:
                continue
            div_df = df[df["dividend"] > 0].copy()
            if div_df.empty:
                continue

            # 분기별 배당률 계산
            div_df["div_yield"] = div_df["dividend"] / df["close"].reindex(div_df.index)
            div_df = div_df.dropna(subset=["div_yield"])
            div_df = div_df[div_df["div_yield"] > 0]

            # 연간 DPS 합계로 성장률 계산 (첫 해/현재 연도 제외)
            div_df["year"] = div_df.index.year
            annual = div_df.groupby("year")["dividend"].sum()
            current_year = pd.Timestamp.today().year
            # 첫 해(데이터 부족), 현재 연도(미완성) 제외
            annual = annual.iloc[1:]
            if annual.index[-1] == current_year:
                annual = annual.iloc[:-1]
            growth = annual.pct_change().dropna()
            growth = growth[growth.abs() < 2.0]  # 극단값 제거 (200% 초과)

            stats[t] = {
                "div_yield_mean": float(div_df["div_yield"].mean()),
                "div_yield_std":  float(div_df["div_yield"].std()),
                "growth_mean":    float(growth.mean()) if len(growth) > 0 else 0.10,
                "growth_std":     float(growth.std())  if len(growth) > 0 else 0.07,
                "div_freq":       int(round(len(div_df) / max(1, (div_df.index[-1] - div_df.index[0]).days / 365))),
            }
        return stats

    def _simulate_synthetic(self, seed, monthly, years, div_stats, rng) -> float:
        """
        가상 데이터 기반 시뮬 (자산가치 기반, 주가 불필요)
        포트폴리오 전체 자산에 배당률 적용
        """
        # 포트폴리오 가중 평균 배당률/성장률
        total_yield_mean = sum(div_stats[t]["div_yield_mean"] * self.weights[t] for t in self.tickers if t in div_stats)
        total_yield_std  = sum(div_stats[t]["div_yield_std"]  * self.weights[t] for t in self.tickers if t in div_stats)
        growth_mean      = sum(div_stats[t]["growth_mean"]    * self.weights[t] for t in self.tickers if t in div_stats)
        growth_std       = sum(div_stats[t]["growth_std"]     * self.weights[t] for t in self.tickers if t in div_stats)
        div_freq         = max(div_stats[t]["div_freq"] for t in self.tickers if t in div_stats) if div_stats else 4

        # 연간 배당률 성장 적용한 분기별 배당률 시계열 생성
        n_quarters = years * 4
        quarterly_yields = []
        current_yield = max(0.001, rng.normal(total_yield_mean, total_yield_std))
        for q in range(n_quarters):
            if q > 0 and q % 4 == 0:
                # 매년 성장률 적용
                annual_growth = rng.normal(growth_mean, growth_std)
                annual_growth = max(-0.30, min(0.60, annual_growth))  # -30%~60% 클리핑
                current_yield *= (1 + annual_growth)
                current_yield  = max(0.001, current_yield)
            y = max(0.0, rng.normal(current_yield, total_yield_std * 0.5))
            quarterly_yields.append(y)

        # 월별 시뮬
        asset = float(seed)
        last_year_start_q = max(0, n_quarters - 4)
        last_year_div = 0.0
        months_per_quarter = 3
        div_months = set(range(0, n_quarters * months_per_quarter, months_per_quarter))  # 분기 첫 달

        for m in range(years * 12):
            asset += monthly
            q = m // 3
            # 분기 배당 (월배당 ETF면 매달, 분기면 3개월마다)
            if div_freq >= 12:
                # 월배당
                div = asset * quarterly_yields[min(q, n_quarters-1)] / 3.0
                if div > 0:
                    if q >= last_year_start_q:
                        last_year_div += div
                    if self.div_mode == "reinvest":
                        asset += div
            else:
                # 분기배당: 분기 마지막 달(2, 5, 8, 11월)에 지급
                if m % 3 == 2:
                    div = asset * quarterly_yields[min(q, n_quarters-1)]
                    if div > 0:
                        if q >= last_year_start_q:
                            last_year_div += div
                        if self.div_mode == "reinvest":
                            asset += div

        return last_year_div

    def _run_synthetic_rolling(self, seed, monthly, years, n_needed) -> List[float]:
        """
        가상 데이터로 n_needed개 케이스 생성
        충분히 긴 가상 시계열 1개 만들어서 롤링
        """
        div_stats = self._calc_div_stats()
        if not div_stats:
            return []

        rng = np.random.default_rng(seed=42)  # 재현성을 위해 고정 시드
        results = []

        # 필요 케이스만큼 독립 시뮬 실행 (각각 다른 랜덤 시드)
        for i in range(n_needed):
            rng_i = np.random.default_rng(seed=i)
            val = self._simulate_synthetic(seed, monthly, years, div_stats, rng_i)
            if val > 0:
                results.append(val)

        return results

    def _run_rolling(self, seed, monthly, years) -> List[float]:
        cache_key = f"{round(seed,-4)}_{round(monthly,-4)}_{years}"
        if cache_key in self._sim_cache:
            return self._sim_cache[cache_key]

        actual_start = self._get_actual_start()
        if actual_start is None:
            return []

        actual_start_dt = pd.Timestamp(actual_start)
        sim_end_latest  = pd.Timestamp.today() - pd.DateOffset(years=years)

        # 실제 데이터 롤링
        real_results = []
        if actual_start_dt <= sim_end_latest:
            roll_starts = pd.date_range(actual_start_dt, sim_end_latest, freq=f"{self.step_months}ME")
            for start in roll_starts:
                val = self._simulate_one(seed, monthly, years, start.strftime("%Y-%m-%d"))
                if val > 0:
                    real_results.append(val)

        # 케이스 부족 시 가상 데이터로 보충
        n_real    = len(real_results)
        n_needed  = max(0, self.MIN_CASES - n_real)
        synthetic = self._run_synthetic_rolling(seed, monthly, years, n_needed) if n_needed > 0 else []

        results = real_results + synthetic
        self._sim_cache[cache_key] = results
        return results

    def _check_prob(self, divs, target_monthly, probability) -> bool:
        if not divs:
            return False
        return float((np.array(divs) >= target_monthly * 12).mean()) >= probability

    def _calc_prob(self, divs, target_monthly) -> float:
        if not divs:
            return 0.0
        return float((np.array(divs) >= target_monthly * 12).mean())

    # ── 앵커 찾기 ──────────────────────────────────────

    def _logistic_fit(self, xs, probs, target_prob):
        import math
        def logit(p):
            return math.log(max(0.001, min(0.999, p)) / (1 - max(0.001, min(0.999, p))))
        pts = [(x, logit(p)) for x, p in zip(xs, probs)]
        if len(pts) < 2:
            for x, p in zip(xs, probs):
                if p >= target_prob:
                    return float(x)
            return None
        n   = len(pts)
        sx  = sum(x for x, y in pts)
        sy  = sum(y for x, y in pts)
        sxy = sum(x*y for x, y in pts)
        sx2 = sum(x*x for x, y in pts)
        denom = n*sx2 - sx*sx
        if abs(denom) < 1e-10:
            return None
        k = (n*sxy - sx*sy) / denom
        b = (sy - k*sx) / n
        if abs(k) < 1e-15:
            return None
        return max(0.0, (logit(target_prob) - b) / k)

    def _find_anchor_years(self, seed, monthly, target_monthly_div, probability):
        checkpoints = [1, 5, 10, 15, 20, 25, 30]
        xs, probs = [], []
        lo_y = 1
        for y in checkpoints:
            p = self._calc_prob(self._run_rolling(seed, monthly, y), target_monthly_div)
            xs.append(y)
            probs.append(p)
            if p >= probability:
                # 로지스틱 피팅으로 대략 추정
                fitted = self._logistic_fit(xs, probs, probability)
                rough = max(lo_y, min(30, round(fitted))) if fitted else y
                # 추정값 근처 ±3년을 1년 단위로 정밀 탐색
                for yy in range(max(lo_y, rough - 3), rough + 1):
                    pp = self._calc_prob(self._run_rolling(seed, monthly, yy), target_monthly_div)
                    if pp >= probability:
                        return yy
                return rough
            lo_y = y
        return None

    def _find_anchor_seed(self, monthly, years, target_monthly_div, probability):
        step = target_monthly_div * 10
        xs, probs = [], []
        for i in range(8):
            s = step * i
            p = self._calc_prob(self._run_rolling(s, monthly, years), target_monthly_div)
            xs.append(s)
            probs.append(p)
            if p >= probability:
                fitted = self._logistic_fit(xs, probs, probability)
                if fitted is not None:
                    return round(max(0.0, fitted), -4)
                return round(s, -4)
        return None

    def _find_anchor_monthly(self, seed, years, target_monthly_div, probability):
        step = target_monthly_div * 0.5
        xs, probs = [], []
        for i in range(8):
            m = step * i
            p = self._calc_prob(self._run_rolling(seed, m, years), target_monthly_div)
            xs.append(m)
            probs.append(p)
            if p >= probability:
                fitted = self._logistic_fit(xs, probs, probability)
                if fitted is not None:
                    return round(max(0.0, fitted), -4)
                return round(m, -4)
        return None

    # ── 앵커 기준 5포인트 확률 곡선 ─────────────────────

    def _years_curve_points(self, seed, monthly, target_monthly_div, probability):
        # 고정 스텝 5년, 앵커 +-2스텝
        anchor = self._find_anchor_years(seed, monthly, target_monthly_div, probability) or 30
        step = 5
        candidates = sorted(set([
            max(1,  anchor - step * 2),
            max(1,  anchor - step),
            anchor,
            min(50, anchor + step),
            min(50, anchor + step * 2),
        ]))
        points = []
        for y in candidates:
            prob = self._calc_prob(self._run_rolling(seed, monthly, y), target_monthly_div)
            points.append({"years": y, "probability": round(prob, 4)})
        return points

    def _seed_curve_points(self, monthly, years, target_monthly_div, probability):
        # 로그 스케일: anchor/4, /2, x1, x2, x4
        anchor = self._find_anchor_seed(monthly, years, target_monthly_div, probability)
        if anchor is None:
            anchor = target_monthly_div * 50
        if anchor == 0:
            step = target_monthly_div * 10
            raw = [0, step, step*2, step*4, step*8]
        else:
            raw = [anchor/4, anchor/2, anchor, anchor*2, anchor*4]
        candidates = sorted(set([max(0, round(v, -4)) for v in raw]))
        points = []
        for s in candidates:
            prob = self._calc_prob(self._run_rolling(s, monthly, years), target_monthly_div)
            points.append({"seed": int(s), "probability": round(prob, 4)})
        return points

    def _monthly_curve_points(self, seed, years, target_monthly_div, probability):
        # 로그 스케일: anchor/4, /2, x1, x2, x4
        anchor = self._find_anchor_monthly(seed, years, target_monthly_div, probability)
        if anchor is None:
            anchor = target_monthly_div * 5
        if anchor == 0:
            step = target_monthly_div * 0.5
            raw = [0, step, step*2, step*4, step*8]
        else:
            raw = [anchor/4, anchor/2, anchor, anchor*2, anchor*4]
        candidates = sorted(set([max(0, round(v, -4)) for v in raw]))
        points = []
        for m in candidates:
            prob = self._calc_prob(self._run_rolling(seed, m, years), target_monthly_div)
            points.append({"monthly": int(m), "probability": round(prob, 4)})
        return points

    # ── 공개 API ────────────────────────────────────────

    def get_probability(self, seed, monthly, years, target_monthly_div) -> dict:
        target_annual = target_monthly_div * 12
        divs = self._run_rolling(seed, monthly, years)
        if not divs:
            return {"probability": 0.0, "cases_count": 0, "distribution": {}}
        arr  = np.array(divs)
        prob = float((arr >= target_annual).mean())
        return {
            "probability":  round(prob, 4),
            "cases_count":  len(divs),
            "distribution": {
                "p10":  round(float(np.percentile(arr, 10))),
                "p25":  round(float(np.percentile(arr, 25))),
                "p50":  round(float(np.percentile(arr, 50))),
                "p75":  round(float(np.percentile(arr, 75))),
                "p90":  round(float(np.percentile(arr, 90))),
                "mean": round(float(np.mean(arr))),
            }
        }

    def get_probability_curve(self, seed, monthly, years, targets) -> List[dict]:
        divs = self._run_rolling(seed, monthly, years)
        if not divs:
            return []
        arr = np.array(divs)
        return [
            {"target_monthly": t, "probability": round(float((arr >= t * 12).mean()), 4)}
            for t in targets
        ]

    def _multi_anchors_from_curve(self, curve: List[dict], xkey: str, prob_levels: List[float]) -> dict:
        """커브 데이터에 로지스틱 피팅해서 여러 확률 기준 앵커값 계산 (외삽 포함)"""
        if not curve:
            return {str(p): None for p in prob_levels}

        xs    = [d[xkey] for d in curve]
        probs = [d["probability"] for d in curve]
        result = {}

        for target_prob in prob_levels:
            # 커브 안에 있으면 직접 찾기
            exact = None
            for d in curve:
                if abs(d["probability"] - target_prob) < 0.02:
                    exact = d[xkey]
                    break

            if exact is not None:
                result[str(target_prob)] = round(exact, -4) if xkey != 'years' else int(exact)
                continue

            # 로지스틱 피팅으로 외삽
            fitted = self._logistic_fit(xs, probs, target_prob)
            if fitted is not None:
                val = round(max(0.0, fitted), -4) if xkey != 'years' else max(1, min(50, round(fitted)))
                result[str(target_prob)] = val
            else:
                result[str(target_prob)] = None

        return result

    def solve(self, target_monthly_div, probability=0.90, seed=None, monthly=None, years=None) -> dict:
        none_count = sum(v is None for v in [seed, monthly, years])

        if none_count == 0:
            return {"mode": "probability",
                    "result": self.get_probability(seed, monthly, years, target_monthly_div)}
        elif none_count == 1:
            prob_levels = [0.50, 0.75, 0.90, 0.95]
            if years is None:
                anchor = self._find_anchor_years(seed, monthly, target_monthly_div, probability)
                curve  = self._years_curve_points(seed, monthly, target_monthly_div, probability)
                multi  = self._multi_anchors_from_curve(curve, 'years', prob_levels)
                return {"mode": "solve_years", "result": anchor, "curve": curve, "multi_anchors": multi}
            elif seed is None:
                anchor = self._find_anchor_seed(monthly, years, target_monthly_div, probability)
                curve  = self._seed_curve_points(monthly, years, target_monthly_div, probability)
                multi  = self._multi_anchors_from_curve(curve, 'seed', prob_levels)
                return {"mode": "solve_seed", "result": anchor, "curve": curve, "multi_anchors": multi}
            else:
                anchor = self._find_anchor_monthly(seed, years, target_monthly_div, probability)
                curve  = self._monthly_curve_points(seed, years, target_monthly_div, probability)
                multi  = self._multi_anchors_from_curve(curve, 'monthly', prob_levels)
                return {"mode": "solve_monthly", "result": anchor, "curve": curve, "multi_anchors": multi}
        elif none_count == 2:
            if seed is not None:
                return {"mode": "isocurve_monthly_years",
                        "isocurve": self._isocurve_monthly_years(seed, target_monthly_div, probability)}
            elif monthly is not None:
                return {"mode": "isocurve_seed_years",
                        "isocurve": self._isocurve_seed_years(monthly, target_monthly_div, probability)}
            else:
                return {"mode": "isocurve_seed_monthly",
                        "isocurve": self._isocurve_seed_monthly(years, target_monthly_div, probability)}
        else:
            raise ValueError("최소 1개 변수는 고정해야 합니다.")

    # ── 등위곡선 ────────────────────────────────────────

    def _isocurve_seed_monthly(self, years, target_monthly_div, probability):
        points = []
        for s in [0, 10000000, 20000000, 50000000, 100000000, 200000000, 500000000]:
            anchor = self._find_anchor_monthly(s, years, target_monthly_div, probability)
            if anchor is not None:
                points.append({"seed": s, "monthly": int(anchor)})
        return points

    def _isocurve_seed_years(self, monthly, target_monthly_div, probability):
        points = []
        for s in [0, 10000000, 20000000, 50000000, 100000000, 200000000, 500000000]:
            anchor = self._find_anchor_years(s, monthly, target_monthly_div, probability)
            if anchor is not None:
                points.append({"seed": s, "years": anchor})
        return points

    def _isocurve_monthly_years(self, seed, target_monthly_div, probability):
        points = []
        for m in [0, 100000, 300000, 500000, 700000, 1000000, 1500000, 2000000, 3000000]:
            anchor = self._find_anchor_years(seed, m, target_monthly_div, probability)
            if anchor is not None:
                points.append({"monthly": m, "years": anchor})
        return points


    # ──────────────────────────────────────────────────
    # 시나리오 기반 다중 계산
    # ──────────────────────────────────────────────────

    def _run_optimize_scenario(
        self, target_monthly_div, probability,
        seeds, monthlys, yearss,
        vary_seed, vary_monthly, vary_years,
        opt_seed, opt_monthly, opt_years,
        seed_cfg, monthly_cfg, years_cfg,
    ) -> dict:
        """최적화 모드: 탐색 변수 각 값에 대해 최적화 변수 역산 → 등위선"""

        # 탐색 변수 결정 (x축)
        if vary_seed:
            x_vals, x_key = seeds, 'seed'
            fixed_monthly = monthlys[0]
            fixed_years   = yearss[0]
        elif vary_monthly:
            x_vals, x_key = monthlys, 'monthly'
            fixed_seed    = seeds[0]
            fixed_years   = yearss[0]
        elif vary_years:
            x_vals, x_key = yearss, 'years'
            fixed_seed    = seeds[0]
            fixed_monthly = monthlys[0]
        else:
            # 탐색 없이 최적화만 → 단일값 반환
            if opt_seed:
                v = self._find_anchor_seed(monthlys[0], yearss[0], target_monthly_div, probability)
                return {"mode": "probability", "result": {"solved_seed": v, "probability": probability}}
            elif opt_monthly:
                v = self._find_anchor_monthly(seeds[0], yearss[0], target_monthly_div, probability)
                return {"mode": "probability", "result": {"solved_monthly": v, "probability": probability}}
            else:
                v = self._find_anchor_years(seeds[0], monthlys[0], target_monthly_div, probability)
                return {"mode": "probability", "result": {"solved_years": v, "probability": probability}}

        # 탐색 변수 x_vals 각각에 대해 최적화 변수 역산
        points = []
        for xv in x_vals:
            if x_key == 'seed':
                s, m, y = xv, fixed_monthly, fixed_years
            elif x_key == 'monthly':
                s, m, y = fixed_seed, xv, fixed_years
            else:
                s, m, y = fixed_seed, fixed_monthly, xv

            if opt_seed:
                opt_val = self._find_anchor_seed(m, y, target_monthly_div, probability)
                if opt_val is not None:
                    points.append({x_key: xv, 'seed': opt_val})
            elif opt_monthly:
                opt_val = self._find_anchor_monthly(s, y, target_monthly_div, probability)
                if opt_val is not None:
                    points.append({x_key: xv, 'monthly': opt_val})
            else:
                opt_val = self._find_anchor_years(s, m, target_monthly_div, probability)
                if opt_val is not None:
                    points.append({x_key: xv, 'years': opt_val})

        opt_key = 'seed' if opt_seed else 'monthly' if opt_monthly else 'years'
        x_label   = '초기 투자금' if x_key   == 'seed' else '월 적립금' if x_key   == 'monthly' else '투자 기간'
        opt_label = '초기 투자금' if opt_key  == 'seed' else '월 적립금' if opt_key  == 'monthly' else '투자 기간'

        return {
            "mode":      "isocurve",
            "x_key":     x_key,
            "opt_key":   opt_key,
            "x_label":   x_label,
            "opt_label": opt_label,
            "points":    points,
        }

    @staticmethod
    def _expand_var(center, step, n, min_val=0):
        """중심값 기준 ±n 스텝 확장, min_val 미만 제거"""
        if n == 0 or step == 0:
            return [center]
        vals = [center + step * i for i in range(-n, n + 1)]
        return [v for v in vals if v >= min_val]

    def run_scenario(
        self,
        target_monthly_div: float,
        probability:        float,
        seed_cfg:           dict,
        monthly_cfg:        dict,
        years_cfg:          dict,
    ) -> dict:
        seed_mode    = seed_cfg.get('mode', 'fixed')
        monthly_mode = monthly_cfg.get('mode', 'fixed')
        years_mode   = years_cfg.get('mode', 'fixed')

        seeds    = self._expand_var(seed_cfg['center'],    seed_cfg['step'],    seed_cfg['n'],    min_val=0)
        monthlys = self._expand_var(monthly_cfg['center'], monthly_cfg['step'], monthly_cfg['n'], min_val=0)
        yearss   = self._expand_var(years_cfg['center'],   years_cfg['step'],   years_cfg['n'],   min_val=1)

        vary_seed    = seed_mode    == 'explore' and seed_cfg['n']    > 0 and seed_cfg['step']    > 0
        vary_monthly = monthly_mode == 'explore' and monthly_cfg['n'] > 0 and monthly_cfg['step'] > 0
        vary_years   = years_mode   == 'explore' and years_cfg['n']   > 0 and years_cfg['step']   > 0

        opt_seed    = seed_mode    == 'optimize'
        opt_monthly = monthly_mode == 'optimize'
        opt_years   = years_mode   == 'optimize'

        vary_count = sum([vary_seed, vary_monthly, vary_years])
        opt_count  = sum([opt_seed, opt_monthly, opt_years])

        if vary_count > 2:
            return {"error": "탐색 변수는 최대 2개입니다."}
        if opt_count > 1:
            return {"error": "최적화 변수는 최대 1개입니다."}

        # 최적화 모드: 탐색 변수의 각 값에 대해 최적화 변수 역산
        if opt_count == 1:
            return self._run_optimize_scenario(
                target_monthly_div, probability,
                seeds, monthlys, yearss,
                vary_seed, vary_monthly, vary_years,
                opt_seed, opt_monthly, opt_years,
                seed_cfg, monthly_cfg, years_cfg,
            )

        if vary_count == 3:
            return {"error": "탐색이 있는 변수는 최대 2개입니다."}

        if vary_count == 0:
            # 모두 고정 → 달성 확률만 반환
            result = self.get_probability(seeds[0], monthlys[0], yearss[0], target_monthly_div)
            return {"mode": "probability", "result": result}

        if vary_count == 1:
            # X축 변수 1개 → 달성확률 곡선 (선 1개)
            if vary_seed:
                x_vals = seeds
                x_key  = "seed"
                fixed  = {"monthly": monthlys[0], "years": yearss[0]}
            elif vary_monthly:
                x_vals = monthlys
                x_key  = "monthly"
                fixed  = {"seed": seeds[0], "years": yearss[0]}
            else:
                x_vals = yearss
                x_key  = "years"
                fixed  = {"seed": seeds[0], "monthly": monthlys[0]}

            points = []
            for v in x_vals:
                s = v if x_key == "seed"    else fixed["seed"]
                m = v if x_key == "monthly" else fixed["monthly"]
                y = v if x_key == "years"   else fixed["years"]
                divs = self._run_rolling(s, m, y)
                prob = self._calc_prob(divs, target_monthly_div)
                points.append({x_key: v, "probability": round(prob, 4)})

            return {"mode": "scenario_1var", "x_key": x_key, "lines": [
                {"label": None, "points": points}
            ]}

        # vary_count == 2
        # 더 많은 포인트를 가진 변수가 X축, 적은 쪽이 여러 선
        if vary_seed and vary_monthly:
            if len(seeds) >= len(monthlys):
                x_vals, x_key = seeds, "seed"
                line_vals, line_key = monthlys, "monthly"
                fixed_val, fixed_key = yearss[0], "years"
            else:
                x_vals, x_key = monthlys, "monthly"
                line_vals, line_key = seeds, "seed"
                fixed_val, fixed_key = yearss[0], "years"
        elif vary_seed and vary_years:
            if len(seeds) >= len(yearss):
                x_vals, x_key = seeds, "seed"
                line_vals, line_key = yearss, "years"
                fixed_val, fixed_key = monthlys[0], "monthly"
            else:
                x_vals, x_key = yearss, "years"
                line_vals, line_key = seeds, "seed"
                fixed_val, fixed_key = monthlys[0], "monthly"
        else:  # vary_monthly and vary_years
            if len(monthlys) >= len(yearss):
                x_vals, x_key = monthlys, "monthly"
                line_vals, line_key = yearss, "years"
                fixed_val, fixed_key = seeds[0], "seed"
            else:
                x_vals, x_key = yearss, "years"
                line_vals, line_key = monthlys, "monthly"
                fixed_val, fixed_key = seeds[0], "seed"

        lines = []
        for lv in line_vals:
            points = []
            for xv in x_vals:
                if x_key == "seed":
                    s, m, y = xv, (lv if line_key == "monthly" else fixed_val), (lv if line_key == "years" else fixed_val)
                elif x_key == "monthly":
                    s, m, y = (lv if line_key == "seed" else fixed_val), xv, (lv if line_key == "years" else fixed_val)
                else:  # x_key == "years"
                    s, m, y = (lv if line_key == "seed" else fixed_val), (lv if line_key == "monthly" else fixed_val), xv

                divs = self._run_rolling(s, m, y)
                prob = self._calc_prob(divs, target_monthly_div)
                points.append({x_key: xv, "probability": round(prob, 4)})

            label = f"{line_key}={lv // 10000}만" if line_key in ("seed", "monthly") else f"{line_key}={lv}년"
            lines.append({"label": label, line_key: lv, "points": points})

        return {
            "mode":      "scenario_2var",
            "x_key":     x_key,
            "line_key":  line_key,
            "fixed_key": fixed_key,
            "fixed_val": fixed_val,
            "lines":     lines,
        }