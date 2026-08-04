# -*- coding: utf-8 -*-
"""백필 손상 스캐너(scripts/scan_backfill_corruption) 판정 회귀.

핵심 회귀 = 실데이터가 사실상 정지한 종목(만기매칭형 회사채 ETF)의 정상 합성이
분모≈0 때문에 매일 CORRUPT로 잡히던 오탐(2026-08-04).
"""
import os
import sqlite3
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from scan_backfill_corruption import scan_code  # noqa: E402


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE price_daily (code TEXT, date TEXT, close REAL, volume REAL)")
    return conn


def _insert(conn, code, n_synth, synth_std, n_real, real_std, seed=0, synth_jump=None):
    """합성(volume=0) n_synth행 + 실데이터(volume>0) n_real행을 연속 거래일로 넣는다."""
    rng = np.random.default_rng(seed)
    rows = []
    d = np.datetime64("2000-01-03")
    price = 10000.0
    for i in range(n_synth + n_real):
        is_synth = i < n_synth
        std = synth_std if is_synth else real_std
        ret = float(rng.normal(0.0, std))
        if synth_jump is not None and i == n_synth // 2:
            ret = synth_jump
        price *= (1.0 + ret)
        rows.append((code, str(d), price, 0 if is_synth else 1000))
        d += np.timedelta64(1, "D")
    conn.executemany("INSERT INTO price_daily VALUES (?,?,?,?)", rows)
    conn.commit()


def test_frozen_real_series_does_not_flag_normal_synth():
    """만기매칭형 회사채 ETF: 실 std 0.0007(정지) + 합성 std 0.0031(정상 채권 수준) → OK."""
    conn = _conn()
    _insert(conn, "0001S0", n_synth=600, synth_std=0.0031, n_real=300, real_std=0.0007)
    r = scan_code(conn, "0001S0")
    assert r is not None
    assert r["real_std"] < 0.0018          # 하한 아래 = 분모 무의미 구간
    assert r["vol_ratio"] < 2.5
    assert r["corrupt"] is False


def test_frozen_real_series_still_flags_broken_synth():
    """같은 분모라도 합성이 진짜 망가지면(SHY 구손상 수준) 잡힌다."""
    conn = _conn()
    _insert(conn, "SHY", n_synth=600, synth_std=0.016, n_real=300, real_std=0.0008)
    r = scan_code(conn, "SHY")
    assert r["vol_ratio"] > 2.5
    assert r["corrupt"] is True


def test_normal_equity_synth_ok():
    conn = _conn()
    _insert(conn, "SPY", n_synth=600, synth_std=0.011, n_real=300, real_std=0.010)
    assert scan_code(conn, "SPY")["corrupt"] is False


def test_single_day_jump_flags():
    conn = _conn()
    _insert(conn, "0046A0", n_synth=600, synth_std=0.002, n_real=300, real_std=0.002,
            synth_jump=0.60)
    r = scan_code(conn, "0046A0")
    assert r["max_daily_ret"] > 0.5
    assert r["corrupt"] is True


def test_nonpositive_close_flags():
    conn = _conn()
    _insert(conn, "BAD", n_synth=600, synth_std=0.002, n_real=300, real_std=0.002)
    conn.execute("UPDATE price_daily SET close=0 WHERE code='BAD' AND rowid IN "
                 "(SELECT rowid FROM price_daily WHERE code='BAD' AND volume=0 LIMIT 1)")
    conn.commit()
    r = scan_code(conn, "BAD")
    assert r["nonpos_rows"] == 1
    assert r["corrupt"] is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
