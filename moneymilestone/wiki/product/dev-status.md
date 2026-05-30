---
updated: 2026-05-30
sources: [PROJECT_MASTER_ROADMAP.md, 세금에서시작된완전리팩토링계획.plan.md, ETF_BACKFILL_ARCHITECTURE_PLAN.md]
tags: [product, tech]
---

# 개발 현황 + 블로커

마지막 업데이트: 2026-05-30 기준.

## 현재 상태 한 줄 요약

> 🔴 **배당 데이터 근본 버그가 현재 블로커.** 세금 리팩토링(Phase 1~3, 2a/2b/2d)·Track F·Track G G1·합성데이터까지 진행됐으나, 배당 액수가 0으로 깨져 있어 세금 Phase 2c(배당 역산)/2e(금종세)와 Track G(다중계좌 세금)를 검증·완성할 수 없음. **배당 백필 재설계(ETF_BACKFILL Phase 6.0)가 1순위.**

## 세금 리팩토링 진행 상황

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 1 | 세금 공통 코어, 절세매도 분리, 청산세 통일 | ✅ 완료 (Gate 1 통과) |
| Phase 2a | TaxableSimulationRunner + 백테스트 | ✅ 완료 (Gate 2a 통과) |
| Phase 2b | 투자계산기 + 은퇴 적립 Runner 전환 | ✅ 완료 (Gate 2b 통과) |
| Phase 2c | 배당 역산 Runner 전환 | ✅ 구현 / 🔴 Gate 재검증 필요 (배당 데이터 0 버그) |
| Phase 2d | 은퇴 인출 세금 주입 | ✅ 완료 (Gate 2d 5/5) |
| Phase 2e | 금융소득 종합과세 경고 + 분할매도 패널 | ⚠️ 부분 구현 (엔진+백테스트만, 아래) |
| Phase 3 | 정리, ISA Runner 통일, 문서화 | ✅ 완료 |
| phase1-api | TaxProfile API 통일 (other_financial_income 주입) | ⏳ 미완료 |

**종합과세(Phase 2e) 실제 상태** (코드 확인 2026-05-30):
- ✅ 계산 엔진 (`base_tax._comprehensive_tax`/2천만 임계/비례공제) — 완전, `tax_truth_test` 단위검증 통과
- ✅ 시뮬 내 당해연도 배당 YTD 누적 트리거 (`account_tax.TaxedDividendEngine`)
- ⚠️ 분할매도/종합과세 패널 — `backtest_logic.py`에만 배선. 계산기/배당/연금 미배선
- ❌ `other_financial_income` 자동산출 미구현 (backtest가 user_settings 수동값/0 — plan 금지 방식)
- ❌ `_ytd_income` 0 고정 — 기존 금융소득 미주입
- 🔴 종합과세 입력 = 배당인데 배당 데이터 0 → 실전 발동 안 함

## 🔴 현재 블로커: 배당 데이터 근본 버그

**증상**: TIGER 미국배당다우존스(458730) 배당 지표 전부 0, SCHD 다수 0. 단일·다중계좌 공통.

**근본 원인** (`debug_dividend.py` 실측 2026-05-30):
1. 백필 가격은 프록시 체인으로 1928년까지 존재(458730 97%, SCHD 85%가 volume=0 백필).
2. 실측 배당(`corporate_actions`)은 ETF 상장 후만(SCHD 2011~, 458730 2023~). 백필 가격 구간에 배당 row 없음.
3. DJUSDIV_PROXY가 **adj-close(total-return)**라 배당이 가격에 임베딩 → 별도 액수 안 나옴 (`_NO_DIVIDEND_INDICES`에 의도적 제외).
4. `data_start`=1928 → 20년 롤링 윈도우 대부분 배당 이전 시대 → `_fit_distribution` p50=0.
5. 백필 provenance 전부 0행 (가격 백필이 `BackfillEngine` 우회).

**해결 방향** (`ETF_BACKFILL_ARCHITECTURE_PLAN.md § Phase 6.0` — 범용 배당 백필 재설계):
- 모든 백필을 'price-return 가격 + 명시적 배당' 표준으로 통일 (total-return 임베딩 폐기, 이중계산 차단).
- Stage A 주식/배당형 먼저 → Stage B 채권/MMF(필수, Phase 7).

## 다음 실행 트랙 (의존성 순서)

```
[1] 배당 백필 범용 재설계 Stage A (ETF_BACKFILL Phase 6.0) — 현재 최우선
  → [2] 세금 Phase 2c/2e 재검증 (정상 배당 데이터로)
  → [3] 배당 백필 Stage B (채권/MMF, Phase 7)
  → [4] Track G 재개 (다중계좌 세금)
  → [5] PHASE4 잔여 (D4/D1/D2/B1/A4/C1/C2/B4)
```

### 다음 실행 명령어
```
ETF_BACKFILL_ARCHITECTURE_PLAN.md § Phase 6.0 Stage A 구현해줘
```

## 사업 일정 대비 현재 위치

| 기간 | 계획 | 현황 |
|---|---|---|
| 2026.06 | 시뮬레이션 엔진 개발 | ⏳ 세금 리팩 완성 필요 |
| 2026.07 | 기타 엔진 (배당, 알림, TDF) | ⏳ 배당 세금 연동 블로커 |
| 2026.08 | 로그인, 개인 계정, 즐겨찾기 | ⏳ 대기 |
| 2026.09 | 코드 안정화 (Windows/iOS/Android) | ⏳ 대기 |
| 2026.10 | 수익 모델 (구독, 광고) | ⏳ 대기 |
| 2026.11 | 마케팅 + 앱스토어 배포 | 🎯 목표 |

→ 전체 기능 목록: [[product/features]]
