---
updated: 2026-06-19
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

> ✅ **2026-06-19 업데이트 95 (UX — 포트폴리오 분석(backtest) 전면 리디자인 + 브랜드 다이얼로그 공용화):** 오너 지시로 좌/우 분할 폐기 → **전체폭 입력 화면 ↔ [분석 실행] 시 결과가 대체**(조건 요약 바 + 히어로 최종자산 + 보조칩 + 차트). **다중계좌 입력칸 = 메인과 동일 컴포넌트(대칭)**: `multi_account_ui.js` 계좌카드를 `.calc-input`·`.ticker-item`(슬라이더 포함)으로 재작성(계산기·은퇴·배당 공유, IDs 보존). **`base.html` 전역 `mmToast`/`mmConfirm`/`mmPrompt`**(native alert/confirm/prompt 대체, 단일 진실원천) + `nicon` 12종 추가 + `components.css`(ds5). backtest 이모지 전면 nicon·차트색 ds 바인딩(액센트/다크 따라감)·alert 11곳→토스트. `portfolio_favorites.js` native→브랜드. 검증 Playwright 실클릭(라이트/다크): 입력↔결과 전환·**대칭 측정(입력높이 21=21·칩 49=49·계좌 슬라이더)**·히어로·4차트·빈실행 토스트(네이티브 dialog 0)·**콘솔에러 0**·계산기/은퇴 스모크 OK. 공용 JS 캐시 `?v=20260619ds`. 상세 → [[디자인통일_plan]].

> ✅ **2026-06-19 업데이트 94 (UX — 내 자산 3개 탭 결 맞춤 + 토글/확인모달):** 오너 "자산현황 외 3탭이 없어보이고 불편". 전부 리치하게 재구성(`myassets.html`, 서버+Playwright 실클릭+스샷 검증). **금액가리기** 체크박스→토글스위치+눈아이콘+상태라벨. **리밸런싱** 인트로 + 기관급 경고밴드(큰 ±N%p·커스텀 슬라이더·눈금·프리셋칩) + 상태배너 + **그룹별 diverging 카드**(현재 채움막대+목표 마커선+매수/매도 칩+현재/차이/목표). **추가매수** 인트로+금액 빠른칩+자동계산+배분막대+합계. **그룹관리** 목표합계배너(100% ok/warn)+엠블럼카드(종목수·평가액·목표막대)+빈상태CTA. **삭제 confirm()→정식 모달**(`#modalConfirm`+`mmConfirm` 헬퍼, 휴지통아이콘). 부수=refreshHoldings 이모지 textContent교체→spinning 클래스. 검증 4탭 스샷+실클릭+네이티브 dialog 안뜸+에러0. 상세 → [[디자인통일_plan]].

> 🐞 **2026-06-19 업데이트 93 (BUGFIX — myassets "박살" 진짜 원인: style.css 주석 `*/` 조기종료로 전역 레거시 토큰 증발):** 오너 라이브 피드백("종목수정 모달·기간버튼·배당클릭·칸막이 다 깨짐"). 서버+Playwright 실클릭·computed·cssRules 덤프로 진단. **근본 = `style.css` 6행 주석 `ds(--brand*/--ds-*)`의 `*/`가 블록주석 조기종료 → 직후 레거시별칭 `:root{--card/--bg/--border…}` 27선언이 깨진 룰로 드롭 → 전역 미정의.** 레거시 토큰 의존 페이지(myassets·calculator…) 모달 투명·칸막이 증발·글씨 튐. 홈은 ds 직접써서 무사라 안 들킴(06-18 별칭도입 205a3fe부터 잠복, 내 디자인변경 아님). **수정 = 주석 `*/` 제거 1줄 → 전 레거시 페이지 동시 수복**(computed `--card #fff` 복구 검증). +버그2 `/api/myassets/data` NaN→None 정규화(가격 1개 빠지면 `res.json()` 실패로 보유종목·자산추이 사망 방지) +버그3 현재가 수정 `prompt()`팝업→인라인 모달. 검증 Playwright 실클릭 전부 PASS·에러0·라이트/다크. **⚠️ 교훈: CSS 주석 안에 `*/` 시퀀스(`--x*/--y` 등) 금지.**

> ✅ **2026-06-19 업데이트 92 (UX — 내 자산 myassets 홈패턴 이식, 배포):** 홈 완성 후 타페이지 확장 시작, 오너 결정 **내자산부터**. 홈 만족 5포인트 이식(`templates/myassets.html` 단일 파일): ① **깊이감**(`.main-content` 배경 ds-soft↓/다크 canvas + `.ma-card` 그림자·다크 dark-el) ② **pill 탭**(홈 위젯탭 결, 활성 ds-ink 채움) ③ **duotone 아이콘**(이모지 전면 SVG — 템플릿 로컬 `mi()` 매크로 12종 ⚠️nicon은 base.html 전용이라 페이지 로컬화 + JS렌더 `MAICON` pencil/trash/undo) ④ **비로그인 데모**(🔒텍스트→삼성전자·SPY 2행 미리보기, 점선카드+"예시"워터마크+배지+"데모 미리보기입니다" 배너 — 실데이터 착각 차단이 핵심[오너 강조]) ⑤ **차트색 토큰 바인딩**(#1a73e8·#1976D2·#2E7D32/#C62828 → --brand/--up/--down). **버그 동시수정**: 모달 닫기버튼 textContent 덮어쓰기로 X버튼 소멸하던 기존버그(id→내부 span). 검증(배선만, 육안=오너 서버확인): Jinja컴파일·분기정확·JS참조 ID 30종 존재·이모지 잔여0·status 200 양쪽. 인라인 style/script라 캐시 무관. **다음 = 오너 서버 육안 → 피드백 반영, 이후 calculator or backtest.** 상세 → [[디자인통일_plan]] §06-19.

> ✅ **2026-06-18 업데이트 91 (UX — 홈 랜딩·아이콘 duotone·깊이·중앙정렬, 세션 종료):** 조종석(업#90) 이후 후속 전부 배포. 비로그인 **랜딩**(데모 그래프 가짜숫자+SPY/TLT+하단 그라데 오버레이 "로그인하면 이렇게"·CTA 장점 2카드·**투자 도구 기능타일** 메인3=계산기/분석/비교·`{% if user %}` 분기, 96fafc8) + **이모지 전면→SVG duotone 아이콘**(`base.html nicon()` 매크로 17종, 사이드바·검색·시장헤더·사다리·타일; 오너 "회색 라인=칙칙" 거부→반투명 면+선 brand 톤, 9082b8c·b750b80) + **깊이감**(배경↓ ds-soft/다크 최암 + 카드 elevated ds-dark-el+은은한 그림자, 색추가0, abf2050) + **중앙정렬**(dashboard-grid margin auto 960px, 좌측 쏠림 해소, c518055). 검증 = Playwright 라이트/다크 콘솔에러 0. **다음 = 홈 패턴(깊이·duotone·중앙·상태분기·타일)을 내자산·계산기·백테로 확장 / 수익화(보류·미구현, 대시보드 레일광고❌·구독+제휴 권장) — 오너 결정.** 상세 → [[디자인통일_plan]] §종료정리.

> ✅ **2026-06-18 업데이트 90 (UX — 홈 조종석 재설계, "다음 할 일" 액션 사다리):** 오너 "팔레트=여전히 색칠, 직관 UX 원함". 홈을 범용 대시보드→**상태 인식 조종석**으로 구조 재설계(색 아닌 정보순서). 마찰 7건 분석 → ① 다크밴드(백테 중복) 제거→**"다음 할 일" 사다리**(💰배당예정·⚖리밸런싱 drift≥5%p·🎯은퇴넛지, 실데이터=`/api/myassets/data`+`/dividends` 조합, **신규 백엔드 0**, 가짜숫자 0) ② 금액 👁 peek 토글(가림설정 임시해제) ③ 시장위젯 강등 ④ 우측 빈칸 정리 ⑤ 상태별(보유O=사다리/보유X=온보딩 3스텝). 검증 = Playwright 사다리렌더·peek 공개·콘솔에러 0. `templates/index.html`만. 다음 = 조종석 패턴 내자산·계산기 확장.

> ✅ **2026-06-18 업데이트 89 (디자인 통일 — 대규모 팔레트 통일, 전 24페이지 코인베이스 채택, 미배포):** 오너 "싹 다 고쳐라". 두 고레버리지 편집: ① `calculator.css` 전체 ds 토큰화(10템플릿 공유=계산기·배당·은퇴·백테·myassets·symbol·portfolio_detail 등 입력패널·티커·결과/지표 일괄) ② `style.css` **레거시 토큰→ds 별칭 매핑**(`--blue→--brand`·`--card→--ds-canvas`·`--border→--ds-hairline`·`--green→--up`·`--red→--down` 등 — Material 블루 #1565C0 → 코인베이스 #0052ff, 미변환 페이지·인라인 수천곳 자동 채택, 다크/액센트는 ds가 처리하므로 다크 레거시 블록은 gold만 잔존). 캐시 `?v=20260618ds`. 검증 = Playwright 10페이지 스윕 콘솔에러 0 + 다크 정상 + home 회귀 없음. **남은 = 페이지별 레이아웃 폴리시(리스트/분석 아키타입 밀도)·alert/confirm→토스트 — 오너 1:1 지시 예정. 미배포(다음 커밋).**

> ✅ **2026-06-18 업데이트 88 (디자인 통일 — 폼 아키타입 단순군 4종 완료, 미배포):** `디자인통일_plan.md` 진행. 폼 목업(`design-preview-form.html`) 기준 **simple·tax_switch·settings·tax_settings** 진짜 재구성(리스킨❌). 각 `<style>` 레거시 토큰(`--card/--border/--blue*`)·하드코딩 블루(#1976D2)→ds 토큰(`--ds-*`/`--brand*`) 재바인딩. **마크업·ID·클래스·JS 무손상**(simple_tools.js·tax_switch.js DOM 계약 보존). 차트 brand 바인딩(simple 평가액=`--brand`/배당=`--up`, tax_switch A=`--up`/B=`--brand`). 검증 = 로컬 서버+Playwright 라이트/다크 풀스샷·콘솔에러 0(4페이지)·실동작(simple 즉시재계산·탭전환) + settings 로그인 에디터(mint_session, ⚠️ 쿠키=stdout 마지막 줄=import Redis 경고 분리). 진행표·`디자인통일_plan.md`·`log.md` 동기화. **미배포(배치 푸시는 오너 승인 후). 다음 = 폼 무거운군(calculator·dividend_target·retirement·alerts)+alert/confirm→토스트.**

> ✅ **2026-06-16 업데이트 87 (성능 최적화 P0+P1 구현·결과불변 검증 — 미배포):** `성능최적화_plan.md` 실행. **선행=골든마스터+벤치 하니스** `scripts/perf_golden.py`(결정론 합성가격 `_FakeLoader` → 실제 load/get_price 경로, DB·네트워크0, ±rel 1e-9). **P0** 롤링 윈도우 재로드 제거(Accumulation·MultiAccount 분석기 = `[roll_start,data_end]` 1회로드+`_slice_window`, multi는 주입 provider 경로 제외). **P1-1** Pool 1 vCPU 가드(withdrawal `_effective_workers`, 워커1=인프로세스→OOM/fork 제거). **P1-2** per-day 멤버십 死코드 제거(simulation_loop, 항상True). **P1-3** 엔진 가격캐시 LRU 상한8. **전부 골든마스터 결과불변 + 변경모듈 회귀 ~190+ PASS**(accum·multi·withdrawal·ISA·합성·tax-switch·fee·배당·백테). 하니스 실측 accum 1.14~1.21×(인메모리라 과소 — 프로덕션 P0 실이득 5~20×). **연산 성능 최적화 종합 — 전부 배포·결과불변 검증 완료.** 상세 → [[perf-optimization]]. 가격로드 재로드 제거(P0) + 배당엔진 per-day pandas→numpy + cash_allocator 無매수 단락 + Pool 1vCPU 가드 + I/O ThreadPool. **탭별 실측(원본 vs 현재): 투자계산기 무세금 5.7×·세금 8.8×·은퇴인출 8.8×·멀티계좌 7.4×·배당계산기 1.36×.** 검증 3중=골든 + 실DB A/B 18시나리오(세금·계좌·자산·모드 byte 동일) + pytest 298 passed(1 failed=저장포폴 사전존재버그 BUG-SAVEDPF-ROUNDTRIP, perf 무관). cash_allocator greedy·total_value·per-day 벡터화는 결과변경 위험이라 미적용(대원칙). 배당계산기(4.76s)만 덜 줄어 추가 최적화 보류. 토폴로지 정정=2vCPU+Celery concurrency2(서버 systemd만, TECH-CELERY-CONCURRENCY). **P2(I/O ThreadPool)도 구현**: P2-1 C3겹쳐보기 포폴지수 병렬(데이터출처 무변경→곡선 불변)·P2-2 watchlist 병렬(순서보존)·P2-3 get_price 트레일링 gap-fill 같은날 1회. 로컬 검증 PASS(골든 불변 + 패치로더). ⚠️ **라이브 지수곡선 대조 probe 필요**. **▶ 남은=P3(후순위) — 오너 결정.**

> ✅ **2026-06-15 업데이트 86 (캘린더 마감 + 비교탭 오버레이 + 버그픽스 + 성능 감사계획):** 한 세션 종합(전부 배포·push). ① **증시 캘린더 완결**: 배당락 클릭→1주당 배당금 팝오버(abee5ea), 로딩 스피너·FRED/yfinance 병렬·econ 디스크캐시(7d48204), **통화정책 결정일 Tier1**=US FOMC+KR 금통위 큐레이션 JSON(0382a3a). ② **포폴 비교탭(`/risk-return`)**: 거시 PART C3 = "추세 겹쳐보기" 오버레이(`PF:<id>` 토큰·`_portfolio_index_series`, 독립오버레이 macro.js 무손상, 스마트프리셋, 기간≤5년) + UI 재배치(광고→겹쳐보기→정밀비교) + "정밀 비교하기" 큰 버튼(e50a5c3·4f161a2). ③ **버그픽스**: 내자산 리밸런싱·추가매수 합계 오류(BUG-REBAL-SUM, 그룹종목만+목표정규화+정수배분), 점 티커 BRK.B 데이터없음(BUG-DOT-TICKER, `_yf_dl_ticker` 점→하이픈), 거시 겹쳐보기 hover 중복(BUG-MACRO-OVERLAP-TIP, index모드+filter). ④ **광고문구** 내자산→비교탭 이동. ⑤ **성능 최적화 계획**(`성능최적화_plan.md`) — 전 연산경로 전수 정독. 1vCPU/4GB·결과불변. **최대레버 = 롤링 윈도우 가격 재로드 제거(Accumulation+MultiAccount 분석기, WithdrawalAnalyzer는 이미 모범패턴). 1vCPU서 multiprocessing.Pool 역효과 발견. 세금엔진=이미 양호(캐시). analyzer/*=死코드.** 미착수(계획만, 선행=골든마스터 하니스). **▶ 다음 = 성능 최적화 착수(P0) — 오너 결정(현재 일시중지). 거시+캘린더 플랜 전체 종결.**

> ✅ **2026-06-15 업데이트 85 (거시경제 지표 탭 `/macro` 신규 — 배포·라이브, 0df9740→040ca98):** 플랜 `거시지표_캘린더_plan.md`. **거시지표 총 129종** = 미 FRED + 한 ECOS + 시장지수 yfinance(`modules/macro_loader.py` SERIES 레지스트리). 테이블 `macro_series`/`macro_observations`(index_master.db), 전 지표 출범부터 전체 히스토리, 129종 한글 설명(`DESCRIPTIONS`). 카테고리=주가지수(39)·금리·인플레·고용·통화·신용·경기·시장, country US/KR/GL. **KOSIS 불필요 확정**(전부 ECOS). 제외=GOLDAMGBD228NLBM(폐지)·USALOLITONOSTSAM(stale). **UI** `/macro` + `templates/macro.html`·`static/js/macro.js` + `/api/macro/{overview,series,compare,multi}` + nav/사이드바: 토글 US/KR/🌏글로벌/🆚한미비교/🔬겹쳐보기. 카테고리 카드그리드(PC 6칸 `grid-column:1/-1`·SVG스파크·툴팁·검색창), 카드클릭→상세(전체 시계열+기간토글 **날짜기준**+설명, 지수는 라인/캔들 LightweightCharts), 한미비교 12쌍(단위자동), **겹쳐보기**(거시+종목/지수 임의 N≤6 오버레이·프리셋4·구간설정·원값개별축[기본]/정규화). **자동갱신** `refresh()`+`tasks.refresh_macro`+beat 2회/일. **배포안전** deploy.yml `--ensure`(`ensure_data`: 빈/1990캡/신규시리즈 자동백필+설명시드, 멱등 `||true`)+읽기경로 ensure_schema. 검증=라이브 엔드포인트 + Playwright 콘솔에러 0(매 변경). **▶ 잔여(거시지표 탭 후속): Step6 증시 캘린더 · PART C3 포폴비교탭 오버레이 통합 — 플랜 기록, 오너 결정 대기.**

> ✅ **2026-06-15 업데이트 84 (C1 버그픽스 4종 + 지수 캔들 회귀 복구 + 내자산/홈/검색 새로고침·수동가격, 배포):** 오너 라이브 피드백 후속. **① 지수 캔들 회귀 복구:** `index_daily`가 종가만(OHLC 컬럼 없음)이라 지수 캔들 비활성됐던 것(렌더러·거래량은 멀쩡). 신규 `index_ohlc` 테이블(OHLCV) + `scripts/backfill_index_ohlc.py`(시장지수 12종 yfinance) → `get_symbol_data` 캔들에 공급(라인=index_daily 유지, 1H=intraday 온디맨드). **배포 안전:** `CREATE TABLE IF NOT EXISTS` + 데이터 없으면 yfinance **지연 백필**(첫 진입 자동적재, 수동 서버작업 불필요) — 직전 배포가 테이블 없어 "종목 못찾음" 크래시낸 것 핫픽스. KRX_GOLD만 close-only(캔들 미지원). **② PC 홈 위젯** 좁은 테이블 → `.market-grid` 3칸(큰 값+스파크). **③ 설정 PC** `.main-content` 2칸그리드 308칸에 끼던 wrap → `grid-column:1/-1`+멀티컬럼. **④ 홈 시세 속도:** 무거운 `get_symbol_data`(전체 history) → 경량 `_wl_recent_closes`(인덱스=index_master 25행/주식=get_price 45일창/미보유지수=yfinance 폴백). **새로고침+수동가격:** 내자산·홈·검색에 🔄(서버 공유 Redis 캐시 + **TTL 15분 고정=floor**, yfinance 15분 지연과 동일해 밴 방지·종목당 TTL 1회 호출). 내자산 = `holdings.manual_price` 컬럼(마이그레이션) + 현재가 ✎ 수동입력·↺자동복귀·"수동" 배지 + `POST /api/myassets/manual-price`. 검색 🔄 = 보이는 종목을 `/api/watchlist/quotes` 라이브로 덮어씀. 전 화면 "⚠ 시세 15분 지연" 문구. 검증 = `test_home_widgets` 16 PASS + 수동가격 override/해제 왕복 + Playwright(지수 캔들+거래량·1H·PC그리드·설정3컬럼·🔄·수동배지·검색 005930 ₩322500 라이브덮어쓰기). 커밋 7394171→8be53b9→6ccf735→(이번). **▶ 다음 = 홈/검색 새로고침 라이브 확인 / PHASE4 잔여(D1·D2·C2·B4).**


> ✅ **2026-06-14 업데이트 83 (C1 — 홈 화면 위젯 + 관심목록 + 설정 페이지, 배포·검증):** 고정 "시장 지수" 6종 → **사용자 구성 위젯 캐러셀**. 위젯=시장지수(기본)+관심목록N, 위젯별 이름·종목(주식/ETF/지수/환율/금/크립토)·홈 표시순서 사용자 지정. **모바일=스와이프 캐러셀(위젯 6개씩 페이지+도트)**, **PC=상단 탭+TradingView-lite 표**(행클릭→symbol). 비로그인/첫방문=기본 6종(편집은 로그인 유도). 계획=`C1_watchlist_plan.md`. **백엔드:** user_settings.home_widgets(JSON) + auth_manager get/save + `/api/home-config` GET·POST(검증) + `/api/watchlist/quotes`(get_symbol_data 경량시세+Redis 캐시) + DEFAULT_HOME_WIDGETS. **설정 페이지** `/settings` 신규(확장형 — 향후 계정/일반설정 자리) + "홈 화면 설정" 섹션(위젯 CRUD·이름 인라인·▲▼순서·검색모달/프리셋칩·저장). 사이드바·nav "설정" 추가. ⚠️ 기존 `/settings`가 tax_settings 별칭이던 충돌 제거(tax=/tax-settings 유지). 검증 = `test_home_widgets.py` 16 PASS(백엔드) + `test_home_widgets_live.js` 라이브 10 PASS(PC표/모바일캐러셀) + `test_settings_browser.js` 로컬 로그인 12 PASS(위젯 CRUD·검색·저장왕복) + 라이브 설정 게이트 PASS. 커밋 adc2ae0→2a65515→180c0b2→040a19c. **▶ 잔여(소) = Phase4 폴리시(다크/반응형 육안) · 다음 = PHASE4 잔여(D1·D2·C2·B4).**


> ✅ **2026-06-14 업데이트 82 (부채꼴 후속 — 세로 2배·슬라이더 애니·줌, 배포·라이브 검증 완료):** 오너 피드백 3건. ① 부채꼴 세로 너무 좁음 → 전용 `.chart-wrap-fan` 240→**480px**(모바일 360). ② 슬라이더 굴릴 때마다 차트 재생성돼 x축서 솟는 애니 거슬림 → `_drawFan`(생성)/`_updateFanBands`(슬라이더용) 분리: 기존 차트의 하단·상단 데이터셋만 교체 + `chart.update()` → **중앙선 고정·밴드 경계만 morph**. ③ 줌 = `chartjs-plugin-zoom@2.2.0` CDN(base.html) + fan options.plugins.zoom: **Ctrl+휠 확대축소(일반 스크롤 보존)·핀치·드래그 이동** + 조작 힌트 텍스트 + `resetFanZoom()` [줌 초기화] 버튼. 캐시 `?v=20260614fan2`(calculator.js·style.css·calculator.css). 검증 = `tests/test_fan_dom.js` **jsdom 15 PASS**(줌 config·중앙선 불변·in-place·resetFanZoom) + ✅ **커밋(eddcdc5)·push·배포·`tests/test_fan_live.js` 라이브 12 PASS**(줌 플러그인 로드·높이>400·중앙선 불변·콘솔에러 0). **▶ 다음 = PHASE4 잔여(D1·D2·C1·C2·B4) — 오너 결정.**

> ✅ **2026-06-14 업데이트 81 (투자계산기 미래 시나리오 부채꼴 — 경험적 퍼센타일 밴드, 배포·라이브 검증 완료):** 오너 결정 = 미래 예측 신규 0, **있는 데이터(과거 롤링 윈도우)를 시작점 정렬로 겹친 경험적 부채꼴.** 단일 Y축 절대금액₩ / x=경과 연차 / 별도 새 카드 / 듀얼핸들 슬라이더로 밴드 하단·상단 퍼센타일 각각 1% 자유 조정(기본 p25~p75) + p50 중앙선. **백엔드:** 공유 헬퍼 `yearly_trajectory`(`multi_account_common.py` — 윈도우 history에서 연차별 자산값, 최종점=세후 end_value) → 단일(`accumulation_analyzer`)·멀티(`multi_account_analyzer`) 둘 다 case에 `_yearly` 부착 → `calculator_logic._build_fan`이 p1~p99×(연차+1) 퍼센타일 그리드 산출(서버 사전계산 → 슬라이더 서버 재호출 0, 표본<5면 None). 응답 `fan` 키, `_yearly` 원본은 cases_summary에서 누락(페이로드 보호). **프론트:** `calculator.html` 부채꼴 카드(canvas+듀얼슬라이더), `style.css` 듀얼레인지 CSS, `calculator.js` `renderFan`/`onFanSlider`/`_drawFan`(Chart.js line, fill:'-1' 밴드 채움). 캐시 `?v=20260614fan`. 검증 = `tests/test_fan_logic.py` **15 PASS**(궤적·그리드·단조·표본부족) + `tests/test_fan_dom.js` **jsdom 12 PASS**(밴드 선택·슬라이더 보정·숨김) + 실데이터 통합(SPY 단일 229윈도우·2계좌 멀티 202윈도우 fan 정상·year0 밴드폭0·단조) + ✅ **커밋(39afaaa)·push·배포·`tests/test_fan_live.js` 라이브 7 PASS**(프로덕션 실 Chart.js 렌더 + 실 슬라이더 oninput 밴드 갱신 + 콘솔에러 0, fake fan 주입 방식). **▶ 다음 = PHASE4 잔여(D1·D2·C1·C2·B4) — 오너 결정.**

> ✅ **2026-06-14 업데이트 80 (투자계산기 롤링 차트 보기 전환 — 최종자산/CAGR/연도별, 배포·라이브 검증 완료):** 오너 요청 = 롤링 차트 위 버튼 3개. **기본=최종자산(수익률 낮은순 정렬)** / **CAGR(수익률순·음수 빨강)** / **연도별(기존 시작 시점별)**. 이중 Y축 논의했으나 월적립 시 CAGR↔최종자산 1:1 비성립 발견 → 단일 Y축 3모드로 분리(오너 결정). `renderRollingChart`를 상태화(`_rollingCases`/`_rollingMode`) + 신규 `setRollingView(mode)`(정렬·라벨·색상·제목·버튼 active 전환), `_renderRolling` 내부 렌더. 데이터 무변경 — case별 `cagr` 이미 응답에 존재(`calculator_logic.py:400`). `calculator.html` 차트 카드에 `.rchart-head`+`.rchart-seg` 버튼, `style.css` segmented 버튼 CSS, 캐시 `?v=20260614rollview`(calculator.js + style.css). 검증 = `tests/test_rolling_view_dom.js` **jsdom 9 PASS** + ✅ **커밋(62a3a04)·push·배포·`tests/test_rolling_view_live.js` 라이브 11 PASS**(실 Chart.js 렌더 + 실 onclick 클릭 + 정렬·색상·제목·버튼 active·콘솔에러 0, fake cases 주입 방식). **▶ 다음 = 몬테카를로 부채꼴(계산기行 경험적 밴드 추천) / PHASE4 잔여 — 오너 결정.**

> ✅ **2026-06-14 업데이트 79 (비교탭 축선택·지표설명 + 백테 연간배당 차트 + 계산기/백테 지표설명):** 오너 후속 5건. ① 비교탭 스파이더 **축 종류 선택**(7후보·최소3) ② 축 옆 **설명 1-2줄** ③ CAGR→**수익률(CAGR)**+수치표 hover ④ 계산기·백테 **지표 설명** ⑤ **백테 연간 배당금 차트**(`backtest_logic` 두 경로에 `annual_dividends` 추가 + `backtest.html` 막대차트·`renderAnnualDividendChart`). 계산기 히스토그램 9카드에 `.result-card-desc`, 백테 btMetrics hover ⓘ. 검증 = run_backtest_logic(SPY 2018~23) annual_dividends 합계=total 일치·JS OK. ⚠️ 실브라우저 미검증·배포 진행. **▶ 다음 = 실브라우저 확인 / 몬테카를로 부채꼴(추후) / PHASE4 잔여 — 오너 결정.**

> ✅ **2026-06-14 업데이트 78 (포트폴리오 비교 탭 — 리스크-리턴 확장):** 오너 = 포폴끼리 비교. 브레인스토밍 후 스파이더+몬테카를로 채택했으나 **몬테카를로는 대공사라 제외**(추후). 기존 `/risk-return`을 **"포트폴리오 비교"**(📊)로 확장. **내 포트폴리오 체크박스 선택 + 벤치마크 칩(기본 SPY·QQQ·GLD·069500·TLT, 삭제/검색추가) + [비교하기]** → ① **11지표 수치표**(CAGR·변동성·MDD·Sharpe·Sortino·배당률·최고/최저연·승률·베타) ② **리스크-리턴 산점도** ③ **레이더 6축**(CAGR·안정성·방어력·배당률·Sharpe·Sortino, 상대 정규화·클수록 좋음, 항목별 표시토글+투명도 슬라이더) ④ **🔗링크/📷이미지 저장**(계산기 share 재사용). 백엔드 `risk_return_logic._metrics_full`+`compute_comparison`(베타기준 SPY 항상로드·배당률=직전1년÷종가 비중가중) + `POST /api/portfolio/compare`. 공통 겹침 기간 자동(3년미만 경고). 검증 = compare(2포폴+벤치) 200·**SPY베타1.0 sanity·TLT혼합0.62·QQQ MDD-80%·GLD배당0**·페이지200·JS OK. ⚠️ **실브라우저 미검증. 배포 진행.** 계획=`포트폴리오비교_plan.md`. **▶ 다음 = 실브라우저 확인 + (추후 몬테카를로 부채꼴) / PHASE4 잔여(D1·D2·C1·C2·B4) — 오너 결정.**

> ✅ **2026-06-14 업데이트 77 (저장 포트폴리오 상세 — 총투자금액→비중 자동배분→추이·배당 + 내자산 배당일정 월별칸·홍보문구 강조):** 오너 요청 3건. ① "내 포트폴리오" 저장 카드 클릭 → **내자산 같은 상세 페이지**(`/myportfolios/<id>`, `portfolio_detail.html`). **총 투자금액 1칸만 입력**(맨 위, 카드는 항상 표시) → 저장된 비중대로 자동 배분(수량=총액×비중÷현재가) → 비중 파이·자산 추이(1M/3M/1Y/전체)·배당금(세전후·원외화·연도탭·막대드릴·**월별 네모칸**·일정 리스트). ② 내자산 배당 CTA(백테/계산기 유도) 너무 작음 → `#divCta` **강조 박스**(0.92rem·연파랑 배경/테두리·💡, 튀지 않게). ③ 내자산 배당 일정 = **12개월 네모칸**(월 합계 표시) 클릭 시 그 달 종목별 펼침 표. **백엔드(app.py)** = `_compute_portfolio_history` 헬퍼 추출(기존 history 재사용) + `_amount_to_holdings(amount, tickers[{code,weight}])` 공통 헬퍼 + 신규 `/api/portfolio/item/<id>`·`/compute`·`/dividends-preview`(내자산 `build_dividend_chart` 동일 엔진). `auth_manager.get_portfolio` 추가. 금액=클라 localStorage 보관(서버 스키마 무변경). **※ 1차는 종목별 수량 입력이었으나 오너 피드백으로 총액 단일입력 모델로 재설계(커밋 8381638→재설계).** 검증 = venv test_client: item/페이지 200, compute(10M·60/40 → 수량 5.297·history keys·금액0→empty), dividends-preview(458730 → 2026 12이벤트, events 키 JSON 문자열·JS 자동변환 정상), history 회귀 200, JS `node --check` 3파일 OK. ⚠️ **실브라우저(Playwright) 미검증. 배포 진행.** **▶ 다음 = 실브라우저 확인 후 PHASE4 잔여(D1·D2·C1·C2·B4) — 오너 결정.**

> ✅ **2026-06-14 업데이트 76 (내자산 월별 배당금 차트 — myassets):** 오너 요청 = 내자산 탭 자산추이 밑 배당금 차트(내포트폴리오→백테/계산기 화면은 보류). 여러 차례 피드백 반영해 최종형 도달. **연도 선택기**(과거 3년 실적 + 올해=실적+예측 혼합 + 내년=전체 예측) → 단일연도 **12개월 막대**(월별 실적 파랑/예측 주황) → **막대 클릭 시 하단 종목별 드릴다운** → **배당 일정 리스트**(종목별 1행 집계: 연 합계+지급월+예측배지) → **세전/세후 × 원화/외화 토글**. 예측 = 종목별 최근 5년 배당 CAGR(올해 빈 달·내년 = 직전연도×(1+CAGR)^k). FX = 과거 ex-date 환율·미래 현재환율. 세후 = 일반 KR15.4%/US15%·ISA·연금·IRP 비과세. 가정(현재 보유수량) + 정밀분석은 백테/투자계산기 유도 안내. **이벤트 기반 백엔드** `modules/dividend_history.py`(`build_dividend_chart`) + `/api/myassets/dividends`. 검증 = `test_dividend_history.py` **7 PASS** + `test_dividend_chart_browser.js` **16 PASS**(로컬 로그인, mint_session) + 라이브 API 401 게이팅·배포 확인. 커밋 fb50d2c→7ffa32b→305862d→439ee65. **▶ 다음 = PHASE4 잔여(D1 TDF·D2 연금통합·C1 watchlist·C2 자산군비교·B4 거래트래킹) — 오너 결정.**

> ✅ **2026-06-14 업데이트 75 (A4 종목 상세 개선 — symbol.html):** PHASE4 A4 완료. **분류** = `get_symbol_data`가 symbol_master is_etf+country로 `asset_type`(INDEX/CRYPTO/KR_ETF/KR_STOCK/US_ETF/US_STOCK) 산출(6자리=무조건 ETF 오분류 해소) + 타입별 지표 분기(주식 시총/PER/PBR/섹터 vs ETF 운용사/보수율/AUM). **차트** = Lightweight Charts 라인/캔들 토글 — **라인 탭=표시기간**(1일/1주 시간봉, 1개월~전체 일봉), **캔들 탭=캔들 1개 간격**(1시간/1일/1주/1개월/1년, 기간 항상 전체). 캔들 간격별 **기본 배율**(1시간 1~2일·1일 ~75일·1주 1년·1개월 ~7년·1년 전체) + **거래량 히스토그램** + **⛶ 전체화면**(Fullscreen API). 1시간봉 = yfinance 1h 730일 fetch(`get_intraday_data range=max`, 신규 `price_hourly` 테이블) + 730일 한계 안내문구. 검증 = `test_symbol_api.py` 8 PASS + `test_symbol_browser.js` **31 PASS**(로컬·라이브 둘 다) + 라이브 23~31 PASS. 커밋 fddaa51→51c5d0c→bf4e88e. **▶ 다음 = A4 완료, PHASE4 잔여로.**

> ✅ **2026-06-13 업데이트 74 (D4 fast-follow ② 은퇴·배당 거래수수료 롤아웃 — 배포완료):** 오너 결정 = 은퇴+배당 둘 다, 은퇴 fee = **적립+인출 양 단계**. fee 미배선이던 은퇴·배당 탭에 거래수수료 배선(계산기·백테는 ①까지 완료). **은퇴 적립** = AccumulationAnalyzer·MultiAccountAnalyzer(이미 fee 파라미터 보유) → retirement_logic이 fee_rate·stock_tickers 전달. **은퇴 인출** = WithdrawalAnalyzer에 fee_rate/stock_tickers 신규 배선(SimulationConfig·Portfolio 주입 + total_fees surface), RetirementPlanner가 적립+인출 합산. **멀티 가구인출** = multi_account_withdrawal `_build_account_runtime` Portfolio fee + window/rolling/samples total_fees 스레딩. **인출기 탭(standalone)** = run_withdrawal_logic 단일·멀티 fee 패스스루(은퇴와 같은 wd 엔진 공유 — UI가 retirement.html 2모드라 일관 필요). **배당** = dividend_simulator `_simulate_one` Portfolio fee + `_fees_cache`/`get_total_fees`(실데이터 윈도우 중앙값; **합성 경로는 거래 없는 순수 자산수학 → fee 미적용, 기술 강제**), MultiDividendSimulator는 MultiAccountSimulationLoop per-account fee + stock_tickers. dividend_logic 단일·멀티 total_fees surface. **UI** = retirement.html·dividend_target.html에 거래수수료 섹션(opt-in+프리셋+율%) + toggleFeePanel(멀티 재렌더)·renderFeeSummary·payload fee_enabled/fee_rate + 계좌 payload 빌더 per-card fee_rate(공용 `_mmFeeField`가 feeEnabledChk로 카드 노출). 검증 = `test_d4_fee_retire_div.py` **3 PASS**(배당 단일·멀티 fee 흐름·≤ 불변식, loader 패치 결정론) + 변경 모듈 기존 타겟 **74 PASS**(fee=0 회귀 무변경: g5 인출·적립·가구·연금·배당·인출CG세·portfolio_fee·d4_fee) + Python·템플릿 JS 문법 OK. ✅ **배포(cfee467)·라이브 probe 3 PASS**(배당 단일 fee 배너 ₩87,410·은퇴 단일 fee 배너 ₩78,338·콘솔에러 0 — 두 엔진 fee 라이브 흐름 확인, 스샷 육안 확인). **공유 엔진 변경이라 전체 회귀(pytest tests/)는 오너 확인 후 실행 대기.** **▶ 다음 = D4 전 5탭 완료 → D1 TDF/D2 연금통합(7월) OR PHASE4 잔여(B2-a·A4·C1·C2·B4) — 오너 결정.**

> ✅ **2026-06-13 업데이트 73 (D4 fast-follow ① 계좌별 거래수수료 UI):** 탭레벨 v1(전 계좌 공통율)을 **계좌 카드별 수수료율 입력**으로 확장(증권사 계좌마다 다름 반영). 백엔드는 이미 계좌별 `fee_rate` 수신·집행(`multi_account_loop` L634→`Portfolio.buy/sell`, normalize 폴백). UI = 공용 `multi_account_ui.js`에 `_mmFeeField`(증권사 프리셋 키움/삼성/토스/직접 + 율% 입력) 추가 — **`feeEnabledChk` 켜진 경우에만 렌더** → 그 체크박스 없는 은퇴·배당 탭은 자동 미표시(미배선 보호). 상태 `acc.fee_rate_pct`(%), 미지정이면 탭레벨 입력 시드. `toggleFeePanel`(계산기·백테)에 멀티계좌 재렌더 추가, payload 빌더 2곳(`buildCalculatorAccountsPayload`·백테)이 계좌마다 `fee_rate`(decimal) 부착(opt-in 시). 캐시버전 `?v=20260613feecard2`(multi_account_ui 4탭+calculator.js; feecard2=직접입력 시 프리셋 라벨 동기화 fix 8d621e4 포함). 검증 = 신규 `tests/test_fee_card_dom.js` **jsdom 16 PASS**(fee OFF→필드 미표시·ON→프리셋+율 렌더·탭 시드 기본·프리셋 selected·계좌별 상태 갱신·음수 클램프·프리셋 DOM 동기화·custom 무변경) + `test_d4_fee_logic` **4 PASS**(신규 2 = normalize 계좌별 우선·disabled→0) + JS 문법 OK. ✅ **배포(61e0993)·라이브 probe 6 PASS**: per-card(`probe_fee_percard_live.js` 3 PASS — 2계좌 카드별 입력 렌더·차등율(계좌1 0.015%/계좌2 0.5%) 실행 총수수료 ₩194,705·콘솔에러 0) + 탭레벨 회귀(`probe_fee_live.js` 3 PASS — 계산기 ₩23,514·백테 ₩2,002 무변경). **잔여 fast-follow ② 은퇴·배당 탭 롤아웃(백엔드 미배선).** **▶ 다음 = fast-follow ②(은퇴·배당 fee 롤아웃) OR D1 TDF/D2 연금통합(7월) OR PHASE4 잔여 — 오너 결정.**

> ✅ **2026-06-13 업데이트 72 (D4 거래수수료 — 계산기·백테, 탭레벨 v1):** 오너 결정 = 계산기+백테 먼저·수수료율 1개 통합·슬리피지 X·프리셋+직접·국내주식 매도세 0.18%·총수수료만·기본OFF, UI는 탭레벨 v1(전 계좌 공통율). 수수료 미배선(`fee_engine` 데드)이던 것을 `Portfolio.buy/sell` 최저 집행층에 주입 → 전 runner 자동 커버(매수 cost×율·매도 proceeds×(율+거래세), 개별주식만 거래세 0.18%, `total_fees` 누적, 기본0=무변경). 배선 = taxable_runner·multi_account_loop(계좌별)·portfolio_engine·SimulationConfig·AccumulationAnalyzer·MultiAccountAnalyzer 패스스루+total_fees(중앙값). `build_stock_tickers`(국내주식 거래세 대상). logic = body fee_enabled+fee_rate→엔진, 결과 total_fees. UI = 계산기·백테 "거래수수료" 섹션(opt-in+프리셋 키움/삼성/토스/직접+율%)+결과 하단 "총 지불 거래수수료 ₩X"(calculator.js v20260613fee). 검증 = `test_portfolio_fee` 6+`test_d4_fee_logic` 2 PASS+멀티 회귀 50 PASS(fee=0 무변경) + **배포(7dd9224)·라이브 probe 3 PASS**(`probe_fee_live.js`: 계산기 ₩23,514·백테 ₩2,002 배너·콘솔에러 0). **잔여(fast-follow): 계좌 카드별 수수료·은퇴/배당 롤아웃.** **▶ 다음 = D2 연금통합 OR D1 TDF(7월) OR PHASE4 잔여 — 오너 결정.**

> ✅ **2026-06-13 업데이트 71 (납입 한도 초과 = 차단 → soft 경고):** 오너 결정 = 연금/IRP/ISA 연납입 한도 초과 설정 시 에러로 막던 것을 **안내 + 진행여부(예/아니오) + "오늘 하루 다시 묻지 않기" + 결과 하단 경고 배너**로 교체(4탭 공유). 백엔드 = `modules/multi_account_common.py`에 `collect_limit_violations`(위반 전수: ISA 2천만/계좌, 연금+IRP 합산 1,800만, 초기자본은 라우팅 무관·월납은 OFF만) + `enforce_contribution_limits`(override 없으면 `limit_confirm` raise, 있으면 경고 반환). calculator/retirement/backtest/dividend_logic 단일+멀티 전부 옛 하드체크(`validate_isa_contribution`·`_validate_initial_capital_limits`·연금 단일 raise) → 교체, 결과에 `limit_warnings` 동봉. 프런트 = 신규 `static/js/limit_guard.js`(`window.MMLimit`: confirm 모달+오늘하루스킵 localStorage, parseError, 결과 하단 배너 attach) + 4탭 `run*()`에 override 인자·재요청 배선·script 포함(`?v=20260613lim`). 정리 = 죽은 옛 에러 핸들러·고아 import 제거, 옛 테스트 import 재지정(함수·테스트 보존). 검증 = 신규 `tests/test_limit_soft_warning.py` **3 PASS**(수집기 룰·override 왕복·dividend 통합) + 옛 `test_l2` PASS + import/JS 문법 OK. ✅ **배포(25d4009)·라이브 probe 6 PASS**(계산기: 모달 위반문구·예→override→배너·아니오 닫힘·오늘하루스킵·스킵당일 모달생략·콘솔에러 0, `probe_limit_soft_live.js`+스크린샷 3종) · **3탭(백테·은퇴·배당) probe 4 PASS**(`probe_limit_soft_live3.js`: 각 탭 모달→예→배너) = **4탭 전부 라이브 검증 완료** · `?v=20260613lim` 라이브 서빙. **▶ 다음 = D1 TDF/D2 연금통합(7월 일정) OR PHASE4 잔여 — 오너 결정.**

> ✅ **2026-06-13 업데이트 70 (배당계산기 멀티계좌 G5-E — 멀티계좌 5탭 전부 완성):** 오너 결정 = 자동 역산 지원(역산 변수=계좌1) + G2 풀 라우팅. 신규 `dividend_multi.py` = `DividendSimulator` 서브클래스(역산 레이어 상속, `_simulate_one`만 `MultiAccountSimulationLoop` 월별 주입·무청산), 합성 폴백 = 계좌별 합. logic = backtest 패턴 미러(한도·규제·정책). UI = 공용 카드 이식(+계좌 즐겨찾기 자동), dtAccount 라디오 제거, 멀티 자동 노트, 절세 패널 계좌별 분해. 검증 = 손계산 7(정합 앵커·합산·역산변수·개인합산·**ISA cascade**·절세 불변식·logic) + 브라우저 13(실DB 86윈도우) PASS + 스크린샷. **▶ 멀티계좌·절세 = 전 탭 마감. 다음 = D1 TDF/D2 연금통합(7월 일정) OR PHASE4 잔여 — 오너 결정.**

> ✅ **2026-06-13 업데이트 69 (P4 배당탭 절세액 3종 — 절세액 전 탭 완성):** 무청산 규약(wd 동일 — 미실현 양쪽 미가산 = 위탁 불변식). 엔진 = `_GrossRecordingDividendEngine` gross 가로채기 + `_run_rolling` 병행 `_savings_cache`(실측 윈도우만) + `get_savings_summary` p50. 배선 = 응답 `savings`(대표 콤보, 역산이면 solved 값). **발견: sync `/scenario` 라우트가 세금 미배선 인라인 stale → dividend_logic 위임 통일.** UI = 공용 포맷 패널 + 배당탭 각주. 검증 = 손계산 4(위탁 불변식·ISA Σgross×15.4% 독립재현·p50/합성제외·배선) + 실브라우저 7(ISA 절세 321만/실제 0·위탁 0/209윈도우) + 타겟 15 PASS. **▶ 절세액 P1~P4 완성. 다음 = 배당탭 멀티계좌(G2 확장) OR PHASE4 — 오너 결정.**

> ✅ **2026-06-13 업데이트 68 (배당계산기 엔진 통합 — divrefactoring 완료, P4 선행):** 오너 결정 = 게이트 방식. **루프 무변경 월별 모드**(신규 `monthly_mode.py` — 월말 리샘플 주입) 발견으로 plan 공정 축소. 게이트 = 실데이터 40윈도우: 속도 세금ON **x2.14**(≤5) · 드리프트 중앙 1%/최대 3.3%(≤5%) **PASS** — 신엔진이 정확한 쪽(ex-date 정합 + 리밸 양도세 실부과). `_simulate_one`만 메인 엔진 조립으로 교체(자체 루프 ~120줄 제거, 상위 역산/캐시/합성 무변경). **보너스: `_classify_kr_etf` sqlite 캐시 — 전 탭 세금 시뮬 ~10배 가속.** 검증 = monthly_mode 6(진리값 앵커 ±5원) + 세금 영향권 35 + 시나리오 풀플로우(확률 3.2s·역산 1.91억/34s). **▶ 다음 = P4 본체(배당탭 절세액 3종 표시) → 배당탭 멀티계좌(G2) 후보.**

> ✅ **2026-06-12 업데이트 67 (리스크-리턴 도표 — P3 완료):** 오너 결정 = CAGR+일간√252(총수익)/공통 겹침 기간/고정 5종+사용자 추가/독립 페이지. 신규 `risk_return_logic.py`(고정비중 일별 근사, 현금 드래그·정규화·skipped 제외) + `POST /api/risk-return` + `/risk-return` 페이지(scatter, 벤치마크 칩 추가, 3년 미만 ⚠). 검증 = 손계산 7 PASS(FakeLoader) + 로그인 E2E 8 PASS(실DB) + 스크린샷. 벤치마크 영속화는 후속(세금설정 json 충돌 회피). **▶ P3 리스크리턴 마감 — 다음 = P4 배당 절세 OR PHASE4 잔여(D1/D2/A4/C1/C2) — 오너 결정.**

> ✅ **2026-06-12 업데이트 66 (멀티계좌 카드 즐겨찾기):** 세금 ON+계좌 추가 시 계좌별 종목 입력에 `★ 즐겨찾기 불러오기` select(`multi_account_ui.js` 공용 — 3탭+wd 자동). 첫 렌더 1회 로드+포커스 재조회, `_mmEsc` XSS 가드, 캐시 fav2. 검증 = E2E 18 PASS(계좌 카드 표시·불러오기 60/40·행 렌더 추가) + 스크린샷. **▶ 다음 = 리스크리턴도표 OR P4.**

> ✅ **2026-06-12 업데이트 65 (내 포트폴리오 관리 페이지 + 자산구성 파이차트):** 오너 요청 2건. ① **`/myportfolios` 신규** — 사이드바 "⭐ 내 포트폴리오"(내 자산 위). 즐겨찾기 카드 목록·생성/수정 모달(종목검색+비중+균등분배)·삭제. 기존 `/api/portfolio/*` 재사용(백엔드 변경 = 라우트 1개). ② **자산 구성 bar→pie** (`renderWeightChart`): 260px 래퍼+maintainAspectRatio:false, legend right/모바일 bottom. **검증:** 신규 `test_myportfolios_browser.js` **15 PASS** = 실서버+실DB 로그인 E2E(`mint_session.py` dev 쿠키 서명으로 OAuth 우회) — 게이팅/생성/수정/계산기 ★ 연동/삭제/파이 type·데이터/JS에러 0 + 기존 fav 스위트(31+20+5) 재PASS + 스크린샷 육안. 전체 pytest는 오너 지시로 미실행(타겟만). **▶ 다음 = 리스크리턴도표 OR P4.**

> ✅ **2026-06-12 업데이트 64 (B1 포트폴리오 즐겨찾기 — 5탭 공용 위젯, PHASE4 착수):** 오너 결정 = 종목+비중 1세트 / 로그인 전용 / 5탭 전부 / 한도 20(`get_portfolio_limit()` 단일 변경점, 요금제 차등 대비). **구현:** `saved_portfolios` 테이블+CRUD(`auth_manager.py`) / `/api/portfolio/list·save·DELETE`(myassets 401 패턴, 이름 1~50자·종목 1~30개 검증) / 신규 공용 위젯 `portfolio_favorites.js`(`MMFav.init`, 규약=[{code,name,badge,weight%}], 동명 confirm 덮어쓰기, 비로그인 비활성+안내, XSS 가드=textContent 전용) / 5탭 배선(계산기·배당·ISA전환=% 그대로, 백테·은퇴=0~1 변환 어댑터). **검증 4층:** API 5 PASS(401·왕복·400 7케이스·한도 신규만 차단·소유권 격리, 임시 DB) + jsdom 20 PASS(XSS·깊은복사·payload 규약) + Playwright 로컬 31 PASS(5탭 렌더·JS에러 0·**어댑터 왕복**=불러오기→상태→저장 payload % 재변환) + **전체 회귀 255 PASS**(250+5) + 라이트/다크/모바일 스크린샷 육안 정상. ⚠️ 로그인 실계정 플로우만 오너 육안 잔여(OAuth 자동화 불가). **▶ 리스크리턴도표 선행조건 해소 — 다음 = 리스크리턴도표 OR P4 배당 절세.**

> ✅ **2026-06-12 업데이트 63 (GAP-DECUM-COMP 해소 확인 — 감사 항목 stale, 구현 없이 검증으로 종결):** 오너 보류 해제 후 코드 점검 — **C3.2(89c927a)부터 decum도 종합과세 기배선이었음**(공유 `TaxSessionState`: 위탁 배당 gross + KR_FOREIGN 인출/리밸 매도차익 한 풀 합산 → 2천만 초과분 가산, 연도 리셋·계좌간 개인 합산 포함). 감사(06-09) 주장 "배당 2천만 초과해도 가산 안 함"은 코드 실상 불일치. **검증 = 신규 `tests/test_decum_comprehensive.py` 4 PASS**(① 연 3천만+근로 1억 2개년: 종료값==after_tax_dividend 순차 재현 ±1원+가산 실발생 ② 임계 미만 플랫 15.4% ③ 2계좌 합산 2,880만: 합동<단독합 ④ KRF 차익: 타계좌 배당이 임계 채우면 actual_tax 증가) + **전체 회귀 250 PASS**. 잔여 = other_financial_income 베이스라인(프런트 미전송 설계) → 기존 "전탭 자동산출" 항목 귀속, decum 고유 갭 아님. bugs.md·roadmap·README 동기화. 엔진 코드 무변경(테스트만 추가) → 배포 영향 없음. **로드맵/감사 stale 4번째 — 착수 전 코드 실상 grep 필수.** **▶ 다음 = P3 포트폴리오 즐겨찾기(B1) OR P4 배당금계산기 절세 — 오너 결정.**

> ✅ **2026-06-12 업데이트 62 (절세액 P3 마감 — 인출기(wd) 절세 3종 패널, 오너 결정):** P2/P3 실상 점검(오너 지시) — **P2 백테스트·P3 적립기/연금수령세는 G5 복제 + 06-03 결정으로 기완료**, 유일 갭 = 인출기 절세 패널 → 오너 결정 "구현". **엔진:** ① `sell_with_tax` 직접호출(인출 매도)도 위탁가정 `_brk_*` 누적 — execute_orders 경로는 기존 `_accrue`와 `_suspend_brk_accrual` 플래그로 이중집계 방지 ② `simulate_household_window`: gross 배당 분류별·배당세·계좌별 연금소득세 누적 → per_account 절세 3종(위탁가정·실제·절세) ③ **설계 핵심: wd는 무청산(end_value=gross)이라 잔여 미실현 미가산** — 적립(_finalize)과 달리 양쪽 다 청산 제외해야 위탁 불변식(절세0) 유지 ④ `analyze_household_withdrawal`: 계좌별 p50 + 합산(적립 규약 동일) → `savings`. retirement_logic wd 응답 + retirement.html wd 모드 렌더(공용 패널) + wd 전용 각주("실제 세금에 연금소득세 포함"). **검증:** 신규 `tests/test_l_save_wd.py` **6 PASS 손계산 ±1원**(위탁 불변식=신규 누적이 실제 과세와 정확 일치 증명 / 연금세 월 58,201.06원×12 / ISA 배당 절세 77,000원 / 혼합 / 세금OFF 무변경) + **전체 회귀 246 PASS** + 실데이터 로컬(위탁3억[미실현1억]+연금2억 10y: 위탁 절세 0 ✓·연금 절세 630만·survival 1.0) + jsdom 렌더 4체크 PASS(`tests/check_wd_savings_dom.js`). ✅ **커밋(90649dc + 캐시버스팅 f670e51)·push·배포·라이브 probe PASS** — `probe_wd_savings_live.js`(위탁3억[미실현1억]+연금2억, 월200만, 30y): 패널 렌더·wd 각주·API savings·위탁 불변식 0·합산=Σ계좌 전부 ✓, 스크린샷 육안 정상. 라이브 p50 절세 0 = 연금소득세(전액 분리과세)가 위탁가정(배당+실현차익)보다 큰 케이스 — 0 하한 클램프 정상 동작(설계 의도: 인출 페이즈 연금은 위탁보다 불리할 수 있음을 정직하게 표시). **▶ 절세액 P1~P3 완전 마감(P4 배당금계산기만 보류). 다음 = P3 포트폴리오 즐겨찾기 OR 기타 — 오너 보고 후.**

> ✅ **2026-06-12 업데이트 61 (ISA 전환 계산기 신규 — P1 세금계산기, 로컬 검증 완료·배포 대기):** 오너 결정 = **(a) 분할 이전 모델 + 독립 페이지**(plan ⏳ 항목 해소). 신규 `/tax-switch`: "위탁 유지(A) vs 매년 ISA 한도만큼 분할 이전(B)" 세후 정면 비교. **선행 정리:** 로드맵 stale 발견·수정 — "다음=금종세(2e)"는 **Phase 2f로 이미 완료(4100ecd, 05-31)**였음 → 자동으로 세금계산기(P1)가 다음. **엔진:** `MultiAccountSimulationLoop` 확장(전부 optional·기본 OFF=기존 G경로 무변경) — ① 계좌 `carried_cost_basis`(취득가 주입: day-0 매수 후 avg_cost 비례축소) ② `switch_policy`(연 1회 위탁 비례매도 `sell_with_tax`→세션 합산 종합과세 정확→순현금 ISA 이전, `ContributionLimitTracker` 연2천만/총1억, ISA 원금=cycle_contribution) ③ `yearly_after_tax_snapshot`(연말 가상청산 세후 — breakeven 입력). Analyzer 패스스루 + 신규 `tax_switch_logic.py`(A/B 동일 롤링 윈도우 페어, p25/50/75·전환세·breakeven·세후궤적·대표 이전스케줄). API `/api/tax-switch/submit·run` + celery task. UI 독립 페이지(검색·비중·평가액/취득가/기간·Chart.js A vs B·이전계획 표·다크/모바일·nav/sidebar 추가). **검증:** 신규 `tests/test_tax_switch.py` **8 PASS 손계산 ±1원**(A 일괄 46,150,000 / B 분할 47,250,000=250만 공제 3회, 차이 정확히 110만 / KR_FOREIGN flat A==B / 차익0 불변식 / 손실 전환세0 / 총1억 한도 5년 중단·잔여 영구위탁 / 연말 스냅샷 / 기본 OFF 무변경) + **전체 회귀 240 PASS**(Gate 2a/2b/2c·tax_truth·phase2f·trackG 전부) + 실데이터 로컬(458730 5천만/3천만 5y: 686윈도우, B +405만, breakeven 1년차 98%) + 로컬 Playwright 스모크(검색·추가·다크·모바일, JS에러 0) + `test_responsive_dark.js`에 `/tax-switch` 추가 → **186 PASS / 0 FAIL**. ✅ **커밋(c65cf80)·push·Hetzner 배포·라이브 검증 완료** — 신규 `tests/e2e_multitax/live_tax_switch.js` 풀플로우(검색 458730→입력 5천만/3천만/5y→실행→결과) **PASS**: 서버 212윈도우, B +49만(8,249만→8,292만), 전환세 340만, **breakeven 4년차(84% 시나리오)** — 1~3년차 A 우세(전환세 드래그)→4년차 역전, API 불변식·콘솔에러 0·결과 스크린샷 육안 정상. **▶ 세금계산기(P1) v1 완료. 다음 = 로드맵 잔여(P2 절세액 P2/P3 OR P3 포트폴리오 즐겨찾기) — 오너 보고 후.**

> ✅ **2026-06-11 업데이트 60 (GAP-RET-KRDATA 해소 ①②③ + race 가드 — E2E 16/16 PASS, P0 L7 완료):** update 59의 발견 2건 전부 종결. **조사:** 서버 SSH 실측으로 ⑴ BUG-WD-MULTI-LIVE 생존율 0% = 일시현상(합성 생성 run 12:12:51 = E2E 실행 중, race 물증) ⑵ 458730 장기경로 = `build_djdiv_proxy.py` 의도된 설계(^GSPC 세그먼트 제거, pre-DVY는 합성) — **낡은 건 로컬 DB**(구체인 1928~ 잔존, 로컬-서버 괴리 원인) ⑶ 합성↔실측 경계 연속(anchor 수정 유효). **수정(9486eee, 오너 결정 셋다+가드):** ① 은퇴 탭 가상데이터 체크박스+`use_synthetic` 배선 ② 인출 투영 prep을 적립과 별도로 인출기간 기준 호출(성능 보존) ③ 실윈도우 0개 → 전량 GBM 합성 폴백(단일·멀티) + "실측 N+가상 M" 라벨 + `simulate_household_window` 리딩 NaN/부분데이터 가드. **검증:** 신규 회귀 3종+기존 104 PASS, 로컬 브라우저 스모크 4 PASS, 라이브 C1 probe 해소 + E2E C·D 재검 7/7 → **16건 전부 PASS = L7 실데이터 통합검증 완료.** 잔여(소): cleanup 스크립트 stale provenance·로컬 DB 재빌드·DB 합성 경로 다양화(9.4 후순위). **▶ 다음 = 금융소득 종합과세 완전 구현(Phase 2e) OR 세금계산기(P1) — 오너 결정.**

> 🔍 **2026-06-11 업데이트 59 (다계좌 세금 E2E 16건 실행 — P0 L7 실행판, 버그 2건 발견):** `다계좌세금_E2E검증_plan.md` 16건을 신규 `tests/e2e_multitax/`(Playwright, 진짜 클릭+API 캡처+불변식)로 라이브에서 전부 실행. **11 PASS / 4 FAIL / 1 SKIP**(B2 재검 포함, ~5분, 콘솔에러 0). **계산기 6/6·백테 3/3 전부 PASS**(멀티 분포·절세액·ISA 한도 서버차단·세액공제 1,205만·금종세 자동판정·ON≤OFF 불변식·단일 회귀). 인출기 D1(UI 배선)·D3(단일 ON 70%≤OFF 84%) PASS. **FAIL 4 = 발견 2건(즉시 수정 금지 규칙 → bugs.md 등록 + 오너 보고):** ① **GAP-RET-KRDATA**(C1·C2·C3): 은퇴 sim이 국내상장 ETF+기본값(적립20y+인출30y)에서 "롤링 윈도우 0개" 하드에러 — 은퇴 탭 synthetic 체크박스 부재(`allow_synthetic` 항상 False)+데이터 범위가 적립 기준 → ISA·연금(국내상장 의무)과 구조 충돌. ② **BUG-WD-MULTI-LIVE**(D2·D4): 인출기 멀티(위탁3억+연금2억·월200만·30y)가 생존율 0%·combined p50 0원(전 윈도우 사망), 동일조건 단일은 70% 정상 — 유력가설 BUG-SYNTH-FX 미수정 DB 합성 경로 잔재. mock 기반 L13이 못 잡던 라이브 데이터 경로를 E2E가 잡음. 테스트 설계 결함 1건(B2 ON/OFF 총투입 불일치)은 단일계좌 대조로 수정·재검 PASS. 산출물 `tests/e2e_multitax/results/20260611_result.md`+스크린샷. **▶ 다음 = 오너 결정: GAP-RET-KRDATA 해소 방향(①은퇴 탭 synthetic 옵션 ②데이터 범위를 적립+인출년 기준 ③가구인출 합성보충) + BUG-WD-MULTI-LIVE 조사 착수. 둘 해소 후 C1~C3·D2·D4 재실행 → L7 완료 처리.**

> ✅ **2026-06-11 업데이트 58 (모바일 후속 — 백테스트·내자산 잔여 깨짐 수정):** 오너 실기기 피드백 2건. ① **백테스트 가로 스크롤+우측 여백**: 라이브 Playwright 재현으로 원인 실측 — `.bt-left` min-content 403px(>390 뷰포트). 진범 = `.date-row input[type=date]`가 flex에서 `min-width:auto`라 안 줄어듦 → `min-width:0` + 모바일 `.bt-left max-width:100%` + style.css에 `.main-content > * { min-width:0 }` 일반 가드. ② **백테스트 결과 차트 왜소(300×130 고정)**: canvas `height` 속성+aspect-ratio 모드라 리사이즈 실패 → `.bt-chart-wrap` 고정높이 래퍼(가치 280/연간 220/낙폭 180, 모바일 240/190/160) + `maintainAspectRatio:false` 3곳. ③ **내자산 가로 스크롤**: 보유종목 테이블 9열 → 모바일(≤768px) **종목별 카드 스택**(td `data-label` + CSS grid, 수정/삭제 하단 정렬), 리밸 밴드카드 `flex-wrap:nowrap` 제거+모바일 wrap, `.rebal-row` wrap, 탭 nowrap. **검증**: 라이브 백테스트 실제 실행(SPY) 재현 스크립트로 수정 전 scrollW 447/차트 300×130 실측 → 수정 후 로컬 myassets 주입 검증 overflow 0 + 라이브 배포 후 동일 시나리오 재실행 PASS. 캐시 v20260611ui2.

> ✅ **2026-06-11 업데이트 57 (모바일 반응형 + 다크모드 + UX 개편 — 전 페이지):** 오너 요청(모바일 깨짐·야간모드 부재·UX 불친절). ① **반응형**: style.css에 미디어쿼리 신설(기존 0개) — ≤1400px 상단 nav 링크 숨김(BUG-NAV-1 해소), ≤1024px 사이드바→햄버거 슬라이드 드로어(오버레이+ESC 닫힘), ≤768px 모바일 레이아웃(calc-layout 1열·입력패널 sticky 해제·테이블 가로스크롤·iOS 줌방지 input 16px), ≤480px 로고 아이콘만+로그인 축약. symbol 2열→1열, myassets 탭 풀폭. ② **다크모드**: `html[data-theme=dark]` CSS 변수 팔레트(스시스템 기본 prefers-color-scheme + 🌙 수동 토글 localStorage, head FOUC 방지 스크립트, 토글 시 리로드로 차트 일괄 적용). Chart.js 전역 다크 기본색(charts.js `MM_DARK`/`MM_CHART_GRID`) + html2canvas 공유이미지 배경 테마 연동. ③ **색상 변수화**: 신규 변수(--green-pale/--red-pale/--gold-pale/--blue-soft/--gold-deep/--input-bg/--navbar-bg) + 템플릿·JS 인라인 하드코딩 라이트 색상 ~200곳 var() 치환(share/share_img는 standalone이라 라이트 유지 — share.html 오치환 발견·원복). ④ UX: 죽은 ⚙ 버튼→테마 토글로 교체. **검증**: 신규 `tests/test_responsive_dark.js`(Playwright) — 9페이지×3뷰포트(390/768/1280)×2테마 가로 오버플로우·테마 적용·JS 에러 0 + 드로어 동작 + BUG-NAV-1 회귀 + 테마 토글 = **168 PASS / 0 FAIL** + 스크린샷 육안(홈·계산기·은퇴·세금설정·세금패널 멀티계좌 다크 모두 정상) + 기존 simple calc/dom 60 PASS + 전 라우트 HTTP 200. 캐시 v20260611ui. ✅ **커밋(4ebbfe3)·push·Hetzner 배포·라이브 검증 완료** — 라이브 대상 동일 Playwright 스위트 재실행 **168 PASS / 0 FAIL** + 모바일 다크 스크린샷 육안 정상. 잔여 = 오너 실기기 확인. **▶ 다음 = E2E 16건 OR 세금계산기(P1).**

> ✅ **2026-06-10 업데이트 56 (Playwright 도입 + 다계좌 세금 E2E 계획 + 세션 동기화):** ① **Playwright Chromium 도입**(`package.json` devDeps=jsdom+playwright — npm prune 사고 방지). 이제 Claude가 실브라우저 기동·클릭·스크린샷 직접 가능 → "브라우저 육안 잔여" 항목 자동화 가능해짐. 간편계산기 라이브 실브라우저 검증 10 PASS(`tests/test_simple_tools_browser.js`)로 입증. ② 스크린샷서 **BUG-NAV-1 발견·등록**(navbar 1280px 글자 세로 깨짐 — 링크 9개 overflow, 수정은 모바일 반응형과 함께 결정). ③ **다계좌 세금 E2E 검증 계획 수립** = `다계좌세금_E2E검증_plan.md`(오너 요청): 4탭(계산기 6·백테 3·은퇴sim 3·인출기 4)=16건, 라이브 서버 대상, 진짜 클릭+API 캡처+불변식 판정, 셀렉터 실측 표 포함. **= roadmap P0 L7의 실행판, 실행 대기(~30분).** ④ 세션 동기화: 간편계산기 완료를 ideas/features/dev-status/trackG plan/README 컨텍스트에 반영, GAP-DECUM-COMP 오너 재확인=계속 보류. 커밋 933afe7+. **▶ 다음 = E2E 16건 실행 OR 세금계산기(P1).**

> ✅ **2026-06-10 업데이트 55 (간편 계산기 4종 신규 — P1 quick win, 로컬 검증 완료):** 오너 결정(P0 L7 대신 P1 간편계산기 착수·GAP-DECUM-COMP 계속 보류·4종 전부+복리에 세후/인플레 추가·JS 전용·기존 배당계산기와 별개 신규·출력 자체설계). 신규 `/simple` 페이지 — 탭 4종: **복리**(초기금·월적립·연수익률·연증액률·과세 15.4% 토글·인플레 실질가치)·**배당 재투자**(잼투리식 스노우볼: 시가배당률 일정 가정, 주기(분기/월)마다 평가액×수익률/횟수 → 세후 재투자)·**인플레 생활비**·**실질 구매력**. 전부 **클라이언트 JS 전용**(`static/js/simple_tools.js`, 서버 호출 0, 입력 즉시 재계산) + `templates/simple.html` + app.py 라우트 + base.html nav/sidebar. 계산규약 = 월초 적립·월복리(연율 기하환산)·실질=명목/(1+i)^N. **검증:** 순수함수 손계산 **25 PASS**(`tests/test_simple_tools_calc.js`, 거치식 closed-form 정확 일치·과세 세후율·월초적립 FV 공식·분기/월배당 결합식) + jsdom DOM 스모크 **35 PASS**(`tests/test_simple_tools_dom.js`, 초기렌더 14필드·탭전환·입력→재계산·과세토글 ON/OFF·런타임에러 0) + 전 라우트 8개 HTTP 200 회귀(base.html nav 무손상). (Claude) ✅ **커밋(fe7c7af)·push·Hetzner 자동배포·서버검증 완료** — 라이브 /simple HTTP 200(20,617B)·JS 파일 로컬과 바이트 동일·전 페이지 nav 링크·4패널 존재 확인. ⚠️ 브라우저 육안만 남음(오너 직접 확인 권장). **▶ 다음 = 세금계산기(P1) OR L7 실데이터검증 OR 타작업.**

> ✅ **2026-06-09 업데이트 54 (G5-D 은퇴 인출기 멀티계좌+세금 배선 구현 완료):** 설계(53) 구현. 오너결정=공통 리밸(wdRebal/wdBand 상단). **백엔드(`retirement_logic.py`):** `run_withdrawal_logic` `accounts>1` 분기+신규 `_run_multi_account_withdrawal_logic`(시작목돈=입력, `analyze_household_withdrawal` 직접호출, cost_basis=목돈−미실현차익(위탁·세금ON; else None), 공통 rebal, 반환=multi_account.accounts[].distribution.end_value+combined_summary(survival/combined_end_value)+median_pension_tax). **단일 세금 갭(BUG-WD-TAX)은 백엔드 이미 배선됨(L694~705 tax_engine 생성·WithdrawalAnalyzer 전달) → UI 갭이 유일원인.** normalize_multi_accounts에 unrealized_gain 추가(기본0, 기존 무영향). **모듈(`multi_account_ui.js`):** MMTAX.mode 인식 — `_mmAmountFields`(신규)·primary 카드가 wd=월적립숨김·시작목돈 라벨·위탁 미실현차익칸(primary 위탁 포함). calculator/적립기(accumulation 기본) 무변경. **UI(`retirement.html`):** switchMode MMTAX 스왑(wd=wdSeed/withdrawal·sim=simSeed/simMonthly/accumulation)+renderTaxAccounts 재호출. wd body 세금(tax_enabled/account_type/gain_harvesting/user_settings)+`buildWdAccountsPayload`(신규: 시작목돈·미실현차익·월적립 없음)+분배정책. renderRetirement wd 멀티 per-account 분포(renderMultiAccountSummary)+median_pension_tax 표시. 캐시 v20260607g5d. **검증:** L13 `test_g5_wd_household.py` 6종+광역회귀 71+jsdom 14종 PASS + E2E 실DB(458730 위탁+069500 연금: 멀티 생존율·계좌별 분포·median_pension_tax 6,121,986·tax ON/OFF). ⚠️계좌별 리밸=상단 공통 가정·브라우저 육안 미확인(jsdom+E2E 커버). **BUG-WD-TAX/GAP-WD-MULTI 둘 다 해소.** **▶ 커밋·Hetzner 배포·서버검증 후 G5 멀티 UI 4탭(계산기·백테·은퇴적립·은퇴인출) 전부 완료 → L7 실데이터 OR 타작업.**

> 🧭 **2026-06-07 업데이트 53 (G5-D 인출기 멀티+세금 설계 — 구현 대기 / 다음 세션 시작점):** 오너가 2단계 완료 후 지적: 은퇴시뮬(sim)=적립기+인출기, 인출 부분은 같은 엔진이어야 하는데 인출기 탭만 단일. **"인출기 백엔드 미지원" 표현 정정 — 멀티 인출 엔진 `analyze_household_withdrawal`(위탁→ISA→연금 순차+연금소득세+위탁 양도세)은 이미 존재·sim서 작동(E2E 생존율 0.6879가 그 결과). standalone `run_withdrawal_logic`이 옛 단일 `WithdrawalAnalyzer`만 호출 → 인출기만 단일.** 추가 갭 발견 **BUG-WD-TAX**(인출기 wd body가 세금 필드 자체를 안 보냄 → 인출기 세금 OFF, 기존 상태). **설계 완료 = plan §G5-D**(`trackG_multiaccount_plan.md` 끝). **오너 결정 3건:** Q1 공용패널 재사용(wd 모드 월적립칸 숨김) · Q2 취득가=계좌별 미실현차익 입력칸(cost_basis=목돈−미실현) · Q3 인출 시작 나이=wdPensionStartAge. **▶▶ 다음 세션 = G5-D 구현.** 순서: ① 모듈 `MMTAX.mode` 인식(wd=월적립숨김·위탁 미실현차익칸, calculator/적립기 회귀0) → ② `run_withdrawal_logic` accounts 분기+`analyze_household_withdrawal` 호출+반환매핑 **+ 단일 세금 갭(BUG-WD-TAX) 동시 수정** → ③ UI(switchMode MMTAX 스왑·wd body 세금·accounts·`buildWdAccountsPayload`·멀티 결과렌더) → ④ jsdom 스모크+E2E(`run_withdrawal_logic` 직접, 로컬 Celery 없음)+배포. 검증 L13 4종. 미해결가정: 계좌별 리밸=상단 wdRebal 공통. 파일: retirement_logic.py·multi_account_ui.js·retirement.html·tests/test_g5_wd_household.py.

> ✅ **2026-06-07 업데이트 52 (G5 2단계 — 백테·은퇴 멀티계좌 UI 배선 완료·배포):** 1단계(공용모듈) 후 backtest·retirement 배선. **모듈 config화(MMTAX):** portfolioTickers·totalInitId·totalMonId로 탭별 결합점 파라미터화 → calculator 무변경, backtest(btTickers/btSeed/btMonthly)·retirement(retTickers/simSeed/simMonthly) 주입. `renderMultiAccountSummary`(분포렌더) calculator.js→모듈 이동(계산기·은퇴적립 공유). **백테(2-A):** 단일 드롭다운→멀티패널, 계좌별 **스칼라 종료자산**(단일윈도우)+절세+g2 자체렌더(btRenderMultiAccount). **은퇴 적립기(2-B):** 멀티패널+sim accounts 페이로드+renderMultiAccountSummary(동형 분포). **인출기(wd)는 단일 유지**(run_withdrawal_logic accounts 미지원=백엔드 한계). **검증:** jsdom 3탭 11/11 PASS·런타임에러0(calc 회귀+bt 회귀+ret 신규) + E2E 백테(sync /run 2계좌 multi_account=True)·은퇴(run_retirement_logic 직접 멀티: 생존율 0.6879·절세 1,632,510·g2). ✅ **커밋(fd41f65·9cface8)·푸시·배포 완료** — 라이브 3탭 v20260607c·HTTP200. ⚠️ 브라우저 육안 미확인·인출기멀티 백엔드 미지원. **▶ G5 멀티계좌 UI 3탭 완료. 다음 = L7 실데이터검증 OR 인출기멀티 엔진 OR 타작업.**

> 🔧 **2026-06-07 업데이트 51 (G5 본선 복귀 — 멀티계좌 UI 탭별 차이정리 + 1단계 공용모듈 추출):** 합성버그 체인 종결 후 Track G5 멀티계좌 UI 배선 복귀. **코드 실측 차이정리:** calculator만 멀티 UI 완비(외부 calculator.js), **backtest·retirement는 구형 단일 드롭다운(`account_type`)만**, 둘 다 JS가 HTML 인라인이라 calculator.js 공유 불가. 탭별 결과렌더 갈림(적립=동형분포 재사용 / 백테=스칼라종료값 / 인출=생존율 신규). **오너 결정=공용 JS 모듈 추출(b)**(복제는 드리프트 기각). **1단계 완료:** 신규 `static/js/multi_account_ui.js`에 멀티계좌 입력 UI 16함수 순수이동(calculator.js −288줄), calculator.html이 모듈→calculator.js 순 로드(v20260607extract). 검증(정적): node --check 양쪽 OK·결합파싱 재선언충돌0·중복정의0·호스트전역보존. **검증(jsdom 브라우저 스모크): 렌더 /calculator HTML에 두 JS 주입→멀티계좌 흐름 8/8 PASS·런타임에러0 → calculator 회귀 0 확정.** **배포·서버검증 완료(57e1fc4):** 라이브 moneymilestone.duckdns.org가 신규 모듈 참조·HTTP 200. 상세 `trackG_multiaccount_plan.md §G5 프론트 UI 배선`. **▶ 다음 = 2단계(backtest/retirement 배선, 은퇴적립→백테→은퇴인출).**

> 🔍 **2026-06-06 업데이트 50 (합성 리밸런싱 현상 조사 — 버그 아님 결론 + FX 상관 오염 발견):** BUG-SYNTH-CORR 배포 후 오너가 "합성 40년 리밸→자산↑·MDD불변·밴드 넓힐수록↑(37→44억)" 제기. 심층조사([[합성_리밸런싱_조사]]). **결론=리밸 수익증가는 실제 금융현상(버그 아님):** 집행 가치보존 확정(코드)·**순수 GLD+SPY 실데이터(합성0) band30 +57.6% vs 셔플 +0.0%** → 넓은밴드 프리미엄은 실제 금/주식 다년 사이클서 100% 발생(셔플하면 소멸). always +17%는 실제=셔플(순수 변동성수확). 합성 i.i.d.는 사이클 못살려 band 중앙값0+고분산 노이즈 → 과대 아니라 과소·불안정. 실엔진 재현: 리밸 +15~23%·MDD ~2%p(평탄) 재현, 단 band1%(잦음)최고·band30 최저 → 오너 "band30최고" 순위는 노이즈라 미재현. **별건=FX 상관오염:** KRW(`apply_fx=T`) 추정이 USD/KRW 공통인자로 상관 부풀림 — **TLT-SPY USD −0.16→KRW +0.23**, GLD-SPY +0.06→+0.25, SCHD-SPY 0.89→0.91(영향미미). MDD 안줄어드는 핵심 = KRW 양상관이라 헤지 죽음. **오너 결정: 실데이터가 진짜라 코드 수정 안 함(손대면 신뢰도↓).** 블록부트스트랩·FX USD모델링·band 저신뢰경고 전부 **보류**. **BUG-SYNTH-CORR 수정(4a48803)은 배포·유지.** **오너 최종결정: FX·넓은분산 둘 다 한국투자자 현실이라 보존, 합성 관련 코드 일절 수정 안 함**(편향 없는 정보 제공이 목적). 미결항목(FX 상관공간·블록부트스트랩)도 **전부 종결**. **▶ 본선 복귀 = Track G5 멀티계좌 UI 배선** — 합성버그 4연속 체인(BUG-CALC-40Y→SYNTH-FX→SYNTH-CORR→리밸조사)은 update45 "(c) BUG-CALC-40Y 확인"에서 시작된 샛길, 전부 종결. **다음 작업 = `retirement.js`·`backtest.js` 멀티계좌 UI(calculator.js 패턴 복제, 엔진 G5-A/B/C 완성됨) → 배포 → L7 실데이터 검증.**

> 🔧 **2026-06-06 업데이트 49 (BUG-SYNTH-CORR 조건부 다변량 구현 — 합성구간 상관 복원):** 오너 결정 확정(9.1=a μ_S캡·**9.2=b 쌍별+nearest-PSD**·9.3=a 다변량-t·9.4=a DB후순위) 후 구현. 신규 `modules/retirement/synthetic_mvn.py` — `estimate_joint_stats`(쌍별 일일수익 상관 최대겹침 + 고유값클리핑 PSD보정) + `generate_joint_window`(세그먼트 분할 조건부 다변량 `r_S=μ_S+B(a−μ_R)+L·z`, B=Σ_SR Σ_RR⁻¹, z=표준t/T_SCALE, μ_S 일일캡). 단일(`_load_with_per_window_synthetic`)·멀티(`_load_window_synthetic`) 둘 다 상단에 joint 분기(raw_loader+tickers로 lazy 1회 추정·캐시)→추정/생성 실패 시 **기존 종목별 독립GBM 폴백**(전부-joint 또는 전부-독립, 회귀 0). 배선 단순화: synthetic_params 플러밍 안 함(실데이터에서만 유도). **핵심 디버그: 역재구성 off-by-one** — `prices[i]=prices[i+1]/(1+r[i])`면 r_i가 d_i→d_{i+1} 전이라 pct_change가 1일 밀려 조건부 상관이 소멸(첫 테스트 corr 0.058) → `r[i+1]`로 교체해 day d_i pct_change=조건부 r_i 정렬. **로컬 검증 PASS:** `tests/test_synthetic_mvn.py` 5종(추정 corr 0.808→합성구간 복원 **0.788**, 독립이면 ≈0·nearest-PSD 단위대각·경계점프 0.5~2·결정론·표본부족 ok=False 폴백) + 회귀 anchor-fx/data-preparer/accum 30 + 광역 137 PASS(rolling·multi·track_g·l_save·gate2·l3·backtest). ✅ **커밋(4a48803)·Hetzner 배포·서버 검증 완료:** domino.service 배포 직후 재시작·HTTP 200. **서버 실데이터(읽기전용) 상관 복원 PASS — SCHD-SPY 추정 0.913 → 합성구간 corr 0.03(수정전)→0.947(수정후)**, SCHD 합성가격 2336~10897 KRW 비폭발(BUG-SYNTH-FX 회귀 무손상). DB경로(generate_and_save) 미수정(9.4=a). ⚠️ 잔여=리밸 정상화(none↔band30 스프레드 소폭·단조·MDD 반응)는 브라우저 실측 미확인. **▶ 다음 = (a)리밸 정상화 브라우저 확인 OR (b)다른 작업.**

> 📝 **2026-06-05 업데이트 48 (BUG-SYNTH-CORR 발견 + 조건부 다변량 설계 플랜):** BUG-SYNTH-FX 폭발 수정 후 오너가 밴드 리밸런싱 이상 발견 — 합성 GLD+SCHD+SPY 40년서 **밴드 넓힐수록 최종자산↑**(none 31.4억→band30% 39.2억 +25%, 밴드폭 비단조), **MDD 거의 무반응**. 조사: ① execute_orders 값보존 검증(net 0, 리밸 로직 무죄) ② 실데이터 QQQ+SPY/GLD+SCHD+SPY는 리밸 거의 무효과(정상) ③ **상관계수 실측 — 합성구간 SCHD-SPY=0.03인데 실데이터=0.89.** → **원인 확정: 합성을 종목별 독립 GBM(`seed=hash(code+window)`)으로 생성해 상관 0.** 독립자산이라 변동성 수확(리밸 보너스) 비현실적 극대화. **이 앱 핵심이 상관 기반 분산효과 시험**이라 치명적. **BUG-SYNTH-CORR** 등록(bugs.md). **설계 플랜 작성** `합성상관계수_plan.md`(완전 조건부 다변량): 데이터(실+백필) 겹침구간 상관행렬 추정→합성종목을 실종목 당일수익에 조건부 다변량 샘플링→synth-real 상관(0.89) 재현, 시장지수 불필요, O(k³)·k≤5 경량. 시장팩터 1차안은 오너 거부(시장지수 없는 ETF 불가). 오너 결정 4건(μ_S캡·공통구간·꼬리·DB경로) 플랜 §9에 설명 추가. ⚠️ **미구현·승인대기.** anchor-FX·mu캡은 이미 배포(별개). **▶ 다음 = 결정 4건 확정 후 `synthetic_mvn.py` 구현.**

> ✅ **2026-06-05 업데이트 47 (BUG-SYNTH-FX 가상데이터 40년 폭발 수정 — 합성 anchor USD/KRW 단위 불일치):** 업데이트46(40년 언블록) 후 오너가 QQQ+GLD+SCHD 등비중 40년 = **2.9조**(SPY 40년 62억 대비 수백배) 발견. 서버 DB 복사본(288M) 실측 재현·분해. **원인=BUG-DIV-3 계열 잔재(계산기 윈도우 합성 경로):** `AccumulationAnalyzer._load_with_per_window_synthetic`이 합성 prefix anchor를 `synthetic_params["anchor_price"]`(data_preparer가 raw price_daily로 잡은 **USD**)로 쓰는데 실 suffix는 `get_price`라 **FX(KRW)** → actual_start 경계서 **~환율배(1300x) 점프** → buy-hold 폭등. 종목격리(40년 보유): QQQ(합성無)=144배 정상, **GLD=70,679배·SCHD=44,300배**(합성만). `build_window_synth_params`(C3)는 이미 FX anchor로 고쳤으나 계산기는 USD anchor 전달로 미수정. **수정:** ① anchor를 actual_start FX 실가격으로(단위일치) ② 합성 mu 캡 `MAX_SYNTH_MU_MONTHLY≈연8.1%`(짧은 불장 외삽 폭발 방지, 두 합성경로 동일). **실측 검증:** GLD 70,679→**18배**·SCHD→**14배**·QGS포트 354억→**6.16억(62배)**·재투자 7.63억. SPY 64배와 동급. QQQ 144배 불변(비합성 무손상). 회귀 `test_synthetic_anchor_fx`(경계점프<5)+관련 43 PASS. ⚠️**정직한 잔여:** 상장전 합성=본질적 D등급 추측, 자산별 장기특성(금 횡보期)은 단일캡으로 못잡음 → 정확도는 실프록시 매핑(금→GC=F 등)·로그공간 전환이 별도 과제. ⚠️ **미커밋·미배포**(prod 현재 폭발값 노출 중 → 시급). **▶ 다음 = 커밋+배포.**

> ✅ **2026-06-05 업데이트 46 (BUG-CALC-40Y 원인 확정·수정 — 백필 ok-skip이 합성 막던 버그):** 투자계산기 장기(40·30년) "가상 데이터 생성 불가" 에러 추적. **서버 DB 실측(오너 승인 SSH 읽기전용)으로 원인 확정:** 서버 `price_daily` = QQQ 1928~(deep)·GLD 2004real+synth1971~·**SCHD real 2003~**(인덱스 프록시 백필 한계). SCHD가 binding. DataPreparer 3단계 보완서 `BackfillEngine.backfill("SCHD")`가 "이미 백필됨(21,046행)→스킵"으로 **status=='ok'** 반환 → `if ok: continue`가 **합성 생성 건너뜀** → SCHD 2003 갇힘 → effective_start=2003. **40년 2003+40>2026 → n_cases=0 → 에러. 20년 2003+20≤2026 → n_cases=11 통과.** 비대칭=순전히 n_cases==0 임계값(코드·sim_years 자체 정상). **수정(`data_preparer.py` 3a):** 백필 ok라도 `new_start > 목표(_min_target)`면 continue 대신 합성 폴스루(잔여 구간 보충). **서버 DB 복사본(288M) 실측 검증:** 수정전 40y=0 → 수정후 **40y=61·30y=61·20y=60**(SCHD 합성 보충). 20y도 11→60 개선(회귀 아님). 회귀테스트 `test_scenario_data_preparer::TestBackfillOkShallowFallsThroughToSynthetic` 2종 + 관련 스위트(data-prep·g5·engine·retirement·rolling·wd1) **79 PASS**. ⚠️ GLD stale(로컬 2020종료)는 별개 데이터 갱신 과제(서버 GLD 2026까지 정상). **C3 무관.** ⚠️ **미커밋·미배포**(push=Hetzner 자동배포). **▶ 다음 = (a)커밋+배포 (b)UI 배선 retirement.js.**

> ✅ **2026-06-04 업데이트 45 (G5-C C3 강검증·정합·한계 전부 해소 — 엔진 완성):** 업데이트44 후 "검증 확실하냐" 점검 → 구멍 정직 식별·전부 닫음. **A 정합 앵커:** 단일 SimulationLoop == 멀티1 `simulate_household_window` — 검증 중 **off-by-one 발견·수정**(멀티가 첫 달 인출, 단일은 시작월 스킵 → 1회 더 인출). 수정 후 성장·하락·인플레·**리밸(분기·밴드)** 전부 **±1원 정확**. **B 분수 생존율:** 변동경로 0<율<1(기존 1.0/0.0만). **C 배당/성장/2종목 경로** 커버. **리밸 배선:** 인출 시뮬이 `PeriodicRebalance(None)` 고정이던 것 → 적립과 동일 `rebal_mode`/`band_width` 전략 빌드(none/band/주기). **합성 보충:** 실윈도우<30이면 GBM(Student-t) 패딩(단일 동형, 티커별 독립경로→`simulate_household_window` 재사용, n_real/n_synthetic surface). **실데이터 스모크:** 069500+458730 세금ON 5+5년 53초, 생존율 0.8405(분수), 분위 단조증가 — 실데이터·성능·분수 동시 검증. **세션서 버그 3개 발견·수정**(gate2a stale golden·BUG-WD-1 인출2배과소·off-by-one). **전체 214 PASS.** **G5-C 엔진 완성(C1·C2·C3·C4, 잔여 한계 전부 해소).** dividend_mode 전역만 남음(단일과 일관·무해). ⚠️ **별건 BUG-CALC-40Y 기록**(투자계산기 장기 시뮬 n_cases==0 실패, 서버 DB 얕음 추정, C3 무관, bugs.md 상세, 미해결). ⚠️ **8커밋 로컬·미푸시**(push=Hetzner 자동배포). **▶ 다음 = (a)UI 배선 retirement.js (b)배포 (c)BUG-CALC-40Y 서버 DB 확인.**

> ✅ **2026-06-04 업데이트 44 (G5-C C3 은퇴 인출 멀티계좌 — 가구 디큐뮬레이션 완성):** 멀티 은퇴 인출(`withdrawal_pending` 스텁) 해소. 단일 RetirementPlanner→WithdrawalAnalyzer의 멀티 대응 신규. **3단계 각 검증후 진행:** **C3.1** `household_withdraw`(월 가구 net을 위탁→ISA→연금/IRP 순 소진, 위탁/ISA=net+CG세별도, 연금=gross-up 개인합산1500만판정, 단일WithdrawalEngine 재사용→정합) 6종. **C3.2** `simulate_household_window`(N계좌 합동, 배당·리밸 독립+가구인출 결합, 취득가 인계)+`analyze_household_withdrawal`(실가격 롤링→합산생존율, 합산자산 월인출 못대는 첫시점=실패=Q4) 윈도우5+롤링3종. **C4(합산생존율) 흡수.** **C3.3** `analyze_household_samples`(11분위 샘플 계좌별 동일분위 시작값→가구인출 롤링→합성)+`_run_multi_account_retirement_logic` 배선(sample_results/combined_summary 실제 surface, 단일형식 미러) L12 5종(생존·고갈·구조·무입력pending·연금세 생존≤OFF). **전체 203 PASS.** ⚠️UI 미배선(엔진우선·오너결정). ⚠️롤링 in-process 순차·합성보충 없음(실윈도우만). **▶ G5-C 엔진핵심 완료(C1·C2·C3·C4). 다음 = UI 배선(retirement.js) OR L7 실데이터.**

> ✅ **2026-06-04 업데이트 43 (BUG-WD-1 은퇴 인출 ~2배 과소인출 수정 — C3 전 발견):** C3(가구 인출 오케스트레이터) 착수 전 인출 원시함수 `WithdrawalEngine` 검토 중 발견. **버그:** 매도 경로가 `needed`만큼 매도해 proceeds를 cash에 가산하나 **인출액 미차감** → 매도월 자산→cash 이동만(유출0), 다음달 주차 cash 소비로 충당 → 격월 유출 → **유효 인출률 ≈ 50%.** 실증: 자산12,000 월1,000×12(의도12,000)→종료6,000. 단일 은퇴 생존율 **과대평가**(모든 은퇴 인출 결과 영향). 세금 아닌 현금흐름 버그. 단일·멀티 공유 원시함수라 C3도 위험. **수정:** 매도 후 `cash = max(0, cash - outflow_from_sales)`(CG세는 sell_with_tax 별도→net+세금 둘다 정확 유출). **검증(재현먼저):** `test_bug_wd1_withdrawal_outflow` 4종(평탄12000·기존cash우선·인플레Σ·고갈0). 수정전 3FAIL→후 4PASS. **회귀 184 PASS**(은퇴 불변식 기반→골든 안깨짐). ⚠️단일 은퇴 생존율 과대→정확(하락). 별건 gate2a stale golden도 갱신(74c343c, off 37,365,073/on 40,913,520, BUG-TAX-1 배당세). **▶ 다음 = C3(정확한 원시함수 위에).**

> ✅ **2026-06-03 업데이트 42 (G5-C C2 연금소득세 인출 배선 — 분리과세 전액 16.5%):** 인출 연금세를 하이브리드(`pension_effective_rate`, BUG-PENSION-1) → `pension_separate_tax_annual`(1500 이하 나이별 3.3~5.5%, 초과 전액 16.5%, 오너결정)로 교체. `WithdrawalAnalyzer._calc_gross_withdrawal` gross-up 실효율 + `_calc_pension_tax_by_age` 표시 둘 다. pension_start_age=인출시작 가정. **검증 `test_g5_pension_withdrawal_wiring` 3종**(나이별 55→5.5·70→4.4·80→3.3·1500만초과 전액16.5% 나이무관·표시 반영). 회귀 **122 PASS**. **BUG-PENSION-1 해소.** ⚠️하이브리드 함수군 프로덕션 미사용(미삭제). ⚠️run_withdrawal_logic·은퇴 인출 연금 결과 바뀜(과소→정확). **▶ 다음 = C3 가구 인출 오케스트레이터(멀티, 위탁→ISA→연금 순차소진).**

> ✅ **2026-06-03 업데이트 41 (G5-C C1 인출 과세 배선 + BUG-TAX-3 진단 정정):** **정정:** 앞선 "은퇴 이중과세"는 부정확 — `wd_config`에 tax_engine 없어 **인출투영 원래 면세**, 적립끝 청산세가 유일 세금(이중 아님). ∴ 무청산 전환(업데이트40)만 하면 적립면세+인출면세=**세금0 회귀**. 오너 규칙의 올바른 구현 = 적립끝 청산 제거 + **인출 과세 배선(C1)**. **모델 확정: 적립 일괄과세 없음 → 인출하며 과세.** **C1:** `carried_cost_basis`(=적립 총납입) 플러밍 RetirementPlanner→WithdrawalAnalyzer→Runner→SimulationLoop, day-1 매수 직후 avg_cost 비례축소 → 위탁 인출 매도가 적립차익 과세(ISA/연금 무해). **`wd_config`에 tax_engine 등 배선**(면세 회귀 해소). 단일+멀티 공유. **검증 `test_g5_withdrawal_basis`:** 거치 종료청산 손계산 ±1원=**924,000**(6M×15.4%)·인출경로 방향성. 회귀 **119 PASS**(calculator/backtest 불변). ⚠️연금 인출세=C2·멀티 가구 오케스트레이터=C3·합산 생존율=C4 잔여. ⚠️단일 은퇴 tax-ON 바뀜(면세→인출과세, 정확). **▶ 다음 = C2 연금소득세 인출 배선(`pension_separate_tax_annual`).**

> ✅ **2026-06-03 업데이트 40 (BUG-TAX-3 은퇴 이중과세 수정 — 무청산 인계):** 오너 지적 "은퇴에선 절대 일괄청산 금지. 투자계산기는 일괄청산 맞음." 코드추적 결과 기존 버그 확인: `AccumulationAnalyzer`/`TaxableSimulationRunner`/`MultiAccountSimulationLoop`이 `tax_enabled`면 적립 끝에 무조건 `apply_liquidation_tax`(연금 5.5%·위탁 15.4/22% 전액청산) → 그 세후값이 `RetirementPlanner`→`WithdrawalAnalyzer` 인출단계로 넘어가 **또 과세**(연금=명백한 이중과세). **수정:** `apply_final_liquidation` 플래그 신설(기본 True=투자계산기·백테 불변). 은퇴 적립 **전 경로** False — 단일 `run_retirement_logic`+`app.py:retirement_run`, 멀티 `_run_multi_account_retirement_logic`. 적립기 중간세(배당·리밸)는 유지, 최종 청산만 스킵 → gross 인계. **검증(빡센 4종 규약):** L11 **7종**(골든 래퍼=엔진·**직접 Runner앵커 loop==runner 양플래그**·combined=Σ·평탄8M·무청산 ON==OFF·폐형식 거치=초기×가격비 20M·ISA 1억캡 stop=20개월·인출pending·디스패치) + **단일 은퇴 무청산 2종**(`test_g5_no_liquidation_handoff` — 연금/위탁 AccumulationAnalyzer 단위: 무청산==gross, 일괄청산<무청산=세금 실부과 실증). 전체 G5+세금 회귀 **117 PASS**(tax_truth/gate1/phase2f/gate2b/pension/track_g/l_save 불변). ⚠️위탁 적립차익은 스칼라 인계라 인출까지 과세 누락 잔존 → 취득가 포지션 인계는 G5-C. **▶ 다음 = G5-C 은퇴 인출 멀티계좌(L12) — 취득가 포지션 인계 + 가구 인출 오케스트레이터(위탁→ISA→연금) + 연금소득세 + 합산 생존율.**

> ✅ **2026-06-03 업데이트 39 (G5-B 은퇴 적립단계 멀티계좌 — 엔진+L11):** 오너 결정 "엔진 전부 먼저, UI 나중". 적립은 투자계산기와 동일 엔진(`MultiAccountAnalyzer`) 공유라 래퍼만 추가. **신규 `retirement_logic._run_multi_account_retirement_logic`**: `_normalize_multi_accounts`(공통모듈)·`years=accumulation_years`·데이터준비=`prepare_scenario_data`(은퇴 관례)·계좌별 규제검증·초기자본 한도·ISA 1억캡(transfers OFF)·transfers(정책/풍차/연금)·`MultiAccountAnalyzer` 롤링→combined+계좌별+savings+g2+split_sale+accumulation_summary surface. 디스패치 `run_retirement_logic`: **accounts 2개↑→멀티, 단일계좌(세금ON/OFF·풍차거부 포함)=기존경로 그대로**. **오너Q&A 결정:** Q1 인출투영(생존율)=G5-C로 완전연기(멀티 응답은 `withdrawal_pending=True`·`sample_results=[]`·`combined_summary=None`) — calculator는 인출 없어 단일→멀티 무손실이나 retirement 단일경로는 인출생존율 생성 → 인출-연기 멀티로 보내면 회귀 → **단일→멀티 합성(savings·단일풍차 자동미러)은 인출 완성(G5-C)까지 연기**. Q2 분기=calculator미러(len>1). Q3 ISA풍차=멀티서 transfers로 허용. Q4 pension_start_age=G5-C로 연기(적립은 과세이연). **L11 검증 5종 PASS**: 골든(래퍼=엔진직접호출±1원, 엔진→Runner는 calculator L0 보증→전이적)·불변식(combined=Σ)·평탄가격 무수익 8,000,000·세금ON<OFF·인출pending·디스패치(2↑멀티/1단일). 회귀 80(G5-A+TrackG+L-save+withdrawal-cg)+retirement 11 PASS. ⚠️ UI 미배선(엔진 다 끝낸 뒤 B단계). **▶ 다음 엔진 = G5-C 은퇴 인출 멀티계좌(L12) — 가구 인출 오케스트레이터(위탁→ISA→연금)·연금소득세(`pension_separate_tax_annual` 토대완료)·생존율 합산·`MultiAccountAnalyzer` withdrawal_amount 확장.**

> ✅ **2026-06-03 업데이트 38 (BUG-TAX-2 위탁 인출 양도세 누락 수정 + G5 복제 플랜):** 오너 지적 "왜 위탁 인출 양도세 없어?" → 기존 버그 확인. 은퇴 인출 위탁이 `WithdrawalEngine.portfolio.sell()` 직행(TaxedOrderExecutor 우회)이라 인출 매도차익 양도세 누락(청산세는 남은 보유분만). **수정:** `TaxedOrderExecutor.sell_with_tax` 추출(리밸·인출 공유 단일소스), `WithdrawalEngine.process(executor=)`로 인출 매도를 세금경유, 루프 2곳 executor 전달, 세금OFF면 fallback. 검증 `test_withdrawal_cg_tax` **10종**(정확값±1원 5: KR_FOREIGN 1,540·US 110,000·US공제내 0·국내 0·ISA 0 + 통합 5)+회귀 73 PASS. ⚠️기존 은퇴 인출 위탁 결과 바뀜(과소→정확). ⚠️gate2a 2종 실패=별건 stale golden(BUG-TAX-1 이후 미갱신, 내 변경 무관 stash확인). **G5 플랜 추가**(백테스트·은퇴 멀티 복제, L10~L12). ✅ **G5-A 백엔드 완료**: 공통모듈(`multi_account_common.py` — normalize/validate/build_savings + `build_loop_accounts`) + `backtest_logic._run_multi_account_backtest_logic`(accounts 분기, `MultiAccountSimulationLoop` 1회=단일윈도우, combined+계좌별+savings+g2 surface). **L10 검증 PASS**(골든 1계좌=TaxableSimulationRunner ±1원·불변식 combined=Σ·평탄가격 무수익 8,000,000·세금ON<OFF). **▶ 다음 = G5-A UI(backtest.js 멀티계좌, calculator.js 패턴 복제) → G5-B 은퇴 적립.**

> ✅ **2026-06-03 업데이트 37 (BUG-G1-2 커서유실 수정 + deploy.yml divergent 복구):** ① deploy.yml: 금 Phase 2 amend+force-push로 서버 git pull이 divergent 실패(exit 128)→미배포. `git pull`→`git fetch`+`git reset --hard origin/main`(origin 단일진실, force-push 복구). 교훈=push 후 amend+force-push 금지. ② BUG-G1-2(중간): 투자계산기 다중계좌 입력 커서유실. oninput 핸들러가 매 키스트로크 `renderTaxAccounts()` 전체 재렌더가 원인. `updateTaxAccountAmount`→`checkTaxLimits()`만, `onAccountTickerWeightChange`→전용 `acctWeightWarn{idx}` div만 갱신(`accountWeightWarnHtml` 분리). 입력칸 비재생성. JS OK. cache v20260603cursorfix. ⚠️브라우저 육안 미검증. **▶ 투자계산기 잔여버그 해소. 다음 = 백테스트/은퇴 탭 복제.**

> ✅ **2026-06-03 업데이트 36 (금 ETF 2차 백필 — 현물=KRX_GOLD·선물=GC=F 갈래 라우팅, 금 Phase 2):** 오너 "금선물 ETF도 같이, 그게 그거" → 현물≠선물이나 우리 소스(가격 레벨)엔 콘탱고 드래그 안 보여 상장전 합성은 근사로 둘 다 OK. **발견:** 모든 금 ETF가 GOLD→GC=F라 현물조차 GC=F 백필 + `fx_applied`가 `market=="US"` 요구→금ETF(COMMODITY)는 환율 미적용→현물(unhedged) 상장전 원화변동 누락. **결정:** 현물/국제금→KRX_GOLD(KRW/g 네이티브), 선물H→GC=F / 순수 금만. **구현:** KRX_GOLD 빌더 모듈함수 `build_krx_gold_krw_series` 추출(price_loader↔backfill_engine 공유), `_GOLD_KRX_SPOT={411060,0072R0,0064K0,0066W0}` 오버라이드, `_load_index("KRX_GOLD")` 공유빌더, KRX_GOLD 무배당 등록. **검증(로컬):** 현물 proxy=KRX_GOLD 1971~(50년+)·선물 GC=F·경계점프 ±2.5%이내·411060 9177행. test_krx_gold 5 PASS(라우팅+빌더일치 신규)+회귀 71 PASS. ⚠️ **미배포·서버 실데이터 검증 남음**(price_daily gitignore→코드만 배포, 서버 lazy 재백필). **▶ 다음 = 서버 배포·검증 OR 백테스트/은퇴 복제.**

> ✅ **2026-06-03 업데이트 35 (KRX 금현물 거래가능 + 위탁전용, 금 Phase 1):** KRX_GOLD가 index_master만 있고 price_daily 없어 위탁 시뮬 'portfolio_value' 에러였음. `price_loader._build_krx_gold_series`로 연속 KRW/g 시계열(2014~ KRX금 + 2014이전 GC=F×USD/KRW ratio규격화) 단락 제공 + 위탁전용 검증(ISA/연금/IRP 거부) + data_start 시계열시작·빈윈도우 스킵(5cc4c1a+ec7cfa2). **서버검증:** 위탁 금 8년 작동(금비과세 savings 0) · ISA+금 account_restrictions 거부 · 2014경계 점프0·2024년 86,940원/g 실제일치. test_krx_gold 3종+회귀 PASS. **GH 절세는 절세액에 합산 표시(25534ac).** **▶ 다음 = 금현물 ETF 2차백필(금데이터백필_plan.md Phase 2).**

> ✅ **2026-06-03 업데이트 34 (단일 풍차 ISA 자동 위탁계좌):** 오너 요청 — 단일 풍차 ISA를 에러로 막지 말고 자동 처리(2ae53c6). 같은 종목·비중 위탁계좌(초기0·월0) 자동생성 + 정책 라우팅 → 멀티경로로 풍차 정상(만기 3회). 결과창 파란 안내박스. **서버검증:** 단일 풍차 ISA 458730 12년 → 절세 2,245,158·종료 3,677만(평범 ISA 3,363만↑). 회귀 L-SAVE26+TrackG41 PASS. JS v20260603windmill. **▶ 절세 P1+단일계좌(풍차 포함) 완료. 다음 = 백테스트/은퇴 복제 플랜.**

> ✅ **2026-06-03 업데이트 33 (분할매도 복구 + 풍차 단일ISA 회귀 수정):** BUG-SAVE-1 A안 부작용 정리(124f82f). ① 분할매도 패널 멀티경로 복구(analyzer가 kr_foreign_gain·금융소득 surface→compute_split_sale_plan). 회귀: 풍차 단일ISA가 멀티서 풍차 미작동(maturity 0) → 라우팅 '非풍차만 멀티'로 한정, 풍차 단일은 단일경로(의도된 'isa_windmill_disabled' 안내·멀티계좌 필요). ② early_cancel은 단일계좌 도달불가(풍차단일 차단)라 무관. **서버검증:** 평범 단일 ISA 절세 1,628,586·위탁 split_sale gain 3747만·풍차단일 안내 PASS. **▶ 절세 P1 전부 정리 완료. 다음 = 백테스트/은퇴 복제 플랜.**

> ✅ **2026-06-02 업데이트 32 (BUG-SAVE-1 수정·서버검증 PASS):** 단일계좌 절세액 미표시 수정(A안). `run_calculator_logic`이 세금ON 단일계좌면 legacy 필드로 accounts 합성→멀티경로 라우팅(f909c69). **서버검증:** 단일 ISA 458730 → 절세 1,628,586 표시. ⚠️부작용: 단일 세금ON서 분할매도·ISA조기해지 패널 미표시(멀티경로에 없음, 에러X). **절세액 P1 버그 2개(TAX-1·SAVE-1) 모두 수정완료.** ▶ 다음 = 백테스트/은퇴 복제 플랜.

> ✅ **2026-06-02 업데이트 31 (BUG-TAX-1 수정·서버검증 PASS):** 단일경로 배당소득세 미부과 수정. 원인=`DividendEngine`이 GROSS를 cash 입금하나 `SimulationLoop`이 배당세 미차감(멀티는 루프가 차감해 정상). `TaxedDividendEngine.process`가 차감 중앙화(5ca9a96). **서버검증:** 458730 위탁 12년 — 보유 3,312만→**3,200만**, 인출 2,754만→**2,585만**(둘 다 손계산 이론 일치). 재투자 3,846만→3,620만. ⚠️배당 실린 종목 기존 단일계좌 결과 전부 바뀜(이제 정확). 회귀 2종+L-SAVE26+TrackG41+gate2c4 PASS. **▶ 남음 = BUG-SAVE-1(단일계좌 절세 패널).**

> 🐞 **2026-06-02 업데이트 30 (버그 2개 발견 — 브라우저 검증 중):** **BUG-TAX-1(높음)** 위탁 세금 과소부과 — 배당 실린 종목(458730)이 이론 15.4%보다 적게 떼임. hold 모드 깨끗 검증: 이론 400만 vs 실제 289만, **누락 111만 ≈ 배당×15.4% → 배당소득세 미부과 의심**. 실효율 재투자12.5%·보유11.1%·인출6.4%(배당 분리도↑일수록↓). 인출은 시세차익마저 과소(추가원인). 단일경로(`TaxableSimulationRunner`) 의심(멀티는 test_l3서 배당세 정상). **BUG-SAVE-1(중)** 절세 패널이 계좌 1개일 때 미표시(`run_calculator_logic:555` len>1 조건). 데이터·분석 [[log]]. **▶ BUG-TAX-1 추적·수정 최우선(실제세금 틀리면 절세액도 틀림) → BUG-SAVE-1.**

> ✅ **2026-06-02 업데이트 29 (절세액 표시 P1 — 투자계산기 완료):** `절세액표시_plan.md` P1 풀구현. **3종 표시**(전체 위탁가정세금·실제세금·절세액=껍데기효과) + **4번째 숫자 GH 절세**(절세매도 자체 효과, 위탁+GH 전용·`estimate_gain_harvest_saving` 분석근사). 계좌별 p50 + 합산(=계좌별 p50 단순합). 신규 순수함수 `modules/tax/saving_estimate.py`(`estimate_brokerage_tax`). 엔진: `order_executor.py`에 위탁가정 실현차익 누적(`_brk_krf_gain`/`_brk_us_by_year`, 계좌유형 무관·GH는 기준리셋이라 미누적)·`multi_account_loop.py`에 배당 클래스별+풍차만기·최종청산 미실현 누적→`brokerage_assumed_tax`/`tax_saving`·`multi_account_analyzer.py` `_build_savings`·`calculator_logic.py` `savings` 응답·`static/js/calculator.js` 절세 3종 패널. **검증: L-SAVE 24종 PASS**(순수함수·ISA단일=858,000·풍차2사이클=2,830,168·GH절세=550,000·연금IRP=550,000·DCA·재투자·다종목·종합과세가산0하한·analyzer풍차·logic매핑) + **Track G 41 회귀 PASS**. 연금/IRP 청산세 5.5%는 현행 유지(오너 결정). **배포+서버검증 PASS**(03f28cb, 실데이터 458730: ISA절세 669,500·위탁 0 원단위일치·합산=Σ). ⚠️미검증=브라우저 육안 렌더만. **오너 결정:** 연금/IRP 인출세는 은퇴탭(P3)만 — 투자계산기/백테스트/배당금엔 미적용(연금절세=적립기 위탁가정−0). ⚠️ 미배포(서버검증 전). **▶ 다음 = (A) 백테스트/은퇴 복제 플랜 작성+P2/P3 OR (B) 서버 배포·검증.**

> 🏁 **2026-06-02 세션 종료 정리:** **Track G2 풀스택 완료** — 엔진(2-2 만기분배·G3 연금이전공제·2-4 금종세 풍차중단·G4 연납입공제, L0~L9 결정론 40+케이스) + B1 배선 + B2 API서버검증 + B3 투자계산기 UI(우선순위·풍차토글·재투자·결과 g2패널). 부수 수정: 배포파이프 버그(index_master 추적→`git rm`+deploy.yml `set -e`)·index_master 서버손상 복구(37코드 재수집)·ISA 연한도 하드거부·연금 합산초과 라우팅·초기자본 에러통일·BUG-INF-1(Infinity JSON)·금종세 수동입력 제거(엔진 자동판정)·한도초과 이전안내·마지막달 풍차 잔재·단일 연금/IRP 한도에러. 브라우저 스모크 ①②③⑦ 정상 확인. 전체 스위트 **111 PASS**. **▶ 다음 = (A) 절세액 표시 P1 `절세액표시_plan.md` (위탁가정·실제·절세액, L-SAVE0~8 검증설계) OR (B) G2 탭 복제(백테스트→은퇴, 1500만 한도) + L7.** 스모크 가이드 `smoketestguide.md`(테스트 9종).

> ✅ **2026-06-02 업데이트 28 (브라우저 스모크 피드백 반영):** ① **금종세 수동입력 제거** — 엔진이 위탁 배당으로 자동판정만(오너 결정). ② **한도초과 이전 안내문구** 추가(멀티계좌 세금창+결과). ③ **sim 마지막 달 풍차 재가입 스킵** — 굴릴 시간 0인 잔재(테스트1 ISA 2008만) 방지, 마지막 만기는 최종청산. `_last_month_idx` 가드. ④ **단일계좌 연금/IRP 한도초과 에러** — 초기+월×12 > 1800만이면 차단(이전 대상 없으므로, ISA 단일은 기존부터 에러). 검증 `test_l5_no_renewal_at_final_month`. Track G 41/41. cache v20260602c. 스모크 결과①②③⑦ 정상 확인(p10<p50<p90·우선순위반영·풍차+공제패널·연금라우팅).

> ✅ **2026-06-02 업데이트 27 (초기자본 연한도 = 에러로 통일):** 오너 결정 — 초기자본 초과는 라우팅 아니라 **에러**(실제 입금이라 한도 초과 불가). `_validate_initial_capital_limits`(calculator_logic): ISA 각 ≤2천만, **연금저축+IRP 합산 ≤1800만(공유)**, transfers 무관 항상. 프론트 initial_capital_limit 배너. 이전 비일관(ISA-G1만 에러·ISA-G2 앉음·연금 무검증) 해소. (월 초과분=라우팅, 초기자본=에러 — 구분 명확.) 검증 `test_l2_initial_capital_limit_validation`. cache v20260602init.

> ✅ **2026-06-02 업데이트 26 (연금/IRP 월납입 초과 라우팅 + ISA 연한도 하드거부 버그):** ① **버그**: `validate_isa_contribution`이 ISA 연2천만 초과를 시뮬 시작 전 하드거부 → G2 분배 자체 차단(브라우저서 발견). 수정: transfers ON이면 스킵(엔진이 라우팅, befc6fb). ② **연금/IRP 합산 1800만 초과분 드롭→라우팅**: 기존엔 ISA만 초과 라우팅하고 연금은 초과분 드롭(자금증발). ISA처럼 `overflow_total` 합산→정책 cascade. 검증 `test_l4_pension_combined_overflow_routes`(연금100+IRP100/월→공유풀 1800만+위탁 600만). 연금/IRP 하드락은 원래 없음(경고만). **Track G 38/38.** ❌ deferred: 연금/IRP·ISA 초기자본>한도 라우팅(sim-start 메커니즘 필요, 계획 기록). **▶ B3 브라우저 스모크 재시도 + 잔여(탭복제·초기자본엣지·L7).**

> 🔧 **2026-06-01 업데이트 25 (B3 프론트 UI 배선):** 계산기 멀티계좌에 G2 컨트롤 추가. ① 계좌별 **우선순위 숫자 입력**(`updateTaxAccountPriority`, 재렌더 없이 저장→커서유지) → `buildDistributionPolicy`가 우선순위 정렬로 `distribution_policy` 생성 ② 글로벌 ISA풍차 체크 → **ISA 계좌별 `isa_renewal`** 매핑(엔진이 계좌별로 읽으므로) ③ 금종세 **수동연도 입력**(`manualComprehensiveYears`, isaRenewalSection) → `manual_comprehensive_years` ④ 기존 `taxDeductionReinvest` → `reinvest_tax_credit` 배선 ⑤ 결과에 g2 패널(만기 N회·종합과세연도·환급액). JS 문법 OK, 캐시버전 v20260601b3. **검증:** node --check 통과 + **배포됨**(서버가 v3 JS·수동연도 입력 서빙 확인) + **풀스택 PASS**(UI 형태 body submit→`g2.enabled=true`·만기 1회·ISA 재가입 라우팅 end-to-end). 미검증(약함, 수용)=DOM 클릭→body 생성(브라우저 육안 스모크 1회 권장: 계좌 2개+우선순위+ISA풍차→실행→g2 패널). **▶ 잔여 = (선택)브라우저 스모크 + 은퇴/백테스트 탭 복제 + L7 실데이터 통합.**

> ✅ **2026-06-01 긴급 (KRX 금현물 타일 복구 완료):** 배포 fix(d581cc3)의 `git checkout -- index_master.db`가 서버 index_master.db를 레포 스텁(1.11MB, KRX_GOLD 1행+USD/KRW)으로 덮어씀 → **홈 KRX 금현물 타일 사라짐.** **정정(이전 진단 과장):** 홈 지수 중 index_master 의존 = **KRX_GOLD 단 하나.** S&P·나스닥·코스피·국제금(GC=F)·환율 = `MarketQuoteService`가 **yfinance 라이브**로 매 요청 조회(차트 과거+오늘값) → index_master 무관 → 처음부터 안 깨짐. KRX금만 yfinance에 없어 index_master 저장 필수("금만 따로 넣은" 이유). **복구:** 서버 `fetch_krx_gold.py --all`(2014-03-24~오늘 KRX API 재수집) → **KRX_GOLD 2989행 풀복구**(갭 없음), `/api/market` krx_gold 타일 정상(+3.09%, 5/29). **price_daily.db(주식·금 가격) 처음부터 무사**(499,565행, 계산기·백테스트 정상). ⚠️ 교훈: 런타임 데이터 DB는 deploy에서 절대 checkout/reset 금지(deploy.yml의 `git checkout -- index_master.db` 줄이 원흉 — 차기 제거 필요). ✅ **전체 index_master 재수집 완료(2026-06-01): 37코드 풀복구** — 주가지수(S&P·나스닥·코스피 등)·원자재(GC=F/SI=F/CL=F/HG=F)·금리(DGS·KTB·CD91·KOFR)·신용(DBAA·CORPAA3Y·CORPBBB3Y)·DJUSDIV_PROXY(5674)·환율·KRX_GOLD(2989). 테이블 3개 정상. 미복구: KQ150(yfinance 실패 1건, 재시도 가능)·DJUSDIV100(폐기됨, 정상). 채권/배당 ETF 백필 데이터 전부 복구. ⚠️ **데이터 파이프 지속불가 = 별도 과제:** 갭채움 로직 전무(`get()`은 양끝만 확장)·gold 외 일일 스케줄러 없음.

> ✅ **2026-06-01 업데이트 24 (배포 파이프 버그 수정 + B2 서버검증 완료):** **중대 발견 — 오늘 커밋 전부 서버 미배포 상태였음.** 원인: `data/meta/index_master.db`가 추적되는데 서버 런타임이 써서 `git pull` abort, deploy.yml이 pull 실패 미체크(systemctl is-active만)라 Action은 success인데 코드 미반영. 수정: ① `git rm --cached index_master.db`(런타임 데이터, *.db로 ignore) ② deploy.yml `set -e` + pull 전 `git checkout`으로 dirty DB 폐기. → 배포 정상화(d581cc3). **B2 서버검증 PASS:** `/api/calculator/submit` G2 body(ISA풍차+위탁, 458730 실데이터) → `g2.enabled=true`·`transfer_log` 실제 만기이벤트(목돈12.4M·만기세4.5만·재가입 라우팅) end-to-end 확인. **▶ 다음 = B3 프론트 UI(분배정책 에디터·풍차토글·금종세입력·재투자토글) + L7 실데이터 통합.**

> 🔧 **2026-06-01 업데이트 23 (B2 — API surfacing):** `/api/calculator/run`=`jsonify(run_calculator_logic())` **pass-through**라 g2/cases 신규 필드 자동 노출(코드 변경 불필요). JSON 직렬화 가드 테스트 추가(`test_b2_g2_result_json_serializable` — transfer_log/comprehensive_years 등 jsonify 안전, 과거 numpy.bool_ 버그 전례 방어). **▶ 잔여 = Hetzner 배포 후 G2 body submit 실데이터 검증(HTTP 200 + 필드 존재) → B3 프론트 UI.**

> ✅ **2026-06-01 업데이트 22 (B1 후속 — 순수 연금/IRP 연납입공제 정리):** 업데이트21 한계 해소. `transfers_enabled`에 `(세금ON & 연금/IRP 존재)` 추가 → 정책 없는 순수 연금/IRP도 연납입공제 산출. 안전성 = `test_l9_pension_transfers_equivalence`(한도 내 연금/IRP는 transfers ON/OFF 종료값 동일, 공제만 추가). Track G 36/36 + 전체 PASS. **▶ 다음 = B2(API surfacing 서버검증) → B3(프론트 UI) → L7.**

> ✅ **2026-06-01 업데이트 21 (Track G B1 — analyzer/logic 배선 완료):** 엔진(L0~L8) 완료 후 analyzer/calculator_logic이 G2 기능 미전달하던 갭 해소. ① analyzer: `manual_comprehensive_years`/`reinvest_tax_credit` 파라미터 + `isa_renewal` 계좌전달 + 결과(transfer_log·comprehensive_years·환급) surfacing ② calculator_logic: `_normalize`가 isa_renewal 독해, body→DistributionPolicy 파싱, transfers_enabled 판정(정책 OR 풍차), **풍차 거부 제거**, transfers ON시 정적 ISA cap 스킵, 응답에 g2 섹션. 검증 **L9 4종(만기 surfacing·G4공제+금종세·G1회귀·정규화) → Track G 35/35** + 전체 스위트 PASS. **⚠️ 한계: 정책 없는 순수 연금/IRP는 연납입공제 미적용**(정책 추가시 작동, 재검토 가능). **▶ 다음 = B2(API surfacing 서버검증) → B3(프론트 UI: 분배정책 에디터·풍차토글·금종세입력·재투자토글, 검증약함) → L7 실데이터.** 상세 [[log]].

> ✅ **2026-06-01 업데이트 20 (Track G4 연 납입 세액공제 완료 + 죽은 v1 삭제):** 플랜 §G4 신규. 매년 연금/IRP 납입 세액공제 환급을 통합 루프에 배선. ① 죽은 `modules/tax/multi_account.py`(v1 MultiAccountSimulator, 호출처0) 삭제 ② `annual_tax_deduction`(기검증) 재사용+`_track_pension_contrib`(연금/IRP external 납입 연도별 분리집계, internal·재투입분 제외) ③ 연경계 정산(마지막해 finalize 보고만) ④ `_apply_credit_reinvest` — G3+G4 환급 **통합 토글**(reinvest_tax_credit), 재투자 시 **분배 정책 cascade**(오너: 별도 목적지 안 만들고 기존 우선순위) ⑤ G3 재투자도 정책 cascade로 통일 ⑥ 결과 `annual_deduction_credit`/`pension_transfer_credit_total` 노출. 오너결정: G3·G4 별도한도(최대 1200만)·재투자 통합토글·정책따라감. 검증 **L8 5종(정상·연금단독cap+고소득·합산cap·0납입·재투자) → Track G 31/31** + 전체 스위트 PASS. **▶ G2 엔진계층 완료(L0~L8). 다음 = B단계: calculator_logic 배선(accounts+정책+isa_renewal+manual_comprehensive_years+reinvest) + 풀커스텀 분배정책 프론트 UI(UI 검증 약함).** 상세 [[log]].

> ✅ **2026-06-01 업데이트 19 (Track G2 2-4 금종세 ISA 풍차중단 + 공유세션 멀티배선 완료):** 플랜 §2-4 구현·검증. ① **공유세션 멀티배선**(`run`서 `TaxSessionState` 1개→전 계좌 div/executor 주입, 전 위탁계좌 금융소득 개인합산, ISA/연금 제외) ② `_isa_renewal_eligible` — 직전3년 중 종합과세(>2천만) 대상이면 풍차 정지, 라이브∪`manual_comprehensive_years` 수동오버라이드 ③ 만기 게이트(비대상=만기스킵→무한유지, 1억참→2-1 리라우팅, 3년 롤링 재평가로 자동 재개) ④ 결과에 `comprehensive_years`/`financial_income_by_year` 노출. 오너결정: 판정 자동+수동 둘다·과세단위 개인. 검증 **L5c 4종(중단→재개·무한유지·1억리라우팅·세금ON 라이브배당) → Track G 26/26** + 전체 스위트 PASS. **▶ 다음 = 연납입 세액공제(900만, 별개) OR calculator_logic 배선+풀커스텀 분배정책 프론트 UI(B단계, UI는 검증 약함).** 상세 [[log]].

> ✅ **2026-06-01 업데이트 18 (Track G2 2-2 만기분배 + G3 연금이전공제 완료):** 플랜 §2-2(풍차 만기 목돈 분배)+§G3(ISA→연금 이전 10%/300만 공제) 구현·검증. ① `_mature_isa`(3년마다 ISA 청산→만기세→리셋, 원가=사이클납입) ② `_compute_injections` 만기 선처리+**외부/내부 자금분리**(만기 재배분=cash_flow 0, 자금보존) ③ `cycle_contribution` 사이클 원가추적(풍차 ISA 평생납입>1억 가능→불변식 사이클기준) ④ G3 `_accrue_pension_credit`(min 10%,300만)+재투자옵션 ⑤ `route_overflow(pension_unlimited=)` — 만기 전환은 1800만 한도와 별도(전액 연금이전 가능, 한국 실제규칙). 검증 **L5/L5b/L6 신규 9개 → Track G 22/22** + **전체 스위트 92/92 PASS**(회귀 무손상). 오너결정: 분배정책=우선순위리스트·재가입 2천만고정·G3동봉. **BUG-TAX-1 폐기**(서민형 `preferential` 정상, 버그 아님). **▶ 다음 = 2-4 금종세 풍차중단(L5c, 공유세션 멀티배선 선행) + 연납입 세액공제(900만, 별개 큰 기능) + calculator_logic 배선 + 풀커스텀 분배정책 프론트 UI.** 상세 [[log]].

> ✅ **2026-06-01 업데이트 17 (L시리즈 검증 엄밀화 완료):** 업데이트16 작업 수행 완료. ① `assert_invariants` 헬퍼 신설(음수0·ISA≤1억·자금보존·flat 보존)→L0/L2/L4 적용 ② L4 구멍 4개 메꿈(정책cap=전기간누적·leftover>0·연금IRP합산1800만·L4-tax 세금ON라우팅) ③ L0~L3 보강(L0 세금ON골든·L1 합산·L3 비과세경계) ④ `route_overflow` cap을 전기간 누적상한으로 명확화(account_tax.py). 검증 **13/13** + 회귀 40/40. (BUG-TAX-1=오진, 폐기 — `isa_type="preferential"`이 정상 코드값. base_tax.py:345 서민형 400만 비과세 정상 작동. 버그 아님.) **▶ 다음 세션 = 2-2 만기분배(L5/L5b) + 2-4 풍차중단(L5c, 공유세션 멀티배선 선행) + G3(L6) 구현 → calculator_logic 배선 → 풀커스텀 분배정책 프론트 UI.** 플랜 테스트표대로 각 계층 4종 충족.

> 🎯 **2026-05-31 업데이트 16 (L시리즈 검증 엄밀화 — 업데이트17서 완료):** 오너 지시 — 모든 L계층이 "완전 검증"(정상경로 손계산+경계/엣지+세금ON/OFF+불변식 4종)이어야 하고, 검증계획 없는 기능(2-4 누락 같은 것) 금지. **▶ 다음 세션 = 「L4 구멍 다 메꾸고 앞으로 모든 L시리즈 테스트는 전부 완전한 검증을 할 수 있게 짜. 검증에 빈틈이 없도록 수정해.」** 구체:
> 1. **`assert_invariants` 공통 헬퍼 신설**(자금보존·음수0·한도위반0) → 전 L케이스 적용.
> 2. **L4 구멍 4개 메꿈:** ④정책 cap 적중 ⑤leftover>0(위탁 미포함 정책) ⑥연금+IRP 동시 1800만 풀공유 + **L4-tax(세금ON 라우팅: 위탁 수신분 KR_FOREIGN 22%/국내 15.4% 정확)**.
> 3. **L0~L3도 4종 충족 점검**(L0 세금ON 골든, L1 그대로, L3 비과세경계 등) — 누락분 보강.
> 4. 플랜 `trackG_multiaccount_plan.md §테스트 설계`에 **L5/L5b/L5c(2-4 신규)/L6 검증항목 이미 정의됨** — 구현 시 이 표대로. **L5c(금종세 풍차중단)는 공유세션 멀티배선 선행.**
> 실행: 「L4 구멍 메꾸고 전 L시리즈 완전검증으로 짜줘」. 이거 끝→그 다음 2-2/2-4/G3 구현+calculator_logic 배선+프론트.

> ✅➡️ **2026-05-31 업데이트 15 (Track G2 토대 — transfer 엔진 + ISA 월 라우팅 2-1 완료 → 다음=2-2/2-4/G3+프론트):** 플랜 §2-1 구현·검증. `MultiAccountSimulationLoop`에 `transfers_enabled=True` 신설(G1 회귀 100% 보존). ① `ContributionLimitTracker`(동적 ISA 연2천만+총1억, 연금/IRP 합산 1800만) ② `DistributionPolicy`+`route_overflow`(cascade) ③ 월경계 `_compute_injections`(ISA 흡수→초과분 정책 라우팅)+`_step_account(contribution_override=)` ④ 위탁 자동싱크(`_ensure_sync_accounts` 첫ISA미러) ⑤ analyzer 패스스루. 검증 **8/8**(L0~L3 회귀 + L4 신규 4: cascade/연리셋/총한도캡/자동싱크) + 회귀 37/37(tax_truth·Gate·2f·cagr). 오너결정: 개인기준·풀커스텀UI·위탁자동싱크·ISA연+총둘다. ⚠️미구현(다음): 2-2 만기분배·2-4 풍차중단(공유세션 멀티배선 선행)·G3 연금이전·calculator_logic 수신·풀커스텀 분배정책 프론트UI. 상세 [[log]].

> ✅➡️ **2026-05-31 업데이트 14 (금융소득 종합과세 Phase 2f 완성 → 다음=Track G2):** 2f 전부 구현·서버검증(4100ecd). ① 청산+**중간실현** KR_FOREIGN 시세차익을 그 해 배당과 합산 종합과세(공유 `TaxSessionState`) ② `_ytd_income` 외부소득 주입 ③ 연도별 종합과세 대상 트래킹(`comprehensive_years`) ④ other_financial_income 자동산출 ⑤ 분할매도 슬라이더 패널 backtest/calculator/retirement 전탭(배당금탭 제외). 검증 7/7+tax_truth 64/64+Gate 2a/b/c 4/4+페이지200. ⚠️잔여=프론트 슬라이더 브라우저 스모크 미확인. **▶ 다음 작업 = Track G2:** transfer 엔진(현 `multi_account_loop` transfers_enabled→NotImplementedError) 신규 + **금종세자 ISA 풍차 중단·만기∞ 무한유지**(`comprehensive_years` 입력) + ISA 1억 한도 리라우팅(연금→위탁) + 3년연속 비대상시 재가입. 플랜 = `trackG_multiaccount_plan.md §2-4` + `§G2`. 실행: 「Track G2 구현해줘」.

> 🧭 **2026-05-31 업데이트 13 (금융소득 종합과세 상세 설계 — 구현 대기):** 오너 디테일 결정 후 플랜 구체화. 코드 실상 = 매년 배당 종합과세는 작동(단 `_ytd_income` 0 시작), **청산/실현 시세차익이 그 해 배당과 합산 안 됨(15.4% 분리)이 핵심 갭.** 결정: 금융소득=이자+전배당+KR_FOREIGN차익(US양도 별도, ISA/연금 제외) / end_value=일괄청산 종합과세+분할매도 슬라이더(소득구간별 상세) / 금종세자=ISA 풍차 중단·만기∞ 무한유지(해지X)·한도참시 연금→위탁 리라우팅·3년연속 비대상시 재가입. 플랜 = 세금 `Phase 2f` + trackG `§2-4` 신규. 다음=구현. 상세 [[log]].

> 📋 **2026-05-31 업데이트 12 (계획파일 동기화 + 다음=금융소득 종합과세):** 전 계획파일(ETF_BACKFILL Phase 7/Stage B, PROJECT_MASTER_ROADMAP, 세금 plan)을 현 상황으로 갱신 — 배당 백필 Stage A/B 완료, 세금 Phase 2c 재검증 완료 반영. **다음 작업 확정 = 금융소득 종합과세 완전 구현.** 종합과세 엔진 수학(`base_tax`)은 완료, 갭 = ① `other_financial_income` 자동산출(현 backtest_logic 수동값/0) ② 분할매도 패널 전탭 배선(현 백테스트만) ③ `TaxedDividendEngine._ytd_income` 기존 금융소득 주입(현 0 고정). 데이터 토대(배당·채권) 완성돼 블로커 없음. 상세 = `세금에서시작된완전리팩토링계획.plan.md` 다음 액션.

> ✅ **2026-05-31 업데이트 11 (US 채권 ETF 자동백필 + 통화가드):** 수동 dict(10종)→**영문명 키워드 분류기**로 US 채권 자동백필. `classify_us_bond_etf`(국채 만기버킷·회사채 DBAA·광범위본드, HY/TIPS/Muni/MBS/해외채=안전스킵). `bond_config` US Fixed Income 게이트(주식 오탐 방지). **회사채 yield=DBAA**(Moody's Baa, BAML은 FRED 3년제한). **통화가드** `unsupported_currency`(엔화/유로/위안)→채권백필 거부, **엔화노출 미국채 3종 차단 확인**(유저 우려 케이스). 검증: 유닛 34/34, 561종 중 300분류/261스킵, 실데이터 대부분 ≤0.7p(VCSH 1.56p·BLV 2.09p Grade C). **❗서버에 `fetch_us_credit_rates.py` 실행 필요**(DBAA). HY는 장기yield 없어 미구현(후속). 상세 [[log]].

> ✅ **2026-05-31 업데이트 10 (Stage B 헤지비용·회사채·KR금리복구 — 서버검증 완료, f175b8a 배포):** 핸드오프 2문제 구현+검증. ❶ **헤지비용:** `build_bond_price_series(hedge_cost_pct=)` + backfill `hedge=="hedge"` ETF에 `(DGS3MO−CD91)/100/252` 일일차감(covered interest parity). 부호 시대별 자동(금리역전 무관). **서버검증: 헤지 ETF CAGR차 2.5p→1.0~1.5p ✅**(잔여~1p=FX베이시스 Grade C). ❷ **회사채 dur 2.6→2.0** — 갭 1.0~1.6p, 듀레이션은 갭에 무영향(주원인 carry 드리프트), Grade C 유지. ❸ KR금리 index_master 소실(로컬만)→ECOS 재수집. 회귀 없음(국채/종합채권/스트립/MMF 핸드오프와 동일). 상세 [[log]] 최상단.

> 🔁 **2026-05-31 업데이트 9 (Stage B 종합검증 — 다음 세션 시작점):** 한국 채권 전 유형 C(총수익보존, DB로 TR재구성)+D(듀레이션) 검증. 국채/스트립/종합채권/레버리지/CD·MMF = ✅ 확실(CAGR차 ≤1p). **다음 세션 = 검증이 잡은 2문제:** ❶ **한국 미국채(헤지) CAGR 2.5%p 과대 = 헤지비용 누락** → (DGS3MO−CD91)/252 차감 구현(우선). ❷ 회사채 CAGR차 1~2p(만기형, Grade C 경계). 상세 해결방향 + 파일 = [[log]] 최상단 핸드오프. 백필 전부 클리어(on-demand), 실데이터·KR금리 보존, gate 2c PASS.

> ✅ **2026-05-31 업데이트 8 (Stage B 채권 완성):** US 국채(10종 검증) + 한국(국고채 3Y/10Y/30Y·종합채권·회사채·CD/MMF carry) 채권 백필 = 듀레이션 가격모델 + 월쿠폰. 한국금리 ECOS 수집(KTB/CD/KOFR/회사채). 듀레이션 실측보정(국채 운용사 일관→단일값). 스트립=×1.6, 레버리지=기존 _apply_leverage, 만기형 회사채=단일값(롤오버 프록시). 한국 미국채 R²≈0은 한미 거래시차(누적 백필 정상). **전 채권 백필 클리어 → on-demand 재생성**(미리 안 함). 한계: 헤지비용/신용스프레드/30년변형 후속. gate 2c PASS.

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
| ✅ **배당 백필 Stage B** | 한국 채권 전유형 + 환헤지비용 + US 채권 키워드 자동분류 + 통화가드. 서버검증 완료 | 완료 | — |
| ✅ 세금 2c 재검증 | Gate 2c PASSED 3/3 (정상 배당 데이터 기준) | 완료 | — |
| ✅ **금융소득 종합과세 (Phase 2f)** | **완성** — ① 청산+중간실현 KR_FOREIGN을 배당과 합산 종합과세(공유 `TaxSessionState`) ② `_ytd_income` 외부소득 주입 ③ 연도별 종합과세 대상 트래킹 ④ other_financial_income 자동산출 ⑤ 분할매도 슬라이더 패널 backtest/calculator/retirement 전탭 배선. 테스트 7/7 + 회귀 무손상. 배당금탭은 별도엔진 제외 | 완료(프론트 브라우저 스모크 권장) | — |
| ✅ **Track G2 + 금종세 ISA 풍차 중단** | 2-1 라우팅·2-2 만기분배·2-4 풍차중단·G3/G4 공제 전부 구현(2026-06-02) → G5로 4탭 확장 완료 | 완료 | — |
| ✅ Track G 전체 | G1~G5 + L7 E2E 16/16 + GAP-DECUM-COMP 해소 — plan 종결(2026-06-13) | 완료 | — |
| ✅ Track F | ISA/계좌 규제 — 백엔드 + BUG-1~5 완료 | 완료 | — |
| PHASE4 잔여 | D4·B2-a·A4·D1·D2·C1·C2·B4 (B1·D6·E1은 완료, 2026-06-13 갱신) | 병렬 가능 | `PHASE4 다음 안전한 항목 진행해줘` |
| ETF_BACKFILL V2 Ph.3+ | etf_master/etf_proxy_map, confidence A~F | Stage A/B 후 | `ETF_BACKFILL Phase 3부터` |
| ~~E1 모바일~~ ✅(06-11) / C4 온보딩 | 반응형 완료 / 튜토리얼 | C4는 전체 안정화 후 | — |

---

## PHASE4 잔여 기능 체크리스트

**중단기 (세금/데이터 독립적 → 병렬 가능):**
- [x] D4 거래수수료 설정 ✅ (2026-06-13 — 5탭 전부: v1·계좌별·은퇴·배당, 5abbbe4~cfee467)
- [x] D5 인플레이션 검증 + 실질 생활비 표시 ✅ 7182ad1
- [x] A4 종목 상세 개선 + 캔들차트 + 시간봉 ✅ (2026-06-13 — asset_type 분류·타입별 지표·Lightweight 캔들·1일/1주 시간봉)
- [x] B1 포트폴리오 즐겨찾기/저장 ✅ a9cc1f2~e92f8f8 (2026-06-12 — 5탭 위젯+멀티계좌 카드+/myportfolios+리스크리턴도표 후속)
- [x] B2-b 자산 추이 차트 (myassets 하단) ✅ 02cb3e8
- [x] B2-c 내자산 현재가 Redis 캐싱 ✅ 1c5db23
- [x] B3 리밸런싱 경고 밴드 ✅ 02cb3e8
- [x] 알림 기능 (가격·신고가/신저가·리밸런싱, 인앱 수신함 🔔) ✅ (2026-06-17 — `/alerts` + Celery Beat 장중 15분 평가, `알림_plan.md`, 54 PASS. 잔여=라이브 검증)
- [x] C1 홈 화면 위젯·관심목록·설정 ✅ (2026-06-14 adc2ae0~040a19c — 사용자 구성 위젯 캐러셀+`/settings`. 후속 2026-06-15: 지수 캔들 회귀복구·새로고침·내자산 수동가격)
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
