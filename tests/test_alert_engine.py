"""
alert_engine 순수 함수 결정론 테스트 — 전 룰타입 + 쿨다운/재무장.
실행: python -m pytest tests/test_alert_engine.py -q
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.alerts.alert_engine import evaluate_rule, cooldown_ok

NOW = datetime(2026, 6, 17, 14, 0, 0)


def _rule(**kw):
    base = {"enabled": 1, "cooldown_h": 24, "last_triggered_at": None,
            "last_extreme": None, "code": "TSLA"}
    base.update(kw)
    return base


# ── daily_pct ─────────────────────────────────────────

def test_daily_pct_up_hit():
    r = _rule(rule_type="daily_pct", direction="up", threshold=5)
    ev = evaluate_rule(r, {"cur": 110, "change_pct": 6.0, "currency": "USD"}, NOW)
    assert ev and "6.00%" in ev["title"]


def test_daily_pct_up_miss():
    r = _rule(rule_type="daily_pct", direction="up", threshold=5)
    assert evaluate_rule(r, {"cur": 110, "change_pct": 3.0}, NOW) is None


def test_daily_pct_down_hit():
    r = _rule(rule_type="daily_pct", direction="down", threshold=5)
    assert evaluate_rule(r, {"cur": 90, "change_pct": -7.0}, NOW) is not None


def test_daily_pct_down_ignores_up():
    r = _rule(rule_type="daily_pct", direction="down", threshold=5)
    assert evaluate_rule(r, {"cur": 110, "change_pct": 8.0}, NOW) is None


def test_daily_pct_both():
    r = _rule(rule_type="daily_pct", direction="both", threshold=5)
    assert evaluate_rule(r, {"cur": 90, "change_pct": -6.0}, NOW) is not None
    assert evaluate_rule(r, {"cur": 110, "change_pct": 6.0}, NOW) is not None


# ── target_price ──────────────────────────────────────

def test_target_above_hit():
    r = _rule(rule_type="target_price", direction="above", threshold=100)
    assert evaluate_rule(r, {"cur": 105, "currency": "USD"}, NOW) is not None


def test_target_above_miss():
    r = _rule(rule_type="target_price", direction="above", threshold=100)
    assert evaluate_rule(r, {"cur": 95}, NOW) is None


def test_target_below_hit():
    r = _rule(rule_type="target_price", direction="below", threshold=100)
    assert evaluate_rule(r, {"cur": 95}, NOW) is not None


# ── new_high / new_low ────────────────────────────────

def test_new_high_hit():
    r = _rule(rule_type="new_high", window="52w")
    ev = evaluate_rule(r, {"cur": 450, "high": 440, "low": 100}, NOW)
    assert ev and ev["new_extreme"] == 450 and "신고가" in ev["title"]


def test_new_high_miss_below_prior():
    r = _rule(rule_type="new_high", window="52w")
    assert evaluate_rule(r, {"cur": 430, "high": 440, "low": 100}, NOW) is None


def test_new_high_rearm_blocks_same_level():
    # 직전 고점 450 기록됨 → 동일/낮은 값 재발화 금지
    r = _rule(rule_type="new_high", window="all", last_extreme=450)
    assert evaluate_rule(r, {"cur": 445, "high": 440}, NOW) is None
    assert evaluate_rule(r, {"cur": 460, "high": 440}, NOW) is not None


def test_new_low_hit():
    r = _rule(rule_type="new_low", window="all")
    ev = evaluate_rule(r, {"cur": 80, "high": 440, "low": 100}, NOW)
    assert ev and ev["new_extreme"] == 80 and "신저가" in ev["title"]


# ── rebalance_band ────────────────────────────────────

def test_rebalance_breach():
    r = _rule(rule_type="rebalance_band", scope="portfolio", code=None, threshold=5)
    ctx = {"groups": [
        {"name": "주식", "current_pct": 72, "target_pct": 60},
        {"name": "채권", "current_pct": 28, "target_pct": 40},
    ]}
    ev = evaluate_rule(r, ctx, NOW)
    assert ev and "리밸런싱" in ev["title"] and len(ev["meta"]["breaches"]) == 2


def test_rebalance_within_band():
    r = _rule(rule_type="rebalance_band", scope="portfolio", threshold=5)
    ctx = {"groups": [{"name": "주식", "current_pct": 62, "target_pct": 60}]}
    assert evaluate_rule(r, ctx, NOW) is None


def test_rebalance_ignores_zero_target():
    r = _rule(rule_type="rebalance_band", scope="portfolio", threshold=5)
    ctx = {"groups": [{"name": "미분류", "current_pct": 30, "target_pct": 0}]}
    assert evaluate_rule(r, ctx, NOW) is None


# ── 쿨다운 ─────────────────────────────────────────────

def test_cooldown_blocks_recent():
    recent = (NOW - timedelta(hours=2)).isoformat()
    r = _rule(rule_type="daily_pct", direction="up", threshold=5,
              cooldown_h=24, last_triggered_at=recent)
    assert evaluate_rule(r, {"cur": 110, "change_pct": 9.0}, NOW) is None


def test_cooldown_allows_after_window():
    old = (NOW - timedelta(hours=30)).isoformat()
    r = _rule(rule_type="daily_pct", direction="up", threshold=5,
              cooldown_h=24, last_triggered_at=old)
    assert evaluate_rule(r, {"cur": 110, "change_pct": 9.0}, NOW) is not None


def test_disabled_rule_never_fires():
    r = _rule(rule_type="daily_pct", direction="up", threshold=5, enabled=0)
    assert evaluate_rule(r, {"cur": 110, "change_pct": 9.0}, NOW) is None


def test_cooldown_ok_no_history():
    assert cooldown_ok(_rule(), NOW) is True
