"""
golden_master.py — 벡터화 회귀 게이트 (P0)
────────────────────────────────────────────────────────────────────────────────
4탭(투자계산기·포트폴리오 분석·은퇴·배당) 대표 시나리오의 현재 결과를 JSON으로 고정.
벡터화 등 엔진 변경 후 이 골든 대비 헤드라인 지표가 5% 이내(전 퍼센타일)인지 자동 확인.

  python tests/golden_master.py --generate   # 기준선 생성/갱신
  python tests/golden_master.py --check       # 기준선 대비 검증(5% 허용)

헤드라인 = cases 있으면 end_value p5/p25/p50/p75/p95, metrics 있으면 cagr/mdd/sharpe/
final, survival_rate, savings.tax_saving. fingerprint = 깊은 숫자 md5(완전 일치=결정성).
"""
import sys, os, json, hashlib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GOLDEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_master.json")
TOL = 0.05  # 5% 허용(부동소수 누적순서 차이)

_QS = [("p5", 5), ("p25", 25), ("p50", 50), ("p75", 75), ("p95", 95)]


def _runner(fn):
    if fn == "calculator":
        from calculator_logic import run_calculator_logic as f
    elif fn == "backtest":
        from backtest_logic import run_backtest_logic as f
    elif fn == "dividend":
        from dividend_logic import run_dividend_scenario_logic as f
    elif fn == "retirement":
        from retirement_logic import run_retirement_logic as f
    elif fn == "withdrawal":
        from retirement_logic import run_withdrawal_logic as f
    else:
        raise ValueError(fn)
    return f


def _deep_numbers(obj, out):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(round(float(obj), 4))
    elif isinstance(obj, dict):
        for k in sorted(obj.keys()):
            _deep_numbers(obj[k], out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _deep_numbers(v, out)


def headline(res: dict) -> dict:
    """결과 형태 무관 범용 헤드라인 스칼라."""
    h = {}
    cases = res.get("cases")
    evs = None
    if isinstance(cases, list) and cases:
        evs = [c.get("end_value") for c in cases if isinstance(c, dict) and c.get("end_value") is not None]
    elif isinstance(res.get("acc_values"), list) and res["acc_values"]:
        # 은퇴: 축적 단계 종료값 분포(MC)
        evs = [v for v in res["acc_values"] if v is not None]
    if evs:
        arr = np.array(evs, dtype=float)
        for name, q in _QS:
            h[f"endval_{name}"] = float(np.percentile(arr, q))
        h["n_cases"] = len(evs)
    m = res.get("metrics")
    if isinstance(m, dict):
        for k in ("cagr", "mdd", "sharpe", "final_value", "total_return"):
            if m.get(k) is not None:
                h[k] = float(m[k])
    if res.get("survival_rate") is not None:
        h["survival_rate"] = float(res["survival_rate"])
    sv = res.get("savings")
    if isinstance(sv, dict) and sv.get("tax_saving") is not None:
        h["tax_saving"] = float(sv["tax_saving"])
    return h


def fingerprint(res: dict) -> str:
    nums = []
    _deep_numbers(res, nums)
    return hashlib.md5(json.dumps(nums).encode()).hexdigest()


def _qq(c, w):
    return {"code": c, "weight": w}


SCENARIOS = [
    # 투자계산기 — 합성 ON, 매년 리밸
    {"id": "calc_synth_yearly", "fn": "calculator", "body": {
        "tickers": [_qq("QQQ", 0.6), _qq("SCHD", 0.4)],
        "initial_capital": 10_000_000, "monthly_contribution": 500_000,
        "years": 20, "rebal_mode": "yearly", "dividend_mode": "reinvest",
        "use_synthetic": True}},
    # 투자계산기 — 합성 OFF, 밴드 리밸, 세금 ISA
    {"id": "calc_nosynth_band_tax_isa", "fn": "calculator", "body": {
        "tickers": [_qq("069500", 0.5), _qq("360750", 0.5)],
        "initial_capital": 10_000_000, "monthly_contribution": 300_000,
        "years": 15, "rebal_mode": "band", "band_width": 0.05, "dividend_mode": "reinvest",
        "use_synthetic": False, "tax_enabled": True, "account_type": "ISA",
        "user_settings": {"earned_income": 50_000_000, "age": 40, "isa_type": "general"}}},
    # 포트폴리오 분석(백테) — 실측, 리밸 없음
    {"id": "backtest_real_none", "fn": "backtest", "body": {
        "tickers": [_qq("QQQ", 0.6), _qq("SCHD", 0.4)],
        "start_date": "2015-01-01", "end_date": "2023-12-31",
        "initial_capital": 10_000_000, "monthly_contribution": 0,
        "rebal_mode": "none", "dividend_mode": "reinvest"}},
    # 포트폴리오 분석(백테) — 세금 ON(위탁)
    {"id": "backtest_tax_taxable", "fn": "backtest", "body": {
        "tickers": [_qq("QQQ", 0.6), _qq("SCHD", 0.4)],
        "start_date": "2016-01-01", "end_date": "2023-12-31",
        "initial_capital": 10_000_000, "monthly_contribution": 200_000,
        "rebal_mode": "yearly", "dividend_mode": "reinvest",
        "tax_enabled": True, "account_type": "위탁",
        "user_settings": {"earned_income": 50_000_000, "age": 40}}},
    # 은퇴 — 축적→인출, 합성 ON
    {"id": "retire_accum_synth", "fn": "retirement", "body": {
        "tickers": [_qq("QQQ", 0.6), _qq("SCHD", 0.4)],
        "initial_capital": 10_000_000, "monthly_contribution": 500_000,
        "accumulation_years": 20, "monthly_withdrawal": 3_000_000,
        "withdrawal_years": 30, "dividend_mode": "reinvest", "rebal_mode": "none",
        "use_synthetic": True}},
    # 은퇴 인출 — 합성 경로
    {"id": "withdraw_spy", "fn": "withdrawal", "body": {
        "tickers": [_qq("SPY", 1.0)],
        "initial_capital": 500_000_000, "monthly_withdrawal": 3_000_000,
        "withdrawal_years": 30, "dividend_mode": "reinvest", "rebal_mode": "none"}},
    # 배당 — 확률 모드 + 절세(ISA)
    {"id": "dividend_prob_isa", "fn": "dividend", "body": {
        "tickers": [_qq("360750", 1.0)],
        "target_monthly_div": 1_000_000, "probability": 0.5,
        "account_type": "isa",
        "user_settings": {"earned_income": 50_000_000, "age": 40, "isa_type": "general"},
        "seed": {"center": 20_000_000, "step": 0, "n": 0, "mode": "fixed"},
        "monthly": {"center": 0, "step": 0, "n": 0, "mode": "fixed"},
        "years": {"center": 20, "step": 0, "n": 0, "mode": "fixed"}}},
]


def run_all() -> dict:
    out = {}
    for sc in SCENARIOS:
        f = _runner(sc["fn"])
        try:
            res = f(dict(sc["body"]))
            out[sc["id"]] = {"ok": True, "headline": headline(res), "fingerprint": fingerprint(res)}
            print(f"  [ok] {sc['id']}")
        except Exception as e:
            out[sc["id"]] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            print(f"  [FAIL] {sc['id']} - {type(e).__name__}: {e}")
    return out


def _within_tol(a, b):
    if a is None or b is None:
        return a == b
    if b == 0:
        return abs(a) < 1.0
    return abs(a - b) / abs(b) <= TOL


def cmd_generate():
    print("골든 마스터 생성:")
    data = run_all()
    with open(GOLDEN_PATH, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)
    print(f"\n저장 → {GOLDEN_PATH} ({len([v for v in data.values() if v.get('ok')])}/{len(data)} ok)")


def cmd_check():
    if not os.path.exists(GOLDEN_PATH):
        print("골든 없음 — 먼저 --generate"); sys.exit(2)
    with open(GOLDEN_PATH, encoding="utf-8") as fp:
        golden = json.load(fp)
    print("골든 대비 검증:")
    cur = run_all()
    fails = []
    for sid, g in golden.items():
        c = cur.get(sid)
        if not c:
            fails.append(f"{sid}: 현재 결과 없음"); continue
        if not g.get("ok") or not c.get("ok"):
            if g.get("ok") != c.get("ok"):
                fails.append(f"{sid}: ok 불일치 g={g.get('ok')} c={c.get('ok')}")
            continue
        exact = g.get("fingerprint") == c.get("fingerprint")
        for k, gv in g["headline"].items():
            cv = c["headline"].get(k)
            if not _within_tol(cv, gv):
                fails.append(f"{sid}.{k}: {cv} vs golden {gv} (>{TOL:.0%})")
        print(f"  {sid}: {'완전일치' if exact else '5%이내'}")
    if fails:
        print("\n[REGRESSION]:")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("\n[PASS] all scenarios within golden")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if mode == "--generate":
        cmd_generate()
    else:
        cmd_check()
