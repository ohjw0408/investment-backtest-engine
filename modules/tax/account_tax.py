"""
modules/tax/account_tax.py
────────────────────────────────────────────────────────────────────────────────
계좌별 세금 규칙 상수 + TaxedDividendEngine (DividendEngine 래퍼)
"""

from __future__ import annotations


# ── 계좌별 납입/공제 한도 ─────────────────────────────────────
ACCOUNT_LIMITS = {
    "위탁": {
        "annual_limit":       None,
        "deduction_limit":    0,
        "risky_asset_limit":  1.0,
    },
    "ISA": {
        "annual_limit":       20_000_000,
        "total_limit":        100_000_000,
        "lock_years":         3,
        "deduction_limit":    0,
        "risky_asset_limit":  1.0,
    },
    "연금저축": {
        "annual_limit":       18_000_000,   # IRP 합산 한도
        "deduction_limit":    6_000_000,    # 단독 세액공제 한도
        "combined_deduction": 9_000_000,    # IRP 합산 세액공제 한도
        "risky_asset_limit":  1.0,
    },
    "IRP": {
        "annual_limit":       18_000_000,   # 연금저축 합산 한도
        "deduction_limit":    9_000_000,    # 합산 세액공제 한도
        "risky_asset_limit":  0.70,         # 위험자산 최대 70%
    },
}


# ── 경고 메시지 생성 ─────────────────────────────────────────

def check_contribution_limits(accounts: list[dict]) -> list[str]:
    """
    복수 계좌 납입액 한도 검증.
    경고 메시지 리스트 반환.
    """
    warnings = []

    # 연금저축 + IRP 합산 연납입
    pension_annual = sum(
        a.get("monthly_contribution", 0) * 12
        for a in accounts if a["type"] == "연금저축"
    )
    irp_annual = sum(
        a.get("monthly_contribution", 0) * 12
        for a in accounts if a["type"] == "IRP"
    )
    combined_annual = pension_annual + irp_annual
    if combined_annual > 18_000_000:
        warnings.append(
            f"연금저축+IRP 연간 납입 합계 {combined_annual:,.0f}원이 "
            f"납입한도 1,800만원을 초과합니다."
        )

    # 세액공제 한도 초과 경고
    combined_deductible = min(pension_annual, 6_000_000) + irp_annual
    if combined_deductible > 9_000_000:
        warnings.append(
            f"연금저축+IRP 세액공제 한도(900만원) 초과분 "
            f"{combined_deductible-9_000_000:,.0f}원은 공제 불가합니다."
        )

    # ISA 연납입 한도
    for a in accounts:
        if a["type"] == "ISA":
            isa_annual = a.get("monthly_contribution", 0) * 12
            if isa_annual > 20_000_000:
                warnings.append(
                    f"ISA 연간 납입 {isa_annual:,.0f}원이 "
                    f"납입한도 2,000만원을 초과합니다."
                )

    return warnings


_ISA_ANNUAL_LIMIT = 20_000_000


def validate_isa_contribution(initial: float, monthly: float) -> list[str]:
    """
    ISA 납입 규칙 하드 체크.
    - 초기 납입 > 2,000만 → 오류
    - 월 납입 > (2,000만 - initial) / 12 → 오류
    위반 시 오류 메시지 리스트 반환. 빈 리스트면 유효.
    """
    errors: list[str] = []
    initial = float(initial or 0.0)
    monthly = float(monthly or 0.0)

    if initial > _ISA_ANNUAL_LIMIT:
        errors.append(
            f"ISA 초기 납입금 {initial:,.0f}원이 연간 납입 한도(2,000만원)를 초과합니다. "
            f"ISA는 개설 후 연간 최대 2,000만원까지만 납입 가능합니다."
        )
        return errors

    annual_remaining = _ISA_ANNUAL_LIMIT - initial
    monthly_max = annual_remaining / 12
    if monthly > monthly_max:
        errors.append(
            f"ISA 월 납입금 {monthly:,.0f}원이 가능한 한도({monthly_max:,.0f}원)를 초과합니다. "
            f"연간 한도 2,000만원에서 초기 납입금 {initial:,.0f}원을 제외한 "
            f"잔여 {annual_remaining:,.0f}원을 12개월로 나눈 값입니다."
        )
    return errors


# ── 계좌별 투자 제약 검증 ────────────────────────────────────

def validate_account_portfolio(
    account_type: str,
    tickers: list[str],
    weights: dict[str, float],
    tax_engine,
) -> dict:
    """
    계좌 유형별 투자 가능 종목 제약 검증.

    규칙:
      위탁   : 제한 없음
      ISA    : 해외 직접 상장(US_DIRECT) 금지
      연금저축 : US_DIRECT·개별주식·레버리지/인버스 ETF 금지
      IRP    : US_DIRECT·개별주식·레버리지/인버스 ETF 금지 + 위험자산 ≤ 70%

    Returns
    -------
    {"valid": bool, "violations": list[str], "disclaimer": str | None}
    """
    if account_type == "위탁":
        return {"valid": True, "violations": [], "disclaimer": None}

    violations: list[str] = []
    disclaimer: str | None = None

    for ticker in tickers:
        market = tax_engine.classify_asset(ticker)          # KR_DOMESTIC | KR_FOREIGN | US_DIRECT | KRX_GOLD
        inst   = tax_engine.classify_instrument_type(ticker) # ETF | STOCK | LEVERAGED_ETF | INVERSE_ETF | UNKNOWN

        # KRX 금현물은 금현물계좌(위탁) 전용 — ISA·연금·IRP 매수 불가.
        if market == "KRX_GOLD":
            violations.append(
                f"KRX 금현물({ticker})은 금현물 계좌(위탁)에서만 매수할 수 있습니다. "
                f"ISA·연금·IRP에선 보유 불가 — 금현물 ETF(예: ACE KRX금현물)를 이용하세요."
            )
            continue

        if account_type == "ISA":
            if market == "US_DIRECT":
                violations.append(
                    f"ISA 계좌는 해외 직접 상장 종목({ticker})을 보유할 수 없습니다. "
                    f"국내 상장 ETF(예: TIGER 미국S&P500)를 이용하세요."
                )

        elif account_type == "연금저축":
            if market == "US_DIRECT":
                violations.append(
                    f"연금저축 계좌는 해외 직접 상장 종목({ticker})을 보유할 수 없습니다. "
                    f"국내 상장 ETF를 이용하세요."
                )
            elif inst == "STOCK":
                violations.append(
                    f"연금저축 계좌는 개별주식({ticker})을 보유할 수 없습니다. ETF만 투자 가능합니다."
                )
            elif inst == "LEVERAGED_ETF":
                violations.append(
                    f"연금저축 계좌는 레버리지 ETF({ticker})를 보유할 수 없습니다."
                )
            elif inst == "INVERSE_ETF":
                violations.append(
                    f"연금저축 계좌는 인버스 ETF({ticker})를 보유할 수 없습니다."
                )

        elif account_type == "IRP":
            if market == "US_DIRECT":
                violations.append(
                    f"IRP 계좌는 해외 직접 상장 종목({ticker})을 보유할 수 없습니다. "
                    f"국내 상장 ETF를 이용하세요."
                )
            elif inst == "STOCK":
                violations.append(
                    f"IRP 계좌는 개별주식({ticker})을 보유할 수 없습니다. ETF만 투자 가능합니다."
                )
            elif inst == "LEVERAGED_ETF":
                violations.append(
                    f"IRP 계좌는 레버리지 ETF({ticker})를 보유할 수 없습니다."
                )
            elif inst == "INVERSE_ETF":
                violations.append(
                    f"IRP 계좌는 인버스 ETF({ticker})를 보유할 수 없습니다."
                )
            elif inst == "COMMODITY_ETF":
                violations.append(
                    f"IRP 계좌는 원자재 ETF({ticker})를 보유할 수 없습니다. "
                    f"주식형·채권형 ETF만 투자 가능합니다."
                )

    # IRP 위험자산 70% 한도 추가 검증
    if account_type == "IRP" and not violations:
        irp_result = tax_engine.validate_irp_weights(weights)
        disclaimer = irp_result.get("disclaimer")
        if not irp_result["valid"]:
            violations.append(irp_result["warning"])

    return {
        "valid":      len(violations) == 0,
        "violations": violations,
        "disclaimer": disclaimer,
    }


# ── TaxedDividendEngine ──────────────────────────────────────

class TaxedDividendEngine:
    """
    기존 DividendEngine을 래핑하여 세금 적용.
    SimulationLoop의 dividend_engine 자리에 교체해서 사용.

    Parameters
    ----------
    base_engine  : 기존 DividendEngine 인스턴스
    tax_engine   : TaxEngine 인스턴스
    account_type : '위탁' | 'ISA' | '연금저축' | 'IRP'
    """

    def __init__(self, base_engine, tax_engine, account_type: str,
                 other_financial_income: float = 0.0, session=None):
        self.base_engine  = base_engine
        self.tax_engine   = tax_engine
        self.account_type = account_type

        # 공유 세션(TaxSessionState) — 있으면 주문실행기와 금융소득 풀 공유(중간실현 합산).
        self._session = session
        # 외부 금융소득(시뮬 밖, 예: 보유 타 자산 이자·배당). 매년 ytd 베이스라인으로 주입.
        self.other_financial_income = float(other_financial_income or 0.0)
        self._ytd_income  = self.other_financial_income
        self._current_year: int | None = None
        # 세션 없을 때만 쓰는 자체 연도별 트래킹.
        self.financial_income_by_year: dict[int, float] = {}
        self._sim_div_this_year = 0.0

    def process(self, portfolio, price_data, price_dict, date, dividend_mode, dividend_today=None):
        """DividendEngine.process() 시그니처와 동일."""
        if self._session is not None:
            self._session.touch(date)
        else:
            # 세션 없을 때 자체 연도 리셋(외부 금융소득부터 재시작)
            if self._current_year != date.year:
                if self._current_year is not None:
                    self.financial_income_by_year[self._current_year] = (
                        self.other_financial_income + self._sim_div_this_year
                    )
                self._current_year = date.year
                self._ytd_income   = self.other_financial_income
                self._sim_div_this_year = 0.0

        # 원본 배당 계산
        gross_by_ticker = self.base_engine.process(
            portfolio, price_data, price_dict, date, dividend_mode, dividend_today=dividend_today
        )

        # 세금 적용
        net_by_ticker = {}
        total_tax = 0.0
        for ticker, gross_div in gross_by_ticker.items():
            if gross_div > 0:
                ytd = (self._session.ytd_financial_income
                       if self._session is not None else self._ytd_income)
                net_div = self.tax_engine.after_tax_dividend(
                    gross_div, ticker, self.account_type, ytd,
                )
                total_tax += max(0.0, gross_div - net_div)
                # 위탁 계좌의 금융소득만 누계에 포함
                if self.account_type == "위탁":
                    if self._session is not None:
                        self._session.add_financial_income(gross_div)
                    else:
                        self._ytd_income       += gross_div
                        self._sim_div_this_year += gross_div
                net_by_ticker[ticker] = net_div
            else:
                net_by_ticker[ticker] = gross_div

        # base_engine이 GROSS를 portfolio.cash에 입금했으므로 배당소득세만큼 차감 → cash엔 net만 남음.
        # (이 차감이 없으면 배당세가 포트폴리오에서 안 빠져 미과세됨 — BUG-TAX-1.)
        if total_tax > 0:
            portfolio.cash = max(0.0, portfolio.cash - total_tax)

        return net_by_ticker

    def finalize_year_tracking(self, extra_final_year_income: float = 0.0) -> dict[int, float]:
        """마지막 연도 금융소득 flush + (선택) 청산 KR_FOREIGN 차익 가산. year → 총 금융소득."""
        if self._session is not None:
            return self._session.finalize(extra_final_year_income)
        if self._current_year is not None:
            self.financial_income_by_year[self._current_year] = (
                self.other_financial_income + self._sim_div_this_year + extra_final_year_income
            )
        return dict(self.financial_income_by_year)

    @property
    def ytd_income(self) -> float:
        if self._session is not None:
            return self._session.ytd_financial_income
        return self._ytd_income


# ── Track G G2: 분배 정책 + 동적 납입 한도 추적 ──────────────────
# 월 납입 초과분을 정책 순서대로 다른 계좌에 라우팅(cascade)할 때 사용한다.
# 한도 상수는 ACCOUNT_LIMITS와 일치(ISA 연 2천만/총 1억, 연금+IRP 합산 연 1800만).

from dataclasses import dataclass as _dataclass, field as _field

_ISA_TOTAL_LIMIT = 100_000_000
_PENSION_ANNUAL_LIMIT = 18_000_000   # 연금저축 + IRP 합산


class ContributionLimitTracker:
    """계좌별 납입 한도의 동적(상태 추적) 버전.

    check_contribution_limits는 정적 경고만 내지만, G2 라우팅은 매 시점
    "이 계좌가 지금 얼마를 더 받을 수 있나(capacity)"를 알아야 한다.
    - ISA: 연 2천만 AND 총 1억 (둘 중 작은 잔여)
    - 연금저축/IRP: 합산 연 1800만 (두 유형이 풀 공유)
    - 위탁: 무제한
    """

    def __init__(self):
        self._isa_annual: dict[int, float] = {}   # account_id → 올해 누적
        self._isa_total: dict[int, float] = {}     # account_id → 총 누적
        self._pension_annual: float = 0.0          # 연금+IRP 합산 올해 누적
        self._policy_routed: dict[int, float] = {} # account_id → 정책 라우팅 누적(cap용, 전기간)
        self._year: int | None = None

    def touch(self, date) -> None:
        """해가 바뀌면 연한도 리셋(총한도는 유지)."""
        y = date.year
        if self._year is None:
            self._year = y
        elif y != self._year:
            self._year = y
            self._isa_annual = {}
            self._pension_annual = 0.0

    def capacity(self, account_id: int, account_type: str) -> float:
        """이 계좌가 추가로 받을 수 있는 최대 금액(무제한이면 inf)."""
        if account_type == "ISA":
            annual = _ISA_ANNUAL_LIMIT - self._isa_annual.get(account_id, 0.0)
            total = _ISA_TOTAL_LIMIT - self._isa_total.get(account_id, 0.0)
            return max(0.0, min(annual, total))
        if account_type in ("연금저축", "IRP"):
            return max(0.0, _PENSION_ANNUAL_LIMIT - self._pension_annual)
        return float("inf")  # 위탁

    def record(self, account_id: int, account_type: str, amount: float) -> None:
        """실제 납입 반영(capacity 차감)."""
        if amount <= 0:
            return
        if account_type == "ISA":
            self._isa_annual[account_id] = self._isa_annual.get(account_id, 0.0) + amount
            self._isa_total[account_id] = self._isa_total.get(account_id, 0.0) + amount
        elif account_type in ("연금저축", "IRP"):
            self._pension_annual += amount


@_dataclass
class DistributionDestination:
    account_id: int                # 목적지 계좌 id (없으면 위탁 자동 싱크)
    cap: float = float("inf")      # 정책 레벨 추가 상한(사용자 지정). None/inf=무제한


@_dataclass
class DistributionPolicy:
    """우선순위 순 목적지 목록. ISA 초과분을 위에서부터 cap까지 채우고 cascade."""
    destinations: list = _field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict | None) -> "DistributionPolicy | None":
        if not raw:
            return None
        dests = []
        for d in raw.get("destinations", []):
            cap = d.get("cap")
            dests.append(DistributionDestination(
                account_id=int(d["account_id"]),
                cap=float(cap) if cap is not None else float("inf"),
            ))
        return cls(destinations=dests) if dests else None


def route_overflow(
    amount: float,
    policy: DistributionPolicy,
    tracker: ContributionLimitTracker,
    account_types: dict[int, str],
    pension_unlimited: bool = False,
) -> tuple[list[tuple[int, float]], float]:
    """초과분(amount)을 정책 순서대로 capacity까지 배분. cascade.

    Parameters
    ----------
    pension_unlimited : ISA 만기 전환(2-2/G3) 경로 전용. 연금/IRP로의 ISA 만기 전환은
        연 1800만 납입한도와 **별도**(전액 전환 가능)이므로 capacity=무제한으로 처리하고
        납입 풀(`_pension_annual`)에 기록하지 않는다. 월 납입 라우팅(2-1)은 False.

    Returns
    -------
    (allocations, leftover)
      allocations : [(account_id, 배분액), ...] (배분 즉시 tracker에 record됨)
      leftover    : 정책이 다 흡수 못한 잔액(보통 위탁 무제한이 마지막이면 0)
    """
    allocations: list[tuple[int, float]] = []
    remaining = float(amount)
    for dest in policy.destinations:
        if remaining <= 1e-9:
            break
        acc_type = account_types.get(dest.account_id, "위탁")
        is_pension_conversion = pension_unlimited and acc_type in ("연금저축", "IRP")
        base_cap = float("inf") if is_pension_conversion else tracker.capacity(dest.account_id, acc_type)
        # dest.cap = 전기간 누적 상한(정책 레벨). 이미 라우팅된 만큼 차감.
        routed = tracker._policy_routed.get(dest.account_id, 0.0)
        policy_room = dest.cap - routed
        cap = min(base_cap, policy_room)
        give = min(remaining, cap)
        if give > 1e-9:
            allocations.append((dest.account_id, give))
            if not is_pension_conversion:
                tracker.record(dest.account_id, acc_type, give)
            tracker._policy_routed[dest.account_id] = routed + give
            remaining -= give
    return allocations, remaining