"""로컬 E2E용 보유종목 시드 — 빈 화면 대신 실제 렌더 상태를 보기 위함.

글자배율 검증(test_font_scale_responsive.js)은 홈 총자산 같은 "긴 숫자"가 실제로
렌더돼야 잘림을 재현할 수 있다. 비로그인 데모 카드는 모바일(≤768px)에서 display:none
이라 로그인 상태 + 보유종목이 필요하다.

사용: venv\\Scripts\\python.exe tests\\seed_e2e_holdings.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.auth_manager import (  # noqa: E402
    get_or_create_user, get_holdings, upsert_holding, init_holdings_db,
)

# 엄마 폰에서 잘린 금액(₩75,808,745)과 같은 자릿수가 나오도록 잡은 수량
SEED = [
    ("005930", 800, 71000),    # 삼성전자
    ("000660", 120, 175000),   # SK하이닉스
    ("379780", 300, 14500),    # RISE 미국S&P500
    ("QQQ",     40, 480),      # 미국 ETF (환산 포함 경로 확인용)
]

init_holdings_db()
user = get_or_create_user("e2e-local", "e2e-local@test.com", "E2E로컬", "")
uid = user["id"]

existing = {h["code"] for h in get_holdings(uid)}
added = 0
for code, qty, avg in SEED:
    if code in existing:
        continue
    upsert_holding(uid, code, qty, avg)
    added += 1

print(f"user_id={uid} seeded={added} total={len(get_holdings(uid))}")
