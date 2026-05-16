"""
smoke_test.py
────────────────────────────────────────────────────────────────────────────────
세금 엔진 Smoke Test — 오류 없이 돌아가는지 확인

실행:
    cd 프로젝트_루트
    python tests/smoke_test.py

    # Flask 서버가 먼저 켜져 있어야 함
    # 기본 BASE_URL = http://127.0.0.1:5000

결과:
    각 케이스 PASS/FAIL 출력
    마지막에 전체 통계
────────────────────────────────────────────────────────────────────────────────
"""

import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import requests
except ImportError:
    print("requests 라이브러리 필요: pip install requests")
    sys.exit(1)

BASE_URL = "http://127.0.0.1:5000"

# ── 종목 정의 ──────────────────────────────────────────────
TICKERS = {
    "SPY":    "US_DIRECT    (해외 직접주식)",
    "360750": "KR_FOREIGN   (국내상장 해외ETF, TIGER 미국S&P500)",
    "069500": "KR_DOMESTIC  (국내주식 ETF, KODEX 200)",
    "005930": "KR_DOMESTIC  (국내 개별주식, 삼성전자)",
}

# ── 단일 계좌 ────────────────────────────────────────────
SINGLE_ACCOUNTS = ["위탁", "ISA", "연금저축", "IRP"]

# ── 복수 계좌 조합 ────────────────────────────────────────
MULTI_ACCOUNTS = [
    ["위탁", "ISA"],
    ["위탁", "연금저축"],
    ["위탁", "IRP"],
    ["ISA",  "연금저축"],
    ["ISA",  "IRP"],
    ["연금저축", "IRP"],
    ["위탁", "ISA", "연금저축"],
    ["위탁", "ISA", "IRP"],
    ["위탁", "연금저축", "IRP"],
    ["ISA",  "연금저축", "IRP"],
    ["위탁", "ISA", "연금저축", "IRP"],
]


def make_payload(ticker, account_type, isa_renewal=False):
    """단일 계좌 테스트 payload 생성."""
    return {
        "tickers":            [{"code": ticker, "weight": 1.0}],
        "initial_capital":    10_000_000,
        "monthly_contribution": 300_000,
        "years":              5,
        "rebal_mode":         "none",
        "band_width":         0.05,
        "dividend_mode":      "reinvest",
        "tax_enabled":        True,
        "account_type":       account_type,
        "isa_renewal":        isa_renewal,
        "user_settings": {
            "age":           40,
            "earned_income": 50_000_000,
            "isa_type":      "general",
        },
    }


def make_multi_payload(ticker, accounts, isa_renewal=False):
    """복수 계좌는 대표 계좌(첫번째)로 단일 시뮬 실행."""
    return make_payload(ticker, accounts[0], isa_renewal)


def call_api(payload):
    """API 호출 후 결과 반환."""
    try:
        resp = requests.post(
            f"{BASE_URL}/api/calculator/run",
            json=payload,
            timeout=120,
        )
        data = resp.json()
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}: {data.get('error', '?')}"
        if "error" in data:
            return False, f"error 필드: {data['error']}"
        if "cases" not in data or len(data["cases"]) == 0:
            return False, "cases 비어있음"
        if "distribution" not in data:
            return False, "distribution 없음"
        return True, f"cases={len(data['cases'])}"
    except requests.Timeout:
        return False, "TIMEOUT (120s 초과)"
    except Exception as e:
        return False, f"예외: {e}"


def run_tests():
    results = []
    total = 0

    print("=" * 70)
    print("Domino Invest 세금 엔진 Smoke Test")
    print(f"대상: {BASE_URL}")
    print("=" * 70)

    # ── 서버 연결 확인 ──
    try:
        requests.get(f"{BASE_URL}/", timeout=5)
    except Exception:
        print("❌ 서버에 연결할 수 없습니다. Flask 서버를 먼저 실행하세요.")
        sys.exit(1)

    # ─────────────────────────────────────────────────────────
    # 1. 단일 계좌 × 4종목
    # ─────────────────────────────────────────────────────────
    print("\n▶ [1] 단일 계좌 × 4종목")
    print("-" * 70)

    for ticker, t_desc in TICKERS.items():
        for account in SINGLE_ACCOUNTS:
            total += 1
            label  = f"[단일] {account:6s} × {ticker:6s}"
            ok, msg = call_api(make_payload(ticker, account))
            tag    = "✅" if ok else "❌"
            print(f"  {tag} {label:30s} {msg}")
            results.append((ok, label))

    # ─────────────────────────────────────────────────────────
    # 2. ISA 풍차돌리기 ON (ISA 포함 케이스만)
    # ─────────────────────────────────────────────────────────
    print("\n▶ [2] ISA 풍차돌리기 ON (SPY × ISA)")
    print("-" * 70)

    for ticker in ["SPY", "360750", "069500", "005930"]:
        total += 1
        label = f"[풍차] ISA × {ticker}"
        ok, msg = call_api(make_payload(ticker, "ISA", isa_renewal=True))
        tag = "✅" if ok else "❌"
        print(f"  {tag} {label:30s} {msg}")
        results.append((ok, label))

    # ─────────────────────────────────────────────────────────
    # 3. 세금 OFF (기준선 확인)
    # ─────────────────────────────────────────────────────────
    print("\n▶ [3] 세금 OFF 기준선 (SPY × 5년)")
    print("-" * 70)

    for ticker in TICKERS:
        total += 1
        payload = make_payload(ticker, "위탁")
        payload["tax_enabled"] = False
        label = f"[세금OFF] {ticker}"
        ok, msg = call_api(payload)
        tag = "✅" if ok else "❌"
        print(f"  {tag} {label:30s} {msg}")
        results.append((ok, label))

    # ─────────────────────────────────────────────────────────
    # 4. 복수 계좌 시뮬 (첫번째 계좌 대표)
    # ─────────────────────────────────────────────────────────
    print("\n▶ [4] 복수 계좌 조합 (SPY, 대표 계좌 각각)")
    print("-" * 70)

    for accounts in MULTI_ACCOUNTS:
        label_accts = "+".join(accounts)
        # 복수 계좌 — 각 계좌별로 개별 시뮬 실행
        all_ok = True
        msgs   = []
        for acc in accounts:
            total += 1
            ok, msg = call_api(make_payload("SPY", acc))
            if not ok:
                all_ok = False
            msgs.append(f"{acc}:{msg}")
            results.append((ok, f"[복수] {label_accts} → {acc}"))

        tag = "✅" if all_ok else "❌"
        print(f"  {tag} [{label_accts}]")
        if not all_ok:
            for m in msgs:
                print(f"       {m}")

    # ─────────────────────────────────────────────────────────
    # 5. 극단 케이스
    # ─────────────────────────────────────────────────────────
    print("\n▶ [5] 극단 케이스")
    print("-" * 70)

    edge_cases = [
        ("초기 0원",        {"initial_capital": 0, "monthly_contribution": 500_000}),
        ("월 납입 0원",     {"initial_capital": 10_000_000, "monthly_contribution": 0}),
        ("30년 장기",       {"years": 30}),
        ("나이 80세",       {"user_settings": {"age": 80, "earned_income": 0, "isa_type": "general"}}),
        ("고소득 종합과세",  {"user_settings": {"age": 40, "earned_income": 200_000_000, "isa_type": "preferential"}}),
    ]

    base = make_payload("SPY", "연금저축")
    for name, overrides in edge_cases:
        total += 1
        payload = {**base, **overrides}
        # user_settings는 dict merge 필요
        if "user_settings" in overrides:
            payload["user_settings"] = {**base["user_settings"], **overrides["user_settings"]}
        ok, msg = call_api(payload)
        tag = "✅" if ok else "❌"
        print(f"  {tag} {name:25s} {msg}")
        results.append((ok, name))

    # ─────────────────────────────────────────────────────────
    # 최종 결과
    # ─────────────────────────────────────────────────────────
    passed = sum(1 for ok, _ in results if ok)
    failed = len(results) - passed

    print("\n" + "=" * 70)
    print(f"결과: {passed}/{len(results)} PASS  ({failed} FAIL)")

    if failed > 0:
        print("\n❌ 실패 케이스:")
        for ok, label in results:
            if not ok:
                print(f"   - {label}")

    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)