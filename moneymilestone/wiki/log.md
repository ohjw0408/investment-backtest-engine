# Log

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
