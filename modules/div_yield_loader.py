"""
div_yield_loader.py
────────────────────────────────────────────────────────────────────────────────
지수별 연도별 배당수익률 수집 및 index_master.db 저장

실행: python modules/div_yield_loader.py
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR       = Path(__file__).resolve().parent.parent
INDEX_DB_PATH  = BASE_DIR / "data" / "meta" / "index_master.db"
PRICE_DB_PATH  = BASE_DIR / "data" / "price_cache" / "price_daily.db"

# 지수 → ETF 프록시 매핑
ETF_PROXY_MAP: dict[str, str] = {
    "^GSPC":      "SPY",    # S&P 500         (1993~)
    "^NDX":       "QQQ",    # Nasdaq 100      (1999~)
    "^DJI":       "DIA",    # Dow Jones       (1998~)
    "^RUT":       "IWM",    # Russell 2000    (2000~)
    "^SOX":       "SOXX",   # 반도체           (2001~)
    "^N225":      "EWJ",    # 일본             (1996~)
    "^STOXX50E":  "FEZ",    # 유럽             (2002~)
    "EEM":        "EEM",    # 이머징           (2003~)
    "ACWI":       "ACWI",   # MSCI World      (2008~)
    "^HSCE":      "MCHI",   # 중국 H주         (2011~)
    "000300.SS":  "ASHR",   # CSI 300         (2013~)
    "^NSEI":      "INDA",   # 인도             (2012~)
    "DJUSDIV100": "SCHD",   # DJ US Dividend  (2011~)
    "TPX.F":      "EWJ",    # TOPIX (EWJ 프록시)
    "KQ150":      None,     # 코스닥150 — ETF 역산으로 처리
}

# 배당 없는 지수 — 수집 대상 제외
NO_DIVIDEND_INDICES: set[str] = {
    "DGS30", "DGS10", "DGS3MO",
    "GC=F", "SI=F", "CL=F", "HG=F",
    "USD/KRW", "USD/JPY",
}


class DivYieldLoader:

    def __init__(self):
        INDEX_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(INDEX_DB_PATH), check_same_thread=False)
        self._ensure_table()

    def __del__(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def _ensure_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS index_div_yield (
                index_code   TEXT,
                year         INTEGER,
                annual_yield REAL,
                source       TEXT,
                PRIMARY KEY (index_code, year)
            )
        """)
        self.conn.commit()

    def download_all(self, force: bool = False):
        print(f"배당수익률 데이터 수집 시작")
        print("=" * 60)

        # 1) ETF 프록시 방식
        for index_code, etf_code in ETF_PROXY_MAP.items():
            if index_code in NO_DIVIDEND_INDICES:
                continue
            if etf_code is None:
                continue
            if not force and self._has_data(index_code):
                count = self._count(index_code)
                print(f"  스킵: {index_code:14s} (기존 {count}년치)")
                continue
            try:
                rows = self._fetch_from_etf_proxy(index_code, etf_code)
                if rows:
                    self._save(rows)
                    print(f"  ✅ {index_code:14s} ← {etf_code}: {len(rows)}년치")
                else:
                    print(f"  ⚠️  {index_code:14s} ← {etf_code}: 데이터 없음")
                time.sleep(0.5)
            except Exception as e:
                print(f"  ❌ {index_code}: {e}")
                time.sleep(0.5)

        # 2) ^GSPC 1928~1992: Shiller 데이터로 보완
        if force or not self._has_data("^GSPC") or self._count("^GSPC") < 30:
            try:
                self._fetch_shiller_pre1993()
            except Exception as e:
                print(f"  ❌ Shiller 다운로드 실패: {e}")

        # 3) KS200
        if force or not self._has_data("KS200"):
            try:
                self._fetch_ks200()
            except Exception as e:
                print(f"  ❌ KS200 배당 수집 실패: {e}")

        print("\n" + "=" * 60)
        print("배당수익률 수집 완료")

    def _fetch_from_etf_proxy(self, index_code: str, etf_code: str) -> list[tuple]:
        import yfinance as yf
        tk   = yf.Ticker(etf_code)
        hist = tk.history(period="max", auto_adjust=False)
        if hist.empty:
            return []

        divs   = hist["Dividends"]
        prices = hist["Close"]
        rows   = []

        for year in range(hist.index.year.min(), hist.index.year.max() + 1):
            total_div = float(divs[divs.index.year == year].sum())
            year_px   = prices[prices.index.year == year]
            if total_div <= 0 or year_px.empty:
                continue
            annual_yield = total_div / float(year_px.iloc[0])
            rows.append((index_code, year, round(annual_yield, 6), f"yf/{etf_code}"))

        return rows

    def _fetch_shiller_pre1993(self):
        """^GSPC 1928~1992: SPY 이전 구간을 Shiller 데이터로 채움."""
        import requests
        import openpyxl
        from io import BytesIO

        url  = "https://shiller.econ.yale.edu/data/ie_data.xls"
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            print(f"  ❌ Shiller 다운로드 실패 (HTTP {resp.status_code})")
            return

        wb = openpyxl.load_workbook(BytesIO(resp.content), data_only=True)
        ws = wb.active

        buckets: dict[int, dict] = {}
        for row in ws.iter_rows(min_row=8, values_only=True):
            date_val = row[0]
            price    = row[1]   # P: 월별 S&P500 가격
            dividend = row[3]   # D: 연간 배당 (이미 연환산)

            if not date_val or not price:
                continue
            try:
                year = int(str(date_val).split(".")[0])
            except Exception:
                continue

            if year < 1928 or year >= 1993:
                continue

            b = buckets.setdefault(year, {"prices": [], "divs": []})
            b["prices"].append(float(price))
            if dividend:
                b["divs"].append(float(dividend) / 12)  # 월별 → 합산용

        rows = []
        for year, b in sorted(buckets.items()):
            if b["prices"] and b["divs"]:
                annual_yield = sum(b["divs"]) / (sum(b["prices"]) / len(b["prices"]))
                rows.append(("^GSPC", year, round(annual_yield, 6), "shiller"))

        self._save(rows, ignore_existing=True)
        print(f"  ✅ ^GSPC Shiller 1928~1992: {len(rows)}년치")

    def _fetch_ks200(self):
        """KS200: FDR 시도 → 실패 시 KODEX200/TIGER200 실측 역산."""
        rows = []

        # FDR 시도
        try:
            import FinanceDataReader as fdr
            df = fdr.DataReader("KS200DY", "1990", "2025")
            if not df.empty:
                for year in df.index.year.unique():
                    val = float(df[df.index.year == year].iloc[:, 0].mean()) / 100.0
                    rows.append(("KS200", int(year), round(val, 6), "fdr"))
        except Exception:
            pass

        # ETF 역산 fallback
        if not rows:
            rows = self._compute_ks200_from_etfs()

        if rows:
            self._save(rows)
            print(f"  ✅ KS200: {len(rows)}년치")
        else:
            print(f"  ⚠️  KS200: 데이터 수집 실패")

    def _compute_ks200_from_etfs(self) -> list[tuple]:
        """KODEX200(069500), TIGER200(102110) 실측 배당으로 KS200 역산."""
        try:
            price_conn = sqlite3.connect(str(PRICE_DB_PATH), check_same_thread=False)
        except Exception:
            return []

        all_rows: list[tuple[int, float]] = []
        for code in ["069500", "102110"]:
            try:
                rows = price_conn.execute("""
                    SELECT strftime('%Y', ca.date) yr,
                           SUM(ca.dividend)       total_div,
                           AVG(pd.close)          avg_price
                    FROM corporate_actions ca
                    JOIN price_daily pd ON ca.code = pd.code AND ca.date = pd.date
                    WHERE ca.code = ? AND ca.dividend > 0
                    GROUP BY yr
                """, (code,)).fetchall()
                for r in rows:
                    if r[2] and float(r[2]) > 0:
                        all_rows.append((int(r[0]), float(r[1]) / float(r[2])))
            except Exception:
                continue

        price_conn.close()

        if not all_rows:
            return []

        by_year: dict[int, list[float]] = {}
        for yr, val in all_rows:
            by_year.setdefault(yr, []).append(val)

        return [
            ("KS200", yr, round(sum(vals) / len(vals), 6), "etf_avg")
            for yr, vals in sorted(by_year.items())
        ]

    def _has_data(self, index_code: str) -> bool:
        return self.conn.execute(
            "SELECT COUNT(*) FROM index_div_yield WHERE index_code=?",
            (index_code,)
        ).fetchone()[0] > 0

    def _count(self, index_code: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM index_div_yield WHERE index_code=?",
            (index_code,)
        ).fetchone()[0]

    def _save(self, rows: list[tuple], ignore_existing: bool = False):
        stmt = "INSERT OR IGNORE" if ignore_existing else "INSERT OR REPLACE"
        self.conn.executemany(
            f"{stmt} INTO index_div_yield "
            f"(index_code, year, annual_yield, source) VALUES (?,?,?,?)",
            rows,
        )
        self.conn.commit()


if __name__ == "__main__":
    DivYieldLoader().download_all(force=False)
