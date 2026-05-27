---
updated: 2026-05-28
tags: [dev]
---

# 현재 개발 상태

**에이전트: 코드 작업 완료 후 이 파일 반드시 업데이트.**

---

## 한 줄 요약

> 세금 리팩토링 Phase 1~3 전부 완료. SYNTHETIC_DATA_INTEGRATION_PLAN 완료. Gate 2a/2b/2c/2d PASS (28/28). ETF_BACKFILL Phase 2 (Provenance 스키마 + 통합) 완료. 다음: ETF_BACKFILL Phase 3 (Universe 확장) 또는 PHASE4 기능 잔여.

---

## 최근 완료된 작업 (Claude 세션 2026-05-28 ETF_BACKFILL Phase 2)

- ✅ modules/provenance.py 신규 생성
  - backfill_runs, price_daily_source, corporate_action_source DDL
  - ensure_provenance_tables, new_run_id, write_backfill_run, write_price_source, write_action_source
  - delete_by_run_id: run_id 기준 안전 삭제 (실측 제외)
  - is_generated: 실측 vs 생성 판별 (volume=0 fallback 포함)
  - get_run_summary: 코드별 백필 이력 조회
- ✅ BackfillEngine 통합
  - __init__: ensure_provenance_tables 호출
  - inject_quarterly_dividends: 반환 타입 int → (int, list[str])
  - backfill(): 완료 후 3종 provenance 기록 (confidence B/C, run_id 반환)
- ✅ synthetic_price_generator.py: generate_and_save 반환 dict에 dates 추가
- ✅ data_preparer.py: 합성 데이터 생성 후 provenance 기록 (confidence D)
- 커밋: dd722ec

---

## 최근 완료된 작업 (Claude 세션 2026-05-28 Tax Phase 2d/2e/3)

- ✅ Tax Phase 2d: 은퇴 인출 세금 주입 (WithdrawalAnalyzer → TaxableSimulationRunner)
  - Gate 2d PASSED 5/5: 위탁 survival/end_value, 연금 pension_tax_info, IRP 에러없음
  - 커밋: 468e349
- ✅ Tax Phase 2e: 종합과세 경고 + 분할매도 절세 패널
  - split_sale_planner.py: 1~20년 분할 시나리오 세금 계산 (2천만 임계선 + 종합과세)
  - backtest.html: btSplitSalePanel, 연수 슬라이더, 절감액 실시간 표시
  - taxable_runner.py: kr_foreign_unrealized_gain 필드 추가
  - 커밋: 2c7b308
- ✅ Tax Phase 3: ISA 풍차돌리기 Runner 통일
  - _run_isa_renewal_cycle: portfolio_engine.run_simulation → TaxableSimulationRunner N회
  - isa_years_held 파라미터로 만기/중도해지 세율 자동 분기
  - 회귀: Gate 2a/2b 4+4 PASS, 전체 28/28 PASS
  - 커밋: f7f84c2

---

## 최근 완료된 작업 (Claude 세션 2026-05-28 Track C Phase 9+10)

- ✅ Phase 9 UI Warning — 가상 데이터 사용 시 경고 배너 표시
  - calculator.html: synthWarningBanner + 체크박스 (이전 세션)
  - calculator.js: renderResult에서 used_synthetic 시 배너 표시 + ticker별 날짜/행수
  - backtest.html: btUseSyntheticCheck 체크박스 + use_synthetic → payload
  - backtest.html: renderBacktest에서 btSynthWarningBanner 표시
- ✅ Phase 10 Unit Tests — tests/test_scenario_data_preparer.py 20/20 PASS
  - _calc_rolling_cases, _data_confidence, allow_synthetic=False 9케이스, allow_synthetic=True 3케이스
- 커밋: 493d856

---

## 최근 완료된 작업 (Claude 세션 2026-05-28 Track B)

- ✅ Track B: Phase 2c Gate 재검증 — G5/G6 전 케이스 PASS (커밋 781f89a)
  - SCHD 위탁: tax OFF 3,750만 / tax ON 7,125만 (+90%) [PASS]
  - 458730(TIGER) 위탁: tax OFF 4,125만 / tax ON 7,500만 (+81.8%) [PASS]
  - SCHD 종합과세 경계: tax OFF 9,375만 / tax ON 16,875만 (+80%) [PASS]
  - SCHD vs TIGER 차이: ~10% (Track A 이전 대비 대폭 수렴)

---

## 최근 완료된 작업 (Claude 세션 2026-05-28 Track A)

- ✅ Track A Step 1: 백필 현황 진단 — DJUSDIV100 1행, KQ150 없음, 백필 84.8% 확인
- ✅ Track A Step 2: DJUSDIV100 소스 조사 — Yahoo Finance 미지원 확인, SDY(0.948)/DVY(0.937) 대안 발견
- ✅ Track A Step 3: DJUSDIV_PROXY 체인 구축 — SCHD←SDY←DVY←^GSPC, 24,714행, 커밋 7b1dc6f
- ✅ Track A Step 4: KOSDAQ150→KQ150 매핑 추가, KQ150 6,284행 (KODEX229200←^KQ11), 커밋 40696f5
- ✅ Track A Step 5: index_loader_develop.py _fetch_fred() def 선언 누락 수정, 커밋 e1a4d6e
- ✅ Track A Step 6: PriceLoader 백필 실패 시 완료 처리 버그 수정 (성공만 _backfilled_codes), 커밋 a761750
- ✅ Track A Step 7: 인덱스 충분성 체크 추가 (100행 미만 거부), 커밋 e33eeeb
- ✅ Track A Step 8: div_stats 현재 연도 미완료 데이터 제외 (complete_div 필터), 커밋 ec56455
- ✅ Track A Step 9 선행 검증: SCHD/TIGER/ACE/SOL price_return_mean 9.61~9.63% 수렴 ✅

## 최근 완료된 작업 (Claude 세션 2026-05-27~28)

- ✅ 홈화면 시장 지수: Redis SETNX 락으로 thundering herd 방지 (동시 yfinance 중복 호출 차단)
- ✅ KRX 금현물 자동 갱신: Celery Beat 태스크 추가 (평일 16:30 KST 자동 실행)
- ✅ Celery Beat 서비스: `deploy/domino-celery-beat.service` 추가, deploy.yml에서 자동 등록/재시작
- ✅ OAuth MismatchingStateError: 에러 catch → 로그인 재시도 redirect (500 대신)
- ✅ SESSION_COOKIE_SAMESITE=Lax 명시 (cross-site OAuth redirect 쿠키 안정성)
- ✅ wiki 시스템 초기화: AGENTS.md, CLAUDE.md, moneymilestone/ vault 구축 및 GitHub 커밋

## 최근 완료된 작업 (Codex 세션 2026-05-27)

- ✅ 목표 배당금 계산기: 0%/짧은 히스토리 ETF가 합성 배당 통계를 왜곡하던 문제 수정
- ✅ 한국 ETF 가격 로더: `pykrx` fallback 제거. 한국 ETF 가격은 yfinance 경로만 사용
- ✅ 월납입금 자동 역산: 초기자금 증가 시 필요 월납입금이 역전되던 버그 수정
- ✅ KODEX 미국배당다우존스: 자동 역산 bracket 과도 확장으로 그래프 개형 볼록해 보이던 문제 수정
- ✅ 기간 자동 역산 탐색 범위: 1~70년으로 확장. 정확도는 기존 1년 단위 유지
- ⚠️ 확인 필요: 은퇴 시뮬레이션에도 유사한 짧은 히스토리/합성 통계 문제가 있는지 미검증

---

## 현재 블로커 ❌

> 현재 블로커 없음. Track A/B 완료로 기존 블로커 전부 해소.

| 블로커 | 상태 |
|---|---|
| SCHD vs TIGER 배당 결과 불일치 | ✅ DJUSDIV_PROXY 체인으로 해결 |
| Phase 2c Gate 미통과 | ✅ Gate 2c PASSED (2026-05-28) |
| `_fetch_fred()` 메서드 없음 | ✅ def 선언 추가 (e1a4d6e) |
| 백필 실패 코드가 완료 처리됨 | ✅ _backfill_skip_codes 분리 (a761750) |

---

## 완료된 것 ✅

### 세금 리팩토링
- Phase 1: 공통 세금 코어, 절세매도 12월 분리, 청산세 통일 (Gate 1 ✅)
- Phase 2a: `TaxableSimulationRunner` 구현, 백테스트 전환 (Gate 2a ✅)
- Phase 2b: 투자계산기 + 은퇴 적립 Runner 전환 (Gate 2b ✅)
- Phase 2c: 배당 역산 Runner 구현 완료 (Gate 2c ✅)
- Phase 2d: 은퇴 인출 세금 주입 (Gate 2d ✅ 5/5)
- Phase 2e: 종합과세 경고 + 분할매도 절세 패널 (backtest에 노출) ✅
- Phase 3: ISA 풍차돌리기 Runner 통일 ✅
- 버그픽스: KR_FOREIGN 청산 손익통산 제거 (개별 15.4% 분리과세)
- 버그픽스: US_DIRECT 리밸런싱 손실 손익통산 반영

### 배당금 계산기 버그픽스
- 9.4억 폭증 버그 수정
- 5년 역전 버그 수정 (로지스틱)
- pykrx fallback 제거, yfinance 단일화
- 그래프 개형 볼록 문제 수정
- 역산 탐색 범위 1~70년 확장

### PHASE4 기능
- A1 검색 퍼지/오타 허용
- A2 종목명 우선 표시
- A3 검색 레이아웃 가로형
- A5 검색 탭 분리
- A6 암호화폐 데이터 추가
- B5 리밸런싱 기능 정확도 검증
- C3 시장 지수 클릭→차트
- C5 결과 공유 URL+이미지 (워터마크, OG태그)
- D3 세금설정 UI 개선

---

## 진행 중 / 대기 ⏳

| 트랙 | 내용 | 선행 조건 | 실행 명령어 |
|---|---|---|---|
| **Track A** | ETF 데이터/백필 안정화 | 없음 (지금 시작) | `마스터 로드맵의 Immediate Track A 진행해줘` |
| Track B | Phase 2c Gate 재검증 | Track A 완료 | `Phase 2c Gate 재검증해줘` |
| Track C | 합성 데이터 공통 facade | Track B 완료 | `SYNTHETIC_DATA_INTEGRATION_PLAN Phase 1부터 진행해줘` |
| Track D | 세금 Phase 2d (은퇴 인출 세금) | Track B 완료 | `세금 Phase 2d 진행해줘` |
| Track D | 세금 Phase 2e (종합과세 경고 패널) | Phase 2d 완료 | — |
| Track D | 세금 Phase 3 (정리·ISA Runner 통일) | Phase 2d+e 완료 | — |
| Track E | PHASE4 잔여 기능 | Track A 완료 후 안전한 것부터 | `PHASE4 다음 안전한 항목 진행해줘` |

---

## PHASE4 잔여 기능 체크리스트

**중단기 (세금/데이터 독립적 → 병렬 가능):**
- [ ] D4 거래수수료 설정 (1~2일) — Runner 안정 후
- [ ] D5 인플레이션 검증 + 실질 생활비 표시 (2~3일)
- [ ] A4 종목 상세 개선 + 시간봉 차트 (3~4일)
- [ ] B1 포트폴리오 즐겨찾기/저장 (2~3일)
- [ ] B2 자산 추이 스냅샷 + 홈 토글 (1~2일)
- [ ] B3 리밸런싱 경고 밴드 (1일, B2 선행)
- [ ] C1 홈 화면 watchlist (2~3일)
- [ ] C2 자산군별 수익률 비교 (2~3일)
- [ ] F1 대기 순위 UX 수정 (0.5일)

**복잡한 기능 (순서 중요):**
- [ ] B4 거래 트래킹 + 추가매수 고도화 (3~4일, B2/B3 선행)
- [ ] D1 TDF 기능 (3~4일, Phase 2d 선행)
- [ ] D2 연금 통합 계산기 (4~5일, Phase 2d 선행)
- [ ] D6 합성 데이터 백테스트 체크박스 (1~2일, Track C 선행)

**나중에:**
- [ ] C4 온보딩 튜토리얼 (전체 완료 후)
- [ ] E1 모바일 반응형 (전체 완료 후)
- [ ] E2 코드 최적화 (프로파일링 후)

---

## 사업 일정 대비

| 기간 | 계획 | 현황 |
|---|---|---|
| 2026.06 | 시뮬레이션 엔진 개발 | ⏳ Track A/B 완료해야 |
| 2026.07 | 배당/알림/은퇴/TDF 기능 | ⏳ 대기 |
| 2026.08 | 로그인, 계정, 즐겨찾기 | ⏳ 대기 |
| 2026.09 | iOS/Android 안정화 | ⏳ 대기 |
| 2026.10 | 수익 모델 구현 | ⏳ 대기 |
| 2026.11 | 마케팅 + 앱스토어 배포 | 🎯 목표 |

→ 상세 Phase 기록: [[dev/phases]]
→ 버그 목록: [[dev/bugs]]
→ 아이디어: [[dev/ideas]]
