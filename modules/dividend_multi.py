"""배당금 계산기 멀티계좌 (G5-E, 2026-06-13 오너 결정).

오너 결정: ① 자동 역산 지원 — 역산 변수(시드/월납)는 **계좌 1** 값으로 해석, 나머지 계좌 고정.
② G2 풀 라우팅 — ISA 연/총 한도 cascade·풍차 만기분배·연금 G3/G4 공제 = `MultiAccountSimulationLoop`
   그대로 사용(월별 모드 주입 — 루프 무변경, divrefactoring과 동일 수법).

구조: `DividendSimulator` 서브클래스. 역산/곡선/시나리오 레이어는 부모 그대로 상속하고
`_simulate_one`(윈도우 1회)만 멀티 루프로, 합성 폴백은 계좌별 단일 합성의 합으로 교체.
반환 규약 동일: "마지막 1년 가구 합산 순배당"(combined `dividend_income`, 무청산).
"""
import copy
from typing import Dict, List

import pandas as pd
import numpy as np

from modules.dividend_simulator import DividendSimulator


class MultiDividendSimulator(DividendSimulator):

    def __init__(
        self,
        loader,
        accounts: list[dict],          # normalize_multi_accounts 출력 형식
        *,
        div_mode: str = "reinvest",
        step_months: int = 3,
        tax_enabled: bool = False,
        user_settings: dict | None = None,
        distribution_policy=None,
        reinvest_tax_credit: bool = False,
    ):
        from modules.tax.base_tax import TaxEngine

        self._accounts = accounts
        self._tax_enabled = bool(tax_enabled)
        self._user_settings = user_settings or {}
        self._distribution_policy = distribution_policy
        self._reinvest_tax_credit = bool(reinvest_tax_credit)
        has_pension = any(a["type"] in ("연금저축", "IRP") for a in accounts)
        self._transfers_enabled = (
            distribution_policy is not None
            or any(a.get("isa_renewal") for a in accounts)
            or (tax_enabled and has_pension)
        )

        # 부모 ctor — 종목/비중 = 전 계좌 합집합(데이터 로딩·실데이터 경계·합성 stats 폴백용).
        # 비중 = 계좌 자본(시드 + 월납×120) 가중 합산 후 정규화.
        cap = {a_idx: (float(a.get("initial_capital", 0)) +
                       float(a.get("monthly_contribution", 0)) * 120) or 1.0
               for a_idx, a in enumerate(accounts)}
        agg: Dict[str, float] = {}
        for a_idx, a in enumerate(accounts):
            for t in a["tickers"]:
                agg[t["code"]] = agg.get(t["code"], 0.0) + float(t["weight"]) * cap[a_idx]
        total = sum(agg.values()) or 1.0
        union_weights = {c: w / total for c, w in agg.items()}

        super().__init__(
            loader=loader,
            tickers=list(union_weights),
            weights=union_weights,
            div_mode=div_mode,
            step_months=step_months,
            rebal_mode="none",   # 리밸은 계좌별 config가 처리 — 부모 필드는 미사용
            tax_engine=TaxEngine(self._user_settings) if tax_enabled else None,
            account_type="위탁",
        )

        # 합성 폴백용 계좌별 단일 시뮬(가격 캐시 공유). G2 라우팅은 합성에서 미모델(근사 — 화면 라벨).
        self._children: list[DividendSimulator] = []
        for a in accounts:
            w = {t["code"]: float(t["weight"]) for t in a["tickers"]}
            child = DividendSimulator(
                loader=loader, tickers=list(w), weights=w, div_mode=div_mode,
                step_months=step_months, rebal_mode=a.get("rebal_mode", "none"),
                band_width=float(a.get("band_width", 0.05)),
                tax_engine=self.tax_engine if tax_enabled else None,
                account_type=a["type"],
                isa_total_limit=100_000_000 if (tax_enabled and a["type"] == "ISA") else None,
            )
            child._price_cache = self._price_cache
            self._children.append(child)
        self._child_stats: list[dict | None] = [None] * len(accounts)

    # ── 윈도우 1회: 멀티 루프(월별 주입, 무청산) ─────────────────
    def _simulate_one(self, seed, monthly, years, start_date) -> float:
        from modules.multi_account_common import build_loop_accounts
        from modules.simulation.multi_account_loop import MultiAccountSimulationLoop
        from modules.simulation.monthly_mode import to_monthly_price_data, last_year_dividend

        self._last_savings = None
        start = pd.Timestamp(start_date)
        end = start + pd.DateOffset(years=years)

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
        valid_froms = [df["close"].first_valid_index() for df in m_data.values()]
        if any(v is None for v in valid_froms):
            return 0.0
        valid_from = max(valid_froms)
        m_dates = [d for d in m_dates if d >= valid_from]
        if not m_dates:
            return 0.0
        m_data = {t: df.loc[m_dates[0]:] for t, df in m_data.items()}

        # 역산 변수 주입: 계좌 1의 시드/월납만 교체(오너 결정), 나머지 고정.
        accounts = copy.deepcopy(self._accounts)
        accounts[0]["initial_capital"] = float(seed)
        accounts[0]["monthly_contribution"] = float(monthly)

        loop_accounts = build_loop_accounts(
            accounts, str(m_dates[0].date()), str(end.date()),
            default_dividend_mode=self.div_mode,
        )
        result = MultiAccountSimulationLoop(
            transfers_enabled=self._transfers_enabled,
        ).run(
            accounts=loop_accounts,
            price_data=m_data,
            dates=m_dates,
            tax_enabled=self._tax_enabled,
            user_settings=self._user_settings,
            distribution_policy=self._distribution_policy,
            reinvest_tax_credit=self._reinvest_tax_credit,
            apply_final_liquidation=False,   # 무청산 — 결과 = 배당 흐름(단일 배당탭 규약 동일)
        )

        # 절세액(P4 멀티): 계좌별 _finalize_account 필드 surface (무청산 규약은 루프가 일관 처리)
        if self._tax_enabled and result.account_results:
            accs = []
            for ar in result.account_results:
                assumed = float(ar.get("brokerage_assumed_tax", 0.0) or 0.0)
                saving = float(ar.get("tax_saving", 0.0) or 0.0)
                accs.append({
                    "account_id": ar.get("account_id"),
                    "type": ar.get("type"),
                    "brokerage_assumed_tax": assumed,
                    "actual_tax": float(ar.get("tax_paid", 0.0) or 0.0),
                    "tax_saving": saving,
                    "gain_harvest_saving": float(ar.get("gain_harvest_saving", 0.0) or 0.0),
                })
            self._last_savings = {"accounts": accs}

        return last_year_dividend(result.combined_history_df, end)

    # ── 합성 폴백: 계좌별 단일 합성의 케이스별 합 (G2 라우팅 미모델 근사) ──
    def _run_synthetic_rolling(self, seed, monthly, years, n_needed) -> List[float]:
        per_acct_params = []
        for idx, a in enumerate(self._accounts):
            s = float(seed) if idx == 0 else float(a.get("initial_capital", 0) or 0)
            m = float(monthly) if idx == 0 else float(a.get("monthly_contribution", 0) or 0)
            if self._child_stats[idx] is None:
                self._child_stats[idx] = self._children[idx]._calc_div_stats() or {}
            per_acct_params.append((s, m, self._child_stats[idx]))

        results = []
        for i in range(n_needed):
            total = 0.0
            for idx, (s, m, stats) in enumerate(per_acct_params):
                if not stats:
                    continue
                rng_i = np.random.default_rng(seed=i * 100 + idx)
                total += self._children[idx]._simulate_synthetic(s, m, years, stats, rng_i)
            if total > 0:
                results.append(total)
        return results

    # ── 절세 요약: 계좌별 p50 + 합산(계좌별 p50 단순합 — G5 규약) ──
    def get_savings_summary(self, seed, monthly, years):
        self._run_rolling(seed, monthly, years)
        years_n = max(1, int(round(float(years))))
        cache_key = f"{round(seed,-4)}_{round(monthly,-4)}_{years_n}"
        savings = self._savings_cache.get(cache_key) or []
        if not savings:
            return None
        n_acc = len(self._accounts)
        fields = ("brokerage_assumed_tax", "actual_tax", "tax_saving", "gain_harvest_saving")
        acc_out = []
        for k in range(n_acc):
            entry = {"account_id": k, "type": self._accounts[k]["type"]}
            for f in fields:
                vals = [s["accounts"][k][f] for s in savings if len(s.get("accounts", [])) > k]
                entry[f] = round(float(np.median(vals)), 2) if vals else 0.0
            acc_out.append(entry)
        combined = {f: round(sum(a[f] for a in acc_out), 2) for f in fields}
        if combined["brokerage_assumed_tax"] <= 0:
            return None
        return {
            "accounts": acc_out,
            "combined": combined,
            # 단일 패널 호환 필드(평탄화) — UI가 합산 3종을 그대로 읽음
            "brokerage_assumed_tax": combined["brokerage_assumed_tax"],
            "actual_tax": combined["actual_tax"],
            "tax_saving": round(combined["tax_saving"] + combined["gain_harvest_saving"], 2),
            "n_windows": len(savings),
        }
