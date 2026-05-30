---
updated: 2026-05-30
sources: [세금에서시작된완전리팩토링계획.plan.md, ETF_BACKFILL_ARCHITECTURE_PLAN.md, SYNTHETIC_DATA_INTEGRATION_PLAN.md]
tags: [dev]
---

# Phase별 진행 상황

> 🔴 **2026-05-30 정정:** 과거 "SCHD/TIGER 수렴 / Gate 2c 통과"는 **가격(CAGR) 수렴만** 검증된 것. 배당 액수는 0으로 깨져 있음(`debug_dividend.py` 실측). 원인은 DJUSDIV_PROXY가 total-return(adj-close)이라 배당이 가격에 임베딩 + 백필 구간 배당 row 부재. 이게 현재 블로커. owner: `ETF_BACKFILL § Phase 6.0`.

---

## 세금 리팩토링 (Tax Refactoring)

목표: 모든 시뮬 화면이 단일 세금 도메인 + 단일 시뮬 파이프라인 공유.

| Phase | 내용 | Gate | 상태 | 비고 |
|---|---|---|---|---|
| Phase 1 | TaxProfile·TaxSessionState·liquidation 추출. 절세매도 분리. 백테스트 청산세 통일. | Gate 1 | ✅ 완료 | harvest off=38,415,192 / on=41,990,905 ±1원 |
| Phase 2a | TaxableSimulationRunner 구현 + 백테스트 마이그레이션 | Gate 2a | ✅ 완료 | 4/4 pass 1.35s |
| Phase 2b | 투자계산기 + 은퇴 적립 Runner 전환 | Gate 2b | ✅ 완료 | 4/4 pass 3.28s |
| Phase 2c | 배당 역산 Runner 전환 + `sim/tax_engine.py` 삭제 | Gate 2c | ✅ 구현 / 🔴 재검증 필요 | 진짜 원인=배당 데이터 0 버그. 가격 수렴만 검증됐었음 |
| Phase 2d | 은퇴 인출 세금 주입 (`WithdrawalAnalyzer`) | Gate 2d | ✅ 완료 | Gate 2d PASSED 5/5 (2026-05-28) |
| Phase 2e | 금융소득 종합과세 경고 + 분할매도 절세 패널 | — | ⚠️ 부분 구현 | 엔진+백테스트 배선만. 자동산출/전탭배선/_ytd_income 미완 |
| Phase 3 | ISA 풍차돌리기 Runner 통일. 정리. 문서화. | Gate 5+6 | ✅ 완료 | TaxableSimulationRunner N회 전환 (2026-05-28) |
| phase1-api | TaxProfile API 통일 (other_financial_income 주입) | — | ⏳ 미완료 | _ytd_income 0 고정 |

---

## ETF 백필 안정화 (Backfill Stabilization)

목표: 배당 포함 데이터 정확성 확보 → 세금 배당/종합과세 검증 가능하게.

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 0 | 진단 스크립트, 현재 백필 상태 리포트 생성 | ✅ 완료 (2026-05-28) |
| Phase 1 | `_fetch_fred()` 구현, KOSDAQ150→KQ150 매핑, DJUSDIV100 보강, PriceLoader 실패 처리, 인덱스 충분성 검사 | ✅ 완료 (가격 한정) |
| Phase 2 | Provenance 스키마(`backfill_runs`/`price_daily_source`/`corporate_action_source`) | ⚠️ 스키마만 존재 — 실제 백필이 우회, 458730/SCHD provenance 0행 |
| **Phase 6.0** | **🔴 범용 배당 백필 재설계 (price-return + 명시적 배당). DJUSDIV_PROXY 등 total-return 체인 raw-close 교체. Stage A 주식형 → Stage B 채권/MMF(필수)** | **🔴 현재 최우선** |
| Phase 3~5,7~10 | ETF 유니버스 확장, Proxy Mapping, BackfillEngine V2, Bond 모델 등 | 💡 장기 |

> ⚠️ "DJUSDIV_PROXY 체인 구축, SCHD vs TIGER 수렴"(2026-05-28)은 **가격만** 맞춘 것. adj-close라 배당 액수가 0 → Phase 6.0에서 raw-close + 명시적 배당으로 재작업.

---

## 합성 데이터 통합 (Synthetic Data Integration)

목표: 투자계산기·백테스트에 opt-in 합성 데이터 지원 + 공통 facade.

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 0~4 | 경로 문서화, `ScenarioDataPreparer` facade, `DataPreparer` 플래그, 투자계산기·백테스트 통합 + UI 체크박스 | ✅ 완료 (Track C, 2026-05-28) |
| Phase 5~10 | 포트폴리오 분석, 은퇴 facade 전환, 배당 분리, provenance 정렬 등 | 💡 나중에 |

> 합성 데이터(GBM, opt-in)와 배당 백필(Phase 6.0)은 별개 경로. 합성은 완료, 배당 백필은 블로커.

---

## PHASE4 제품 기능

→ 전체 체크리스트: [[dev/status]]  
→ 완료 항목: A1 A2 A3 A5 A6 B5 C3 C5 D3 + F1 B2-b B2-c B3 D5  
→ 미완/이슈: D4(미착수), D5(인플레 총액 유효숫자/금액 버그 — handoff 참고), A4 B1 C1 C2 B4 D1 D2
