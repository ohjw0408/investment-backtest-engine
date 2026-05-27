"""
scenario_data_preparer.py
─────────────────────────────────────────────────────────────────────────────
공통 시나리오 데이터 준비 facade.

목적:
  - 투자계산기 / 백테스트 / 은퇴 등 모든 탭에서 단일 진입점을 통해 데이터 준비.
  - allow_synthetic=False(기본) 시 가상 데이터 생성 없이 실제/백필 범위만 반환.
  - allow_synthetic=True 시 기존 DataPreparer(합성 포함) 경유.
  - 탭은 내부 구현(BackfillEngine / SyntheticPriceGenerator / DataPreparer)을 몰라도 됨.

반환 형식:
    {
        "data_start":       str,           # 전체 데이터 최초일
        "data_end":         str,           # 데이터 끝일
        "effective_start":  str,           # 포트폴리오 유효 시작일 (max of tickers)
        "requested_start":  str | None,
        "n_cases":          int | None,
        "backfilled":       list[str],
        "synthetic_info":   dict,          # code -> {rows_added, date_from, date_to, ...}
        "data_confidence":  "actual" | "backfilled" | "synthetic",
        "used_synthetic":   bool,
        "warnings":         list[str],
    }

Phase:
    Phase 1 — facade 추가. 기존 동작 변경 없음.
    Phase 2 — DataPreparer에 allow_* 플래그 추가 후 이 파일 업데이트 예정.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

BASE_DIR      = Path(__file__).resolve().parent.parent.parent
PRICE_DB_PATH = BASE_DIR / "data" / "price_cache" / "price_daily.db"
USD_KRW_START = "1964-05-04"


def _get_actual_start(price_conn: sqlite3.Connection, code: str) -> str | None:
    row = price_conn.execute(
        "SELECT MIN(date) FROM price_daily WHERE code=?", (code,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _calc_rolling_cases(data_start: str, data_end: str, sim_years: int, step_months: int = 3) -> int:
    from dateutil.relativedelta import relativedelta
    start = pd.Timestamp(data_start)
    end   = pd.Timestamp(data_end)
    count = 0
    cur   = start
    while cur + relativedelta(years=sim_years) <= end:
        count += 1
        cur   += relativedelta(months=step_months)
    return count


def _data_confidence(backfilled: list, synthetic_info: dict) -> str:
    if synthetic_info:
        return "synthetic"
    if backfilled:
        return "backfilled"
    return "actual"


def prepare_scenario_data(
    tickers: list[str],
    required_years: Optional[int] = None,
    data_end: Optional[str] = None,
    requested_start: Optional[str] = None,
    step_months: int = 3,
    allow_backfill: bool = True,
    allow_synthetic: bool = False,
    purpose: str = "generic",
    price_db_path: Optional[str | Path] = None,
    verbose: bool = False,
) -> dict:
    """
    시나리오 데이터 준비 공통 facade.

    Parameters
    ----------
    tickers         : 종목 코드 리스트
    required_years  : 필요 시뮬레이션 기간 (년). None이면 n_cases 계산 생략.
    data_end        : 데이터 끝 날짜 (None이면 오늘).
    requested_start : 호출자가 원하는 시작일 (참고용, 강제 아님).
    step_months     : 롤링 스텝 (월). 기본 3.
    allow_backfill  : 백필 허용 여부. 기본 True.
    allow_synthetic : 가상 데이터 생성 허용 여부. 기본 False.
                      True 시 기존 DataPreparer 경유 (DB 기록 발생 가능).
    purpose         : 호출 목적 레이블 (로그용). "calculator" / "backtest" / "retirement" 등.
    price_db_path   : price_daily.db 경로 오버라이드.
    verbose         : 상세 로그 출력 여부.

    Returns
    -------
    dict — 상단 docstring 참조.
    """
    import datetime
    import math
    db_path  = Path(price_db_path) if price_db_path else PRICE_DB_PATH
    today    = datetime.date.today().isoformat()
    data_end = data_end or today

    # requested_start 있으면 required_years 자동 계산 (allow_synthetic=True 경로용)
    if requested_start is not None and required_years is None:
        delta = (pd.Timestamp(data_end) - pd.Timestamp(requested_start)).days
        required_years = max(1, math.ceil(delta / 365.25))

    # ── allow_synthetic=True → 기존 DataPreparer 경유 ───────────────────────
    if allow_synthetic:
        if required_years is None:
            raise ValueError("allow_synthetic=True 시 required_years 필수.")
        from modules.retirement.data_preparer import DataPreparer
        dp     = DataPreparer(price_db_path=db_path, verbose=verbose)
        result = dp.prepare(
            tickers          = tickers,
            sim_years        = required_years,
            data_end         = data_end,
            step_months      = step_months,
            allow_backfill   = allow_backfill,
            allow_synthetic  = True,
        )
        dp.close()

        backfilled     = result.get("backfilled", [])
        synthetic_info = result.get("synthetic_info", {})
        warnings       = list(result.get("warnings", []))
        for code, info in synthetic_info.items():
            warnings.append(
                f"Synthetic data used for {code}: "
                f"{info.get('date_from')} ~ {info.get('date_to')} "
                f"({info.get('rows_added', 0)} rows)"
            )

        return {
            "data_start":      result["data_start"],
            "data_end":        data_end,
            "effective_start": result["data_start"],
            "requested_start": requested_start,
            "n_cases":         result.get("n_cases"),
            "backfilled":      backfilled,
            "synthetic_info":  synthetic_info,
            "data_confidence": _data_confidence(backfilled, synthetic_info),
            "used_synthetic":  bool(synthetic_info),
            "warnings":        warnings,
        }

    # ── allow_synthetic=False → 실제/백필 데이터 범위만 보고 ─────────────────
    price_conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        # 백필 (옵션)
        backfilled: list[str] = []
        if allow_backfill:
            from modules.backfill_engine import BackfillEngine
            be = BackfillEngine(verbose=verbose)
            for code in tickers:
                r = be.backfill(code)
                if r.get("status") == "ok":
                    backfilled.append(code)
                    if verbose:
                        print(f"[ScenarioDataPreparer:{purpose}] {code} backfilled")

        # 유효 시작일 산출
        starts = {code: _get_actual_start(price_conn, code) for code in tickers}
        valid  = [s for s in starts.values() if s]
        if not valid:
            raise ValueError(f"가격 데이터가 없는 종목들: {tickers}")

        effective_start = max(valid)
        if effective_start < USD_KRW_START:
            effective_start = USD_KRW_START

        # 데이터 부족 경고
        warnings: list[str] = []
        for code, s in starts.items():
            if s is None:
                warnings.append(f"No price data found for {code}.")
            elif required_years is not None:
                from dateutil.relativedelta import relativedelta
                needed = (pd.Timestamp(data_end) - relativedelta(years=required_years)).strftime("%Y-%m-%d")
                if s > needed:
                    warnings.append(
                        f"{code} data starts {s}, but {required_years}yr simulation needs data from {needed}. "
                        f"Enable synthetic data to fill the gap."
                    )

        n_cases = None
        if required_years is not None:
            n_cases = _calc_rolling_cases(effective_start, data_end, required_years, step_months)

        # 전체 data_start (모든 종목 중 가장 이른 날짜)
        data_start = min(valid)

        return {
            "data_start":      data_start,
            "data_end":        data_end,
            "effective_start": effective_start,
            "requested_start": requested_start,
            "n_cases":         n_cases,
            "backfilled":      backfilled,
            "synthetic_info":  {},
            "data_confidence": _data_confidence(backfilled, {}),
            "used_synthetic":  False,
            "warnings":        warnings,
        }
    finally:
        price_conn.close()
