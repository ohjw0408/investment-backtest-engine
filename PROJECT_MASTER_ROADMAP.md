# Project Master Roadmap

Last updated: 2026-06-11 (✅ **모바일 반응형+다크모드+UX 전 페이지 개편** — 햄버거 드로어·`data-theme=dark` 팔레트·인라인 색상 ~200곳 변수화·BUG-NAV-1 해소·백테/내자산 모바일 후속 수정. Playwright 168체크+라이브 검증+오너 실기기 확인 완료. 상세 = status update 57~58. 이전: 2026-06-10 ✅ **간편 계산기 4종 신규 `/simple`** — 오너 결정으로 P1 착수: 복리(세후·인플레)·배당재투자(잼투리식)·인플레 생활비·실질 구매력, 전부 클라이언트 JS. 손계산 25 + jsdom 35 PASS. GAP-DECUM-COMP = 오너 결정 **계속 보류**. 이전: 2026-06-09 **Track G5 멀티계좌 탭 복제 전체 완료**: G5-A 백테 ✅ → G5-B 은퇴적립 ✅ → G5-C 은퇴인출 엔진 ✅ → G5-D 인출기 standalone 멀티+세금 ✅ → **UI 4탭(계산기·백테·은퇴적립·은퇴인출) 전부 배선·배포** → **세금 커버리지 전탭 감사 = 신규 배선버그 0**. BUG-WD-TAX·GAP-WD-MULTI 해소. 발견 갭 1개 **GAP-DECUM-COMP**(인출 중 금융소득 종합과세 미모델링)=오너 보류. → **다음 = L7 실데이터 통합검증(브라우저) OR 신규 간편도구(간편계산기·세금계산기) OR GAP-DECUM-COMP**)

> 이력: 2026-06-03 = 절세액 P1·단일계좌·KRX 금현물 Phase 1+2·BUG-TAX-1/2·BUG-G1-2·deploy.yml 복구 (당시 진행 중 = G5-C 토대).

> ⚠️ **2026-05-30 정정:** 아래 "SCHD vs TIGER now converge" / "Phase 2c Gate 통과" / "Track A 완료"는 **가격(CAGR) 수렴만** 검증된 것이었음. `debug_dividend.py` 실측 결과, 배당 **액수**는 0임이 확인됨. 원인: Track A가 DJUSDIV_PROXY를 total-return(adj-close)로 구축 → 가격은 맞지만 배당이 가격에 임베딩되어 itemize 안 됨. 백필 가격 구간(1928~)에 배당 row 없음 + provenance 전부 0행. **이는 세금 Phase 2c(배당 역산)·2e(금종세)·Track G(다중계좌 세금)의 데이터 기반을 무효화한다.** 해결 owner: `ETF_BACKFILL_ARCHITECTURE_PLAN.md § Phase 6.0`(범용 배당 백필 재설계). 우선순위는 아래 "Current Recommended Next Action" 참조.

## Purpose

This file is the thin command document for the project. It does not replace the detailed plans. It tells future maintainers and AI agents which plan owns which work, what the current execution state is, and what should happen next.

Do not merge the detailed plans into one giant document. Keep them separate and use this file as the coordination layer.

## Source Plans

| File | Role | Status |
|---|---|---|
| `PHASE4_PLAN.md` | Product feature roadmap: search, symbol pages, my assets, home, sharing, UX, advanced calculators, synthetic-data checkbox idea, server price-cache retention policy | Partially completed (A1/A2/A3/A5/A6/B5/C3/C5/D3 done) |
| `세금에서시작된완전리팩토링계획.plan.md` | Tax and simulation-core correctness roadmap: TaxProfile, TaxSessionState, TaxableSimulationRunner, gates by screen | Phase 1~3 + 2c/2d 완료. ✅ **Phase 2f(금융소득 종합과세) 완료(2026-05-31, 4100ecd)** — 중간실현 합산·`other_financial_income` 자동산출·`_ytd_income` 주입·분할매도 슬라이더 전탭(배당탭은 별도엔진 제외). 검증 = test_phase2f 7/7 + tax_truth 64/64 + Gate 2a/2b/2c. 잔여 = Phase 3 정리·문서(낮음). |
| `ETF_BACKFILL_ARCHITECTURE_PLAN.md` | Long-term ETF backfill, data provenance architecture, and canonical server price-retention policy | ✅ **Phase 6.0 Stage A + Stage B 완료**(주식 배당 + 채권/MMF·환헤지비용·US 채권 키워드 자동분류·통화가드, 서버검증). Phase 3+ (etf_master, etf_proxy_map, confidence grading)는 이후. |
| `SYNTHETIC_DATA_INTEGRATION_PLAN.md` | Opt-in synthetic data support and common data preparation facade for calculator/backtest/portfolio tabs | ✅ Complete (Phase 1~10, all screens). |
| `isafix.md` | Korean regulatory compliance: account-type investment restrictions (ISA/연금저축/IRP), ISA contribution limits, ISA windmill block, COMMODITY_ETF classification for IRP | **Backend complete (e8b7c1e). Frontend partially done. BUG-1~5 remain.** |
| `PHASE4_PLAN.md § 4G` | Multi-account simulation engine + real ISA windmill (sequential/conditional flow). Requires Track F first. Key constraint: percentiles must be computed after per-scenario sum, not by summing individual percentiles. | ✅ 엔진+투자계산기 완료. → `trackG_multiaccount_plan.md`로 이관. |
| `trackG_multiaccount_plan.md` | 다중계좌 엔진(G1~G4·2-4) + 배선/UI(B1~B3) + 탭복제(G5: 백테스트·은퇴) | ✅ **G5 전체 완료(2026-06-09).** G5-A 백테·G5-B 은퇴적립·G5-C 은퇴인출 엔진·G5-D 인출기 standalone 멀티+세금·UI 4탭 배선·배포·세금감사(신규버그0) 전부 완료. 잔여=L7 실데이터 브라우저 검증·GAP-DECUM-COMP(보류). |
| `절세액표시_plan.md` | 결과화면 절세액 3종(위탁가정·실제·절세액)+GH 절세. L-SAVE 검증설계. | ✅ **P1 완료**(투자계산기, 03f28cb+). 백테스트/은퇴는 G5 복제로 따라옴. P2/P3 후속. |
| `금데이터백필_plan.md` | KRX 금현물 거래가능 시계열(위탁전용) + 금 ETF 상장전 백필 | ✅ **Phase 1**(위탁 KRW/g 시계열, 서버검증)+**Phase 2**(현물=KRX_GOLD·선물=GC=F 갈래 라우팅, 로컬검증) 완료. |
| `간편계산기_plan.md` | 가정 기반 간편 계산기 묶음(복리·배당재투자 등, 시트 대체). 롤링 엔진과 별개. | ✅ **4종 구현·배포·서버검증 완료(2026-06-10, `/simple`, JS 전용, fe7c7af).** 잔여=브라우저 육안. |
| `세금계산기_plan.md` | 위탁→ISA 전환 결정 도구(전환 양도세 vs ISA 세제혜택, 스위칭코스트). | ✅ **v1 완료(2026-06-12, c65cf80).** `/tax-switch` 독립 페이지, (a) 분할이전 모델(오너 결정). 라이브 검증 PASS. |
| `리스크리턴도표_plan.md` | 저장 포트폴리오 위험-수익 산점도(FunETF 류). | 💡 아이디어 — 미착수. **선행=포트폴리오 즐겨찾기(미구현)** → 후순위. |
| `다계좌세금_E2E검증_plan.md` | 4탭(계산기·백테·은퇴sim·인출기) 멀티계좌 세금 배선 Playwright 실브라우저 자동검증 16건. **= P0 L7의 실행판.** | 📝 **계획 완료(2026-06-10)·실행 대기.** 셀렉터 실측 포함, Claude가 직접 실행 가능. |

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
- ✅ **완료(2026-05-31, 4100ecd):** 금융소득 종합과세 완전 구현(Phase 2f) — 중간실현 합산·자동산출·`_ytd_income` 주입·분할매도 슬라이더 전탭(배당탭 제외). ※ 이 줄은 과거 "지금/다음"이었으나 2026-06-12 stale 정리로 완료 반영.
- ✅ **Track G 대거 진척(2026-06-02):** G1 ✅ + **G2 자금이동**(2-1 라우팅·2-2 만기분배)·**G3 연금이전공제**·**2-4 금종세 풍차중단**·**G4 연납입공제** 엔진 전부 완료(L0~L9 결정론 40+케이스). **B1**(analyzer/logic 배선)·**B2**(API 서버검증)·**B3**(투자계산기 UI: 우선순위·풍차토글·재투자·결과패널) 완료. 잔여: 은퇴/백테스트 탭 복제·L7 실데이터·**절세액 표시**(신규 계획).

완료 (가격/구조 레벨 — 단, 배당 액수 정확성은 별개):

- ✅ Tax Phase 1~3, Phase 2a/2b/2d — Gates passed. 종합과세 **계산 엔진**도 완전(단위검증 OK).
  ⚠️ **2c: 재검증 필요**(배당 데이터 의존). ⚠️ **2e: 부분 구현** — 백테스트만 배선, 기존
  금융소득 자동산출·전탭 배선·`_ytd_income` 주입 미완. Stage A 완료 후 정상 배당 데이터 기준 재검증 필요.
- ✅ Track A/Stage A: DJUSDIV_PROXY raw-close price-return 재구축 + 배당 분리 주입 완료.
- ⚠️ Track B: Phase 2c Gate "passed" — 가격 기준. 배당 정상화 후 재검증 대상.
- ✅ Track C: Synthetic data integration complete across all screens (Phases 1~10).
- ✅ ETF_BACKFILL Phase 0~2 provenance 스키마는 Stage A 백필 가격/배당 기록에 사용됨.
- ✅ PHASE4: A1/A2/A3/A5/A6/B5/C3/C5/D3 done.

Current blocker: **없음.** 배당 Stage A/B + Phase 2c 재검증 + Phase 2f(금종세 완전 구현, 4100ecd) 완료. 다음 = **세금 전환 계산기**(`세금계산기_plan.md`, P1). (2026-06-12 갱신)

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

> ✅ **2026-06-12 추가 (절세액 P2/P3 완전 마감 — 인출기 절세 패널, 라이브 검증까지):** 오너 지시로 P2/P3 실상 점검 → P2 백테스트·P3 적립기/연금수령세는 G5 복제로 기완료, 유일 갭 = 인출기(wd) 절세 패널 → 오너 결정 "구현". `sell_with_tax` 위탁가정 누적(이중집계 가드) + wd 절세 3종 + 렌더. 검증 = `test_l_save_wd.py` 6 PASS ±1원 + 회귀 246 PASS + 실데이터 + jsdom + **라이브 probe PASS**(`probe_wd_savings_live.js`: 패널·각주·위탁 불변식 0·합산=Σ). 커밋 90649dc·f670e51. 상세 = status update 62. **절세액 P1~P3 마감(P4 배당금계산기 보류). 다음 = P3 포트폴리오 즐겨찾기(B1, 리스크리턴도표 선행) OR 기타 — 오너 결정.**

> ✅ **2026-06-12 (ISA 전환 계산기 완료 — P1 세금계산기 v1, 배포·라이브 검증까지):** 오너 결정 = **(a) 분할 이전 모델 + 독립 페이지.** 신규 `/tax-switch`(A 위탁유지 vs B 연 1회 ISA 한도 분할이전, 세후 비교 + breakeven + 이전계획). 엔진 = `MultiAccountSimulationLoop` optional 확장(carried_cost_basis·switch_policy·yearly_after_tax_snapshot, 기본 OFF=기존 무변경) + `tax_switch_logic.py`. 검증 = 신규 8 PASS 손계산 ±1원 + 회귀 240 PASS + Playwright 186 PASS + **라이브 풀플로우 PASS**(`live_tax_switch.js`: 458730 5천만/3천만/5y → 212윈도우, B +49만, breakeven 4년차 84%, 콘솔에러 0). 커밋 c65cf80. 상세 = status update 61 + `세금계산기_plan.md`. **다음 = 절세액 P2/P3(P2) OR 포트폴리오 즐겨찾기(P3) OR 기타 — 오너 결정.**

> ✅ **2026-06-11 (L7 완료):** **다계좌 세금 E2E 16건 전부 PASS** — 실행 중 발견 2건(GAP-RET-KRDATA·BUG-WD-MULTI-LIVE)을 당일 조사(서버 SSH 실측)·수정(9486eee: 은퇴 탭 synthetic 옵션 + 인출 투영 별도 prep + 0윈도우 합성 폴백+라벨 + NaN race 가드)·라이브 재검(C·D 7/7)까지 완료. **P0 L7 = 완료.** 신규 상시 검증자산 = `tests/e2e_multitax/`(16건 자동 재실행 가능). 상세 = status update 59~60 + log 4건 + `tests/e2e_multitax/results/20260611_result.md`. ~~다음 = 금융소득 종합과세(P2) OR 세금계산기(P1) — 오너 결정~~ → **2026-06-12 정리: 금종세는 Phase 2f로 이미 완료(4100ecd, 2026-05-31)였음(이 줄이 stale). 따라서 다음 = 세금 전환 계산기(P1, `세금계산기_plan.md`).**

> (이전) ✅ **2026-06-11:** 모바일 반응형 + 다크모드 + UX 전 페이지 개편 완료·배포·라이브 검증(status update 57~58). BUG-NAV-1 해소. `tests/test_responsive_dark.js` 168체크. 오너 실기기 확인 완료.

> (이전) ✅ **2026-06-10:** G5 전체 완료(06-09) + **간편 계산기 4종 `/simple` 배포·검증 완료**(06-10, P1 첫 항목 소화) + **Playwright 실브라우저 검증 체계 도입** + **다계좌 세금 E2E 검증 계획 수립**(`다계좌세금_E2E검증_plan.md` 16건).

**[P0 — Track G5 마무리 검증 & 보류건] (2026-06-11 갱신)**
- ✅ **L7 실데이터 통합검증 — 완료(2026-06-11).** `다계좌세금_E2E검증_plan.md` 16건 라이브 전부 PASS(발견 2건 당일 수정 포함, 커밋 98afdbf~9486eee). 결과 = `tests/e2e_multitax/results/20260611_result.md`.
- ⏸️ **GAP-DECUM-COMP** — 오너 재확인(2026-06-10): **계속 보류.** 은퇴 인출 중 금융소득 종합과세 미모델링(`multi_account_withdrawal.py:107` other_financial_income=0 하드코딩). 버그 아닌 보수적 근사. **오너 결정 전 착수 금지.**

> ✅ **완료 기록(2026-06-09):** G5-A 백테(L10)·G5-B 은퇴적립(L11)·G5-C 은퇴인출 엔진(L12)·G5-D 인출기 standalone 멀티+세금(L13, 커밋 759e393)·UI 4탭 배선·배포·세금 전탭 감사(421ac71). BUG-WD-TAX·GAP-WD-MULTI 해소. 상세 = `trackG_multiaccount_plan.md` 끝 + `wiki/dev/status.md` update 39~54 + log 감사항목.

**[P1 — 신규 간편 도구 (오너 아이디어, quick win)]**
- ✅ **간편 계산기 묶음** (`간편계산기_plan.md`) — **완료·배포·서버검증(2026-06-10, fe7c7af).** `/simple` 4종(복리·배당재투자·인플레 생활비·실질 구매력), JS 전용, 손계산 25+jsdom 35 PASS, 라이브 200·JS 바이트 동일. 잔여 = 브라우저 육안.
- ✅ **세금 전환 계산기** (`세금계산기_plan.md`) — **v1 완료(2026-06-12, c65cf80).** `/tax-switch` 독립 페이지, (a) 분할이전 모델. 손계산 8 PASS + 회귀 240 + 라이브 풀플로우 PASS.

**[P2 — 절세액 P2/P3 + 데이터 토대]**
- ✅ **절세액 P2/P3 완료(2026-06-12 정리+마감).** P2 백테스트·P3 적립기/연금수령세 = G5 복제로 기완료였음(점검으로 확인). 잔여 갭이던 **인출기(wd) 절세 패널** 구현(오너 결정) — test_l_save_wd 6 PASS + 회귀 246. 잔여 = P4 배당금계산기(보류). 상세 = `절세액표시_plan.md` 끝 + status update 62.
- ~~금융소득 종합과세 완전 구현(2e 배선)~~ ✅ Phase 2f로 완료(2026-05-31, 4100ecd). 잔여 = 배당금계산기 탭(별도 엔진, 곁가지 참조).

**[P3 — PHASE4 제품 기능]**
- 포트폴리오 즐겨찾기(B1) ← 리스크리턴도표 선행. D1 TDF·D2 연금통합·A4 종목상세·C1/C2.

**[잔여 곁가지(낮음)]**
- KQ150 fdr 티커 수정(수집 실패). 데이터 파이프 갭채움+gold 외 일일 스케줄러.
- 배당금계산기 G2/절세액 미지원(별도 엔진, 후속).
- 리스크리턴도표(`리스크리턴도표_plan.md`) — 즐겨찾기 선행.

**[6] 마지막 — 인프라/UX 마감:** E1 모바일, E2/E3/E4 최적화, C4 온보딩.
