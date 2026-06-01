# Log

## [2026-06-01] fix | 배포 파이프 버그(BUG-DEPLOY-1) + B2 서버검증

**중대 발견:** 오늘 커밋 전부 서버 미배포 상태였음(로컬 106 테스트는 통과, 코드 정상, 배포만 막힘). B2 서버검증하다 발견.

- **원인:** `data/meta/index_master.db`가 git 추적되는데 서버 런타임이 이 파일에 씀 → `git pull` "local changes would be overwritten"로 abort. `deploy.yml`이 pull 실패 미체크(마지막 `systemctl is-active`만 성공판정) → GitHub Action은 6연속 success인데 코드는 옛날 것.
- **진단:** /api/calculator/run·submit 둘 다 `g2` 필드 없음(B1 이전 코드) → Action success와 모순 → git pull abort 추론(로그 403이라 정황). DB 추적 확인(`git ls-files`).
- **수정 (d581cc3):** ① `git rm --cached data/meta/index_master.db`(런타임 데이터, .gitignore `*.db`로 자동 무시). ② `deploy.yml`: `set -e`(pull 실패 시 Action 실패 가시화) + pull 전 `git checkout -- data/meta/index_master.db`(서버 dirty DB 1회 폐기→이후 untracked 영구 해소).
- **검증:** 배포 d581cc36 success → `/api/calculator/submit` G2 body(ISA풍차+위탁, 458730 실데이터) → `g2.enabled=true` + `transfer_log` 실제 만기이벤트(목돈 12,406,850·만기세 44,703·재가입 라우팅). **B2 end-to-end PASS.**
- ⚠️ 부수효과: 서버 index_master.db 1회 레포버전 복귀(ECOS 재수집 루틴). [[feedback-deploy-verify-workflow]]에 서버 https URL 메모 추가.

_작성: Claude (Opus 4.8)_

---

## [2026-06-01] fix | Track G B1 후속 — 순수 연금/IRP 연납입공제 정리

B1 한계(정책 없는 순수 연금/IRP에 연납입공제 미적용) 해소.

- **원인:** G4 공제 로직이 transfers 경로(`_compute_injections`)에만 존재. `transfers_enabled` = 정책 OR 풍차라 순수 연금/IRP는 transfers OFF → 공제 미산출.
- **수정** (`calculator_logic.py`): `transfers_enabled`에 `(tax_enabled AND 연금/IRP 존재)` 추가.
- **안전성 증명:** `test_l9_pension_transfers_equivalence` — 한도 내 연금/IRP는 transfers ON/OFF **종료값 동일**(공제는 별도 보고, reinvest OFF면 포트폴리오 미주입). 즉 순수 연금/IRP에 transfers 켜도 종료값 불변·공제만 추가. ISA 공존 시 ISA도 transfers 경로(연 2천만 한도 엔진 동적처리 — 한도 내 무차이, 초과 시 더 정확).
- 검증: Track G 36/36 + 전체 스위트 PASS.

_작성: Claude (Opus 4.8)_

---

## [2026-06-01] feat | Track G B1 — analyzer/logic 배선 (G2 엔진 → logic 관통, L9)

플랜 §B(배선&UI) 중 B1. 엔진 계층(L0~L8) 완료됐으나 analyzer/calculator_logic이 G2 기능을 안 넘기던 갭 해소.

### 배선
- **`multi_account_analyzer.py`**: `__init__`에 `manual_comprehensive_years`·`reinvest_tax_credit` 추가. `loop_accounts`에 계좌별 `isa_renewal` 포함. `.run()` 호출에 신규 파라미터 전달. 윈도우별 결과(`transfer_log`·`comprehensive_years`·`annual_deduction_credit`·`pension_transfer_credit`) metrics에 surfacing.
- **`calculator_logic.py`**: `_normalize_multi_accounts`가 `isa_renewal` 독해. body→`DistributionPolicy.from_dict`·`manual_comprehensive_years`·`reinvest_tax_credit` 파싱. `transfers_enabled` = 정책 有 OR 임의 풍차. **풍차 거부 블록 제거**(이제 G2 지원). **transfers ON시 정적 ISA cap(contribution_end_months) 스킵**(엔진 tracker가 동적 처리, 충돌 방지). analyzer에 전달. 응답: cases별 G2 필드 + top-level `g2`(대표 중앙값 케이스).

### 검증 (L9 4종, Track G 35/35)
- analyzer 만기 surfacing(L5 재현: ISA2천만/위탁2천만)·G4공제+금종세 surfacing(297만·2020 포함)·G1 회귀(정책無→transfer_log 비어있음·합산 정확)·정규화 isa_renewal 독해.
- 회귀: 전체 스위트 PASS.

### ⚠️ 한계 (다음 검토)
- `transfers_enabled` = 정책 OR 풍차만. **정책 없는 순수 연금/IRP 계좌는 연납입공제 미적용**(연납입공제가 transfers 경로에만 있음). 분배정책 추가하면 작동. 순수 연금/IRP에도 공제 주려면 결정 필요.

### 남은 것
- B2 API surfacing(서버 검증) → B3 프론트 UI(분배정책 에디터·풍차토글·금종세입력·재투자토글, 검증 약함). L7 실데이터 통합.

_작성: Claude (Opus 4.8)_

---

## [2026-06-01] feat | Track G4 연 납입 세액공제 (L8) + 죽은 v1 삭제

플랜 §G4 신규 설계·구현·검증. 매년 연금/IRP 납입 세액공제 환급을 통합 루프에 배선.

### 사전 정리
- **죽은 코드 삭제** `modules/tax/multi_account.py`(`MultiAccountSimulator`) — §결정1이 폐기한 v1(계좌 독립시뮬 후 합산). 호출처 0개. 계산식·재투자 패턴만 통합 루프로 이식. (⚠️ README:990 `_init_worker` 언급 stale, 코드 무관)

### 구현 (`multi_account_loop.py`)
- **공제 계산** = 기존 `TaxEngine.annual_tax_deduction`(min(합산,900만)×16.5/13.2%, 이미 tax_truth 검증) 재사용. 통합 루프에 호출 배선만.
- **base 집계** `_track_pension_contrib` — 연금/IRP **external 납입**(직접 월납입 + 2-1 ISA초과 라우팅)을 연도별 분리집계. ISA 만기 전환분(internal)·환급 재투입분 제외(G3 대상·이중공제/재귀 방지).
- **연 경계 정산** — `_compute_injections`서 연도 바뀌면 직전 해 `annual_tax_deduction` 계산→누계. 마지막 해는 finalize서 보고만.
- **재투자 통합** `_apply_credit_reinvest` — G3 이전공제 환급 + G4 연납입공제 환급 **공통 토글**(`reinvest_tax_credit`, run 레벨). 재투자 ON이면 **분배 정책 cascade로 재투입**(오너 결정: 별도 목적지 안 만들고 기존 우선순위 따라감, `route_overflow` 정상 한도). 직전 해분만 재투입(현실: 익년 정산), 마지막 해 보고만.
- **G3 재투자 통일** — 기존 "연금 자기자신 재투입" → 정책 cascade로 변경(L6 재투자도 갱신, 결과 동일).
- 결과 노출: `annual_deduction_credit`·`pension_transfer_credit_total`.

### 오너 결정 (2026-06-01)
- G3 전환공제(300만)·연납입공제(900만) **별도 한도**(같은 해 둘 다, 최대 1200만). 재투자 목적지=분배 정책 따라감. 재투자 토글 통합 1개.

### 검증 (`tests/test_track_g_multi_account.py` L8 5종, Track G 31/31)
- 정상(연금600+IRP300 저소득→148.5만/년)·연금단독 600만cap+고소득13.2%(79.2만)·합산 900만cap·0납입(공제0)·**재투자(정책 cascade, 직전해만 재투입 위탁 종료 148.5만, 마지막해 보고만)**.
- 회귀: 전체 스위트 PASS(L0~L6/L5c 불변).

### 남은 것
- B단계: `calculator_logic.py` 배선(accounts+정책+isa_renewal+manual_comprehensive_years+reinvest 수신) + 풀커스텀 분배정책 프론트 UI. (UI는 검증 약함)
- L7 실데이터 통합(불변식만).

_작성: Claude (Opus 4.8)_

---

## [2026-06-01] feat | Track G2 2-4 금종세 ISA 풍차중단 (L5c) + 공유세션 멀티배선

플랜 `§2-4` 구현·검증. ISA 풍차(2-2)의 "중단" 분기. 오너 결정(2026-06-01): 판정=자동(라이브)+수동 오버라이드 둘 다 / 과세단위=개인.

### 구현
- **공유세션 멀티배선** (`multi_account_loop.py`): `run`에서 `TaxSessionState` 1개 생성→전 계좌 `_build_runtime(tax_session=)`로 div_engine·executor에 주입. **전 위탁계좌 금융소득(배당 gross + KR_FOREIGN 실현차익)을 한 풀로 집계**(개인 과세단위, ISA/연금 제외). 기존 단일계좌 Phase 2f 세션 패턴을 멀티로 확장.
- **`_isa_renewal_eligible(date)`**: 직전 3개 과세기간(year-1·-2·-3) 중 1회라도 종합과세 대상(>2천만)이면 풍차 자격 False. 종합과세 연도 = 라이브 세션 집계 ∪ `manual_comprehensive_years`(수동 오버라이드). 만기일에 `session.touch`로 직전연도 flush 후 판정.
- **만기 블록 게이트**: `idx%36==0 and _isa_renewal_eligible(date)` → 비대상이면 만기 청산·재가입 **스킵**(기존 ISA 무한유지, 리셋 없음). 1억 한도는 리셋 안 되니 자연히 차고→2-1 리라우팅(기존 로직). **3년 롤링 재평가**라 대상연도가 창 밖으로 밀리면 풍차 자동 재개(별도 카운터 불필요).
- **결과 노출**: `MultiAccountRunResult.financial_income_by_year`/`comprehensive_years` 추가(라이브∪수동). calculator_logic·검증용.
- `run(manual_comprehensive_years=)` 파라미터 추가.

### 검증 (`tests/test_track_g_multi_account.py` L5c 4종, Track G 26/26)
- **정상(중단→재개)**: 수동 {2022}→2023 만기 정지·2026 만기 재개(롤링). 만기 1회(L5b는 2회), 종료 ISA 4천만/위탁 1.2억.
- **경계 무한유지**: 수동 {2022,2025}→만기 0회, ISA 9년 통째 보유 1.6억, cycle_contribution 2천만(리셋無)≤1억.
- **1억 리라우팅**: 정지+월납입→ISA 5년 1억 도달→초과 위탁(ISA 1억/위탁 2.6억). 무한유지 중 한도참 리라우팅 확인.
- **세금ON 라이브**: 위탁 배당 gross 3천만(2022)→공유세션 2022 종합과세 판정→2023 풍차 정지. `comprehensive_years`에 2022 포함(멀티배선 입증).
- 회귀: 공유세션 도입 후 Track G 26/26 + 전체 스위트 PASS(L0~L6 불변).

### 남은 것
- 연납입 세액공제(연금600+IRP300=900만) — G3 이전공제와 별개 큰 기능.
- `calculator_logic.py` 배선(accounts+정책+isa_renewal+manual_comprehensive_years 수신) + 풀커스텀 분배정책 프론트 UI.

_작성: Claude (Opus 4.8)_

---

## [2026-06-01] feat | Track G2 2-2 만기분배 + G3 연금이전 세액공제 (L5/L5b/L6)

플랜 `trackG_multiaccount_plan.md §2-2`(풍차 만기 목돈 분배) + `§G3`(ISA→연금 이전 공제) 구현·검증. 오너 결정: 분배정책=우선순위 리스트(옵션3, ISA도 목적지), 재가입 상한 2천만 연한도 고정, G3 이전공제 동봉(연납입 900만 세액공제·2-4 금종세는 다음).

### 구현 (`modules/simulation/multi_account_loop.py`)
- **`_mature_isa`** — 3년(36개월)마다 ISA 풍차 만기: 청산→만기세(`after_tax_withdrawal`, 원가=**사이클 납입액**)→포지션·평균단가·tracker(연/총/policy_routed) 리셋→세후 목돈 반환.
- **`_compute_injections` 확장** — 월경계에서 만기(2-2) 선처리 후 월납입(2-1). **외부/내부 자금 분리:** 월납입=external(cash_flow 기록), 만기목돈 재배분=internal(cash_flow 0) → 자금보존 불변식 보존. 반환 `(external, internal)`.
- **`_step_account(transfer_override=)`** — 내부이동분은 현금 추가하되 cash_flow 미기록.
- **사이클 원가추적** `cycle_contribution` — 만기세·최종청산·≤1억 사이클 불변식 기준. 풍차 ISA는 평생납입 1억 초과 가능하므로 불변식을 사이클 기준으로 변경.
- **G3** `_accrue_pension_credit` — ISA→연금/IRP 이전 시 공제 `min(이전액×10%, 연 300만)`. 재투자 옵션(`reinvest_tax_credit`)이면 환급금을 연금에 외부 재투입.
- **`route_overflow(pension_unlimited=)`** (`account_tax.py`) — 만기 전환 시 연금/IRP는 **1800만 납입한도와 별도**(전액 전환 가능, 한국 실제 규칙), capacity=무제한·납입풀 미기록. 월 라우팅(2-1)은 기존대로 1800만 cap. → 오너 "연금 우선이면 전액 연금이전"과 일치.
- finalize: `maturity_tax_paid`·`cycle_contribution`·`pension_transfer_credit` 노출, tax_paid에 만기세 포함.

### 검증 (`tests/test_track_g_multi_account.py` 22/22)
- **L5(2-2)**: 정상경로(만기 4천만→재가입2천만+위탁2천만)·경계<2천만(전액ISA)·경계>1억(연한도캡)·세금ON(만기세 277.2만). remainder(4년 1부분사이클)=L5 정상경로가 겸함.
- **L5b**: 9년 3사이클(만기 2회·재가입·비과세리셋·위탁누적 1.2억)·세금ON(사이클별 청산세 178.2만 누적).
- **L6(G3)**: 정상(이전 1800만→공제180만+위탁cascade)·경계+세금ON(전액이전→300만 상한적중)·재투자(공제 300만 연금 재투입→종료값+300만).
- 회귀: **전체 스위트 92/92 PASS**(tax_truth·Gate·phase2f·cagr·portfolio_accounting 포함). G1/2-1 L0~L4 100% 불변.

### BUG-TAX-1 폐기
- 오너 확인: ISA 서민형 비과세 미구현 = 버그 아님. `isa_type="preferential"`이 정상 코드값(base_tax.py:345 → 400만 비과세 정상). bugs.md 항목 삭제.

### 미구현(다음)
- **2-4 금종세 풍차중단(L5c)** — `comprehensive_years` 입력→대상연도 풍차정지·기존ISA 무한유지. 공유세션 멀티배선 선행.
- **연납입 세액공제(900만, 13.2~16.5%)** — 매년 연금/IRP 납입 환급(G3 이전공제와 별개, 범위 큼).
- `calculator_logic.py` 배선(만기/정책 수신) + 풀커스텀 분배정책 프론트 UI.

_작성: Claude (Opus 4.8)_

---

## [2026-06-01] test | Track G2 L시리즈 검증 엄밀화 — assert_invariants + L4 구멍 메꿈 + L0~L3 보강

오너 지시(검증 빈틈 없이) 수행. 코드 1줄(cap 의미 명확화) 외 전부 테스트.

### 1. `assert_invariants` 공통 헬퍼 신설
- 음수잔액0 + ISA납입≤1억 + (옵션) 자금보존(Σ납입=실투입) + (flat_price) Σraw_end=Σ납입.
- L0(tax)·L2·L4 전 케이스에 적용.

### 2. L4 구멍 4개 메꿈 (신규 테스트 4)
- `test_l4_policy_cap_caps_destination` — 정책 `cap`(전기간 누적 상한) 적중→cascade. ISA20/연금10/위탁30.
- `test_l4_leftover_when_policy_cannot_absorb` — 무제한 목적지 없으면 leftover 누적(22M), 계좌합<실투입.
- `test_l4_pension_irp_share_annual_limit` — 연금+IRP 합산 1800만 풀 공유(연금18/IRP0/위탁22).
- `test_l4_tax_on_routing_liquidation` — 세금ON 라우팅. ISA고정(청산세0)+위탁 수신분 458730 2배→KR_FOREIGN 15.4% 청산세 61.6만 정확.

### 3. 코드 수정 (account_tax.py)
- `route_overflow`의 `dest.cap`을 **월별→전기간 누적 상한**으로 변경(`tracker._policy_routed` 추가). 기존 테스트는 cap=inf라 무영향, 신규 cap 테스트 위해 의미 확정.

### 4. L0~L3 보강
- `test_l0..._tax_on` 신규(세금ON 골든: 멀티루프 청산세 = Runner ±1원).
- L1에 시나리오 합산 어서트 추가, L2에 invariants, L3에 비과세한도 경계(순이익=200만 정확→세금0).

### 5. 플랜 갱신(전 세션) 반영 확인 — L5/L5b/L5c(2-4 신규)/L6 검증항목 정의됨.

### 검증
- `tests/test_track_g_multi_account.py` **13/13**(L0×2·L1·L2·L3·L4×8). 회귀 phase2f·Gate·cagr·tax_truth 포함 **40/40**.

### BUG-TAX-1 = 오진(버그 아님, 정정)
- 처음 L3 서민형 케이스를 `isa_type="low_income"`(미인식 값)으로 작성 → general fallback(792,000원) → "서민형 미구현"으로 오판.
- 실제 서민형 코드값은 `"preferential"`(base_tax.py:345). 그 값 쓰면 594,000원 정상. 코드 무수정. L3 케이스를 `"preferential"`로 교정.

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] feature | Track G2 토대 — transfer 엔진 + ISA 월 한도초과 라우팅(2-1)

플랜 `trackG_multiaccount_plan.md §2-1` 구현. G1 통합루프에 `transfers_enabled=True` 경로 신설. **범위 한정:** 월 한도초과 라우팅 + L0~L4 검증까지. 만기분배(2-2)·풍차중단(2-4)·G3·공유세션 멀티배선·프론트 UI = 다음 세션.

### 구현
- **`modules/tax/account_tax.py`** (append):
  - `ContributionLimitTracker` — 동적(상태추적) 납입 한도. ISA 연 2천만 AND 총 1억(둘 중 작은 잔여), 연금+IRP 합산 연 1800만, 위탁 ∞. `touch`(연 리셋)/`capacity`/`record`. 기존 정적 `check_contribution_limits`는 경고만 내서 라우팅에 부적합 → 동적판 신규.
  - `DistributionPolicy`/`DistributionDestination` + `from_dict` — 우선순위 순 목적지 목록(+정책 상한).
  - `route_overflow(amount, policy, tracker, types)` — 초과분을 정책 순서대로 capacity까지 cascade 배분, `(allocations, leftover)` 반환.
- **`modules/simulation/multi_account_loop.py`**:
  - `run(..., distribution_policy=None)` 추가. `transfers_enabled=False` 경로는 100% 불변(G1 회귀 보존).
  - 월 경계 1회 `_compute_injections` — ISA 흡수(한도까지)+초과분 라우팅 계산. `_step_account(contribution_override=)` 로 실제 납입액 주입(월 게이팅은 루프가 책임, ContributionEngine 우회).
  - `_ensure_sync_accounts` — 정책 목적지가 없는 계좌 가리키면 **위탁 자동 싱크**(첫 ISA 종목·비중 미러) 생성. (오너 결정)
  - `MultiAccountRunResult.transfer_log` 추가.
- **`modules/retirement/multi_account_analyzer.py`**: `transfers_enabled`/`distribution_policy` 패스스루.

### 오너 결정 (2026-05-31)
- 종합과세 판정 = **개인** 기준 / 분배정책 UI = **풀 커스텀**(다음 세션) / 행선지 부재 = **위탁 자동싱크** / 위탁 배분 = **ISA 원계좌 미러** / ISA 한도 = **연 2천만 + 총 1억 둘 다**.

### 검증 (결정론적 픽스처, 손계산)
- `tests/test_track_g_multi_account.py` **8/8** (기존 L0~L3 4개 + 신규 L4 4개):
  - L4 cascade: ISA 월500만/1년 → ISA 20M(연한도)·연금 18M·위탁 22M·합산 60M, 자금보존, transfer_log 8회/초과 40M.
  - 연한도 연 리셋(2년→ISA 40M)·총한도 1억 캡(6년 누적→ISA 100M·위탁 260M)·위탁 자동싱크 생성.
- 회귀: tax_truth·Gate 2a/2b/2c·phase2f·cagr 포함 **37/37**. G1 L0~L3 불변.

### 다음 세션
- 2-2 만기 목돈분배 + 2-4 풍차중단(금종세자, 공유세션 멀티배선 선행) + G3 연금이전공제 + `calculator_logic` 수신 + 풀 커스텀 분배정책 프론트 UI.

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] feature | 투자계산기 전체 롤링 케이스 가격 출처 표시

- 커밋: `afd37b4 feat(calc): show rolling price provenance`
- 배경: 배당 히스토그램에는 실측/백필 시작점이 보였지만, 결과창 우측 상단의 `N년 | M개 롤링 케이스`가 가격 데이터 기준으로 몇 케이스가 실측이고 몇 케이스가 지수 기반 프록시/백필인지 설명하지 못했다.
- 구현:
  - `calculator_logic.py`
    - `price_provenance` 응답 필드 추가.
    - 단일 계좌/다중 계좌 모두 동일하게 포함.
    - 케이스 분류 기준: 모든 종목의 `volume > 0` 실측 가격 시작일 중 가장 늦은 날짜 이후에 시작하는 롤링 케이스만 `actual_cases`; 그 이전부터 시작하는 케이스는 `backfilled_cases`.
    - 종목별 `data_start`, `real_start`, `proxy`, `sources` 제공.
  - `templates/calculator.html`
    - 결과 헤더 아래 `priceProvenanceNote` 영역 추가.
  - `static/js/calculator.js`
    - `renderPriceProvenance()` 추가.
    - 예: `가격 데이터: 실측 0개 / 프록시·백필 221개 (총 221개 롤링 케이스)`.
    - 펼치면 종목별 실측 시작일과 백필 프록시/구간/행 수 표시.
  - `static/css/calculator.css`
    - 결과 헤더용 작은 provenance 안내 스타일 추가.
- 로컬 검증:
  - `python -m py_compile calculator_logic.py` PASS
  - `node --check static/js/calculator.js` PASS
  - `458730`, 7년, 10억원, 월적립 0원 샘플: `cases=221`, `actual_cases=0`, `backfilled_cases=221`, `proxy=DJUSDIV_PROXY`, `real_start=2023-06-20`
  - `360750`, 7년 샘플: `cases=221`, `actual_cases=0`, `backfilled_cases=221`, `proxy=^GSPC`, `real_start=2020-08-07`
  - `SCHD`, 7년 샘플: `actual_cases=31`, `backfilled_cases=190`, `proxy=DJUSDIV_PROXY`
  - `SPY`, 7년 샘플: `actual_cases=106`, `backfilled_cases=115`
- 주의:
  - 이 기능은 수익률 계산 로직을 바꾸지 않고, 결과의 데이터 출처 투명성만 추가한다.
  - 프론트 캐시 무효화를 위해 `calculator.js?v=20260531b`로 변경했다.

_작성: Codex_

---

## [2026-05-31] feature | Phase 2f 완성 — 중간실현 합산 + 자동산출 + 분할매도 슬라이더 전탭 배선

2f 핵심(청산 합산) 이후 오너 지시로 남은 3개 완료.

### 1. 중간 실현 KR_FOREIGN 합산 (공유 세션)
- **`TaxSessionState` 확장:** `ytd_financial_income`(배당+KR_FOREIGN 실현차익+외부) 단일 풀 + `ytd_us_realized_gains` 분리 + 연도별 트래킹 + `touch/add_financial_income/add_us_gain/finalize`.
- **`TaxedDividendEngine`·`TaxedOrderExecutor`가 공유 세션 사용**(`session=` 인자). 배당과 리밸/절세매도 KR_FOREIGN 실현차익이 **같은 풀**로 합산돼 종합과세. 세션 없으면 기존 동작(multi_account 등 backward compat).
- `order_executor._calc_cg_tax` KR_FOREIGN: 세션 있으면 그 해 ytd와 합산 종합과세, 풀에 가산. US는 세션 us_gains.
- `taxable_runner`: 단일 세션 생성→두 엔진 주입, 청산/트래킹 세션 사용.

### 2. other_financial_income 자동산출
- `split_sale_planner.recurring_financial_income(financial_income_by_year)` — 청산연도 제외 직전 완료년도 금융소득을 패널 baseline으로 자동 사용(수동입력 대체).

### 3. 분할매도 슬라이더 전탭 배선
- **backtest:** 자동산출 적용 + 패널 텍스트 정정(end_value가 일괄 종합과세 반영). `comprehensive_years`/`financial_income_by_year` API 노출.
- **calculator:** `AccumulationAnalyzer`가 case별 kr_foreign_gain/financial_income/comprehensive 수집 → `calculator_logic`이 중앙값 기준 `split_sale_plan` 빌드 → `calculator.html`+`calculator.js` 슬라이더 패널.
- **retirement:** 동일(적립 종료 기준 중앙값) → `retirement.html` 슬라이더 패널.
- 배당금 계산기: 별도 엔진(DividendSimulator)·최하위 우선순위 → 제외(노트).

### 검증
- `test_phase2f_comprehensive` **7/7**(중간실현 합산 + 무세션 flat 회귀 추가). tax_truth 64/64, Gate 2a/2b/2c 각 4/4.
- 프론트 패널은 서버 배포 후 브라우저 스모크 권장(백엔드 split_sale_plan 응답은 검증).

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] feature | Phase 2f 핵심 구현 — 청산 시세차익+배당 합산 종합과세 + 트래킹

오너 핵심 갭(청산 KR_FOREIGN을 그 해 배당과 합산 종합과세) 구현. 순서 = 2f 먼저 → G2 나중(플랜 명시).

### 구현 (단일계좌, transfer 불필요분)
- **`liquidation.py`:** KR_FOREIGN 청산이익 flat 15.4% → **그 해 금융소득(ytd_financial_income)과 합산 종합과세.** 2천만 이하 15.4% 분리, 초과분 종합과세(배당과 동일 `_comprehensive_extra_tax` 재사용). 오너 1.3억 케이스 동작.
- **`account_tax.py` TaxedDividendEngine:** `other_financial_income` 인자 추가 → `_ytd_income` 매년 외부 금융소득부터 시작(현 0 고정 해소). 연도별 금융소득 트래킹(`financial_income_by_year`) + `finalize_year_tracking`(마지막 연도에 청산차익 가산).
- **`taxable_runner.py`:** user_settings에서 other_financial_income 주입, 청산에 ytd_financial_income 전달, 연도별 종합과세 대상(`comprehensive_years`) 산출 → `RunResult`에 추가.
- US_DIRECT 양도차익은 22% 별도 유지(미합산, Q2 결정대로).

### 검증
- **신규 `test_phase2f_comprehensive.py` 5/5 PASS:** ① 청산 1억+배당 3천=1.3억 합산 종합과세(=`_year_tax` 일치) ② ytd0 단독 ③ 소액(1천만) flat 15.4% 회귀 ④ `_ytd_income` 주입 ⑤ 연도별 트래킹+대상 flag.
- **회귀 무손상:** tax_truth 64/64, Gate 2a/2b/2c/phase1 각 4/4 PASS.

### 남은 것 (후속 보고)
- ❌ 중간 실현 KR_FOREIGN(리밸/절세매도, `order_executor._calc_cg_tax`)은 아직 flat 15.4% — 배당풀 미합산(매수후보유 배당ETF는 드묾).
- ❌ `other_financial_income` 자동산출(직전 완료년도 sim 배당) — 현재 user_settings 주입값 사용.
- ❌ 분할매도 슬라이더 패널 전탭 배선(계산기/배당/연금) + `comprehensive_years` UI/API 노출.

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] plan | 금융소득 종합과세 상세 설계 (오너 디테일 결정 → Phase 2f + Track G 2-4)

오너와 디테일 확정 후 플랜 구체화. 코드 실상 확인 = 매년 배당 종합과세는 작동(단 _ytd_income 0 시작), **청산/실현 시세차익이 그 해 배당과 합산 안 됨(15.4% 분리)이 핵심 갭.**

### 오너 결정 (4)
- **소득 범위:** 금융소득 = 이자 + 전 배당 + KR_FOREIGN 시세차익(세법상 배당소득). US 양도차익 22% 별도(미합산). ISA/연금 제외.
- **end_value/패널:** 헤드라인 = 일괄청산 종합과세 기준(그 해 실현 배당+차익 합산). 결과에 분할매도 슬라이더(현 백테스트 방식)→일괄/절세/세후순이익, 소득구간별(2천만↓/매년2천만↑/최고세율↑) 절세효과 0~중간~0 상세 표시.
- **ISA 가입불가 처리:** 금종세 대상자=ISA 신규/만기연장만 차단, 기존 ISA 강제해지 아님. **풍차의 진실=만기 아니라 의무가입기간 3년.** 대상자 되면 풍차(해지·재가입) 멈추고 만기∞ 무한유지, 1억 한도 채우면 추가납입 중단→리라우팅. 해지 시 전액연금이전/9.9%/서민형 400만 비과세 유지.
- **재분배/재가입:** 막힌 납입금 = 연금한도 우선→위탁. 3년 연속 비대상→ISA 재가입(풍차 재개) 동적 허용.

### 플랜 반영
- **세금 plan `#### Phase 2f` 신규:** 종합과세 정확도(실현차익+배당 합산·매년) + `_ytd_income` 주입 + other_financial_income 자동산출 + 분할매도 전탭 배선 + **연도별 종합과세 대상 트래킹**. frontmatter todo + 다음 액션 갱신.
- **trackG plan `§ 2-4` 신규:** 금종세자 ISA 풍차 중단·무한유지 알고리즘 + 계좌간 금융소득 집계 + 동적 재가입. (ISA 한도 리라우팅은 기존 G2 설계됨·미구현 확인.)

### 다음 = 구현 (오너 지시 대기)
구현 순서: 선행 gross/net 확인 → ① 실현차익 ytd 합산 종합과세 → ② `_ytd_income` 주입 → ③ 자동산출 → ④ 전탭 배선 → ⑤ 트래킹 → (Track G) 풍차 중단·리라우팅. 검증=소득구간 3종+1.3억 합산+경계+회귀.

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] docs | 계획파일 전체 동기화 + 다음 작업 확정(금융소득 종합과세)

배당 백필 Stage A/B 완료·세금 2c 재검증 완료를 전 계획파일에 반영. 다음 작업 = 금융소득 종합과세 완전 구현으로 확정.

### 갱신한 계획파일
- **ETF_BACKFILL_ARCHITECTURE_PLAN.md:** Phase 7에 Stage B 완료 addendum(한국 채권 전유형·환헤지비용·US 키워드 자동분류·통화가드·서버검증). Stage B 헤더 ✅.
- **PROJECT_MASTER_ROADMAP.md:** 헤더·현재위치·블로커·다음액션·플랜인덱스 표 갱신. 블로커=없음, 다음=금융소득 종합과세.
- **세금에서시작된완전리팩토링계획.plan.md:** "다음 액션" = 금융소득 종합과세(Phase 2e 배선 + phase1-api). 갭 3종 + 선행확인(gross/net) 명시.
- **wiki status.md:** 진행중 표 갱신(Stage B ✅, 종합과세 = 다음), 한 줄 요약 업데이트 12.

### 다음 작업 = 금융소득 종합과세 완전 구현 (확정)
- 문제(오너): 올해 금융소득(이자·배당) 2천만 초과해도 15.4%(미국 15%)만 떼고 종합소득 누진 집계 안 됨.
- 실상: 종합과세 **엔진 수학은 완료**(`base_tax._comprehensive_tax`/`after_tax_dividend`/`_comprehensive_extra_tax`, 2천만 임계, `tax_truth_test` 통과). 갭은 **배선·데이터:**
  - ① `other_financial_income` 자동산출 미구현 — `backtest_logic.py:117` 수동값/0 fallback(plan 금지). case별 직전 완료년도 gross 배당·이자 집계 필요.
  - ② 분할매도/종합과세 패널 백테스트 탭에만 배선 — 계산기/배당/연금 `*_logic.py` 미배선.
  - ③ `TaxedDividendEngine._ytd_income` 0 고정(`account_tax.py:230`) — 기존 금융소득 미주입.
  - + KR_FOREIGN 청산이익은 설계상 15.4% 기준선 유지, 종합과세는 분할매도 패널로 안내(end_value 불변).
- 선행: 히스토리/breakdown `dividend_income` gross/net 여부 먼저 확인.

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] feature | US 채권 ETF 자동백필(키워드 분류기) + 회사채 DBAA + 통화 가드

수동 dict(TLT 등 10종)로만 되던 US 채권 백필을 **영문명 키워드 분류기로 자동화**. + 비USD/KRW 통화 노출 채권 안전차단.

### 한 일
1. **US 채권 키워드 분류기** `bond_model.classify_us_bond_etf(name)` — 결정론(LLM 아님). 국채 만기버킷(20+/10-20/7-10/3-7/1-3 → DGS30/DGS10dur9/7.5/4.5/DGS3MO), 회사채 IG(DBAA, 만기별 dur 2.7/6/8/13), 광범위본드(DGS10 만기별). 모델불가 유형(HY/TIPS/Muni/MBS/CLO/International/EM/Preferred/Convertible) = None **안전스킵**.
2. **`bond_config` 확장 + 게이트:** `us_category=="US Fixed Income"`일 때만 이름분류 → 주식 ETF명 오탐 방지('Credit Suisse' 등). 우선순위 코드dict > KR카테고리 > US이름분류.
3. **회사채 yield 소스 DBAA(Moody's Baa, 1986~ 10137행) 수집** `scripts/fetch_us_credit_rates.py`. ICE BofA(BAML)는 FRED 라이선스로 최근3년만 → 백필 불가하여 DBAA 채택. **HY는 장기 무료 yield 없어 미수집→안전스킵**(Grade D 스프레드 프록시는 후속 옵션).
4. **통화 가드** `unsupported_currency(name)` — 엔화/JPY/유로/위안/파운드 마커 → 채권백필 거부. backfill_engine에 `is_bond and unsupported_currency(name)` 차단 추가. **라벨이 'US Treasury'로 맞아도 차단**(엔진이 USD/KRW만 모델링하는 한계 방어).

### 검증 (철저)
- **분류기 유닛 34/34 PASS** (`test_us_bond_classifier.py`): 만기/유형별 기대값 + 스킵 + 통화가드.
- **커버리지:** US Fixed Income 561종 → **300 분류 / 261 안전스킵**(스킵=HY/TIPS/Muni/MBS/International 등 모델불가, 정확).
- **통화가드 실효:** KR 채권류 중 **3종 차단** — `RISE/ACE 미국30년국채엔화노출(H)`, `PLUS 일본엔화초단기국채`. ★유저 우려 케이스(엔화→USD 둔갑) 차단 확인. 주식 엔화ETF는 is_bond=False라 미적용.
- **실데이터 end-to-end** (`verify_us_bond_auto.py`, yfinance 총수익 vs 모델): 양호 ≤0.7p = LQD 0.69/VCIT 0.12/VCLT 0.51/TLH 0.54/IEI 0.36/SHY 0.55/BND 0.58/BSV 0.00 (월상관 0.81~0.97). **약점(Grade C):** VCSH 단기회사채 1.56p(DBAA 장기yield carry 과대), BLV 장기광범위 2.09p(국채 carry 과소) — 단일yield 프록시 만기극단 한계, 오버핏 회피해 수용.
- 회귀: 기존 TLT(hand)/KR 카테고리/주식→None 경로 불변 확인.

### 서버 적용 주의
- **서버 index_master에 DBAA 필요** → 배포 후 서버에서 `fetch_us_credit_rates.py` 실행해야 US 회사채 백필 작동(db는 미커밋, Celery 충돌 방지).

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] fix | Stage B 헤지비용 모델 + 회사채 듀레이션 하향 + KR금리 복구

핸드오프 2문제 구현. **서버 검증 대기**(KR 채권 ETF 실가격은 로컬 없음, Hetzner에 있음).

### 한 일
1. **헤지비용 모델 (문제1):** `bond_model.build_bond_price_series`에 `hedge_cost_pct` 인자 추가 — `daily_ret − (DGS3MO−CD91)/100/252`. `backfill_engine.backfill`에서 `hedge=="hedge"` ETF에 DGS3MO/CD91 차를 그날그날 계산해 전달. covered interest parity.
2. **회사채 듀레이션 2.6→2.0 (문제2):** `_BOND_CATEGORY_CONFIG["KR_CORPORATE"]`. 만기형 실측 0.7~1.0 반영, CAGR차 축소 목적.
3. **부수발견·복구:** KR금리(KTB*/CD91/CORPAA3Y/KOFR)가 index_master에서 **전부 소실**(핸드오프는 "보존"이라 했으나 실제 0행). `scripts/fetch_kr_rates.py` ECOS 재수집으로 복구(CD91 7975행 1995~, CORPAA3Y 7975행 등 10종).

### 핵심 통찰 — 헤지비용 부호 시대별 자동전환 (오너 우려 "금리역전 시 깨지나?" 해소)
그날그날 역사적 금리 사용 → 부호 자동. 검증(로컬 DGS30 sanity):
| 기간 | 헤지비용(연율) | 효과 |
|---|---|---|
| 2023~2025 (ETF 실거래) | +1.5~1.6% | CAGR 차감 → 과대 수정 (핸드오프 방향 일치) |
| 1995~2020 (백필 과거, 한국금리>미국) | 평균 −2.2% | 헤지 프리미엄 가산 (시대 정확) |
- 6181/7975일이 역전(US<KR) — 코드가 부호로 자동 처리. 금리역전돼도 안 깨짐.

### 한계 (Grade C)
핸드오프 갭 2.5%p 중 **금리차로 ~1.5%p 설명**. 나머지 ~1%p = FX 베이시스(선물환 수급 프리미엄, 단기금리차로 미포착). 2.5p→~1p 개선 예상. 수용 범위.

### 검증 상태 — ✅ 서버 검증 완료 (f175b8a 배포, stage_b_verify_kr.py 모델에 헤지비용 반영)
- **헤지 ETF CAGR차: 2.5p → 1.0~1.5p ✅** (453850=1.23p / 484790=1.03p / 458250스트립=1.46p / 267490레버=0.43p). 금리차 ~1.5p 메움, 잔여 ~1p=FX베이시스(Grade C). 월상관 0.93~0.97 유지.
- **회사채(dur 2.0): 갭 1.0~1.6p** (438330=1.03 / 473290=1.05 / 0016X0=1.63). 듀레이션 하향은 갭에 거의 무영향 — 갭 주원인은 carry(CORPAA3Y yield) 드리프트(model<actual). dur는 요청대로 적용. Grade C 유지.
- **회귀 없음:** 국채 0.13~0.88p / 종합채권 0.45~0.52p / 스트립 0.25p / MMF 0.13~0.57p — 핸드오프와 동일.
- 서버 services(domino/celery/beat) 전부 active. 서버 index_master KR금리 정상(소실은 로컬만).

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] verify+handoff | Stage B 한국 채권 종합검증 완료 + 다음 세션 핸드오프 (헤지비용·회사채)

**다음 세션 시작점 — 검증이 잡은 2문제 해결.** 아래 그대로 이어받으면 됨.

### 종합 검증 결과 (`scripts/stage_b_verify_kr.py`, 카테고리당 2~3종, C 총수익보존 + D 듀레이션)
TR은 DB 실데이터로 재구성(close수익 + 배당재투자, yfinance 불필요).

| 카테고리 | C 월TR상관 | C CAGR차 | 판정 |
|---|---|---|---|
| 국고채 3Y/10Y/30Y | 0.96~1.00 | 0.1~0.9p | ✅ 확실 |
| 스트립 30Y | 1.00 | 0.25p (D실측 26.7≈config 28.8) | ✅ |
| 종합채권 | 0.93~0.94 | 0.45~0.52p | ✅ |
| 레버리지 2x | 0.93 | 1.17p (`_apply_leverage` 일별리셋 확인) | ✅ |
| CD/MMF carry | 0.71~0.84(평평해 corr낮음) | 0.13~0.57p | ✅ |
| **회사채** | 0.86~0.96 | **1.05~2.17p** | ⚠️ 보통 |
| **한국 미국채(헤지)** | 0.97(shape 좋음) | **2.31~2.76p** | ❌ LEVEL 과대 |

### ★ 다음에 풀 문제 2개 + 해결방향

**[문제1 — 우선] 한국상장 미국채(헤지) CAGR 2.5%p 과대.**
- 원인: **헤지비용 누락.** 헤지 ETF 수익 = USD국채수익 − 헤지비용(≈ 미-한 단기금리차 ~2.5%/yr). 모델은 DGS30 그대로라 과대. shape(월상관0.97)는 맞고 LEVEL만 틀림.
- 해결방향: 헤지 ETF(meta hedge="hedge")의 백필 가격수익에서 **(DGS3MO − CD91)/252 일일 차감.** 데이터 둘 다 index_master에 있음. 적용지점 = `backfill_engine.backfill()` 채권 분기(bond price 만든 직후) or `bond_model.build_bond_price_series`에 hedge_cost 인자 추가.
- 대상: meta hedge="hedge"인 채권 ETF (US_TREASURY_30Y 대부분). 언헤지는 ×환율(이미 처리)이라 별개.

**[문제2] 회사채 CAGR차 1~2p (국채 0.1~0.5p보다 큼).**
- 원인: ① 만기형 듀레이션 실측 0.7~1.0 vs 모델 2.6(롤오버 프록시라 의도된 것) ② carry(CORPAA3Y yield) 과대. 
- 해결방향: 회사채 `book_factor` 별도로 더 낮추거나(현재 전역 0.87), 그냥 Grade C 수용(만기형은 롤오버 프록시라 큰 오차 불가피). 우선순위 낮음.

### 현재 상태 (코드/데이터)
- **모든 채권 백필 클리어됨 → on-demand 재생성** (유저가 ETF 쓸 때 현재 config로). 실데이터·KR금리(ECOS) 보존.
- 핵심 파일: `modules/bond_model.py`(_BOND_ETF_CONFIG US / _BOND_CATEGORY_CONFIG 한국 / COUPON_BOOK_FACTOR 0.87 / STRIP_DURATION_MULT 1.6), `modules/backfill_engine.py`(채권 분기 ~L447-565 / inject_monthly_coupons / _apply_leverage L427 일별리셋).
- 검증 스크립트: `stage_b_verify_kr.py`(한국 C·D), `stage_b_full_verify.py`(US A·B·C·D), `stage_b_duration`/`fetch_kr_rates`/`stage_b_clear_backfill`/`stage_b_rebackfill`.
- gate 2c PASSED.

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] feature | Stage B 채권 모델 완성 — 회사채/스트립/레버리지 + 전 백필 클리어(on-demand)

- **회사채(만기형 포함):** `KR_CORPORATE` 단일 듀레이션 2.6(상시형 실측). 오너 통찰 — 만기형은 롤오버하면 채권사다리라 평균듀레이션 단일값으로 충분(income 추구라 듀레이션 정밀도 실익 작음, 만기보유 시 총수익≈쿠폰yield). 만기 후 데이터 끝은 백필로 못 푸는 별개 한계(티커 자동롤오버 미지원).
- **스트립(무이표):** ETF명 '스트립'/strip 감지 → 듀레이션 ×1.6(STRIP_DURATION_MULT). 검증: 국고채30 스트립 일변동 0.686% vs 순수 0.407% = 1.69x ✅.
- **레버리지/인버스:** 신규 코드 없음 — `meta.leverage`로 기존 `_apply_leverage` 재사용(채권 가격경로에 적용). 검증: 미국채 레버리지 1.580% ≈ 순수 2x ✅.
- **한국 미국채 R²≈0 규명:** 모델 문제 아님 — 한미 거래시차(한국 종가가 전일 미국금리 반영). 전일 lag 회귀 시 R²0.48~0.50, dur 11~12로 회복. 누적 백필 경로는 정상(시차는 월단위로 평균돼 사라짐). 헤지=무FX, 언헤지=×환율(meta가 처리).
- **전 채권 백필 클리어:** 검증 끝나 한국 124종 + US 10종 백필 전부 삭제(실데이터 보존). **on-demand 재생성** 상태 — 유저가 ETF 쓸 때 현재 config로 자동 백필. 미리 다 할 필요 없음(오너 결정).
- gate 2c PASSED. worker 재시작.
- **Stage B 현황:** US 국채 ✅검증 / 한국 국고채·종합채권·회사채·CD/MMF(carry) ✅ / 스트립·레버리지 ✅ / 한국 미국채 ✅(시차는 검증만 영향). **남은 것:** 헤지비용(미-한 금리차, 현재무시 Grade C), 30년 변형 일부, 신용스프레드 정밀화는 후속.

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] verify+fix | Stage B 한국 듀레이션 실측 + 국채 단일값 통일 + stale 백필 삭제

- **듀레이션 실측 (`stage_b_kr_duration.py`, 카테고리당 운용사 다른 3~4종):** ETF 일수익을 Δ금리에 회귀.
  - ✅ **운용사 일관(단일값 OK):** KR_TREASURY_3Y 2.50~3.01(중앙2.54), 10Y 7.42~8.08(중앙7.68), 종합채권 3.63~4.89(중앙4.17).
  - ⚠️❌ **흩어짐 — 운용사 아니라 상품유형 차이:** 30Y 17~27(순수 vs 스트립/Enhanced), 회사채 0.7~2.6(상시 vs **만기형=시변듀레이션**), **미국채(헤지) DGS30 회귀 R²≈0**(한국 거래시차/헤지 NAV).
- **국채 단일값 통일 (오너 결정):** KR_TREASURY_3Y 2.7→2.6, 10Y 8.0→7.7, 종합채권 5.0→4.2. 30Y/회사채/미국채는 별도 검토 유지.
- **stale 백필 삭제 (`stage_b_clear_backfill.py`):** 검증용으로 일괄 백필했던 한국 채권 124종을 삭제(옛 듀레이션이라 stale) — 백필가격 857,122행 + 쿠폰 40,913행. **실데이터(volume>0) 보존.** on-demand로 새 config 재생성 대기. worker 재시작.
- **결론:** 미리 다 백필할 필요 없음(on-demand). 순수 국채는 단일 듀레이션으로 충분. 만기형 회사채(시변)·한국상장 미국채(DGS30 회귀 깨짐)·30Y 변형은 별도 모델/세분 필요.

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] feature | Stage B 한국 채권 — ECOS 금리 수집 + 카테고리 매핑

- **한국 금리 수집 (`scripts/fetch_kr_rates.py`):** ECOS 시장금리 일별(817Y002) → index_master. 국고채 1/2/3/10/20/30년(010190000~010230000), CD91(010502000), KOFR(010901000), 회사채 AA-/BBB- 3년(010300000/010320000). 서버 수집 완료: KTB3Y 6825행(1998~), KTB10Y 6301(2000~), KTB30Y 3380(2012~), CD91 7975(1995~), KOFR 1106(2021~), CORPAA3Y 7975(1995~). ECOS 키 서버 업로드(chmod 600).
- **카테고리 매핑 (`bond_model._BOND_CATEGORY_CONFIG`):** 한국 채권 ETF는 meta.index가 이미 세분 카테고리라 코드별 대신 카테고리 매핑(신규 ETF 자동 커버). `bond_config(code, category)` = 코드별(US) > 카테고리(한국). KR_TREASURY_3Y/10Y/30Y→KTB, KR_BOND_AGGREGATE/KR_CORPORATE→duration, KR_MONEY_MARKET→CD91 carry, US_TREASURY_30Y→DGS30. FX/헤지는 기존 meta(market/hedge)가 처리.
- **검증 (한국 대표 3종 백필):**
  - 114260 KODEX 국고채3년 → KTB3Y duration: 2662행(1998~2009) + 쿠폰129 ✅
  - 459580 KODEX CD금리액티브 → CD91 **carry(가격 평평 1,000,965)** + 쿠폰342 ✅
  - 453850 ACE 미국30년국채(H) → DGS30 duration(헤지 무FX): 11513행(1977~) + 쿠폰554 ✅
  - gate 2c PASSED.
- **발견:** **stale 백필(이전 비-bond 로드)이 신규 bond 백필을 `already` 체크로 차단/오염**(114260 1행만, 453850 NULL close). `stage_b_rebackfill.py`로 삭제 후 재생성하면 정상. → **기존 로드된 한국 채권 ETF 전부 재백필 필요(ops).**
- **남은 것:** ① 한국 ETF 듀레이션 실측 보정(US처럼 — 단 yfinance 한국 adj-close 커버리지 한계로 검증 방식 조정 필요) ② 전 한국 채권 ETF 재백필 ③ 헤지 미국채 hedge-cost(현재 무시) ④ 미배선 카테고리(US_MIXED 혼합형, USD_SOFR, unhedged 미국 MMF).

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] feature+verify | Stage B 모델타입 일반화 + 전수 검증 (US 채권 10종)

- **배경:** Stage B 1차(TLT만 검증) 후 전수 검증(`stage_b_full_verify`: A 가격·B 쿠폰·C 총수익보존·D 시변듀레이션)으로 문제 발견 — ① SHY/SCHO 가격상관 0.4(DGS3MO가 단기곡선 미대표) ② AGG/BND 듀레이션 config 6 vs 실측 4.4 ③ 쿠폰 1.13~1.52x 과대(모델=현재금리 vs 실측=book yield). **실측 데이터는 무손상**(모델은 백필 구간만 생성).
- **결론(검증):** 상수 듀레이션은 장기채 TE(~5%)만 유발(상관 0.98). 더 나쁜 케이스는 rate 매핑(단기)·신용 미모델(aggregate)·쿠폰 기준 문제. **한국 국채/회사채/CD/단기채에서 동일 재발** 예상 → US에서 모델타입 먼저 일반화(오너 결정).
- **구현 (`bond_model.py`/`backfill_engine.py`):**
  - **듀레이션 실측 보정**: GOVT 6→5.3, AGG/BND 6→4.4, SHY/SCHO 1.9→0.8 (stage_b_full_verify D 회귀 중앙값).
  - **`model` 필드**: `duration`(가격 -dur×Δy) | `carry`(가격 평평·수익=이자, MMF/CD/초단기). US **BIL**(단기 T-bill)을 carry 검증용 추가.
  - **쿠폰 book_factor=0.87**: 모델 쿠폰(현재금리)을 실측 분배(book yield, 보수차감)에 근접.
  - `stage_b_rebackfill.py`: 백필 삭제→현재 config 재생성(실데이터 보존). 10종 재백필.
- **재검증 (서버):**
  - D 듀레이션: GOVT 5.3·AGG 4.2·BND 4.4·SHY/SCHO 0.8 = config 일치 ✅.
  - **carry 모델(BIL): 가격 평평 + 쿠폰만으로 총수익 상관 0.945·CAGR차 0.14%p** ✅ → 한국 CD/MMF 모델타입 입증.
  - **총수익 보존 전 10종 우수** (CAGR차 0.03~0.86%p).
  - 회귀: gate 2c PASSED, SCHD 불변.
- **남은 한계(문서화·Grade C 수용):** SHY/SCHO 가격상관 0.4(DGS3MO≠단기곡선; 총수익은 맞음), AGG/BND 0.88(신용/MBS 미모델), 장기채 TE~5%(상수듀레이션), 쿠폰 book_factor는 verify의 raw B엔 미반영(주입 단계만).
- **다음:** 한국 — KOFR/KTB/CD 금리 수집(ECOS/KRX) → config 행 추가(model: 국고채=duration, CD/MMF=carry, 회사채=duration+스프레드) + FX(원화 미국채 ×환율). 모델타입은 입증됨.

_작성: Claude (Opus 4.8)_

---

## [2026-05-31] feature | 배당 백필 Stage B — 채권 듀레이션 가격모델 + 쿠폰 주입 (US 국채)

- **목표:** Stage A의 "price-return 가격 + 명시 분배금" 표준을 채권에 적용. 기존엔 채권 ETF가 `DGS*`(금리 **수치**)에 매핑돼 yield를 가격으로 쓰고(가짜) `_NO_DIVIDEND_INDICES`라 쿠폰 0이었음.
- **결정(오너):** US 국채만 먼저, 듀레이션 표준값. 한국 국채/회사채/MMF는 바로 후속(검증 후). 가용 데이터: DGS10(1962~)/DGS30(1977~)/DGS3MO(1982~) 준비됨. 한국 금리(KOFR/KTB)·신용스프레드는 없음 → 후속 수집 필요.
- **구현 (`modules/bond_model.py` + `backfill_engine.py`, 2개 커밋):**
  - `bond_model`: `_BOND_ETF_CONFIG`(ETF별 rate+duration 명시 매핑, etf_proxy_map 씨앗 — TLT/VGLT/SPTL→DGS30, IEF/GOVT/AGG/BND→DGS10, SHY/SCHO→DGS3MO). `build_bond_price_series`: yield(%)→price-return = `-duration×Δyield`(캐리=이자 제외, 쿠폰으로 분리 → 이중계산 방지).
  - `backfill_engine`: bond_config(code)면 채권 분기 — index_code=rate, yield→price 변환, 배당 대신 `inject_monthly_coupons`(월 쿠폰=price×yield/12). confidence=C. us_etf_list "US Fixed Income" 뭉뚱그림은 ETF 코드 직접 키잉으로 우회.
- **검증 (서버):**
  - 모델 vs 실측 TLT 오버랩(2003~2023): **월수익 상관 0.986**, 추적오차 ~4.9~5.1%, CAGR 모델 -0.12% vs 실측 0.65% → **Grade C** (상관은 A/B급, TE만 C). 가격 경로가 80년대 금리폭등→채권폭락(1977 93.7→1985 36.5)·이후 회복 잡음.
  - TLT 백필: 1977-02~2002-12 (6,461행 + 쿠폰 311건 월). 실측 2003(86.3)에 매끄럽게 연결.
  - 계산기: TLT 20yr **total_dividend(쿠폰) p50=35.2M**(이전 0), end_value p50 71M(~10%/yr), 118케이스(DGS 긴 데이터).
  - 회귀: gate 2c PASSED, SCHD 주식경로 불변(2003~2026, 5674행).
- **다음:** 한국 국채/회사채/MMF — KOFR/KTB·CD 금리 수집(ECOS/KRX) 후 `_BOND_ETF_CONFIG`에 행 추가. 회사채는 신용스프레드 데이터 필요(국채 근사 시 Grade↓).

_작성: Claude (Opus 4.8)_

---

## [2026-05-30] feature | 투자계산기 가상데이터 보충 (use_synthetic 체크 시 윈도우별 독립 합성)

- **배경:** 투자계산기 SCHD 20년이 11케이스뿐(2003 컷 → 22.6년 데이터에 20년 윈도우가 ~11개, 98% 겹쳐 사실상 독립표본 ~1개). "가상데이터 사용" 체크해도 안 늘어남. 원인:
  - DataPreparer 보완 루프가 종목별 **백필 "ok"면 synthetic 스킵** → SCHD는 백필 성공(0행)이라 합성 생성 안 함.
  - 단일계좌=`AccumulationAnalyzer`(체크박스 흔한 경로), 2+계좌=`MultiAccountAnalyzer`. 둘 다 윈도우 수는 data_start~data_end 제한.
- **결정(오너):** B안 — 투자계산기도 배당계산기처럼 **부족분만 가상 보충**. TARGET=40. 체크박스 ON일 때만(OFF면 순수 실데이터). 꼬리 중요 → 윈도우별 독립 GBM(단일경로 슬라이스 아티팩트 회피).
- **구현 (`3c86c49`~`7af4c05`):**
  - `synthetic_price_generator.build_window_synth_params` 공유 헬퍼 추출(종목별 mu/sigma/anchor/actual_start). `WINDOW_SYNTH_TARGET_CASES=40`.
  - `MultiAccountAnalyzer`·`AccumulationAnalyzer` 양쪽: use_synthetic이고 외부 합성 params 없으면 헬퍼로 params 빌드 + 롤링 시작점을 `data_end - years - TARGET×step`로 앞당김 → 합성 prefix + 실 suffix 윈도우 보충. AccumulationAnalyzer는 `_synth_supplement` 플래그로 **기존 DataPreparer 합성 흐름·ISA 풍차돌리기는 불변**.
  - **버그 수정:** anchor를 raw price_daily(USD)로 쓰면 실 suffix가 `get_price`(USD ETF→KRW ×환율)라 단위 불일치 → 2003에서 ~1181배 점프 → CAGR 860억배 폭발. anchor를 `get_price`(FX 적용)로 산출해 해결.
- **검증 (서버):** 단일계좌 SCHD 20년 — syn OFF=11케이스(end_value p50 78.5M), syn ON=**41케이스**(p50 66.5M, p10 69M→45M로 꼬리 확장, 값 정상). 회귀 26/26 PASS(track_g/scenario/rolling), gate 2c PASSED, HTTP 200.
- **유의:** ① 합성 꼬리는 GBM 모델이라 표본 수↑여도 "진짜 정보"는 안 늘고 모델 꼬리만 매끈. ② use_synthetic ON 시 ~4배 느려짐(풀 시뮬). ③ MultiAccountAnalyzer `cagr` 필드는 syn 무관하게 garbage(기존 별개 버그, 분포는 end_value 사용이라 무영향) — 추후 확인.

_작성: Claude (Opus 4.8)_

---

## [2026-05-30] feature | 배당 계산기 확률 슬라이더 기본 50% + 월배당 p25~p75 분포 표시

- **배경:** 자동모드 헤드라인이 90% 단일 꼬리값 → 같은 지수 ETF(402970/458730/SCHD)도 seed가 430~520M로 25% 갈려 보이고 숫자 부풀려 보임(넛지 우려). 실측: 50%(중앙값)로 풀면 4개 다 ~361~364M로 수렴(<1% 차). 차이는 전부 1년+p90 꼬리효과(한국ETF FX리스크 + 실데이터경계 아티팩트).
- **변경 (`73791c6`, 오너 결정):**
  - ① 확률 슬라이더 기본 90%→**50%**, 범위 50~99%→**0~100%** (50%가 한가운데=균형점, 보수계획은 유저가 직접 올림). `dividend_target.html` + `dividend_logic.py` default 0.90→0.50.
  - ② `probability` 모드(고정/자동) 결과에 **예상 월배당 중앙값(p50) + 범위(p25~p75)** 카드 추가. `_run_optimize_scenario` 단일해도 solved value의 배당 분포 반환(`dividend_simulator.py`).
  - ③ 범위(scenario) 모드는 확률곡선이 이미 전 확률 표시 → 밴드 불필요(2변수 스윕 시각폭발 회피, 슬라이더로 탐색).
- **검증 (서버 73791c6):**
  - 3모드 다 정상: 고정(seed 100M→p50 월배당 275k), 자동(seed optimize 50%→solved 363.75M, p50 월배당 1,002,159≈목표100만), 범위(scenario_1var 5pt).
  - 자동모드 4개 ETF ~360M 수렴. /dividend-target HTTP 200, 슬라이더 min0/max100/val50 서빙 확인. gate 2c PASSED(명시 0.90 회귀없음).
- **남은 트레이드오프:** p10~p90 오차막대(IQR 외 더 넓은 구간)는 단일 시나리오 한정으로 추후 검토. std 금지(분포 비정규).

_작성: Claude (Opus 4.8)_

---

## [2026-05-30] fix+verify | 배당 역산 롤링 3단 폴백 + 실데이터 경계 결정화 (BUG-DIV-1 해소)

- **배경:** 직전 재검증에서 배당금 계산기 역산 20yr이 **실데이터를 전부 버리고 가상으로만** 돌던 것 발견. 원인 둘:
  - ① `_find_real_data_start()` 배당간격 휴리스틱이 4종목 전부 오검출(SCHD 2003·458730 2024·446720 2024·402970 2025 vs 진짜 volume>0 경계 2011/2023/2022/2021). 월배당 ETF의 주기전환을 백필경계로 오판.
  - ② `_run_rolling` all-or-nothing: 실 케이스<MIN_CASES(30)면 실데이터 버리고 가상 30개로 **교체**(보충 아님).
- **수정 (`97ac6ab`, `modules/dividend_simulator.py`):**
  - `_find_real_data_start` → `MIN(date) FROM price_daily WHERE volume>0` provenance 결정값으로 교체(투자계산기 `_get_real_dividend_start`와 동일 방식). 휴리스틱 제거.
  - `_run_rolling` 3단 폴백 + `_roll_window` 헬퍼: ①실데이터 구간 롤링 ≥30이면 사용 → ②부족하면 백필 포함 전구간 롤링 → ③그래도 부족하면 **부족분만 가상 보충(실측/백필 케이스 유지)**.
- **검증 (서버):**
  - 휴리스틱→결정값: SCHD/458730/446720/402970 **4/4 OK** (real_start == volume>0 경계).
  - 20yr 케이스 분해: 두 종목 다 tier3 = **백필실측 10 + 가상 20 = 30** (458730 이전 실0→10, 실데이터 안 버림).
  - Gate 2c **PASSED 3/3**. SCHD seed 78.75M vs 458730 82.5M = **1.05x** (4x→1.2x(프록시)→1.05x(3단폴백) 수렴).
  - 투자계산기 변화없음(별경로): 97.2M≈99.4M.
- **결과:** 배당금·투자 계산기 양쪽 SCHD≈458730 내부 일관. 정확성↑(실측 보존), 속도 동일.

_작성: Claude (Opus 4.8)_

---

## [2026-05-30] fix+verify | DJUSDIV_PROXY ^GSPC 제거(2003 시작) + Phase 2c/2e 재검증

- **배경:** Phase 2c/2e 재검증 중 발견 — 배당금 계산기 역산에서 SCHD seed 225M vs 458730 56.25M (**4x 갈림**). 근본원인 둘:
  - ① `dividend_simulator._find_real_data_start()` 배당간격 휴리스틱이 월배당(458730)을 synthetic 경로로, 분기배당(SCHD)을 1928~ 백필 실롤링 경로로 분기 → 분포 폭 달라 p90 역산 증폭.
  - ② DJUSDIV_PROXY 1928~2003 구간이 **^GSPC(S&P500 가격지수)** — 광범위 시장지수라 SCHD 배당전략 미대표. 오너 판단: "전부 빼고 2003 시작".
- **코드 변경 (`e6707bd`):** `scripts/build_djdiv_proxy.py`에서 ^GSPC 세그먼트 + `_fetch_index_db` 제거. 체인 = DVY(2003-11-07)←SDY←SCHD. proxy 24,718행→5,674행.
- **서버 재실행:** `build_djdiv_proxy.py`(DJUSDIV_PROXY 2003-11-07~2026, 5,674행) + `stage_a_rebackfill.py SCHD 458730 446720 402970`. 4개 ETF price_daily 2003~ 재생성(SCHD 5,674행=백필2,002+실3,672). 실측 배당·실데이터 보존.
- **재검증 (서버):**
  - 투자계산기(`calculator_logic`): SCHD total_div p50=97.2M·yield 13.9% ≈ 458730 99.4M·13.0% (div_data_start=2003-12-31, cases=11). **수렴 ✅**
  - 배당금 계산기 역산(`gate_2c_verify.py`): **Gate 2c PASSED 3/3**. SCHD seed 71.25M vs 458730 86.25M — 구 4x→**1.2x 수렴** ✅ (^GSPC 제거로 SCHD 긴 꼬리 롤링 사라지며 자연 해소).
  - 2e 종합과세 엔진(`tax_truth_test.py`): **64/64 PASS**.
- **트레이드오프:** 20yr 롤링 케이스 169→11 (2003 시작이라 20yr-시작점 2003~2006뿐). 신뢰구간 넓어짐 + 2008 폭락 포함으로 dividend_mdd 악화. 방법론상 정직.
- **잔존:** ① `_find_real_data_start` 휴리스틱 자체는 취약(현재 수렴엔 무영향) — bugs.md BUG-DIV-1. ② 2e 갭(other_financial_income 자동산출/전탭배선/_ytd_income 0) = 빌드작업, 재검증 범위 밖.

_작성: Claude (Opus 4.8)_

---

## [2026-05-30] sync+ops | Stage A 서버 적용 완료 + 계획/위키 상태 동기화

- **서버 적용:** Hetzner `178.105.84.213`의 `/root/investment-backtest-engine`을 `52e97c9`까지 fast-forward. `domino`, `domino-celery` 재시작 후 active 확인.
- **서버 DB 재생성:** `scripts/build_djdiv_proxy.py` 실행 후 `scripts/stage_a_rebackfill.py SCHD 458730 446720 402970` 실행.
  - SCHD: 백필 21,046행 + 백필 배당 335건.
  - 458730: 백필 23,979행 + 백필 배당 382건.
  - 446720: 백필 23,832행 + 백필 배당 379건.
  - 402970: 백필 23,563행 + 백필 배당 375건.
- **검증:** 서버 `stage_a_verify.py` PASS 성격 결과, `debug_dividend.py` 배당 p50 > 0 확인, 직접 `run_calculator_logic`에서 458730 `div_real_start=2023-07-28`, `div_is_backfilled=True`, `total_dividend_p50=153,950,817` 확인. `/`와 `/calculator` HTTP 200.
- **정리:** 임시 서버 백업/점검 파일 삭제. 기존 서버 미추적 파일(`data/meta/index_master.db.bak_`, `gunicorn.conf.py`, `share_images/`)은 보존.
- **문서 동기화:** README/로드맵/ETF plan/세금 plan/wiki status·phases·bugs·product 문서를 “배당 0 블로커 → Stage A로 해소, 다음은 Phase 2c/2e 재검증” 상태로 갱신.
- **다음:** `Phase 2c/2e 재검증해줘`. 이후 Stage B(채권/MMF 쿠폰)와 Track G 재개.

_작성: Codex_

---

## [2026-05-30] feature | 배당 백필 Stage A 1~2 — 배당 0 버그 수정 (로컬 검증)

- **Stage A-1 (`a1564ae`):** `build_djdiv_proxy.py`의 SDY/DVY를 `auto_adjust=False`(raw)로 → DJUSDIV_PROXY를 일관된 price-return 체인으로 재구축. 2011 이후(SCHD 앵커+실데이터) 보존, 2011 이전만 price-return 거동으로 변경.
- **Stage A-2:** `backfill_engine.py` — `_NO_DIVIDEND_INDICES`에서 DJUSDIV_PROXY 제거 + `_YIELD_TABLE_ALIAS` (DJUSDIV_PROXY→DJUSDIV100 16년치 yield) 추가. `scripts/stage_a_rebackfill.py`로 SCHD/458730 vol=0 백필 삭제 → 새 proxy로 재백필 + 배당 분리 주입.
  - SCHD: 백필 21,046행 재생성 + 배당 335건. 458730: 23,979행 + 배당 382건(×환율). 실데이터(vol>0)·실측배당 100% 보존.
  - provenance 기록됨 (backfill_runs/price_daily_source/corporate_action_source).
- **검증 (`debug_dividend.py`):** 배당 지표 0→정상. 458730/SCHD total_dividend p50≈1.23억, div CAGR≈8.9%, yield_on_cost≈12.7%. **SCHD≈458730 수렴** (같은 프록시).
- ⚠️ **로컬만 적용** — `price_daily.db`는 git 미추적. 서버(Hetzner)는 코드 pull 후 `build_djdiv_proxy.py` + `stage_a_rebackfill.py` 재실행 필요.
- **남은 Stage A:** ① UI 실측/추정 구분(div_data_start가 1928 표시 — 오해소지) ② 총수익 보존 검증(CAGR 전후 대조) ③ DJUSDIV_PROXY 쓰는 다른 US배당 ETF도 재백필.

_작성: Claude (Opus 4.8)_

---

## [2026-05-30] update | 추가 해결 항목 반영 (오너 확인)

- 오너 확인: isafix 잔여 ①(에러 팝업→배너)·③(T-B3 목표비중 계정연동), handoff T-D5·T-B3·에러팝업, PHASE4 D5·B3 — **전부 해결**.
- 반영: `isafix.md`, `handoff.md`, `PHASE4_PLAN.md`, `PROJECT_MASTER_ROADMAP.md`(Track F 잔여=배당0뿐, Track E 완료목록 갱신), wiki `phases.md`/`status.md`.
- 남은 블로커: 배당 0(`ETF_BACKFILL Phase 6.0`)뿐.

_작성: Claude (Opus 4.8)_

---

## [2026-05-30] sync | 전 계획 파일 + 위키 진행상황 일괄 최신화 + README 규칙 추가

- **배경:** 계획 파일들이 서로 stale·모순 (로드맵은 "Phase 2c/2e 완료·블로커 없음", 세금 plan은 "2e pending", phases.md는 "SCHD/TIGER 수렴"). 실제 진행과 불일치.
- **전 파일 정독 후 실제 상태로 통일** (일관된 through-line = 배당 데이터 0 버그가 현재 블로커):
  - `PROJECT_MASTER_ROADMAP.md`: Current Situation/Source Plans/Dependency Order/Next Action 4곳 정정 (이전 커밋들).
  - `세금...리팩토링계획.plan.md`: Phase 2d→완료, 2e→부분구현(갭 명시), 2c→재검증 필요.
  - `ETF_BACKFILL`: Phase 6.0 범용 배당 백필 재설계 + Phase 7 쿠폰.
  - `PHASE4_PLAN.md`: 상단 진행상태 블록(완료/이슈/미착수/4G 보류).
  - `SYNTHETIC`: 완료 헤더 + 배당백필과 별개 명시. `isafix.md`: 완료 헤더 + 잔여.
  - `handoff.md`: 2026-05-30 정리 배너(해결/미해결 구분).
  - wiki: `product/dev-status.md`(전면 갱신), `phases.md`(3테이블 동기화), `features.md`, `status.md`(블로커/완료/진행중 정정), `index.md`(날짜), `ideas.md`(배당 결정 추가 + 인코딩 손상 flag).
- **README 규칙 추가:** 오너가 "정리할 거 정리해"라고 하면 모든 계획+위키 정독 → 실제 상태 대조 → 전부 최신화 → 로드맵 → commit/push 하는 절차를 README 필수 규칙으로 명시.
- **⚠️ 발견:** `wiki/dev/ideas.md` 일부 한글 mojibake 손상. 손상부 미수정(악화 위험), 복구는 별도 작업.
- **코드 변경 없음.** 문서 동기화만.

_작성: Claude (Opus 4.8)_

---

## [2026-05-30] diagnosis+planning | 배당 0 버그 근본원인 규명 + 배당 백필 계획 추가

- **버그 재정의:** "다중계좌 배당 0"은 다중계좌 문제 아님. 단일계좌 458730/SCHD도 동일. `debug_dividend.py`로 실측(추정 아님).
- **근본 원인:** 가격은 프록시 체인 백필로 1928년까지 존재(458730 백필 97%, SCHD 85%)하나, 실측 배당은 ETF 상장 후만(SCHD 2011~, 458730 2023~). 백필 가격 구간에 `corporate_actions` 배당 row 없음(가격 백필이 `BackfillEngine` 아닌 index_loader 프록시 체인 경로라 배당 주입 단계 누락). `data_start`=1928 → 20년 롤링 윈도우 169개 대부분 배당 이전 시대 → `_fit_distribution` p50=0.
- **추가 발견:** DJUSDIV_PROXY 체인은 adj-close(total-return)라 배당이 가격에 임베딩 → 별도 주입 시 이중계산 → `_NO_DIVIDEND_INDICES`에 의도적 제외. 채권/MMF는 프록시가 금리 수치(DGS10/30/3MO)라 현재 공식 적용 불가로 제외(무배당이라서가 아님). provenance 테이블 전부 0행 = 백필이 provenance 우회 중.
- **결정 (사용자) — 범용 재설계:** 모든 백필을 'price-return 가격 + 명시적 배당' 표준으로 통일(total-return 임베딩 폐기, 이중계산 구조적 차단). DJUSDIV_PROXY 등 adj-close 체인 raw-close로 교체. 단계적: Stage A 주식/배당형 먼저 → Stage B 채권/MMF 후속(필수, 생략 불가). 원자재·FX는 무배당 유지.
- **계획 갱신:** `ETF_BACKFILL_ARCHITECTURE_PLAN.md § Phase 6.0`를 범용 재설계로 재작성 + Phase 7에 쿠폰→분배금 명시 주입(Stage B 필수) 추가. `trackG_multiaccount_plan.md` item 1 정정.
- **코드 변경 없음.** 진단 스크립트(`debug_dividend.py`) + 계획 문서만.
- **다음:** Stage A 구현(total-return 체인 식별 → price-return 재구축 + 배당 분리 → provenance → UI 라벨링 → 검증). 이후 Stage B(채권/MMF).

_작성: Claude (Opus 4.8)_

---

## [2026-05-30] feature+verify | Track G G1 구현(Codex) + 검증(Claude) + 브라우저 실검증

- **커밋:** `b14ed44` (Codex G1 구현), `045d3a7` (divrefactoring.md 커밋). 자동 배포됨.
- **G1 구현 (Codex):** `MultiAccountSimulationLoop`/`MultiAccountAnalyzer` 신규. `calculator_logic.py` accounts 배열 분기(2개↑ 다중, 1개 단일 유지). 투자계산기 UI 계좌별 독립 입력으로 교체. `tests/test_track_g_multi_account.py` L0~L3 추가.
- **검증 (Claude):** L0~L3 4/4 PASS + 테스트 내용 직접 확인(형식적 아님). L1이 "시나리오 합산 ≠ 퍼센타일 덧셈" 정확히 증명. L3 세금 손계산값 일치. Gate 2a/2b/2c 12/12 PASS(단일계좌 회귀 안 깨짐).
- **브라우저 실검증:** TIGER미국배당다우존스(ISA) + SPY(위탁) 다중계좌 실데이터 정상 작동. 시작시점 1964년은 정상(USD/KRW FX 바닥값, 단일계좌와 동일 동작).
- **G1 후속 보완 항목** (trackG_multiaccount_plan.md에 기록, 중요도순):
  1. [버그] 다중계좌 시 배당 지표 전부 0 (총배당/마지막연도/CAGR/배당률분포) — 결과 스키마에 배당 분포 메트릭 누락 추정. 우선순위 높음.
  2. [UX] 2번째 계좌 입력 시 커서 사라짐 — 입력 중 전체 재렌더로 포커스 유실(BUG-6 패턴). 중간.
  3. [미적] 계좌 카드 UI 통일성/위계. 낮음.
- **다음:** G1 후속 보완(배당버그 우선) → 은퇴/백테스트 탭 확장 → G2.

_작성: Claude (Opus 4.8) — 구현 Codex, 검증 Claude_

---

## [2026-05-30] planning | Track G 다중 계좌 시뮬 상세 계획 작성 (trackG_multiaccount_plan.md)

- **신규 파일:** `trackG_multiaccount_plan.md`. `PHASE4_PLAN.md § 4G`에서 링크.
- **핵심 설계 결정:**
  - 단일 통합 엔진 (다중 계좌 시간 루프). G1/G2/G3는 별도 엔진 아니라 `transfers` 기능 플래그. G1에서 만든 루프를 G2/G3가 그대로 씀 — 버리는 코드 없음.
  - 계좌별 독립 입력 (초기자본/월적립금/종목/비중/유형). 기존 `taxAccounts` %분할 모델 폐기.
  - 자금 흐름 = 사용자 설정 분배 정책(순서 있는 목적지+상한). 고정 프리셋 폐기. 월 초과분·만기 목돈 동일 메커니즘.
  - ISA→연금 이전 제도가 풍차돌리기 핵심 경로 (v1의 "위탁 임시운용+매달매도" 전략 폐기).
  - **배당금 계산기는 Track G 범위 제외 — 단일 계좌 유지.** `DividendSimulator` 자체 루프라 통합 엔진 공유 불가, 풀 통합은 속도 위험으로 보류(divrefactoring.md). 적용 탭: 투자계산기/백테스트/은퇴 3개.
- **G1 확정:** 합산 위험지표 포함(일별 합산 기록), 공유 시작일 max, 회귀 ±1원/±0.01%, 테스트 가능성 위해 결정론적 데이터 주입 설계.
- **테스트 설계:** 결정론적 가격 픽스처(평탄/고정성장/단일배당/계단) + 계층 L0~L7. L5b 다중사이클 풍차돌리기 핵심 검증. 자금보존 등 공통 불변식.
- **구현 순서:** 투자계산기 1탭 완성·검증(L0~L3) → 나머지 탭 복제. G2는 G1 코드 보고 재설계 후 착수.
- 코드 변경 없음. 계획 문서만.

_작성: Claude (Opus 4.8)_

---

## [2026-05-30] fix+bugfix | BUG-1 수정 + ISA 캡 구현 + 백필 데이터 노출 버그 수정

- **커밋:** `f35a611` (BUG-1), `7dd75a4` (ISA 캡 재설계), `3e572b7` (백필 차트/신규종목)
- **BUG-1 수정**: calculator.js + retirement.html catch 블록에서 `_errData` null 시 `err.message` JSON 파싱 fallback 추가 → ISA+SPY 등 계좌 제한 에러가 alert() 팝업 대신 인라인 배너로 표시됨
- **ISA 1억 캡 로직 재설계**: 월 납입금 균등 축소 → 납입 지속 후 한도 도달 시 중단 방식으로 변경. `SimulationConfig.contribution_end_months`, `AccumulationAnalyzer`, `DividendSimulator.isa_total_limit` 추가
- **백필 데이터 차트 노출 버그**: `get_symbol_data`에서 volume=0(BackfillEngine 추정 데이터) 행 차트 제외. 217770 같은 프록시 백필 ETF가 2000년부터 잘못된 데이터를 표시하던 문제 해결
- **신규 종목 은퇴시뮬 실패 버그**: `retirement_logic.py`에 `prepare_scenario_data` 전 `get_price` pre-loading 추가. BackfillEngine은 실데이터 있는 ETF만 백필 가능 — 한 번도 조회 안 된 종목에서 "가격 데이터 없음" 오류 방지
- **조사**: (H) 환헷지 백필 이미 올바르게 처리됨 (`hedge == "unhedged"` 조건). 인버스/레버리지 단순 배수 적용 확인, Phase 5에서 daily reset 모델 고도화 예정

---

## [2026-05-29] fix+planning | UI 버그 수정 + ISA 캡 재설계 계획 + 문서 전면 정비

- **커밋:** `671b28b` (rebal-action 폭 고정), `e734b4a` (calculator.js 캐시 무효화)
- **BUG-6 수정:** 리밸런싱 행 `.rebal-action` min-width:145px/flex-shrink:0 추가, ₩amount min-width:100px. 메시지 길이 달라도 열 폭 고정.
- **TF5 수정:** calculator.js 버전 문자열 `20250523c5→20260529`. 브라우저 캐시에서 구버전 JS 제공하던 문제 해결.
- **ISA 1억 캡 재설계 계획** (`handoff.md` 추가): 현재 방식(월 납입 균등 축소) → 올바른 방식(납입 지속하다 1억 도달 시 납입 중단). AccumulationAnalyzer에 `contribution_end_months` 파라미터 추가 설계. 파이어 시나리오("N년 적립 후 코스팅") 범용 기능으로 확장 가능.
- **문서 전면 정비:** phases.md (Track A/B/C/D + Phase 2c~3 ✅), bugs.md (활성 BUG-1~5 신규 기재), status.md (PHASE4 체크리스트 갱신 + 한 줄 요약 수정), PROJECT_MASTER_ROADMAP.md (Track F "Not started"→"Backend complete, BUG-1~5 remaining").
- **미완료:** BUG-1(TF1 팝업), BUG-2(retirement.html 배너), BUG-3(연금 나이 입력), BUG-4(ISA 캡 재설계 구현), BUG-5(슬라이더 입력).

_작성: Claude_

---

## [2026-05-29] feature | PHASE4 빠른 항목들 — F1/B2-b/B2-c/B3/D5 구현

- **커밋:** `1c5db23` (F1+B2-c), `02cb3e8` (B2-b+B3), `7182ad1` (D5) — GitHub push 완료. Hetzner 배포 필요.
- **F1 (대기 UX)**: Celery 2-worker 기준으로 대기 문구 수정. rank < 2 → "곧 시작됩니다". rank >= 2 → "내 앞에 N개 대기 중". 예상 대기시간도 워커 수 고려 보정.
- **B2-c (내자산 캐싱)**: `myassets_data()` Redis 캐시 추가. US 종목 개별 `yf.Ticker()` 반복 → `yf.download()` 배치 1회. 장중 15분, 장외 4시간 TTL.
- **B2-b (자산 추이 차트)**: myassets.html 자산현황 탭 하단에 포트폴리오 추이 차트 추가. `/api/portfolio/history` 재사용. 1개월/3개월/1년/전체 기간 선택.
- **B3 (리밸런싱 경고 밴드)**: 5% 기본 밴드 기준으로 색상 경고 + 이탈 뱃지 추가. 전체 적정/이탈 요약 배너.
- **D5 (인플레이션 생활비)**: 은퇴 시뮬 입력 패널에 실시간 생활비 계산 인포박스. 결과 메시지에 명목 수익률 기준 안내.
- **미완료/스킵**: D4(거래수수료) — FeeEngine이 시뮬 루프에 연결 안 됨, 별도 작업 필요. B2-a(홈 토글) — 우선순위 낮아 스킵.
- **다음:** Hetzner 배포 후 T-F1~T-F8 + PHASE4 항목 브라우저 테스트. 이후 D4 또는 D1/D2로.

_작성: Claude_

---

## [2026-05-29] feature | Track F — ISA/계좌 규제 정합성 강제 구현

- **커밋:** `e8b7c1e feat: Track F — ISA/계좌 규제 정합성 강제`
- **배포:** GitHub push 완료. Hetzner SSH 불가 (네트워크 타임아웃). 사용자 수동 배포 필요: `git pull --ff-only && systemctl restart domino domino-celery`
- **구현 내용:**
  - `base_tax.py`: `COMMODITY_ETF` 분류 추가 (골드선물·원유선물·원자재 등 키워드 기반). `classify_instrument_type()` 반환값에 추가.
  - `account_tax.py`: 연금저축/IRP 블록 분리. IRP에 COMMODITY_ETF 금지 추가. `validate_isa_contribution(initial, monthly)` 신규 함수 — `(2000만-initial)/12` 기준 월납입 상한 검증.
  - `calculator_logic.py`: 종목 제한 검증 + ISA 풍차돌리기 hard block + ISA 납입 하드 체크 + 1억 총 납입 소프트 캡 + `isa_cap_info` 반환.
  - `retirement_logic.py`: 동일 검증 패턴 적용.
  - `dividend_logic.py`: 종목 제한 + ISA 납입 하드 체크.
  - `calculator.html`: 에러 배너 3종 추가 (종목 제한 빨간, ISA 한도 빨간, ISA 1억 캡 주황).
  - `retirement.html`: 에러 배너 2종 추가.
  - `calculator.js`: FAILURE 시 JSON 파싱 에러 핸들링 → 배너 표시. `renderResult`에 ISA 캡 경고 배너 처리.
- **백엔드 단위 검증 PASS:**
  - ISA+SPY → BLOCKED
  - ISA+458730(KR_FOREIGN) → PASS
  - ISA initial 3000만 → BLOCKED
  - ISA monthly 100만(한도83만) → BLOCKED
  - ISA 정상(500만/50만) → PASS
  - KODEX 골드선물(132030) → COMMODITY_ETF
  - IRP+골드선물 → BLOCKED
  - 연금저축+골드선물 → PASS
- **미완료:** 브라우저 배너 시각 확인 (사용자 직접 테스트 필요). Hetzner 배포.
- **다음:** Track G (다중 계좌 시뮬) 또는 PHASE4 빠른 항목들.

_작성: Claude_

---

## [2026-05-29] planning | 규제 정합성 계획 + 마스터 로드맵 전면 재정비

- **수동 테스트 T1~T4 완료**: T1(가상 데이터 배너) PASS, T2(종합과세/분할매도) PASS, T3(ETF 백필 provenance) PASS.
- **T4 무효화 확정**: ISA 풍차돌리기 + 중도해지 체크박스 테스트였으나, Track F(isafix) 구현 시 ISA 풍차돌리기 자체가 hard block됨 → T4는 Track G(다중 계좌) 완료 후 재작성 필요.
- **ISA/계좌 규제 정합성 문제 발견**: 투자계산기·연금·배당금 계산기에서 ISA+SPY, IRP+원자재 ETF 등 불법 조합이 무제한 실행됨. 백테스트에는 이미 검증 있으나 나머지 시뮬에 없음.
- **`isafix.md` 신규 생성**: 계좌별 종목 제한(ISA/연금저축/IRP), ISA 납입 한도(초기·월·총 1억), ISA 풍차돌리기 차단, COMMODITY_ETF 분류 추가 계획 문서. 프로젝트 루트에 저장.
- **`PHASE4_PLAN.md` 4G 섹션 추가**: 다중 계좌 시뮬레이션 엔진 계획. G1(롤링 엔진 — 퍼센타일 단순 덧셈 금지, 시나리오별 합산 후 분포 계산), G2(진짜 ISA 풍차돌리기: 만기→2000만 재납입+나머지→위탁), G3(ISA→연금 이전). Track F 선행 필수.
- **`PROJECT_MASTER_ROADMAP.md` 전면 재정비**: Track A/B/C/D 전부 완료 반영, 우선순위 [1]~[5] 순서 재정리, ETF_BACKFILL V2 Phase 3+ 영구 보류→[3]으로 격상, 일정 기반 계획 제거 → 품질·의존성 기반으로 전환.
- **현재 우선순위**: [1] Track F(isafix) + PHASE4 빠른 항목 병렬 → [2] Track G → [3] ETF_BACKFILL V2 Phase 3+ → [4] PHASE4 핵심/복잡 → [5] 인프라/UX 마감.
- 코드 변경 없음. 계획 문서만 수정.

_작성: Claude_

---

## [2026-05-29] close | 세금설정 통일 세션 마감 상태

- 최종 코드/문서 HEAD: `c12ca1e 금융소득 자동산출 계획 정본화`.
- 서버 repo도 `c12ca1e`로 fast-forward 완료. 마지막 코드 배포(`192693c`) 후 `domino`, `domino-celery` active 및 주요 5개 화면 HTTP 200 확인.
- 오늘 완료: T2 JSON 직렬화 수정, 분할매도 세후금액/근로소득 반영 확인, 세금설정 프로필 입력원 통일, 금융소득 수동 입력 제거, 금융소득 자동 산출 계획 정본화.
- 다음 작업 후보: `세금에서시작된완전리팩토링계획.plan.md` Phase 2e의 금융소득 자동 산출 구현. 백테스트부터 직전 완료년도 gross 배당·이자 집계 → `other_financial_income` 런타임 주입 순서로 진행.
- 로컬에 남은 uncommitted 항목은 이번 Codex 코드 변경이 아님: `data/meta/index_master.db`, `moneymilestone/.obsidian/graph.json`, `moneymilestone/.obsidian/workspace.json`, `4testguide.md`.

_작성: Codex_

---

## [2026-05-29] feature | 세금 설정 프로필 입력 통일 + 금융소득 자동 산출 계획

- 사용자 요청: 각 계산기 탭에 흩어진 나이/연간 근로소득 입력칸을 제거하고 세금 설정탭 값을 공통으로 사용. 금융소득은 세금설정에서 묻지 말고 계산 결과에서 자동 산출할 수 있는지 계획만 수립.
- 수정:
  - `templates/calculator.html`, `static/js/calculator.js`: 투자계산기 세금 패널에서 나이/연소득 입력 제거. 세금 ON 시 `/api/settings/tax` 우선, localStorage fallback으로 프로필 로드 후 `user_settings`에 주입.
  - `templates/backtest.html`: 백테스트 세금 패널에서 나이/연소득/기존 금융소득 입력 제거. 계좌 유형만 남기고 세금 프로필을 표시.
  - `templates/retirement.html`: 연금 시뮬레이션 세금 패널에서 나이/연소득 입력 제거. 세금 프로필의 나이로 수령 시작 나이/세금 안내 계산.
  - `templates/dividend_target.html`: 배당금 계산기도 localStorage만 보던 로직을 서버 세금설정 API 우선 로드로 변경.
  - `templates/tax_settings.html`: `기존 연간 금융소득` 수동 입력/요약/저장 제거.
- 계획 문서화: `moneymilestone/wiki/dev/ideas.md`에 금융소득 자동 산출 설계 추가. 핵심은 계산기별 시뮬레이션에서 직전/최근 완료년도 세전 gross 배당·이자 흐름을 집계해 `other_financial_income`으로 세금 엔진에 넘기는 것.
- 주의: `backtest_logic.py`와 `split_sale_planner.py`의 `other_financial_income` 파라미터는 유지. UI 수동 입력만 제거했고, 향후 자동 산출값 주입 지점으로 사용한다.
- 검증/배포: 로컬 `py_compile`, `node --check`, `git diff --check` PASS. Flask test client와 브라우저 토글 확인에서 5개 화면(`/calculator`, `/backtest`, `/retirement`, `/dividend-target`, `/tax-settings`) PASS. 서버 `192693c` 배포 후 gunicorn 5000 포트 기준 5개 화면 HTTP 200 확인.
- 정정: 금융소득 자동 산출 상세 계획의 정본 위치를 `moneymilestone/wiki/dev/ideas.md`가 아니라 `세금에서시작된완전리팩토링계획.plan.md` Phase 2e로 이동. `ideas.md`에는 포인터만 남김.

_작성: Codex_

---

## [2026-05-29] feature/fix | 분할매도 최적연수 기준 명확화 + 세후금액/기존 금융소득 반영

- 사용자 질문: 분할매도 패널의 `최적 연수` 기준, 근로소득/금융소득 반영 여부, 세후 금액 표시 필요.
- 현재 기준 확인: `optimal_years`는 1~20년 균등분할 시나리오의 총 세금(`plan_by_year`)이 최소인 연수. 동률이면 가장 먼저 나온 작은 연수가 선택됨.
- 기존 상태: 근로/사업소득(`earned_income`)은 종합과세 누진세 계산에 반영되고 있었으나, 백테스트에서 기존 금융소득(`other_financial_income`)은 `0.0`으로 고정되어 있었다.
- 수정:
  - `backtest_logic.py`: `user_settings.other_financial_income`을 `compute_split_sale_plan()`에 전달.
  - `split_sale_planner.py`: `gain`, `lump_sum_after_tax`, `split_after_tax`, `optimal_after_tax`, `after_tax_by_year`, 입력 소득값(`earned_income`, `other_financial_income`) 반환.
  - `templates/tax_settings.html`: 세금 설정에 `기존 연간 금융소득` 입력/저장/요약 추가.
  - `templates/backtest.html`: 세금 ON 시 저장된 세금 설정을 로드하고, 백테스트 세금 패널에 `기존 연간 금융소득` 입력 추가. 분할매도 패널에 일괄/분할 세후 이익과 최적 세후 이익 표시.
- 검증:
  - 로컬 단위: 같은 1억 KR_FOREIGN 이익에서 소득 0/0 vs 근로 5천만+금융 1,500만의 일괄세금/최적연수가 달라짐. JSON 직렬화 통과.
  - 서버 배포: 커밋 `c519620`, `git fetch origin main && git merge --ff-only origin/main`, `systemctl restart domino domino-celery`.
  - 서버 `/api/backtest/submit`: 458730, 과세 ON, 위탁, 근로소득 5천만, 기존 금융소득 1,500만 검증 PASS. `split_sale_plan`에 `lump_sum_after_tax=664,301,962`, `split_after_tax=746,736,130`, `optimal_after_tax=855,433,488` 반환 확인.

_작성: Codex_

---

## [2026-05-29] bugfix | T2 split_sale_plan JSON 직렬화 오류 수정

- 증상: T2 금융소득종합과세/분할매도 패널 테스트 중 백테스트가 `TypeError('Object of type bool is not JSON serializable')`로 실패.
- 원인: `modules/tax/split_sale_planner.py`의 `over_threshold`가 `numpy.float64` 비교 결과인 `numpy.bool_`로 반환됨. 서버 Python에서는 클래스명이 `bool`로 표시되어 Celery/Kombu JSON serializer가 결과 저장 중 실패.
- 수정: `over_threshold = bool(...)`로 명시 변환하고 반환 dict에서도 `bool(over_threshold)`로 보강. 커밋 `f64846c`.
- 구현 상태: 금융소득종합과세/분할매도 계산 자체는 동작 중이었고, 이번 문제는 결과 payload 타입 정리 누락이었다.
- 서버 배포: `git pull --ff-only`, `systemctl restart domino domino-celery`.
- 검증:
  - 서버 단위 확인: `compute_split_sale_plan(np.float64(...))` 결과가 `json.dumps()` 통과.
  - 실제 `/api/backtest/submit` T2 유사 payload(458730, 과세 ON, 위탁, 초기 5억원, 2015-01-01~2026-05-28) 성공.
  - 결과: `status=SUCCESS`, `split_sale_plan.over_threshold=True`, `kr_foreign_unrealized_gain=1,203,859,330`, 분할매도 패널용 `plan_by_year` 반환 확인.

_작성: Codex_

---

## [2026-05-29] ops/bugfix | 479080 T1 float(None) 재현 원인 확인 및 서버 worker 정리

- 증상: 투자 계산기 T1 검증 중 479080(머니마켓/CD 계열 ETF) + 가상 데이터 ON 실행 시 프런트에 `float() argument must be a string or a real number, not 'NoneType'` 표시.
- 서버 로그 위치: `tasks.run_simulation_task -> calculator_logic.run_calculator_logic -> prepare_scenario_data -> DataPreparer.prepare -> TickerStatsCache.get_or_compute`.
- 서버 DB 확인: `price_daily`의 479080 실제 가격은 2024-04-02~2026-05-27 518행, 그중 2025-11-13 row는 배당 이벤트만 있고 `open/high/low/close=NULL`, `volume=0`, `corporate_actions.dividend=455`.
- 현재 배포 코드(`ff43956`)의 `TickerStatsCache`에는 NULL close 필터가 이미 있어 단독 `get_or_compute('479080')`는 정상 성공. 이후 stats cache 생성됨.
- 추가 원인: 서버에 Celery worker가 두 벌 떠 있었음. systemd worker 외에 과거 수동 실행 worker가 큐를 같이 소비해 stale worker가 작업을 잡을 수 있는 상태였다.
- 조치: 수동 Celery worker(PID 67797 계열) 종료. systemd `domino-celery` worker와 `domino-celery-beat`만 active 상태로 정리.
- 검증:
  - `DataPreparer.prepare(['479080'], sim_years=20, allow_synthetic=True)` 정상: `n_cases=61`, `used_synthetic=True`, `anchor_price=50020.0`.
  - 실제 프런트와 동일한 `/api/calculator/submit` 경로로 479080 20년 synthetic ON 실행 성공: `status=SUCCESS`, `cases_count=61`, `used_synthetic=True`, `synthetic_info.479080` 생성.
- 부작용/상태: 검증 과정에서 서버 DB에 479080 synthetic rows 8,570개(1991-05-28~2024-04-01)와 `ticker_return_stats` cache가 생성됨. 이는 T1 검증용 정상 데이터.

_작성: Codex_

---

## [2026-05-28] bugfix | 가상 데이터 시뮬 2차 — 배너·2007이상치·float크래시 수정

- **버그 1**: `used_synthetic` 배너 미표시
  - 원인: DataPreparer n_cases≥30 early return 시 `used_synthetic=False` 하드코딩
  - 수정: early return 전 `price_daily_synthetic` 존재 쿼리, 커밋 `3a190b5`
- **버그 2**: 가상 데이터 차트에서 2007 시작이 항상 최고 수익
  - 원인: `seed=hash(code)` → 단일 결정론적 GBM 경로를 60개 윈도우가 공유. 경로 저점에 걸린 윈도우가 항상 높은 CAGR
  - 수정: `AccumulationAnalyzer._load_with_per_window_synthetic()` 신설 — 윈도우별 `seed=hash(code+start_date)` 독립 경로. DB 저장 경로는 배너 감지용으로만 유지. 커밋 `cccda40`
- **버그 3**: `float() argument must be a string or a real number, not 'NoneType'` — sigma_monthly
  - 원인: `_load_with_per_window_synthetic()` None 가드에 `sigma_monthly` 누락
  - 수정: 가드 조건 추가, 커밋 `86d6a39`
- **버그 4**: 동일 에러 — KOFR 등 flat ETF
  - 원인: `TickerStatsCache` `float(r[1])` NULL close 행 비필터링. `DataPreparer` anchor_price에 NULL close 미처리
  - 수정: NULL 행 사전 필터 + `is not None` 체크, 커밋 `786831f`
- **T1~T4 수동 테스트**: 코드 수정 완료, 브라우저 직접 확인 대기 중

_작성: Claude_

---

## [2026-05-28] bugfix | 가상 데이터 시뮬레이션 무한대기 3연속 버그 수정

- **버그 1**: `get_price(allow_synthetic=True)` 롤링 168창마다 yfinance API 호출
  - 원인: `get_date_range_in_db()`이 `price_daily`만 확인 → synthetic 구간을 갭으로 인식 → API 시도
  - 수정: `allow_synthetic=True`시 `price_daily_synthetic` 범위도 합산 → API 호출 0회
  - 커밋: `0a90252`
- **버그 2**: TARGET_CASES 캡이 `if synthetic_info:` 조건에 막혀 미적용
  - 원인: synthetic 데이터 이미 존재 시 `synthetic_info={}` → 캡 블록 미실행 → 169 창
  - 수정: 조건 제거, 항상 적용
  - 커밋: `d8133f5`
- **버그 3 (진짜 원인)**: DataPreparer step 2 early return이 cap보다 먼저 실행
  - 원인: `n_cases=169 >= MIN_CASES(30)` → step 2에서 즉시 return → step 4 cap 미도달
  - 수정: cap을 early return 전으로 이동
  - 커밋: `86ac13d`
- **결과**: 495330 20년 가상 데이터 시뮬 → 169창 → 61창, ~30초 완료

_작성: Claude_

---

## [2026-05-28] bugfix | 가상 데이터 DB 오염 — 중대 아키텍처 버그 수정 + 서버 클린업

- **버그**: `SyntheticPriceGenerator`가 `price_daily` 실데이터 테이블에 가상 데이터 직접 기록. `retirement_logic.py` `allow_synthetic=True` 하드코딩으로 유저 옵트인 없이도 오염됨
- **수정**: `price_daily_synthetic` / `corporate_actions_synthetic` 별도 테이블 신설. `allow_synthetic` 플래그를 `PriceLoader → PriceDataLoader → AccumulationAnalyzer` 전체 콜체인에 전파
- **서버 클린업**: `scripts/cleanup_synthetic_contamination.py` 실행 → `price_daily` 199,581행 / `corporate_actions` 2,585행 제거. 정상 백필 4개 종목 복원(069500, 133690, 446720, 458730)
- **수정 파일**: `synthetic_price_generator.py`, `price_loader.py`, `price_data_loader.py`, `accumulation_analyzer.py`, `retirement_logic.py`, `data_preparer.py`, `backfill_engine.py`
- 커밋: `374f0a5`

_작성: Claude_

---

## [2026-05-28] bugfix | 투자 계산기 — 가상 데이터 관련 버그 2건 수정

- **버그 1**: 상장 1년 미만 ETF(예: 0103T0) + 가상 데이터 ON → "롤링 케이스가 0개입니다" 에러
  - 원인: TickerStatsCache가 데이터 부족으로 None 반환 → DataPreparer가 가상 데이터 스킵 → effective_start 최근일 유지 → 롤링 0
  - 수정: calculator_logic.py에서 n_cases=0 시 "가상 데이터 생성 불가" 명확한 에러. data_preparer.py warnings 추가.
  - 커밋: 2151db1
- **버그 2**: 새 종목 첫 실행 시 "준비 중" 장시간 (495330 등)
  - 원인: BackfillEngine이 PriceLoader(get_price)와 DataPreparer 두 곳에서 중복 실행. 준비 단계 동안 진행률 없음.
  - 수정: backfill_engine.py volume=0 행 있으면 즉시 ok 반환(중복 계산 스킵). tasks.py preparing PROGRESS 전송. calculator.js "데이터 준비 중" 표시.
  - 커밋: 90afb15
  - 영향 범위: BackfillEngine fix는 백테스트/은퇴 탭도 자동 적용. "데이터 준비 중" UI는 투자 계산기만.

_작성: Claude_

---

## [2026-05-28] feature | 금액가리기+내자산연동 정상화

- 홈 포트폴리오 카드:
  - `/api/portfolio/history`가 기존 DB 히스토리 뒤에 내자산 현재가 기반 평가액을 오늘 날짜로 반영.
  - 프론트에서 `_portfolioData` 1회 캐시를 제거하고 60초마다 포트폴리오/자산군 데이터를 재조회.
- 홈 자산군 비교:
  - `/api/assets`가 그룹 목표비중 대신 실제 보유자산 그룹별 현재 평가액 비중을 우선 반환.
  - 실제 평가액이 없으면 기존처럼 목표비중 fallback.
- 금액 가리기:
  - 내자산 탭 상단에 `금액 가리기` 체크박스 추가.
  - 기본값은 가리기(`hide_amounts=True`).
  - 가리기 ON이면 홈/내자산 금액 표시와 차트 tooltip/y축 금액을 `***,***,***원` 또는 `***`로 표시.
  - 설정은 `user_settings.tax` JSON의 `hide_amounts`에 보존. 세금 설정 저장 시 기존 `hide_amounts`를 유지하도록 `save_settings()` 보강.
- 검증:
  - `.\venv\Scripts\python.exe -m py_compile app.py modules\auth_manager.py` PASS.
  - `.\venv\Scripts\python.exe app.py` 기동 후 `/`, `/myassets` HTTP 200 확인.
- 작성: Codex

---

## [2026-05-28] decision | 가격 데이터 저장 정책 문서화

- 사용자 질문: 즐겨찾기/검색/계산 종목을 전부 서버에 쌓으면 용량이 터질 수 있는데, 데이터를 사용자 폰/컴퓨터에 저장하는 발상 전환이 맞는지 검토.
- 결론: 서버 DB가 canonical price history를 유지한다. 클라이언트 IndexedDB/모바일 SQLite는 나중에 chart/search UX cache로만 사용한다.
- 이유:
  - 서버가 시뮬레이션 입력, API 키 보안, actual/backfilled/synthetic provenance, confidence, 재생성/삭제 정책을 책임져야 함.
  - 클라이언트는 기기 변경/캐시 삭제/다중 기기/stale 데이터 위험이 있어 정본 저장소로 부적합.
  - 서버 용량 문제는 `price_cache_meta` + core/protected/user_requested/generated/transient 등급 + dry-run cleanup으로 관리 가능.
- 문서 반영:
  - `ETF_BACKFILL_ARCHITECTURE_PLAN.md`: `Price Cache Metadata`, `Price Data Retention And Client Cache Policy` 추가.
  - `PHASE4_PLAN.md`: E4 `서버 가격 데이터 보존 정책 (core + user-requested TTL/LRU)` 추가.
  - `PROJECT_MASTER_ROADMAP.md`: `Data Storage Policy Decision` 및 Do Not Do Yet 보강.
  - `wiki/dev/status.md`, `wiki/dev/ideas.md` 최신화.
- 구현 순서 메모: 먼저 diagnostics → `price_cache_meta` → core registry → access tracking → protected resolver → dry-run cleanup → 제한적 cleanup → 이후 client UX cache.
- 작성: Codex

---

연대순 기록. Append-only. 삭제하지 말 것.

---

## [2026-05-28] bugfix | KRX 금현물 stale 가격 및 지수 최신화 로직 보강

- 원인: 서버에 `data/meta/krx_api_key.txt`가 없어 Celery Beat `tasks.refresh_krx_gold`가 07:30 UTC 실행 후 실패했고, Redis `mq:krx_gold`에는 2026-03-31 가격 캐시가 남아 홈 화면이 stale 값을 표시함.
- 서버 조치: `ecos_api_key.txt`, `fred_api_key.txt`, `krx_api_key.txt` 업로드 및 `chmod 600`.
- 코드 조치:
  - `refresh_krx_gold`: 최근 15일 fallback, 저장 성공 시 Redis `mq:krx_gold` 삭제, 오류는 Celery 실패로 드러나게 변경.
  - `celery_app.py`: KRX 금현물 Beat를 16:40 / 18:30 / 22:30 / 다음날 08:30 KST 다회 재시도로 변경.
  - `KRXClient`: 환경변수 키 지원 및 날짜 미지정 시 최근 15일 fallback.
  - `IndexLoader.download_all()`: 기존 “DB에 있으면 스킵” 제거, `get()` 기반으로 누락 앞/뒤 구간 fetch.
- 서버 상태: `KRX_GOLD` 전체 재수집을 백그라운드로 진행 중. 날짜별 API 호출이라 장시간 소요.
- 검증: `py_compile` PASS, 임시 DB 테스트에서 `download_all()`이 누락 구간 fetch 호출 확인.

_작성: Codex_

---

## [2026-05-28] bugfix | ISA 풍차돌리기 잔여 사이클 세율 수정

- 문제: 시뮬 기간이 3의 배수 아닐 때 잔여 사이클에 중도해지세 강제 적용 → 의도와 다른 결과
- 수정: 잔여 사이클 기본값 만기 가정(9.9%)으로 변경. 중도해지 가정(15.4%) 값도 추가 계산.
- 프론트: ISA 중도해지 경고 배너 + 체크박스. 체크 시 p10/p50/p90, 히스토그램, 롤링 차트 즉시 전환 (재요청 없음)
- base_tax.py 주석 오류 수정: ISA_CANCEL_RATE 16.5% → 15.4%
- 커밋: 7b76a63

_작성: Claude_

---

## [2026-05-28] feature | ETF_BACKFILL Phase 2 완료 — Provenance 스키마 + 통합

- modules/provenance.py 신규 (커밋 dd722ec)
  - 3개 테이블: backfill_runs, price_daily_source, corporate_action_source
  - 유틸: ensure_provenance_tables, new_run_id, write_backfill_run, write_price_source, write_action_source
  - delete_by_run_id: run_id로 생성 데이터 안전 삭제 (source_type='actual' 제외)
  - is_generated: 실측 vs 생성 판별 (provenance 레코드 없으면 volume=0 fallback)
  - get_run_summary: 코드별 백필 실행 이력
- BackfillEngine.__init__: ensure_provenance_tables 호출
- inject_quarterly_dividends: 반환 타입 int → (int, list[str])
- BackfillEngine.backfill(): 성공 시 provenance 3종 기록 (confidence B/C), run_id 반환
- generate_and_save: 반환 dict에 dates 리스트 추가
- data_preparer.py: 합성 데이터 생성 후 provenance 기록 (confidence D)
- 다음: ETF_BACKFILL Phase 3 (Universe 확장) 또는 PHASE4 잔여 기능

_작성: Claude_

---

## [2026-05-28] feature | Tax Phase 2d/2e/3 완료 — 세금 리팩토링 전 단계 완료

- Phase 2d: WithdrawalAnalyzer → TaxableSimulationRunner 전환. Gate 2d 5/5 PASS
  - SCHD 위탁: tax OFF p50=13.4억 vs ON p50=10.9억 (-23%)
  - 연금저축: pension_tax_info 2개 구간(55-70, 70-80세). IRP 에러없음.
- Phase 2e: split_sale_planner.py, backtest 종합과세 경고 + 분할매도 슬라이더 패널
  - 2천만 초과 시에만 노출. 1~20년 분할 시나리오 + 절감액 실시간 계산
- Phase 3: ISA 풍차돌리기 Runner 통일. isa_years_held 파라미터로 만기/중도해지 분기
- 전체 회귀: Gate 2a/2b 4+4 + scenario_data 20 = 28/28 PASS

_작성: Claude_

---

## [2026-05-28] feature | Track C Phase 9+10 완료 — UI 경고 + 단위테스트

- Phase 9 UI Warning:
  - `calculator.html` synthWarningBanner + renderResult 배너 로직 (calculator.js)
  - `backtest.html` btUseSyntheticCheck 체크박스 + use_synthetic payload + renderBacktest 배너
  - 가상 데이터 사용 시 ticker별 날짜/행수 표시, 참고용 경고 안내
- Phase 10 Unit Tests: `tests/test_scenario_data_preparer.py` 20/20 PASS
  - _calc_rolling_cases, _data_confidence, allow_synthetic=False/True 전 경로 커버
- 커밋: 493d856 (push 대기)
- SYNTHETIC_DATA_INTEGRATION_PLAN.md Phase 0~10 전부 완료

_작성: Claude_

---

## [2026-05-28] rule | Wiki 작성자 서명 규칙 도입

- README.md에 서명 규칙 명문화: log.md 항목 끝 `_작성: Claude/Codex/오너_`, 테이블 셀 `(Claude)`, 계획 문서 섹션 끝 `_검토/추가: Codex, YYYY-MM-DD_`
- Codex가 ETF_BACKFILL_ARCHITECTURE_PLAN.md에 추가한 `Codex Review Notes` 섹션 검토 → 내용 타당, 승인
- 기존 Codex/Claude 추가 섹션에 소급 서명 적용

_작성: Claude_

---

## [2026-05-28] feature | Track B 완료 — Gate 2c PASSED

- Gate 2c 검증 스크립트 작성: `tests/gate_2c_verify.py` (781f89a)
- G5/G6 전 케이스 로컬 실행 PASS:
  - SCHD 위탁: tax OFF 3,750만 / tax ON 7,125만 (+90%)
  - 458730(TIGER) 위탁: tax OFF 4,125만 / tax ON 7,500만 (+81.8%)
  - SCHD 종합과세 경계: tax OFF 9,375만 / tax ON 16,875만 (+80%)
- SCHD vs TIGER 차이: ~10% (Track A 이전 대비 대폭 수렴)
- 블로커 전부 해소. 다음: Track C 또는 Track D

_작성: Claude_

---

## [2026-05-28] plan | ETF_BACKFILL_ARCHITECTURE_PLAN 단일종목 레버리지/규제완화 대응 추가

- `### Leveraged / Inverse ETFs` 섹션 확장: 광지수/단일종목/인버스 별 policy + 등급 명시
- 신규 섹션 `### Regulatory Expansion ETFs (2025~ Korean Market)` 추가
  - 트리거: 신규 ETF → `etf_proxy_map` 조회 → 없으면 `needs_review` (코드 수정 불필요)
  - 단일종목 레버리지(삼성/SK하이닉스/TSLA 2X 등), 테마, 커버드콜, 버퍼형 등 분류표
  - 핵심 원칙: 새 ETF 추가 = `etf_proxy_map` 행 삽입, `backfill_engine.py` 수정 금지
- `Priority ETF Families`에 Korean Single-Stock Leveraged/Inverse 패밀리 추가

_작성: Claude_

---

## [2026-05-27] ingest | 창업계획서.pdf + 5개 개발 계획서

**소스:**
- `창업계획서.pdf` — 사업계획서 (대학원생 Tech-up 창업동아리)
- `PROJECT_MASTER_ROADMAP.md` — 전체 개발 로드맵 조율 문서
- `PHASE4_PLAN.md` — 제품 기능 로드맵 (5개 그룹: 검색/내자산/홈/계산기/인프라)
- `세금에서시작된완전리팩토링계획.plan.md` — 세금·시뮬 정확도 리팩토링
- `ETF_BACKFILL_ARCHITECTURE_PLAN.md` — ETF 데이터 백필 아키텍처
- `SYNTHETIC_DATA_INTEGRATION_PLAN.md` — 합성 데이터 통합 계획

**생성된 페이지:**
- `wiki/overview.md`
- `wiki/product/features.md`
- `wiki/product/dev-status.md`
- `wiki/business/competitors.md`
- `wiki/business/target-users.md`
- `wiki/business/revenue-model.md`
- `wiki/index.md`
- `wiki/log.md` (이 파일)

**핵심 인사이트:**
- 현재 최대 블로커: SCHD vs TIGER 미국배당다우존스 데이터 불일치 → ETF 백필 데이터 품질 문제
- 대부분 계산기 기능은 완료됨. 세금 정확도 + 데이터 품질이 현재 핵심 과제
- 사업계획서 기준 런칭 목표: 2026년 11월 앱스토어 배포

---

## [2026-05-28] feature | US ETF 리스트 162개 → 4593개 확장

- ETFdb.com API로 전체 수집 (4595개 중 4593개, 중복 2개 제외)
- symbol_master.db 업데이트 (전체 심볼 15,008개)
- MSTY(YieldMax), JEPI, JEPQ 등 신규 인기 ETF 포함
- 카테고리: US Equity / Fixed Income / Commodity / Real Estate / Multi-Asset 등
- 커밋: ec788da

---

## [2026-05-27] feature | 홈화면 가격불러오기 안정성 및 정시성 추가

- market_quote_service: Redis SETNX 락으로 thundering herd 방지 (캐시 만료 시 yfinance 중복 호출 차단)
- tasks.py: refresh_krx_gold Celery Beat 태스크 추가
- celery_app.py: beat_schedule 추가 (평일 16:30 KST = 07:30 UTC 자동 실행)
- deploy/domino-celery-beat.service: systemd Beat 서비스 파일 repo에 추가
- deploy.yml: 배포 시 Beat 서비스 자동 등록/재시작 (이후 수동 SSH 불필요)
- KRX 금현물은 장 마감 후에만 당일 데이터 생성됨 (API 특성)

---

## [2026-05-28] feature | Track A Step 4~8 완료

- Step 4: KOSDAQ150→KQ150 매핑, KQ150 6284행(KODEX229200←^KQ11) index_master.db 저장 (40696f5)
- Step 5: index_loader_develop.py _fetch_fred() def 선언 누락 1줄 수정 (e1a4d6e)
- Step 6: PriceLoader 백필 실패 시 _backfilled_codes에 추가 안 하도록 수정, _backfill_skip_codes 분리 (a761750)
- Step 7: backfill_engine 인덱스 100행 미만 시 거부 (index_insufficient) (e33eeeb)
- Step 8: dividend_simulator._calc_div_stats() yield/freq 계산 시 현재 미완료 연도 제외 (ec56455)

---

## [2026-05-28] feature | Track A Step 2-3: DJUSDIV_PROXY 프록시 체인 구축

- 문제: DJUSDIV100 index_master.db에 1행뿐 (2026-03-18) → DJ 배당 ETF 백필 불가
- ^DJDVP (Yahoo Finance) 역사 데이터 미지원 확인
- 해결: SCHD(2011~) <- SDY(2005~) <- DVY(2003~) <- ^GSPC(1928~) adj close 체인 구성
- SCHD/SDY/DVY 상관계수: SDY 0.948, DVY 0.937 (SCHD 기준)
- scripts/build_djdiv_proxy.py 생성, DJUSDIV_PROXY 24,714행 index_master.db 저장
- backfill_engine.py: DJ_US_DIVIDEND -> DJUSDIV_PROXY, _NO_DIVIDEND_INDICES 추가
- us_etf_list.csv: SCHD->Dividend, VIG/DVY/SDY/etc->Dividend Growth, JEPI/JEPQ->Covered Call
- 458730/446720/402970 재백필 성공, 접합점 연속성 확인
- Step 9 선행 검증: price_return_mean 4종(SCHD/TIGER/ACE/SOL) 9.61~9.63% 수렴 확인
- 커밋: 7b1dc6f

---

## [2026-05-27] bugfix | 배당금 계산기 세션 메모 wiki 갱신
이 세션의 기억을 바탕으로 wiki를 갱신함. 확실히 확인된 내용만 반영:
- 목표 배당금 계산기 9.4억 폭증 버그 수정 기록.
- 한국 ETF 가격 로더에서 pykrx fallback 제거 및 yfinance 사용 결정 기록.
- 월납입금 자동 역산 5년 역전 버그 수정 기록.
- KODEX 미국배당다우존스 그래프 개형 볼록함 수정 기록.
- 기간 자동 역산 범위 1~70년 확장 기록.
- 은퇴 시뮬레이션 유사 문제는 확인 필요 항목으로만 기록.

---

## [2026-05-28] decision | Codex ETF 백필 자동화 검토 반영

- `ETF_BACKFILL_ARCHITECTURE_PLAN.md`에 `Codex Review Notes: Automation Risks and Practical Rollout` 섹션 추가.
- 판단: 프록시 매핑 자동화는 완전 자동 정답 선택기가 아니라, 자동 후보 제안 + 검증된 좁은 패밀리만 자동 승인 + 나머지는 `needs_review`로 멈추는 운영 시스템이어야 함.
- 주요 우려:
  - `underlying_symbol`이 비어 있거나 불완전하면 단일종목/레버리지 자동화의 입력으로 사용할 수 없음.
  - 이름/카테고리 기반 추론은 triage에는 유용하지만 최종 프록시 근거로는 위험함.
  - 커버드콜, 테마/액티브, missing-underlying 레버리지 상품은 명시적 reject 정책이 먼저 필요함.
  - provenance 없이 ETF 타입을 넓히면 잘못 생성된 장기 히스토리를 audit/delete/regenerate 하기 어려움.
- 현실적 단계:
  1. diagnostics
  2. provenance tables
  3. minimal `etf_proxy_map`
  4. `BackfillEngine` reads `etf_proxy_map` first
  5. explicit reject policies
  6. reviewed-underlying daily-reset leverage
  7. selected-family holdings/regression
  8. bond/covered-call models later
- 서명: Codex가 이 부분을 검토하고 수정함.

---

## [2026-05-30] feature | Track G G1 투자계산기 다중 계좌 엔진 1차 구현

- 신규 `modules/simulation/multi_account_loop.py`: `MultiAccountSimulationLoop` 추가. transfers OFF 상태에서 N개 계좌를 같은 날짜 루프로 운용하고 일별 합산 총액 기록.
- 신규 `modules/retirement/multi_account_analyzer.py`: `MultiAccountAnalyzer` 추가. 공유 윈도우 기반 롤링 실행, 시나리오별 combined_i 합산 후 분포 계산, price_provider 주입 지원.
- `calculator_logic.py`: `accounts` 배열이 2개 이상이면 다중 계좌 경로 사용. 계좌 1개는 기존 단일 경로 유지.
- `templates/calculator.html` / `static/js/calculator.js`: 기존 taxAccounts %분할 UI를 계좌별 초기자본·월적립금·종목·비중·유형 독립 입력 UI로 교체. 배당금 탭은 미변경.
- 테스트: `tests/test_track_g_multi_account.py` L0~L3 4/4 PASS, 기존 Gate 2a/2b/2c 12/12 PASS, JS syntax PASS, 브라우저 UI 스모크 PASS.

_작성: Codex_
