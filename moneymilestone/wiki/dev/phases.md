---
updated: 2026-05-27
sources: [세금에서시작된완전리팩토링계획.plan.md, ETF_BACKFILL_ARCHITECTURE_PLAN.md, SYNTHETIC_DATA_INTEGRATION_PLAN.md]
tags: [dev]
---

# Phase별 진행 상황

---

## 세금 리팩토링 (Tax Refactoring)

목표: 모든 시뮬 화면이 단일 세금 도메인 + 단일 시뮬 파이프라인 공유.

| Phase | 내용 | Gate | 상태 | 비고 |
|---|---|---|---|---|
| Phase 1 | TaxProfile·TaxSessionState·liquidation 추출. 절세매도 분리. 백테스트 청산세 통일. | Gate 1 | ✅ 완료 | harvest off=38,415,192 / on=41,990,905 ±1원 |
| Phase 2a | TaxableSimulationRunner 구현 + 백테스트 마이그레이션 | Gate 2a | ✅ 완료 | 4/4 pass 1.35s |
| Phase 2b | 투자계산기 + 은퇴 적립 Runner 전환 | Gate 2b | ✅ 완료 | 4/4 pass 3.28s |
| Phase 2c | 배당 역산 Runner 전환 + `sim/tax_engine.py` 삭제 | Gate 2c | ⏳ 구현됨, Gate 블로킹 | SCHD/TIGER 불일치 → Track A 선행 필요 |
| Phase 2d | 은퇴 인출 세금 주입 (`WithdrawalAnalyzer`) | Gate 2d | ⏳ 대기 | Phase 2c Gate 통과 후 |
| Phase 2e | 금융소득 종합과세 경고 + 분할매도 절세 패널 | — | ⏳ 대기 | KR_FOREIGN 이익 2천만 초과 시 UI |
| Phase 3 | ISA 풍차돌리기 Runner 통일. 정리. 문서화. | Gate 5+6 | ⏳ 대기 | Phase 2 전체 완료 후 |

**미완료 태스크**:
- `phase1-tax-profile-api`: TaxProfile API 통일 (other_financial_income 주입)

---

## ETF 백필 안정화 (Backfill Stabilization)

목표: SCHD/TIGER 데이터 불일치 해소 → Phase 2c Gate 통과 가능하게.

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 0 | 진단 스크립트, 현재 백필 상태 리포트 생성 | ⏳ **지금 시작 (Track A)** |
| Phase 1 | 즉각적 수정: `_fetch_fred()` 구현, KOSDAQ150→KQ150 매핑, DJUSDIV100 보강, PriceLoader 실패 처리 수정, 인덱스 충분성 검사 추가 | ⏳ Track A |
| Phase 2 | Provenance 스키마: `backfill_runs`, `price_daily_source`, `corporate_action_source` 테이블 추가 | 💡 나중에 |
| Phase 3~10 | ETF 유니버스 확장, Proxy Mapping 시스템, BackfillEngine V2, Bond 모델 등 | 💡 장기 |

**현재 즉시 필요한 것 (Phase 0~1만)**:
- `DJUSDIV100` 인덱스 범위 확인 + 보강
- `_fetch_fred()` 메서드 추가
- `KOSDAQ150 → KQ150` 매핑 추가 확인
- `PriceLoader` 실패 코드 완료 처리 수정
- `dividend_simulator._calc_div_stats()` 미완료 연도 제외

---

## 합성 데이터 통합 (Synthetic Data Integration)

목표: 투자계산기·백테스트에 opt-in 합성 데이터 지원 + 공통 facade.

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 0 | 기존 합성 데이터 경로 문서화 (DataPreparer, WithdrawalAnalyzer, DividendSimulator) | ⏳ Track C |
| Phase 1 | `ScenarioDataPreparer` facade 추가 | ⏳ Track C |
| Phase 2 | `DataPreparer`에 `allow_backfill`, `allow_synthetic` 플래그 추가 | ⏳ Track C |
| Phase 3 | 투자계산기 통합 + UI 체크박스 | ⏳ Track C |
| Phase 4 | 백테스트 통합 + UI 체크박스 | ⏳ Track C |
| Phase 5~10 | 은퇴, 배당, provenance 정렬 등 | 💡 나중에 |

---

## PHASE4 제품 기능

→ 전체 체크리스트: [[dev/status]]  
→ 완료 항목: A1 A2 A3 A5 A6 B5 C3 C5 D3
