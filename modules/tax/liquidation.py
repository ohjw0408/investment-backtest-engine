"""
modules/tax/liquidation.py
최종 청산 세금 계산 — 모든 시뮬 화면이 공유하는 단일 구현.

backtest_logic.py의 근사식(gain*weight)을 대체.
포지션별 실제 취득단가 + YTD 실현차익 반영으로 정확도 향상.
"""


def apply_liquidation_tax(
    end_value: float,
    portfolio,
    last_prices: dict,
    tax_engine,
    account_type: str,
    total_contribution: float,
    ytd_us_realized_gains: float = 0.0,
    age: int = None,
    pension_years: int = 0,
    isa_years_held: int = 3,
    ytd_financial_income: float = 0.0,
) -> float:
    """
    시뮬레이션 종료 시 청산 세금 계산 후 세후 최종자산 반환.

    Parameters
    ----------
    end_value             : 시뮬레이션 최종 자산 (recorder 기준)
    portfolio             : 최종 포트폴리오 (위탁 미실현차익 계산용)
    last_prices           : ticker → 최종 가격
    tax_engine            : TaxEngine
    account_type          : 위탁 | ISA | 연금저축 | IRP
    total_contribution    : 총 납입금액
    ytd_us_realized_gains : 당해연도 이미 실현한 US_DIRECT 차익 (250만 공제 잔여 계산용)
    age                   : 연금 수령 나이
    pension_years         : 연금 적립 기간
    isa_years_held        : ISA 보유 기간
    ytd_financial_income  : 청산 연도의 기 발생 금융소득 (위탁 배당 gross + 외부 금융소득).
                            KR_FOREIGN 청산이익을 이 값과 합산해 금융소득 종합과세 판정.
    """
    if account_type in ("ISA", "연금저축", "IRP"):
        return tax_engine.after_tax_withdrawal(
            end_value, account_type, total_contribution,
            age=age,
            pension_years=pension_years,
            isa_years_held=isa_years_held,
        )

    # 위탁: 포지션별 미실현 차익으로 청산세 계산 (손익통산 적용)
    if portfolio is None or not last_prices or not hasattr(portfolio, "unrealized_gain"):
        return end_value

    us_direct_gains   = 0.0
    kr_foreign_gain   = 0.0   # 배당소득세(15.4% + 종합과세). 손익통산 없음 — 이익 포지션만.
    liquidation_tax   = 0.0

    for ticker, position in portfolio.positions.items():
        if ticker not in last_prices or position.quantity <= 0:
            continue
        price = last_prices[ticker]
        unrealized = portfolio.unrealized_gain(ticker, price)
        if unrealized == 0.0:
            continue

        asset_type = tax_engine.classify_asset(ticker)

        if asset_type == "KR_FOREIGN":
            if unrealized > 0:
                kr_foreign_gain += unrealized

        elif asset_type == "US_DIRECT":
            us_direct_gains += unrealized   # 양도소득세: 손익통산 O

    # KR_FOREIGN 청산이익: 그 해 금융소득(ytd_financial_income)과 합산 → 금융소득 종합과세.
    # 2천만 이하 → 15.4% 분리. 초과 → 임계 아래 15.4% + 초과분 종합과세(배당과 동일 로직 재사용).
    if kr_foreign_gain > 0:
        withheld = kr_foreign_gain * 0.154
        liquidation_tax += withheld
        if ytd_financial_income + kr_foreign_gain > tax_engine.DIVIDEND_THRESHOLD:
            liquidation_tax += tax_engine._comprehensive_extra_tax(
                kr_foreign_gain, ytd_financial_income, withheld
            )

    if us_direct_gains > 0:
        # 당해연도 이미 실현한 차익 반영 → 250만 공제 중복 방지
        remaining_exempt = max(0.0, 2_500_000 - ytd_us_realized_gains)
        taxable = max(0.0, us_direct_gains - remaining_exempt)
        liquidation_tax += taxable * 0.22

    return max(0.0, end_value - liquidation_tax)
