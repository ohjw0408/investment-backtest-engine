# Synthetic Data Integration Plan

> **상태 (2026-05-30):** ✅ Phase 0~4 완료 (Track C, 2026-05-28) — `ScenarioDataPreparer` facade, `DataPreparer` allow_backfill/allow_synthetic 플래그, 투자계산기·백테스트 opt-in 체크박스 + 경고 배너. Phase 5~10(포트폴리오 분석, 은퇴 facade 전환, 배당 분리, provenance 정렬)은 💡 나중에.
>
> ⚠️ **혼동 주의:** 이 계획의 "합성 데이터"는 opt-in GBM 가격 생성(데이터 부족 시 사용자 선택). **배당 백필(`ETF_BACKFILL § Phase 6.0`)과 별개.** 합성은 완료, 배당 백필 Stage A도 서버 적용 완료. 채권/MMF Stage B는 후속.
>
> ✅ **2026-06-13 추가:** 배당 백필 Stage B(채권/MMF)도 완료(2026-05-31, 서버검증). **은퇴 탭 합성 체크박스**는 GAP-RET-KRDATA 해소(2026-06-11, 9486eee)로 추가 — 계산기·백테·은퇴 전 탭 opt-in 가능. 멀티계좌 합성 보충(가구 인출 GBM 폴백)도 동작. 종목 간 상관 복원은 `합성상관계수_plan.md`(구현 완료, 서버 실데이터 검증 대기).

## Purpose

This document defines a safe, incremental plan for adding optional synthetic data support to more application tabs while reducing duplicated synthetic-data logic.

The user wants synthetic data support in the investment calculator and portfolio/backtest analysis areas, but only as an explicit opt-in because synthetic data can contaminate results and reduce accuracy. The UI should expose a checkbox with a clear warning. The backend should use a common data preparation entry point so future backfill and synthetic-data architecture can be improved without rewriting every tab again.

This plan is intentionally incremental. Do not attempt to rewrite every analyzer at once.

## Core Decision

Create a common data preparation facade first.

Do not immediately merge every existing synthetic algorithm into one large replacement. Instead:

1. Add a shared entry point for scenario data preparation.
2. Internally reuse the existing `modules.retirement.data_preparer.DataPreparer` where possible.
3. Add opt-in synthetic support to the investment calculator and backtest/portfolio analysis tabs.
4. Keep retirement behavior stable.
5. Migrate dividend and withdrawal synthetic case generation later, after provenance and confidence handling exist.

This avoids a risky large-scale refactor while establishing the future architecture.

## Current State

There are currently three different synthetic-data patterns in the codebase.

### 1. DB-Level Synthetic Price Generation

Files:

- `modules/retirement/data_preparer.py`
- `modules/retirement/synthetic_price_generator.py`
- `modules/retirement/ticker_stats_cache.py`

Behavior:

1. `DataPreparer.prepare()` checks current data range.
2. If rolling cases are enough, it returns the existing data start.
3. If data is insufficient, it first tries `BackfillEngine.backfill()`.
4. If backfill fails, it computes monthly return statistics through `TickerStatsCache`.
5. It calls `generate_and_save()` from `synthetic_price_generator.py`.
6. Synthetic rows are written into `price_daily.db`.
7. Synthetic dividend rows may also be injected using observed dividend yield statistics.

Current consumers:

- Retirement full workflow.
- Retirement withdrawal-only workflow.
- Some synchronous routes in `app.py`.

Important limitation:

- Generated rows are stored with `volume = 0`, same as current backfilled rows.
- There is no robust provenance table yet.
- This means old generated rows cannot be cleanly separated by method.

### 2. In-Memory Synthetic Withdrawal Cases

File:

- `modules/retirement/withdrawal_analyzer.py`

Behavior:

1. Runs real rolling withdrawal cases.
2. If there are fewer than `MIN_CASES = 30`, it estimates monthly return statistics.
3. It generates synthetic withdrawal cases in memory.
4. These cases are not written to DB.
5. Cases are marked with `is_synthetic = True`.

Important limitation:

- Return statistics are based primarily on the first ticker.
- Dividends are not realistically modeled in synthetic cases.
- This logic is separate from `DataPreparer`.

### 3. Dividend Simulator Synthetic Rolling

File:

- `modules/dividend_simulator.py`

Behavior:

1. Runs real rolling dividend simulations.
2. If there are fewer than `MIN_CASES = 30`, it calculates dividend stats from actual data.
3. It generates synthetic last-year dividend outcomes in memory.
4. Results are not written to DB.

Important limitation:

- It is independent from `DataPreparer`.
- Short ETF histories can distort estimated price return and dividend assumptions.
- It does not share confidence/provenance with the rest of the system.

## Current Tab Coverage

| Feature / Tab | Current Backfill | Current DB Synthetic Data | Current In-Memory Synthetic Cases | Notes |
|---|---:|---:|---:|---|
| Retirement calculator | Yes | Yes, through `DataPreparer` | Withdrawal side can add cases | Most complete support |
| Withdrawal calculator | Yes | Yes, through `DataPreparer` | Yes | Two synthetic layers exist |
| Investment calculator | Yes, via `PriceLoader` auto backfill | No | No | Fails if requested years exceed available data |
| Backtest | Yes, via `PriceLoader` auto backfill | No | No | Loads requested date range directly |
| Dividend target calculator | Yes, via `PriceLoader` auto backfill | No | Yes, own logic | Separate synthetic model |
| Portfolio / my assets | Price/current-data focused | No | No | Needs clarification by route |

## Target User Experience

For investment calculator and backtest/portfolio analysis tabs, add an explicit opt-in control.

Suggested UI:

```text
[ ] Use synthetic data
    Use only when actual data is insufficient. Synthetic data is statistically generated and may reduce accuracy.
```

Korean UI copy:

```text
가상 데이터 사용
실제 데이터가 부족한 경우에만 선택하세요. 통계적으로 생성된 데이터가 포함되어 결과 정확도가 낮아질 수 있습니다.
```

Recommended behavior:

- Checkbox default: unchecked.
- If unchecked:
  - Use actual data and existing backfill only.
  - If data is insufficient, show the current data-shortage error.
- If checked:
  - Allow the backend to create or use synthetic data for missing history.
  - Show a result warning if synthetic data was used.
  - Return `synthetic_info` and `warnings` in the API response.

## Architectural Direction

Add a new common module:

```text
modules/data_preparation/
  __init__.py
  scenario_data_preparer.py
```

Primary public API:

```python
prepare_scenario_data(
    tickers: list[str],
    required_years: int | None,
    data_end: str,
    requested_start: str | None = None,
    step_months: int = 3,
    allow_backfill: bool = True,
    allow_synthetic: bool = False,
    purpose: str = "generic",
    price_db_path: str | Path | None = None,
    verbose: bool = False,
) -> dict
```

Suggested return shape:

```python
{
    "data_start": "YYYY-MM-DD",
    "data_end": "YYYY-MM-DD",
    "requested_start": "YYYY-MM-DD" | None,
    "effective_start": "YYYY-MM-DD",
    "n_cases": int | None,
    "backfilled": ["SCHD", "360750"],
    "synthetic_info": {
        "458730": {
            "date_from": "1964-05-04",
            "date_to": "2023-06-19",
            "rows_added": 12345,
            "div_rows": 200,
            "stats_basis": "2023-06-20 ~ 2026-05-22",
            "confidence": "D"
        }
    },
    "data_confidence": "actual" | "backfilled" | "synthetic",
    "used_synthetic": bool,
    "warnings": [
        "Synthetic data was used for 458730 from 1964-05-04 to 2023-06-19."
    ]
}
```

At first, this facade may call the existing retirement `DataPreparer`. Later it should call Backfill Engine V2 directly.

## Why A Facade First

The current code has working pieces but inconsistent entry points. A facade gives each tab a stable API now and a clean upgrade path later.

Current short-term implementation:

```text
Investment calculator
Backtest
Retirement
    -> ScenarioDataPreparer
        -> existing DataPreparer
            -> BackfillEngine
            -> TickerStatsCache
            -> SyntheticPriceGenerator
```

Future implementation:

```text
All tabs
    -> ScenarioDataPreparer
        -> BackfillEngineV2
            -> exact_index
            -> parent_etf
            -> holdings
            -> regression
            -> bond_duration
            -> synthetic
            -> no_backfill
```

Tabs should not know which internal method generated the data. They should only know whether synthetic data was used, what confidence applies, and what warning to show.

## Important Safety Rule

Do not generate synthetic data unless the user explicitly opts in for that workflow, except where existing retirement behavior already does so.

For new tabs:

- `allow_synthetic = False` by default.
- UI checkbox must be explicit.
- API payload must contain `use_synthetic: true`.
- Result must include warnings when synthetic data is used.

## Phase 0. Document And Diagnose Existing Behavior

Goal:

Make current synthetic behavior visible before changing it.

Tasks:

- Add comments or developer documentation identifying all synthetic paths:
  - `DataPreparer`
  - `SyntheticPriceGenerator`
  - `WithdrawalAnalyzer` in-memory synthetic cases
  - `DividendSimulator` synthetic rolling
- Add a small diagnostics helper later if needed:
  - count `volume = 0` rows by code
  - identify generated rows without provenance
  - identify codes with synthetic stats cache

Acceptance criteria:

- Developers can tell which code path generated synthetic data.
- No behavior change yet.

## Phase 1. Add `ScenarioDataPreparer`

Goal:

Create a common entry point without changing existing behavior.

Files to add:

```text
modules/data_preparation/__init__.py
modules/data_preparation/scenario_data_preparer.py
```

Initial design:

```python
from pathlib import Path
from modules.retirement.data_preparer import DataPreparer

def prepare_scenario_data(
    tickers,
    required_years=None,
    data_end=None,
    requested_start=None,
    step_months=3,
    allow_backfill=True,
    allow_synthetic=False,
    purpose="generic",
    price_db_path=None,
    verbose=False,
):
    ...
```

Behavior for initial version:

1. If `allow_synthetic` is true:
   - Use existing `DataPreparer.prepare()`.
   - This may backfill and may generate synthetic DB data.
2. If `allow_synthetic` is false:
   - Do not call synthetic generation.
   - It may still rely on existing `PriceLoader` auto-backfill behavior unless explicitly disabled later.
   - Return data range based on actual/backfilled DB data.
3. Always return normalized metadata:
   - `data_start`
   - `effective_start`
   - `backfilled`
   - `synthetic_info`
   - `used_synthetic`
   - `warnings`

Important:

- Existing `DataPreparer` does not currently separate `allow_backfill` and `allow_synthetic`.
- If necessary, extend `DataPreparer.prepare()` with optional flags:

```python
prepare(..., allow_backfill=True, allow_synthetic=True)
```

But keep default behavior unchanged for retirement.

Acceptance criteria:

- Existing retirement logic can call the facade and receive equivalent output.
- No UI changes yet.
- No synthetic data is generated when `allow_synthetic=False`.

## Phase 2. Add Flags To Existing `DataPreparer`

Goal:

Allow callers to request backfill without synthetic generation, or backfill plus synthetic generation.

Modify:

- `modules/retirement/data_preparer.py`

Add parameters:

```python
def prepare(
    self,
    tickers,
    sim_years,
    data_end,
    step_months=3,
    allow_backfill=True,
    allow_synthetic=True,
) -> dict:
```

Behavior:

- If `allow_backfill=False`, skip `BackfillEngine.backfill()`.
- If `allow_synthetic=False`, do not call `generate_and_save()`.
- If both are false, only report current data availability.
- Keep current retirement behavior by defaulting both to true.

Return additions:

```python
"used_synthetic": bool
"warnings": list[str]
"data_confidence": "actual" | "backfilled" | "synthetic"
```

Acceptance criteria:

- Retirement outputs remain compatible.
- Investment/backtest callers can safely ask for "no synthetic".
- Unit test can confirm no new `volume=0` rows are created when `allow_synthetic=False`.

## Phase 3. Investment Calculator Integration

Goal:

Add optional synthetic support to the investment calculator with minimal backend changes.

Current behavior:

- `calculator_logic.py` loads prices through `PriceLoader`.
- It computes `data_start`.
- If requested `years > max_years`, it raises a data shortage error.

New payload field:

```json
{
  "use_synthetic": true
}
```

Backend changes:

1. In `calculator_logic.py`, read:

```python
use_synthetic = bool(body.get("use_synthetic", False))
```

2. If `use_synthetic` is false:
   - Keep existing behavior.

3. If `use_synthetic` is true:
   - Call `prepare_scenario_data(...)` before computing `data_start`.
   - Use the returned `data_start`.
   - Continue into `AccumulationAnalyzer`.

Suggested call:

```python
prep = prepare_scenario_data(
    tickers=ticker_codes,
    required_years=years,
    data_end=datetime.date.today().strftime("%Y-%m-%d"),
    step_months=3,
    allow_backfill=True,
    allow_synthetic=use_synthetic,
    purpose="calculator",
)
```

Response additions:

```python
"data_start": data_start
"used_synthetic": prep["used_synthetic"]
"synthetic_info": prep["synthetic_info"]
"backfilled": prep["backfilled"]
"warnings": prep["warnings"]
```

Frontend changes:

- Add checkbox to calculator settings area:
  - Label: `가상 데이터 사용`
  - Hint: `실제 데이터가 부족한 경우에만 선택하세요. 통계적으로 생성된 데이터가 포함되어 결과 정확도가 낮아질 수 있습니다.`
- Send `use_synthetic`.
- If response has warnings, show a small warning panel near results.

Acceptance criteria:

- Default unchecked behavior is unchanged.
- Checked behavior can run longer simulations when actual data is short and synthetic generation succeeds.
- Result clearly indicates synthetic use.

## Phase 4. Backtest Integration

Goal:

Allow user-requested backtests to optionally fill missing early history with synthetic data.

Current behavior:

- `backtest_logic.py` receives `start_date` and `end_date`.
- It loads price data directly with `portfolio_engine.price_loader.load(tickers, start_date, end_date)`.

New payload field:

```json
{
  "use_synthetic": true
}
```

Policy:

- If unchecked:
  - Keep existing behavior.
  - If data is unavailable, fail or run only with available data according to current loader behavior.
- If checked:
  - Call `prepare_scenario_data(...)` with `requested_start=start_date`.
  - If synthetic data is generated, keep the user's requested `start_date`.
  - If synthetic data cannot be generated, return a clear error or warning.

Suggested call:

```python
prep = prepare_scenario_data(
    tickers=tickers,
    required_years=None,
    requested_start=start_date,
    data_end=end_date,
    step_months=3,
    allow_backfill=True,
    allow_synthetic=use_synthetic,
    purpose="backtest",
)
```

Implementation detail:

- Existing `DataPreparer` works in terms of `sim_years`, not arbitrary requested start.
- The facade should compute required years when `requested_start` is provided:

```python
required_years = ceil((data_end - requested_start).days / 365.25)
```

Response additions:

```python
"used_synthetic": prep["used_synthetic"]
"synthetic_info": prep["synthetic_info"]
"backfilled": prep["backfilled"]
"warnings": prep["warnings"]
"data_confidence": prep["data_confidence"]
```

Frontend changes:

- Add same checkbox and warning text to backtest input panel.
- Show warning in result if synthetic data was included.

Acceptance criteria:

- Default unchecked behavior is unchanged.
- Checked behavior can satisfy earlier requested start dates if synthetic generation succeeds.
- Synthetic usage is visible in the result.

## Phase 5. Portfolio Analysis Integration

Goal:

Add optional synthetic support to the portfolio analysis area, but first clarify which route is meant.

Potential current areas:

- `/myassets` and `/api/myassets/data`: current holdings and grouping.
- `modules/analyzer/portfolio_analyzer.py`: performance analyzer over existing history.
- Backtest tab may currently be the real portfolio analysis workflow.

Required clarification:

- If "portfolio analysis tab" means backtest/performance simulation:
  - Reuse Phase 4 backtest integration.
- If it means `/myassets` holdings:
  - Synthetic long-history generation may not be appropriate unless there is a performance-history chart.

Recommended approach:

1. Add synthetic checkbox only to workflows that run historical simulations or rolling analysis.
2. Do not add synthetic data to current-price-only holdings views.
3. If a portfolio history chart is added later, route it through `prepare_scenario_data`.

Acceptance criteria:

- Synthetic data is not used for simple current-value holdings.
- Historical analysis views can opt in through the common facade.

## Phase 6. Retirement Refactor To Facade

Goal:

Make retirement use the same common entry point without changing behavior.

Current behavior:

- `retirement_logic.py` directly calls `DataPreparer`.

Change:

- Replace direct `DataPreparer` calls with `prepare_scenario_data(...)`.
- Set `allow_synthetic=True` to preserve existing behavior.
- Keep response fields:
  - `synthetic_info`
  - `backfilled`
  - `data_start`

Acceptance criteria:

- Retirement results remain materially unchanged.
- One common facade now serves retirement, calculator, and backtest.

## Phase 7. Keep Dividend Simulator Separate Initially

Goal:

Avoid destabilizing dividend target calculations during the first integration.

Why:

- `DividendSimulator` does not create price histories.
- It generates synthetic dividend outcomes directly.
- Its synthetic model is target-probability specific and not equivalent to DB-level synthetic price generation.

Initial action:

- Do not rewrite dividend synthetic logic immediately.
- Add a warning in the architecture notes that it remains a separate synthetic path.
- Fix known short-history issue separately:
  - Exclude current incomplete year from price return stats.
  - Add minimum actual-history checks before trusting synthetic stats.

Later migration:

- Create a separate common module:

```text
modules/data_preparation/synthetic_scenario_generator.py
```

Potential API:

```python
generate_synthetic_cases(
    purpose="dividend",
    tickers=tickers,
    weights=weights,
    n_needed=n_needed,
    stats_source="proxy_or_actual",
    confidence_floor="C",
)
```

Acceptance criteria for later migration:

- Dividend synthetic outcomes carry confidence and warning metadata.
- Short-history ETFs do not silently drive aggressive long-term assumptions.

## Phase 8. Provenance And Confidence Alignment

Goal:

Align synthetic integration with `ETF_BACKFILL_ARCHITECTURE_PLAN.md`.

Required future tables:

- `backfill_runs`
- `price_daily_source`
- `corporate_action_source`

Synthetic integration should prepare for these fields now:

```python
"confidence": "D"
"source_type": "synthetic"
"method_version": "synthetic_gbm_v1"
```

Near-term:

- Include confidence in `synthetic_info` even before DB provenance exists.

Long-term:

- DB synthetic generation should write provenance rows.
- `TickerStatsCache` should exclude generated rows by provenance.
- UI should show confidence grade.

Acceptance criteria:

- New API response structure will not conflict with future Backfill V2 provenance.
- Synthetic rows can eventually be audited and regenerated.

## Phase 9. UI Warning And Result Disclosure Standard

Goal:

Use consistent language across tabs.

Input checkbox:

```text
가상 데이터 사용
실제 데이터가 부족한 경우에만 선택하세요. 통계적으로 생성된 데이터가 포함되어 결과 정확도가 낮아질 수 있습니다.
```

Result warning examples:

```text
이 결과에는 가상 데이터가 포함되어 있습니다. 실제 과거 수익률이 아니라 통계적으로 생성된 구간이므로 참고용으로만 사용하세요.
```

```text
458730: 1964-05-04 ~ 2023-06-19 구간은 가상 데이터입니다.
```

Display rules:

- Show only if `used_synthetic=True`.
- Show affected ticker and date range where available.
- Do not bury warning in tooltip only.
- Keep it visible near summary metrics.

## Phase 10. Testing Strategy

### Unit Tests

Add tests for:

- `prepare_scenario_data` with `allow_synthetic=False`.
- `prepare_scenario_data` with `allow_synthetic=True`.
- DataPreparer flags:
  - backfill off / synthetic off
  - backfill on / synthetic off
  - backfill on / synthetic on
- Warning generation.
- Data confidence calculation.

### Integration Tests

Investment calculator:

- Existing actual-data case unchanged.
- Short-history ETF fails when synthetic unchecked.
- Short-history ETF runs when synthetic checked.
- Response includes synthetic warning.

Backtest:

- Existing start/end behavior unchanged when synthetic unchecked.
- Earlier start date can run when synthetic checked and data generation succeeds.

Retirement:

- Existing behavior remains compatible after switching to facade.

Dividend:

- No behavior change during initial phases.

### Manual QA

Use test cases:

- SCHD
- TIGER 미국배당다우존스
- A recently listed Korean ETF
- A broad S&P500 Korean wrapper
- A short-history thematic ETF

Confirm:

- Checkbox default is off.
- Results warn when synthetic is used.
- No warning when only actual/backfilled data is used.
- Data shortage error still appears when unchecked.

## Suggested Implementation Order

1. Add `ScenarioDataPreparer` facade.
2. Extend existing `DataPreparer` with `allow_backfill` and `allow_synthetic` flags.
3. Add backend support to investment calculator.
4. Add calculator UI checkbox and result warning.
5. Add backend support to backtest.
6. Add backtest UI checkbox and result warning.
7. Refactor retirement to use facade, preserving behavior.
8. Add diagnostic/reporting for synthetic usage.
9. Later: migrate dividend synthetic cases into shared scenario generator.
10. Later: connect facade to Backfill Engine V2.

## Non-Goals For First Implementation

Do not do these in the first implementation slice:

- Do not rewrite `DividendSimulator` synthetic logic.
- Do not rewrite `WithdrawalAnalyzer` synthetic case logic.
- Do not implement full Backfill Engine V2.
- Do not add U.S. full ETF universe ingestion.
- Do not create a complex UI for confidence grades yet.
- Do not delete legacy `volume=0` rows without a migration plan.

## Risks

### Risk 1. Data Pollution

Synthetic rows are written into `price_daily.db`.

Mitigation:

- Require explicit opt-in for new tabs.
- Add warnings.
- Add provenance in a future phase.
- Prefer generating only when requested history is impossible otherwise.

### Risk 2. Silent Result Distortion

Users may treat synthetic results as factual.

Mitigation:

- Visible warning in input and result.
- Include ticker/date details.
- Add confidence grade later.

### Risk 3. Over-Refactor

Trying to merge all synthetic logic at once can break retirement and dividend calculations.

Mitigation:

- Facade first.
- Keep behavior-compatible defaults.
- Migrate one tab at a time.

### Risk 4. Stats Based On Generated Rows

`TickerStatsCache` can accidentally use generated rows because provenance is weak.

Mitigation:

- Short-term: be conservative and document limitation.
- Medium-term: use `price_daily_source`.
- Long-term: stats cache excludes all non-actual rows.

## Long-Term Target

Eventually, all tabs should use the same preparation contract:

```text
UI intent
  -> allow_synthetic flag
  -> ScenarioDataPreparer
  -> BackfillEngineV2 / Synthetic fallback
  -> price data + confidence + warnings
  -> analyzer
  -> result disclosure
```

The analyzers should not independently decide how to fabricate missing history. They should consume prepared data and metadata.

## Definition Of Done

This integration is complete when:

- Investment calculator has optional synthetic support.
- Backtest/portfolio analysis has optional synthetic support.
- Synthetic option is unchecked by default.
- UI warning is visible before running.
- Result warning is visible after running if synthetic data was used.
- Retirement behavior is preserved.
- A common facade is used by at least retirement, investment calculator, and backtest.
- Dividend synthetic logic is documented as a separate path, with a later migration plan.
- API responses include enough metadata for future confidence/provenance display.

