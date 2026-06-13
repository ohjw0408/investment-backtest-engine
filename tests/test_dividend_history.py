"""내자산 배당금 차트(build_dividend_chart) 결정론 불변식 검증.

실 corporate_actions 데이터를 쓰므로 절대값 대신 불변식으로 검증:
- 과거 3년 + 예측연도 구조
- 세후 = 세전 × (1-세율): 일반 KR 15.4% / US 15%, ISA·연금·IRP 비과세
- 통화: KR 보유는 KRW=네이티브·USD=÷환율, US 보유는 반대
"""
from datetime import datetime

import pytest

from modules.portfolio_engine import PortfolioEngine
from modules.dividend_history import build_dividend_chart

pe = PortfolioEngine()
L  = pe.loader


def _yeartot(d, cur, tax, year):
    return sum(d["series"][cur][tax][year])


def test_structure():
    d = build_dividend_chart(L, [{"code": "458730", "quantity": 10, "account_type": "일반"}])
    assert len(d["past_years"]) == 3
    assert d["proj_year"] == datetime.today().year
    assert d["proj_year"] == d["past_years"][-1] + 1
    # 각 연도 series = 12개월
    for cur in ("KRW", "USD"):
        for tax in ("pretax", "posttax"):
            for y in d["past_years"] + [d["proj_year"]]:
                assert len(d["series"][cur][tax][y]) == 12


def test_kr_general_account_tax_154():
    # KR ETF 일반계좌 → 세후 = 세전 × (1-0.154)
    d = build_dividend_chart(L, [{"code": "458730", "quantity": 10, "account_type": "일반"}])
    y = d["past_years"][-1]
    pre  = _yeartot(d, "KRW", "pretax", y)
    post = _yeartot(d, "KRW", "posttax", y)
    assert pre > 0
    assert post == pytest.approx(pre * (1 - 0.154), rel=1e-6)


def test_isa_account_exempt():
    # ISA → 운용 중 비과세 → 세후 = 세전
    d = build_dividend_chart(L, [{"code": "458730", "quantity": 10, "account_type": "ISA"}])
    y = d["past_years"][-1]
    pre  = _yeartot(d, "KRW", "pretax", y)
    post = _yeartot(d, "KRW", "posttax", y)
    assert pre > 0 and post == pytest.approx(pre, rel=1e-9)


def test_us_general_account_tax_15_and_fx():
    # US 일반계좌 → 세후 = 세전 × 0.85, has_foreign, KRW > USD(환율 ~1300)
    d = build_dividend_chart(L, [{"code": "SCHD", "quantity": 100, "account_type": "일반"}])
    assert d["has_foreign"] is True
    y = d["past_years"][-1]
    pre_usd  = _yeartot(d, "USD", "pretax", y)
    post_usd = _yeartot(d, "USD", "posttax", y)
    pre_krw  = _yeartot(d, "KRW", "pretax", y)
    assert pre_usd > 0
    assert post_usd == pytest.approx(pre_usd * (1 - 0.15), rel=1e-6)
    assert pre_krw > pre_usd * 1000          # 원화 환산 > 달러 (환율 배수)


def test_projection_uses_growth():
    # 예측연도 = 베이스(직전연도) 패턴 × (1+CAGR). growth 양수면 예측 >= 베이스.
    d = build_dividend_chart(L, [{"code": "SCHD", "quantity": 100, "account_type": "일반"}])
    base = d["past_years"][-1]
    proj = d["proj_year"]
    g = d["growth"].get("SCHD", 0)
    base_tot = _yeartot(d, "USD", "pretax", base)
    proj_tot = _yeartot(d, "USD", "pretax", proj)
    if g > 0:
        assert proj_tot > base_tot
    assert "SCHD" in d["growth"]


def test_empty_and_gold_skipped():
    d = build_dividend_chart(L, [{"code": "KRX_GOLD", "quantity": 5, "account_type": "일반"}])
    for cur in ("KRW", "USD"):
        for tax in ("pretax", "posttax"):
            for y in d["past_years"] + [d["proj_year"]]:
                assert sum(d["series"][cur][tax][y]) == 0
