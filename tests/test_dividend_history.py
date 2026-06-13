"""내자산 배당금 차트(build_dividend_chart, 이벤트 기반) 결정론 불변식 검증.

실 corporate_actions 데이터 → 절대값 대신 불변식:
- 연도 구조(과거3+예측1), 이벤트 필드, 세율(일반 KR15.4%/US15%·ISA 비과세), FX, 예측 성장.
"""
from datetime import datetime

import pytest

from modules.portfolio_engine import PortfolioEngine
from modules.dividend_history import build_dividend_chart

pe = PortfolioEngine()
L  = pe.loader


def _sum(events, key):
    return sum(e[key] for e in events)


def test_structure_and_event_fields():
    d = build_dividend_chart(L, [{"code": "458730", "quantity": 10, "account_type": "일반"}])
    Y = datetime.today().year
    assert d["years"] == [Y - 3, Y - 2, Y - 1, Y]
    assert d["proj_year"] == Y
    assert d["default_year"] == Y - 1
    ev = d["events"][Y - 1][0]
    for k in ("date", "month", "day", "code", "name", "krw_pre", "krw_post", "usd_pre", "usd_post", "projected"):
        assert k in ev
    assert 1 <= ev["month"] <= 12 and 1 <= ev["day"] <= 31


def test_kr_general_tax_154():
    d = build_dividend_chart(L, [{"code": "458730", "quantity": 10, "account_type": "일반"}])
    evs = d["events"][d["default_year"]]
    assert evs and _sum(evs, "krw_pre") > 0
    assert _sum(evs, "krw_post") == pytest.approx(_sum(evs, "krw_pre") * (1 - 0.154), rel=1e-6)


def test_isa_exempt():
    d = build_dividend_chart(L, [{"code": "458730", "quantity": 10, "account_type": "ISA"}])
    evs = d["events"][d["default_year"]]
    assert evs and _sum(evs, "krw_post") == pytest.approx(_sum(evs, "krw_pre"), rel=1e-9)


def test_us_tax_15_and_fx():
    d = build_dividend_chart(L, [{"code": "SCHD", "quantity": 100, "account_type": "일반"}])
    assert d["has_foreign"] is True
    evs = d["events"][d["default_year"]]
    assert evs and _sum(evs, "usd_pre") > 0
    assert _sum(evs, "usd_post") == pytest.approx(_sum(evs, "usd_pre") * (1 - 0.15), rel=1e-6)
    assert _sum(evs, "krw_pre") > _sum(evs, "usd_pre") * 1000   # 원화 환산 > 달러
    # 종목명 채워짐
    assert evs[0]["name"] and evs[0]["name"] != ""


def test_projection_flag_and_growth():
    d = build_dividend_chart(L, [{"code": "SCHD", "quantity": 100, "account_type": "일반"}])
    proj = d["events"][d["proj_year"]]
    assert proj and all(e["projected"] for e in proj)
    if d["growth"].get("SCHD", 0) > 0:
        base = d["events"][d["proj_year"] - 1]
        assert _sum(proj, "usd_pre") > _sum(base, "usd_pre")


def test_gold_skipped():
    d = build_dividend_chart(L, [{"code": "KRX_GOLD", "quantity": 5, "account_type": "일반"}])
    assert all(len(d["events"][y]) == 0 for y in d["years"])
