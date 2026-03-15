"""
classify_kr_etf_llm.py
────────────────────────────────────────────────────────────────────────────────
Anthropic API로 한국 ETF 전체 분류
- kr_etf_list.csv 읽어서 배치로 LLM에 분류 요청
- 결과를 kr_etf_list.csv에 업데이트
────────────────────────────────────────────────────────────────────────────────
"""

import sys
import json
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "meta" / "kr_etf_list.csv"
BATCH_SIZE = 50  # 한 번에 처리할 ETF 수

SYSTEM_PROMPT = """당신은 한국 ETF 분류 전문가입니다.
ETF 이름을 보고 다음 4가지를 JSON으로 분류해주세요:

1. index: 기초지수 코드
   - 주식: SP500, NASDAQ100, NASDAQ, DOW, RUSSELL2000, KOSPI200, KOSPI, KOSDAQ150, KOSDAQ, KRX300, MSCI_WORLD, MSCI_EM, JAPAN, CHINA, INDIA, VIETNAM, EUROPE, BRAZIL, KOREA_DIVIDEND_ARISTOCRATS
   - 채권: US_TREASURY_30Y, US_TREASURY_10Y, US_TREASURY, KR_TREASURY_30Y, KR_TREASURY_10Y, KR_TREASURY, KR_BOND_AGGREGATE, KR_CORPORATE, US_CORPORATE, US_HIGH_YIELD, KR_MONEY_MARKET
   - 원자재: GOLD, SILVER, OIL, COPPER, AGRICULTURE
   - 섹터/테마: KR_SEMICONDUCTOR, US_SEMICONDUCTOR, KR_BATTERY, KR_AI, US_AI, KR_NUCLEAR, US_NUCLEAR, KR_DEFENSE, US_DEFENSE, KR_BIO, US_BIO, KR_REIT, US_REIT, KR_DIVIDEND, US_DIVIDEND, KR_COVERED_CALL, US_COVERED_CALL, KR_ENERGY, US_ENERGY, TDF, ASSET_ALLOCATION, GOLD_MINING, KR_ROBOT, US_ROBOT, US_TECH, KR_TECH, KR_BEAUTY, KR_AUTO, KR_SECURITIES, KR_ESG, KR_VALUE, KR_VALUEUP, KR_GROWTH, KR_CULTURE, HYDROGEN, METAVERSE, QUANTUM, AEROSPACE, CLEAN_ENERGY, INFRASTRUCTURE, KR_BOND_MIX, USD, KR_HOLDING, KR_SOFTWARE, KR_CONSTRUCTION, RARE_EARTH, AUTONOMOUS, TECH_INNOVATION, UNKNOWN
   
2. market: 기초자산 시장
   - KR: 한국 자산 (코스피, 코스닥, 한국채권 등)
   - US: 미국 자산 (S&P500, 나스닥, 미국채 등)
   - CHINA, JAPAN, INDIA, VIETNAM, EUROPE, GLOBAL, COMMODITY, CURRENCY

3. leverage: 레버리지 배수 (숫자)
   - 1.0: 일반
   - 2.0: 레버리지 2배
   - 3.0: 레버리지 3배
   - -1.0: 인버스
   - -2.0: 인버스 2배

4. hedge: 환헤지 여부
   - none: 한국 자산 (환율 무관)
   - hedge: 환헤지 ((H) 표시)
   - unhedged: 환노출 (해외자산, 헤지 없음)

반드시 JSON 배열만 반환하세요. 다른 텍스트 없이.
형식: [{"code": "069500", "index": "KOSPI200", "market": "KR", "leverage": 1.0, "hedge": "none"}, ...]
"""

def classify_batch(etf_batch: list) -> list:
    """ETF 배치를 LLM으로 분류"""
    
    etf_list_text = "\n".join([
        f"{row['code']}: {row['name']}"
        for row in etf_batch
    ])
    
    user_message = f"다음 ETF들을 분류해주세요:\n\n{etf_list_text}"
    
    response = fetch_classification(user_message)
    
    try:
        # JSON 파싱
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        results = json.loads(clean.strip())
        return results
    except Exception as e:
        print(f"  ⚠️  JSON 파싱 실패: {e}")
        print(f"  응답: {response[:200]}")
        return []

def fetch_classification(user_message: str) -> str:
    """Anthropic API 호출"""
    import urllib.request
    
    data = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4000,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": user_message}
        ]
    }).encode("utf-8")
    
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return result["content"][0]["text"]

def main():
    df = pd.read_csv(CSV_PATH)
    print(f"총 {len(df)}개 ETF 로드")
    
    records = df.to_dict("records")
    total_batches = (len(records) + BATCH_SIZE - 1) // BATCH_SIZE
    
    results_map = {}
    
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        
        print(f"\n[{batch_num}/{total_batches}] {batch[0]['name']} ~ {batch[-1]['name']} 처리 중...")
        
        results = classify_batch(batch)
        
        if results:
            for r in results:
                results_map[str(r["code"])] = r
            print(f"  ✅ {len(results)}개 분류 완료")
        else:
            print(f"  ❌ 분류 실패, 기존 값 유지")
        
        time.sleep(0.5)
    
    # 결과 반영
    updated = 0
    for idx, row in df.iterrows():
        code = str(row["code"])
        if code in results_map:
            r = results_map[code]
            df.at[idx, "index"]    = r.get("index",    row["index"])
            df.at[idx, "market"]   = r.get("market",   row["market"])
            df.at[idx, "leverage"] = r.get("leverage", row["leverage"])
            df.at[idx, "hedge"]    = r.get("hedge",    row["hedge"])
            updated += 1
    
    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    
    print(f"\n완료: {updated}개 업데이트")
    print(f"UNKNOWN: {(df['index'] == 'UNKNOWN').sum()}개")
    print(f"분류율: {(df['index'] != 'UNKNOWN').sum() / len(df) * 100:.1f}%")

if __name__ == "__main__":
    main()