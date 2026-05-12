"""
modules/tax/base_tax.py
────────────────────────────────────────────────────────────────────────────────
세금 엔진 핵심 클래스

계좌 타입별 세금 처리:
  위탁:    배당 15.4%(국내)/15%(미국), 해외 매매차익 250만 공제 후 22%
  ISA:     운용 중 비과세, 만기 시 순이익 200/400만 공제 후 9.9%
           (중도해지 3년 전: 16.5%)
  연금저축: 운용 중 비과세, 수령 시 3.3~5.5% 연금소득세
  IRP:     운용 중 비과세, 수령 시 3.3~5.5% 연금소득세
           (위험자산 70% 제한)

금융소득 종합과세:
  위탁 계좌 이자+배당 연 2,000만 초과 시 근로소득 합산 누진과세
"""

from __future__ import annotations


# ── 종합소득세 세율표 (2025년 기준) ─────────────────────────
COMPREHENSIVE_TAX_BRACKETS = [
    (14_000_000,  0.06,          0),
    (50_000_000,  0.15,  1_260_000),
    (88_000_000,  0.24,  5_760_000),
    (150_000_000, 0.35, 15_440_000),
    (300_000_000, 0.38, 19_940_000),
    (500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000),
    (float("inf"),  0.45, 65_940_000),
]

# 지방소득세 포함 승수
LOCAL_TAX_MULT = 1.1


def _comprehensive_tax(taxable_income: float) -> float:
    """종합소득세 계산 (지방소득세 포함)"""
    if taxable_income <= 0:
        return 0.0
    for bracket, rate, deduction in COMPREHENSIVE_TAX_BRACKETS:
        if taxable_income <= bracket:
            return (taxable_income * rate - deduction) * LOCAL_TAX_MULT
    return 0.0


def _marginal_rate(taxable_income: float) -> float:
    """해당 과세표준의 한계세율 반환 (지방소득세 포함)"""
    for bracket, rate, _ in COMPREHENSIVE_TAX_BRACKETS:
        if taxable_income <= bracket:
            return rate * LOCAL_TAX_MULT
    return 0.45 * LOCAL_TAX_MULT


class TaxEngine:
    """
    계좌 타입 × 종목 타입 조합에 따른 세금 계산 엔진.

    Parameters
    ----------
    user_settings : dict
        earned_income  : float  근로/사업소득 (연간, 원)
        age            : int    나이 (연금소득세율 결정)
        isa_type       : str    'general' (200만) | 'preferential' (400만)
        pension_age    : int    연금 수령 예정 나이
    """

    DIVIDEND_THRESHOLD = 20_000_000  # 금융소득 종합과세 기준
    OVERSEAS_CG_EXEMPT = 2_500_000   # 해외 양도세 기본공제
    OVERSEAS_CG_RATE   = 0.22        # 해외 양도세율 (지방세 포함)
    ISA_GENERAL_EXEMPT = 2_000_000   # ISA 일반형 비과세 한도
    ISA_PREF_EXEMPT    = 4_000_000   # ISA 서민형 비과세 한도
    ISA_TAX_RATE       = 0.099       # ISA 만기 분리과세율
    ISA_CANCEL_RATE    = 0.165       # ISA 중도해지 기타소득세
    PENSION_RATES      = {           # 연금소득세율 (나이 → 세율)
        55: 0.055,
        70: 0.044,
        80: 0.033,
    }

    def __init__(self, user_settings: dict):
        self.earned_income = float(user_settings.get("earned_income", 0))
        self.age           = int(user_settings.get("age", 40))
        self.isa_type      = user_settings.get("isa_type", "general")
        self.pension_age   = int(user_settings.get("pension_age", 65))

    # ═══════════════════════════════════════════════════════════
    # 1. 배당 세후 금액
    # ═══════════════════════════════════════════════════════════

    def after_tax_dividend(
        self,
        gross_dividend: float,
        ticker: str,
        account_type: str,
        ytd_financial_income: float = 0.0,
    ) -> float:
        """
        세후 배당금 반환.

        Parameters
        ----------
        gross_dividend        : 세전 배당금
        ticker                : 종목 코드 (자산 타입 판별용)
        account_type          : '위탁' | 'ISA' | '연금저축' | 'IRP'
        ytd_financial_income  : 올해 금융소득 누계 (종합과세 판단용)
        """
        if gross_dividend <= 0:
            return 0.0

        # 연금 계좌: 과세이연 → 그대로 반환
        if account_type in ("ISA", "연금저축", "IRP"):
            return gross_dividend

        # 위탁 계좌
        asset_type = self.classify_asset(ticker)

        if asset_type == "US_DIRECT":
            # 미국 직접 → 현지 15% 원천징수 (한국 세율 14% < 15%)
            # 2,000만 이하: 추가 납부 없음
            # 2,000만 초과: 종합과세 (외국납부세액공제 적용)
            withheld = gross_dividend * 0.15
            net = gross_dividend - withheld

            if ytd_financial_income + gross_dividend > self.DIVIDEND_THRESHOLD:
                # 종합과세 추가 부담
                extra = self._comprehensive_extra_tax(
                    gross_dividend, ytd_financial_income, withheld
                )
                net -= extra
            return max(0.0, net)

        else:
            # 국내 상장 종목 (국내 주식형/해외주식형 ETF, 개별주식)
            rate = 0.154  # 15.4% 원천징수
            withheld = gross_dividend * rate
            net = gross_dividend - withheld

            if ytd_financial_income + gross_dividend > self.DIVIDEND_THRESHOLD:
                extra = self._comprehensive_extra_tax(
                    gross_dividend, ytd_financial_income, withheld
                )
                net -= extra
            return max(0.0, net)

    def _comprehensive_extra_tax(
        self,
        new_div: float,
        ytd: float,
        already_withheld: float,
    ) -> float:
        """종합과세 구간에서 추가 납부액 계산"""
        total_income  = self.earned_income + max(0, ytd - self.DIVIDEND_THRESHOLD) + new_div
        prev_total    = self.earned_income + max(0, ytd - self.DIVIDEND_THRESHOLD)
        marginal_rate = _marginal_rate(total_income)
        gross_tax     = new_div * marginal_rate
        # 이미 원천징수된 세액 차감
        extra = max(0.0, gross_tax - already_withheld)
        return extra

    # ═══════════════════════════════════════════════════════════
    # 2. 만기/수령 세후 금액
    # ═══════════════════════════════════════════════════════════

    def after_tax_withdrawal(
        self,
        end_value: float,
        account_type: str,
        total_contribution: float,
        age: int | None = None,
        is_early_cancel: bool = False,
        isa_years_held: int = 3,
    ) -> float:
        """
        만기/수령 후 실수령액 반환.

        Parameters
        ----------
        end_value          : 시뮬레이션 최종 자산
        account_type       : 계좌 타입
        total_contribution : 원금 합계 (ISA 순이익 계산용)
        age                : 수령 나이 (연금소득세율 결정)
        is_early_cancel    : ISA 3년 전 해지 여부
        isa_years_held     : ISA 보유 기간 (년)
        """
        if account_type == "위탁":
            return end_value  # 운용 중 이미 과세

        if account_type == "ISA":
            return self._isa_tax(
                end_value, total_contribution,
                is_early_cancel or isa_years_held < 3
            )

        if account_type in ("연금저축", "IRP"):
            return self._pension_tax(end_value, age or self.pension_age)

        return end_value

    def _isa_tax(
        self,
        end_value: float,
        total_contribution: float,
        is_early_cancel: bool,
    ) -> float:
        net_profit = end_value - total_contribution

        if net_profit <= 0:
            return end_value  # 손실이면 세금 없음

        if is_early_cancel:
            # 중도해지: 순이익 전체에 16.5% 기타소득세
            tax = net_profit * self.ISA_CANCEL_RATE
            return end_value - tax

        # 만기: 비과세 한도 초과분에 9.9%
        exempt = (
            self.ISA_PREF_EXEMPT
            if self.isa_type == "preferential"
            else self.ISA_GENERAL_EXEMPT
        )
        taxable = max(0.0, net_profit - exempt)
        tax = taxable * self.ISA_TAX_RATE
        return end_value - tax

    def _pension_tax(self, end_value: float, age: int) -> float:
        rate = (
            self.PENSION_RATES[80] if age >= 80
            else self.PENSION_RATES[70] if age >= 70
            else self.PENSION_RATES[55]
        )
        return end_value * (1.0 - rate)

    # ═══════════════════════════════════════════════════════════
    # 3. 세액공제 환급액
    # ═══════════════════════════════════════════════════════════

    def annual_tax_deduction(
        self,
        annual_pension_contrib: float,
        annual_irp_contrib: float,
        earned_income: float | None = None,
    ) -> float:
        """
        연금저축 + IRP 세액공제 연간 환급액 계산.

        환급액 = min(합산납입, 공제한도) × 공제율
        공제한도: 연금저축 단독 600만, 합산 900만
        공제율:  총급여 5,500만↓ 16.5% / 초과 13.2%
        """
        ei = earned_income if earned_income is not None else self.earned_income
        rate = 0.165 if ei <= 55_000_000 else 0.132

        pension_limit = 6_000_000
        combined_limit = 9_000_000

        pension_deductible = min(annual_pension_contrib, pension_limit)
        combined = pension_deductible + annual_irp_contrib
        total_deductible = min(combined, combined_limit)

        return total_deductible * rate

    # ═══════════════════════════════════════════════════════════
    # 4. 종목 타입 분류
    # ═══════════════════════════════════════════════════════════

    def classify_asset(self, ticker: str) -> str:
        """
        종목 코드 → 자산 타입 반환.

        Returns
        -------
        'KR_DOMESTIC'  국내 주식형 ETF / 국내 개별주식
        'KR_FOREIGN'   국내 상장 해외주식형 ETF (TIGER S&P500 등)
        'US_DIRECT'    미국 직접 상장 주식/ETF (SPY, SCHD 등)
        'KRX_GOLD'     KRX 금현물
        """
        if ticker == "KRX_GOLD":
            return "KRX_GOLD"

        # 미국 직접 (알파벳만, ^ 제외)
        if ticker.isalpha() or ticker.startswith("^") or "=" in ticker:
            return "US_DIRECT"

        # 6자리 숫자 → 국내 상장
        if ticker.isdigit() and len(ticker) == 6:
            return self._classify_kr_etf(ticker)

        return "US_DIRECT"

    def _classify_kr_etf(self, ticker: str) -> str:
        """
        국내 상장 종목이 해외주식형 ETF인지 판별.
        symbol_master.db의 category 필드로 1차 판별,
        없으면 KR_DOMESTIC으로 처리.
        """
        try:
            from pathlib import Path
            import sqlite3
            db = Path(__file__).resolve().parents[2] / "data" / "meta" / "symbol_master.db"
            if not db.exists():
                return "KR_DOMESTIC"
            conn = sqlite3.connect(str(db))
            row  = conn.execute(
                "SELECT category, index_name FROM symbols WHERE code=?", (ticker,)
            ).fetchone()
            conn.close()
            if row:
                text = " ".join(str(v) for v in row if v).upper()
                # 해외 지수 추종 키워드
                FOREIGN_KEYWORDS = [
                    "S&P", "SP500", "NASDAQ", "DOW", "MSCI", "US",
                    "미국", "해외", "GLOBAL", "글로벌", "WORLD",
                    "JAPAN", "CHINA", "EUROPE", "아시아",
                ]
                if any(k in text for k in FOREIGN_KEYWORDS):
                    return "KR_FOREIGN"
        except Exception:
            pass
        return "KR_DOMESTIC"

    # ═══════════════════════════════════════════════════════════
    # 5. IRP 위험자산 비중 검증
    # ═══════════════════════════════════════════════════════════

    def validate_irp_weights(self, weights: dict) -> dict:
        """
        IRP 위험자산 70% 한도 검증.
        초과 시 경고 메시지와 조정된 비중 반환.

        Returns {'valid': bool, 'warning': str | None, 'adjusted_weights': dict}
        """
        SAFE_CODES = {"CASH", "TLT", "IEF", "BND"}  # 대표 안전자산 코드

        risky_total = sum(
            w for code, w in weights.items()
            if code not in SAFE_CODES
        )

        if risky_total <= 0.70:
            return {"valid": True, "warning": None, "adjusted_weights": weights}

        # 70% 초과 → 비례 축소
        scale = 0.70 / risky_total
        adjusted = {}
        safe_total = sum(w for c, w in weights.items() if c in SAFE_CODES)
        safe_scale = 0.30 / max(safe_total, 1e-9)

        for code, w in weights.items():
            if code in SAFE_CODES:
                adjusted[code] = w * safe_scale
            else:
                adjusted[code] = w * scale

        return {
            "valid":            False,
            "warning":          f"IRP 위험자산 비중이 {risky_total*100:.1f}%입니다. "
                                f"70%로 자동 조정됩니다.",
            "adjusted_weights": adjusted,
        }