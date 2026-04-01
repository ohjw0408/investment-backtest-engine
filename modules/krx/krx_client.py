import requests
import pandas as pd
from pathlib import Path

BASE_DIR     = Path(__file__).resolve().parent.parent.parent
META_DIR     = BASE_DIR / "data" / "meta"
KRX_KEY_PATH = META_DIR / "krx_api_key.txt"


class KRXClient:

    def __init__(self, debug=True):
        self.auth_key = self._load_key()
        self.debug = debug

    def _load_key(self) -> str:
        if KRX_KEY_PATH.exists():
            return KRX_KEY_PATH.read_text().strip()
        raise FileNotFoundError(f"KRX API 키 없음: {KRX_KEY_PATH}")

    def _get(self, url: str, params: dict) -> dict:
        headers = {
            "AUTH_KEY": self.auth_key,
            "User-Agent": "Mozilla/5.0"
        }

        r = requests.get(url, headers=headers, params=params, timeout=30)

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
    def get_gold_price(self, bas_dd: str) -> pd.DataFrame:
        urls = [
            "https://data-dbg.krx.co.kr/svc/apis/gen/gold_bydd_trd",
        ]

        for url in urls:
            try:
                data = self._get(url, {"basDd": bas_dd})
                rows = self._extract_rows(data)

                if not rows:
                    print(f"⚠️ rows 없음 ({url})")
                    continue

                records = []
                for r in rows:

                    # 🔥 핵심: 금 1kg만 필터
                    if r.get("ISU_CD") != "04020000":
                        continue

                    records.append({
                        "date":   r.get("BAS_DD", bas_dd),
                        "open":   self._to_float(r.get("TDD_OPNPRC", 0)),
                        "high":   self._to_float(r.get("TDD_HGPRC",  0)),
                        "low":    self._to_float(r.get("TDD_LWPRC",  0)),
                        "close":  self._to_float(r.get("TDD_CLSPRC", 0)),
                        "volume": self._to_float(r.get("ACC_TRDVOL", 0)),
                    })

                df = pd.DataFrame(records)

                if not df.empty:
                    print(f"✅ 금(1kg) 데이터 수신: {len(df)}개")
                    return df

            except Exception as e:
                print(f"❌ 금 API 실패: {url} / {e}")

        print("🚨 금 데이터 완전 실패")
        return pd.DataFrame()