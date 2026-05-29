# 인수인계 — 2026-05-29 (2차 업데이트)

## 완료된 작업

### Track F — ISA/계좌 규제 정합성 (커밋 e8b7c1e)
- ISA+SPY 등 불법 조합 → hard error (투자계산기/연금/배당금 계산기)
- IRP + 원자재 ETF → hard error
- ISA 초기/월 납입 한도 → hard error
- ISA 풍차돌리기 → hard error
- ISA 총 1억 초과 → 캡핑 + 주황 경고 배너

### PHASE4 빠른 항목들
- **F1** (1c5db23): 대기 UX — rank < 2 → "곧 시작됩니다"
- **B2-c** (1c5db23): 내자산 현재가 Redis 캐싱 + US 배치 조회
- **B2-b** (02cb3e8): 자산 추이 차트 (myassets 자산현황 탭)
- **B3** (02cb3e8): 리밸런싱 경고 밴드 5%
- **D5** (7182ad1): 인플레이션 생활비 인포박스 + 명목수익률 안내

---

## 지금 당장 할 일: Hetzner 배포

```bash
ssh -i ~/.ssh/hetzner_ed25519 root@5.78.209.211
cd /root/investment-backtest-engine
git pull --ff-only
systemctl restart domino domino-celery
```

---

## 직접 확인해야 할 항목 (브라우저 테스트)

### Track F 테스트 (T-F1 ~ T-F8)

| # | 위치 | 테스트 | 기대 결과 |
|---|------|--------|-----------|
| T-F1 | `/calculator` | 세금 ON + ISA + SPY + 시뮬 실행 | 빨간 에러 배너 |
| T-F2 | `/calculator` | 세금 ON + ISA + 458730(TIGER) + 시뮬 실행 | 정상 결과 |
| T-F3 | `/calculator` | 세금 ON + ISA + 초기금 3000만 | 빨간 에러 배너 (초과) |
| T-F4 | `/calculator` | 세금 ON + ISA + 초기 1000만 + 월 100만 | 빨간 에러 배너 (83만 한도) |
| T-F5 | `/calculator` | 세금 ON + ISA + 초기 500만 + 월 50만 + 20년 | 주황 경고 배너 (1억 캡) |
| T-F6 | `/retirement` | 세금 ON + 연금저축 + SPY | 빨간 에러 배너 |
| T-F7 | `/retirement` 또는 `/calculator` | 세금 ON + IRP + 132030(KODEX 골드선물) | 빨간 에러 배너 |
| T-F8 | `/calculator` | 세금 ON + 연금저축 + 132030 | 정상 결과 (연금저축은 원자재 허용) |

### PHASE4 테스트

| # | 위치 | 테스트 | 기대 결과 |
|---|------|--------|-----------|
| T-B2b | `/myassets` | 자산현황 탭 하단 | 자산 추이 차트 표시 (1개월/3개월/1년/전체) |
| T-B3 | `/myassets` → 리밸런싱 탭 | 목표비중 설정된 그룹 있을 때 | 밴드 이탈 시 주황 경고, 정상 시 초록 OK |
| T-D5 | `/retirement` | 월 인출금/기간/인플레이션 입력 | 입력창 아래 "인플레이션 반영 생활비" 인포박스 실시간 갱신 |

---

## 테스트 완료 후 보고 형식

```
T-F1: PASS / FAIL
T-F2: PASS / FAIL
T-F3: PASS / FAIL
T-F4: PASS / FAIL
T-F5: PASS / FAIL
T-F6: PASS / FAIL
T-F7: PASS / FAIL
T-F8: PASS / FAIL
T-B2b: PASS / FAIL
T-B3: PASS / FAIL
T-D5: PASS / FAIL
```

---

## 다음 작업 후보

1. **D4 거래수수료**: FeeEngine → simulation_loop.py 연결. 1~2일. 복잡함.
2. **D1 TDF**: TDF(Target Date Fund) 기능. 3~4일.
3. **D2 연금 통합 계산기**: 4~5일.
4. **Track G**: 다중 계좌 시뮬 엔진. Track F 완료됐으므로 시작 가능. 2~3주.

```text
# 원하는 다음 작업 명령어:
D4: "D4 거래수수료 설정 구현해줘"
D1/D2: "D1 TDF 기능 구현해줘"
Track G: "PHASE4_PLAN.md § 4G G1부터 구현해줘"
```
