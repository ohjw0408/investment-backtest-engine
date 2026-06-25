"""OpenFIGI CUSIP→티커 매핑. 무료 키(env OPENFIGI_API_KEY), 키 없으면 빈 매핑 반환(graceful)."""
import os
import time
import requests

_URL = "https://api.openfigi.com/v3/mapping"


def _key():
    return os.environ.get("OPENFIGI_API_KEY", "").strip()


def map_cusips(cusips):
    """CUSIP 리스트 → {cusip: ticker}. 미국 보통주 우선. 실패분은 dict에서 빠짐."""
    key = _key()
    if not key:
        return {}  # 키 없음 = no-op (UI는 미매핑으로 표기)
    cusips = [c for c in dict.fromkeys(cusips) if c]  # 중복 제거, 순서 보존
    headers = {"Content-Type": "application/json", "X-OPENFIGI-APIKEY": key}
    out = {}
    # 인증 시 배치 100건/req, 25 req/6s 제한 → 배치당 짧은 대기
    for i in range(0, len(cusips), 100):
        batch = cusips[i:i + 100]
        body = [{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in batch]
        r = requests.post(_URL, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        for c, res in zip(batch, r.json()):
            data = res.get("data") or []
            if not data:
                continue
            # 보통주(Common Stock) 우선, 없으면 첫 결과
            pick = next((d for d in data if d.get("securityType") == "Common Stock"), data[0])
            tic = pick.get("ticker")
            if tic:
                out[c] = tic.upper()
        time.sleep(0.3)
    return out
