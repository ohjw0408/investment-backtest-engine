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
from pathlib import Path
import sqlite3

# ── ETF 메타 캐시 (CSV 반복 로딩 방지) ──────────────────────
_KR_ETF_LOOKUP: dict | None = None   # code → {name, index, leverage}
_US_ETF_SET:    set   | None = None   # 미국 상장 ETF 코드 집합

def _get_kr_etf_lookup() -> dict:
    global _KR_ETF_LOOKUP
    if _KR_ETF_LOOKUP is None:
        try:
            import pandas as pd
            csv = Path(__file__).resolve().parents[2] / "data" / "meta" / "kr_etf_list.csv"
            if csv.exists():
                df = pd.read_csv(csv, dtype={"code": str})
                _KR_ETF_LOOKUP = {
                    r["code"]: {
                        "name":     str(r.get("name", "") or ""),
                        "index":    str(r.get("index", "") or "").upper(),
                        "leverage": float(r.get("leverage", 1.0) or 1.0),
                    }
                    for _, r in df.iterrows()
                }
            else:
                _KR_ETF_LOOKUP = {}
        except Exception:
            _KR_ETF_LOOKUP = {}
    return _KR_ETF_LOOKUP

def _get_us_etf_set() -> set:
    global _US_ETF_SET
    if _US_ETF_SET is None:
        try:
            import pandas as pd
            csv = Path(__file__).resolve().parents[2] / "data" / "meta" / "us_etf_list.csv"
            if csv.exists():
                df = pd.read_csv(csv, dtype={"code": str})
                _US_ETF_SET = set(df["code"].str.upper())
            else:
                _US_ETF_SET = set()
        except Exception:
            _US_ETF_SET = set()
    return _US_ETF_SET


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
    # 마지막 구간이 float("inf")이므로 도달 불가 — 방어용
    return (taxable_income * 0.45 - 65_940_000) * LOCAL_TAX_MULT


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

    # IRP 안전자산 index 유형 (kr_etf_list.csv index 컬럼 기준)
    SAFE_INDEX_TYPES = frozenset({
        "KR_MONEY_MARKET",
        "KR_BOND_AGGREGATE",
        "KR_TREASURY", "KR_TREASURY_3Y", "KR_TREASURY_5Y",
        "KR_TREASURY_10Y", "KR_TREASURY_30Y",
        "KR_CORPORATE",
        "US_BOND_AGGREGATE", "US_TREASURY", "US_TREASURY_10Y", "US_TREASURY_30Y",
        "ASIA_BOND",
    })
    # 종목명에 포함 시 안전자산으로 분류
    SAFE_NAME_KEYWORDS = frozenset({
        "채권", "국채", "통안채", "회사채", "CD금리", "KOFR",
        "단기자금", "머니마켓", "BOND", "TREASURY",
    })

    DIVIDEND_THRESHOLD = 20_000_000  # 금융소득 종합과세 기준
    OVERSEAS_CG_EXEMPT = 2_500_000   # 해외 양도세 기본공제
    OVERSEAS_CG_RATE   = 0.22        # 해외 양도세율 (지방세 포함)
    ISA_GENERAL_EXEMPT = 2_000_000   # ISA 일반형 비과세 한도
    ISA_PREF_EXEMPT    = 4_000_000   # ISA 서민형 비과세 한도
    ISA_TAX_RATE       = 0.099       # ISA 만기 분리과세율
    ISA_CANCEL_RATE    = 0.154       # ISA 중도해지 배당소득세
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
        # 'earned'(근로소득자, 총급여 5,500만 기준) | 'comprehensive'(종합소득자, 4,500만 기준)
        self.income_type   = user_settings.get("income_type", "earned")

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
        """종합과세 구간에서 추가 납부액 계산.

        임계선(2,000만) 부분 돌파 시에도 정확하게 처리:
        - ytd < 2,000만 < ytd+new_div → new_div 중 임계 초과분만 종합과세
        - 원천징수 공제는 종합과세 대상(초과분)에 비례해서만 적용
        """
        threshold = self.DIVIDEND_THRESHOLD
        prev_fin  = max(0.0, ytd - threshold)
        curr_fin  = max(0.0, ytd + new_div - threshold)
        tax_with    = _comprehensive_tax(self.earned_income + curr_fin)
        tax_without = _comprehensive_tax(self.earned_income + prev_fin)

        # 종합과세 대상 금액(초과분)에 비례하는 원천징수액만 공제
        # 예: ytd=1900만, new_div=200만 → 초과분 100만 / 200만 = 50%만 공제
        excess = curr_fin - prev_fin
        if new_div > 0 and excess < new_div:
            withheld_on_excess = already_withheld * (excess / new_div)
        else:
            withheld_on_excess = already_withheld

        extra = max(0.0, tax_with - tax_without - withheld_on_excess)
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
        pension_years: int = 0,
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
        pension_years      : 연금 적립 기간 (세액공제 미수령 원금 계산용)
        """
        if account_type == "위탁":
            return end_value  # 운용 중 이미 과세

        if account_type == "ISA":
            return self._isa_tax(
                end_value, total_contribution,
                is_early_cancel or isa_years_held < 3
            )

        if account_type in ("연금저축", "IRP"):
            if pension_years > 0:
                annual = total_contribution / pension_years if total_contribution > 0 else 0.0
            else:
                annual = 0.0  # 기간 불명 → 비과세 원금 계산 스킵
            return self._pension_tax(
                end_value, age or self.pension_age,
                total_contribution=total_contribution,
                annual_contribution=annual,
                years=pension_years,
            )

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

    def _pension_tax(
        self,
        end_value: float,
        age: int,
        total_contribution: float = 0.0,
        annual_contribution: float = 0.0,
        years: int = 0,
    ) -> float:
        """
        연금저축/IRP 수령세 계산.

        세액공제 한도(연 900만) 초과 납입분은 원금 반환이므로 비과세.
        - non_deductible: 세액공제를 받지 못한 원금 총액
        - 과세 대상 = end_value - non_deductible
        """
        if age < 55:
            raise ValueError(
                f"연금 수령은 만 55세 이상만 가능합니다. (입력 나이: {age})"
            )
        rate = (
            self.PENSION_RATES[80] if age >= 80
            else self.PENSION_RATES[70] if age >= 70
            else self.PENSION_RATES[55]
        )

        # 세액공제 한도 초과 납입분 계산
        # (연 납입액 중 900만 초과분은 세액공제 불가 → 수령 시 비과세 반환)
        # pension_years=0이면 정보 부족 → 보수적으로 전액 과세 (기존 동작)
        if annual_contribution > 0 and years > 0 and annual_contribution > 9_000_000:
            non_deductible_total = max(0.0, annual_contribution - 9_000_000) * years
            non_deductible_total = min(non_deductible_total, total_contribution)
        else:
            non_deductible_total = 0.0

        taxable = max(0.0, end_value - non_deductible_total)
        return non_deductible_total + taxable * (1.0 - rate)
    # ═══════════════════════════════════════════════════════════
    # 6. 연금 수령 세금 (1,500만원 초과 처리 포함)
    # ═══════════════════════════════════════════════════════════

    PENSION_ANNUAL_THRESHOLD = 15_000_000   # 1,500만원
    PENSION_EXCESS_SEP_RATE  = 0.165        # 초과분 분리과세 16.5%

    def pension_rate_by_age(self, age: int) -> float:
        """나이별 연금소득세율 (지방소득세 포함)."""
        if age >= 80: return self.PENSION_RATES[80]
        if age >= 70: return self.PENSION_RATES[70]
        return self.PENSION_RATES[55]

    def pension_monthly_after_tax(
        self,
        monthly_amount: float,
        age: int,
        earned_income: float | None = None,
    ) -> float:
        """
        연금 월 수령액 세후 금액.

        1,500만원 이하: 나이별 3.3~5.5% 분리과세
        1,500만원 초과: 초과분에 대해 16.5% 분리과세 or 종합과세 중 유리한 쪽

        Parameters
        ----------
        monthly_amount : 월 수령액 (원)
        age            : 수령 나이
        earned_income  : 근로소득 (종합과세 판단용, None이면 self.earned_income)
        """
        if monthly_amount <= 0:
            return 0.0

        annual       = monthly_amount * 12
        threshold    = self.PENSION_ANNUAL_THRESHOLD
        rate_low     = self.pension_rate_by_age(age)
        monthly_thr  = threshold / 12

        if annual <= threshold:
            return monthly_amount * (1.0 - rate_low)

        # 1,500만 이하 부분: 저율 적용
        low_part  = monthly_thr * (1.0 - rate_low)

        # 초과 부분: 유리한 세율 선택
        excess_monthly = monthly_amount - monthly_thr
        excess_rate    = self._pension_excess_rate(annual, earned_income)
        high_part      = excess_monthly * (1.0 - excess_rate)

        return low_part + high_part

    def _pension_excess_rate(
        self,
        annual_pension: float,
        earned_income: float | None = None,
    ) -> float:
        """
        1,500만원 초과 연금소득에 대한 실효세율.
        16.5% 분리과세 vs 종합소득세 증분세액 중 낮은 쪽.

        한계세율 대신 증분세액(comprehensive_tax 차분)으로 계산해야
        구간 경계 근처에서 과대 추정을 피할 수 있음.
        """
        ei      = earned_income if earned_income is not None else self.earned_income
        excess  = annual_pension - self.PENSION_ANNUAL_THRESHOLD
        if excess <= 0:
            return self.pension_rate_by_age(self.age)

        # 분리과세: 16.5%
        sep_tax = excess * self.PENSION_EXCESS_SEP_RATE

        # 종합과세: 증분세액 방식 (한계세율 대신 실제 차분 사용)
        tax_with    = _comprehensive_tax(ei + annual_pension)
        tax_without = _comprehensive_tax(ei + self.PENSION_ANNUAL_THRESHOLD)
        comp_tax    = tax_with - tax_without

        if sep_tax <= comp_tax:
            return self.PENSION_EXCESS_SEP_RATE
        else:
            return comp_tax / excess if excess > 0 else self.PENSION_EXCESS_SEP_RATE

    def pension_annual_tax(
        self,
        annual_amount: float,
        age: int,
        earned_income: float | None = None,
    ) -> float:
        """연간 연금 수령 시 총 세금액."""
        monthly_tax = (annual_amount / 12) - self.pension_monthly_after_tax(
            annual_amount / 12, age, earned_income
        )
        return monthly_tax * 12

    def pension_effective_rate(
        self,
        annual_amount: float,
        age: int,
        earned_income: float | None = None,
    ) -> float:
        """연간 연금 수령 실효세율."""
        if annual_amount <= 0:
            return 0.0
        tax = self.pension_annual_tax(annual_amount, age, earned_income)
        return tax / annual_amount


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
        # 근로소득자: 총급여 5,500만 이하 → 16.5%, 초과 → 13.2%
        # 종합소득자(income_type='comprehensive'): 종합소득금액 4,500만 이하 → 16.5%
        if self.income_type == "comprehensive":
            rate = 0.165 if ei <= 45_000_000 else 0.132
        else:
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

        # "005930.KS", "069500.KQ" 등 야후 파이낸스 형식 → 국내 상장으로 처리
        base = ticker.split(".")[0]
        if base.isdigit() and len(base) == 6:
            return self._classify_kr_etf(base)

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

    def _is_safe_asset(self, ticker: str) -> bool:
        """
        IRP 안전자산 여부 판별.
        kr_etf_list.csv index 유형과 종목명 키워드의 합집합으로 판단.
        """
        if ticker == "CASH":
            return True
        base = ticker.split(".")[0]
        if not (base.isdigit() and len(base) == 6):
            return False  # KR 상장 ETF·CASH만 IRP 허용 대상

        info = _get_kr_etf_lookup().get(base)
        if info:
            if info["index"] in self.SAFE_INDEX_TYPES:
                return True
            if any(k in info["name"] for k in self.SAFE_NAME_KEYWORDS):
                return True

        # CSV에 없는 경우 symbol_master.db name으로 fallback
        try:
            db = Path(__file__).resolve().parents[2] / "data" / "meta" / "symbol_master.db"
            if db.exists():
                conn = sqlite3.connect(str(db))
                row = conn.execute("SELECT name FROM symbols WHERE code=?", (base,)).fetchone()
                conn.close()
                if row and any(k in (row[0] or "") for k in self.SAFE_NAME_KEYWORDS):
                    return True
        except Exception:
            pass
        return False

    def classify_instrument_type(self, ticker: str) -> str:
        """
        종목 유형 판별.

        Returns
        -------
        'ETF'           일반 ETF
        'LEVERAGED_ETF' 레버리지 ETF
        'INVERSE_ETF'   인버스 ETF
        'STOCK'         개별주식
        'UNKNOWN'       판별 불가
        """
        base = ticker.split(".")[0]

        # 1. symbol_master.db 조회 (is_etf, leverage 필드)
        try:
            db = Path(__file__).resolve().parents[2] / "data" / "meta" / "symbol_master.db"
            if db.exists():
                conn = sqlite3.connect(str(db))
                row = conn.execute(
                    "SELECT is_etf, leverage, name FROM symbols WHERE code=?", (base,)
                ).fetchone()
                conn.close()
                if row is not None:
                    is_etf, leverage, name = row
                    if not is_etf:
                        return "STOCK"
                    if leverage is not None:
                        if float(leverage) > 1.0:
                            return "LEVERAGED_ETF"
                        if float(leverage) < 0:
                            return "INVERSE_ETF"
                    # is_etf=1 이지만 leverage가 NULL → 이름으로 재확인
                    name = name or ""
                    if any(k in name for k in ["레버리지", "LEVERAGE", "2X", "3X"]):
                        return "LEVERAGED_ETF"
                    if any(k in name for k in ["인버스", "INVERSE", "-1X", "-2X"]):
                        return "INVERSE_ETF"
                    return "ETF"
        except Exception:
            pass

        # 2. kr_etf_list.csv 조회 (6자리 국내 코드)
        if base.isdigit() and len(base) == 6:
            info = _get_kr_etf_lookup().get(base)
            if info:
                lev = info["leverage"]
                if lev > 1.0:
                    return "LEVERAGED_ETF"
                if lev < 0:
                    return "INVERSE_ETF"
                return "ETF"

        # 3. us_etf_list.csv 조회 (알파벳 US 코드)
        if ticker.isalpha() and ticker.upper() in _get_us_etf_set():
            return "ETF"

        return "UNKNOWN"

    # ═══════════════════════════════════════════════════════════
    # 5. IRP 위험자산 비중 검증
    # ═══════════════════════════════════════════════════════════

    def validate_irp_weights(self, weights: dict) -> dict:
        """
        IRP 위험자산 70% 한도 검증.
        안전자산 분류는 SAFE_INDEX_TYPES + SAFE_NAME_KEYWORDS 합집합 기준.

        Returns
        -------
        {
          'valid': bool,
          'warning': str | None,
          'risky_ratio': float,
          'disclaimer': str,
        }
        """
        DISCLAIMER = (
            "안전자산 분류는 index 유형 및 종목명 기반 자동 분류이며, "
            "실제 금융감독원 기준 안전자산과 다를 수 있습니다."
        )

        risky_total = sum(
            w for code, w in weights.items()
            if not self._is_safe_asset(code)
        )

        if risky_total <= 0.70:
            return {
                "valid":       True,
                "warning":     None,
                "risky_ratio": risky_total,
                "disclaimer":  DISCLAIMER,
            }

        return {
            "valid":       False,
            "warning":     f"IRP 위험자산 비중이 {risky_total*100:.1f}%로 한도(70%)를 초과합니다.",
            "risky_ratio": risky_total,
            "disclaimer":  DISCLAIMER,
        }