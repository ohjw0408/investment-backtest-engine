"""
modules/simulation/multi_account_loop.py
G1 다중 계좌 통합 시간 루프.

한 시나리오 안에서 여러 계좌 포트폴리오를 같은 날짜축으로 동시에 운용한다.
G1에서는 transfers_enabled=False만 지원하며, 계좌 간 이동 단계는 생략한다.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class MultiAccountRunResult:
    combined_history_df: pd.DataFrame
    combined_end_value: float
    account_results: list[dict[str, Any]]
    transfer_log: list[dict[str, Any]] = field(default_factory=list)
    financial_income_by_year: dict = field(default_factory=dict)  # 개인 금융소득 합계(연도별)
    comprehensive_years: tuple = ()                                # 종합과세 대상 연도(>2천만 ∪ 수동)
    annual_deduction_credit: float = 0.0       # G4 연 납입 세액공제 환급 누계
    pension_transfer_credit_total: float = 0.0  # G3 ISA→연금 이전공제 환급 누계


class MultiAccountSimulationLoop:
    """N개 계좌를 하나의 날짜 루프에서 동시에 운용하는 오케스트레이터."""

    def __init__(self, transfers_enabled: bool = False):
        self.transfers_enabled = transfers_enabled

    def run(
        self,
        accounts: list[dict[str, Any]],
        price_data: dict[str, pd.DataFrame],
        dates,
        tax_enabled: bool = False,
        user_settings: dict | None = None,
        progress_callback=None,
        record_history: bool = True,
        distribution_policy=None,
        manual_comprehensive_years=None,
        reinvest_tax_credit: bool = False,
        apply_final_liquidation: bool = True,
    ) -> MultiAccountRunResult:
        if not accounts:
            raise ValueError("계좌가 없습니다.")
        if not dates:
            raise ValueError("시뮬레이션 날짜가 없습니다.")

        user_settings = user_settings or {}
        # 투자계산기·백테스트=True(끝에 일괄청산). 은퇴 적립=False(무청산 인계 → 인출단계서 과세).
        self._apply_final_liquidation = apply_final_liquidation

        # G2: 정책 목적지가 없는 계좌를 가리키면 위탁 자동 싱크(첫 ISA 미러) 생성
        if self.transfers_enabled and distribution_policy is not None:
            accounts, distribution_policy = self._ensure_sync_accounts(
                accounts, distribution_policy
            )

        # 2-4: 계좌간 금융소득을 한 풀로 집계하는 공유 세션(개인 과세단위).
        # 위탁 배당 gross + KR_FOREIGN 실현차익만 가산(ISA/연금 제외) → 연도별 종합과세 판정.
        tax_session = None
        if tax_enabled:
            from modules.tax.session import TaxSessionState
            other_fin = float((user_settings or {}).get("other_financial_income", 0.0) or 0.0)
            tax_session = TaxSessionState(other_financial_income=other_fin)
        self._tax_session = tax_session
        self._manual_comprehensive_years = set(manual_comprehensive_years or ())
        self._comprehensive_threshold = 20_000_000

        # G4: 연 납입 세액공제 상태(개인 단위). external 연금/IRP 납입 연도별 집계.
        self._reinvest_tax_credit = bool(reinvest_tax_credit)
        self._pension_ext_by_year: dict[int, float] = {}
        self._irp_ext_by_year: dict[int, float] = {}
        self._annual_deduction_total = 0.0
        self._injection_year: int | None = None
        # sim 마지막 월 인덱스 — 그 달엔 풍차 재가입 안 함(굴릴 시간 0 = 비현실적 잔재 방지).
        self._last_month_idx = len({(d.year, d.month) for d in dates}) - 1

        runtimes = [
            self._build_runtime(i, account, tax_enabled, user_settings, dates, tax_session)
            for i, account in enumerate(accounts)
        ]
        self._ref_tax_engine = next(
            (rt["tax_engine"] for rt in runtimes if rt.get("tax_engine") is not None), None
        )

        # G2 라우팅 상태(transfers OFF면 전부 미사용 → G1 동작 그대로)
        tracker = None
        account_types: dict[int, str] = {}
        transfer_log: list[dict[str, Any]] = []
        loop_last_month = None
        self._transfer_month_idx = 0
        if self.transfers_enabled:
            from modules.tax.account_tax import ContributionLimitTracker
            tracker = ContributionLimitTracker()
            tracker.touch(dates[0])
            account_types = {rt["account_id"]: rt["account_type"] for rt in runtimes}
            # 초기자본도 한도 소비(ISA 연/총)
            for rt in runtimes:
                init = float(getattr(rt["config"], "initial_capital", 0.0) or 0.0)
                if init > 0:
                    tracker.record(rt["account_id"], rt["account_type"], init)

        price_array: dict[str, Any] = {}
        valid_index: dict[str, Any] = {}
        for ticker, df in price_data.items():
            price_array[ticker] = df["close"].values
            valid_index[ticker] = df.index

        combined_rows: list[dict[str, Any]] = []
        total_dates = len(dates)
        update_step = max(1, total_dates // 20)

        import time as _time
        start_time = _time.time() if progress_callback else None

        for i, date in enumerate(dates):
            combined_value = 0.0
            combined_cash = 0.0
            combined_dividend = 0.0
            combined_cash_flow = 0.0
            active_accounts = 0
            account_values: dict[str, float] = {}

            # G2: 월 경계에서만 납입 라우팅(상한+cascade)+만기분배 계산. 비경계 = 납입 0.
            injections: dict[int, float] | None = None   # 외부 자금(cash_flow 기록)
            transfers: dict[int, float] | None = None     # 내부 이동(만기 목돈 재배분, cash_flow 0)
            if self.transfers_enabled:
                cur_m = (date.year, date.month)
                if cur_m != loop_last_month:
                    loop_last_month = cur_m
                    injections, transfers = self._compute_injections(
                        runtimes, tracker, account_types,
                        distribution_policy, date, transfer_log,
                        price_array, valid_index, i,
                    )
                else:
                    injections = {}
                    transfers = {}

            for rt in runtimes:
                price_dict = self._price_dict_for_account(
                    rt["config"].tickers, price_array, valid_index, i, date
                )
                if not price_dict:
                    continue

                override = None
                transfer_in = 0.0
                if self.transfers_enabled:
                    override = float(injections.get(rt["account_id"], 0.0)) if injections else 0.0
                    transfer_in = float(transfers.get(rt["account_id"], 0.0)) if transfers else 0.0

                dividend_by_ticker, cash_flow = self._step_account(
                    rt, price_data, price_dict, date,
                    contribution_override=override, transfer_override=transfer_in,
                )
                portfolio = rt["portfolio"]
                total_value = float(portfolio.total_value(price_dict))

                if record_history:
                    rt["recorder"].record(
                        date,
                        portfolio,
                        price_dict,
                        rt["config"].tickers,
                        dividend_by_ticker,
                        cash_flow=cash_flow,
                    )

                active_accounts += 1
                combined_value += total_value
                combined_cash += float(portfolio.cash)
                combined_dividend += float(sum(dividend_by_ticker.values()))
                combined_cash_flow += float(cash_flow)
                account_values[f"account_{rt['account_id']}_value"] = total_value

            if record_history and active_accounts > 0:
                combined_rows.append({
                    "date": date,
                    "portfolio_value": combined_value,
                    "asset_value": combined_value - combined_cash,
                    "cash": combined_cash,
                    "dividend_income": combined_dividend,
                    "cash_flow": combined_cash_flow,
                    **account_values,
                })

            if progress_callback and i % update_step == 0:
                progress_callback(
                    current=i + 1,
                    total=total_dates,
                    elapsed=_time.time() - start_time,
                )

        account_results = [self._finalize_account(rt, price_data) for rt in runtimes]
        combined_history_df = pd.DataFrame(combined_rows)
        if not combined_history_df.empty:
            combined_history_df = combined_history_df.sort_values("date").reset_index(drop=True)

        # 2-4: 개인 금융소득 연도별 집계 + 종합과세 대상 연도(라이브 ∪ 수동)
        financial_income_by_year: dict = {}
        comprehensive_years: tuple = ()
        if tax_session is not None:
            financial_income_by_year = tax_session.finalize()
            comp = set(self._manual_comprehensive_years)
            comp |= {y for y, inc in financial_income_by_year.items()
                     if inc > self._comprehensive_threshold}
            comprehensive_years = tuple(sorted(comp))

        # G4: 마지막 해 연납입 세액공제 정산(보고만 — 이후 연도 없어 재투입 불가).
        if self.transfers_enabled and self._injection_year is not None:
            self._annual_deduction_total += self._annual_deduction_for_year(self._injection_year)

        return MultiAccountRunResult(
            combined_history_df=combined_history_df,
            combined_end_value=float(sum(r["end_value"] for r in account_results)),
            account_results=account_results,
            transfer_log=transfer_log,
            financial_income_by_year=financial_income_by_year,
            comprehensive_years=comprehensive_years,
            annual_deduction_credit=float(self._annual_deduction_total),
            pension_transfer_credit_total=float(
                sum(r.get("pension_transfer_credit", 0.0) for r in account_results)
            ),
        )

    def _compute_injections(
        self,
        runtimes: list[dict[str, Any]],
        tracker,
        account_types: dict[int, str],
        distribution_policy,
        date,
        transfer_log: list[dict[str, Any]],
        price_array: dict[str, Any],
        valid_index: dict[str, Any],
        i: int,
    ) -> tuple[dict[int, float], dict[int, float]]:
        """월 경계 1회: 만기 분배(2-2) + 월 납입/초과 라우팅(2-1) 계산.

        반환 = (external, internal)
          external : 외부 신규 자금(월 납입·초과 라우팅) → cash_flow 기록
          internal : 만기 목돈 재배분 → 내부 이동이므로 cash_flow 미기록(자금보존)

        - ISA: 연 2천만/총 1억 한도까지만 흡수. 초과분은 정책대로 cascade.
        - 연금/IRP: 합산 연 1800만 한도 내 base 납입.
        - 위탁: 무제한.
        - 풍차 만기(isa_renewal, 36개월마다): ISA 청산→만기세→리셋→목돈을 정책대로 재배분.
        """
        from modules.tax.account_tax import route_overflow

        idx = self._transfer_month_idx
        self._transfer_month_idx += 1
        tracker.touch(date)

        external: dict[int, float] = defaultdict(float)
        internal: dict[int, float] = defaultdict(float)
        rt_by_id = {rt["account_id"]: rt for rt in runtimes}
        cur_year = date.year

        # ── G4: 연 경계 — 직전 해 연 납입 세액공제 정산 + (재투자 ON) 정책 cascade 재투입 ──
        if self._injection_year is None:
            self._injection_year = cur_year
        elif cur_year != self._injection_year:
            prev = self._injection_year
            self._injection_year = cur_year
            credit = self._annual_deduction_for_year(prev)
            if credit > 0:
                self._annual_deduction_total += credit
                self._apply_credit_reinvest(
                    credit, distribution_policy, tracker, account_types,
                    external, rt_by_id, transfer_log, date, kind="annual_deduction",
                )

        # ── 2-2/2-4: ISA 풍차 만기 (3년=36개월마다) ──
        # 2-4: 직전 3개 과세기간 중 1회라도 금융소득종합과세 대상이면 풍차 중단
        #      (청산·재가입 스킵 → 기존 ISA 무한유지). 3년 롤링 재평가로 자격 복귀.
        if idx > 0 and idx % 36 == 0 and idx != self._last_month_idx \
                and distribution_policy is not None \
                and self._isa_renewal_eligible(date):
            g3_credit = 0.0
            for rt in runtimes:
                if rt["account_type"] != "ISA" or not rt.get("isa_renewal"):
                    continue
                lump = self._mature_isa(rt, tracker, price_array, valid_index, i, date)
                if lump <= 1e-9:
                    continue
                # 만기 전환: 연금/IRP는 1800만 한도와 별도(전액 전환) → pension_unlimited
                allocs, leftover = route_overflow(
                    lump, distribution_policy, tracker, account_types,
                    pension_unlimited=True,
                )
                for dest_id, amt in allocs:
                    internal[dest_id] += amt
                    dtype = account_types.get(dest_id, "위탁")
                    if dtype == "ISA":
                        rt_by_id[dest_id]["cycle_contribution"] += amt
                    elif dtype in ("연금저축", "IRP"):
                        # G3: 연금 이전 세액공제(이전액 10%, 연 300만 상한)
                        g3_credit += self._accrue_pension_credit(rt_by_id[dest_id], amt, date)
                transfer_log.append({
                    "date": str(getattr(date, "date", lambda: date)()),
                    "type": "maturity",
                    "account_id": rt["account_id"],
                    "lump": lump,
                    "maturity_tax": rt.get("_last_maturity_tax", 0.0),
                    "allocations": allocs,
                    "leftover": leftover,
                })
            # G3 이전공제 환급도 통합 토글로 정책 cascade 재투입(만기월 즉시).
            if g3_credit > 0:
                self._apply_credit_reinvest(
                    g3_credit, distribution_policy, tracker, account_types,
                    external, rt_by_id, transfer_log, date, kind="transfer_credit",
                )

        # ── 2-1: 월 납입 + 한도초과 라우팅 (외부 자금) ──
        # ISA(연2천만/총1억)·연금+IRP(합산 연1800만) 한도까지만 흡수, 초과분은 정책 cascade.
        overflow_total = 0.0
        for rt in runtimes:
            config = rt["config"]
            cap_m = getattr(config, "contribution_end_months", None)
            base = (
                0.0
                if (cap_m is not None and idx >= cap_m)
                else float(config.monthly_contribution or 0.0)
            )
            if base <= 0:
                continue
            aid = rt["account_id"]
            atype = rt["account_type"]
            if atype == "ISA":
                cap = tracker.capacity(aid, "ISA")
                absorbed = min(base, cap)
                tracker.record(aid, "ISA", absorbed)
                external[aid] += absorbed
                rt["cycle_contribution"] += absorbed
                overflow = base - absorbed
                if overflow > 1e-9:
                    overflow_total += overflow
            elif atype in ("연금저축", "IRP"):
                cap = tracker.capacity(aid, atype)   # 연금+IRP 합산 1800만 풀
                give = min(base, cap)
                tracker.record(aid, atype, give)
                external[aid] += give
                self._track_pension_contrib(atype, cur_year, give)  # G4 공제 base
                overflow = base - give
                if overflow > 1e-9:
                    overflow_total += overflow   # 합산한도 초과분 → 정책 라우팅
            else:  # 위탁(무제한)
                external[aid] += base

        if overflow_total > 1e-9 and distribution_policy is not None:
            allocs, leftover = route_overflow(
                overflow_total, distribution_policy, tracker, account_types
            )
            for dest_id, amt in allocs:
                external[dest_id] += amt
                dtype = account_types.get(dest_id, "위탁")
                if dtype == "ISA":
                    rt_by_id[dest_id]["cycle_contribution"] += amt
                elif dtype in ("연금저축", "IRP"):
                    self._track_pension_contrib(dtype, cur_year, amt)  # G4 공제 base
            transfer_log.append({
                "date": str(getattr(date, "date", lambda: date)()),
                "overflow": overflow_total,
                "allocations": allocs,
                "leftover": leftover,
            })

        return dict(external), dict(internal)

    def _isa_renewal_eligible(self, date) -> bool:
        """2-4: ISA 풍차(해지·재가입) 자격 판정 (개인 과세단위).

        직전 3개 과세기간(year-1·-2·-3) 중 1회라도 금융소득종합과세 대상(>2천만)이면
        신규가입·연장 불가 → 풍차 중단(False). 종합과세 연도 = 라이브 공유세션 집계
        ∪ 수동 오버라이드(manual_comprehensive_years).
        세션 없음(세금 OFF)·정보 부족이면 자격 있음(True) — 풍차 정상 진행.
        """
        session = getattr(self, "_tax_session", None)
        threshold = getattr(self, "_comprehensive_threshold", 20_000_000)
        comp_years = set(getattr(self, "_manual_comprehensive_years", ()) or ())
        if session is not None:
            # 직전 연도까지 기록되도록 현재 만기일로 세션 flush(연 경계 정산).
            session.touch(date)
            for y, inc in session.financial_income_by_year.items():
                if inc > threshold:
                    comp_years.add(y)
        year = date.year
        return not any((year - k) in comp_years for k in (1, 2, 3))

    def _mature_isa(self, rt, tracker, price_array, valid_index, i, date) -> float:
        """ISA 풍차 만기: 청산→만기세→계좌 초기화. 세후 목돈(재배분 대상) 반환.

        - 만기세 = after_tax_withdrawal(가치, ISA, 사이클납입액, isa_years_held=3).
          순이익=가치−사이클납입, 비과세 한도(200/400만) 초과분에 9.9%.
        - 포지션·평균단가 초기화 + tracker(연/총/policy_routed) 리셋 → 새 ISA 토대.
        - cycle_contribution=0 (재배분 라우팅이 재가입분만큼 다시 채움).
        """
        price_dict = self._price_dict_for_account(
            rt["config"].tickers, price_array, valid_index, i, date
        )
        portfolio = rt["portfolio"]
        value = float(portfolio.total_value(price_dict))
        tax = 0.0
        tax_engine = rt.get("tax_engine")
        if tax_engine is not None:
            after = tax_engine.after_tax_withdrawal(
                value, "ISA", rt["cycle_contribution"], isa_years_held=3,
            )
            tax = max(0.0, value - after)
        lump = value - tax

        # 절세액(위탁 가정): 만기 청산 = 그 사이클 미실현차익 실현(자산분류별).
        # 기준 리셋 전 누적 → 다음 사이클·최종청산과 무중복(풍차 통합 추적).
        executor = rt.get("executor")
        if executor is not None and tax_engine is not None \
                and hasattr(executor, "_brk_us_by_year"):
            cyc_year = date.year
            for ticker, pos in portfolio.positions.items():
                if ticker not in price_dict or pos.quantity <= 0:
                    continue
                gain = float(portfolio.unrealized_gain(ticker, price_dict[ticker]))
                cls = tax_engine.classify_asset(ticker)
                if cls == "KR_FOREIGN":
                    if gain > 0:
                        executor._brk_krf_gain += gain
                elif cls == "US_DIRECT":
                    executor._brk_us_by_year[cyc_year] = \
                        executor._brk_us_by_year.get(cyc_year, 0.0) + gain

        portfolio.positions = {}
        portfolio.cash = 0.0
        if hasattr(portfolio, "_avg_costs"):
            portfolio._avg_costs = {}

        aid = rt["account_id"]
        tracker._isa_annual.pop(aid, None)
        tracker._isa_total.pop(aid, None)
        tracker._policy_routed.pop(aid, None)
        rt["cycle_contribution"] = 0.0
        rt["maturity_tax_paid"] = rt.get("maturity_tax_paid", 0.0) + tax
        rt["_last_maturity_tax"] = tax
        return lump

    def _accrue_pension_credit(self, rt, amount, date) -> float:
        """G3: ISA→연금/IRP 이전 세액공제. 이전액의 10%(연 300만 상한) 환급액 반환.

        누계(pension_transfer_credit)에 가산. 연 300만 상한은 연도별로 적용.
        """
        if rt is None:
            return 0.0
        year = date.year
        credited = rt.setdefault("_credit_by_year", {})
        used = credited.get(year, 0.0)
        room = max(0.0, 3_000_000.0 - used)
        credit = min(amount * 0.10, room)
        if credit <= 0:
            return 0.0
        credited[year] = used + credit
        rt["pension_transfer_credit"] = rt.get("pension_transfer_credit", 0.0) + credit
        return credit

    def _track_pension_contrib(self, account_type, year, amount) -> None:
        """G4: 연 납입 세액공제 base — 연금/IRP external 납입(직접+2-1라우팅)을 연도별 집계.
        ISA 만기 전환분(internal)·환급 재투입분은 제외(G3 대상·이중공제 방지)."""
        if amount <= 0:
            return
        if account_type == "연금저축":
            self._pension_ext_by_year[year] = self._pension_ext_by_year.get(year, 0.0) + amount
        elif account_type == "IRP":
            self._irp_ext_by_year[year] = self._irp_ext_by_year.get(year, 0.0) + amount

    def _annual_deduction_for_year(self, year) -> float:
        """G4: 한 해 연금/IRP external 납입 → 세액공제 환급액(이미 검증된 계산식)."""
        if self._ref_tax_engine is None:
            return 0.0
        pension = self._pension_ext_by_year.get(year, 0.0)
        irp = self._irp_ext_by_year.get(year, 0.0)
        if pension <= 0 and irp <= 0:
            return 0.0
        return float(self._ref_tax_engine.annual_tax_deduction(pension, irp))

    def _apply_credit_reinvest(self, amount, distribution_policy, tracker, account_types,
                               external, rt_by_id, transfer_log, date, kind) -> None:
        """세액공제 환급금(G3 이전공제·G4 연납입공제 공통) 재투자.

        재투자 ON이면 환급액을 **분배 정책 cascade**로 재투입(정상 납입 한도 소비,
        pension_unlimited=False). 우선순위대로 채우고 마지막 위탁/leftover. 재투입분은
        다음 해 공제 base에 미포함(재귀 방지). 재투자 OFF면 환급액 보고만(미주입).
        """
        if amount <= 1e-9 or distribution_policy is None or not self._reinvest_tax_credit:
            return
        from modules.tax.account_tax import route_overflow
        allocs, leftover = route_overflow(amount, distribution_policy, tracker, account_types)
        for dest_id, amt in allocs:
            external[dest_id] += amt
            if account_types.get(dest_id) == "ISA":
                rt_by_id[dest_id]["cycle_contribution"] += amt
        transfer_log.append({
            "date": str(getattr(date, "date", lambda: date)()),
            "type": "credit_reinvest",
            "kind": kind,
            "amount": amount,
            "allocations": allocs,
            "leftover": leftover,
        })

    def _ensure_sync_accounts(self, accounts, distribution_policy):
        """정책 목적지가 없는 계좌(account_id >= len)를 가리키면 위탁 자동 싱크 생성.

        싱크 계좌 = 첫 ISA의 종목·비중 미러(같은 전략으로 굴림), 초기·월납입 0.
        라우팅 수신액만으로 운용되어 위탁 세율이 청산 시 적용된다.
        """
        from modules.config.simulation_config import SimulationConfig
        from modules.rebalance.periodic import PeriodicRebalance
        from modules.tax.account_tax import DistributionPolicy, DistributionDestination

        accounts = list(accounts)
        isa = next((a for a in accounts if a.get("type") == "ISA"), None)
        resolved: list = []
        for dest in distribution_policy.destinations:
            if dest.account_id < len(accounts):
                resolved.append(dest)
                continue
            if isa is None:
                resolved.append(dest)  # 미러 소스 없음 → 흡수 0(존재 안 함)
                continue
            src = isa["config"]
            weights = dict(src.target_weights)
            rebal = getattr(src, "rebalance_frequency", None)
            cfg = SimulationConfig(
                start_date=src.start_date,
                end_date=src.end_date,
                tickers=list(src.tickers),
                target_weights=weights,
                initial_capital=0.0,
                monthly_contribution=0.0,
                withdrawal_amount=0,
                dividend_mode=src.dividend_mode,
                rebalance_frequency=rebal,
                inflation=0.0,
            )
            new_id = len(accounts)
            accounts.append({
                "type": "위탁",
                "config": cfg,
                "strategy": PeriodicRebalance(weights, rebalance_frequency=rebal),
                "gain_harvesting": False,
            })
            resolved.append(DistributionDestination(account_id=new_id, cap=dest.cap))

        return accounts, DistributionPolicy(destinations=resolved)

    def _build_runtime(
        self,
        account_id: int,
        account: dict[str, Any],
        tax_enabled: bool,
        user_settings: dict,
        dates,
        tax_session=None,
    ) -> dict[str, Any]:
        from modules.core.portfolio import Portfolio, TaxTrackedPortfolio
        from modules.execution.cash_allocator import CashAllocator
        from modules.execution.order_executor import OrderExecutor, TaxedOrderExecutor
        from modules.simulation.contribution_engine import ContributionEngine
        from modules.simulation.dividend_engine import DividendEngine
        from modules.simulation.history_recorder import HistoryRecorder
        from modules.simulation.withdrawal_engine import WithdrawalEngine
        from modules.tax.base_tax import TaxEngine
        from modules.tax.account_tax import TaxedDividendEngine

        config = account["config"]
        account_type = account.get("type", "위탁")
        gain_harvesting = bool(account.get("gain_harvesting", False))
        init_capital = float(getattr(config, "initial_capital", 0.0) or 0.0)

        if tax_enabled:
            tax_engine = account.get("tax_engine") or TaxEngine(user_settings)
            # 공유 세션 — 전 위탁계좌 금융소득을 한 풀로(개인 과세단위) 집계.
            div_engine = TaxedDividendEngine(DividendEngine(), tax_engine, account_type,
                                             session=tax_session)
            executor = TaxedOrderExecutor(
                tax_engine,
                account_type,
                gain_harvesting=gain_harvesting,
                session=tax_session,
            )
            portfolio = TaxTrackedPortfolio(config.initial_capital)
        else:
            tax_engine = None
            div_engine = DividendEngine()
            executor = OrderExecutor()
            portfolio = Portfolio(config.initial_capital)

        return {
            "account_id": account_id,
            "account_type": account_type,
            "config": config,
            "strategy": account["strategy"],
            "tax_engine": tax_engine,
            "isa_years_held": int(account.get("isa_years_held", 3)),
            "isa_renewal": bool(account.get("isa_renewal", False)),
            "cycle_contribution": init_capital,
            "maturity_tax_paid": 0.0,
            "_last_maturity_tax": 0.0,
            "pension_transfer_credit": 0.0,
            "dividend_engine": div_engine,
            "contribution_engine": ContributionEngine(),
            "withdrawal_engine": WithdrawalEngine(),
            "executor": executor,
            "cash_allocator": CashAllocator(),
            "portfolio": portfolio,
            "recorder": HistoryRecorder(),
            "last_month": None,
            "last_withdrawal_month": (dates[0].year, dates[0].month) if dates else None,
            "elapsed_months": 0,
            "last_inflation_month": None,
            "is_first_day": True,
            "last_cf_month": None,
            "initial_capital_cf": 0.0,
            "dividend_tax_paid": 0.0,
            # 절세액(위탁 가정): 자산분류별 세전 배당 누계(전 기간·풍차 통합).
            "cf_gross_div_by_class": {},
        }

    def _price_dict_for_account(
        self,
        tickers: list[str],
        price_array: dict[str, Any],
        valid_index: dict[str, Any],
        i: int,
        date,
    ) -> dict[str, float]:
        price_dict: dict[str, float] = {}
        for ticker in tickers:
            if ticker not in valid_index or date not in valid_index[ticker]:
                continue
            arr = price_array[ticker]
            if i >= len(arr):
                continue
            price = arr[i]
            if price is None or price != price or price <= 0:
                continue
            price_dict[ticker] = float(price)
        return price_dict

    def _step_account(
        self, rt: dict[str, Any], price_data, price_dict, date,
        contribution_override: float | None = None,
        transfer_override: float = 0.0,
    ) -> tuple[dict, float]:
        portfolio = rt["portfolio"]
        config = rt["config"]
        strategy = rt["strategy"]

        current_month = (date.year, date.month)
        if rt["last_inflation_month"] is None:
            rt["last_inflation_month"] = current_month
        elif current_month != rt["last_inflation_month"]:
            rt["elapsed_months"] += 1
            rt["last_inflation_month"] = current_month

        if rt["is_first_day"]:
            rt["is_first_day"] = False
            rt["initial_capital_cf"] = getattr(config, "initial_capital", 0.0)
            cash_target = config.target_weights.get("CASH", 0)
            if cash_target == 0 and portfolio.cash > 0:
                rt["cash_allocator"].allocate_cash(portfolio, price_dict, config.target_weights)

        gross_dividend_by_ticker = self._gross_dividend_by_ticker(
            portfolio,
            price_data,
            date,
            taxed=hasattr(rt["dividend_engine"], "tax_engine"),
        )
        dividend_by_ticker = rt["dividend_engine"].process(
            portfolio,
            price_data,
            price_dict,
            date,
            config.dividend_mode,
        )
        if gross_dividend_by_ticker:
            dividend_tax = sum(
                max(0.0, gross - float(dividend_by_ticker.get(ticker, 0.0)))
                for ticker, gross in gross_dividend_by_ticker.items()
            )
            if dividend_tax > 0:
                # 현금 차감은 TaxedDividendEngine.process가 담당(이중차감 방지) — 여기선 보고만.
                rt["dividend_tax_paid"] += dividend_tax
            # 절세액(위탁 가정): 세전 배당을 자산분류별 누적(계좌유형 무관).
            tax_engine = rt.get("tax_engine")
            if tax_engine is not None:
                cls_acc = rt["cf_gross_div_by_class"]
                for ticker, gross in gross_dividend_by_ticker.items():
                    cls = tax_engine.classify_asset(ticker)
                    cls_acc[cls] = cls_acc.get(cls, 0.0) + float(gross)
        dividend_total = sum(dividend_by_ticker.values())
        if config.dividend_mode == "withdraw" and dividend_total > 0:
            portfolio.cash -= dividend_total

        if contribution_override is not None:
            # transfers 경로: 루프가 월 경계에서 계산한 실제 납입액(상한+라우팅 반영).
            # 월 1회 게이팅은 루프가 책임지므로 ContributionEngine 우회.
            # effective_monthly = 외부 신규 자금(cash_flow 기록), transfer_override = 만기 내부이동(미기록).
            effective_monthly = float(contribution_override)
            total_add = effective_monthly + float(transfer_override or 0.0)
            if total_add > 0:
                portfolio.cash += total_add
                cash_target = config.target_weights.get("CASH", 0)
                if cash_target == 0:
                    rt["cash_allocator"].allocate_cash(portfolio, price_dict, config.target_weights)
        else:
            effective_monthly = (
                0.0
                if (
                    getattr(config, "contribution_end_months", None) is not None
                    and rt["elapsed_months"] >= config.contribution_end_months
                )
                else config.monthly_contribution
            )
            rt["last_month"] = rt["contribution_engine"].process(
                portfolio,
                effective_monthly,
                date,
                rt["last_month"],
            )
            if effective_monthly > 0:
                cash_target = config.target_weights.get("CASH", 0)
                if cash_target == 0:
                    rt["cash_allocator"].allocate_cash(portfolio, price_dict, config.target_weights)

        rt["last_withdrawal_month"] = rt["withdrawal_engine"].process(
            portfolio,
            config.withdrawal_amount,
            price_dict,
            config.target_weights,
            date=date,
            last_month=rt["last_withdrawal_month"],
            elapsed_months=rt["elapsed_months"],
            inflation=getattr(config, "inflation", 0.0),
            executor=rt["executor"],
        )

        if strategy.should_rebalance(date, portfolio, price_dict):
            orders = strategy.generate_orders(portfolio, price_dict)
            rt["executor"].execute_orders(portfolio, orders, price_dict, date=date)

        if hasattr(rt["executor"], "maybe_gain_harvest"):
            rt["executor"].maybe_gain_harvest(portfolio, price_dict, date)

        if config.dividend_mode in ("reinvest", "withdraw") and config.withdrawal_amount == 0:
            cash_target = config.target_weights.get("CASH", 0)
            if cash_target == 0:
                rt["cash_allocator"].allocate_cash(portfolio, price_dict, config.target_weights)

        if current_month != rt["last_cf_month"]:
            rt["last_cf_month"] = current_month
            cash_flow = effective_monthly - config.withdrawal_amount
            if rt["initial_capital_cf"] > 0:
                cash_flow += rt["initial_capital_cf"]
                rt["initial_capital_cf"] = 0.0
        else:
            cash_flow = 0.0

        return dividend_by_ticker, float(cash_flow)

    def _gross_dividend_by_ticker(self, portfolio, price_data, date, taxed: bool) -> dict[str, float]:
        if not taxed:
            return {}
        gross: dict[str, float] = {}
        for ticker, position in portfolio.positions.items():
            if ticker not in price_data or date not in price_data[ticker].index:
                continue
            dividend = price_data[ticker].loc[date, "dividend"]
            if dividend > 0:
                gross[ticker] = float(dividend) * float(position.quantity)
        return gross

    def _finalize_account(self, rt: dict[str, Any], price_data: dict[str, pd.DataFrame]) -> dict[str, Any]:
        history_df = rt["recorder"].to_dataframe()
        if history_df.empty:
            return {
                "account_id": rt["account_id"],
                "type": rt["account_type"],
                "history_df": history_df,
                "raw_end_value": 0.0,
                "end_value": 0.0,
                "total_contribution": 0.0,
                "tax_paid": 0.0,
                "brokerage_assumed_tax": 0.0,
                "tax_saving": 0.0,
                "gain_harvest_saving": 0.0,
            }

        config = rt["config"]
        raw_end_value = float(history_df["portfolio_value"].iloc[-1])
        positive_cash_flow = history_df.loc[history_df["cash_flow"] > 0, "cash_flow"]
        total_contribution = float(positive_cash_flow.sum())
        end_value = raw_end_value
        liquidation_tax = 0.0
        kr_foreign_unrealized_gain = 0.0

        tax_engine = rt.get("tax_engine")
        # 은퇴 적립은 무청산 인계(self._apply_final_liquidation=False) — 끝에 안 판다.
        # 적립기 중간세(배당·리밸·풍차 만기세)는 루프에서 이미 처리됨. 최종 청산만 스킵.
        apply_final_liq = getattr(self, "_apply_final_liquidation", True)
        if tax_engine is not None:
            from modules.tax.liquidation import apply_liquidation_tax

            last_prices = {
                t: float(price_data[t]["close"].iloc[-1])
                for t in config.tickers
                if t in price_data and not price_data[t].empty
            }
            # 위탁 미실현 KR_FOREIGN 차익(정보용 — 청산 여부와 무관하게 surface).
            if rt["account_type"] == "위탁" and hasattr(rt["portfolio"], "positions"):
                for ticker, pos in rt["portfolio"].positions.items():
                    if ticker in last_prices and pos.quantity > 0:
                        if tax_engine.classify_asset(ticker) == "KR_FOREIGN":
                            gain = rt["portfolio"].unrealized_gain(ticker, last_prices[ticker])
                            if gain > 0:
                                kr_foreign_unrealized_gain += gain

            if apply_final_liq:
                ytd_us_gains = getattr(rt["executor"], "_ytd_us_gains", 0.0)
                # 풍차 ISA: 최종 청산세 원가는 마지막 사이클 납입액(전 기간 누적 아님).
                tc_for_tax = total_contribution
                if rt["account_type"] == "ISA" and rt.get("isa_renewal"):
                    tc_for_tax = float(rt.get("cycle_contribution", total_contribution))
                end_value = apply_liquidation_tax(
                    end_value=raw_end_value,
                    portfolio=rt["portfolio"],
                    last_prices=last_prices,
                    tax_engine=tax_engine,
                    account_type=rt["account_type"],
                    total_contribution=tc_for_tax,
                    ytd_us_realized_gains=ytd_us_gains,
                    age=getattr(tax_engine, "age", 40),
                    isa_years_held=rt.get("isa_years_held", 3),
                )
                liquidation_tax = max(0.0, raw_end_value - end_value)
                # 절세액(위탁 가정): 최종 청산 = 잔여 미실현차익 실현(계좌유형 무관, 자산분류별).
                executor = rt.get("executor")
                if executor is not None and hasattr(executor, "_brk_us_by_year") \
                        and hasattr(rt["portfolio"], "positions"):
                    last_year = 0
                    for t in config.tickers:
                        if t in price_data and not price_data[t].empty:
                            last_year = max(last_year, price_data[t].index[-1].year)
                    for ticker, pos in rt["portfolio"].positions.items():
                        if ticker not in last_prices or pos.quantity <= 0:
                            continue
                        gain = float(rt["portfolio"].unrealized_gain(ticker, last_prices[ticker]))
                        cls = tax_engine.classify_asset(ticker)
                        if cls == "KR_FOREIGN":
                            if gain > 0:
                                executor._brk_krf_gain += gain
                        elif cls == "US_DIRECT":
                            executor._brk_us_by_year[last_year] = \
                                executor._brk_us_by_year.get(last_year, 0.0) + gain

        dividend_tax = float(rt.get("dividend_tax_paid", 0.0))
        realized_tax = float(getattr(rt["executor"], "total_cg_tax_paid", 0.0))
        maturity_tax = float(rt.get("maturity_tax_paid", 0.0))
        actual_tax = dividend_tax + realized_tax + liquidation_tax + maturity_tax

        # 절세액(위탁 가정): 누적 세전흐름으로 위탁 세금 추정 → 절세액 = max(0, 위탁가정 − 실제).
        brokerage_assumed_tax = 0.0
        tax_saving = 0.0
        gain_harvest_saving = 0.0
        executor = rt.get("executor")
        if tax_engine is not None and executor is not None \
                and hasattr(executor, "_brk_us_by_year"):
            from modules.tax.saving_estimate import (
                estimate_brokerage_tax, estimate_gain_harvest_saving,
            )
            brokerage_assumed_tax = estimate_brokerage_tax(
                rt.get("cf_gross_div_by_class", {}),
                executor._brk_krf_gain,
                executor._brk_us_by_year,
            )
            tax_saving = max(0.0, brokerage_assumed_tax - actual_tax)
            # GH 절세(절세매도 자체 효과): 위탁계좌 + GH ON 전용.
            if rt["account_type"] == "위탁" and getattr(executor, "gain_harvesting", False) \
                    and executor._brk_us_harvested_total > 0:
                last_year = 0
                for t in config.tickers:
                    if t in price_data and not price_data[t].empty:
                        last_year = max(last_year, price_data[t].index[-1].year)
                gain_harvest_saving = estimate_gain_harvest_saving(
                    executor._brk_us_by_year,
                    executor._brk_us_harvested_total,
                    last_year,
                )

        return {
            "account_id": rt["account_id"],
            "type": rt["account_type"],
            "history_df": history_df,
            "raw_end_value": raw_end_value,
            "end_value": float(end_value),
            "total_contribution": total_contribution,
            "cycle_contribution": float(rt.get("cycle_contribution", total_contribution)),
            "tax_paid": actual_tax,
            "dividend_tax_paid": dividend_tax,
            "realized_tax_paid": realized_tax,
            "liquidation_tax_paid": liquidation_tax,
            "maturity_tax_paid": maturity_tax,
            "brokerage_assumed_tax": brokerage_assumed_tax,
            "tax_saving": tax_saving,
            "gain_harvest_saving": gain_harvest_saving,
            "pension_transfer_credit": float(rt.get("pension_transfer_credit", 0.0)),
            "kr_foreign_unrealized_gain": kr_foreign_unrealized_gain,
            "portfolio": rt["portfolio"],
        }
