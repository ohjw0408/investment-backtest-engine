"""
perf_golden.py — 성능 최적화 골든마스터 + 벤치 하니스.

목적(성능최적화_plan.md §3 선행 작업): 모든 최적화가 "같은 입력 → 같은 출력"임을
자동으로 증명하는 안전장치. 대표 입력별 분포 스냅샷을 저장(save)하고, 최적화 뒤
재실행(check)해 ±tol 내 동일함을 확인하면서 wall-time을 기록한다.

설계 핵심:
- DB·네트워크 0. 결정론적 합성 가격을 담은 가짜 로더(_FakeLoader)를 PortfolioEngine에
  주입해 **실제 PriceDataLoader.load / get_price 경로를 그대로** 구동한다. 따라서 P0(롤링
  윈도우 재로드 제거)가 load 경로를 바꿔도 출력이 변하면 즉시 잡힌다.
- 시나리오 BBB는 2000년부터 시작 → 윈도우 union/reindex/ffill 경계를 일부러 만든다
  (P0가 "전체 1회 로드 + 슬라이스"로 바꿀 때 가장 깨지기 쉬운 지점).
- 인출 시나리오는 윈도우 ≥ 30개 → 합성 패딩(RNG) 경로를 회피해 결정론 유지.

usage:
  python scripts/perf_golden.py save     # 골든 스냅샷 기록
  python scripts/perf_golden.py check    # 골든 대비 검증 + 타이밍
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")   # 한글 출력 깨짐 방지(Windows cp949)
except Exception:
    pass

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "tests" / "golden" / "perf_golden.json"

DATA_START = "1990-01-01"
DATA_END   = "2024-12-31"

# 분포 스냅샷에서 비교할 통계량(값 배열 대신 — 단일 케이스 변화도 mean/percentile을 흔든다).
STATS = ["mean", "std", "p10", "p25", "p50", "p75", "p90"]


# ════════════════════════════════════════════════════════════════════
# 결정론 합성 가격
# ════════════════════════════════════════════════════════════════════

def _build_frames() -> dict:
    """code -> 전체 일별 프레임(index=date, cols=ohlcv+dividend+split). 시드 고정."""
    bdays = pd.bdate_range(DATA_START, DATA_END)
    specs = {
        # code   seed  start          s0     mu        sigma   div(주당, 분기말)
        "AAA": (1, "1990-01-01", 100.0, 0.00030, 0.011, 0.4),
        "BBB": (2, "2000-01-03",  50.0, 0.00020, 0.016, 0.0),   # 늦은 시작 → 경계 커버
        "CCC": (3, "1990-01-01", 200.0, 0.00035, 0.009, 0.6),
    }
    frames = {}
    for code, (seed, start, s0, mu, sigma, divq) in specs.items():
        dates = bdays[bdays >= pd.Timestamp(start)]
        n = len(dates)
        rng = np.random.default_rng(seed)
        rets = rng.normal(mu, sigma, n)
        close = s0 * np.cumprod(1.0 + rets)

        div = np.zeros(n)
        if divq > 0:
            qkey = dates.year.values * 4 + dates.quarter.values
            is_qend = np.append(qkey[:-1] != qkey[1:], True)   # 각 분기 마지막 영업일
            div[is_qend] = divq

        df = pd.DataFrame(
            {"open": close, "high": close, "low": close, "close": close,
             "volume": 1000.0, "dividend": div, "split": 1.0},
            index=dates,
        )
        df.index.name = "date"
        frames[code] = df
    return frames


class _FakeLoader:
    """PriceLoader 대체 — get_price만 구현(reindex/ffill은 실 PriceDataLoader가 수행)."""

    def __init__(self, frames: dict):
        self.frames = frames

    def get_price(self, code, start_date, end_date, apply_fx=True, allow_synthetic=False):
        full = self.frames[code]
        s = pd.Timestamp(start_date)
        e = pd.Timestamp(end_date)
        sub = full.loc[(full.index >= s) & (full.index <= e)]
        # 실 get_price와 동일하게 'date' 컬럼을 가진 DataFrame 반환(NaN close 행은 애초에 없음).
        return sub.reset_index()


def _engine(frames: dict):
    from modules.portfolio_engine import PortfolioEngine
    return PortfolioEngine(loader=_FakeLoader(frames))


def _strategy_factory(target_weights, rebal_mode):
    from modules.rebalance.periodic import PeriodicRebalance
    if rebal_mode == "none":
        freq, drift = None, None
    elif rebal_mode == "band":
        freq, drift = None, 0.05
    else:
        freq, drift = rebal_mode, None

    def factory():
        return PeriodicRebalance(target_weights=target_weights,
                                 rebalance_frequency=freq, drift_threshold=drift)
    return factory


# ════════════════════════════════════════════════════════════════════
# 시나리오 (대표 입력 — P0/P1 핫스팟을 모두 경유)
# ════════════════════════════════════════════════════════════════════

def sc_accum_single(frames):
    """AccumulationAnalyzer: 1종목·월적립·무세금·재투자. (윈도우 재로드 핫스팟)"""
    from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
    a = AccumulationAnalyzer(
        portfolio_engine=_engine(frames), tickers=["AAA"],
        strategy_factory=_strategy_factory({"AAA": 1.0}, "none"),
        data_start=DATA_START, data_end=DATA_END,
        accumulation_years=15, monthly_contribution=300_000, initial_capital=10_000_000,
        dividend_mode="reinvest", step_months=3, tax_engine=None, account_type="위탁",
    )
    return a.run()


def sc_accum_dual_tax(frames):
    """AccumulationAnalyzer: 2종목(늦은시작 포함)·일시납·연1리밸·세금ON 위탁. (경계+세금)"""
    from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
    from modules.tax.base_tax import TaxEngine
    te = TaxEngine({"earned_income": 50_000_000, "age": 45})
    a = AccumulationAnalyzer(
        portfolio_engine=_engine(frames), tickers=["AAA", "BBB"],
        strategy_factory=_strategy_factory({"AAA": 0.6, "BBB": 0.4}, "yearly"),
        data_start=DATA_START, data_end=DATA_END,
        accumulation_years=12, monthly_contribution=0, initial_capital=50_000_000,
        dividend_mode="reinvest", step_months=3, tax_engine=te, account_type="위탁",
    )
    return a.run()


def sc_multi_2acct_tax(frames):
    """MultiAccountAnalyzer: 위탁+연금저축 2계좌·세금ON. (멀티계좌 윈도우 재로드 핫스팟)"""
    from modules.retirement.multi_account_analyzer import MultiAccountAnalyzer
    accounts = [
        {"type": "위탁", "initial_capital": 30_000_000, "monthly_contribution": 0,
         "tickers": [{"code": "AAA", "weight": 1.0}], "rebal_mode": "none",
         "dividend_mode": "reinvest"},
        {"type": "연금저축", "initial_capital": 20_000_000, "monthly_contribution": 0,
         "tickers": [{"code": "CCC", "weight": 1.0}], "rebal_mode": "yearly",
         "dividend_mode": "reinvest"},
    ]
    a = MultiAccountAnalyzer(
        portfolio_engine=_engine(frames), accounts=accounts,
        data_start=DATA_START, data_end=DATA_END, accumulation_years=12,
        dividend_mode="reinvest", step_months=3, tax_enabled=True,
        user_settings={"earned_income": 50_000_000, "age": 45},
        apply_final_liquidation=True,
    )
    return a.run()


def sc_withdrawal_single(frames):
    """WithdrawalAnalyzer: 1종목·인출·무세금. (모범 패턴 + P1-1 Pool 경로)"""
    from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer
    a = WithdrawalAnalyzer(
        portfolio_engine=_engine(frames), tickers=["CCC"],
        strategy_factory=_strategy_factory({"CCC": 1.0}, "none"),
        data_start=DATA_START, data_end=DATA_END, withdrawal_years=15,
        monthly_withdrawal=3_000_000, initial_capital=500_000_000, inflation=0.02,
        dividend_mode="reinvest", step_months=3, tax_engine=None,
    )
    return a.run()


SCENARIOS = {
    "accum_single":     sc_accum_single,
    "accum_dual_tax":   sc_accum_dual_tax,
    "multi_2acct_tax":  sc_multi_2acct_tax,
    "withdrawal_single": sc_withdrawal_single,
}


# ════════════════════════════════════════════════════════════════════
# 스냅샷 추출 / 비교
# ════════════════════════════════════════════════════════════════════

def _has_dist(d) -> bool:
    return isinstance(d, dict) and any(
        isinstance(v, dict) and "p50" in v for v in d.values()
    )


def _dist_and_n(result: dict):
    """분석기별 반환 형태에서 (주분포, 케이스수) 추출."""
    dist = result.get("distribution")
    if _has_dist(dist):
        # Accumulation / Withdrawal — distribution 키 명세가 분석기마다 다름(end_value vs end_value_ratio).
        return dist, len(result.get("cases", []))
    if "combined" in result and _has_dist(result["combined"].get("distribution")):
        return result["combined"]["distribution"], result.get(
            "cases_count", len(result.get("cases", [])))
    raise ValueError("알 수 없는 분석기 반환 형태")


def _snapshot(result: dict) -> dict:
    dist, n = _dist_and_n(result)
    snap = {"_n": n}
    for metric, d in dist.items():
        if isinstance(d, dict) and "p50" in d:
            snap[metric] = {s: float(d[s]) for s in STATS if s in d}
    return snap


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)


def _diff(golden: dict, current: dict) -> list:
    fails = []
    for metric, gv in golden.items():
        if metric == "_n":
            if gv != current.get("_n"):
                fails.append(f"_n {gv} -> {current.get('_n')}")
            continue
        cv = current.get(metric)
        if cv is None:
            fails.append(f"{metric} 누락")
            continue
        for stat, gx in gv.items():
            cx = cv.get(stat)
            if cx is None:
                fails.append(f"{metric}.{stat} 누락")
            elif not _close(gx, cx):
                fails.append(f"{metric}.{stat}  {gx:.6g} -> {cx:.6g}")
    return fails


# ════════════════════════════════════════════════════════════════════
# 실행
# ════════════════════════════════════════════════════════════════════

def _run_all(frames: dict) -> dict:
    out = {}
    for name, fn in SCENARIOS.items():
        t0 = time.perf_counter()
        result = fn(frames)
        wall = time.perf_counter() - t0
        out[name] = {"snapshot": _snapshot(result), "wall_s": round(wall, 3)}
        print(f"  [{name:18s}] n={out[name]['snapshot']['_n']:4d}  {wall:7.2f}s")
    return out


def cmd_save():
    frames = _build_frames()
    print("=== 골든 스냅샷 생성 ===")
    data = _run_all(frames)
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GOLDEN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {GOLDEN_PATH}")


def cmd_check():
    if not GOLDEN_PATH.exists():
        print(f"골든 없음: {GOLDEN_PATH}  먼저 `save` 실행.")
        return 2
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        golden = json.load(f)
    frames = _build_frames()
    print("=== 골든 대비 검증 ===")
    current = _run_all(frames)

    all_ok = True
    print("\n--- 결과 ---")
    for name in SCENARIOS:
        g = golden.get(name)
        c = current.get(name)
        if g is None:
            print(f"  [{name}] 골든에 없음 — 새 시나리오, save 필요")
            continue
        fails = _diff(g["snapshot"], c["snapshot"])
        gw, cw = g["wall_s"], c["wall_s"]
        speed = f"{gw:.2f}s -> {cw:.2f}s ({gw / cw:.2f}x)" if cw > 0 else f"{gw}s -> {cw}s"
        if fails:
            all_ok = False
            print(f"  ❌ {name:18s} 불일치 {len(fails)}건  | {speed}")
            for ln in fails[:12]:
                print(f"       {ln}")
        else:
            print(f"  ✅ {name:18s} 동일  | {speed}")

    print("\n" + ("✅ 전부 결과 불변 — 최적화 안전" if all_ok else "❌ 결과 변동 — 머지 금지"))
    return 0 if all_ok else 1


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "save":
        cmd_save()
        return 0
    if mode == "check":
        return cmd_check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
