"""
tests/test_synthetic_anchor_fx.py
──────────────────────────────────────────────────────────────────────────────
BUG-DIV-3 회귀 (계산기 윈도우 합성 경로).

_load_with_per_window_synthetic 가 합성 prefix를 stitch할 때 anchor를
data_preparer의 raw USD 값(params["anchor_price"])으로 잡으면, 실 suffix는
get_price 의 FX(KRW) 값이라 actual_start 경계에서 ~환율배(약 1,300배) 가격
점프가 생기고 buy-hold 시뮬이 폭발한다(실측: 40년 GLD 70,679배, 포트 2.9조).

수정: anchor를 actual_start의 FX 실가격으로 잡아 연속성 보장.
이 테스트는 경계에서 비현실적 가격 점프가 없음을 검증한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import types

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from modules.retirement.accumulation_analyzer import AccumulationAnalyzer

FX = 1300.0            # USD→KRW 배율 (실 suffix는 이 단위)
ACTUAL_START = "2003-11-07"
ANCHOR_USD = 7.0       # data_preparer가 넘기는 raw USD anchor


class _FakeLoader:
    """actual_start 이후만 실데이터(FX·KRW) 반환. 그 이전은 빈 df."""
    def get_price(self, code, start, end, allow_synthetic=False):
        s = max(pd.Timestamp(start), pd.Timestamp(ACTUAL_START))
        e = pd.Timestamp(end)
        idx = pd.bdate_range(s, e)
        if len(idx) == 0:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "dividend", "split"])
        close = np.full(len(idx), ANCHOR_USD * FX)   # KRW 실가격 (≈9100)
        return pd.DataFrame({
            "date": idx.strftime("%Y-%m-%d"),
            "open": close, "high": close, "low": close, "close": close,
            "volume": np.zeros(len(idx)), "dividend": np.zeros(len(idx)), "split": np.ones(len(idx)),
        })


def _make_dummy():
    return types.SimpleNamespace(
        tickers=["SCHD"],
        synthetic_params={"SCHD": {
            "mu_monthly": 0.008, "sigma_monthly": 0.04,
            "actual_start": ACTUAL_START, "anchor_price": ANCHOR_USD,  # raw USD (틀린 단위)
        }},
        portfolio_engine=types.SimpleNamespace(
            price_loader=types.SimpleNamespace(loader=_FakeLoader())
        ),
    )


def test_no_fx_boundary_explosion():
    dummy = _make_dummy()
    method = AccumulationAnalyzer._load_with_per_window_synthetic
    combined, dates = method(dummy, pd.Timestamp("1995-01-02"), pd.Timestamp("2010-01-01"))
    assert "SCHD" in combined
    close = combined["SCHD"]["close"].dropna().values
    assert len(close) > 100
    # 연속 일간 비율: 경계에 ~FX배(1300x) 점프가 있으면 안 됨
    ratios = close[1:] / np.where(close[:-1] > 0, close[:-1], 1.0)
    max_jump = float(np.nanmax(ratios))
    assert max_jump < 5.0, f"boundary price jump too large (~FX mismatch): {max_jump:.1f}x"
    # 합성 prefix가 실 suffix와 같은 KRW 단위(≈9100)인지 — prefix 가격이 USD(≈7)이면 실패
    synth_prefix = combined["SCHD"].loc[combined["SCHD"].index < pd.Timestamp(ACTUAL_START), "close"].dropna()
    assert not synth_prefix.empty
    assert synth_prefix.median() > 100, f"synthetic prefix not in KRW units: median={synth_prefix.median():.1f}"
