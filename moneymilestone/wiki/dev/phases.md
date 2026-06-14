---
updated: 2026-06-13
sources: [세금에서시작된완전리팩토링계획.plan.md, ETF_BACKFILL_ARCHITECTURE_PLAN.md, SYNTHETIC_DATA_INTEGRATION_PLAN.md]
tags: [dev]
---

# Phase별 진행 상황

> ✅ **2026-06-13 동기화:** 세금 리팩토링 전 Phase 완료(2c 재검증 05-31 PASS, 2e/2f·phase1-api는 4100ecd로 충족). 배당 백필 Stage A+B 완료. 합성 데이터 체크박스 전 탭(은퇴는 06-11 추가). 자세한 정정 근거 = `세금에서시작된완전리팩토링계획.plan.md` 2026-06-13 정정 노트.

---

## 세금 리팩토링 (Tax Refactoring)

목표: 모든 시뮬 화면이 단일 세금 도메인 + 단일 시뮬 파이프라인 공유.

| Phase | 내용 | Gate | 상태 | 비고 |
|---|---|---|---|---|
| Phase 1 | TaxProfile·TaxSessionState·liquidation 추출. 절세매도 분리. 백테스트 청산세 통일. | Gate 1 | ✅ 완료 | harvest off=38,415,192 / on=41,990,905 ±1원 |
| Phase 2a | TaxableSimulationRunner 구현 + 백테스트 마이그레이션 | Gate 2a | ✅ 완료 | 4/4 pass 1.35s |
| Phase 2b | 투자계산기 + 은퇴 적립 Runner 전환 | Gate 2b | ✅ 완료 | 4/4 pass 3.28s |
| Phase 2c | 배당 역산 Runner 전환 + `sim/tax_engine.py` 삭제 | Gate 2c | ✅ 완료 | 재검증 PASS 3/3 (2026-05-31, 정상 배당 데이터 기준) |
| Phase 2d | 은퇴 인출 세금 주입 (`WithdrawalAnalyzer`) | Gate 2d | ✅ 완료 | Gate 2d PASSED 5/5 (2026-05-28) |
| Phase 2e/2f | 금융소득 종합과세 + 분할매도 절세 패널 | — | ✅ 완료 (4100ecd, 2026-05-31) | 자동산출·전탭배선·_ytd_income 주입 전부. 인출(decum)도 기배선 확인(06-12) |
| Phase 3 | ISA 풍차돌리기 Runner 통일. 정리. 문서화. | Gate 5+6 | ✅ 완료 | TaxableSimulationRunner N회 전환 (2026-05-28) |
| phase1-api | TaxProfile API 통일 (other_financial_income 주입) | — | ✅ 완료 (2026-06-13 정리 — 2f로 충족) | _ytd_income 주입 = account_tax.py:243 코드 확인 |

---

## ETF 백필 안정화 (Backfill Stabilization)

목표: 배당 포함 데이터 정확성 확보 → 세금 배당/종합과세 검증 가능하게.

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 0 | 진단 스크립트, 현재 백필 상태 리포트 생성 | ✅ 완료 (2026-05-28) |
| Phase 1 | `_fetch_fred()` 구현, KOSDAQ150→KQ150 매핑, DJUSDIV100 보강, PriceLoader 실패 처리, 인덱스 충분성 검사 | ✅ 완료 (가격 한정) |
| Phase 2 | Provenance 스키마(`backfill_runs`/`price_daily_source`/`corporate_action_source`) | ✅ Stage A 백필 가격/배당 기록에 사용 |
| **Phase 6.0 Stage A** | **price-return + 명시적 배당. DJUSDIV_PROXY raw-close 교체, SCHD/458730/446720/402970 재백필, UI 실측/추정 구분** | **✅ 서버 적용 완료 (2026-05-30, Codex)** |
| **Phase 6.0 Stage B / Phase 7** | **채권/MMF 금리→가격+쿠폰 분배금 모델** | ✅ 완료 (2026-05-31, 서버검증 — 한국 채권 전유형·환헤지비용·US 채권 자동분류·통화가드) |
| Phase 3~5,7~10 | ETF 유니버스 확장, Proxy Mapping, BackfillEngine V2, Bond 모델 등 | 💡 장기 |

> ✅ Stage A 서버 검증: `stage_a_verify.py`, `debug_dividend.py`, 계산기 직접 실행에서 배당 지표 p50 > 0 및 `div_real_start/div_is_backfilled` 확인.

---

## 합성 데이터 통합 (Synthetic Data Integration)

목표: 투자계산기·백테스트에 opt-in 합성 데이터 지원 + 공통 facade.

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 0~4 | 경로 문서화, `ScenarioDataPreparer` facade, `DataPreparer` 플래그, 투자계산기·백테스트 통합 + UI 체크박스 | ✅ 완료 (Track C, 2026-05-28) |
| 은퇴 탭 체크박스 | 은퇴 sim/인출 `use_synthetic` + 합성 폴백·실측/가상 라벨 | ✅ 완료 (2026-06-11, 9486eee — GAP-RET-KRDATA 해소) |
| 상관 복원 | 종목 간 상관(조건부 다변량, `synthetic_mvn.py`) | ✅ 구현(2026-06-06) · ⚠️ 서버 실데이터 검증 대기 |
| Phase 5~10 잔여 | provenance 정렬 등 | 💡 나중에 |

> 합성 데이터(GBM, opt-in)와 배당 백필(Phase 6.0)은 별개 경로. 합성은 완료, 배당 Stage A도 완료. 채권/MMF Stage B는 후속.

---

## PHASE4 제품 기능

→ 전체 체크리스트: [[dev/status]]  
→ 완료 항목: A1 A2 A3 **A4** A5 A6 B5 **C1** C3 C5 D3 **D4** + F1 B2-b B2-c B3 D5 + **B1 D6 E1 4G** (2026-06-15 갱신)  
→ C1(2026-06-14)=홈위젯·관심목록·설정. C1 후속(2026-06-15)=지수 캔들 회귀복구(index_ohlc)·새로고침버튼(내자산/홈/검색)·내자산 수동가격  
→ 미착수: C2, B4, D1, D2, E2~E4, C4  (B2-a=오너 skip)
