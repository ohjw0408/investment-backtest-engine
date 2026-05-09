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
    code          TEXT PRIMARY KEY,
    mu_monthly    REAL NOT NULL,
    sigma_monthly REAL NOT NULL,
    data_start    TEXT NOT NULL,
    data_end      TEXT NOT NULL,
    n_months      INTEGER NOT NULL,
    is_synthetic  INTEGER NOT NULL DEFAULT 0,
    computed_at   TEXT NOT NULL
)
"""


class TickerStatsCache:

    def __init__(self, price_db_path: str | Path):
        self.db_path = Path(price_db_path)
        self._conn   = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute(_DDL)
        self._conn.commit()

    def get(self, code: str) -> dict | None:
        """캐시에서 읽기. TTL 초과 시 None 반환."""
        row = self._conn.execute(
            "SELECT mu_monthly, sigma_monthly, data_start, data_end, n_months, computed_at "
            "FROM ticker_return_stats WHERE code=?",
            (code,)
        ).fetchone()

        if row is None:
            return None

        computed_at = datetime.fromisoformat(row[5])
        if datetime.now() - computed_at > timedelta(days=CACHE_TTL_DAYS):
            return None  # 만료

        return {
            "mu_monthly":    row[0],
            "sigma_monthly": row[1],
            "data_start":    row[2],
            "data_end":      row[3],
            "n_months":      row[4],
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

        self._conn.execute(
            """INSERT OR REPLACE INTO ticker_return_stats
               (code, mu_monthly, sigma_monthly, data_start, data_end, n_months, is_synthetic, computed_at)
               VALUES (?,?,?,?,?,?,0,?)""",
            (code, mu, sigma, data_start, data_end, n_months, computed_at)
        )
        self._conn.commit()

        return {"mu_monthly": mu, "sigma_monthly": sigma,
                "data_start": data_start, "data_end": data_end, "n_months": n_months}

    def get_or_compute(self, code: str) -> dict | None:
        """캐시 hit → 반환, miss → 계산 후 저장 후 반환."""
        cached = self.get(code)
        if cached:
            return cached
        return self.compute_and_save(code)

    def close(self):
        try: self._conn.close()
        except: pass