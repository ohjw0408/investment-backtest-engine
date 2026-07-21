from datetime import datetime, timedelta
import os

import requests
import pandas as pd
from pathlib import Path

BASE_DIR     = Path(__file__).resolve().parent.parent.parent
META_DIR     = BASE_DIR / "data" / "meta"
KRX_KEY_PATH = META_DIR / "krx_api_key.txt"


class KRXClient:

    def __init__(self, debug=True, timeout=30):
        self.auth_key = self._load_key()
        self.debug = debug
        # 웹 요청 경로에서 쓸 때는 짧게 준다. KRX가 응답을 끊지 않고 물고 있으면
        # 기본 30초 × 시장 2개 = 60초 → gunicorn worker timeout(30s)에 먼저 죽는다.
        self.timeout = timeout

    def _load_key(self) -> str:
        env_key = os.environ.get("KRX_API_KEY") or os.environ.get("KRX_AUTH_KEY")
        if env_key:
            return env_key.strip()
        if KRX_KEY_PATH.exists():
            return KRX_KEY_PATH.read_text().strip()
        raise FileNotFoundError(f"KRX API 키 없음: {KRX_KEY_PATH}")

    def _get(self, url: str, params: dict) -> dict:
        headers = {
            "AUTH_KEY": self.auth_key,
            "User-Agent": "Mozilla/5.0"
        }

        r = requests.get(url, headers=headers, params=params, timeout=self.timeout)

        if self.debug:
            print("\n===== KRX DEBUG =====")
            print("URL:", r.url)
            print("STATUS:", r.status_code)
            print("RESPONSE:", r.text[:1000])
            print("=====================\n")

        if r.status_code != 200:
            raise RuntimeError(f"KRX API 오류: {r.status_code} / {r.text[:300]}")

        try:
            return r.json()
        except Exception:
            raise RuntimeError(f"JSON 파싱 실패: {r.text[:300]}")

    def _extract_rows(self, data: dict):
        return (
            data.get("OutBlock_1")
            or data.get("output")
            or data.get("result")
            or data.get("data")
            or []
        )

    def _to_float(self, val) -> float:
        try:
            return float(str(val).replace(",", "") or 0)
        except Exception:
            return 0.0

    # 🔥 금현물 (금 1kg ONLY)
    def get_gold_price(self, bas_dd: str = None) -> pd.DataFrame:
        if bas_dd is None:
            dates = [
                (datetime.today() - timedelta(days=delta)).strftime("%Y%m%d")
                for delta in range(15)
            ]
        else:
            dates = [bas_dd]
        urls = [
            "https://data-dbg.krx.co.kr/svc/apis/gen/gold_bydd_trd",
        ]

        for date in dates:
            for url in urls:
                try:
                    data = self._get(url, {"basDd": date})
                    rows = self._extract_rows(data)

                    if not rows:
                        if self.debug:
                            print(f"[KRX] rows 없음 ({date}, {url})")
                        continue

                    records = []
                    for r in rows:

                        # 금 1kg만 필터
                        if r.get("ISU_CD") != "04020000":
                            continue

                        records.append({
                            "date":   r.get("BAS_DD", date),
                            "open":   self._to_float(r.get("TDD_OPNPRC", 0)),
                            "high":   self._to_float(r.get("TDD_HGPRC",  0)),
                            "low":    self._to_float(r.get("TDD_LWPRC",  0)),
                            "close":  self._to_float(r.get("TDD_CLSPRC", 0)),
                            "volume": self._to_float(r.get("ACC_TRDVOL", 0)),
                        })

                    df = pd.DataFrame(records)

                    if not df.empty:
                        if self.debug:
                            print(f"[KRX] 금(1kg) 데이터 수신: {date}, {len(df)}개")
                        return df

                except Exception as e:
                    print(f"[KRX] 금 API 실패: {date}, {url} / {e}")

        if self.debug:
            print("[KRX] 금 데이터 없음")
        return pd.DataFrame()
    def get_current_prices_kr(self, codes: list, bas_dd: str = None) -> dict:
        """
        KR 종목 현재가 (종가) 일괄 조회
        codes: 단축코드 리스트 ['133690', '458730', ...]
        반환: {code: price} dict (KRW)
        """
        from datetime import datetime, timedelta
        if bas_dd is None:
            d = datetime.today()
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            bas_dd = d.strftime("%Y%m%d")

        code_set = set(codes)
        prices   = {}

        for market_url in [
            "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd",   # KOSPI
            "https://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd",   # KOSDAQ
        ]:
            try:
                data = self._get(market_url, {"basDd": bas_dd})
                rows = self._extract_rows(data)
                for r in rows:
                    # ISU_CD: KR7133690004 → short code: [3:9]
                    isu_cd  = r.get("ISU_CD", "")
                    short   = isu_cd[3:9] if len(isu_cd) >= 9 else ""
                    if short in code_set:
                        price = self._to_float(r.get("TDD_CLSPRC", 0))
                        if price > 0:
                            prices[short] = price
            except Exception as e:
                if self.debug:
                    print(f"KRX 현재가 조회 실패 ({market_url}): {e}")

        return prices
