# Project Master Roadmap

Last updated: 2026-05-30 (Track G G1 구현·검증 완료, 후속 보완 대기)

## Purpose

This file is the thin command document for the project. It does not replace the detailed plans. It tells future maintainers and AI agents which plan owns which work, what the current execution state is, and what should happen next.

Do not merge the detailed plans into one giant document. Keep them separate and use this file as the coordination layer.

## Source Plans

| File | Role | Status |
|---|---|---|
| `PHASE4_PLAN.md` | Product feature roadmap: search, symbol pages, my assets, home, sharing, UX, advanced calculators, synthetic-data checkbox idea, server price-cache retention policy | Partially completed (A1/A2/A3/A5/A6/B5/C3/C5/D3 done) |
| `세금에서시작된완전리팩토링계획.plan.md` | Tax and simulation-core correctness roadmap: TaxProfile, TaxSessionState, TaxableSimulationRunner, gates by screen | ✅ Phase 1~3 + 2d/2e all complete. All Gates passed. |
| `ETF_BACKFILL_ARCHITECTURE_PLAN.md` | Long-term ETF backfill, data provenance architecture, and canonical server price-retention policy | Phase 0~2 complete. Phase 3+ (etf_master, etf_proxy_map, full US ETF universe, confidence grading) — planned after Track G. |
| `SYNTHETIC_DATA_INTEGRATION_PLAN.md` | Opt-in synthetic data support and common data preparation facade for calculator/backtest/portfolio tabs | ✅ Complete (Phase 1~10, all screens). |
| `isafix.md` | Korean regulatory compliance: account-type investment restrictions (ISA/연금저축/IRP), ISA contribution limits, ISA windmill block, COMMODITY_ETF classification for IRP | **Backend complete (e8b7c1e). Frontend partially done. BUG-1~5 remain.** |
| `PHASE4_PLAN.md § 4G` | Multi-account simulation engine + real ISA windmill (sequential/conditional flow). Requires Track F first. Key constraint: percentiles must be computed after per-scenario sum, not by summing individual percentiles. | Not started. Requires Track F first. |

## Current Situation

All originally-blocking tracks are complete. No current blockers.

Completed (as of 2026-05-29):

- ✅ Tax Phase 1~3, Phase 2a/2b/2c/2d/2e — all Gates passed.
- ✅ Track A: DJUSDIV_PROXY chain built, KQ150 mapping added, div_stats incomplete-year fix, PriceLoader backfill-failure bug fixed, index sufficiency check. SCHD vs TIGER now converge.
- ✅ Track B: Phase 2c Gate revalidated and passed.
- ✅ Track C: Synthetic data integration complete across all screens (Phases 1~10).
- ✅ ETF_BACKFILL Phase 0~2: provenance DB (backfill_runs, price_daily_source, corporate_action_source), BackfillEngine integration.
- ✅ PHASE4: A1/A2/A3/A5/A6/B5/C3/C5/D3 done.

Current blocker: **None.**

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
✅ Tax Phase 1~3 + 2a/2b/2c/2d/2e (전 Gate 통과)
✅ Track A: backfill 안정화 (DJUSDIV_PROXY, KQ150, div_stats fix)
✅ Track B: Phase 2c Gate 통과
✅ Track C: Synthetic data 전 화면 완료
✅ Track D: Tax 2d/2e/3 완료
✅ PHASE4 부분 완료: A1/A2/A3/A5/A6/B5/C3/C5/D3

현재 위치 ↓

[1] Track F: ISA 규제 정합성 (isafix.md)
    ├─ [PARALLEL] PHASE4 빠른 항목들 (F1/B2-c/D4/D5/B2/B3)

[2] Track G: 다중 계좌 시뮬 엔진 (Track F 완료 후)
    → G1 rolling engine (시나리오별 합산 → 퍼센타일)
    → G2 ISA 풍차돌리기 (만기→2000만 재납입 + 나머지→위탁)
    → G3 ISA→연금 이전 옵션 (선택)

[3] ETF_BACKFILL V2 Phase 3+: 전체 아키텍처
    → etf_master 테이블, etf_proxy_map 정밀 매핑
    → confidence A~F 자동 분류
    → 전체 미국 ETF 유니버스 수집
    → 기존 volume=0 rows 마이그레이션
    (Track G와 병렬 진행 가능 — 데이터 품질 기반 시뮬 신뢰도 향상)

[4] PHASE4 핵심 기능: D1/D2/B1/A4/C1/C2/B4

[5] E1 모바일 반응형

[6] E2/E3/E4 최적화/캐시/데이터 보존

[7] C4 온보딩 (전체 기능 안정화 후 마지막)
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
- ISA total > 1억 → orange banner ⚠️ (캡 로직 재설계 필요, BUG-4)

Suggested command phrase:
```text
BUG-1,2,3,4,5 수정해줘
```

### Track E. PHASE4 Product Work (진행 중)

Owner plan: `PHASE4_PLAN.md`

**완료:** A1/A2/A3/A5/A6/B5/C3/C5/D3

**Track F와 병렬 가능 (의존성 없는 항목):**

| 항목 | 난이도 | 선행 조건 |
|------|--------|-----------|
| F1 대기 순위 UX 수정 | 0.5일 | 없음 |
| B2-c 내자산 현재가 캐싱 | 0.5일 | 없음 |
| D4 거래수수료 설정 | 1~2일 | 없음 |
| D5 인플레이션 검증 + 실질생활비 | 2~3일 | 없음 |
| B2 자산 추이 + 홈 토글 | 1~2일 | 없음 |
| B3 리밸런싱 경고 밴드 | 1일 | B2 |
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

**[1] 지금 — Track G G1 후속 보완:**
```text
trackG_multiaccount_plan.md "G1 후속 보완" 1번부터 수정해줘
```
G1 투자계산기 탭 구현·검증·배포 완료 (2026-05-30, b14ed44). L0~L3 + Gate 회귀 PASS. 남은 보완(중요도순): ① 다중계좌 배당 지표 0 버그(높음) ② 계좌 입력 커서 유실(중간) ③ 계좌 카드 UI 통일(낮음).

**[2] G1 보완 후 — 나머지 탭 확장:**
은퇴 → 백테스트 탭에 다중계좌 적용 (배당금 제외). 검증된 투자계산기 패턴 복제.

**[3] 그 다음 — Track G G2:**
```text
PHASE4_PLAN.md § 4G / trackG_multiaccount_plan.md G2 설계 정밀화해줘
```
자금이동 ON(분배 정책). G1 실제 코드 보고 시점별 트리거 설계 보강 후 착수. 퍼센타일 단순 덧셈 금지.

**[3] Track G와 병렬 — ETF_BACKFILL V2 Phase 3+:**
```text
ETF_BACKFILL_ARCHITECTURE_PLAN.md Phase 3부터 진행해줘
```
etf_master/etf_proxy_map 정밀 매핑, confidence A~F, 전체 미국 ETF 유니버스. 시뮬 데이터 신뢰도 근본적 개선.

**[4] 이후 — PHASE4 핵심/복잡한 기능:**
D1/D2/B1/A4/C1/C2/B4

**[5] 마지막 — 인프라/UX 마감:**
E1 모바일, E2/E3/E4 최적화, C4 온보딩
