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

    def _run_rolling(self, seed, monthly, years) -> List[float]:
        cache_key = f"{round(seed,-4)}_{round(monthly,-4)}_{years}"
        if cache_key in self._sim_cache:
            return self._sim_cache[cache_key]
        actual_start = self._get_actual_start()
        if actual_start is None:
            return []
        actual_start_dt = pd.Timestamp(actual_start)
        sim_end_latest  = pd.Timestamp.today() - pd.DateOffset(years=years)
        if actual_start_dt > sim_end_latest:
            return []
        roll_starts = pd.date_range(actual_start_dt, sim_end_latest, freq=f"{self.step_months}ME")
        results = []
        for start in roll_starts:
            val = self._simulate_one(seed, monthly, years, start.strftime("%Y-%m-%d"))
            if val > 0:
                results.append(val)
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
        seed_cfg:           dict,   # {center, step, n}
        monthly_cfg:        dict,
        years_cfg:          dict,
    ) -> dict:
        """
        시나리오 기반 계산

        n=0인 변수: 고정값
        n>0인 변수: 여러 값 생성
        n>0인 변수가 1개: X축 → 달성확률 곡선 (선 1개)
        n>0인 변수가 2개: X축 + 여러 선
        n>0인 변수가 3개: 에러
        """
        seeds    = self._expand_var(seed_cfg['center'],    seed_cfg['step'],    seed_cfg['n'],    min_val=0)
        monthlys = self._expand_var(monthly_cfg['center'], monthly_cfg['step'], monthly_cfg['n'], min_val=0)
        yearss   = self._expand_var(years_cfg['center'],   years_cfg['step'],   years_cfg['n'],   min_val=1)

        vary_seed    = seed_cfg['n']    > 0 and seed_cfg['step']    > 0
        vary_monthly = monthly_cfg['n'] > 0 and monthly_cfg['step'] > 0
        vary_years   = years_cfg['n']   > 0 and years_cfg['step']   > 0

        vary_count = sum([vary_seed, vary_monthly, vary_years])

        if vary_count == 3:
            return {"error": "스텝이 있는 변수는 최대 2개입니다."}

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