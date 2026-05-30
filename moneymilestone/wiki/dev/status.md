---
updated: 2026-05-30
tags: [dev]
---

> 2026-05-29 업데이트: T1 검증 중 479080(머니마켓/CD ETF) `float(None)` 오류를 서버에서 확인. 479080에는 2025-11-13 배당 이벤트 row의 `close=NULL`이 있으나 현재 코드의 NULL 필터는 정상 동작함. 실제 운영 리스크는 systemd worker 외 수동 Celery worker가 함께 떠서 stale worker가 큐를 소비할 수 있던 상태였음. 수동 worker 종료 후 `/api/calculator/submit` 479080 synthetic ON 검증 PASS(`cases_count=61`, `used_synthetic=True`).

> 2026-05-29 추가 업데이트: T2 금융소득종합과세/분할매도 패널 테스트 중 `Object of type bool is not JSON serializable` 오류 수정. 원인은 `split_sale_plan.over_threshold`가 `numpy.bool_`로 반환된 것. `bool(...)` 캐스팅 후 서버 배포 및 `/api/backtest/submit` 458730 과세 ON 검증 PASS(`split_sale_plan` 반환).

> 2026-05-29 추가 업데이트 2: 분할매도 `최적 연수` 기준은 1~20년 균등분할 중 총 세금 최소 연수로 확정. 백테스트가 기존 금융소득(`other_financial_income`)도 반영하도록 수정하고, 세금 설정/백테스트 패널에 기존 연간 금융소득 입력 추가. 분할매도 패널에 일괄/분할/최적 세후 이익 표시. 서버 검증 PASS.

> 2026-05-29 추가 업데이트 3: 세금 설정 프로필을 단일 입력원으로 통일. 투자계산기/백테스트/연금 탭의 나이·연간 근로소득 중복 입력칸 제거, 배당금 계산기도 서버 세금설정 API 우선 로드로 정리. 금융소득은 세금설정에서 묻지 않도록 UI 제거하고, 계산기별 자동 산출 계획을 `dev/ideas.md`에 기록. 서버 `192693c` 배포 및 주요 5개 화면 HTTP 200 확인.

> 2026-05-30 업데이트: Track G G1(다중 계좌 시뮬레이션 엔진 — 자금이동 OFF) 투자계산기 탭 1차 구현 완료. `MultiAccountSimulationLoop`/`MultiAccountAnalyzer` 신규 추가, `calculator_logic.py` accounts 배열 분기 추가, 투자계산기 UI를 계좌별 독립 입력으로 변경. L0~L3 결정론적 테스트 4/4 PASS, 기존 Gate 2a/2b/2c 12/12 PASS, 브라우저 UI 스모크 확인. (Codex)

# 현재 개발 상태

**에이전트: 코드 작업 완료 후 이 파일 반드시 업데이트.**

---

## 한 줄 요약

> ✅ **2026-05-31 업데이트 7 (Stage B 모델타입 일반화 + 전수검증):** US 채권 10종 `stage_b_full_verify`(가격/쿠폰/총수익보존/시변듀레이션). 듀레이션 실측 보정(GOVT 5.3·AGG/BND 4.4·SHY/SCHO 0.8), `model` 필드(duration|carry), 쿠폰 book_factor 0.87. **carry 모델 BIL 검증**(총수익 상관 0.945·CAGR차 0.14%p) → 한국 CD/MMF 모델타입 입증. 총수익 보존 전 10종 CAGR차 0.03~0.86%p. 한계(Grade C): SHY/SCHO 가격상관 0.4·AGG/BND 0.88·장기채 TE~5%. gate 2c PASS. **다음=한국 금리수집(KOFR/KTB/CD)→config 행추가+FX.**

> ✅ **2026-05-31 업데이트 6 (배당 백필 Stage B — US 국채):** 채권이 `DGS*` 금리를 가격으로 쓰던(가짜) 문제 + 쿠폰 0 해소. `bond_model.build_bond_price_series`(yield→price = -duration×Δyield) + `inject_monthly_coupons`. ETF별 듀레이션 명시 매핑(TLT/IEF/SHY…→DGS30/10/3MO). 검증: 모델 vs 실측 TLT 월상관 **0.986**, Grade C. TLT 백필 1977~2002(6461행+쿠폰311) + 계산기 total_dividend 0→35.2M. gate 2c PASS·SCHD 불변. **다음=한국 국채/회사채/MMF (KOFR/KTB·CD 금리 수집 선행).**

> ✅ **2026-05-31 업데이트 5 (투자계산기 가상데이터 보충):** "가상데이터 사용" 체크해도 SCHD 20년이 11케이스 그대로던 문제 수정(`3c86c49`~`7af4c05`). 원인=DataPreparer가 백필 "ok"면 합성 스킵 + 분석기가 윈도우 수를 data 범위로 제한. `AccumulationAnalyzer`·`MultiAccountAnalyzer` 양쪽이 use_synthetic 시 윈도우별 독립 GBM으로 **TARGET=40까지 보충**(체크 OFF면 순수 실데이터). 공유 헬퍼 `build_window_synth_params` 추출. **버그수정:** anchor를 raw USD로 잡아 실 suffix(get_price=KRW×환율)와 1181배 어긋나 CAGR 폭발 → anchor를 get_price(FX)로 산출. 검증: SCHD 20년 OFF=11/ON=41케이스, end_value 정상·꼬리확장(p10 69→45M), 회귀 26/26·gate 2c PASS. ⚠️ ON 시 ~4배 느림. ⚠️ MultiAccountAnalyzer `cagr` 필드 garbage(기존 별개 버그, 분포는 end_value라 무영향).

> ✅ **2026-05-31 업데이트 4 (배당 계산기 UX):** 확률 슬라이더 기본 90%→**50%**, 범위 0~100%(50%=중앙값=균형점, 넛지 완화). `probability` 모드 결과에 **예상 월배당 중앙값(p50)+범위(p25~p75)** 카드 추가(중복표기 목표월배당·기준확률 제거). 슬라이더 라벨 desync 버그 수정(stale 복원 시 라벨 미갱신). 커밋 `73791c6`·`06bd19f`. 범위(scenario) 모드는 확률곡선이 이미 전 확률 표시 → 밴드 불필요.

> ✅ **2026-05-30 업데이트 3 (배당 역산 3단 폴백):** 배당금 계산기 역산이 실데이터<30케이스 시 실측 전부 버리고 가상으로만 돌던 버그 수정(`97ac6ab`). `_find_real_data_start` 배당간격 휴리스틱(4종목 전부 오검출)→`volume>0` 결정값 교체, `_run_rolling` 3단 폴백(①실데이터 ②백필포함 전구간 ③부족분만 가상 보충, 실측 유지). 검증: 휴리스틱 4/4 OK, 20yr=백필실측10+가상20, Gate 2c PASSED 3/3, **역산 SCHD 78.75M vs 458730 82.5M = 1.05x 수렴**(4x→1.2x→1.05x). BUG-DIV-1 해소.

> ✅ **2026-05-30 업데이트 2 (Phase 2c/2e 재검증 + 프록시 2003 단축):** DJUSDIV_PROXY에서 S&P500(^GSPC) 1928~2003 구간 제거 — 광범위 시장지수는 SCHD 배당전략을 대표 못함. 체인을 DVY(2003-11-07)←SDY←SCHD로 단축, SCHD/458730/446720/402970 재백필(price_daily 2003~). 재검증: **투자계산기 SCHD≈458730**(total_div 97.2M≈99.4M, yield 13.9%≈13.0%), **배당금 계산기 역산 Gate 2c PASSED 3/3**(SCHD 71.25M vs 458730 86.25M, 구 4x→1.2x 수렴). 2e 종합과세 엔진 `tax_truth_test` 64/64 PASS. 커밋 e6707bd. ⚠️ 20yr 롤링 케이스 169→11 감소(2003 시작 트레이드오프). 잔존: `_find_real_data_start` 휴리스틱 기술부채([[dev/bugs]] BUG-DIV-1), 2e 자동산출/전탭배선 미완.

> 이전 요약: 배당 백필 Stage A 서버 적용 완료. DJUSDIV_PROXY를 price-return 체인으로 재구축하고 SCHD/458730/446720/402970 백필 구간에 명시적 배당을 주입했다. 서버 `stage_a_verify.py`, `debug_dividend.py`, 계산기 직접 실행에서 배당 지표 p50 > 0 및 UI 실측/추정 필드 확인.

> 이전 요약: Track G G1 투자계산기 탭 구현·검증·배포 완료 (b14ed44, L0~L3 + Gate 회귀 PASS, 브라우저 실검증).

---

## 최근 완료된 작업 (Claude 세션 2026-05-29 UI 버그 수정 + 문서 정비)

- ✅ BUG-6 (리밸런싱 행 폭 변동): `.rebal-action` min-width:145px + flex-shrink:0, ₩amount min-width:100px 고정. 커밋 671b28b
- ✅ TF5 (ISA 캡 배너 미표시): calculator.js 버전 문자열 20250523c5→20260529 갱신, 브라우저 캐시 강제 무효화. 커밋 e734b4a
- ✅ `handoff.md` ISA 1억 캡 재설계 계획 추가: 월 납입금 균등 축소 → 납입 지속 후 한도 도달 시 중단 방식으로 변경. AccumulationAnalyzer `contribution_end_months` 파라미터 추가 설계.
- ✅ 위키/플랜 파일 현황 반영 업데이트: phases.md (Track A/B/C/D + Phase 2c~3 완료), bugs.md (활성 BUG-1~5 추가), status.md (PHASE4 체크리스트 갱신), PROJECT_MASTER_ROADMAP.md (Track F 상태 수정)

---

## 최근 완료된 작업 (Claude 세션 2026-05-28 가상 데이터 시뮬 버그 2차 수정)

- ✅ `used_synthetic=False` 버그: DataPreparer early return 시 항상 False → `price_daily_synthetic` 존재 쿼리로 정상화 (3a190b5)
- ✅ 2007 이상치 버그: 단일 GBM 경로 슬라이싱 → 60개 윈도우 상관관계. `AccumulationAnalyzer._load_with_per_window_synthetic()` 신설로 윈도우별 독립 경로 생성 (cccda40)
- ✅ `float(None)` 크래시 (sigma_monthly 미체크): 가드 조건 누락 수정 (86d6a39)
- ✅ `float(None)` 크래시 (KOFR 등 flat ETF): `TickerStatsCache` NULL close 행 필터, `DataPreparer` anchor_price NULL 처리 (786831f)
- ✅ `DataPreparer.prepare()` early return 경로에 `actual_start`, `anchor_price`, mu/sigma 포함 — 윈도우별 생성에 필요한 파라미터 전달
- ✅ `data_preparer.py` `synthetic_info`에 `actual_start`, `anchor_price` 추가 (normal path)
- ✅ `calculator_logic.py` / `retirement_logic.py`: `synthetic_params` 전달

---

## 최근 완료된 작업 (Codex 세션 2026-05-28 KRX/Index 데이터 갱신 안정화)

- ✅ 서버 KRX API 키 누락 확인 및 `ecos/fred/krx_api_key.txt` 서버 업로드 (`chmod 600`)
- ✅ `refresh_krx_gold`: KRX 금현물 조회 범위 3일 → 15일, 저장 성공 시 Redis `mq:krx_gold` 캐시 삭제
- ✅ Celery Beat 금현물 갱신: 16:40 / 18:30 / 22:30 / 다음날 08:30 KST 다회 재시도
- ✅ `KRXClient`: API 키 환경변수(`KRX_API_KEY`, `KRX_AUTH_KEY`) 지원, 날짜 미지정 시 최근 15일 fallback
- ✅ `IndexLoader.download_all()`: 기존 “있으면 스킵” 제거, `get()` 기반으로 누락 앞/뒤 구간 보강
- ✅ 서버 `KRX_GOLD` 전체 재수집 진행 중: 2014-03-24부터 순차 복구 (긴 날짜별 API 호출)
- 검증: `py_compile` PASS, 임시 DB에서 `download_all()` 누락 구간 fetch 호출 확인 (Codex)

---

## 최근 완료된 작업 (Codex 세션 2026-05-28 가격 데이터 저장 정책 문서화)

- ✅ 모든 계획 파일 확인: `PROJECT_MASTER_ROADMAP.md`, `PHASE1_PLAN.md`, `PHASE3_PLAN.md`, `PHASE4_PLAN.md`, `ETF_BACKFILL_ARCHITECTURE_PLAN.md`, `SYNTHETIC_DATA_INTEGRATION_PLAN.md`, `세금에서시작된완전리팩토링계획.plan.md`
- ✅ 결정 기록: 가격 히스토리 정본은 서버 DB, 클라이언트 IndexedDB/모바일 SQLite는 나중에 UX 캐시로만 사용
- ✅ `ETF_BACKFILL_ARCHITECTURE_PLAN.md`: `Price Cache Metadata`, `Price Data Retention And Client Cache Policy` 추가
- ✅ `PHASE4_PLAN.md`: E4 `서버 가격 데이터 보존 정책 (core + user-requested TTL/LRU)` 추가
- ✅ `PROJECT_MASTER_ROADMAP.md`: `Data Storage Policy Decision` 추가 및 금지사항 보강
- 핵심 원칙: `core_permanent`/`protected_user_asset`는 자동 삭제 금지, `user_requested_cache`는 180일 기본 보존 후 dry-run 검토, `generated_history`는 provenance 기반으로만 정리

---

## 최근 완료된 작업 (Codex 세션 2026-05-28 금액가리기+내자산연동 정상화)

- ✅ 홈 포트폴리오 카드가 `/api/portfolio/history` 응답을 매번 새로 받아오고, 60초마다 자동 갱신되도록 수정
- ✅ 홈 포트폴리오 히스토리 마지막값에 내자산 현재가 기반 평가액을 반영
- ✅ 홈 자산군 비교(`/api/assets`)를 목표비중이 아니라 실제 보유자산 그룹별 현재 평가액 비중 우선으로 표시
- ✅ 내자산 탭에 `금액 가리기` 체크박스 추가, 기본값은 가리기
- ✅ 가리기 ON이면 홈/내자산 금액 표시를 `***,***,***원`으로 마스킹
- ✅ 세금 설정 저장 시 `hide_amounts` 설정이 덮여 사라지지 않도록 보존
- 검증: `venv` 기준 `py_compile` PASS, Flask `/`, `/myassets` 200 응답 확인

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

## 현재 블로커 / 재검증 필요 ❌

> 🔁 **배당 액수 0 블로커는 Stage A로 해소.** 이제 정상 배당 데이터 기준으로 세금 2c/2e를 다시 검증해야 한다.

| 블로커 | 상태 |
|---|---|
| **배당 액수 0 (total-return 백필 + 배당 row 부재)** | ✅ Stage A로 해소 — price-return proxy + 명시 배당 서버 적용 (Codex) |
| SCHD vs TIGER 배당 결과 불일치 | ✅ 투자계산기·배당금계산기 양쪽 수렴 확인. ^GSPC 제거로 역산 4x→1.2x (e6707bd, Claude) |
| Phase 2c Gate | ✅ 재검증 완료 — 2003 시작 데이터로 Gate 2c PASSED 3/3 (Claude) |
| `_fetch_fred()` 메서드 없음 | ✅ def 선언 추가 (e1a4d6e) |
| 백필 실패 코드가 완료 처리됨 | ✅ _backfill_skip_codes 분리 (a761750) |

---

## 완료된 것 ✅

### 세금 리팩토링
- Phase 1: 공통 세금 코어, 절세매도 12월 분리, 청산세 통일 (Gate 1 ✅)
- Phase 2a: `TaxableSimulationRunner` 구현, 백테스트 전환 (Gate 2a ✅)
- Phase 2b: 투자계산기 + 은퇴 적립 Runner 전환 (Gate 2b ✅)
- Phase 2c: 배당 역산 Runner 구현 ✅ / 🔁 Gate 재검증 필요 (Stage A 정상 배당 데이터 기준)
- Phase 2d: 은퇴 인출 세금 주입 (Gate 2d ✅ 5/5)
- Phase 2e: ⚠️ 부분 구현 — 종합과세 엔진+백테스트 배선만. 자동산출/전탭배선/_ytd_income 미완
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
| ✅ **배당 백필 Stage A** | 서버 적용 완료: DJUSDIV_PROXY raw 재구축, SCHD/458730/446720/402970 재백필+배당주입, UI 실측/추정 구분, 검증 PASS (Codex) | 완료 | — |
| 🔁 세금 2c/2e 재검증 | 정상 배당으로 배당역산·금종세 재확인 | Stage A 완료 | `Phase 2c/2e 재검증해줘` |
| 🔴 배당 백필 Stage B | 채권/MMF 금리→가격+쿠폰 분배금 (필수) | 2c/2e 재검증 후/병렬 검토 | `ETF_BACKFILL § Phase 7 + 6.0 Stage B` |
| ⏸️ Track G | 다중계좌 — G1 ✅(Codex, 배당0은 Stage A로 해소). ② 커서 ③ UI + G2 자금이동 | 세금 재검증 후 | `Track G 재개해줘` |
| ✅ Track F | ISA/계좌 규제 — 백엔드 + BUG-1~5 완료 | — | (완료, 미관 잔여만) |
| PHASE4 핵심 | D4 D1/D2/B1/A4/C1/C2/B4 | 배당 토대 후/병렬 | `PHASE4 다음 안전한 항목 진행해줘` |
| ETF_BACKFILL V2 Ph.3+ | etf_master/etf_proxy_map, confidence A~F | Stage A/B 후 | `ETF_BACKFILL Phase 3부터` |
| E1 모바일 / C4 온보딩 | 반응형 / 튜토리얼 | 전체 기능 안정화 후 | — |

---

## PHASE4 잔여 기능 체크리스트

**중단기 (세금/데이터 독립적 → 병렬 가능):**
- [ ] D4 거래수수료 설정 (1~2일) — Runner 안정 후
- [x] D5 인플레이션 검증 + 실질 생활비 표시 ✅ 7182ad1
- [ ] A4 종목 상세 개선 + 시간봉 차트 (3~4일)
- [ ] B1 포트폴리오 즐겨찾기/저장 (2~3일)
- [x] B2-b 자산 추이 차트 (myassets 하단) ✅ 02cb3e8
- [x] B2-c 내자산 현재가 Redis 캐싱 ✅ 1c5db23
- [x] B3 리밸런싱 경고 밴드 ✅ 02cb3e8
- [ ] C1 홈 화면 watchlist (2~3일)
- [ ] C2 자산군별 수익률 비교 (2~3일)
- [x] F1 대기 순위 UX 수정 ✅ 1c5db23

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
