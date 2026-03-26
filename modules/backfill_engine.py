"""
backfill_engine.py
────────────────────────────────────────────────────────────────────────────────
한국 상장 ETF의 상장일 이전 데이터를 기초지수로 백필링

흐름:
  1. kr_etf_list.csv에서 ETF 메타데이터 로드
  2. index_master.db에서 기초지수 데이터 로드
  3. ETF 상장일 기준 스케일 맞추기
  4. 레버리지 적용 (일간 수익률 × leverage)
  5. 환율 적용 (market=US, hedge=unhedged → × USD/KRW)
  6. price_daily.db에 저장

사용법:
  engine = BackfillEngine()
  engine.backfill("360750")        # 단일 ETF
  engine.backfill_all()            # 전체 ETF
────────────────────────────────────────────────────────────────────────────────
"""

import sqlite3
import logging
from pathlib import Path

import pandas as pd
import numpy as np

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

BASE_DIR      = Path(__file__).resolve().parent.parent
DATA_DIR      = BASE_DIR / "data"
META_DIR      = DATA_DIR / "meta"
PRICE_DIR     = DATA_DIR / "price_cache"

INDEX_DB_PATH = META_DIR / "index_master.db"
PRICE_DB_PATH = PRICE_DIR / "price_daily.db"
KR_ETF_PATH   = META_DIR / "kr_etf_list.csv"

# ── US ETF category → index_master.db 코드 매핑 ──────────
US_CATEGORY_MAP = {
    "US Equity - Large Cap Blend":      "^GSPC",
    "US Equity - Large Cap Growth":     "^NDX",
    "US Equity - Large Cap Value":      "^GSPC",
    "US Equity - Total Market":         "^GSPC",
    "US Equity - Mid Cap Blend":        "^GSPC",
    "US Equity - Small Cap Blend":      "^RUT",
    "US Equity - Small Cap Growth":     "^RUT",
    "US Equity - Small Cap Value":      "^RUT",
    "US Equity - Dividend":             "DJUSDIV100",
    "US Equity - Dividend Growth":      "DJUSDIV100",
    "US Equity - Factor":               "^GSPC",
    "US Bond - Long Treasury":          "DGS30",
    "US Bond - Intermediate Treasury":  "DGS10",
    "US Bond - Short Treasury":         "DGS3MO",
    "US Bond - Aggregate":              "DGS10",
    "US Bond - Corporate IG":           "DGS10",
    "US Bond - High Yield":             "DGS10",
    "US Bond - TIPS":                   "DGS10",
    "US Bond - MBS":                    "DGS10",
    "US Bond - Municipal":              "DGS10",
    "Commodity - Gold":                 "GC=F",
    "Commodity - Silver":               "SI=F",
    "Commodity - Energy":               "CL=F",
    "Commodity - Precious Metals":      "GC=F",
    "Commodity - Broad":                "CL=F",
    "Commodity - Agriculture":          None,
    "International Equity - Developed": "ACWI",
    "International Equity - Emerging":  "EEM",
    "International Equity - Country":   "ACWI",
    "Global Equity":                    "ACWI",
    "International Bond":               "DGS10",
    "Emerging Markets Bond":            "DGS10",
    "US Sector - Technology":           "^NDX",
    "US Sector - Healthcare":           "^GSPC",
    "US Sector - Financials":           "^GSPC",
    "US Sector - Energy":               "CL=F",
    "US Sector - Consumer Discretionary": "^GSPC",
    "US Sector - Consumer Staples":     "^GSPC",
    "US Sector - Industrials":          "^GSPC",
    "US Sector - Materials":            "^GSPC",
    "US Sector - Real Estate":          "^GSPC",
    "US Sector - Utilities":            "^GSPC",
    "US Sector - Communication":        "^GSPC",
    "Asset Allocation":                 "^GSPC",
    "Thematic":                         "^GSPC",
    "Covered Call":                     "^GSPC",
    "Leveraged":                        None,
    "Inverse":                          None,
    "Crypto":                           None,
}

# ── 지수 → index_master.db 코드 매핑 ──────────────────────
INDEX_MAP = {
    "SP500":               "^GSPC",
    "NASDAQ100":           "^NDX",
    "KOSPI200":            "KS200",
    "KOSPI":               "KS200",
    "KRX300":              "KS200",
    "DJ_US_DIVIDEND":      "DJUSDIV100",
    "PHLX_SEMICONDUCTOR":  "^SOX",
    "US_TREASURY_30Y":     "DGS30",
    "US_TREASURY_10Y":     "DGS10",
    "US_TREASURY":         "DGS10",
    "GOLD":                "GC=F",
    "SILVER":              "SI=F",
    "COPPER":              "HG=F",
    "OIL":                 "CL=F",
    "JAPAN_NIKKEI225":     "^N225",
    "JAPAN_TOPIX":         "TPX.F",
    "CHINA_HSCEI":         "^HSCE",
    "CHINA_CSI300":        "000300.SS",
    "INDIA_NIFTY50":       "^NSEI",
    "MSCI_WORLD":          "ACWI",
    "MSCI_EM":             "EEM",
    "DOW":                 "^DJI",
    "RUSSELL2000":         "^RUT",
    "EUROPE":              "^STOXX50E",
}


class BackfillEngine:

    def __init__(self, verbose: bool = True):
        self.verbose    = verbose
        self.index_conn = sqlite3.connect(str(INDEX_DB_PATH), check_same_thread=False)
        self.price_conn = sqlite3.connect(str(PRICE_DB_PATH), check_same_thread=False)
        self._index_cache: dict = {}
        self._usdkrw_cache      = None
        self._etf_meta          = self._load_etf_meta()

    def __del__(self):
        try: self.index_conn.close()
        except: pass
        try: self.price_conn.close()
        except: pass

    # ── 메타데이터 로드 ────────────────────────────────────

    def _load_etf_meta(self) -> pd.DataFrame:
        """KR + US ETF 메타데이터 통합 로드"""
        frames = []

        # 한국 ETF
        if KR_ETF_PATH.exists():
            kr = pd.read_csv(KR_ETF_PATH, dtype=str)
            kr["leverage"] = pd.to_numeric(kr["leverage"], errors="coerce").fillna(1.0)
            kr["etf_type"] = "KR"
            frames.append(kr)

        # 미국 ETF
        us_etf_path = META_DIR / "us_etf_list.csv"
        if us_etf_path.exists():
            us = pd.read_csv(us_etf_path, dtype=str)
            us["index"]    = us["category"].map(US_CATEGORY_MAP)
            us["market"]   = "US"
            us["leverage"] = 1.0
            us["hedge"]    = "unhedged"
            us["etf_type"] = "US"
            frames.append(us)

        if not frames:
            raise FileNotFoundError("ETF 메타데이터 파일이 없습니다.")

        df = pd.concat(frames, ignore_index=True)
        return df.set_index("code")

    # ── 지수 데이터 로드 (캐시) ───────────────────────────

    def _load_index(self, index_code: str) -> pd.Series | None:
        if index_code in self._index_cache:
            return self._index_cache[index_code]

        df = pd.read_sql(
            "SELECT date, close FROM index_daily WHERE code=? ORDER BY date",
            self.index_conn,
            params=(index_code,),
        )
        if df.empty:
            return None

        df["date"] = pd.to_datetime(df["date"])
        series = df.set_index("date")["close"].astype(float)
        self._index_cache[index_code] = series
        return series

    # ── 환율 데이터 로드 (캐시) ───────────────────────────

    def _load_usdkrw(self) -> pd.Series:
        if self._usdkrw_cache is not None:
            return self._usdkrw_cache

        df = pd.read_sql(
            "SELECT date, close FROM index_daily WHERE code='USD/KRW' ORDER BY date",
            self.index_conn,
        )
        df["date"] = pd.to_datetime(df["date"])
        series = df.set_index("date")["close"].astype(float)
        full_idx = pd.date_range(series.index.min(), series.index.max(), freq="D")
        series   = series.reindex(full_idx).ffill()
        self._usdkrw_cache = series
        return series

    # ── ETF 기존 데이터 범위 조회 ─────────────────────────

    def _get_etf_range(self, code: str):
        row = self.price_conn.execute(
            "SELECT MIN(date), MAX(date) FROM price_daily WHERE code=?", (code,)
        ).fetchone()
        return row[0], row[1]

    # ── 저장 ──────────────────────────────────────────────

    def _save(self, code: str, df: pd.DataFrame):
        df = df.copy()
        df["code"] = code
        rows = df[["code", "date", "open", "high", "low", "close", "volume"]].values.tolist()
        self.price_conn.executemany(
            "INSERT OR IGNORE INTO price_daily (code, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
            rows
        )
        self.price_conn.commit()

    # ── 레버리지 적용 ─────────────────────────────────────

    def _apply_leverage(self, series: pd.Series, leverage: float) -> pd.Series:
        """일간 수익률에 레버리지 적용 후 첫 번째 값 기준 복원"""
        if leverage == 1.0:
            return series
        daily_ret = series.pct_change().fillna(0)
        lev_ret   = daily_ret * leverage
        result    = (1 + lev_ret).cumprod() * series.iloc[0]
        return result

    # ── 스케일 맞추기 ─────────────────────────────────────

    def _scale_to_etf(
        self,
        index_series: pd.Series,
        etf_series:   pd.Series,
        etf_start:    pd.Timestamp,
    ) -> pd.Series | None:
        """
        ETF 상장일 기준으로 지수 데이터 스케일 조정
        ETF 첫 거래일 가격 / 지수 첫 거래일 값 = scale factor
        """
        # 지수에서 ETF 상장일 이후 첫 번째 날짜 찾기
        idx_after = index_series.index[index_series.index >= etf_start]
        if len(idx_after) == 0:
            return None
        scale_date = idx_after[0]

        # ETF에서 같은 날짜 또는 이후 첫 번째 날짜 찾기
        etf_after = etf_series.index[etf_series.index >= scale_date]
        if len(etf_after) == 0:
            return None
        etf_scale_date = etf_after[0]

        # 지수도 같은 날짜로 맞추기
        idx_match = index_series.index[index_series.index >= etf_scale_date]
        if len(idx_match) == 0:
            return None
        final_scale_date = idx_match[0]

        index_val = index_series[final_scale_date]
        etf_val   = etf_series[etf_scale_date]

        if index_val == 0:
            return None

        scale  = etf_val / index_val
        scaled = index_series * scale
        return scaled

    # ── 단일 ETF 백필링 ───────────────────────────────────

    def backfill(self, code: str) -> dict:
        """단일 ETF 백필링"""
        if code not in self._etf_meta.index:
            return {"code": code, "status": "no_meta"}

        meta      = self._etf_meta.loc[code]
        index_nm  = str(meta["index"])
        market    = str(meta["market"])
        leverage  = float(meta["leverage"])
        hedge     = str(meta["hedge"])
        name      = str(meta.get("name", code))

        # 지수 코드 매핑
        # US ETF는 index 컬럼이 이미 index_master.db 코드 (^GSPC, DGS30 등)
        # KR ETF는 index 컬럼이 SP500, NASDAQ100 등 → INDEX_MAP으로 변환
        etf_type = str(meta.get("etf_type", "KR"))
        if etf_type == "US":
            index_code = index_nm if index_nm and index_nm != "None" else None
        else:
            index_code = INDEX_MAP.get(index_nm)

        if not index_code or index_code == "None":
            return {"code": code, "status": f"no_index_map ({index_nm})"}

        # ETF 기존 데이터 확인
        etf_min, etf_max = self._get_etf_range(code)
        if etf_min is None:
            return {"code": code, "status": "no_etf_data"}

        etf_start = pd.Timestamp(etf_min)

        # 지수 데이터 로드
        index_series = self._load_index(index_code)
        if index_series is None:
            return {"code": code, "status": f"no_index_data ({index_code})"}

        # ETF 상장일 이전 지수 데이터 확인
        pre_series = index_series[index_series.index < etf_start]
        if pre_series.empty:
            return {"code": code, "status": "no_pre_data"}

        # ETF 실제 가격 데이터
        etf_df = pd.read_sql(
            "SELECT date, close FROM price_daily WHERE code=? ORDER BY date",
            self.price_conn,
            params=(code,),
        )
        etf_df["date"] = pd.to_datetime(etf_df["date"])
        etf_series = etf_df.set_index("date")["close"].astype(float)

        # 레버리지 적용 (전체 구간에 적용)
        if leverage != 1.0:
            index_series = self._apply_leverage(index_series, leverage)

        # 환율 적용 여부 결정
        # - 한국 ETF (market=US, hedge=unhedged): ETF 가격이 원화이므로 환율 적용
        # - 미국 ETF: ETF 가격이 달러이므로 환율 적용 안 함 (get_price에서 처리)
        etf_type   = str(meta.get("etf_type", "KR"))
        fx_applied = etf_type == "KR" and market == "US" and hedge == "unhedged"

        if fx_applied:
            usdkrw = self._load_usdkrw()
            def get_rate(d):
                if d in usdkrw.index:
                    return float(usdkrw[d])
                before = usdkrw[usdkrw.index <= d]
                return float(before.iloc[-1]) if not before.empty else 1.0
            rates        = index_series.index.map(get_rate)
            index_series = index_series * rates.values

        # 스케일 맞추기 (전체 index_series 기준, ETF 상장일 가격으로 맞춤)
        scaled = self._scale_to_etf(index_series, etf_series, etf_start)
        if scaled is None:
            return {"code": code, "status": "scale_failed"}

        # ETF 상장 이전 구간만
        scaled = scaled[scaled.index < etf_start]
        if scaled.empty:
            return {"code": code, "status": "empty_after_scale"}

        # DataFrame 구성
        df = pd.DataFrame({
            "date":   scaled.index.strftime("%Y-%m-%d"),
            "open":   scaled.values,
            "high":   scaled.values,
            "low":    scaled.values,
            "close":  scaled.values,
            "volume": 0.0,
        })

        self._save(code, df)

        result = {
            "code":       code,
            "status":     "ok",
            "rows_added": len(df),
            "date_from":  df["date"].min(),
            "date_to":    df["date"].max(),
            "index_code": index_code,
            "leverage":   leverage,
            "fx_applied": fx_applied,
        }

        if self.verbose:
            fx_str  = " ×환율" if fx_applied else ""
            lev_str = f" ×{leverage}" if leverage != 1.0 else ""
            print(f"  ✅ {code:8s} {name[:22]:22s} "
                  f"← {index_code:12s}{lev_str}{fx_str} "
                  f"| {result['date_from']} ~ {result['date_to']} ({len(df):,}행)")

        return result

    # ── 전체 ETF 백필링 ───────────────────────────────────

    def backfill_all(self, market_filter: str = None) -> pd.DataFrame:
        """전체 ETF 백필링"""
        meta = self._etf_meta.copy()
        if market_filter:
            meta = meta[meta["market"] == market_filter]

        print(f"\n{'='*65}")
        print(f"전체 백필링 시작: {len(meta)}개 ETF")
        if market_filter:
            print(f"  필터: market={market_filter}")
        print(f"{'='*65}")

        results = []
        ok = skip = fail = 0

        for code in meta.index:
            result = self.backfill(code)
            results.append(result)
            status = result["status"]
            if status == "ok":
                ok += 1
            elif status in ("no_pre_data", "no_etf_data"):
                skip += 1
            else:
                fail += 1
                if self.verbose and status not in ("no_index_map",):
                    print(f"  ⚠️  {code:8s} → {status}")

        print(f"\n{'='*65}")
        print(f"완료: {ok}개 성공 / {skip}개 스킵 / {fail}개 실패")
        return pd.DataFrame(results)


if __name__ == "__main__":
    engine = BackfillEngine(verbose=True)

    # 핵심 ETF 테스트
    print("\n── 핵심 ETF 백필링 테스트 ──────────────────────────")
    test_codes = [
        "360750",  # TIGER 미국S&P500 (환노출)
        "379800",  # KODEX 미국S&P500 (환노출)
        "133690",  # TIGER 미국나스닥100 (환노출)
        "069500",  # KODEX 200 (KR)
        "102110",  # TIGER 200 (KR)
        "453850",  # ACE 미국30년국채액티브(H)
        "411060",  # ACE KRX금현물
    ]

    for code in test_codes:
        engine.backfill(code)

    # 결과 확인
    print("\n── 백필링 후 전체 데이터 범위 ──────────────────────")
    for code in test_codes:
        row = engine.price_conn.execute(
            "SELECT MIN(date), MAX(date), COUNT(*) FROM price_daily WHERE code=?", (code,)
        ).fetchone()
        name = engine._etf_meta.loc[code, "name"] if code in engine._etf_meta.index else code
        print(f"  {code} {name[:20]:20s}: {row[0]} ~ {row[1]}  ({row[2]:,}행)")