"""
ticker_stats_cache.py
────────────────────────────────────────────────────────────────────────────────
종목별 월수익률 통계 (mu, sigma) 계산 및 캐시

- price_daily.db의 ticker_return_stats 테이블에 저장
- 30일마다 재계산
- 계산 기준: 실제 데이터 전체 범위 (가상 데이터 제외)
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

CACHE_TTL_DAYS = 30   # 캐시 유효기간
TRADING_DAYS_PER_MONTH = 21

# 테이블 DDL
_DDL = """
CREATE TABLE IF NOT EXISTS ticker_return_stats (
    code             TEXT PRIMARY KEY,
    mu_monthly       REAL NOT NULL,
    sigma_monthly    REAL NOT NULL,
    data_start       TEXT NOT NULL,
    data_end         TEXT NOT NULL,
    n_months         INTEGER NOT NULL,
    is_synthetic     INTEGER NOT NULL DEFAULT 0,
    computed_at      TEXT NOT NULL,
    div_yield_mu     REAL,
    div_yield_sigma  REAL
)
"""


class TickerStatsCache:

    def __init__(self, price_db_path: str | Path):
        self.db_path = Path(price_db_path)
        self._conn   = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute(_DDL)
        self._migrate_dividend_columns()
        self._conn.commit()

    def _migrate_dividend_columns(self):
        """구 스키마(배당 컬럼 없음) 테이블 보강. CREATE TABLE IF NOT EXISTS는
        기존 테이블을 갱신하지 않아 SELECT div_yield_mu가 'no such column'으로 깨짐.
        컬럼이 없으면 추가하고, 배당 통계가 비어 있는 구 캐시 행은 비워 재계산을 유도한다."""
        cols = {r[1] for r in self._conn.execute(
            "PRAGMA table_info(ticker_return_stats)").fetchall()}
        migrated = False
        if "div_yield_mu" not in cols:
            self._conn.execute("ALTER TABLE ticker_return_stats ADD COLUMN div_yield_mu REAL")
            migrated = True
        if "div_yield_sigma" not in cols:
            self._conn.execute("ALTER TABLE ticker_return_stats ADD COLUMN div_yield_sigma REAL")
            migrated = True
        if migrated:
            # 배당 컬럼이 막 생긴 구 행 → 배당 통계 없음 → 재계산 유도(get miss).
            self._conn.execute("DELETE FROM ticker_return_stats")

    def get(self, code: str) -> dict | None:
        """캐시에서 읽기. TTL 초과 시 None 반환."""
        row = self._conn.execute(
            "SELECT mu_monthly, sigma_monthly, data_start, data_end, n_months, computed_at, "
            "div_yield_mu, div_yield_sigma "
            "FROM ticker_return_stats WHERE code=?",
            (code,)
        ).fetchone()

        if row is None:
            return None

        computed_at = datetime.fromisoformat(row[5])
        if datetime.now() - computed_at > timedelta(days=CACHE_TTL_DAYS):
            return None  # 만료

        return {
            "mu_monthly":      row[0],
            "sigma_monthly":   row[1],
            "data_start":      row[2],
            "data_end":        row[3],
            "n_months":        row[4],
            "div_yield_mu":    row[6],
            "div_yield_sigma": row[7],
        }

    def compute_and_save(self, code: str) -> dict | None:
        """
        price_daily.db에서 실제 데이터(가상 아닌 것)로 mu/sigma 계산 후 저장.
        실제 데이터가 12개월 미만이면 None 반환.
        """
        # 실제 가격 데이터 로드 (가상 데이터 제외: volume=0은 백필/합성일 수 있으므로
        # 날짜 기준으로 실제 상장일 이후만 사용)
        rows = self._conn.execute(
            "SELECT date, close FROM price_daily WHERE code=? ORDER BY date",
            (code,)
        ).fetchall()

        rows = [(r[0], r[1]) for r in rows if r[1] is not None]
        if not rows or len(rows) < TRADING_DAYS_PER_MONTH * 12:
            return None

        dates  = pd.to_datetime([r[0] for r in rows])
        closes = np.array([float(r[1]) for r in rows])

        # 월별 샘플링 (~21 거래일 간격)
        idx         = np.arange(0, len(closes), TRADING_DAYS_PER_MONTH)
        monthly_px  = closes[idx]
        monthly_ret = np.diff(monthly_px) / np.where(monthly_px[:-1] > 0, monthly_px[:-1], 1.0)

        # 극단값 제거 (±50% 초과)
        monthly_ret = monthly_ret[np.isfinite(monthly_ret)]
        monthly_ret = monthly_ret[np.abs(monthly_ret) < 0.5]

        if len(monthly_ret) < 12:
            return None

        mu    = float(np.mean(monthly_ret))
        sigma = float(np.std(monthly_ret))

        if sigma <= 0 or not np.isfinite(mu):
            return None

        data_start  = dates[0].strftime("%Y-%m-%d")
        data_end    = dates[-1].strftime("%Y-%m-%d")
        n_months    = len(monthly_ret)
        computed_at = datetime.now().isoformat()

        # 배당수익률 통계: corporate_actions JOIN price_daily
        # 0.0 = "계산했으나 배당 없음"(NULL=미계산과 구분 → 구 캐시 재계산 트리거용).
        div_yield_mu    = 0.0
        div_yield_sigma = 0.0
        try:
            div_data = self._conn.execute("""
                SELECT strftime('%Y', ca.date) yr,
                       SUM(ca.dividend)       total_div,
                       AVG(pd.close)          avg_price
                FROM corporate_actions ca
                JOIN price_daily pd ON ca.code = pd.code AND ca.date = pd.date
                WHERE ca.code = ? AND ca.dividend > 0
                GROUP BY yr
            """, (code,)).fetchall()
        except Exception:
            div_data = []
        if div_data:
            yields = [r[1] / r[2] for r in div_data if r[2] and r[2] > 0]
            if yields:
                div_yield_mu = float(np.mean(yields))
                n_div        = len(yields)
                div_yield_sigma = max(
                    float(np.std(yields)) if n_div >= 2 else div_yield_mu * 0.20,
                    div_yield_mu * 0.10,
                )

        self._conn.execute(
            """INSERT OR REPLACE INTO ticker_return_stats
               (code, mu_monthly, sigma_monthly, data_start, data_end, n_months,
                is_synthetic, computed_at, div_yield_mu, div_yield_sigma)
               VALUES (?,?,?,?,?,?,0,?,?,?)""",
            (code, mu, sigma, data_start, data_end, n_months,
             computed_at, div_yield_mu, div_yield_sigma)
        )
        self._conn.commit()

        return {
            "mu_monthly":      mu,
            "sigma_monthly":   sigma,
            "data_start":      data_start,
            "data_end":        data_end,
            "n_months":        n_months,
            "div_yield_mu":    div_yield_mu,
            "div_yield_sigma": div_yield_sigma,
        }

    def get_or_compute(self, code: str) -> dict | None:
        """캐시 hit → 반환, miss → 계산 후 저장 후 반환.
        배당 통계 없는(div_yield_mu IS NULL) 구 캐시 행은 1회 재계산해 배당을 채운다."""
        cached = self.get(code)
        if cached and cached.get("div_yield_mu") is not None:
            return cached
        return self.compute_and_save(code) or cached

    def close(self):
        try: self._conn.close()
        except: pass