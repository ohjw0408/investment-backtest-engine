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
        tax_engine                          = None,
        account_type:         str           = "위탁",
        isa_renewal:          bool          = False,
        gain_harvesting:      bool          = False,
        progress_callback                   = None,
        use_synthetic:          bool        = False,
        synthetic_params:       dict        = None,
        contribution_end_months: Optional[int] = None,
        apply_final_liquidation: bool        = True,
        fee_rate:               float        = 0.0,
        stock_tickers                        = None,
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
        self.tax_engine            = tax_engine
        self.account_type          = account_type
        self.isa_renewal           = isa_renewal and account_type == "ISA"
        self.gain_harvesting       = gain_harvesting and account_type == "위탁"
        self.progress_callback     = progress_callback
        self.use_synthetic         = use_synthetic
        # code -> {mu_monthly, sigma_monthly, actual_start, anchor_price}
        self.synthetic_params      = synthetic_params or {}
        self.contribution_end_months = contribution_end_months
        # 투자계산기=True(끝에 일괄청산). 은퇴 적립=False(무청산 인계 → 인출단계서 과세).
        self.apply_final_liquidation = apply_final_liquidation
        # D4 거래수수료 — SimulationConfig에 실어 runner로 전달(0이면 무수수료).
        self.fee_rate              = float(fee_rate or 0.0)
        self.stock_tickers         = stock_tickers

    def _estimate_total_cases(self, start=None) -> int:
        cur = start if start is not None else self.data_start
        count = 0
        while True:
            end = cur + relativedelta(years=self.accumulation_years)
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
        if self.verbose:
            print(f"[AccumulationAnalyzer] {len(cases)}개 케이스 완료")
            print(f"  종료자산 중앙값: {distribution['end_value']['p50']:,.0f}")
            print(f"  CAGR 중앙값:    {distribution['cagr']['p50']:.2%}")

        result = {"cases": cases, "distribution": distribution}

        # ISA 풍차돌리기 + 3의 배수가 아닌 시뮬 기간 → 중도해지 가정 분포 추가
        if self.isa_renewal and self.accumulation_years % 3 != 0:
            early_vals = np.array([
                c.get("end_value_early_cancel", c["end_value"]) for c in cases
            ], dtype=float)
            result["distribution_early_cancel"] = {
                "p10": float(np.percentile(early_vals, 10)),
                "p25": float(np.percentile(early_vals, 25)),
                "p50": float(np.percentile(early_vals, 50)),
                "p75": float(np.percentile(early_vals, 75)),
                "p90": float(np.percentile(early_vals, 90)),
                "mean": float(np.mean(early_vals)),
                "values": early_vals.tolist(),
            }

        return result

    def _run_rolling(self) -> List[dict]:
        import time
        from modules.simulation.taxable_runner  import TaxableSimulationRunner
        from modules.config.simulation_config   import SimulationConfig

        runner      = TaxableSimulationRunner()

        # use_synthetic이고 외부 합성 params가 없으면(실데이터 충분하나 케이스 보충 원함) 윈도우별
        # 독립 합성 params를 만들어 롤링 시작점을 앞당겨 TARGET까지 보충한다. 기존 DataPreparer 합성
        # 흐름(params 이미 존재)·ISA 풍차돌리기는 건드리지 않는다.
        self._synth_supplement = False
        if self.use_synthetic and not self.synthetic_params and not self.isa_renewal:
            from modules.retirement.synthetic_price_generator import build_window_synth_params
            built = build_window_synth_params(self.portfolio_engine, self.tickers)
            if built:
                self.synthetic_params = built
                self._synth_supplement = True

        roll_start = self.data_start
        if self._synth_supplement:
            from modules.retirement.synthetic_price_generator import WINDOW_SYNTH_TARGET_CASES
            extended = (self.data_end - relativedelta(years=self.accumulation_years)
                        - relativedelta(months=WINDOW_SYNTH_TARGET_CASES * self.step_months))
            roll_start = min(self.data_start, extended)

        # P0-1: 윈도우마다 price_loader.load(DB read+reindex+ffill)를 재실행하던 것을
        # [roll_start, data_end] 1회 로드 후 윈도우 슬라이스로 대체(WithdrawalAnalyzer 모범 패턴).
        # 합성 보충(per-window synthetic) 경로는 제외 — 윈도우별 독립 생성이라 그대로 둔다.
        self._full_pd = None
        self._full_dates = None
        if not (self.use_synthetic and self.synthetic_params):
            try:
                self._full_pd, self._full_dates = self.portfolio_engine.price_loader.load(
                    self.tickers,
                    roll_start.strftime("%Y-%m-%d"),
                    self.data_end.strftime("%Y-%m-%d"),
                    allow_synthetic=self.use_synthetic,
                )
            except Exception:
                self._full_pd = None

        total_cases = self._estimate_total_cases(roll_start) if self.progress_callback else 0
        start_time  = time.time()
        cases, cur, run_id = [], roll_start, 1

        while True:
            end = cur + relativedelta(years=self.accumulation_years)
            if end > self.data_end:
                break
            strategy = self.strategy_factory()
            _krf_gain, _fin_by_yr, _comp_yrs = 0.0, {}, []   # Phase 2f 기본값
            _total_fees = 0.0                                 # D4 거래수수료

            # ── ISA 풍차돌리기 (특수 경로 — 주기별 수동 청산·재가입) ────
            if self.isa_renewal and self.tax_engine:
                _maturity, _early = self._run_isa_renewal_cycle(cur, self.accumulation_years)
                final_value = _maturity
                # 지표 계산용 무세금 시뮬 (history만 필요)
                isa_result = self.portfolio_engine.run_simulation(
                    tickers              = self.tickers,
                    start_date           = cur.strftime("%Y-%m-%d"),
                    end_date             = end.strftime("%Y-%m-%d"),
                    initial_capital      = self.initial_capital,
                    monthly_contribution = self.monthly_contribution,
                    strategy             = strategy,
                    dividend_mode        = self.dividend_mode,
                )
                history_df  = isa_result["history"]
                raw_final   = float(isa_result["final_value"])

            # ── 일반 경로 — Runner ───────────────────────────────────
            else:
                _early = None
                try:
                    if self.use_synthetic and self.synthetic_params:
                        price_data, dates = self._load_with_per_window_synthetic(cur, end)
                    elif self._full_pd is not None:
                        price_data, dates = self._slice_window(cur, end)
                    else:
                        price_data, dates = self.portfolio_engine.price_loader.load(
                            self.tickers,
                            cur.strftime("%Y-%m-%d"),
                            end.strftime("%Y-%m-%d"),
                            allow_synthetic=self.use_synthetic,
                        )
                except Exception:
                    cur    += relativedelta(months=self.step_months)
                    run_id += 1
                    continue

                target_weights = getattr(strategy, 'target_weights',
                                         {t: 1.0 / len(self.tickers) for t in self.tickers})
                rebal_freq     = getattr(strategy, 'rebalance_frequency', None)

                config = SimulationConfig(
                    start_date              = cur.strftime("%Y-%m-%d"),
                    end_date                = end.strftime("%Y-%m-%d"),
                    tickers                 = self.tickers,
                    target_weights          = target_weights,
                    initial_capital         = self.initial_capital,
                    monthly_contribution    = self.monthly_contribution,
                    contribution_end_months = self.contribution_end_months,
                    withdrawal_amount       = 0,
                    dividend_mode           = self.dividend_mode,
                    rebalance_frequency     = rebal_freq,
                    inflation               = 0.0,
                    fee_rate                = self.fee_rate,
                    stock_tickers           = self.stock_tickers,
                )

                run_result  = runner.run(
                    config          = config,
                    price_data      = price_data,
                    dates           = dates,
                    strategy        = strategy,
                    tax_enabled     = bool(self.tax_engine),
                    account_type    = self.account_type,
                    tax_engine      = self.tax_engine,
                    gain_harvesting = self.gain_harvesting,
                    apply_final_liquidation = self.apply_final_liquidation,
                )
                history_df  = run_result.history_df
                final_value = run_result.end_value
                _total_fees = float(getattr(run_result, 'total_fees', 0.0))
                raw_final   = float(history_df['portfolio_value'].iloc[-1]) if not history_df.empty else 0.0
                # Phase 2f: 종합과세 패널/트래킹 정보 (case별)
                _krf_gain   = getattr(run_result, 'kr_foreign_unrealized_gain', 0.0)
                _fin_by_yr  = getattr(run_result, 'financial_income_by_year', None) or {}
                _comp_yrs   = list(getattr(run_result, 'comprehensive_years', ()) or ())

            if history_df is None or history_df.empty:
                cur    += relativedelta(months=self.step_months)
                run_id += 1
                continue

            metrics              = self._calc_metrics(history_df, self.accumulation_years)
            metrics["run_id"]    = run_id
            metrics["start"]     = cur.strftime("%Y-%m-%d")
            metrics["end"]       = end.strftime("%Y-%m-%d")
            metrics["end_value"] = final_value
            metrics["total_fees"] = _total_fees
            metrics["kr_foreign_unrealized_gain"] = _krf_gain
            metrics["financial_income_by_year"]   = _fin_by_yr
            metrics["comprehensive_years"]        = _comp_yrs
            if self.isa_renewal and self.tax_engine and _early is not None:
                metrics["end_value_early_cancel"] = _early

            # 경험적 부채꼴용 연차 궤적(시점별 자산값)
            from modules.multi_account_common import yearly_trajectory
            metrics["_yearly"] = yearly_trajectory(
                history_df, self.accumulation_years, final_value)

            # 청산세 적용으로 end_value가 세전 history와 달라진 경우 → CAGR 재계산
            if final_value != raw_final:
                total_contrib = (
                    self.initial_capital
                    + self.monthly_contribution * self.accumulation_years * 12
                )
                if total_contrib > 0 and final_value > 0 and self.accumulation_years > 0:
                    metrics["cagr"] = (
                        (final_value / total_contrib) ** (1.0 / self.accumulation_years) - 1
                    )

            cases.append(metrics)
            if self.progress_callback:
                self.progress_callback(
                    current=run_id,
                    total=total_cases,
                    elapsed=time.time() - start_time,
                )
            if self.verbose:
                print(f"  [{run_id:03d}] {cur.strftime('%Y-%m')} ~ {end.strftime('%Y-%m')}"
                      f"  종료자산(세후): {final_value:,.0f}")
            cur    += relativedelta(months=self.step_months)
            run_id += 1
        return cases

    def _slice_window(self, start_ts, end_ts):
        """P0-1: 사전 로드한 전체 프레임에서 [start_ts, end_ts] 윈도우를 슬라이스.
        per-window price_loader.load와 동일 결과(이미 union·reindex·ffill된 전체에서 잘라냄).
        WithdrawalAnalyzer._run_wd_case와 같은 슬라이싱 방식."""
        dates = [d for d in self._full_dates if start_ts <= d <= end_ts]
        price_data = {
            ticker: df.loc[(df.index >= start_ts) & (df.index <= end_ts)]
            for ticker, df in self._full_pd.items()
        }
        return price_data, dates

    def _run_isa_renewal_cycle(
        self,
        start: "pd.Timestamp",
        total_years: int,
    ) -> tuple:
        """
        ISA 3년마다 해지·재가입 시뮬레이션 — TaxableSimulationRunner 기반 (Phase 3).
        각 3년 사이클: Runner(account_type="ISA", isa_years_held=3) → end_value가 세후값.
        나머지 기간(remainder > 0): 만기 가정(isa_years_held=3)으로 기본 계산.
          → 중도해지 가정값도 추가 계산해서 함께 반환 (프론트 체크박스 토글용).

        Returns
        -------
        (end_value_maturity, end_value_early_cancel)
          end_value_early_cancel: remainder==0이면 None
        """
        from modules.simulation.taxable_runner import TaxableSimulationRunner
        from modules.config.simulation_config   import SimulationConfig

        runner          = TaxableSimulationRunner()
        current_capital = self.initial_capital
        current_start   = start
        n_full    = total_years // 3
        remainder = total_years % 3

        for _cycle in range(n_full):
            cycle_end = current_start + relativedelta(years=3)
            if cycle_end > self.data_end:
                cycle_end = self.data_end
            if current_start >= cycle_end:
                break

            strategy = self.strategy_factory()
            try:
                if self.use_synthetic and self.synthetic_params:
                    price_data, dates = self._load_with_per_window_synthetic(current_start, cycle_end)
                elif self._full_pd is not None:
                    price_data, dates = self._slice_window(current_start, cycle_end)
                else:
                    price_data, dates = self.portfolio_engine.price_loader.load(
                        self.tickers,
                        current_start.strftime("%Y-%m-%d"),
                        cycle_end.strftime("%Y-%m-%d"),
                        allow_synthetic=self.use_synthetic,
                    )
                config = SimulationConfig(
                    start_date           = current_start.strftime("%Y-%m-%d"),
                    end_date             = cycle_end.strftime("%Y-%m-%d"),
                    tickers              = self.tickers,
                    target_weights       = getattr(strategy, 'target_weights',
                                                   {t: 1.0/len(self.tickers) for t in self.tickers}),
                    initial_capital      = current_capital,
                    monthly_contribution = self.monthly_contribution,
                    withdrawal_amount    = 0,
                    dividend_mode        = self.dividend_mode,
                    rebalance_frequency  = getattr(strategy, 'rebalance_frequency', None),
                    inflation            = 0.0,
                    fee_rate             = self.fee_rate,
                    stock_tickers        = self.stock_tickers,
                )
                run_result = runner.run(
                    config          = config,
                    price_data      = price_data,
                    dates           = dates,
                    strategy        = strategy,
                    tax_enabled     = True,
                    account_type    = "ISA",
                    tax_engine      = self.tax_engine,
                    isa_years_held  = 3,
                )
                current_capital = run_result.end_value  # 이미 after_tax_withdrawal 적용됨
            except Exception:
                break
            current_start = cycle_end

        # 나머지 기간 없으면 early_cancel 없음
        if remainder == 0 or current_start >= self.data_end:
            return current_capital, None

        # 나머지 기간 처리: 만기 가정(기본) + 중도해지 가정(체크박스) 둘 다 계산
        rem_end = current_start + relativedelta(years=remainder)
        if rem_end > self.data_end:
            rem_end = self.data_end

        end_value_maturity    = current_capital
        end_value_early_cancel = current_capital

        if current_start < rem_end:
            strategy = self.strategy_factory()
            try:
                if self.use_synthetic and self.synthetic_params:
                    price_data, dates = self._load_with_per_window_synthetic(current_start, rem_end)
                elif self._full_pd is not None:
                    price_data, dates = self._slice_window(current_start, rem_end)
                else:
                    price_data, dates = self.portfolio_engine.price_loader.load(
                        self.tickers,
                        current_start.strftime("%Y-%m-%d"),
                        rem_end.strftime("%Y-%m-%d"),
                        allow_synthetic=self.use_synthetic,
                    )
                config = SimulationConfig(
                    start_date           = current_start.strftime("%Y-%m-%d"),
                    end_date             = rem_end.strftime("%Y-%m-%d"),
                    tickers              = self.tickers,
                    target_weights       = getattr(strategy, 'target_weights',
                                                   {t: 1.0/len(self.tickers) for t in self.tickers}),
                    initial_capital      = current_capital,
                    monthly_contribution = self.monthly_contribution,
                    withdrawal_amount    = 0,
                    dividend_mode        = self.dividend_mode,
                    rebalance_frequency  = getattr(strategy, 'rebalance_frequency', None),
                    inflation            = 0.0,
                    fee_rate             = self.fee_rate,
                    stock_tickers        = self.stock_tickers,
                )
                # 만기 가정: isa_years_held=3 (기본 표시값)
                run_maturity = runner.run(
                    config         = config,
                    price_data     = price_data,
                    dates          = dates,
                    strategy       = strategy,
                    tax_enabled    = True,
                    account_type   = "ISA",
                    tax_engine     = self.tax_engine,
                    isa_years_held = 3,
                )
                end_value_maturity = run_maturity.end_value

                # 중도해지 가정: isa_years_held=remainder (체크박스 토글용)
                run_early = runner.run(
                    config         = config,
                    price_data     = price_data,
                    dates          = dates,
                    strategy       = strategy,
                    tax_enabled    = True,
                    account_type   = "ISA",
                    tax_engine     = self.tax_engine,
                    isa_years_held = remainder,
                )
                end_value_early_cancel = run_early.end_value
            except Exception:
                pass

        return end_value_maturity, end_value_early_cancel

    def _load_with_per_window_synthetic(
        self, window_start: pd.Timestamp, window_end: pd.Timestamp
    ) -> tuple:
        """Per-window independent GBM paths — avoids single-path slice artifact."""
        import numpy as np
        from modules.retirement.synthetic_price_generator import (
            SYNTHETIC_DF, T_SCALE, TRADING_DAYS_PER_MONTH,
        )

        raw_loader = self.portfolio_engine.price_loader.loader
        combined: dict = {}
        all_dates_set: set = set()

        # BUG-SYNTH-CORR: 조건부 다변량(종목 간 상관 복원) 우선 시도.
        # 추정 실패(표본부족·특이)·생성 실패 시 아래 종목별 독립 GBM 폴백(회귀 0).
        js = getattr(self, "_joint_stats", "unset")
        if js == "unset":
            try:
                from modules.retirement.synthetic_mvn import estimate_joint_stats
                self._joint_stats = estimate_joint_stats(self.tickers, raw_loader)
            except Exception:
                self._joint_stats = {"ok": False}
            js = self._joint_stats
        if js and js.get("ok"):
            try:
                from modules.retirement.synthetic_mvn import generate_joint_window
                return generate_joint_window(self.tickers, js, window_start, window_end, raw_loader)
            except Exception:
                pass  # 독립 폴백으로 진행

        for code in self.tickers:
            params = self.synthetic_params.get(code)
            window_start_str = window_start.strftime("%Y-%m-%d")
            window_end_str   = window_end.strftime("%Y-%m-%d")

            if (
                params is None
                or params.get("mu_monthly") is None
                or params.get("sigma_monthly") is None
                or params.get("anchor_price") is None
                or params.get("actual_start") is None
            ):
                # No usable synthetic params: fall back to DB path
                df = raw_loader.get_price(code, window_start_str, window_end_str,
                                          allow_synthetic=True)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
                combined[code] = df
                all_dates_set.update(df.index)
                continue

            actual_start_str = params["actual_start"]
            actual_start_dt  = pd.Timestamp(actual_start_str)
            from modules.retirement.synthetic_price_generator import MAX_SYNTH_MU_MONTHLY
            # mu 상한 캡: 짧은 불장 표본 mu를 수십 년 외삽 시 폭발 방지(generate_and_save와 동일).
            mu_monthly       = min(float(params["mu_monthly"]), MAX_SYNTH_MU_MONTHLY)
            sigma_monthly    = float(params["sigma_monthly"])
            # anchor는 실 suffix와 같은 FX 단위(KRW)여야 한다. params["anchor_price"]는
            # data_preparer가 raw price_daily(USD)로 잡은 값이라 get_price(FX·KRW) 실데이터와
            # 경계에서 ~환율배 어긋나 가격이 폭발한다(BUG-DIV-3). actual_start의 FX 실가격으로
            # anchor를 잡아 연속성을 보장한다(build_window_synth_params와 동일 방식).
            _a_end = (actual_start_dt + pd.Timedelta(days=14)).strftime("%Y-%m-%d")
            _adf   = raw_loader.get_price(code, actual_start_str, _a_end, allow_synthetic=False)
            if _adf is not None and not _adf.empty and "close" in _adf.columns and float(_adf["close"].iloc[0]) > 0:
                anchor_price = float(_adf["close"].iloc[0])
            else:
                anchor_price = float(params["anchor_price"])

            if window_start >= actual_start_dt:
                # Window fully in real range
                df = raw_loader.get_price(code, window_start_str, window_end_str,
                                          allow_synthetic=False)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
                combined[code] = df
                all_dates_set.update(df.index)
                continue

            # Need synthetic prefix: [window_start, min(actual_start-1, window_end)]
            synth_end_dt = min(actual_start_dt - pd.Timedelta(days=1), window_end)
            bdays = pd.bdate_range(start=window_start, end=synth_end_dt)

            if len(bdays) > 0:
                seed   = abs(hash(code + window_start_str)) % (2 ** 31)
                n      = len(bdays)
                mu_d   = mu_monthly / TRADING_DAYS_PER_MONTH
                sig_d  = sigma_monthly / np.sqrt(TRADING_DAYS_PER_MONTH)
                rng    = np.random.default_rng(seed=seed)
                raw    = rng.standard_t(df=SYNTHETIC_DF, size=n)
                rets   = (raw / T_SCALE) * sig_d + mu_d
                prices = np.empty(n)
                prices[-1] = anchor_price / (1.0 + rets[-1])
                for i in range(n - 2, -1, -1):
                    prices[i] = prices[i + 1] / (1.0 + rets[i])
                    if prices[i] <= 0:
                        prices[i] = prices[i + 1] * 0.99
                synth_df = pd.DataFrame(
                    {"open": prices, "high": prices, "low": prices,
                     "close": prices, "volume": np.zeros(n),
                     "dividend": np.zeros(n), "split": np.ones(n)},
                    index=pd.DatetimeIndex(bdays),
                )
                synth_df.index.name = "date"
            else:
                synth_df = None

            if window_end >= actual_start_dt:
                real_df = raw_loader.get_price(code, actual_start_str, window_end_str,
                                               allow_synthetic=False)
                real_df["date"] = pd.to_datetime(real_df["date"])
                real_df = real_df.set_index("date")
                for col in ["open", "high", "low", "close", "volume", "dividend", "split"]:
                    if col not in real_df.columns:
                        real_df[col] = 0.0 if col != "split" else 1.0
                if synth_df is not None and not synth_df.empty:
                    df = pd.concat([synth_df, real_df], axis=0)
                    df = df[~df.index.duplicated(keep="last")].sort_index()
                else:
                    df = real_df
            else:
                df = synth_df if synth_df is not None else pd.DataFrame()

            if df is not None and not df.empty:
                combined[code] = df
                all_dates_set.update(df.index)

        if not combined:
            return {}, []

        dates      = sorted(all_dates_set)
        full_index = pd.DatetimeIndex(dates)
        for code in self.tickers:
            if code not in combined:
                continue
            df = combined[code].reindex(full_index)
            df[["open", "high", "low", "close", "volume"]] = (
                df[["open", "high", "low", "close", "volume"]].ffill()
            )
            if "dividend" in df.columns:
                df["dividend"] = df["dividend"].fillna(0)
            if "split" in df.columns:
                df["split"] = df["split"].fillna(1)
            combined[code] = df

        return combined, dates

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
        # 초기 일시금만 있는 경우에는 IRR을 월수익률처럼 연율화하면 왜곡된다.
        mwr = 0.0
        if self.monthly_contribution > 0 and "cash_flow" in history.columns:
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
            "total_fees",   # D4 거래수수료(중앙값 표시용)
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
