import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from modules.price_loader import _drop_isolated_price_spikes, PriceLoader


def test_drop_isolated_one_day_high_spike():
    df = pd.DataFrame(
        [
            {"date": "2026-06-16", "open": 750.0, "high": 760.0, "low": 740.0, "close": 750.0, "volume": 1},
            {"date": "2026-06-17", "open": 332000.0, "high": 348000.0, "low": 331500.0, "close": 346500.0, "volume": 1},
            {"date": "2026-06-18", "open": 746.0, "high": 748.0, "low": 743.0, "close": 746.0, "volume": 1},
        ]
    )

    out = _drop_isolated_price_spikes(df)

    assert out["date"].tolist() == ["2026-06-16", "2026-06-18"]


def test_keep_persistent_price_level_change():
    df = pd.DataFrame(
        [
            {"date": "2026-06-16", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1},
            {"date": "2026-06-17", "open": 2600.0, "high": 2620.0, "low": 2590.0, "close": 2600.0, "volume": 1},
            {"date": "2026-06-18", "open": 2700.0, "high": 2720.0, "low": 2690.0, "close": 2700.0, "volume": 1},
        ]
    )

    out = _drop_isolated_price_spikes(df)

    assert out["date"].tolist() == ["2026-06-16", "2026-06-17", "2026-06-18"]


def test_purge_isolated_spikes_deletes_otick_from_db():
    # 근본 클린업: DB에 박힌 고립 오틱 행을 실제 DELETE, 정상 행은 보존.
    pl = PriceLoader.__new__(PriceLoader)  # __init__(실 DB 연결) 우회
    pl.conn = sqlite3.connect(":memory:")
    pl.conn.execute("CREATE TABLE price_daily (code TEXT, date TEXT, close REAL)")
    base = datetime.now() - timedelta(days=10)
    rows = []
    for i in range(6):
        d = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        rows.append(("SPY", d, 346500.0 if i == 3 else 750.0 + i))  # day3 = 오틱
    pl.conn.executemany("INSERT INTO price_daily VALUES (?,?,?)", rows)
    pl.conn.commit()
    otick = (base + timedelta(days=3)).strftime("%Y-%m-%d")

    deleted = pl.purge_isolated_spikes(days=120)

    remaining = {d for (d,) in pl.conn.execute("SELECT date FROM price_daily WHERE code='SPY'")}
    assert deleted == 1
    assert otick not in remaining
    assert len(remaining) == 5


def test_validate_price_rows_filters_poison_rows():
    # B-2① 단일 검증 훅: NULL close·0/음수가·미래날짜 행 차단, 정상 행 보존.
    from modules.price_loader import _validate_price_rows
    future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    df = pd.DataFrame(
        [
            {"date": "2026-06-16", "close": 100.0},
            {"date": "2026-06-17", "close": None},    # NULL홀 근원
            {"date": "2026-06-18", "close": 0.0},     # 0가
            {"date": "2026-06-19", "close": -5.0},    # 음수가
            {"date": "2026-06-20", "close": 101.0},
            {"date": future, "close": 102.0},         # 미래날짜
        ]
    )

    out = _validate_price_rows(df)

    assert out["date"].tolist() == ["2026-06-16", "2026-06-20"]


def test_validate_price_rows_clean_data_unchanged():
    # 결과 불변: 정상 데이터는 값·순서 그대로 통과.
    from modules.price_loader import _validate_price_rows
    df = pd.DataFrame(
        [
            {"date": "2026-06-16", "close": 100.0},
            {"date": "2026-06-17", "close": 101.5},
            {"date": "2026-06-18", "close": 99.8},
        ]
    )

    out = _validate_price_rows(df)

    assert out["close"].tolist() == [100.0, 101.5, 99.8]
    assert out["date"].tolist() == df["date"].tolist()


def test_upsert_actions_real_value_beats_placeholder():
    # B-3: 자리표시(dividend=0) 선점 행을 실값이 이기고, 기존 실값은 보존.
    pl = PriceLoader.__new__(PriceLoader)
    pl.conn = sqlite3.connect(":memory:")
    pl.conn.execute("CREATE TABLE corporate_actions (code TEXT, date TEXT, dividend REAL, split REAL, PRIMARY KEY (code, date))")
    pl.conn.execute("INSERT INTO corporate_actions VALUES ('TLT','2026-04-01',0.0,1.0)")    # 자리표시 선점
    pl.conn.execute("INSERT INTO corporate_actions VALUES ('TLT','2026-05-01',0.315,1.0)")  # 기존 실값
    pl.conn.execute("INSERT INTO corporate_actions VALUES ('AAPL','2026-06-10',0.0,1.0)")   # 스플릿 자리표시
    df = pd.DataFrame([
        {"code": "TLT",  "date": "2026-04-01", "dividend": 0.345, "split": 1.0},  # 실값 → 갱신
        {"code": "TLT",  "date": "2026-05-01", "dividend": 0.0,   "split": 1.0},  # 자리표시 → 기존 보존
        {"code": "TLT",  "date": "2026-06-01", "dividend": 0.336, "split": 1.0},  # 신규 insert
        {"code": "AAPL", "date": "2026-06-10", "dividend": 0.0,   "split": 4.0},  # 실스플릿 → 갱신
    ])

    pl._upsert_actions(df)

    got = {(c, d): (div, sp) for c, d, div, sp in
           pl.conn.execute("SELECT code, date, dividend, split FROM corporate_actions").fetchall()}
    assert got[("TLT", "2026-04-01")] == (0.345, 1.0)
    assert got[("TLT", "2026-05-01")] == (0.315, 1.0)
    assert got[("TLT", "2026-06-01")] == (0.336, 1.0)
    assert got[("AAPL", "2026-06-10")] == (0.0, 4.0)
