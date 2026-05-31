# Project Master Roadmap

Last updated: 2026-05-31 (✅ 배당 백필 Stage A + Stage B(채권/MMF·환헤지·US 채권 자동분류·통화가드) 서버검증 완료, Phase 2c 재검증 완료 → 다음=금융소득 종합과세 완전 구현(세금 Phase 2e 배선 + `_ytd_income` 주입))

> ⚠️ **2026-05-30 정정:** 아래 "SCHD vs TIGER now converge" / "Phase 2c Gate 통과" / "Track A 완료"는 **가격(CAGR) 수렴만** 검증된 것이었음. `debug_dividend.py` 실측 결과, 배당 **액수**는 0임이 확인됨. 원인: Track A가 DJUSDIV_PROXY를 total-return(adj-close)로 구축 → 가격은 맞지만 배당이 가격에 임베딩되어 itemize 안 됨. 백필 가격 구간(1928~)에 배당 row 없음 + provenance 전부 0행. **이는 세금 Phase 2c(배당 역산)·2e(금종세)·Track G(다중계좌 세금)의 데이터 기반을 무효화한다.** 해결 owner: `ETF_BACKFILL_ARCHITECTURE_PLAN.md § Phase 6.0`(범용 배당 백필 재설계). 우선순위는 아래 "Current Recommended Next Action" 참조.

## Purpose

This file is the thin command document for the project. It does not replace the detailed plans. It tells future maintainers and AI agents which plan owns which work, what the current execution state is, and what should happen next.

Do not merge the detailed plans into one giant document. Keep them separate and use this file as the coordination layer.

## Source Plans

| File | Role | Status |
|---|---|---|
| `PHASE4_PLAN.md` | Product feature roadmap: search, symbol pages, my assets, home, sharing, UX, advanced calculators, synthetic-data checkbox idea, server price-cache retention policy | Partially completed (A1/A2/A3/A5/A6/B5/C3/C5/D3 done) |
| `세금에서시작된완전리팩토링계획.plan.md` | Tax and simulation-core correctness roadmap: TaxProfile, TaxSessionState, TaxableSimulationRunner, gates by screen | Phase 1~3 + 2c/2d 완료. 🔴 **다음 = 금융소득 종합과세 완전 구현(Phase 2e 배선 + phase1-api).** 엔진 수학은 완료, 갭 = `other_financial_income` 자동산출·전탭배선·`_ytd_income` 주입(데이터 토대 완성돼 블로커 없음). |
| `ETF_BACKFILL_ARCHITECTURE_PLAN.md` | Long-term ETF backfill, data provenance architecture, and canonical server price-retention policy | ✅ **Phase 6.0 Stage A + Stage B 완료**(주식 배당 + 채권/MMF·환헤지비용·US 채권 키워드 자동분류·통화가드, 서버검증). Phase 3+ (etf_master, etf_proxy_map, confidence grading)는 이후. |
| `SYNTHETIC_DATA_INTEGRATION_PLAN.md` | Opt-in synthetic data support and common data preparation facade for calculator/backtest/portfolio tabs | ✅ Complete (Phase 1~10, all screens). |
| `isafix.md` | Korean regulatory compliance: account-type investment restrictions (ISA/연금저축/IRP), ISA contribution limits, ISA windmill block, COMMODITY_ETF classification for IRP | **Backend complete (e8b7c1e). Frontend partially done. BUG-1~5 remain.** |
| `PHASE4_PLAN.md § 4G` | Multi-account simulation engine + real ISA windmill (sequential/conditional flow). Requires Track F first. Key constraint: percentiles must be computed after per-scenario sum, not by summing individual percentiles. | Not started. Requires Track F first. |

## Current Situation

✅ **배당 데이터 근본 버그의 Stage A 조치 완료 (2026-05-30).** DJUSDIV_PROXY를
price-return 체인으로 재구축하고 SCHD/458730/446720/402970에 명시적 배당을 주입했다.
서버에서 `stage_a_verify.py`, `debug_dividend.py`, 계산기 직접 실행으로 배당 p50 > 0과
UI 실측/추정 필드를 확인했다.

✅ **2026-05-31 추가 완료:** ① ^GSPC(S&P500) 백필 제거 → proxy 2003 시작(SCHD 배당전략 미대표).
② Phase 2c 재검증 완료(Gate 2c PASSED 3/3, 양 계산기 SCHD≈458730 수렴, 2e 엔진 `tax_truth_test`
64/64). ③ 배당역산 SCHD≠458730 4x버그 수정(`dividend_simulator` 3단 폴백 + 휴리스틱 결정화,
[[dev/bugs]] BUG-DIV-1). ④ 배당계산기 UX(확률 슬라이더 50% 기본 + p25~p75 분포). ⑤ 투자계산기
가상데이터 보충(use_synthetic 체크 시 윈도우별 독립 합성 TARGET=40). 현재 위치 = **Stage B 착수 직전.**

현재 위치 (한눈에):
- ✅ **완료:** 배당 백필 Stage A + ^GSPC 제거(2003) — `ETF_BACKFILL § Phase 6.0 Stage A`
- ✅ **완료:** 배당 백필 Stage B(채권/MMF) — 한국 채권 전유형·환헤지비용·US 채권 자동분류·통화가드, 서버검증 — `ETF_BACKFILL § Phase 7 addendum`
- ✅ **완료:** 세금 Phase 2c 재검증 (2e 엔진 검증 완료, 2e 배선 갭은 빌드 잔여)
- 🔴 **지금/다음:** 금융소득 종합과세 완전 구현(세금 Phase 2e 배선 + phase1-api `_ytd_income` 주입) — 데이터 토대 완성, 블로커 없음
- ⏸️ **대기:** Track G(다중계좌 세금) — G1 ✅, 후속 ②커서 ③UI

완료 (가격/구조 레벨 — 단, 배당 액수 정확성은 별개):

- ✅ Tax Phase 1~3, Phase 2a/2b/2d — Gates passed. 종합과세 **계산 엔진**도 완전(단위검증 OK).
  ⚠️ **2c: 재검증 필요**(배당 데이터 의존). ⚠️ **2e: 부분 구현** — 백테스트만 배선, 기존
  금융소득 자동산출·전탭 배선·`_ytd_income` 주입 미완. Stage A 완료 후 정상 배당 데이터 기준 재검증 필요.
- ✅ Track A/Stage A: DJUSDIV_PROXY raw-close price-return 재구축 + 배당 분리 주입 완료.
- ⚠️ Track B: Phase 2c Gate "passed" — 가격 기준. 배당 정상화 후 재검증 대상.
- ✅ Track C: Synthetic data integration complete across all screens (Phases 1~10).
- ✅ ETF_BACKFILL Phase 0~2 provenance 스키마는 Stage A 백필 가격/배당 기록에 사용됨.
- ✅ PHASE4: A1/A2/A3/A5/A6/B5/C3/C5/D3 done.

Current blocker: **없음.** 배당 Stage A/B + Phase 2c 재검증 완료. 다음 = **금융소득 종합과세 완전 구현**(2e 배선 + `_ytd_income` 주입). (2026-05-31 갱신)

## Decision

Do not combine the four detailed plans into one massive plan. That would make maintenance harder and blur ownership.

Instead:

1. Keep each detailed plan focused.
2. Use this master roadmap to coordinate priority and dependencies.
3. Update this file when a track changes status or the next action changes.
4. Update the owning detailed plan when implementing work inside that domain.

## Data Storage Policy Decision

Decision recorded on 2026-05-28:

- Server-side price history remains canonical.
- Client-side storage may be added later only as a UX edge cache for charts, search, and recently viewed market summaries.
- Do not move API keys, canonical historical prices, backfill provenance, or synthetic-data confidence decisions to user devices.
- Long-term server storage should be bounded by a metadata-driven retention policy:
  - `core_permanent`: indices, FX, KRX gold, core benchmark ETFs/stocks, app examples.
  - `protected_user_asset`: holdings, saved portfolios, home watchlists, favorites, active presets.
  - `user_requested_cache`: search/detail/calculator/backtest/myassets fetches, kept by last access and evicted only after dry-run review.
  - `generated_history`: backfilled/synthetic rows, deleted only through provenance such as `run_id`, `model_version`, `source_type`, or confidence.
  - `transient_quote`: Redis/in-memory quote cache with short TTL.

Owner plans:

- Full architecture and deletion guardrails: `ETF_BACKFILL_ARCHITECTURE_PLAN.md` → `Price Data Retention And Client Cache Policy`.
- Product/infrastructure task: `PHASE4_PLAN.md` → `E4. 서버 가격 데이터 보존 정책`.

Implementation rule:

Do not implement client-canonical storage. First implement server diagnostics, `price_cache_meta`, protected-code resolution, and dry-run cleanup. Add client IndexedDB/mobile cache only after the server policy is stable.

## Dependency Order

```text
✅ Tax Phase 1~3 + 2a/2b/2d
✅ Track C: Synthetic data 전 화면 완료
✅ Track F: ISA 규제 정합성 (BUG-1~5 해결)
✅ Track G G1: 다중계좌 투자계산기 탭 (구조/가격)
✅ PHASE4 부분 완료: A1/A2/A3/A5/A6/B5/C3/C5/D3
✅ ETF_BACKFILL Stage A: price-return + 명시 배당으로 SCHD/458730/446720/402970 서버 적용

현재 위치 ↓

[1] 🔁 세금 Phase 2c(배당 역산)/2e(금종세) 재검증 — 정상 배당 데이터로  ← 지금

[2] 🔴 배당 백필 Stage B (채권/MMF, 필수) — ETF_BACKFILL § Phase 7
    → 금리 수치 → 듀레이션 가격 모델 + 쿠폰을 분배금으로 명시 주입

[3] ⏸️ Track G 재개 (세금 재검증 후)
    → G1 후속: ② 입력 커서 유실 ③ UI 통일 (① 배당 0은 Stage A로 해소)
    → 은퇴/백테스트 탭 확장 → G2 자금이동 → G3 ISA→연금 이전

[5] ETF_BACKFILL V2 Phase 3+: etf_master/etf_proxy_map, confidence A~F, 전체 US 유니버스

[6] PHASE4 핵심 기능: D1/D2/B1/A4/C1/C2/B4

[7] E1 모바일 / E2~E4 최적화 / C4 온보딩 (마지막)
```

**핵심 규칙:**
- Track G 퍼센타일: 시나리오 i마다 `combined_i = Σ account_i` → 그 분포에서 p10/p50/p90. 계좌별 퍼센타일 덧셈 금지.
- ISA + US_DIRECT 조합: Track F 완료 후 모든 시뮬에서 hard error.
- ETF_BACKFILL V2: 블로킹 아님이지만 영구 보류도 아님 — Track G 이후 병행 진행.

## Immediate Tracks

### Track A. Data/Backfill Stabilization ✅ COMPLETE

Owner plan: `ETF_BACKFILL_ARCHITECTURE_PLAN.md`

Completed 2026-05-28: DJUSDIV_PROXY chain, KQ150 mapping, _fetch_fred() fix, PriceLoader backfill-failure bug, index sufficiency check, div_stats incomplete-year fix. SCHD vs TIGER now converge.

---

### Track B. Phase 2c Gate Revalidation ✅ COMPLETE

Owner plan: `세금에서시작된완전리팩토링계획.plan.md`

Completed 2026-05-28: Gate 2c passed. G5/G6 all cases PASS.

---

### Track C. Synthetic Data Common Entry Point ✅ COMPLETE

Owner plan: `SYNTHETIC_DATA_INTEGRATION_PLAN.md`

Completed 2026-05-28: All phases 1~10 done. Synthetic checkbox + warning banners on all screens.

---

### Track D. Tax Phase 2d And Later ✅ COMPLETE

Owner plan: `세금에서시작된완전리팩토링계획.plan.md`

Completed 2026-05-28:
- Phase 2d (withdrawal tax injection): Gate 2d PASSED 5/5.
- Phase 2e (comprehensive tax warning + split-sale panel): done.
- Phase 3 (ISA runner unification): done.

### Track F. ISA/Account Regulatory Compliance

Owner plan: `isafix.md`

**Status: Backend complete, frontend partially done. Remaining: BUG-1~5.**

Completed (e8b7c1e, 2026-05-29):
- ✅ `COMMODITY_ETF` classification in `base_tax.py`
- ✅ IRP COMMODITY_ETF block in `account_tax.py`
- ✅ `validate_isa_contribution()` in `account_tax.py`
- ✅ Full validation in `calculator_logic.py`, `retirement_logic.py`, `dividend_logic.py`
- ✅ Error banners in `calculator.html` + `calculator.js`

All BUG-1~5 resolved (2026-05-30):
- ✅ BUG-1: TF1 계열 popup → banner fix (f35a611)
- ✅ BUG-2: retirement.html 배너 확인 — 이미 존재, BUG-1 fix로 해결
- ✅ BUG-3: 은퇴 계산기 연금 수령 시작 나이 입력 추가
- ✅ BUG-4: ISA 1억 캡 납입 중단 방식으로 재설계 (7dd75a4)
- ✅ BUG-5: 밴드 슬라이더 숫자 직접 입력 추가

Exit criteria (original — partially met):
- ISA + SPY → hard error ✅
- IRP + commodity ETF → hard error ✅
- 연금저축 + commodity ETF → passes ✅
- ISA contribution limits → hard error ✅
- ISA windmill → hard error ✅
- ISA total > 1억 → 납입중단 방식 캡 + orange banner ✅ (BUG-4 재설계 완료)

✅ 2026-05-30: 에러 팝업→배너 미관, T-B3 목표비중 계정연동 해결. Track F의 배당 0 블로커는 Stage A로 해소, 세금 재검증 필요.

### Track E. PHASE4 Product Work (진행 중)

Owner plan: `PHASE4_PLAN.md`

**완료:** A1/A2/A3/A5/A6/B5/C3/C5/D3 + F1/B2-b/B2-c/B3/D5

**남은 항목 (의존성 없음):**

| 항목 | 난이도 | 선행 조건 |
|------|--------|-----------|
| D4 거래수수료 설정 | 1~2일 | 없음 |
| B2-a 홈 화면 자산 토글 | 0.5일 | 없음 |
| D6 합성 데이터 백테스트 체크박스 | 1~2일 | Track C ✅ |

**Track G 이후 또는 병렬 가능:**

| 항목 | 난이도 | 선행 조건 |
|------|--------|-----------|
| B1 포트폴리오 즐겨찾기/저장 | 2~3일 | 없음 |
| A4 종목 상세 개선 + 캔들차트 | 3~4일 | 없음 |
| D1 TDF 기능 | 3~4일 | Tax 2d ✅ |
| D2 연금 통합 계산기 | 4~5일 | Tax 2d ✅ |
| C1 홈 화면 watchlist | 2~3일 | 없음 |
| C2 자산군별 수익률 비교 | 2~3일 | 없음 |

**나중에 (선행 의존성 있는 것들):**

| 항목 | 난이도 | 선행 조건 |
|------|--------|-----------|
| B4 거래트래킹 + 추가매수 고도화 | 3~4일 | B2/B3 |
| E1 모바일 반응형 | 5~7일 | 전체 기능 안정화 후 |
| C4 온보딩 튜토리얼 | 1~2주 | B4 + 전체 |
| E2/E3/E4 최적화/캐시 | 1~3일 | 트래픽 확인 후 |

Suggested command phrase:

```text
PHASE4 다음 안전한 항목 진행해줘
```

## Do Not Do Yet

- Do not merge the plan files into one large document.
- Do not delete legacy `volume = 0` rows without provenance (`run_id`/`model_version`) — 마이그레이션 계획 없이 삭제 금지.
- Do not make client devices the canonical price-history store. `price_cache_meta` + dry-run cleanup 구현 전까지 클라이언트는 캐시 전용.
- Do not add automatic server price-history deletion before dry-run report reviewed.
- Do not treat synthetic data as factual historical data in UI.
- Do not start Track G before Track F is complete.
- Do not sum percentiles across accounts in Track G — sum per-scenario first, then compute percentiles on the combined distribution.

## Status Update Rules

When work is completed:

1. Update this `PROJECT_MASTER_ROADMAP.md` if it changes priority or track status.
2. Update the owning detailed plan with exact status and Gate result.
3. If code changed, mention the relevant files and tests in the final response.
4. If a Gate is blocked, record the blocker under the owning plan and this roadmap.

## AI Execution Protocol

Every AI agent or maintainer continuing this project must treat this section as the operating protocol.

Before starting any track:

1. Read this `PROJECT_MASTER_ROADMAP.md`.
2. Read the owner plan listed under the target track.
3. Confirm the current blocker, dependency order, and exit criteria.
4. Check whether the requested work skips a required dependency.
5. If the requested work conflicts with the dependency order, explain the conflict before implementing.

During implementation:

1. Keep changes inside the active track unless a dependency forces a small supporting fix.
2. Do not silently expand scope into another major plan.
3. Record newly discovered blockers in the owner plan as soon as they affect the track outcome.
4. Preserve existing user work and avoid unrelated refactors.

After completing work:

1. Update `Last updated` in this roadmap.
2. Update the relevant track status in this roadmap.
3. Update `Current Recommended Next Action`.
4. Update the owner detailed plan with exact completed tasks, blocked tasks, and Gate result.
5. Add or update completion notes with changed files, verification commands, and results.
6. If verification could not be run, record why.
7. If a Gate fails, leave the track marked as blocked and write the concrete blocker.
8. If a Gate passes, mark the Gate as passed and advance the next recommended action.

Required completion note format:

```text
Completion note - YYYY-MM-DD
- Track:
- Status: completed | partially completed | blocked
- Changed files:
- Verification:
- Gate result:
- Remaining blockers:
- Next action:
```

## Current Recommended Next Action

> ⚠️ **우선순위 전환 (2026-05-30):** 배당 데이터 근본 버그 발견. Track G는 다중계좌 **세금**(금종세·배당) 시뮬이라 배당/세율 데이터가 정확해야 테스트·구현이 의미 있음. 현재 배당 액수가 0이라 Track G 진행은 검증 불가능한 토대 위에 쌓는 셈. **따라서 데이터 토대부터 고친다.**

**[★ 지금 — 다음 작업] 금융소득 종합과세 완전 구현 (세금 Phase 2e + phase1-tax-profile-api):**
데이터 토대(배당 Stage A + 채권 Stage B) 완성 → 더 이상 블로커 없음. 종합과세 **엔진 수학은
구현·단위검증 완료**(`base_tax._comprehensive_tax`/`after_tax_dividend`/`_comprehensive_extra_tax`,
2천만 임계). 남은 것 = **배선·데이터 갭 3종:**
- ① `other_financial_income` 자동산출 미구현 — `backtest_logic.py:117`이 수동값/0 fallback(plan 금지).
  case별 직전 완료년도 gross 배당·이자 자동집계 필요.
- ② 분할매도/종합과세 패널이 **백테스트 탭에만** 배선 — 계산기/배당/연금 `*_logic.py` 미배선.
- ③ `TaxedDividendEngine._ytd_income` **0 고정**(`account_tax.py:230`) — 기존 금융소득 미주입.
실행 지시: 「금융소득 종합과세 구현해줘」. 상세 갭 = `세금에서시작된완전리팩토링계획.plan.md` Phase 2e.

**[✅ 완료 2026-05-31] 배당 백필 Stage A + Stage B (채권/MMF):**
Stage A(주식 배당, price-return + 명시배당) + Stage B(한국 채권 전유형·환헤지비용·US 채권 키워드
자동분류·통화가드) 구현·서버검증 완료. 세금 Phase 2c 재검증 PASS(Gate 2c 3/3). 상세 =
`ETF_BACKFILL § Phase 7 완료 addendum` + `wiki/log.md`.

**[3] 세금 재검증 후 — Track G 재개:**
G1 후속 보완(② 입력 커서 유실 ③ UI 통일 — 배당 0(①)은 Stage A로 해소). 이후 은퇴/백테스트 탭 확장 → G2 자금이동.

**[5] 이후 — PHASE4 핵심/복잡한 기능:**
D1/D2/B1/A4/C1/C2/B4

**[6] 마지막 — 인프라/UX 마감:**
E1 모바일, E2/E3/E4 최적화, C4 온보딩
