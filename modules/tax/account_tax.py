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

        if account_type == "ISA":
            if market == "US_DIRECT":
                violations.append(
                    f"ISA 계좌는 해외 직접 상장 종목({ticker})을 보유할 수 없습니다. "
                    f"국내 상장 ETF(예: TIGER 미국S&P500)를 이용하세요."
                )

        elif account_type in ("연금저축", "IRP"):
            if market == "US_DIRECT":
                violations.append(
                    f"{account_type} 계좌는 해외 직접 상장 종목({ticker})을 보유할 수 없습니다. "
                    f"국내 상장 ETF를 이용하세요."
                )
            elif inst == "STOCK":
                violations.append(
                    f"{account_type} 계좌는 개별주식({ticker})을 보유할 수 없습니다. "
                    f"ETF만 투자 가능합니다."
                )
            elif inst == "LEVERAGED_ETF":
                violations.append(
                    f"{account_type} 계좌는 레버리지 ETF({ticker})를 보유할 수 없습니다."
                )
            elif inst == "INVERSE_ETF":
                violations.append(
                    f"{account_type} 계좌는 인버스 ETF({ticker})를 보유할 수 없습니다."
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

    def __init__(self, base_engine, tax_engine, account_type: str):
        self.base_engine  = base_engine
        self.tax_engine   = tax_engine
        self.account_type = account_type

        self._ytd_income  = 0.0
        self._current_year: int | None = None

    def process(self, portfolio, price_data, price_dict, date, dividend_mode):
        """DividendEngine.process() 시그니처와 동일."""
        # 연도 바뀌면 연간 누계 리셋
        if self._current_year != date.year:
            self._current_year = date.year
            self._ytd_income   = 0.0

        # 원본 배당 계산
        gross_by_ticker = self.base_engine.process(
            portfolio, price_data, price_dict, date, dividend_mode
        )

        # 세금 적용
        net_by_ticker = {}
        for ticker, gross_div in gross_by_ticker.items():
            if gross_div > 0:
                net_div = self.tax_engine.after_tax_dividend(
                    gross_div,
                    ticker,
                    self.account_type,
                    self._ytd_income,
                )
                # 위탁 계좌의 금융소득만 누계에 포함
                if self.account_type == "위탁":
                    self._ytd_income += gross_div
                net_by_ticker[ticker] = net_div
            else:
                net_by_ticker[ticker] = gross_div

        return net_by_ticker

    @property
    def ytd_income(self) -> float:
        return self._ytd_income