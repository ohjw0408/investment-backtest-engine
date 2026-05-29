---
updated: 2026-05-29
tags: [dev, test]
---

# 수동 테스트 가이드

**2026-05-29 현재 상태:**
- T1: ✅ PASS (가상 데이터 배너 — 479080 synthetic ON 검증)
- T2: ✅ PASS (종합과세 경고 + 분할매도 패널 — 458730 위탁 검증)
- T3: ✅ PASS (ETF 백필 provenance DB 존재 확인)
- T4: ⛔ 무효 — Track F(isafix) 구현 시 ISA 풍차돌리기 자체가 hard block됨. Track G(G2) 완료 후 재작성 필요.

서버 배포 후 직접 눌러서 확인할 것. 결과를 Claude에게 알려주면 버그 수정 진행.

---

## T1. Track C Phase 9 — 합성 데이터 경고 배너

**위치:** 배당금 계산기 (`/calculator`)

**테스트 방법:**
1. 상장 역사가 짧은 ETF 입력 (예: 최근 출시된 한국 ETF)
2. `가상 데이터 허용` 체크박스 ON
3. 시뮬레이션 실행
4. 결과 화면 확인

**기대 결과:**
- 가상 데이터 사용 시: 결과 상단에 노란 배너 표시
  ```
  ⚠ 가상 데이터 포함 — 실측 데이터가 부족해...
  XXXXXX: 2003-01-01 ~ 2011-09-01 (OOOO행 추정)
  ```
- 가상 데이터 미사용 시 (실측 데이터 충분한 ETF): 배너 숨김

**실패 판정:** 배너가 아예 안 뜨거나, 항상 떠 있거나, JS 에러 발생

---

## T2. Tax Phase 2e — 종합과세 경고 + 분할매도 패널

**위치:** 백테스트 (`/backtest`)

**테스트 방법:**
1. TIGER 미국배당다우존스(458730) 또는 SCHD 선택
2. 세금 ON, 계좌 = 위탁
3. 초기자금 크게 설정 (예: 5억 이상), 기간 10~20년
4. 백테스트 실행
5. 결과 하단 확인

**기대 결과:**
- KR_FOREIGN 미실현 이익이 2천만원 초과이면: 주황색 패널 표시
  ```
  ⚠ 금융소득 종합과세 주의
  미실현 이익: OOO만원
  [슬라이더: 1~20년]
  일시 매도 세금: OOO만원 / 분할 매도 세금: OOO만원 / 절감액: OOO만원
  ```
- 슬라이더 움직이면 숫자 실시간 변경
- 2천만원 미만이면 패널 숨김

**실패 판정:** 패널 안 뜨거나, 슬라이더 작동 안 하거나, 숫자가 0 또는 이상한 값

---

## T3. ETF_BACKFILL Phase 2 — Provenance DB 기록

**위치:** 서버 터미널 / DB 확인

**테스트 방법:**
서버에서 아래 명령 실행:

```bash
cd /path/to/investment-backtest-engine
python - << 'EOF'
import sqlite3
from pathlib import Path

db_path = Path("data/price_cache/price_daily.db")
conn = sqlite3.connect(str(db_path))

# 테이블 존재 확인
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("테이블 목록:", [t[0] for t in tables])

# backfill_runs 확인
runs = conn.execute("SELECT COUNT(*) FROM backfill_runs").fetchone()
print("backfill_runs 행 수:", runs[0])

# price_daily_source 확인
src = conn.execute("SELECT COUNT(*) FROM price_daily_source").fetchone()
print("price_daily_source 행 수:", src[0])

# 최근 실행 5개
recent = conn.execute(
    "SELECT code, status, method, confidence, rows_written, started_at "
    "FROM backfill_runs ORDER BY started_at DESC LIMIT 5"
).fetchall()
print("\n최근 backfill_runs:")
for r in recent:
    print(" ", r)

conn.close()
EOF
```

**기대 결과:**
- `backfill_runs`, `price_daily_source`, `corporate_action_source` 테이블 존재
- 기존에 백필 실행된 적 있으면 `backfill_runs` 행 수 > 0

> ⚠️ 주의: 테이블은 백필 엔진 최초 실행 시 생성됨.
> 테이블은 있는데 행이 0개면 → 아직 백필을 새로 돌리지 않은 것 (정상).
> 테이블 자체가 없으면 → 버그.

새 백필 실행 후 확인하려면:
```bash
python -c "
from modules.backfill_engine import BackfillEngine
e = BackfillEngine(verbose=True)
r = e.backfill('360750')
print(r)
"
```
→ `result['run_id']` 값이 있으면 provenance 기록 성공.

**실패 판정:** 테이블 없음, 또는 백필 후 `run_id` 없음

---

## T4. ISA 풍차돌리기 잔여 사이클 수정 + 중도해지 체크박스

**위치:** 배당금 계산기 (`/calculator`)

**테스트 방법:**
1. 세금 ON
2. 계좌 유형 = ISA
3. ISA 풍차돌리기 ON
4. 시뮬 기간 = **3의 배수가 아닌 값** (예: 5년, 7년, 10년)
5. 실행

**기대 결과 A — 배너 표시:**
결과 상단에 주황 배너:
```
⚠ ISA 시뮬 기간이 3의 배수가 아닙니다
— 기본값은 마지막 2년을 만기 해지(9.9%)로 가정합니다.
3년 이전 중도 해지 시 추가 세금이 발생할 수 있습니다.
☐ 중도 해지 시 세금으로 다시 보기 (15.4%)
```

**기대 결과 B — 체크박스 토글:**
- 체크박스 ON: p10/p50/p90 카드 숫자 감소 (세금 더 많이 냄), 히스토그램 변경
- 체크박스 OFF: 원래 숫자로 복귀
- 페이지 새로고침 없이 즉시 반응

**기대 결과 C — 3의 배수 기간:**
- 시뮬 기간 = 3년, 6년, 9년 → 배너 표시 안 됨

**실패 판정:**
- 배너 안 뜨거나
- 체크박스 눌러도 숫자 안 변하거나
- 만기/중도해지 값이 동일하게 나오거나 (세율 차이 미반영)
- 3의 배수인데 배너 뜨거나

---

## 결과 보고 방법

테스트 후 Claude에게:
```
T1: PASS / FAIL (실패 시 어떤 증상인지)
T2: PASS / FAIL
T3: PASS / FAIL (출력 결과 붙여넣기)
T4: PASS / FAIL
```

형식으로 알려주면 됨.
