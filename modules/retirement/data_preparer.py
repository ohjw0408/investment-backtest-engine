"""
data_preparer.py
────────────────────────────────────────────────────────────────────────────────
시뮬레이션 전 데이터 준비 오케스트레이터

흐름:
  1. 종목별 현재 데이터 범위 확인
  2. 포트폴리오 유효 시작일 = max(종목별 시작일)
  3. 롤링 케이스 수 계산 → MIN_CASES 이상이면 끝
  4. 부족한 종목:
     a. 백필 가능 (index 매핑 있음) → BackfillEngine.backfill()
     b. 백필 불가 → TickerStatsCache로 mu/sigma 계산
                  → SyntheticPriceGenerator로 가상 가격 생성
  5. 재계산 후 유효 시작일, 케이스 수 반환
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Dict

import pandas as pd

from modules.backfill_engine              import BackfillEngine
from modules.retirement.ticker_stats_cache       import TickerStatsCache
from modules.retirement.synthetic_price_generator import generate_and_save

BASE_DIR      = Path(__file__).resolve().parent.parent.parent
PRICE_DB_PATH = BASE_DIR / "data" / "price_cache" / "price_daily.db"
USD_KRW_START = "1964-05-04"   # 환율 데이터 시작일 = 유효 최대 시작일
MIN_CASES     = 30


def _get_ticker_data_start(price_conn: sqlite3.Connection, code: str) -> str | None:
    """price_daily.db에서 종목 최초 날짜 조회."""
    row = price_conn.execute(
        "SELECT MIN(date) FROM price_daily WHERE code=?", (code,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _calc_rolling_cases(data_start: str, data_end: str, sim_years: int, step_months: int = 3) -> int:
    """롤링 케이스 수 계산."""
    from dateutil.relativedelta import relativedelta
    start = pd.Timestamp(data_start)
    end   = pd.Timestamp(data_end)
    count = 0
    cur   = start
    while cur + relativedelta(years=sim_years) <= end:
        count += 1
        cur   += relativedelta(months=step_months)
    return count


class DataPreparer:

    def __init__(
        self,
        price_db_path: str | Path = PRICE_DB_PATH,
        verbose: bool = True,
    ):
        self.price_db_path = Path(price_db_path)
        self.verbose       = verbose
        self.price_conn    = sqlite3.connect(str(self.price_db_path), check_same_thread=False)
        self.stats_cache   = TickerStatsCache(self.price_db_path)
        self._backfill_engine: BackfillEngine | None = None

    def _get_backfill_engine(self) -> BackfillEngine:
        if self._backfill_engine is None:
            self._backfill_engine = BackfillEngine(verbose=self.verbose)
        return self._backfill_engine

    def prepare(
        self,
        tickers:    List[str],
        sim_years:  int,
        data_end:   str,
        step_months: int = 3,
    ) -> dict:
        """
        Parameters
        ----------
        tickers     : 포트폴리오 종목 리스트
        sim_years   : 시뮬레이션 기간 (년)
        data_end    : 데이터 끝 날짜
        step_months : 롤링 스텝 (월)

        Returns
        -------
        dict:
            data_start      : 유효 시작일 (str)
            n_cases         : 롤링 케이스 수
            synthetic_info  : 가상 데이터 생성 종목 정보
            backfilled      : 백필 처리된 종목 리스트
        """
        synthetic_info = {}
        backfilled     = []

        # ── 1단계: 현재 데이터 범위 확인 ─────────────────
        starts = {}
        for code in tickers:
            s = _get_ticker_data_start(self.price_conn, code)
            starts[code] = s
            if self.verbose:
                print(f"  [{code}] 현재 데이터 시작일: {s}")

        # ── 2단계: 포트폴리오 유효 시작일 ────────────────
        valid_starts = [s for s in starts.values() if s]
        if not valid_starts:
            raise ValueError("가격 데이터가 있는 종목이 없습니다.")

        effective_start = max(valid_starts)

        # USD_KRW_START 이전은 KRW 변환 불가 → 항상 캡 적용
        if effective_start < USD_KRW_START:
            effective_start = USD_KRW_START

        n_cases = _calc_rolling_cases(effective_start, data_end, sim_years, step_months)

        if self.verbose:
            print(f"  포트폴리오 유효 시작일: {effective_start}  롤링 케이스: {n_cases}개")

        if n_cases >= MIN_CASES:
            return {
                "data_start":     effective_start,
                "n_cases":        n_cases,
                "synthetic_info": synthetic_info,
                "backfilled":     backfilled,
            }

        # ── 3단계: 종목별 보완 ────────────────────────────
        for code in tickers:
            current_start = starts[code]

            # 이미 USD_KRW_START까지 있으면 스킵
            if current_start and current_start <= USD_KRW_START:
                continue

            if self.verbose:
                print(f"  [{code}] 데이터 부족 → 보완 시도")

            # ── 3a. 백필 시도 ─────────────────────────────
            be     = self._get_backfill_engine()
            result = be.backfill(code)

            if result["status"] == "ok":
                new_start = _get_ticker_data_start(self.price_conn, code)
                starts[code] = new_start
                backfilled.append(code)
                if self.verbose:
                    print(f"  [{code}] 백필 완료: {result['date_from']} ~ {result['date_to']}")
                continue

            # ── 3b. 백필 불가 → 가상 데이터 생성 ─────────
            if self.verbose:
                print(f"  [{code}] 백필 불가 ({result['status']}) → 가상 데이터 생성")

            stats = self.stats_cache.get_or_compute(code)
            if stats is None:
                if self.verbose:
                    print(f"  [{code}] ⚠️  실제 데이터 부족으로 통계 계산 불가 → 스킵")
                continue

            if self.verbose:
                print(f"  [{code}] mu={stats['mu_monthly']:.4f}/월  "
                      f"sigma={stats['sigma_monthly']:.4f}/월  "
                      f"기준기간: {stats['data_start']} ~ {stats['data_end']}")

            # 가상 데이터: USD_KRW_START ~ 실제 첫 날짜
            actual_start = current_start or stats["data_start"]
            gen_result   = generate_and_save(
                code          = code,
                mu_monthly    = stats["mu_monthly"],
                sigma_monthly = stats["sigma_monthly"],
                target_start  = USD_KRW_START,
                actual_start  = actual_start,
                price_conn    = self.price_conn,
                seed          = abs(hash(code)) % 100000,
            )

            if gen_result["status"] == "ok":
                new_start    = _get_ticker_data_start(self.price_conn, code)
                starts[code] = new_start

                # 합성 구간 배당 주입 (실측 mu/sigma 기반)
                div_yield_mu    = stats.get("div_yield_mu")
                div_yield_sigma = stats.get("div_yield_sigma")
                div_rows = 0

                if div_yield_mu and div_yield_mu > 0:
                    synth_px = pd.read_sql(
                        "SELECT date, close FROM price_daily "
                        "WHERE code=? AND date BETWEEN ? AND ? ORDER BY date",
                        self.price_conn,
                        params=(code, gen_result["date_from"], gen_result["date_to"]),
                    )
                    if not synth_px.empty:
                        synth_px["date"] = pd.to_datetime(synth_px["date"])
                        price_series = synth_px.set_index("date")["close"]
                        from modules.backfill_engine import inject_quarterly_dividends
                        div_rows = inject_quarterly_dividends(
                            price_conn=self.price_conn,
                            code=code,
                            price_series=price_series,
                            annual_yield_src=("musigma", div_yield_mu, div_yield_sigma),
                            seed=abs(hash(code)) % 2**31,
                        )

                synthetic_info[code] = {
                    "mu_monthly":    stats["mu_monthly"],
                    "sigma_monthly": stats["sigma_monthly"],
                    "rows_added":    gen_result["rows"],
                    "div_rows":      div_rows,
                    "date_from":     gen_result["date_from"],
                    "date_to":       gen_result["date_to"],
                    "stats_basis":   f"{stats['data_start']} ~ {stats['data_end']}",
                }
                if self.verbose:
                    div_str = f" | 배당 {div_rows}건" if div_rows > 0 else ""
                    print(f"  [{code}] 가상 데이터 생성: {gen_result['date_from']} ~ "
                          f"{gen_result['date_to']} ({gen_result['rows']:,}행){div_str}")
            else:
                if self.verbose:
                    print(f"  [{code}] 가상 데이터 생성 실패: {gen_result['status']}")

        # ── 4단계: 재계산 ─────────────────────────────────
        valid_starts    = [s for s in starts.values() if s]
        effective_start = max(valid_starts)

        # USD_KRW_START보다 앞으로는 의미없음
        if effective_start < USD_KRW_START:
            effective_start = USD_KRW_START

        n_cases = _calc_rolling_cases(effective_start, data_end, sim_years, step_months)

        if self.verbose:
            print(f"\n  ✅ 최종 유효 시작일: {effective_start}  롤링 케이스: {n_cases}개")

        return {
            "data_start":     effective_start,
            "n_cases":        n_cases,
            "synthetic_info": synthetic_info,
            "backfilled":     backfilled,
        }

    def close(self):
        self.stats_cache.close()
        try: self.price_conn.close()
        except: pass