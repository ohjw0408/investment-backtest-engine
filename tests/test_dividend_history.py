"""내자산 배당금 차트(build_dividend_chart) 결정론 불변식 검증.

연도 모델: 과거 3년 실적 + 올해(실적+예측 혼합) + 내년(전체 예측).
세율(일반 KR15.4%/US15%·ISA비과세)·FX·예측 플래그 불변식 검증(실 corporate_actions 기반).
"""
from datetime import datetime

import pytest

from modules.portfolio_engine import PortfolioEngine
from modules.dividend_history import build_dividend_chart

pe = PortfolioEngine()
L  = pe.loader
Y  = datetime.today().year


def _sum(events, key):
    return sum(e[key] for e in events)


def test_year_model():
    d = build_dividend_chart(L, [{"code": "SCHD", "quantity": 100, "account_type": "일반"}])
    assert d["years"] == [Y - 3, Y - 2, Y - 1, Y, Y + 1]
    assert d["current_year"] == Y
    assert d["full_proj_year"] == Y + 1
    assert d["default_year"] == Y
    # 과거 3년 = 전부 실적
    for y in (Y - 3, Y - 2, Y - 1):
        assert d["events"][y] and all(not e["projected"] for e in d["events"][y])
    # 내년 = 전부 예측
    assert d["events"][Y + 1] and all(e["projected"] for e in d["events"][Y + 1])


def test_current_year_mixed():
    # 올해는 실적(앞쪽 달) + 예측(이후 달) 혼합
    d = build_dividend_chart(L, [{"code": "SCHD", "quantity": 100, "account_type": "일반"}])
    cur = d["events"][Y]
    assert cur
    reals = [e for e in cur if not e["projected"]]
    projs = [e for e in cur if e["projected"]]
    assert reals, "올해 실데이터(실적) 이벤트가 있어야 함"
    assert projs, "올해 남은 달 예측 이벤트가 있어야 함"
    # 실적 이벤트의 달 < 예측 이벤트의 달 (경계 = 이번 달)
    assert max(e["month"] for e in reals) <= min(e["month"] for e in projs)


def test_event_fields():
    d = build_dividend_chart(L, [{"code": "458730", "quantity": 10, "account_type": "일반"}])
    ev = d["events"][Y - 1][0]
    for k in ("date", "month", "day", "code", "name", "krw_pre", "krw_post", "usd_pre", "usd_post", "projected"):
        assert k in ev


def test_kr_general_tax_154():
    d = build_dividend_chart(L, [{"code": "458730", "quantity": 10, "account_type": "일반"}])
    evs = d["events"][Y - 1]
    assert evs and _sum(evs, "krw_pre") > 0
    assert _sum(evs, "krw_post") == pytest.approx(_sum(evs, "krw_pre") * (1 - 0.154), rel=1e-6)


def test_isa_exempt():
    d = build_dividend_chart(L, [{"code": "458730", "quantity": 10, "account_type": "ISA"}])
    evs = d["events"][Y - 1]
    assert evs and _sum(evs, "krw_post") == pytest.approx(_sum(evs, "krw_pre"), rel=1e-9)


def test_us_tax_15_and_fx():
    d = build_dividend_chart(L, [{"code": "SCHD", "quantity": 100, "account_type": "일반"}])
    assert d["has_foreign"] is True
    evs = d["events"][Y - 1]
    assert evs and _sum(evs, "usd_pre") > 0
    assert _sum(evs, "usd_post") == pytest.approx(_sum(evs, "usd_pre") * (1 - 0.15), rel=1e-6)
    assert _sum(evs, "krw_pre") > _sum(evs, "usd_pre") * 1000
    assert evs[0]["name"]


def test_gold_skipped():
    d = build_dividend_chart(L, [{"code": "KRX_GOLD", "quantity": 5, "account_type": "일반"}])
    assert all(len(d["events"][y]) == 0 for y in d["years"])
