# 세금 의사결정 계산기 계획 (아이디어 기록)

작성: 2026-06-03 (Claude, 오너 아이디어). 상태: **아이디어 — 미착수.**
연관: `절세액표시_plan.md`(가정 비교) / 이건 **실제 전환 결정** 비교.

---

## 한 줄 정의

"지금 보유한 **위탁 자산을 팔아서(양도세 내고) ISA로 옮길까**, 아니면 **그냥 위탁에서 계속 굴릴까**?"
— 전환비용(지금 내는 양도세) vs 미래 ISA 세제혜택을 정면 비교해 답을 주는 결정 도구.

기존 절세액 표시(if-위탁-가정)와 다름: 이건 **실제 갈아타기 결정**(스위칭 코스트 포함).

---

## 왜 (제품 관점)

- **온-모트:** 앱의 킥 = 한국 세금 정확 반영. 이건 그 정수(전환 양도세 vs ISA 만기세).
- **액셔너블:** 시뮬 구경이 아니라 "A 이득 / B 이득 / 몇 년 뒤 역전" 답.
- 타겟층(박곰희TV 구독자)이 실제로 고민하는 질문.

## 비교 두 전략

- **A) 위탁 유지:** 현재 보유 그대로 위탁에서 N년 운용. 배당세·양도세 반영.
- **B) 지금 ISA 이전:** 현재 평가액에서 **지금 매도 양도세** 차감 → 순액을 ISA로 → N년 → ISA 만기세(9.9%).

→ 종료자산(중앙값) 비교. 차이 + 가능하면 **역전(breakeven) 기간** 표시.

## 입력

- 현재 위탁 **평가액**
- 현재 **취득가**(= 지금 팔 때 양도차익·세금 계산용) ← **필수**
- 종목(분류·미래수익 시뮬용)
- 투자 기간(N년)
- (세금설정에서) 나이·근로소득·ISA유형

## 핵심 난점 — ISA 연 2천만 한도

위탁 평가액 > 2천만이면 한 번에 ISA 못 넣음. 두 갈래(v1 결정 ⏳):
- **(a) 분할 이전 모델:** 매년 2천만씩 위탁→ISA(`backfill`과 동일 메커니즘). 정확하나 복잡·검증 어려움.
- **(b) v1 단순:** 2천만 이하만 깔끔 비교, 초과는 "분할 필요" 안내. 단순·안전.
- ✅ **오너 결정(2026-06-12): (a) 분할 이전 모델로 v1.** UI = 독립 페이지.

## 구현 난이도 = 중간 (backfill 자동로직보다 쉽고 안전)

- 핵심 = **독립 시뮬 2번 + 비교.** 연도별 셔플·우선순위 상호작용 없음.
- 엔진 재사용: `TaxableSimulationRunner`(위탁/ISA 각각) 또는 멀티 루프.
- "지금 매도 양도세" = 현재 미실현차익에 분류별 세율(KR_FOREIGN 15.4%·US 250만공제후 22%·국내/금 0%) 1회 적용 — `saving_estimate`/`liquidation` 로직 재사용.

## 검증 (깔끔)

- 결정론 픽스처: A 종료값·B 종료값 각각 손계산 ±1원.
- 경계: 전환세 0(손실 종목)·breakeven 존재/부재·2천만 경계.
- 불변식: 차익 0이면 A==B(전환세 0, ISA 만기세도 0).

## 반려된 형제 아이디어 — ISA 자동 채움(backfill)

매년 ISA 빈 한도를 위탁 팔아 자동 채우는 로직. **반려(고급옵션 후보):**
- 일반 투자자 거의 안 하는 능동 절세행동, 모델에 숨기면 혼란.
- 위탁 양도세 즉시 발생 → 순이득 모호.
- 복잡·검증난 → 세금(모트) 자리에 버그 위험 = 리스크>보상.
- 대신 이 **결정 계산기**가 같은 질문을 사용자에게 **드러내서** 답하는 더 나은 형태.

---

## v1 구현 설계 (2026-06-12, 오너 결정 반영: (a) 분할 이전 + 독립 페이지)

### 엔진 재사용 결론 (조사 완료)

| 필요 | 재사용 | 비고 |
|---|---|---|
| 취득가 주입(초기 미실현차익) | `carried_cost_basis` 메커니즘 (`simulation_loop.py:97`) | day-0 매수 후 `_avg_costs` 비례축소. multi_account_loop엔 없음 → 계좌 필드로 추가 |
| 부분매도+양도세+종합과세 합산 | `TaxedOrderExecutor.sell_with_tax` + 공유 `TaxSessionState` | Phase 2f가 KR_FOREIGN 실현차익 세션 합산 이미 구현 |
| ISA 연2천만/총1억 한도 | `ContributionLimitTracker.capacity/record` | 그대로 사용 |
| ISA 만기세(200/400만 비과세+9.9%) | `TaxEngine.after_tax_withdrawal(ISA)` | `isa_type` user_settings 연동 |
| 롤링 윈도우/분포 | `MultiAccountAnalyzer` | A·B 각각 실행, 동일 data_start/end/step → 윈도우 페어링 |

### 신규 작업

1. **`MultiAccountSimulationLoop` 확장 (전부 optional·기본 None → 기존 경로 무변경):**
   - 계좌 필드 `carried_cost_basis`: first-day 매수 직후 avg_cost 비례축소 (위탁만 의미).
   - `switch_policy={"source_id":0, "dest_id":1}`: 매년 첫 거래월(+ day0 즉시)에
     `X = min(source 평가액, tracker.capacity(dest,"ISA"))` 비례 매도(sell_with_tax → 전환양도세,
     세션 합산) → 순현금을 dest로 내부이동(transfer, cash_flow 0) → dest 정책 매수.
     자체 ContributionLimitTracker 사용(transfers_enabled와 독립 게이트).
   - `yearly_after_tax_snapshot`: 연말 거래일마다 계좌별 가상청산 세후가치 기록
     → `after_tax_by_year`(combined). breakeven 산출 입력. ISA는 경과년수<3이면 중도해지 규칙.
2. **`MultiAccountAnalyzer`**: 위 신규 kwarg 패스스루 + 케이스 metrics에 after_tax_by_year·전환세 노출.
3. **`tax_switch_logic.py`**: A(단일 위탁, carried basis) vs B(위탁+ISA, switch) 동일 윈도우 페어 실행.
   출력 = A/B 종료자산 분포(중앙값), 차이, 전환양도세 총액(중앙값), breakeven 연도(페어별 → 중앙값/없음),
   연도별 세후 궤적(중앙값).
4. **API + 독립 페이지**: POST 라우트 + 템플릿/JS(다크모드·모바일 준수, 네비 추가).

### 검증 설계 (plan 원안 유지 + 보강)

- 결정론 픽스처(고정 가격): A·B 종료값 손계산 ±1원.
- 경계: 전환세 0(손실/취득가=평가액), flat 가격+배당0 → A==B 불변식, 2천만 경계, 총1억 초과 잔여 영구 위탁,
  breakeven 존재/부재.
- 회귀: Gate 2a/2b/2c + tax_truth + phase2f + trackG 전부 불변.
