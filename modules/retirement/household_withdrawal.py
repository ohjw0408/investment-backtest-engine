"""가구 인출 오케스트레이터 (G5-C C3).

월 1회, 가구 단일 인출액(net 생활비)을 여러 계좌에 걸쳐 세금최적 순서로 소진한다.

오너 결정:
- Q2 인출 순서 = 위탁 → ISA → 연금/IRP (과세 적은 계좌 먼저 소진, 연금 과세이연 최대 유지).
  같은 유형 다계좌는 account_id(인덱스) 순.
- Q3 연금소득세 = 개인 합산(전 연금/IRP 인출 net 합)으로 1500만 판정 →
  `TaxEngine.pension_separate_tax_annual`(1500 이하 나이별 3.3~5.5%, 초과 전액 16.5%).

위탁/ISA: net `d`를 인출하면 `d`가 포트폴리오를 떠남. CG세는 `sell_with_tax`가 별도 차감
  (BUG-TAX-2 — 위탁 인출 매도차익 양도세). 즉 계좌는 d + CG세 만큼 감소.
연금/IRP: 가구에 net `d`를 주려면 gross = d/(1-rate)를 인출(차액 = 연금소득세).

단일 계좌(WithdrawalEngine)와 동일 매도 메커니즘을 재사용 → 단일 == 멀티 1계좌 정합.
인플레이션·월 게이팅은 호출자(분석기)가 관리 — net_need는 이미 inflation 반영된 값으로 받는다.
"""
from modules.simulation.withdrawal_engine import WithdrawalEngine

_PENSION_TYPES = ("연금저축", "IRP")
_EPS = 1e-6


def _priority(account_type: str) -> int:
    if account_type == "위탁":
        return 0
    if account_type == "ISA":
        return 1
    return 2  # 연금저축 / IRP


def _ordered(accounts):
    return sorted(accounts, key=lambda a: (_priority(a["type"]), a["account_id"]))


def household_withdraw(
    accounts,
    net_need: float,
    price_dict: dict,
    date,
    *,
    tax_engine=None,
    age: int = 65,
) -> dict:
    """가구 월 인출 1회 실행. 포트폴리오를 변형(mutate)한다.

    accounts: [{account_id, type, portfolio, executor, target_weights}, ...]
    net_need: 가구 월 net 인출액(인플레이션 반영 완료).
    반환: {delivered_net, shortfall, depleted, pension_rate, per_account:[...]}.
    """
    we = WithdrawalEngine()
    remaining = float(net_need)
    per_account: list[dict] = []

    pension_accounts = [a for a in accounts if a["type"] in _PENSION_TYPES]
    nonpension = [a for a in _ordered(accounts) if a["type"] not in _PENSION_TYPES]
    pension_accounts = _ordered(pension_accounts)

    # ── 1차: 위탁 → ISA (net = 인출액, CG세 별도) ──────────────────
    for acct in nonpension:
        if remaining <= _EPS:
            break
        pf = acct["portfolio"]
        cap = pf.total_value(price_dict)
        take = min(remaining, cap)
        if take <= _EPS:
            continue
        we.process(
            pf, take, price_dict, acct["target_weights"],
            date=date, last_month=None, elapsed_months=0,
            inflation=0.0, executor=acct.get("executor"),
        )
        remaining -= take
        per_account.append({
            "account_id":   acct["account_id"],
            "type":         acct["type"],
            "withdrawn_net": round(take, 2),
            "pension_tax":  0.0,
        })

    # ── 2차: 연금/IRP (gross-up, 개인 합산 분리과세) ─────────────────
    pension_rate = 0.0
    if remaining > _EPS and pension_accounts:
        # 1500만 판정용 연 추정 = 이번달 연금 충당 net × 12 (단일계좌 _calc_gross_withdrawal 동형).
        annual_proxy = remaining * 12.0
        if tax_engine is not None and annual_proxy > 0:
            tax = tax_engine.pension_separate_tax_annual(annual_proxy, age)
            pension_rate = tax / annual_proxy if annual_proxy > 0 else 0.0
        for acct in pension_accounts:
            if remaining <= _EPS:
                break
            pf = acct["portfolio"]
            tv = pf.total_value(price_dict)
            net_cap = tv * (1.0 - pension_rate)
            take_net = min(remaining, net_cap)
            if take_net <= _EPS:
                continue
            gross = take_net / (1.0 - pension_rate) if pension_rate < 1.0 else take_net
            we.process(
                pf, gross, price_dict, acct["target_weights"],
                date=date, last_month=None, elapsed_months=0,
                inflation=0.0, executor=acct.get("executor"),
            )
            remaining -= take_net
            per_account.append({
                "account_id":    acct["account_id"],
                "type":          acct["type"],
                "withdrawn_net": round(take_net, 2),
                "pension_tax":   round(gross - take_net, 2),
            })

    shortfall = max(0.0, remaining)
    return {
        "delivered_net": round(net_need - shortfall, 2),
        "shortfall":     round(shortfall, 2),
        "depleted":      shortfall > _EPS,
        "pension_rate":  round(pension_rate, 6),
        "per_account":   per_account,
    }
