"""
E2E API Test — investment-backtest-engine
Usage:
    python e2e_test.py                                      # 기본: moneymilestone.co.kr
    python e2e_test.py http://localhost:5000                # 로컬
    python e2e_test.py http://216.128.152.205               # 서버 IP 직접
"""

import sys
import time
import json
import requests

# Windows CP949 터미널 대응
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://moneymilestone.co.kr"
POLL_INTERVAL = 3       # seconds between polls
ASYNC_TIMEOUT = 300     # 5 minutes

RESULTS: list[dict] = []

# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

def log(label: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    mark   = "OK" if passed else "NG"
    msg    = f"  [{mark}] {label}"
    if detail:
        msg += f"\n         → {detail}"
    print(msg)
    RESULTS.append({"label": label, "passed": passed, "detail": detail})


def post(path: str, payload: dict, timeout: int = 30) -> requests.Response:
    return requests.post(f"{BASE_URL}{path}", json=payload, timeout=timeout)


def poll_task(task_id: str) -> dict:
    """task_id 완료까지 폴링. SUCCESS → result dict, FAILURE → raises."""
    deadline = time.time() + ASYNC_TIMEOUT
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/task/{task_id}", timeout=10)
        r.raise_for_status()
        data = r.json()
        state = data.get("status")
        if state == "SUCCESS":
            return data.get("result") or data
        if state == "FAILURE":
            raise RuntimeError(data.get("error", "task FAILURE"))
        pct = data.get("percent", 0)
        pos = data.get("queue_pos")
        if pos is not None:
            print(f"         … 대기중 (queue #{pos})")
        else:
            print(f"         … {pct:.0f}%")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"task {task_id} 미완료 ({ASYNC_TIMEOUT}s 초과)")


def run_async(path: str, payload: dict) -> dict:
    """submit → task_id → poll → result"""
    r = post(path, payload)
    r.raise_for_status()
    body = r.json()
    task_id = body.get("task_id")
    if not task_id:
        raise ValueError(f"task_id 없음: {body}")
    print(f"         task_id={task_id}")
    return poll_task(task_id)


# ──────────────────────────────────────────────
# 공통 페이로드
# ──────────────────────────────────────────────

TICKERS_SPY = [{"code": "SPY", "weight": 1.0}]
TICKERS_MIX = [
    {"code": "SPY", "weight": 0.6},
    {"code": "QQQ", "weight": 0.4},
]

CALC_PAYLOAD = {
    "tickers":              TICKERS_SPY,
    "initial_capital":      10_000_000,
    "monthly_contribution": 300_000,
    "years":                10,
    "rebal_mode":           "none",
    "dividend_mode":        "reinvest",
    "tax_enabled":          False,
}

# 동기 /run용 — gunicorn 30s 타임아웃 안에 들어오도록 years 줄임
CALC_PAYLOAD_SYNC = {**CALC_PAYLOAD, "years": 3}

RETIREMENT_PAYLOAD = {
    "tickers":              TICKERS_SPY,
    "initial_capital":      5_000_000,
    "monthly_contribution": 300_000,
    "accumulation_years":   20,
    "monthly_withdrawal":   2_000_000,
    "withdrawal_years":     20,
    "dividend_mode":        "reinvest",
    "rebal_mode":           "none",
    "inflation":            0.02,
    "target_percentile":    0.90,
    "tax_enabled":          False,
}

WITHDRAWAL_PAYLOAD = {
    "tickers":             TICKERS_SPY,
    "initial_capital":     300_000_000,
    "monthly_withdrawal":  2_000_000,
    "withdrawal_years":    20,
    "inflation":           0.02,
    "dividend_mode":       "reinvest",
    "rebal_mode":          "none",
    "target_percentile":   0.90,
    "tax_enabled":         False,
}

# 동기 /probability 용 — seed/monthly/years 가 plain 숫자
DIVIDEND_PAYLOAD = {
    "tickers":            TICKERS_SPY,
    "seed":               50_000_000,
    "monthly":            500_000,
    "years":              15,
    "target_monthly_div": 1_000_000,
    "dividend_mode":      "payout",
}

# 비동기 /submit 용 — run_dividend_scenario_logic 은 seed/monthly/years 를 config dict 로 받음
DIVIDEND_PAYLOAD_ASYNC = {
    "tickers":            TICKERS_SPY,
    "seed":    {"center": 50_000_000, "step": 0, "n": 0, "mode": "fixed"},
    "monthly": {"center": 500_000,    "step": 0, "n": 0, "mode": "fixed"},
    "years":   {"center": 15,         "step": 0, "n": 0, "mode": "fixed"},
    "target_monthly_div": 1_000_000,
    "dividend_mode":      "payout",
    "probability":        0.90,
}

BACKTEST_PAYLOAD = {
    "tickers":              TICKERS_MIX,
    "start_date":           "2015-01-01",
    "end_date":             "2024-12-31",
    "initial_capital":      10_000_000,
    "monthly_contribution": 0,
    "dividend_mode":        "reinvest",
    "rebal_mode":           "annual",
    "tax_enabled":          False,
}


# ──────────────────────────────────────────────
# 테스트 함수
# ──────────────────────────────────────────────

def test_health():
    """서버 응답 기본 확인"""
    label = "서버 헬스 (GET /)"
    try:
        r = requests.get(f"{BASE_URL}/", timeout=10)
        passed = r.status_code == 200
        log(label, passed, f"HTTP {r.status_code}")
    except Exception as e:
        log(label, False, str(e))


def test_calculator_async():
    """투자 계산기 비동기 (/api/calculator/submit → poll)"""
    label = "투자 계산기 (비동기)"
    try:
        result = run_async("/api/calculator/submit", CALC_PAYLOAD)
        cases_count = result.get("cases_count", 0) if result else 0
        dist = result.get("distribution") if result else None
        passed = cases_count > 0 and dist is not None
        log(label, passed, f"cases={cases_count}, dist keys={list(dist.keys())[:4] if dist else None}")
    except Exception as e:
        log(label, False, str(e))


def test_calculator_sync():
    """투자 계산기 동기 (/api/calculator/run) — years=3으로 gunicorn 30s 타임아웃 회피"""
    label = "투자 계산기 (동기, /run)"
    try:
        r = post("/api/calculator/run", CALC_PAYLOAD_SYNC, timeout=30)
        data = r.json()
        passed = r.status_code == 200 and data.get("cases_count", 0) > 0
        log(label, passed, f"HTTP {r.status_code}, cases={data.get('cases_count')}")
    except Exception as e:
        log(label, False, str(e))


def test_retirement_async():
    """은퇴 설계 축적+인출 통합 (/api/retirement/submit → poll)"""
    label = "은퇴 설계 축적기 (비동기)"
    try:
        result = run_async("/api/retirement/submit", RETIREMENT_PAYLOAD)
        acc_count = result.get("acc_cases_count", 0) if result else 0
        summary   = result.get("combined_summary") if result else None
        passed    = acc_count > 0 and summary is not None
        log(label, passed, f"acc_cases={acc_count}, summary keys={list(summary.keys())[:4] if summary else None}")
    except Exception as e:
        log(label, False, str(e))


def test_withdrawal_async():
    """은퇴 인출기 (비동기, _withdrawal_only=True)"""
    label = "은퇴 설계 인출기 (비동기)"
    payload = {**WITHDRAWAL_PAYLOAD, "_withdrawal_only": True}
    try:
        result = run_async("/api/retirement/submit", payload)
        # submit with _withdrawal_only goes through retirement task
        # result may be the withdrawal result dict
        passed = result is not None and isinstance(result, dict)
        keys   = list(result.keys())[:5] if result else []
        log(label, passed, f"result keys={keys}")
    except Exception as e:
        log(label, False, str(e))


def test_withdrawal_sync():
    """은퇴 인출기 동기 (/api/retirement/withdrawal)"""
    label = "은퇴 설계 인출기 (동기, /withdrawal)"
    try:
        r = post("/api/retirement/withdrawal", WITHDRAWAL_PAYLOAD, timeout=120)
        data   = r.json()
        rate   = data.get("survival_rate")
        passed = r.status_code == 200 and rate is not None
        log(label, passed, f"HTTP {r.status_code}, survival_rate={rate}")
    except Exception as e:
        log(label, False, str(e))


def test_dividend_probability():
    """배당금 계산기 (/api/dividend-target/probability) — 동기"""
    label = "배당금 계산기 (동기)"
    try:
        r = post("/api/dividend-target/probability", DIVIDEND_PAYLOAD, timeout=120)
        data  = r.json()
        prob  = data.get("probability")
        passed = r.status_code == 200 and prob is not None
        log(label, passed, f"HTTP {r.status_code}, probability={prob}")
    except Exception as e:
        log(label, False, str(e))


def test_dividend_async():
    """배당금 계산기 비동기 (/api/dividend-target/submit → poll)
    seed/monthly/years 는 scenario config dict 형식"""
    label = "배당금 계산기 (비동기)"
    try:
        result = run_async("/api/dividend-target/submit", DIVIDEND_PAYLOAD_ASYNC)
        # run_scenario 결과: dict with various keys (no single 'probability' key)
        passed = isinstance(result, dict) and len(result) > 0
        keys   = list(result.keys())[:5] if result else []
        log(label, passed, f"result keys={keys}")
    except Exception as e:
        log(label, False, str(e))


def test_backtest_submit():
    """포트폴리오 분석 비동기 (/api/backtest/submit → poll)"""
    label = "포트폴리오 분석 (비동기)"
    try:
        result  = run_async("/api/backtest/submit", BACKTEST_PAYLOAD)
        metrics = result.get("metrics") if result else None
        passed  = metrics is not None and "cagr" in metrics
        log(label, passed, f"metrics={metrics}")
    except Exception as e:
        log(label, False, str(e))


def test_backtest_run():
    """포트폴리오 분석 동기 (/api/backtest/run)"""
    label = "포트폴리오 분석 (동기, /run)"
    try:
        r      = post("/api/backtest/run", BACKTEST_PAYLOAD, timeout=120)
        data   = r.json()
        metrics = data.get("metrics")
        passed  = r.status_code == 200 and metrics is not None and "cagr" in metrics
        log(label, passed, f"HTTP {r.status_code}, cagr={metrics.get('cagr') if metrics else None}")
    except Exception as e:
        log(label, False, str(e))


def test_error_handling():
    """에러 처리 — 잘못된 페이로드 → 4xx or error 필드"""
    label = "에러 처리 (빈 tickers)"
    try:
        r = post("/api/calculator/run", {"tickers": [], "initial_capital": 0,
                                         "monthly_contribution": 0, "years": 1,
                                         "rebal_mode": "none", "dividend_mode": "reinvest"},
                 timeout=30)
        data   = r.json()
        passed = r.status_code in (400, 500) or "error" in data
        log(label, passed, f"HTTP {r.status_code}, error='{data.get('error', '')[:60]}'")
    except Exception as e:
        log(label, False, str(e))


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

TESTS = [
    ("헬스 체크",              test_health),
    ("투자 계산기 [비동기]",   test_calculator_async),
    ("투자 계산기 [동기]",     test_calculator_sync),
    ("은퇴 축적기 [비동기]",   test_retirement_async),
    ("은퇴 인출기 [비동기]",   test_withdrawal_async),
    ("은퇴 인출기 [동기]",     test_withdrawal_sync),
    ("배당금 계산기 [동기]",   test_dividend_probability),
    ("배당금 계산기 [비동기]", test_dividend_async),
    ("포트폴리오 분석 [비동기]", test_backtest_submit),
    ("포트폴리오 분석 [동기]", test_backtest_run),
    ("에러 처리",              test_error_handling),
]


def main():
    print(f"\n{'='*55}")
    print(f"  E2E TEST  --  {BASE_URL}")
    print(f"{'='*55}\n")

    start = time.time()
    for group, fn in TESTS:
        print(f"[ {group} ]")
        fn()
        print()

    elapsed = time.time() - start
    passed  = sum(1 for r in RESULTS if r["passed"])
    total   = len(RESULTS)
    failed  = total - passed

    print(f"{'='*55}")
    print(f"  결과: {passed}/{total} PASS  |  {failed} FAIL  |  {elapsed:.1f}s")
    print(f"{'='*55}")

    if failed:
        print("\n실패 목록:")
        for r in RESULTS:
            if not r["passed"]:
                print(f"  [NG] {r['label']}")
                if r["detail"]:
                    print(f"    {r['detail']}")
        sys.exit(1)
    else:
        print("\n모든 테스트 통과.")
        sys.exit(0)


if __name__ == "__main__":
    main()
