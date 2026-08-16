"""test_guru_pit_browser.js가 쓰는 결과 샘플 생성 — tmp/guru_pit_sample.json.

브라우저 검증은 렌더 경로를 봐야 하는데, 실행 자체는 celery 큐를 탄다(로컬엔 worker 없음).
그래서 엔진(run_backtest_logic)이 **실제로 뱉은** 결과를 파일로 떨어뜨려 그대로 흘려 넣는다.
지어낸 payload가 아니라 진짜 계산 결과다.

사용: venv/Scripts/python.exe tests/make_guru_pit_sample.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest_logic as bl

BODY = {
    "start_date": "2016-01-01",
    "end_date": "2026-08-01",
    "initial_capital": 10_000_000,
    "monthly_contribution": 0,
    "dividend_mode": "reinvest",
    "rebal_mode": "yearly",
    "guru": "warren-buffett",
    "guru_name": "워런 버핏",
    "tickers": [
        {"code": "AAPL", "name": "APPLE INC", "weight": 0.253},
        {"code": "AXP", "name": "AMERICAN EXPRESS", "weight": 0.197},
        {"code": "KO", "name": "COCA COLA", "weight": 0.125},
        {"code": "GOOGL", "name": "ALPHABET", "weight": 0.108},
        {"code": "BAC", "name": "BANK OF AMERICA", "weight": 0.106},
    ],
}

if __name__ == "__main__":
    result = bl.run_backtest_logic(dict(BODY))
    if not result.get("guru_pit"):
        raise SystemExit("guru_pit이 비었다 — 시점별 스케줄을 못 만들었다(가격 DB 확인)")
    os.makedirs("tmp", exist_ok=True)
    with open("tmp/guru_pit_sample.json", "w", encoding="utf-8") as fh:
        json.dump({"body": BODY, "result": result}, fh, ensure_ascii=False)
    print("guru_pit =", result["guru_pit"])
    print("saved: tmp/guru_pit_sample.json")
