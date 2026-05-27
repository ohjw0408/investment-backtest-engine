"""
modules/provenance.py
────────────────────────────────────────────────────────────────────────────────
ETF 백필/합성 데이터 Provenance 추적 유틸리티 (Phase 2)

목적:
  - 생성된 가격/배당 데이터의 출처, 방법, 신뢰도를 추적
  - 특정 run_id로 생성된 데이터를 안전하게 삭제·재생성
  - 실측 데이터와 생성 데이터를 구분

테이블:
  backfill_runs          — 백필 실행 메타데이터 (1 실행 = 1 행)
  price_daily_source     — 가격 행별 출처 (code, date PRIMARY KEY)
  corporate_action_source — 배당 행별 출처 (code, date, action_type PRIMARY KEY)
"""

from __future__ import annotations

import sqlite3
import uuid
import datetime
from typing import Optional


MODEL_VERSION_BACKFILL  = "backfill_engine_v1"
MODEL_VERSION_SYNTHETIC = "synthetic_gbm_v1"


def ensure_provenance_tables(conn: sqlite3.Connection) -> None:
    """3개 provenance 테이블을 idempotent하게 생성."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS backfill_runs (
            run_id       TEXT PRIMARY KEY,
            code         TEXT NOT NULL,
            started_at   TEXT NOT NULL,
            finished_at  TEXT,
            status       TEXT,
            method       TEXT,
            model_version TEXT,
            proxy_code   TEXT,
            confidence   TEXT,
            date_from    TEXT,
            date_to      TEXT,
            rows_written INTEGER,
            div_rows_written INTEGER,
            fx_applied   INTEGER,
            leverage     REAL,
            error        TEXT
        );

        CREATE TABLE IF NOT EXISTS price_daily_source (
            code          TEXT NOT NULL,
            date          TEXT NOT NULL,
            source_type   TEXT,
            source_code   TEXT,
            run_id        TEXT,
            model_version TEXT,
            confidence    TEXT,
            PRIMARY KEY (code, date)
        );

        CREATE TABLE IF NOT EXISTS corporate_action_source (
            code          TEXT NOT NULL,
            date          TEXT NOT NULL,
            action_type   TEXT NOT NULL DEFAULT 'dividend',
            source_type   TEXT,
            source_code   TEXT,
            run_id        TEXT,
            model_version TEXT,
            confidence    TEXT,
            PRIMARY KEY (code, date, action_type)
        );
    """)
    conn.commit()


def new_run_id() -> str:
    """UUID4 기반 run_id 생성."""
    return str(uuid.uuid4())


def write_backfill_run(
    conn:          sqlite3.Connection,
    run_id:        str,
    code:          str,
    status:        str,
    method:        str,
    model_version: str,
    proxy_code:    Optional[str] = None,
    confidence:    Optional[str] = None,
    date_from:     Optional[str] = None,
    date_to:       Optional[str] = None,
    rows_written:  int = 0,
    div_rows_written: int = 0,
    fx_applied:    bool = False,
    leverage:      float = 1.0,
    error:         Optional[str] = None,
) -> None:
    """backfill_runs 테이블에 실행 기록 삽입."""
    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO backfill_runs
          (run_id, code, started_at, finished_at, status, method, model_version,
           proxy_code, confidence, date_from, date_to, rows_written,
           div_rows_written, fx_applied, leverage, error)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            run_id, code, now, now, status, method, model_version,
            proxy_code, confidence, date_from, date_to, rows_written,
            div_rows_written, int(fx_applied), leverage, error,
        ),
    )
    conn.commit()


def write_price_source(
    conn:          sqlite3.Connection,
    run_id:        str,
    code:          str,
    dates:         list[str],
    source_type:   str,
    source_code:   Optional[str] = None,
    model_version: Optional[str] = None,
    confidence:    Optional[str] = None,
) -> None:
    """price_daily_source에 날짜 목록 일괄 삽입 (OR IGNORE — 실측 우선)."""
    rows = [
        (code, d, source_type, source_code, run_id, model_version, confidence)
        for d in dates
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO price_daily_source
          (code, date, source_type, source_code, run_id, model_version, confidence)
        VALUES (?,?,?,?,?,?,?)
        """,
        rows,
    )
    conn.commit()


def write_action_source(
    conn:          sqlite3.Connection,
    run_id:        str,
    code:          str,
    dates:         list[str],
    source_type:   str,
    action_type:   str = "dividend",
    source_code:   Optional[str] = None,
    model_version: Optional[str] = None,
    confidence:    Optional[str] = None,
) -> None:
    """corporate_action_source에 날짜 목록 일괄 삽입."""
    rows = [
        (code, d, action_type, source_type, source_code, run_id, model_version, confidence)
        for d in dates
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO corporate_action_source
          (code, date, action_type, source_type, source_code, run_id, model_version, confidence)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    conn.commit()


def delete_by_run_id(conn: sqlite3.Connection, run_id: str) -> dict:
    """
    특정 run_id로 생성된 가격·배당 데이터를 안전하게 삭제.
    실측(actual) 데이터는 건드리지 않음.

    Returns
    -------
    dict: {"price_rows": int, "div_rows": int}
    """
    # 가격 삭제
    conn.execute(
        """
        DELETE FROM price_daily
        WHERE (code, date) IN (
            SELECT code, date FROM price_daily_source
            WHERE run_id = ? AND source_type != 'actual'
        )
        """,
        (run_id,),
    )
    price_deleted = conn.execute("SELECT changes()").fetchone()[0]

    # 배당 삭제
    conn.execute(
        """
        DELETE FROM corporate_actions
        WHERE (code, date) IN (
            SELECT code, date FROM corporate_action_source
            WHERE run_id = ? AND source_type != 'actual'
        )
        """,
        (run_id,),
    )
    div_deleted = conn.execute("SELECT changes()").fetchone()[0]

    # provenance 레코드도 정리
    conn.execute("DELETE FROM price_daily_source WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM corporate_action_source WHERE run_id = ?", (run_id,))
    conn.execute("UPDATE backfill_runs SET status = 'deleted' WHERE run_id = ?", (run_id,))
    conn.commit()

    return {"price_rows": price_deleted, "div_rows": div_deleted}


def is_generated(conn: sqlite3.Connection, code: str, date: str) -> bool:
    """
    해당 (code, date) 가격 행이 생성된 데이터인지 반환.
    provenance 미기록(레거시) 행은 volume=0이면 generated로 간주.
    """
    row = conn.execute(
        "SELECT source_type FROM price_daily_source WHERE code=? AND date=?",
        (code, date),
    ).fetchone()
    if row:
        return row[0] != "actual"
    # 레거시 fallback: volume=0이면 generated
    vol_row = conn.execute(
        "SELECT volume FROM price_daily WHERE code=? AND date=?",
        (code, date),
    ).fetchone()
    return bool(vol_row and vol_row[0] == 0)


def get_run_summary(conn: sqlite3.Connection, code: str) -> list[dict]:
    """특정 코드의 backfill 실행 기록 요약."""
    rows = conn.execute(
        """
        SELECT run_id, method, model_version, confidence,
               date_from, date_to, rows_written, div_rows_written, status
        FROM backfill_runs
        WHERE code = ?
        ORDER BY started_at DESC
        """,
        (code,),
    ).fetchall()
    cols = ["run_id", "method", "model_version", "confidence",
            "date_from", "date_to", "rows_written", "div_rows_written", "status"]
    return [dict(zip(cols, r)) for r in rows]
