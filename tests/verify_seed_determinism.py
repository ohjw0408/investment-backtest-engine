"""
시드 결정화 검증 — 별도 프로세스에서 호출해 MC(가상데이터) 결과 지문을 출력.

사용:
  python tests/verify_seed_determinism.py "QQQ:0.5,SCHD:0.5"
출력: JSON {tickers, n_cases, fingerprint(md5), p50}

목적:
  - 같은 입력을 별도 프로세스 2회 → fingerprint 동일해야(프로세스 간 재현성 = 이번 픽스 핵심).
  - 종목 종류/개수 바꿔도 크래시 없이 지문 산출돼야.
"""
import sys, os, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calculator_logic import run_calculator_logic


def fingerprint(tickers_spec: str) -> dict:
    tickers = []
    for part in tickers_spec.split(","):
        code, w = part.split(":")
        tickers.append({"code": code.strip().upper(), "weight": float(w)})
    body = {
        "tickers": tickers,
        "initial_capital": 10_000_000,
        "monthly_contribution": 500_000,
        "years": 20,
        "rebal_mode": "yearly",
        "dividend_mode": "reinvest",
        "use_synthetic": True,   # 합성 윈도우 보충 강제 → 변경한 시드 코드 경유
    }
    res = run_calculator_logic(body)
    cases = res.get("cases", [])
    end_vals = sorted(round(c["end_value"]) for c in cases)
    fp = hashlib.md5(json.dumps(end_vals).encode()).hexdigest()
    dist = res.get("distribution", {}) or {}
    ev = dist.get("end_value_ratio", {}) or {}
    return {
        "tickers": tickers_spec,
        "n_cases": len(cases),
        "fingerprint": fp,
        "p50": ev.get("p50"),
    }


if __name__ == "__main__":
    spec = sys.argv[1] if len(sys.argv) > 1 else "QQQ:0.5,SCHD:0.5"
    print(json.dumps(fingerprint(spec)))
