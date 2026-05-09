"""
synthetic_price_generator.py
────────────────────────────────────────────────────────────────────────────────
GBM + Student-t 분포로 과거 가상 가격 시계열 생성 후 price_daily.db에 저장

- 실제 데이터 첫 날짜(actual_start)의 가격을 기준점으로 역방향 생성
- 저장 시 INSERT OR IGNORE → 실제 데이터 덮어쓰기 없음
- 저장 형식: USD 기준 (get_price()에서 KRW 변환)
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

SYNTHETIC_DF            = 5     # Student-t 자유도
TRADING_DAYS_PER_MONTH  = 21
T_SCALE                 = float(np.sqrt(SYNTHETIC_DF / (SYNTHETIC_DF - 2)))  # ≈ 1.291


def generate_and_save(
    code:          str,
    mu_monthly:    float,
    sigma_monthly: float,
    target_start:  str,           # 가상 데이터 시작일 (예: "1964-05-04")
    actual_start:  str,           # 실제 데이터 첫 날짜 (스케일 기준점)
    price_conn:    sqlite3.Connection,
    seed:          int = 42,
) -> dict:
    """
    target_start ~ actual_start 구간의 가상 가격 생성 후 저장.

    역방향 생성 원리:
      실제 첫 가격 P0를 기준으로, 월별 수익률을 역방향으로 적용.
      P[-1] = P0 / (1 + r[-1])
      P[-2] = P[-1] / (1 + r[-2])
      ...
      → actual_start 가격과 연속성 보장

    일별 가격:
      월별 수익률을 TRADING_DAYS_PER_MONTH로 쪼개서 일별로 변환.
    """

    target_dt = pd.Timestamp(target_start)
    actual_dt = pd.Timestamp(actual_start)

    if target_dt >= actual_dt:
        return {"code": code, "status": "no_gap", "rows": 0}

    # 실제 첫 가격 조회
    row = price_conn.execute(
        "SELECT close FROM price_daily WHERE code=? AND date>=? ORDER BY date LIMIT 1",
        (code, actual_start)
    ).fetchone()

    if row is None:
        return {"code": code, "status": "no_anchor_price", "rows": 0}

    anchor_price = float(row[0])

    # ── 생성할 거래일 목록 ────────────────────────────────
    # target_start ~ actual_start 전날까지의 평일
    bdays = pd.bdate_range(start=target_dt, end=actual_dt - pd.Timedelta(days=1))
    if len(bdays) == 0:
        return {"code": code, "status": "empty_range", "rows": 0}

    n_days = len(bdays)

    # ── 일별 mu, sigma 변환 ───────────────────────────────
    mu_daily    = mu_monthly    / TRADING_DAYS_PER_MONTH
    sigma_daily = sigma_monthly / np.sqrt(TRADING_DAYS_PER_MONTH)

    # ── GBM + Student-t 일별 수익률 생성 ─────────────────
    rng  = np.random.default_rng(seed=seed)
    raw  = rng.standard_t(df=SYNTHETIC_DF, size=n_days)
    rets = (raw / T_SCALE) * sigma_daily + mu_daily

    # ── 역방향 가격 재구성 ────────────────────────────────
    # 마지막 합성 가격이 anchor_price에 연결되도록
    # forward: prices[i+1] = prices[i] * (1 + rets[i])
    # backward: prices[i]  = prices[i+1] / (1 + rets[i])
    prices       = np.empty(n_days)
    prices[-1]   = anchor_price / (1.0 + rets[-1])
    for i in range(n_days - 2, -1, -1):
        prices[i] = prices[i + 1] / (1.0 + rets[i])
        if prices[i] <= 0:
            prices[i] = prices[i + 1] * 0.99  # 음수 방지

    # ── DB 저장 ───────────────────────────────────────────
    rows = [
        (code, bdays[i].strftime("%Y-%m-%d"),
         float(prices[i]), float(prices[i]), float(prices[i]), float(prices[i]), 0.0)
        for i in range(n_days)
    ]

    price_conn.executemany(
        "INSERT OR IGNORE INTO price_daily (code, date, open, high, low, close, volume) "
        "VALUES (?,?,?,?,?,?,?)",
        rows
    )
    price_conn.commit()

    return {
        "code":       code,
        "status":     "ok",
        "rows":       len(rows),
        "date_from":  bdays[0].strftime("%Y-%m-%d"),
        "date_to":    bdays[-1].strftime("%Y-%m-%d"),
        "anchor":     anchor_price,
    }