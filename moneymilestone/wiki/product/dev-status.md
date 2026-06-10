---
updated: 2026-06-10
sources: [PROJECT_MASTER_ROADMAP.md, trackG_multiaccount_plan.md, 세금에서시작된완전리팩토링계획.plan.md]
tags: [product, tech]
---

# 개발 현황 + 블로커

마지막 업데이트: 2026-06-10 기준. (최신 상세는 [[dev/status]]가 항상 우선)

## 현재 상태 한 줄 요약

> ✅ **Track G5 다중계좌 4탭(계산기·백테·은퇴적립·은퇴인출) 전체 완료(2026-06-09, 세금감사 신규버그 0) + 간편 계산기 4종 `/simple` 배포(2026-06-10).** 블로커 없음. **다음 = 다계좌 세금 E2E 실브라우저 검증**(`다계좌세금_E2E검증_plan.md` 16건, Playwright 도입으로 자동화 가능) OR 세금계산기(P1). GAP-DECUM-COMP는 오너 보류. 상세 = [[dev/status]].

## 세금 리팩토링 진행 상황

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 1 | 세금 공통 코어, 절세매도 분리, 청산세 통일 | ✅ 완료 (Gate 1 통과) |
| Phase 2a | TaxableSimulationRunner + 백테스트 | ✅ 완료 (Gate 2a 통과) |
| Phase 2b | 투자계산기 + 은퇴 적립 Runner 전환 | ✅ 완료 (Gate 2b 통과) |
| Phase 2c | 배당 역산 Runner 전환 | ✅ 완료 (Gate 2c 재검증 PASS, 2026-05-31) |
| Phase 2d | 은퇴 인출 세금 주입 | ✅ 완료 (Gate 2d 5/5) ⚠️ BUG-TAX-2: 인출 매도 위탁 양도세 누락은 수정됨(공유 sell_with_tax) |
| Phase 2e/2f | 금융소득 종합과세 + 분할매도 패널 | ✅ 다중계좌 배선 완료(공유세션 개인합산·comprehensive_years). 단일계좌도 surface. ⚠️ other_financial_income 전탭 자동산출만 잔여 |
| Phase 3 | 정리, ISA Runner 통일, 문서화 | ✅ 완료 |
| phase1-api | TaxProfile API 통일 (other_financial_income 주입) | ⏳ 미완료 (전탭 자동산출) |

**종합과세(Phase 2e) 실제 상태** (코드 확인 2026-05-30):
- ✅ 계산 엔진 (`base_tax._comprehensive_tax`/2천만 임계/비례공제) — 완전, `tax_truth_test` 단위검증 통과
- ✅ 시뮬 내 당해연도 배당 YTD 누적 트리거 (`account_tax.TaxedDividendEngine`)
- ⚠️ 분할매도/종합과세 패널 — `backtest_logic.py`에만 배선. 계산기/배당/연금 미배선
- ❌ `other_financial_income` 자동산출 미구현 (backtest가 user_settings 수동값/0 — plan 금지 방식)
- ❌ `_ytd_income` 0 고정 — 기존 금융소득 미주입
- 🔁 종합과세 입력 = 배당. Stage A 정상 배당 데이터 기준으로 실제 발동/금액 재검증 필요

## ✅ 해결된 블로커: 배당 데이터 근본 버그

**기존 증상**: TIGER 미국배당다우존스(458730) 배당 지표 전부 0, SCHD 다수 0. 단일·다중계좌 공통.

**근본 원인** (`debug_dividend.py` 실측 2026-05-30):
1. 백필 가격은 프록시 체인으로 1928년까지 존재(458730 97%, SCHD 85%가 volume=0 백필).
2. 실측 배당(`corporate_actions`)은 ETF 상장 후만(SCHD 2011~, 458730 2023~). 백필 가격 구간에 배당 row 없음.
3. DJUSDIV_PROXY가 **adj-close(total-return)**라 배당이 가격에 임베딩 → 별도 액수 안 나옴 (`_NO_DIVIDEND_INDICES`에 의도적 제외).
4. `data_start`=1928 → 20년 롤링 윈도우 대부분 배당 이전 시대 → `_fit_distribution` p50=0.
5. 백필 provenance 전부 0행 (가격 백필이 `BackfillEngine` 우회).

**해결 방향** (`ETF_BACKFILL_ARCHITECTURE_PLAN.md § Phase 6.0` — 범용 배당 백필 재설계):
- 모든 백필을 'price-return 가격 + 명시적 배당' 표준으로 통일 (total-return 임베딩 폐기, 이중계산 차단).
- Stage A 주식/배당형 먼저 → Stage B 채권/MMF(필수, Phase 7).

**적용 결과** (2026-05-30, Codex):
- Stage A 서버 적용 완료: SCHD/458730/446720/402970 재백필 + 명시 배당 주입.
- 서버 `stage_a_verify.py`, `debug_dividend.py`, 계산기 직접 실행에서 배당 p50 > 0 확인.
- UI가 `div_real_start`/`div_backfill_start` 기준 실측/추정 구분 표시.

## 다음 실행 트랙 (의존성 순서)

```
[P0] Track G5 다중계좌 탭 복제 — 현재 진행
  ✅ G5-A 백테스트 백엔드+L10  ✅ G5-C 토대(연금 분리과세)
  → G5-C 인출 엔진 본체(가구 인출 오케스트레이터+연금소득세+생존율+L12)
  → 통합(run_retirement_logic 적립+인출 멀티) → UI 일괄(backtest.js·retirement.js)
[P1] 신규 간편 도구 — 간편계산기 묶음 / 세금 전환 계산기
[P2] 절세액 P2/P3 · 종합과세 other_financial_income 전탭 자동산출
[P3] PHASE4 (즐겨찾기→리스크리턴도표, D1/D2/A4/C1/C2)
```

### 다음 실행 명령어
```
G5-C 은퇴 인출 엔진 구현해줘
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
