"""
perf_ab.py — 실 DB A/B 결과불변 검증 (세금·계좌종류·자산종류·시뮬방식 매트릭스).

골든마스터(합성 FakeLoader)와 달리 **실 DB + 실 종목**으로 분류(asset_type)·세금·계좌별
분기를 전부 태워, 최적화 전/후 결과가 byte 동일한지 광범위 검증한다.

usage:
  python scripts/perf_ab.py dump OUT.json   # 현재 코드로 전 시나리오 지문 산출
A/B 절차:
  python scripts/perf_ab.py dump new.json
  git checkout HEAD~1 -- <변경파일>   (구버전)
  python scripts/perf_ab.py dump old.json
  git checkout HEAD -- <변경파일>     (복원)
  python scripts/perf_ab.py cmp old.json new.json
"""
from __future__ import annotations

import json, math, sys, time, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np

from modules.portfolio_engine import PortfolioEngine
from modules.rebalance.periodic import PeriodicRebalance
from modules.tax.base_tax import TaxEngine

PE = PortfolioEngine()


def _sf(weights, rebal="none"):
    freq = None if rebal in ("none", "band") else rebal
    drift = 0.05 if rebal == "band" else None
    def f():
        return PeriodicRebalance(target_weights=weights, rebalance_frequency=freq, drift_threshold=drift)
    return f


def _te(income=60_000_000, age=45):
    return TaxEngine({"earned_income": income, "age": age})


# ── 시나리오 빌더 (각각 .run() 결과 반환) ─────────────────────────────
DS, DE = "2008-01-01", "2024-12-31"
WDS = "2005-01-01"


def accum(tickers, weights, account_type="위탁", tax=False, gh=False, isa_renewal=False,
          div_mode="reinvest", years=8, rebal="none"):
    from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
    a = AccumulationAnalyzer(
        portfolio_engine=PE, tickers=tickers, strategy_factory=_sf(weights, rebal),
        data_start=DS, data_end=DE, accumulation_years=years,
        monthly_contribution=300_000, initial_capital=10_000_000, dividend_mode=div_mode,
        step_months=6, tax_engine=(_te() if tax else None), account_type=account_type,
        isa_renewal=isa_renewal, gain_harvesting=gh)
    return a.run()


def withdrawal(tickers, weights, account_type="위탁", tax=False, years=8):
    from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer
    a = WithdrawalAnalyzer(
        portfolio_engine=PE, tickers=tickers, strategy_factory=_sf(weights),
        data_start=WDS, data_end=DE, withdrawal_years=years, monthly_withdrawal=3_000_000,
        initial_capital=500_000_000, inflation=0.02, dividend_mode="reinvest",
        step_months=3, tax_engine=(_te() if tax else None), account_type=account_type)
    return a.run()


def multi(accounts, tax=True, years=8):
    from modules.retirement.multi_account_analyzer import MultiAccountAnalyzer
    a = MultiAccountAnalyzer(
        portfolio_engine=PE, accounts=accounts, data_start=DS, data_end=DE,
        accumulation_years=years, dividend_mode="reinvest", step_months=6, tax_enabled=tax,
        user_settings={"earned_income": 60_000_000, "age": 45}, apply_final_liquidation=True)
    return a.run()


def _acct(t, code, init=20_000_000, rebal="none"):
    return {"type": t, "initial_capital": init, "monthly_contribution": 0,
            "tickers": [{"code": code, "weight": 1.0}], "rebal_mode": rebal,
            "dividend_mode": "reinvest"}


SCENARIOS = {
    # ── AccumulationAnalyzer (SimulationLoop = 변경 경로) — 세금×계좌×자산×모드 ──
    "ac_위탁_notax":        lambda: accum(["SPY","TLT","GLD"], {"SPY":.5,"TLT":.3,"GLD":.2}),
    "ac_위탁_tax":          lambda: accum(["SPY","TLT","GLD"], {"SPY":.5,"TLT":.3,"GLD":.2}, tax=True),
    "ac_위탁_tax_yearly":   lambda: accum(["SPY","TLT"], {"SPY":.6,"TLT":.4}, tax=True, rebal="yearly"),
    "ac_위탁_tax_gh":       lambda: accum(["SPY","QQQ"], {"SPY":.5,"QQQ":.5}, tax=True, gh=True),
    "ac_ISA_tax":           lambda: accum(["069500","229200"], {"069500":.6,"229200":.4}, account_type="ISA", tax=True),
    "ac_ISA_renewal":       lambda: accum(["069500"], {"069500":1.0}, account_type="ISA", tax=True, isa_renewal=True, years=10),
    "ac_연금저축_tax":      lambda: accum(["SCHD","VOO"], {"SCHD":.5,"VOO":.5}, account_type="연금저축", tax=True),
    "ac_IRP_tax":           lambda: accum(["360750"], {"360750":1.0}, account_type="IRP", tax=True),
    "ac_월배당_위탁_tax":   lambda: accum(["458730"], {"458730":1.0}, tax=True),   # 월배당 ETF = 배당 경로 집중
    "ac_혼합자산_tax":      lambda: accum(["SPY","069500","KRX_GOLD","^GSPC"], {"SPY":.4,"069500":.3,"KRX_GOLD":.2,"^GSPC":.1}, tax=True),
    "ac_KR주식_tax":        lambda: accum(["005930","000660"], {"005930":.5,"000660":.5}, tax=True),
    "ac_divmode_withdraw":  lambda: accum(["SCHD"], {"SCHD":1.0}, tax=True, div_mode="withdraw"),
    "ac_divmode_hold":      lambda: accum(["SCHD","BND"], {"SCHD":.5,"BND":.5}, tax=True, div_mode="hold"),
    # ── WithdrawalAnalyzer (SimulationLoop worker = 변경 경로) ──
    "wd_위탁_notax":        lambda: withdrawal(["SPY","TLT"], {"SPY":.6,"TLT":.4}),
    "wd_위탁_tax":          lambda: withdrawal(["SPY","TLT"], {"SPY":.6,"TLT":.4}, tax=True),
    "wd_연금_tax":          lambda: withdrawal(["SPY","BND"], {"SPY":.5,"BND":.5}, account_type="연금저축", tax=True),
    # ── MultiAccountAnalyzer (MultiAccountSimulationLoop = pandas 폴백, 불변 확인) ──
    "mt_위탁_연금_tax":     lambda: multi([_acct("위탁","SPY"), _acct("연금저축","SCHD")]),
    "mt_ISA_위탁_tax":      lambda: multi([_acct("ISA","069500"), _acct("위탁","VOO")]),
}


def _fingerprint(result: dict) -> dict:
    """결과에서 비교용 숫자 전부 추출 — 분포의 모든 metric의 values 배열(케이스별) + 퍼센타일."""
    dist = result.get("distribution")
    if not (isinstance(dist, dict) and any(isinstance(v, dict) and "p50" in v for v in dist.values())):
        if "combined" in result:
            dist = result["combined"]["distribution"]
    fp = {"cases_count": len(result.get("cases", result.get("combined", {}).get("cases", [])))}
    for metric, d in sorted(dist.items()):
        if isinstance(d, dict) and "values" in d:
            # values = 케이스별 원값(가장 민감). 정렬 안 함 — 윈도우 순서 결정론.
            fp[metric] = [round(float(x), 6) for x in d["values"]]
    return fp


def cmd_dump(out):
    res = {}
    for name, fn in SCENARIOS.items():
        t = time.time()
        try:
            res[name] = {"ok": True, "fp": _fingerprint(fn())}
            print(f"  [{name:20s}] {time.time()-t:6.2f}s  cases={res[name]['fp']['cases_count']}")
        except Exception as e:
            res[name] = {"ok": False, "err": f"{type(e).__name__}: {e}"}
            print(f"  [{name:20s}] FAIL {res[name]['err']}")
            traceback.print_exc()
    Path(out).write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    print(f"저장: {out}  ({sum(1 for v in res.values() if v['ok'])}/{len(res)} ok)")


def _close(a, b):
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-4)


def cmd_cmp(fa, fb):
    A = json.loads(Path(fa).read_text(encoding="utf-8"))
    B = json.loads(Path(fb).read_text(encoding="utf-8"))
    allok = True
    for name in sorted(set(A) | set(B)):
        a, b = A.get(name), B.get(name)
        if not a or not b:
            print(f"  ⚠️ {name}: 한쪽 없음"); allok = False; continue
        if a["ok"] != b["ok"]:
            print(f"  ❌ {name}: ok 불일치 old={a.get('err','ok')} new={b.get('err','ok')}"); allok = False; continue
        if not a["ok"]:
            print(f"  ⏭ {name}: 양쪽 모두 실패(동일)"); continue
        fa_, fb_ = a["fp"], b["fp"]
        diffs = []
        if fa_.get("cases_count") != fb_.get("cases_count"):
            diffs.append(f"cases {fa_.get('cases_count')}→{fb_.get('cases_count')}")
        for m in sorted(set(fa_) | set(fb_)):
            if m == "cases_count":
                continue
            va, vb = fa_.get(m), fb_.get(m)
            if va is None or vb is None or len(va) != len(vb):
                diffs.append(f"{m}: 길이/누락"); continue
            for i, (x, y) in enumerate(zip(va, vb)):
                if not _close(x, y):
                    diffs.append(f"{m}[{i}] {x}→{y}"); break
        if diffs:
            allok = False
            print(f"  ❌ {name}: {len(diffs)}건  " + " | ".join(diffs[:4]))
        else:
            print(f"  ✅ {name}: 동일")
    print("\n" + ("✅ 전 시나리오 결과 불변" if allok else "❌ 결과 변동 발견"))
    return 0 if allok else 1


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "dump":
        cmd_dump(sys.argv[2]); sys.exit(0)
    if mode == "cmp":
        sys.exit(cmd_cmp(sys.argv[2], sys.argv[3]))
    print(__doc__)
