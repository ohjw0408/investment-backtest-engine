"""
tests/test_scenario_data_preparer.py
──────────────────────────────────────────────────────────────────────────────
prepare_scenario_data 단위 테스트 (Phase 10)

테스트 전략:
  - DB 접근 mock → 실제 price_daily.db 불필요
  - allow_synthetic=False 경로: 직접 DB 조회 + backfill
  - allow_synthetic=True  경로: DataPreparer 위임
  - 반환 dict 필드 검증
  - data_confidence 값 검증
  - requested_start → required_years 자동 계산 검증
"""

from __future__ import annotations

import sqlite3
import tempfile
import os
import sys
from pathlib import Path
from datetime import date

import pytest
import pandas as pd

# 프로젝트 루트 경로 추가
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from modules.data_preparation.scenario_data_preparer import (
    prepare_scenario_data,
    _calc_rolling_cases,
    _data_confidence,
)


# ─── 헬퍼: 인메모리 DB 생성 ────────────────────────────────────────────────────

def _make_db(rows: dict[str, list[tuple[str, float]]]) -> str:
    """code -> [(date, close), ...] 로부터 임시 price_daily.db 생성. 경로 반환."""
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE price_daily (code TEXT, date TEXT, close REAL)"
    )
    for code, data in rows.items():
        conn.executemany(
            "INSERT INTO price_daily(code,date,close) VALUES (?,?,?)",
            [(code, d, c) for d, c in data],
        )
    conn.commit()
    conn.close()
    return tmp


def _daily_range(start: str, end: str, close: float = 100.0) -> list[tuple[str, float]]:
    """영업일 아닌 단순 daily range."""
    dates = pd.date_range(start, end, freq="D")
    return [(d.strftime("%Y-%m-%d"), close) for d in dates]


# ─── _calc_rolling_cases 테스트 ────────────────────────────────────────────────

class TestCalcRollingCases:
    def test_basic_10yr(self):
        # 1990-01-01 ~ 2010-01-01 = 20년, 10년 시뮬, step=3개월
        # start 1990-01-01 ~ 2000-01-01 모두 유효 (inclusive both ends)
        # 10년 = 40 quarters → 41개 시작점
        n = _calc_rolling_cases("1990-01-01", "2010-01-01", sim_years=10, step_months=3)
        assert n == 41, f"expected 41, got {n}"

    def test_exact_fit(self):
        # 딱 sim_years 만큼만 있으면 케이스 1개
        n = _calc_rolling_cases("2000-01-01", "2005-01-01", sim_years=5, step_months=3)
        assert n == 1

    def test_too_short(self):
        # 데이터가 sim_years 미만 → 0
        n = _calc_rolling_cases("2020-01-01", "2022-01-01", sim_years=5, step_months=3)
        assert n == 0

    def test_step1month(self):
        # 1990-01-01 ~ 1991-01-01 = 1년, 1년 시뮬, step=1 → 1케이스
        n = _calc_rolling_cases("1990-01-01", "1991-01-01", sim_years=1, step_months=1)
        assert n == 1


# ─── _data_confidence 테스트 ──────────────────────────────────────────────────

class TestDataConfidence:
    def test_actual(self):
        assert _data_confidence([], {}) == "actual"

    def test_backfilled(self):
        assert _data_confidence(["SCHD"], {}) == "backfilled"

    def test_synthetic(self):
        assert _data_confidence([], {"SCHD": {}}) == "synthetic"

    def test_synthetic_wins(self):
        # 둘 다 있으면 synthetic
        assert _data_confidence(["SCHD"], {"SCHD": {}}) == "synthetic"


# ─── prepare_scenario_data allow_synthetic=False 경로 ────────────────────────

class TestPrepareSyntheticFalse:
    """allow_synthetic=False 경로: DB에서 직접 조회, DataPreparer 호출 없음."""

    def test_returns_expected_keys(self):
        db = _make_db({"SCHD": _daily_range("1990-01-01", "2025-01-01")})
        try:
            result = prepare_scenario_data(
                tickers=["SCHD"],
                required_years=10,
                data_end="2025-01-01",
                allow_backfill=False,
                allow_synthetic=False,
                price_db_path=db,
            )
            expected_keys = {
                "data_start", "data_end", "effective_start", "requested_start",
                "n_cases", "backfilled", "synthetic_info", "data_confidence",
                "used_synthetic", "warnings",
            }
            assert expected_keys.issubset(set(result.keys()))
        finally:
            os.unlink(db)

    def test_used_synthetic_false(self):
        db = _make_db({"SCHD": _daily_range("1990-01-01", "2025-01-01")})
        try:
            result = prepare_scenario_data(
                tickers=["SCHD"],
                required_years=5,
                data_end="2025-01-01",
                allow_backfill=False,
                allow_synthetic=False,
                price_db_path=db,
            )
            assert result["used_synthetic"] is False
            assert result["synthetic_info"] == {}
        finally:
            os.unlink(db)

    def test_effective_start_is_max(self):
        """effective_start = max(ticker starts)."""
        db = _make_db({
            "AAA": _daily_range("1980-01-01", "2025-01-01"),
            "BBB": _daily_range("2000-01-01", "2025-01-01"),
        })
        try:
            result = prepare_scenario_data(
                tickers=["AAA", "BBB"],
                required_years=5,
                data_end="2025-01-01",
                allow_backfill=False,
                allow_synthetic=False,
                price_db_path=db,
            )
            # effective_start should be capped at BBB's start (later one)
            assert result["effective_start"] >= "2000-01-01"
        finally:
            os.unlink(db)

    def test_data_start_is_min(self):
        """data_start = min(ticker starts)."""
        db = _make_db({
            "AAA": _daily_range("1980-01-01", "2025-01-01"),
            "BBB": _daily_range("2000-01-01", "2025-01-01"),
        })
        try:
            result = prepare_scenario_data(
                tickers=["AAA", "BBB"],
                required_years=5,
                data_end="2025-01-01",
                allow_backfill=False,
                allow_synthetic=False,
                price_db_path=db,
            )
            assert result["data_start"] == "1980-01-01"
        finally:
            os.unlink(db)

    def test_data_confidence_actual(self):
        db = _make_db({"SCHD": _daily_range("1990-01-01", "2025-01-01")})
        try:
            result = prepare_scenario_data(
                tickers=["SCHD"],
                required_years=5,
                data_end="2025-01-01",
                allow_backfill=False,
                allow_synthetic=False,
                price_db_path=db,
            )
            assert result["data_confidence"] == "actual"
        finally:
            os.unlink(db)

    def test_n_cases_none_when_no_required_years(self):
        db = _make_db({"SCHD": _daily_range("1990-01-01", "2025-01-01")})
        try:
            result = prepare_scenario_data(
                tickers=["SCHD"],
                required_years=None,
                data_end="2025-01-01",
                allow_backfill=False,
                allow_synthetic=False,
                price_db_path=db,
            )
            assert result["n_cases"] is None
        finally:
            os.unlink(db)

    def test_requested_start_auto_required_years(self):
        """requested_start 있으면 required_years 자동 계산 → n_cases 계산됨."""
        db = _make_db({"SCHD": _daily_range("1990-01-01", "2025-01-01")})
        try:
            result = prepare_scenario_data(
                tickers=["SCHD"],
                requested_start="2010-01-01",
                data_end="2025-01-01",
                allow_backfill=False,
                allow_synthetic=False,
                price_db_path=db,
            )
            # requested_start → required_years=15 → n_cases != None
            assert result["n_cases"] is not None
            assert result["n_cases"] > 0
        finally:
            os.unlink(db)

    def test_no_data_raises(self):
        db = _make_db({})  # empty
        try:
            with pytest.raises(ValueError, match="가격 데이터가 없는 종목"):
                prepare_scenario_data(
                    tickers=["NOPE"],
                    required_years=5,
                    data_end="2025-01-01",
                    allow_backfill=False,
                    allow_synthetic=False,
                    price_db_path=db,
                )
        finally:
            os.unlink(db)

    def test_data_end_defaults_to_today(self):
        db = _make_db({"SCHD": _daily_range("1990-01-01", "2025-01-01")})
        try:
            result = prepare_scenario_data(
                tickers=["SCHD"],
                required_years=5,
                allow_backfill=False,
                allow_synthetic=False,
                price_db_path=db,
            )
            today = date.today().isoformat()
            assert result["data_end"] == today
        finally:
            os.unlink(db)


# ─── prepare_scenario_data allow_synthetic=True 경로 ─────────────────────────

class TestPrepareSyntheticTrue:
    """allow_synthetic=True 경로: DataPreparer 위임. DataPreparer를 mock."""

    def test_delegates_to_data_preparer(self, monkeypatch):
        """DataPreparer.prepare() 호출 여부 확인."""
        called = {}

        class FakeDataPreparer:
            def __init__(self, price_db_path, verbose):
                called["init"] = True

            def prepare(self, tickers, sim_years, data_end, step_months,
                        allow_backfill, allow_synthetic):
                called["prepare"] = {
                    "tickers": tickers, "sim_years": sim_years,
                    "allow_synthetic": allow_synthetic,
                }
                return {
                    "data_start":     "1990-01-01",
                    "n_cases":        50,
                    "synthetic_info": {},
                    "backfilled":     [],
                    "used_synthetic": False,
                    "warnings":       [],
                }

            def close(self):
                called["close"] = True

        import modules.data_preparation.scenario_data_preparer as mod
        monkeypatch.setattr(
            "modules.retirement.data_preparer.DataPreparer",
            FakeDataPreparer,
        )
        # monkeypatch the import inside prepare_scenario_data
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else None

        # Simpler: patch the module-level import path used in the function
        import unittest.mock as mock
        with mock.patch("modules.data_preparation.scenario_data_preparer.DataPreparer",
                        FakeDataPreparer, create=True):
            # Need to also patch the actual import inside the function
            with mock.patch.dict("sys.modules", {
                "modules.retirement.data_preparer": type(sys)("fake"),
            }):
                sys.modules["modules.retirement.data_preparer"].DataPreparer = FakeDataPreparer
                result = prepare_scenario_data(
                    tickers=["SCHD"],
                    required_years=10,
                    data_end="2025-01-01",
                    allow_backfill=True,
                    allow_synthetic=True,
                )

        assert "prepare" in called, "DataPreparer.prepare() not called"
        assert called["prepare"]["allow_synthetic"] is True

    def test_requires_required_years(self):
        """allow_synthetic=True 시 required_years 없으면 ValueError."""
        with pytest.raises(ValueError, match="required_years 필수"):
            prepare_scenario_data(
                tickers=["SCHD"],
                required_years=None,
                allow_synthetic=True,
            )

    def test_return_keys_present(self, monkeypatch):
        """반환 dict에 필수 키 모두 있는지."""
        import unittest.mock as mock

        fake_result = {
            "data_start":     "2000-01-01",
            "n_cases":        40,
            "synthetic_info": {"SCHD": {"date_from": "2000-01-01", "date_to": "2005-01-01",
                                         "rows_added": 1000, "confidence": "D",
                                         "source_type": "synthetic", "method": "synthetic_gbm_v1"}},
            "backfilled":     [],
            "used_synthetic": True,
            "warnings":       [],
        }

        class FakeDP:
            def __init__(self, **kw): pass
            def prepare(self, **kw): return fake_result
            def close(self): pass

        with mock.patch.dict("sys.modules", {
            "modules.retirement.data_preparer": type(sys)("fake"),
        }):
            sys.modules["modules.retirement.data_preparer"].DataPreparer = FakeDP
            result = prepare_scenario_data(
                tickers=["SCHD"],
                required_years=5,
                data_end="2025-01-01",
                allow_synthetic=True,
            )

        expected_keys = {
            "data_start", "data_end", "effective_start", "requested_start",
            "n_cases", "backfilled", "synthetic_info", "data_confidence",
            "used_synthetic", "warnings",
        }
        assert expected_keys.issubset(set(result.keys()))
        assert result["used_synthetic"] is True
        assert result["data_confidence"] == "synthetic"


# ─── 실행 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], check=False)
