# Project Master Roadmap

Last updated: 2026-05-24

## Purpose

This file is the thin command document for the project. It does not replace the detailed plans. It tells future maintainers and AI agents which plan owns which work, what the current execution state is, and what should happen next.

Do not merge the detailed plans into one giant document. Keep them separate and use this file as the coordination layer.

## Source Plans

| File | Role | Status |
|---|---|---|
| `PHASE4_PLAN.md` | Product feature roadmap: search, symbol pages, my assets, home, sharing, UX, advanced calculators, synthetic-data checkbox idea | Partially completed |
| `세금에서시작된완전리팩토링계획.plan.md` | Tax and simulation-core correctness roadmap: TaxProfile, TaxSessionState, TaxableSimulationRunner, gates by screen | Phase 2c implemented, Gate blocked by data/backfill issue |
| `ETF_BACKFILL_ARCHITECTURE_PLAN.md` | Long-term ETF backfill and data provenance architecture | New architecture plan, not implemented |
| `SYNTHETIC_DATA_INTEGRATION_PLAN.md` | Opt-in synthetic data support and common data preparation facade for calculator/backtest/portfolio tabs | New integration plan, not implemented |

## Current Situation

The project was moving through PHASE4 product work and then shifted into a tax/simulation correctness refactor.

Completed or mostly completed:

- PHASE4 search/symbol UI items such as A1, A2, A3, A5.
- PHASE4 A6 crypto data addition.
- PHASE4 B2 my-assets basics, plus B5 rebalancing validation.
- PHASE4 C3 market-index chart linkage and C5 sharing.
- PHASE4 D3 tax settings UI.
- Tax Phase 1 common tax core and liquidation correctness.
- Tax Phase 2a TaxableSimulationRunner for backtest.
- Tax Phase 2b AccumulationAnalyzer/calculator accumulation runner migration.
- Tax Phase 2c dividend reverse-calculation runner migration appears implemented.

Current blocker:

- During Phase 2c verification, `SCHD` and `TIGER 미국배당다우존스(458730)` produced materially different dividend-target results under same assumptions.
- Investigation indicates this is primarily a data/backfill/synthetic-stats issue, not a tax-runner issue.
- Main causes:
  - `DJUSDIV100` index daily data is incomplete or too short.
  - Korean U.S. Dividend Dow Jones ETFs have short actual histories and fall into synthetic assumptions too quickly.
  - `DividendSimulator._calc_div_stats()` includes current incomplete year in price-return statistics.
  - Backfilled and synthetic rows both rely on weak `volume = 0` identification.
  - There is no provenance table for generated rows.

## Decision

Do not combine the four detailed plans into one massive plan. That would make maintenance harder and blur ownership.

Instead:

1. Keep each detailed plan focused.
2. Use this master roadmap to coordinate priority and dependencies.
3. Update this file when a track changes status or the next action changes.
4. Update the owning detailed plan when implementing work inside that domain.

## Dependency Order

High-level order:

```text
Tax Phase 2c implemented
  -> Backfill/data issue discovered
  -> Backfill Phase 0~1 stabilization
  -> Dividend stats short-history fix
  -> Phase 2c Gate revalidation
  -> Synthetic Data Integration facade/checkboxes
  -> Tax Phase 2d withdrawal tax
  -> Remaining PHASE4 advanced calculator items
  -> Backfill V2 long-term architecture
```

Rationale:

- Phase 2c cannot be trusted until SCHD/TIGER data differences are understood and bounded.
- Synthetic checkbox work depends on having a clean common data-preparation entry point.
- Backfill V2 is important but too large to block every other feature. Only its Phase 0~1 stabilization should be immediate.

## Immediate Tracks

### Track A. Data/Backfill Stabilization For Phase 2c Gate

Owner plan:

- `ETF_BACKFILL_ARCHITECTURE_PLAN.md`

Scope:

- Only Phase 0~1 and the immediately listed code issues.
- Do not start full U.S. ETF universe ingestion yet.
- Do not implement the full Backfill Engine V2 dispatcher yet.

Tasks:

1. Add or run a diagnostic report for current backfill state.
2. Confirm `DJUSDIV100` index daily range and source.
3. Repair/populate `DJUSDIV100` if a reliable source is available.
4. Add `KOSDAQ150 -> KQ150` mapping if still missing.
5. Fix `index_loader_develop.py` so `_fetch_fred()` is a real method.
6. Change `PriceLoader` so failed backfill attempts are not marked as completed in-session.
7. Add index sufficiency checks before backfill accepts a proxy.
8. Fix `dividend_simulator._calc_div_stats()` to exclude the current incomplete year from price-return statistics.
9. Re-run SCHD vs TIGER 미국배당다우존스 comparison.

Exit criteria:

- SCHD and Korean U.S. Dividend Dow Jones ETF no longer diverge merely because one has short actual history.
- If they still differ, the difference is explainable by fees, currency, dividend schedule, tax, or confidence grade.
- Phase 2c Gate can be evaluated without known bad data assumptions.

Suggested command phrase:

```text
마스터 로드맵의 Immediate Track A 진행해줘
```

### Track B. Phase 2c Gate Revalidation

Owner plan:

- `세금에서시작된완전리팩토링계획.plan.md`

Scope:

- Validate the already-implemented dividend reverse-calculation runner migration after Track A.
- Do not add new product features here.

Tasks:

1. Re-run Gate 2c cases.
2. Confirm tax ON produces lower net dividend outcome than tax OFF.
3. Confirm tax OFF behavior is reasonably close to pre-Phase-2c output after data fixes.
4. Confirm performance/caching has not regressed materially.
5. Update tax plan status from "Gate revalidation blocked" to "Gate 2c passed" if successful.

Exit criteria:

- Gate 2c passes and is documented.
- If it fails, the cause is categorized as tax logic, data logic, or performance.

Suggested command phrase:

```text
Phase 2c Gate 재검증해줘
```

### Track C. Synthetic Data Common Entry Point

Owner plan:

- `SYNTHETIC_DATA_INTEGRATION_PLAN.md`

Scope:

- Implement common facade and opt-in checkbox for investment calculator and backtest/portfolio analysis.
- Do not rewrite `DividendSimulator` synthetic logic yet.
- Do not rewrite withdrawal in-memory synthetic cases yet.

Tasks:

1. Add `modules/data_preparation/scenario_data_preparer.py`.
2. Add `allow_backfill` and `allow_synthetic` flags to existing `DataPreparer`.
3. Integrate investment calculator backend with `use_synthetic`.
4. Add calculator UI checkbox and result warning.
5. Integrate backtest backend with `use_synthetic`.
6. Add backtest UI checkbox and result warning.
7. Refactor retirement logic to call facade while preserving behavior.

Exit criteria:

- Synthetic data is off by default in new tabs.
- Results clearly warn when synthetic data was used.
- Retirement behavior remains stable.
- API responses expose `used_synthetic`, `synthetic_info`, `backfilled`, and `warnings`.

Suggested command phrase:

```text
SYNTHETIC_DATA_INTEGRATION_PLAN Phase 1부터 진행해줘
```

### Track D. Tax Phase 2d And Later

Owner plan:

- `세금에서시작된완전리팩토링계획.plan.md`

Scope:

- Continue tax runner migration after Phase 2c Gate passes.

Tasks:

1. Phase 2d: withdrawal tax injection.
2. Phase 2e: financial-income comprehensive tax warning and split-sale planner.
3. Phase 3: cleanup, ISA runner unification, docs.

Exit criteria:

- Gate 2d and Gate 5 pass.
- Tax behavior is unified across screens.

Suggested command phrase:

```text
세금 Phase 2d 진행해줘
```

### Track E. PHASE4 Product Work

Owner plan:

- `PHASE4_PLAN.md`

Scope:

- Product UX and feature backlog.
- Avoid simulation-core changes unless they are coordinated through the tax/data tracks.

Recommended next PHASE4 items after data/tax unblock:

- D6 synthetic data checkbox work should follow Track C.
- D4 fee/slippage should wait until runner pipeline is stable.
- D1/D2 retirement extensions should wait until Phase 2d withdrawal tax is done.
- C4 onboarding should remain late-stage, after major feature surfaces stabilize.

Suggested command phrase:

```text
PHASE4 다음 안전한 항목 진행해줘
```

## Do Not Do Yet

Do not do these until the immediate blocker is resolved:

- Do not merge the four plan files into one large document.
- Do not implement full U.S. ETF universe ingestion yet.
- Do not rewrite all synthetic logic in one pass.
- Do not delete legacy `volume = 0` rows without a migration/provenance plan.
- Do not continue tax Phase 2d assuming Phase 2c Gate is clean.
- Do not treat synthetic data as factual historical data in UI.

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

Proceed with Track A.

Reason:

- It directly addresses the SCHD/TIGER dividend discrepancy.
- It unblocks Phase 2c Gate revalidation.
- It is smaller than full Backfill V2.
- It reduces risk before adding synthetic-data checkboxes to more tabs.

Next prompt to use:

```text
마스터 로드맵의 Immediate Track A 진행해줘
```
