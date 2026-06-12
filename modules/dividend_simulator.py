"""
dividend_simulator.py
배당금 목표 역산 전용 경량 시뮬레이터
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional, List, Dict

from modules.sim.fee_engine import FeeEngine


def _finite_float(value, default=0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(default)
    return v if np.isfinite(v) else float(default)


def _looks_like_krx_code(ticker: str) -> bool:
    code = str(ticker).split(".")[0].upper()
    return bool(code) and len(code) == 6 and code[0].isdigit() and code.isalnum()


def fmtKRW_py(v):
    if v >= 100000000: return f'{v/100000000:.1f}억'
    if v >= 10000:     return f'{round(v/10000)}만'
    return f'{round(v):,}'


class DividendSimulator:

    TICKER_REGION_MAP = {
        "GOLD": "GOLD", "KRX_GOLD": "GOLD",
        "BTC": "CRYPTO", "ETH": "CRYPTO",
    }

    def _get_region(self, ticker: str) -> str:
        if ticker in self.TICKER_REGION_MAP:
            return self.TICKER_REGION_MAP[ticker]
        if _looks_like_krx_code(ticker):
            return "KR"
        if any("\uAC00" <= c <= "\uD7A3" for c in ticker):
            return "KR"
        return "US"

    def __init__(
        self,
        loader,
        tickers,
        weights,
        div_mode:     str   = "reinvest",
        step_months:  int   = 3,
        rebal_mode:   str   = "none",
        band_width:   float = 0.05,
        tax_engine=None,
        fee_engine:   Optional[FeeEngine] = None,
        account_type: str   = "위탁",
        isa_total_limit: Optional[float] = None,
    ):
        self.loader      = loader
        active_tickers = [
            ticker for ticker in tickers
            if float(weights.get(ticker, 0) or 0) > 0
        ]
        self.tickers     = active_tickers or list(tickers)
        self.weights     = {
            ticker: float(weights.get(ticker, 0) or 0)
            for ticker in self.tickers
        }
        self.div_mode    = div_mode
        self.step_months = step_months
        self.rebal_mode  = rebal_mode
        self.band_width  = band_width
        self.tax_engine   = tax_engine
        self.fee_engine   = fee_engine
        self._account_type = account_type
        self._isa_total_limit = isa_total_limit
        self._price_cache: Dict[str, pd.DataFrame] = {}
        self._sim_cache:   Dict[str, List[float]]   = {}

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
        """1윈도우 시뮬 — 메인 엔진(SimulationLoop) 월별 모드로 실행 (divrefactoring 3-5).

        기존 자체 월별 루프를 제거하고 투자계산기·백테스트와 같은 파이프라인을 공유한다.
        월별 모드 = 월말 리샘플 데이터 주입(루프 무변경, `monthly_mode.to_monthly_price_data`).
        반환은 동일하게 "마지막 1년 순배당 합계"(`last_year_dividend`, 경계 = start+years − 1년).

        구엔진 대비 의도된 차이(게이트 벤치 2026-06-13, 중앙 ~1%·최대 ~3.3%):
        - 월내 순서가 배당→적립(구: 적립→배당) — 그 달 적립분은 그 달 배당 미수령(ex-date 정합).
        - 리밸런싱이 TaxedOrderExecutor 경유 → 위탁 양도세 실제 부과(구: 수량 조정만, 무세금).
        - 비중합<100% 잔여는 CashAllocator가 전액 투자(구: 미투자 방치). UI는 합 100 강제.
        ※ self.fee_engine은 프로덕션 미사용(항상 None) — 신 경로 미반영.
        """
        from modules.config.simulation_config import SimulationConfig
        from modules.core.portfolio import Portfolio, TaxTrackedPortfolio
        from modules.execution.order_executor import OrderExecutor, TaxedOrderExecutor
        from modules.execution.cash_allocator import CashAllocator
        from modules.simulation.dividend_engine import DividendEngine
        from modules.simulation.contribution_engine import ContributionEngine
        from modules.simulation.withdrawal_engine import WithdrawalEngine
        from modules.simulation.history_recorder import HistoryRecorder
        from modules.simulation.simulation_loop import SimulationLoop
        from modules.simulation.monthly_mode import to_monthly_price_data, last_year_dividend
        from modules.rebalance.periodic import PeriodicRebalance

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

        m_data, m_dates = to_monthly_price_data(data)
        # 종목별 시작 시차 → 전 종목 유효한 첫 월부터 (leading NaN 가격 오염 방지)
        valid_froms = [df["close"].first_valid_index() for df in m_data.values()]
        if any(v is None for v in valid_froms):
            return 0.0
        valid_from = max(valid_froms)
        m_dates = [d for d in m_dates if d >= valid_from]
        if not m_dates:
            return 0.0
        m_data = {t: df.loc[m_dates[0]:] for t, df in m_data.items()}

        # ISA 총한도 → 납입 중단 개월 (구엔진 _contrib_end와 동일 공식)
        contrib_end = None
        if self._isa_total_limit and monthly > 0:
            remaining = max(0.0, self._isa_total_limit - seed)
            contrib_end = int(remaining / monthly)

        cfg = SimulationConfig(
            start_date=str(m_dates[0].date()), end_date=str(end.date()),
            tickers=list(self.tickers), target_weights=dict(self.weights),
            initial_capital=float(seed), monthly_contribution=float(monthly),
            contribution_end_months=contrib_end,
            withdrawal_amount=0, dividend_mode=self.div_mode,
            rebalance_frequency=(
                None if self.rebal_mode in ("none", "band") else self.rebal_mode
            ),
            inflation=0.0,
        )

        strategy = PeriodicRebalance(
            dict(self.weights),
            rebalance_frequency=cfg.rebalance_frequency,
            drift_threshold=self.band_width if self.rebal_mode == "band" else None,
        )

        if self.tax_engine is not None:
            from modules.tax.account_tax import TaxedDividendEngine
            from modules.tax.session import TaxSessionState
            session = TaxSessionState(other_financial_income=0.0)  # 윈도우별 독립 연도 풀
            portfolio  = TaxTrackedPortfolio(float(seed))
            div_engine = TaxedDividendEngine(DividendEngine(), self.tax_engine,
                                             self._account_type, session=session)
            executor   = TaxedOrderExecutor(self.tax_engine, self._account_type,
                                            session=session)
        else:
            portfolio  = Portfolio(float(seed))
            div_engine = DividendEngine()
            executor   = OrderExecutor()

        loop = SimulationLoop(div_engine, ContributionEngine(), WithdrawalEngine(),
                              executor, CashAllocator())
        recorder = HistoryRecorder()
        loop.run(portfolio, strategy, cfg, m_data, m_dates, recorder)
        return last_year_dividend(recorder.to_dataframe(), end)

    MIN_CASES = 30  # 롤링 케이스 최소 보장 개수

    def _calc_div_stats(self) -> dict:
        """
        실제 배당 데이터에서 배당률/성장률/연평균수익률 분포 계산
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
            current_year = pd.Timestamp.today().year
            annual = div_df.groupby("year")["dividend"].sum()
            annual = annual.iloc[1:]
            if len(annual) > 0 and annual.index[-1] == current_year:
                annual = annual.iloc[:-1]
            growth = annual.pct_change().dropna()
            growth = growth[growth.abs() < 2.0]

            # 연평균 주가 수익률 계산 (배당 제외, 순수 가격 상승, 미완료 연도 제외)
            annual_prices = df["close"].resample("YE").last().dropna()
            annual_prices = annual_prices[annual_prices.index.year < current_year]
            if len(annual_prices) > 2:
                price_returns = annual_prices.pct_change().dropna()
                # 극단값 제거
                price_returns = price_returns[price_returns.abs() < 1.0]
                mean_price_return = float(price_returns.mean())
            else:
                mean_price_return = 0.07  # fallback: 연 7%

            # 최근 3년 데이터로 div_freq/div_yield 계산 (백필 오염 레코드 제거)
            # 완성된 연도 우선 사용 → 현재 연도 부분 데이터로 인한 통계 왜곡 방지
            complete_div = div_df[div_df.index.year < current_year]
            freq_base = complete_div if len(complete_div) >= 4 else div_df
            recent_cutoff = freq_base.index.max() - pd.DateOffset(years=3)
            freq_df = freq_base[freq_base.index >= recent_cutoff]
            if len(freq_df) >= 4:
                freq_years = max(0.25, (freq_df.index[-1] - freq_df.index[0]).days / 365)
                div_freq   = int(round(len(freq_df) / freq_years))
                yield_mean = float(freq_df["div_yield"].mean())
                yield_std  = float(freq_df["div_yield"].std())
            else:
                freq_years = max(1, (div_df.index[-1] - div_df.index[0]).days / 365)
                div_freq   = int(round(len(div_df) / freq_years))
                yield_mean = float(div_df["div_yield"].mean())
                yield_std  = float(div_df["div_yield"].std())

            stats[t] = {
                "div_yield_mean":    yield_mean,
                "div_yield_std":     yield_std,
                "growth_mean":       float(growth.mean()) if len(growth) > 0 else 0.10,
                "growth_std":        float(growth.std())  if len(growth) > 0 else 0.07,
                "div_freq":          div_freq,
                "price_return_mean": mean_price_return,
            }
        for t, s in stats.items():
            div_freq = max(0, int(round(_finite_float(s.get("div_freq"), 0))))
            event_mean = _finite_float(s.get("div_yield_mean"), 0.0)
            event_std = _finite_float(s.get("div_yield_std"), 0.0)
            s["div_yield_mean"] = event_mean
            s["div_yield_std"] = event_std
            s["annual_yield_mean"] = _finite_float(event_mean * div_freq, 0.0)
            s["annual_yield_std"] = _finite_float(event_std * (div_freq ** 0.5), 0.0)
            s["growth_mean"] = _finite_float(s.get("growth_mean"), 0.10)
            s["growth_std"] = _finite_float(s.get("growth_std"), 0.07)
            s["div_freq"] = div_freq
            s["div_obs"] = int(_finite_float(s.get("div_obs"), div_freq))
            s["price_return_mean"] = _finite_float(s.get("price_return_mean"), 0.07)
            s["reliable"] = s["div_obs"] >= 4

        for t in self.tickers:
            if t in stats:
                continue
            df = self._load(t)
            if df.empty:
                continue
            current_year = pd.Timestamp.today().year
            annual_prices = df["close"].resample("YE").last().dropna()
            annual_prices = annual_prices[annual_prices.index.year < current_year]
            if len(annual_prices) > 2:
                price_returns = annual_prices.pct_change().dropna()
                price_returns = price_returns[price_returns.abs() < 1.0]
                price_return_mean = _finite_float(price_returns.mean(), 0.07)
            else:
                price_return_mean = 0.07
            stats[t] = {
                "div_yield_mean": 0.0,
                "div_yield_std": 0.0,
                "annual_yield_mean": 0.0,
                "annual_yield_std": 0.0,
                "growth_mean": 0.0,
                "growth_std": 0.0,
                "div_freq": 0,
                "div_obs": 0,
                "price_return_mean": price_return_mean,
                "reliable": False,
            }

        return stats

    def _simulate_synthetic(self, seed, monthly, years, div_stats, rng) -> float:
        """
        가상 데이터 기반 시뮬 (자산가치 기반)
        배당률 고정 + 연평균 주가 상승률 반영
        """
        price_return_mean  = sum(div_stats[t]["price_return_mean"]  * self.weights[t] for t in self.tickers if t in div_stats)

        n_quarters = years * 4

        # 배당률 고정 샘플링
        # Synthetic cases use portfolio annual yield and distribute it monthly.
        annual_yield_mean = sum(
            _finite_float(div_stats[t].get("annual_yield_mean"), 0.0) * self.weights[t]
            for t in self.tickers if t in div_stats
        )
        annual_yield_std = sum(
            (_finite_float(div_stats[t].get("annual_yield_std"), 0.0) * self.weights[t]) ** 2
            for t in self.tickers if t in div_stats
        ) ** 0.5
        sampled_annual_yield = rng.normal(annual_yield_mean, annual_yield_std * 0.3)
        annual_div_yield = max(0.0, _finite_float(sampled_annual_yield, annual_yield_mean))
        div_yield = annual_div_yield / 12.0
        div_freq = 12

        # 월간 주가 상승률
        monthly_price_return = (1 + price_return_mean) ** (1 / 12) - 1

        asset = float(seed)
        last_year_start_q = max(0, n_quarters - 4)
        last_year_div = 0.0
        # 합성 시뮬은 실제 날짜 없음 -> yr(0,1,2...) 인덱스로 연간 ytd 추적
        synthetic_ytd: Dict[int, float] = {}
        rep_ticker = self.tickers[0] if self.tickers else "SPY"

        _syn_contrib_end = None
        if self._isa_total_limit and monthly > 0:
            _remaining = max(0.0, self._isa_total_limit - seed)
            _syn_contrib_end = int(_remaining / monthly)

        for m in range(years * 12):
            # 주가 상승 반영 (자산가치 증가)
            asset *= (1 + monthly_price_return)
            _eff_monthly = monthly if (_syn_contrib_end is None or m < _syn_contrib_end) else 0.0
            asset += _eff_monthly
            q = m // 3
            yr = q // 4

            if div_freq >= 12:
                gross = asset * div_yield
                if gross > 0:
                    if self.tax_engine:
                        ytd = synthetic_ytd.get(yr, 0.0)
                        div = self.tax_engine.after_tax_dividend(
                            gross, rep_ticker, self._account_type, ytd
                        )
                        synthetic_ytd[yr] = ytd + gross
                    else:
                        div = gross
                    if q >= last_year_start_q:
                        last_year_div += div
                    if self.div_mode == "reinvest":
                        asset += div
            else:
                pay_interval = max(1, round(12 / div_freq))
                if m % pay_interval == pay_interval - 1:
                    gross = asset * div_yield
                    if gross > 0:
                        if self.tax_engine:
                            ytd = synthetic_ytd.get(yr, 0.0)
                            div = self.tax_engine.after_tax_dividend(
                                gross, rep_ticker, self._account_type, ytd
                            )
                            synthetic_ytd[yr] = ytd + gross
                        else:
                            div = gross
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

    def _find_real_data_start(self) -> pd.Timestamp:
        """실측 데이터(volume>0) 시작일 = 백필(volume=0)/실데이터 경계.
        provenance 기반 결정값(배당간격 휴리스틱 아님). 다종목이면 가장 늦은
        실데이터 시작(모든 종목이 실측인 시점)을 반환한다.
        """
        conn = getattr(self.loader, "conn", None)
        candidates = []
        for t in self.tickers:
            ts = None
            if conn is not None:
                try:
                    row = conn.execute(
                        "SELECT MIN(date) FROM price_daily WHERE code=? AND volume>0", (t,)
                    ).fetchone()
                    if row and row[0]:
                        ts = pd.Timestamp(row[0])
                except Exception:
                    ts = None
            if ts is None:
                df = self._load(t)
                if not df.empty:
                    ts = df.index.min()
            if ts is not None:
                candidates.append(ts)
        return max(candidates) if candidates else pd.Timestamp("1900-01-01")

    def _roll_window(self, seed, monthly, years, start_dt, end_dt) -> List[float]:
        """[start_dt, end_dt]를 step_months 간격으로 롤링해 케이스 생성."""
        results = []
        if start_dt <= end_dt:
            roll_starts = pd.date_range(start_dt, end_dt, freq=f"{self.step_months}ME")
            for start in roll_starts:
                val = self._simulate_one(seed, monthly, years, start.strftime("%Y-%m-%d"))
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

        actual_start_dt  = pd.Timestamp(actual_start)
        real_data_start  = self._find_real_data_start()
        sim_end_latest   = pd.Timestamp.today() - pd.DateOffset(years=years)

        # 3단 폴백: 실측을 버리지 않고, 부족분만 가상으로 보충한다.
        # 1단 — 실데이터(volume>0) 구간만 롤링. 실측 역사가 충분하면 그대로 사용.
        real_start = max(actual_start_dt, real_data_start)
        real_only  = self._roll_window(seed, monthly, years, real_start, sim_end_latest)
        if len(real_only) >= self.MIN_CASES:
            results = real_only
        else:
            # 2단 — 백필 포함 전구간 롤링. 실측+백필 경로를 최대한 사용.
            full = self._roll_window(seed, monthly, years, actual_start_dt, sim_end_latest)
            if len(full) >= self.MIN_CASES:
                results = full
            else:
                # 3단 — 부족분만 가상으로 보충 (실측/백필 케이스는 유지).
                # [SYNTHETIC_PATH: In-Memory] DB 기록 없음. ScenarioDataPreparer 경유 불필요.
                need    = self.MIN_CASES - len(full)
                results = full + self._run_synthetic_rolling(seed, monthly, years, need)
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

    def _find_anchor_years(self, seed, monthly, target_monthly_div, probability, cancel_check=None):
        checkpoints = [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]
        lo_y, lo_p = 1, 0.0
        for y in checkpoints:
            if cancel_check: cancel_check()
            p = self._calc_prob(self._run_rolling(seed, monthly, y), target_monthly_div)
            if p >= probability:
                hi_y = y
                # lo~hi 사이를 1년 단위로 스윕 (early stop)
                for yy in range(lo_y, hi_y + 1):
                    if cancel_check: cancel_check()
                    pp = self._calc_prob(self._run_rolling(seed, monthly, yy), target_monthly_div)
                    if pp >= probability:
                        return float(yy)
                return float(hi_y)
            lo_y, lo_p = y, p
        return None

    def _bisect_anchor(self, lo, hi, fn_prob, probability, cancel_check, n=3):
        """bracket [lo, hi] 안에서 이분탐색으로 threshold 정밀 추정."""
        for _ in range(n):
            if cancel_check: cancel_check()
            mid = (lo + hi) / 2
            if fn_prob(mid) >= probability:
                hi = mid
            else:
                lo = mid
        return hi

    def _narrow_anchor_bracket(self, lo, hi, step, fn_prob, probability, cancel_check, max_steps=8):
        if step <= 0 or hi - lo <= step * 2:
            return lo, hi

        probe = lo + step
        while probe < hi and max_steps > 0:
            if cancel_check:
                cancel_check()
            if fn_prob(probe) >= probability:
                return probe - step, probe
            lo = probe
            probe += step
            max_steps -= 1
        return lo, hi

    def _find_anchor_seed(self, monthly, years, target_monthly_div, probability, cancel_check=None):
        def _cc(): cancel_check() if cancel_check else None
        step = target_monthly_div * 10
        xs, probs = [], []
        # 1단계: 고정 스텝 8번 스윕
        for i in range(8):
            _cc()
            s = step * i
            p = self._calc_prob(self._run_rolling(s, monthly, years), target_monthly_div)
            xs.append(s)
            probs.append(p)
            if p >= probability:
                if i == 0:
                    return 0.0
                lo = step * (i - 1)
                result = self._bisect_anchor(
                    lo, s,
                    lambda v: self._calc_prob(self._run_rolling(v, monthly, years), target_monthly_div),
                    probability, cancel_check,
                )
                return round(result, -4)
        # 2단계: 지수 탐색으로 bracket 찾기 → 이분탐색으로 정밀화
        s = step * 8
        for _ in range(10):
            _cc()
            p = self._calc_prob(self._run_rolling(s, monthly, years), target_monthly_div)
            xs.append(s)
            probs.append(p)
            if p >= probability:
                lo = s / 2
                lo, s = self._narrow_anchor_bracket(
                    lo, s, step,
                    lambda v: self._calc_prob(self._run_rolling(v, monthly, years), target_monthly_div),
                    probability, cancel_check,
                )
                result = self._bisect_anchor(
                    lo, s,
                    lambda v: self._calc_prob(self._run_rolling(v, monthly, years), target_monthly_div),
                    probability, cancel_check,
                )
                return round(result, -4)
            s *= 2
        return None

    def _find_anchor_monthly(self, seed, years, target_monthly_div, probability, cancel_check=None):
        def _cc(): cancel_check() if cancel_check else None
        step = target_monthly_div * 0.5
        xs, probs = [], []
        # 1단계: 고정 스텝 8번 스윕
        for i in range(8):
            _cc()
            m = step * i
            p = self._calc_prob(self._run_rolling(seed, m, years), target_monthly_div)
            xs.append(m)
            probs.append(p)
            if p >= probability:
                if i == 0:
                    return 0.0
                lo = step * (i - 1)
                result = self._bisect_anchor(
                    lo, m,
                    lambda v: self._calc_prob(self._run_rolling(seed, v, years), target_monthly_div),
                    probability, cancel_check,
                )
                return round(result, -4)
        # 2단계: 지수 탐색으로 bracket 찾기 → 이분탐색으로 정밀화
        m = step * 8
        for _ in range(10):
            _cc()
            p = self._calc_prob(self._run_rolling(seed, m, years), target_monthly_div)
            xs.append(m)
            probs.append(p)
            if p >= probability:
                lo = m / 2
                lo, m = self._narrow_anchor_bracket(
                    lo, m, step,
                    lambda v: self._calc_prob(self._run_rolling(seed, v, years), target_monthly_div),
                    probability, cancel_check,
                )
                result = self._bisect_anchor(
                    lo, m,
                    lambda v: self._calc_prob(self._run_rolling(seed, v, years), target_monthly_div),
                    probability, cancel_check,
                )
                return round(result, -4)
            m *= 2
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
        progress_callback=None,
        cancel_check=None,
    ) -> dict:
        """최적화 모드: 탐색 변수 각 값에 대해 최적화 변수 역산 → 등위선"""

        vary_count = sum([vary_seed, vary_monthly, vary_years])

        # 탐색 없이 최적화만 → 단일값 반환
        if vary_count == 0:
            if opt_seed:
                v = self._find_anchor_seed(monthly_cfg['center'], years_cfg['center'], target_monthly_div, probability, cancel_check=cancel_check)
                res = {"solved_seed": v, "probability": probability}
                if v is not None:
                    res["distribution"] = self.get_probability(v, monthly_cfg['center'], years_cfg['center'], target_monthly_div).get("distribution", {})
                return {"mode": "probability", "result": res}
            elif opt_monthly:
                v = self._find_anchor_monthly(seed_cfg['center'], years_cfg['center'], target_monthly_div, probability, cancel_check=cancel_check)
                res = {"solved_monthly": v, "probability": probability}
                if v is not None:
                    res["distribution"] = self.get_probability(seed_cfg['center'], v, years_cfg['center'], target_monthly_div).get("distribution", {})
                return {"mode": "probability", "result": res}
            else:
                v = self._find_anchor_years(seed_cfg['center'], monthly_cfg['center'], target_monthly_div, probability, cancel_check=cancel_check)
                res = {"solved_years": v, "probability": probability}
                if v is not None:
                    res["distribution"] = self.get_probability(seed_cfg['center'], monthly_cfg['center'], v, target_monthly_div).get("distribution", {})
                return {"mode": "probability", "result": res}

        # 탐색 1개 → X축 = 탐색 변수, Y축 = 최적화 변수 (등위선 1개)
        # 탐색 2개 → X축 = 더 많은 포인트 가진 변수, 나머지 탐색 변수는 여러 선
        opt_key   = 'seed' if opt_seed else 'monthly' if opt_monthly else 'years'
        opt_label = '초기 투자금' if opt_seed else '월 적립금' if opt_monthly else '투자 기간'

        if vary_count == 1:
            if vary_seed:
                x_vals, x_key, line_vals, line_key = seeds, 'seed', [None], None
                get_s = lambda xv, lv: xv
                get_m = lambda xv, lv: monthly_cfg['center']
                get_y = lambda xv, lv: years_cfg['center']
            elif vary_monthly:
                x_vals, x_key, line_vals, line_key = monthlys, 'monthly', [None], None
                get_s = lambda xv, lv: seed_cfg['center']
                get_m = lambda xv, lv: xv
                get_y = lambda xv, lv: years_cfg['center']
            else:
                x_vals, x_key, line_vals, line_key = yearss, 'years', [None], None
                get_s = lambda xv, lv: seed_cfg['center']
                get_m = lambda xv, lv: monthly_cfg['center']
                get_y = lambda xv, lv: xv

        else:  # vary_count == 2
            # 더 많은 포인트 → X축, 적은 포인트 → 여러 선
            vary_pairs = []
            if vary_seed:    vary_pairs.append(('seed',    seeds))
            if vary_monthly: vary_pairs.append(('monthly', monthlys))
            if vary_years:   vary_pairs.append(('years',   yearss))

            # 포인트 많은 쪽이 X축
            if len(vary_pairs[0][1]) >= len(vary_pairs[1][1]):
                x_key, x_vals     = vary_pairs[0]
                line_key, line_vals = vary_pairs[1]
            else:
                x_key, x_vals     = vary_pairs[1]
                line_key, line_vals = vary_pairs[0]

            def get_s(xv, lv):
                if x_key == 'seed':    return xv
                if line_key == 'seed': return lv
                return seed_cfg['center']
            def get_m(xv, lv):
                if x_key == 'monthly':    return xv
                if line_key == 'monthly': return lv
                return monthly_cfg['center']
            def get_y(xv, lv):
                if x_key == 'years':    return xv
                if line_key == 'years': return lv
                return years_cfg['center']

        x_label    = '초기 투자금' if x_key == 'seed' else '월 적립금' if x_key == 'monthly' else '투자 기간'
        line_label = ('초기 투자금' if line_key == 'seed' else '월 적립금' if line_key == 'monthly' else '투자 기간') if line_key else None
        line_label_of = lambda v: fmtKRW_py(v) if line_key != 'years' else f'{v}년'

        import time as _t
        _opt_start = _t.time()
        total_pts = len(line_vals) * len(x_vals)
        done = 0
        lines = []
        for lv in line_vals:
            points = []
            for xv in x_vals:
                s, m, y = get_s(xv, lv), get_m(xv, lv), get_y(xv, lv)
                if opt_seed:
                    opt_val = self._find_anchor_seed(m, y, target_monthly_div, probability, cancel_check=cancel_check)
                elif opt_monthly:
                    opt_val = self._find_anchor_monthly(s, y, target_monthly_div, probability, cancel_check=cancel_check)
                else:
                    opt_val = self._find_anchor_years(s, m, target_monthly_div, probability, cancel_check=cancel_check)
                if opt_val is not None:
                    points.append({x_key: xv, opt_key: opt_val})
                done += 1
                if progress_callback:
                    progress_callback(current=done, total=total_pts, elapsed=_t.time() - _opt_start)

            lbl = None if lv is None else (
                f'{line_label}={lv//10000}만' if line_key in ("seed","monthly") else f'{line_label}={lv}년'
            )
            lines.append({"label": lbl, line_key: lv, "points": points} if lv is not None
                         else {"label": None, "points": points})

        return {
            "mode":       "isocurve",
            "x_key":      x_key,
            "opt_key":    opt_key,
            "line_key":   line_key,
            "x_label":    x_label,
            "opt_label":  opt_label,
            "line_label": line_label,
            "lines":      lines,
        }

    @staticmethod
    def _expand_var(center, step, n, min_val=0):
        """중심값 기준 ±n 스텝 확장, min_val 미만 제거"""
        if n == 0 or step == 0:
            return [center]
        vals = [center + step * i for i in range(-n, n + 1)]
        return [v for v in vals if v >= min_val]

    def _preload_all(self, progress_callback=None):
        n = len(self.tickers)
        if progress_callback:
            progress_callback(current=0, total=max(n, 1), elapsed=0, phase='loading')
        for i, ticker in enumerate(self.tickers):
            self._load(ticker)
            if progress_callback:
                progress_callback(current=i + 1, total=n, elapsed=0, phase='loading')

    def run_scenario(
        self,
        target_monthly_div: float,
        probability:        float,
        seed_cfg:           dict,
        monthly_cfg:        dict,
        years_cfg:          dict,
        progress_callback=None,
        cancel_check=None,
    ) -> dict:
        import time as _t
        _scenario_start = _t.time()
        if progress_callback:
            self._preload_all(progress_callback)
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
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

        if vary_count == 3:
            return {"error": "탐색이 있는 변수는 최대 2개입니다."}

        if vary_count == 0:
            if progress_callback:
                progress_callback(current=1, total=1, elapsed=_t.time() - _scenario_start)
            result = self.get_probability(seed_cfg['center'], monthly_cfg['center'], years_cfg['center'], target_monthly_div)
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

            total_pts = len(x_vals)
            points = []
            for idx, v in enumerate(x_vals, 1):
                s = v if x_key == "seed"    else fixed["seed"]
                m = v if x_key == "monthly" else fixed["monthly"]
                y = v if x_key == "years"   else fixed["years"]
                divs = self._run_rolling(s, m, y)
                prob = self._calc_prob(divs, target_monthly_div)
                points.append({x_key: v, "probability": round(prob, 4)})
                if progress_callback:
                    elapsed = _t.time() - _scenario_start
                    progress_callback(current=idx, total=total_pts, elapsed=elapsed)

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

        total_combos = len(line_vals) * len(x_vals)
        combo_done   = 0
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
                combo_done += 1
                if progress_callback:
                    elapsed = _t.time() - _scenario_start
                    progress_callback(current=combo_done, total=total_combos, elapsed=elapsed)

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
