# Log

## [2026-06-15] feature(WIP) | 거시경제 지표 — 데이터 레이어(Step 1/6)

신규 기능 플랜 `거시지표_캘린더_plan.md`(거시지표 탭 + 증시 캘린더, 알림 제외) 착수. 오너 한·미 지표 전체 승인.

**Step 1 완료(데이터 레이어):** 신규 `modules/macro_loader.py` — SERIES 레지스트리 86종(미국 FRED 66 + 한국 ECOS 20) + `fetch_fred`(공식 API, 키 `data/meta/fred_api_key.txt`)·`fetch_ecos`(StatisticSearch, 키 `data/meta/ecos_api_key.txt`)·`backfill`·`validate`. 신규 테이블 `macro_series`(메타)·`macro_observations`(시계열) in `index_master.db`. **전 코드 라이브 실호출 검증 → 86/86 적재 = 283,536행.**

**코드 확정(실호출):** FRED 69종 중 68 존재 — 제외 2 = `GOLDAMGBD228NLBM`(폐지 HTTP400, 금은 기존 KRX_GOLD/yfinance 보유)·`USALOLITONOSTSAM`(OECD 미 CLI FRED 최신 2024-01 stale). 한국 ECOS = KOSIS 불필요 확정(고용 901Y027/실업률 I61BC·고용률 I61E·참가율 I61D, 산업생산 901Y033/[A00,1], 선행지수 901Y067/I16A, M2 161Y005/BBHS00, GDP 200Y107/10601, BSI 512Y008/[BA,99988], CSI 511Y002/FME, 주택가격 901Y062/P63A, 가계신용 151Y001 등 전부 ECOS 수록). 2차원 통계표 item 순서·GDP 가격기준 라이브 검증 완료.

**Step 4 완료(/macro UI, 로컬 검증·미배포):** 오너 결정 = 레이아웃 A(국가토글 US/KR/비교 + 카테고리 섹션 + 카드그리드), 카드클릭→전체 시계열, 한미비교는 단위별 자동(%·%p 원값 / 그 외 시작=100 정규화). 한국 국채금리 4종(817Y002 KTB1/3/10Y·CD91) 레지스트리 추가 → 90종. 신규 `templates/macro.html`+`static/js/macro.js`(SVG 스파크라인 90카드·경량, 상세/비교=Chart.js, 날짜→연단위 선형축으로 date-adapter 의존 회피) + 라우트 `/macro`·`/api/macro/{overview,series/<code>,compare}` + base.html nav/사이드바("🌐 거시지표"). 검증 = 라이브 엔드포인트 4종 + Playwright(US 67카드·KR 23·스파크 67·상세캔버스·비교캔버스·12쌍·비교모드문구·콘솔에러 0).

**배포 완료(커밋 0df9740):** push→Actions→Hetzner. deploy.yml에 `venv/bin/python -m modules.macro_loader --ensure || true`(서버 테이블 비었을 때만 최초 백필; FRED/ECOS 키 서버보유) 추가. 서버 자동백필 작동 확인 = 프로덕션 `/api/macro/overview` 90종 반환. 읽기경로 ensure_schema로 빈테이블 크래시 방지(C1 index_ohlc 교훈). **라이브 검증:** Playwright(moneymilestone.duckdns.org/macro) US 67·KR 23카드·상세/비교 캔버스 렌더·콘솔에러 0.

**오너 라이브 피드백 후속(같은 날, Step4 보강):** ① **전체 히스토리** — fetch start 1990 하드캡 제거(FRED 1900-01-01·ECOS 1900) → 시리즈 출범부터(DGS10 1962·CPI 1947·UNRATE 1948, 총 394,593행). `ensure_data`가 1990캡(US_DGS10 min date≥1990) 감지 시 서버 자동 재백필 → 배포만으로 히스토리 업그레이드. ② **PC 풀폭** — `.main-content`가 grid `1fr 308px`라 좁은 1fr에 갇혀 2칸/줄이던 것 → `.mc-wrap{grid-column:1/-1}` + max-width 1560 + 조밀 그리드(minmax 158) = PC 6칸/줄(C1 설정페이지와 동일 패턴). ③ **검색** — US/KR 뷰 상단 검색창, 이름 부분일치 실시간 필터. ④ **임의 겹쳐보기**(🔬 토글) — 단위 무시하고 N개(≤6) 추세 비교. 거시지표 90종 + **종목/ETF/지수**(`/api/search`+`get_symbol_data`) 검색추가. 기본=공통 시작점=100 정규화, 2개일 땐 원값 좌우 2축 토글. 신규 `/api/macro/multi?keys=`(토큰 = 거시코드 또는 `SYM:<종목>`). 검증 = Playwright(PC 6칸·검색 4건·커스텀 기본2+차트·AAPL 종목추가 3칩·콘솔에러 0) + multi 엔드포인트(KR_M2 270 + USDKRW 17444 + AAPL 6651 혼합).

**겹쳐보기 고도화(피드백 후속, PART C C1·C2):** ① **비교 구간 설정** — 커스텀에 시작/종료일 date 입력 + 퀵(1·5·10년·전체), 정규화 기준점 = 사용자 구간 시작일(기존 공통 최소일 고정 → 변경). ② **N≥3 다축** — "정규화 ↔ 원값(개별 축)" 토글을 전 N에서 제공(기존 3개↑ 자동 정규화 폴백 해제, Chart.js 시리즈별 y축 좌우 교대·축틱 색상=시리즈색). `drawDual`→`drawAxes`(N축 일반화). 검증 Playwright(구간컨트롤·원값모드·3칩 다축·1년 퀵→시작일·콘솔에러 0). **C3(포폴 비교탭 통합)=큰 작업, 계획만 기록.**

**다음:** Step 3 Celery beat 자동갱신 → Step 5 설명 콘텐츠(LLM, macro_series.description 현재 빈값) → Step 6 캘린더(`market_events` + yfinance 실적 + FRED releases) / PART C3 포폴비교 통합(오너 결정).

## [2026-06-15] fix+feature | C1 버그픽스 4종 + 지수 캔들 회귀 복구 + 새로고침/수동가격

오너 라이브 피드백 후속(C1 배포 후 발견 버그 + 신규 요청).

**C1 버그 4종(커밋 7394171):** ① **지수 캔들 회귀** — 홈 지수 클릭→상세 캔들 비활성. 원인 = `index_daily`가 종가만(OHLC 컬럼 없음). 캔들 렌더러(거래량 히스토그램 포함)는 51c5d0c 이후 멀쩡, 데이터만 없던 것. 51c5d0c가 가용성 체크를 `allData.prices[0].open`(일봉 고정)으로 바꿔 지수 무조건 disabled가 된 게 회귀. **신규 `index_ohlc` 테이블(code,date,OHLCV)** + `scripts/backfill_index_ohlc.py`(^GSPC·^IXIC·^KS11·^NDX·^DJI·^N225·GC=F·SI=F·CL=F·NG=F·HG=F·KRW=X yfinance period=max) → `price_loader.get_symbol_data` 지수 분기가 index_ohlc 우선 반환(라인=index_daily 유지, 1H=intraday 온디맨드 그대로). ② PC 홈 위젯 좁은 `<table>` → `.market-grid` 3칸(큰 값+큰 스파크), 죽은 `.wt-*` CSS 제거. ③ 설정 PC = `.main-content` 2칸그리드(`1fr 308px`)의 308칸에 끼던 settings-wrap → `grid-column:1/-1`+`width:100%` 풀폭 + `#weList` 멀티컬럼. ④ 홈 로딩 느림 = 위젯 시세가 무거운 `get_symbol_data`(2000~전체 history) → 경량 `_wl_recent_closes`(인덱스=index_master 25행 / 주식=`get_price` 45일창 / index_daily에 없는 ^KS11 등=yfinance 폴백).

**핫픽스(커밋 8be53b9):** 직전 배포가 라이브에 `index_ohlc` 없어 `SELECT`가 "no such table"→"종목 못찾음" 크래시. `CREATE TABLE IF NOT EXISTS` + 데이터 없으면 yfinance **지연 백필**(첫 지수 진입이 자동 적재 → 수동 서버작업 불필요). `_wl_recent_closes`도 try 폴백. 기존 데이터 불변(신규 테이블 생성·삽입만).

**새로고침+수동가격(커밋 6ccf735 + 이번):** 오너 결정 = 새로고침 floor **15분 고정**(yfinance 15분 지연과 동일 → 더 자주 호출해도 같은 값, 밴 방지. 공유 Redis 캐시라 종목당 TTL 1회만 API, 전 사용자 dedup). 범위 = 내자산(필수)·홈·검색. **내자산:** `holdings.manual_price` 컬럼(ALTER 마이그레이션) + `set_manual_price`/`POST /api/myassets/manual-price`(null=해제) + `myassets_data`가 수동가 설정 종목은 fetch 무시·그 값(KRW) 사용+`manual_codes` 반환 + 현재가 셀 ✎입력·↺자동복귀·"수동" 배지 + 🔄. `_asset_ttl` 15분 고정. **홈:** 위젯 헤더 🔄→`refreshWidgets`(loadWidgets). `_watchlist_quote` TTL 15분 고정. **검색:** 컨트롤바(문구+🔄) → `refreshSearchPrices`가 보이는 종목을 `/api/watchlist/quotes` 라이브로 카드 가격/등락 덮어씀(초기 렌더는 price_daily 종가). 전 화면 "⚠ 시세 약 15분 지연 — 새로고침해도 실시간과 다를 수 있습니다" 문구.

검증 = `test_home_widgets.py` 16 PASS + 수동가격 override/해제 왕복(test_client) + Playwright(^GSPC 캔들+거래량 1D·1H 렌더 / 홈 PC 6칸 그리드 / 설정 3컬럼 / 내자산 🔄·수동배지·✎↺ / 검색 005930 ₩322500 라이브 덮어쓰기 / 전 화면 문구). index_ohlc 드롭=라이브 모사로 지수 상세 4종 무크래시 자동복구 확인.

**▶ 다음 = 홈/검색 새로고침 라이브 확인 / PHASE4 잔여(D1·D2·C2·B4) — 오너 결정.**

## [2026-06-14] feature | C1 — 홈 화면 위젯 + 관심목록 + 설정 페이지

PHASE4 C1(관심종목) 확장판. 오너 결정으로 단순 watchlist를 넘어 **홈 시장지수 위젯의 사용자 구성화 + 다중 관심목록 + 설정 페이지**로 확대. 계획 = `C1_watchlist_plan.md`.

오너 결정: 비로그인=기본값만(편집 로그인유도) / PC=상단 탭 / 종목추가=기존 /api/search + 지수·환율 프리셋 / 설정탭=`/settings` 신규(확장형, 그 안 "홈화면 설정" 섹션) / 모바일=스와이프(위젯당 6개/페이지, 넘으면 다음 페이지) / 기본값=현재 홈 6종.

**Phase 1 백엔드(adc2ae0):** `user_settings.home_widgets`(JSON) 컬럼 마이그레이션 + auth_manager `get_home_widgets`/`save_home_widgets`. `app.py` DEFAULT_HOME_WIDGETS(6종) + `_watchlist_quote`(get_symbol_data 기반 경량 시세 — value/change/up/spark, Redis mq:wl:<code> 캐시) + `_clean_home_widgets`(검증: 위젯1~10·이름1~20·종목1~30) + `GET/POST /api/home-config` + `GET /api/watchlist/quotes`. 검증 `test_home_widgets.py` 16 PASS.

**Phase 2 홈 렌더(2a65515):** 정적 market 카드 → 동적 위젯. `loadWidgets`(config+quotes fetch) + `renderWidgets`(matchMedia 분기). PC=`_renderTable`(위젯 탭바 + 표: 종목·현재가·등락%·스파크, 행클릭→symbol). 모바일=`_renderMobile`(전 위젯을 6개씩 페이지로 평탄화한 scroll-snap 캐러셀 + 도트, 스크롤 시 제목·도트 동기화). 헤더 ⚙→/settings. 검증 `test_home_widgets_live.js` 라이브 10 PASS(PC표 6행+^GSPC / 모바일 캐러셀·도트).

**Phase 3 설정 페이지(180c0b2, 040a19c):** `/settings`(settings.html, 확장형 섹션) + base.html 사이드바·nav "설정". "홈 화면 설정" 섹션 = 위젯 매니저(이름 인라인 편집·▲▼ 순서·추가/삭제, 위젯별 종목 칩 ✕·종목추가 검색모달[/api/search]+지수/환율 프리셋칩·저장 POST). 비로그인→로그인 게이트. ⚠️ 기존 `/settings`=tax_settings 별칭 충돌 제거(tax=/tax-settings 유지). 검증 `test_settings_browser.js` 로컬 로그인 12 PASS(게이트·위젯 CRUD·검색/프리셋·저장 왕복·삭제·콘솔에러0) + 라이브 설정 게이트 PASS.

전부 가법 — 기존 /api/market·tax-settings 무영향. 잔여(소) = 다크/반응형 육안.

## [2026-06-14] feature | 부채꼴 후속 — 세로 2배 + 슬라이더 in-place 애니 + 줌

오너 피드백 3건. ① 세로 너무 좁음 → 전용 `.chart-wrap-fan` 240→480px(모바일 360, calculator.css). ② 슬라이더 굴릴 때마다 차트 재생성 → x축서 솟는 애니 거슬림. `_drawFan`(최초 생성)/`_updateFanBands`(슬라이더) 분리 — 기존 차트의 하단·상단 데이터셋 data/label만 교체 후 `chart.update()` → 중앙선(p50) 불변·밴드 경계만 부드럽게 morph. ③ 줌 = `chartjs-plugin-zoom@2.2.0` CDN(base.html, Chart.js 뒤) + fan options.plugins.zoom(`wheel.modifierKey:'ctrl'`·pinch·pan xy) + 카드에 조작 힌트("🔍 Ctrl+휠 확대·축소 · 드래그 이동 · 핀치") + `resetFanZoom()` [줌 초기화] 버튼. Ctrl 게이팅으로 일반 휠 스크롤 보존.

검증: `tests/test_fan_dom.js` jsdom 15 PASS(줌 config·중앙선 불변·in-place 갱신·resetFanZoom 무오류) + `tests/test_fan_live.js` 라이브 12 PASS(줌 플러그인 resetZoom 존재·높이>400·중앙선 불변·콘솔에러 0). 커밋 eddcdc5. 캐시 v20260614fan2.

**후속 fix(ad3fe59, v20260614fan3):** 슬라이더로 밴드 좁히면 y축이 데이터 범위 따라 자동 확대 → 프레임이 매번 바뀌어 변화 인지 어렵다는 오너 피드백. y.min/max를 전체 분포(p1~p99) 범위로 고정(`Math.min(bands[0])`~`Math.max(bands[98])` ±5% 패딩) → 슬라이더 조정 시 프레임 불변, 밴드 경계만 그 안에서 이동. 수동 줌은 플러그인이 별도 override라 그대로. 검증 jsdom 17 PASS + 라이브 13 PASS(y축 고정 확인).

**후속 3(e99d9d0, v20260614fan5):** range input 팬 슬라이더가 게이지처럼 보이고 가로가 안 부드럽다는 피드백 → **커스텀 스크롤바**로 교체. 트랙(`.fan-scroll`)+thumb(`.fan-scroll-thumb`, 폭=창/전체 비율) 잡고 pointer 드래그로 부드럽게 팬(step 없음). `_fanThumbDown`(thumb 잡기→document pointermove/up)·`_fanPanTo(axis,frac)`(창 위치 설정)·`_syncFanScroll`(thumb 크기·위치·disabled 동기화, 휠줌 후 onZoomComplete/onPanComplete 콜백). 세로=우측(top=고액), 가로=하단. 미확대 시 `.disabled`(opacity 0). 검증 jsdom 24 PASS + 라이브 16 PASS. **줌 플러그인 CDN을 jsdelivr→cdnjs(Chart.js와 동일 호스트)로 옮기고 `defer` 부여 — head 외부 스크립트 파서 블로킹 제거(CDN 행 시 페이지 렌더 멈춤 방지). 줌은 계산 후 사용이라 defer로 타이밍 안전.** ① 줌 초기화 = 전체 복귀 대신 **현재 선택 밴드(하단~상단)에 맞춰 y 재규격화**(`resetFanZoom`이 rowLo min~rowHi max ±8% + resetZoom으로 수동줌 클리어, _fanFull.y 갱신). ② 드래그 팬이 데스크탑서 불편 → **가로(x축 하단)·세로(y축 우측) 팬 슬라이더** 추가(`onFanPan`이 _fanFull 전체범위 기준으로 보이는 창 이동, `_syncFanPan`이 휠줌/팬 후 슬라이더 위치·활성 동기화 — `onZoomComplete`/`onPanComplete` 콜백, 미확대 시 disabled). 세로 슬라이더 = `writing-mode:vertical-lr`+`appearance:slider-vertical`. ③ Ctrl+휠 확대축소 유지. 검증 jsdom 23 PASS(리셋 밴드fit·팬 창이동·활성/비활성) + 라이브 16 PASS(팬 슬라이더 존재·미확대 비활성·리셋 밴드fit). ⚠️ 세로 슬라이더 시각 방향은 오너 육안 권장(크로스브라우저).

## [2026-06-14] feature | 투자계산기 미래 시나리오 부채꼴 (경험적 퍼센타일 밴드)

오너 요청 = 부채꼴 차트. 핵심 결정 = **미래 예측 신규 0, 있는 데이터(과거 롤링 윈도우)를 "이렇게 굴러갈 수도 있다"는 시나리오로 시작점에 모은 경험적 부채꼴.** (GBM·모수 몬테카를로 아님 — 용어 정리: 현재 GBM 합성은 과거 백필용이고 그 자체가 이미 몬테카를로. 부채꼴은 별개로 미래 예측 안 하고 실측 궤적만 겹침.)

오너 결정(AskUserQuestion 2라운드): 단일 Y축 절대금액₩ / x=경과 연차(1년차~N) / 별도 새 카드 / 듀얼핸들 슬라이더로 밴드 하단·상단 퍼센타일 **각각 1% 자유 조정**(기본 p25~p75) + p50 중앙선 / 합성 윈도우는 사용자 allow_synthetic 체크 따름(별도 필터 X) / 단일+멀티계좌 합산 둘 다.

구현(전부 가법 — 기존 로직·값 무변경):
- **백엔드** 공유 헬퍼 `modules/multi_account_common.py:yearly_trajectory(history, years, final_value)` — 윈도우 history(date·portfolio_value)에서 연차 offset별 자산값, 최종점=세후 end_value(헤드라인 일치). 단일 `accumulation_analyzer._run_rolling`·멀티 `multi_account_analyzer._run_rolling`이 case에 `metrics["_yearly"]` 부착(합산은 combined_history_df). `calculator_logic._build_fan(cases, years)` = 윈도우들 `_yearly` 모아 `np.percentile` p1~p99×(연차+1) 그리드 산출(서버 사전계산 → 슬라이더가 서버 재호출 0으로 임의 밴드 즉시 그림, 표본<5면 None). 양쪽 응답에 `fan` 키 추가. `_yearly` 원본은 cases_summary에서 제외(페이로드 보호).
- **프론트** `calculator.html` 부채꼴 카드(`#fanCard`: canvas + 듀얼 range 슬라이더 + 범례), `style.css` 듀얼레인지 오버레이 CSS(`.fan-slider` pointer-events 트릭), `calculator.js` `renderFan`(카드 표시/숨김·그리드 저장)·`onFanSlider`(하단<상단 강제·라벨 갱신)·`_drawFan`(Chart.js line 3데이터셋, 상단 fill:'-1'로 밴드 채움, x='시작/N년차'). renderResult에서 `renderFan(data.fan)` 호출. 캐시 `?v=20260614fan`.

검증: `tests/test_fan_logic.py` **15 PASS**(yearly_trajectory 궤적·final_value 오버라이드·빈값 / _build_fan 그리드 shape·year0 동일·p50 median·퍼센타일 단조·표본<5 None·길이불일치 제외) + `tests/test_fan_dom.js` **jsdom 12 PASS**(기본 25/75 밴드 선택·슬라이더 조정·하단≥상단 보정·null 숨김) + 실데이터 통합(SPY 단일 229윈도우, 2계좌 멀티 202윈도우 — fan 생성·year0 밴드폭0·p25<p50<p75 단조·`_yearly` 누설 0). ⚠️ 실브라우저 미검증·미배포(배포는 라이브 브라우저 테스트 선행).

## [2026-06-14] feature | 투자계산기 롤링 차트 보기 전환 (최종자산/CAGR/연도별)

오너 요청 = 롤링 차트("시작 시점별 종료 자산") 위에 버튼 3개로 보기 전환. **기본 = 최종자산**(수익률 낮은순 정렬) / **CAGR**(수익률순, 음수면 빨강) / **연도별**(기존 시작 시점별, 입력 순서 유지).

설계 경위: 처음 "이중 Y축(왼쪽 CAGR·오른쪽 최종자산, 막대 1세트)" 논의 → 거치식은 CAGR↔최종자산 1:1이라 양축 정확하나 **월적립 있으면 같은 CAGR라도 최종자산 갈림 → 한쪽 축 근사** 발견. 오너 결정 = 이중축 폐기, **단일 Y축 3모드 분리**.

구현(프론트 전용, 백엔드·데이터 무변경): case별 `cagr`는 이미 응답에 존재(`calculator_logic.py:400`). `static/js/calculator.js` `renderRollingChart`를 상태화(`_rollingCases`/`_rollingMode`, 기본 `asset`) + 신규 `setRollingView(mode)`(정렬·라벨·색상·툴팁·제목·버튼 active 전환) + `_renderRolling` 내부 렌더. `asset`/`cagr`는 cagr 오름차순 정렬, `year`는 입력순 유지. `templates/calculator.html` 차트 카드에 `.rchart-head`+`.rchart-seg` 버튼 3개, `static/css/style.css`에 segmented 버튼 CSS. 캐시 `?v=20260614rollview`(calculator.js + style.css/base.html).

검증: 신규 `tests/test_rolling_view_dom.js` **jsdom 9 PASS**(Chart 모킹 — asset 최종자산·cagr순 정렬·전부 초록 / cagr CAGR%·음수만 빨강·제목·버튼 active / year 입력순 유지) + `node --check` OK. ✅ **커밋(62a3a04)·push·배포 후 `tests/test_rolling_view_live.js` 라이브 11 PASS** — 프로덕션에서 실 Chart.js 렌더 + 실 버튼 onclick 클릭 + 정렬/색상/제목/active/콘솔에러 0 확인(결과 카드는 계산 전 hidden이라 fake cases 주입+조상 노출 방식).

## [2026-06-14] fix | 비교탭 모바일 표→항목카드(가로스크롤 제거) + 상세 자산추이 차트 2배

오너: 비교탭 패딩/폰트만 줄인 1차 모바일 수정은 11열 표라 가로스크롤 그대로 → 효과 미미(반영은 됨, 인라인 style이라 캐시無). ① **비교탭 모바일 = 항목별 카드**(포폴/벤치마다 카드, 지표 라벨/값 2열 그리드 세로 나열) → 가로스크롤 제거. 데스크탑은 표 유지, `window.resize`로 표↔카드 전환(`rrLastData` 재렌더). `#rrTable`→`#rrTableHost` 호스트 div. ② **상세 자산추이 차트** canvas 래퍼+`maintainAspectRatio:false`, 데스크탑 180px·모바일 340px(약 2배). CSS+JS, 백엔드 무변경. 검증 = risk_return·portfolio_detail JS `node --check` OK. 커밋 6a61770.

## [2026-06-14] fix | 배당성장률 마지막연도 제외 + 모바일 최적화(내포폴·비교·상세)

오너 후속 2건. ① 배당 성장률 차트 **마지막 연도 제외**(그 해 배당 다 못 받아 낮게 보임) — `renderDividendGrowthChart`에서 `full.slice(0,-1)`로 마지막 빼고 성장률·CAGR 계산(막대 1개 이상 위해 3년+ 필요). ② **모바일 최적화** — `risk_return`(.rr-card 패딩↓·수치표 셀 패딩/폰트↓·[비교하기] 풀폭·검색/투명도 풀폭), `myportfolios`(헤더 wrap·+버튼 풀폭·모달 액션 flex), `portfolio_detail`(금액박스 wrap·계산버튼 풀폭). CSS만(JS 무변경, backtest만 성장률 JS 변경).

검증: backtest JS `node --check` OK. ⚠️ 실모바일 미검증.

## [2026-06-14] fix | 백테 배당차트 낙폭아래 이동 + 배당성장률 그래프 + 비교탭 기본 불투명도 18%

오너 후속 3건. ① 백테 연간 배당금 차트 → **낙폭(drawdown) 아래로** 순서 이동. ② **배당 성장률 그래프** 추가(전년대비 증가율 막대 + 전체 배당 CAGR 노트). ③ 비교탭 스파이더 기본 투명도 50→**18%**(0=완전투명·100=불투명, 슬라이더 max 60→100, 라벨 "불투명도").

- `backtest.html`: 차트 순서 = 가치추이→연간수익률→낙폭→**연간배당금→배당성장률**. `renderDividendGrowthChart(annual_dividends)` 신규 — YoY 증가율(첫해 제외, 2년 이상만 표시) + `Math.pow(last/first, 1/n)-1` 전체 CAGR 노트. 백엔드 무변경(annual_dividends 재사용·성장률은 프론트 계산).
- `risk_return.html`: `rrOpacity` 0.25→0.18, 슬라이더 0~100.

검증: backtest·risk_return JS `node --check` OK. ⚠️ 실브라우저 미검증.

## [2026-06-14] feature | 비교탭 스파이더 축선택·지표설명 + 백테 연간 배당금 차트 + 계산기/백테 지표 설명

오너 후속 5건. ① 비교탭 스파이더 **꼭짓점(축) 종류 선택** — 7후보 풀(수익률·안정성·방어력·배당률·Sharpe·Sortino·승률) 체크박스, 최소 3개. ② 축 선택창 옆 **설명 1-2줄**(선택 축 설명 리스트). ③ 비교탭 CAGR → **"수익률(CAGR)"** + 수치표 헤더 hover 설명(ⓘ). ④ 계산기·백테 **각 지표 설명 1-2줄**. ⑤ **백테 탭 연간 배당금 차트**(비교탭보다 정보 적으면 안 됨).

- **비교탭** `risk_return.html`: `SPIDER_POOL`(7축)+`rrAxisKeys`(기본6)+`rrToggleAxis`(최소3 유지·풀순 정렬), 컨트롤에 축 체크박스+설명박스 추가. 수치표 cols에 desc → `<th title>ⓘ`. 레이더 라벨 'CAGR'→'수익률', 수치표 헤더 'CAGR'→'수익률(CAGR)'.
- **백테 배당** `backtest_logic.py`: 두 경로(`_run_multi_account_backtest_logic`·`run_backtest_logic`) 연도 groupby에 `annual_dividends`(dividend_income 연합산) 추가 → 반환. `backtest.html`: 연간수익률 뒤 **연간 배당금 막대 차트**(`#btDivCard`·`renderAnnualDividendChart`, 데이터 없으면 숨김) + btMetrics 각 항목 desc → `title` hover ⓘ.
- **계산기** `calculator.html`: 히스토그램 9카드(종료자산·CAGR·MDD·Sharpe·Sortino·Calmar·총배당·배당CAGR·마지막연도배당) 제목 밑 `.result-card-desc` 설명 줄.

검증: run_backtest_logic(SPY 2018~23 cash) → `annual_dividends` 6행 증가·합계=total_dividend(1,441,476) 일치 PASS. risk_return·backtest JS `node --check` OK. backtest_logic syntax OK. ⚠️ 실브라우저 미검증.

## [2026-06-14] feature | 포트폴리오 비교 탭 (리스크-리턴 → 종목선택+11지표표+산점도+레이더+공유)

오너: 포트폴리오끼리 비교 — 리스크리턴만으론 부족. 브레인스토밍 후 채택 = ④스파이더 + ⑤몬테카를로 부채꼴. **단 몬테카를로는 대공사라 이번엔 제외**(추후). 기존 `/risk-return`을 **"포트폴리오 비교"** 탭으로 확장.

- **결정(2026-06-14)**: 지표 필수+고급(CAGR·변동성·MDD·Sharpe·배당률 + Sortino·최고/최저연·승률·베타) / 공통 겹침 기간 자동 / 벤치마크 기본셋 유지(SPY·QQQ·GLD·069500·TLT, 삭제·추가 가능) / 몬테카를로 제외 / 스파이더 표시토글+투명도 슬라이더 / 이미지·링크 저장(계산기 share 재사용).
- **백엔드** `risk_return_logic.py`: `_metrics_full()` (기존 cagr/vol/sharpe + mdd·sortino·연최고/최저·월승률·베타) + `compute_comparison(portfolios, benchmarks, loader)`. 베타 기준 = SPY 항상 로드(표시무관). 배당률 = 종목별 직전1년 배당합÷마지막종가 → 비중가중. 기존 `compute_risk_return` 보존.
- **API** `app.py`: `POST /api/portfolio/compare` ({portfolio_ids, benchmarks}). portfolio_ids 빈배열=선택0, 키부재=전체. 기존 `/api/risk-return` 보존.
- **프론트** `risk_return.html` 전면 개편: 내 포트폴리오 체크박스(전체 기본선택)+벤치마크 칩(기본셋+검색)+[비교하기] → 11지표 수치표 + 리스크리턴 산점도(점=항목) + 레이더 6축(CAGR·안정성=1−vol·방어력=1−|mdd|·배당률·Sharpe·Sortino, 상대 min-max 정규화·클수록 좋음) + 항목별 표시 체크·투명도 슬라이더 + 🔗링크/📷이미지(html2canvas→/api/share/upload).
- **nav** `base.html`: "리스크-리턴" → "포트폴리오 비교" (📊).
- 계획 = `포트폴리오비교_plan.md`.

검증(venv test_client): compare(2포폴+SPY/GLD) 200 — **SPY 베타=1.0 sanity·TLT혼합 0.62·QQQ MDD-80%(닷컴)·GLD 배당0**. 페이지 200(제목 확인). 벤치마크-only(포폴 0) 200. JS `node --check` OK. ⚠️ 실브라우저 미검증.

## [2026-06-14] fix | 포트폴리오 상세 후속 — 월칸 토글버그·CTA 상단확대·기본금액 1천만

오너 피드백 3건. ① 월별 네모칸 버그: 분기배당(3·6·9·12월만)일 때 3월 클릭하면 배당 없는 1·2·4·5월까지 파랗게 선택됨. **원인 = `classList.toggle('active', cond)`에서 빈 달은 `dataset.month` undefined → `undefined && ...` = undefined → toggle 2번째 인자 undefined면 force 무시되고 매번 토글되어 active 추가**. 수정 = `!!(...)`로 boolean 강제. (myassets·portfolio_detail 동일 버그 둘 다.) ② 백테/계산기 유도 CTA 일반 사용자가 못 찾음 → 배당 박스 **밖, 자산현황 탭 맨 위 정적 배너**로 이동·확대(아이콘 2rem·제목 1.1rem 볼드·본문 0.92rem, 연파랑 유지). myassets는 `#divCta` 동적 채우기 제거 후 tab-overview 첫 카드로, portfolio_detail은 제목 아래 배너. ③ portfolio_detail 총 투자금액 **기본값 1천만원** — 진입 즉시 자동 계산(localStorage 저장값 있으면 그것, 없으면 10000000). 변경 = `templates/myassets.html`·`templates/portfolio_detail.html`(JS·HTML만, 백엔드 무변경). 검증 = JS `node --check` 2파일 OK.

## [2026-06-14] feature | 저장 포트폴리오 상세(총투자금액→비중 자동배분→추이·배당) + 내자산 배당일정 월별칸·홍보문구 강조

오너: ① "내 포트폴리오" 저장 카드 클릭 → 내자산 같은 상세 화면. **총 투자금액 1칸만 입력** → 저장된 비중대로 자동 배분(수량 자동 환산) → 받은/예측 배당·자산추이·비중 표시. 입력창은 **상세 페이지 맨 위, 카드는 항상 표시**(입력해야 나오는 게 아님). ② 내자산 배당 CTA(백테/계산기 유도)가 너무 작음 → 크게·눈에 띄는 색(튀지 않게). ③ 배당 일정 — 막대 클릭 말고 **월별 네모칸** 누르면 표로 펼침.

※ 1차 구현은 종목별 수량 입력이었으나 오너 피드백("수량 말고 총액 하나만, 비중 자동")으로 **총 투자금액 단일 입력 모델로 재설계**.

- **백엔드(app.py)**: `_compute_portfolio_history(valid)` 헬퍼 추출(기존 `/api/portfolio/history`가 호출) → 재사용. 신규: 페이지 `/myportfolios/<id>`, API `GET /api/portfolio/item/<id>`, `POST /api/portfolio/compute`, `POST /api/portfolio/dividends-preview`(내자산 `build_dividend_chart` 동일 엔진). 공통 헬퍼 `_amount_to_holdings(amount, tickers[{code,weight}])` = **수량 = 총액×(비중/100)÷현재가(KRW)** 산출 후 holdings 생성. `auth_manager.get_portfolio(uid,pid)` 추가.
- **신규 페이지 `portfolio_detail.html`**: 맨 위 총 투자금액 입력칸(프리셋 100만~1억) + [계산]. 비중 파이(금액 무관 즉시 표시)·자산 추이(1M/3M/1Y/전체)·배당금(세전후·원외화·연도탭·막대드릴·월별 네모칸·일정 리스트). 카드 항상 표시(금액 0이면 안내). 금액 = `localStorage(pf_amount_<id>)` 보관. 내자산 배당 렌더 패턴 재사용.
- **myportfolios.html**: 카드 이름·📂 버튼 → `/myportfolios/<id>` 이동.
- **myassets.html ②**: 배당 안내(`#divNote`)에서 백테/계산기 CTA 분리 → `#divCta` 강조 박스(0.92rem, 연한 파랑 배경+테두리, 💡).
- **myassets.html ③**: 배당 일정에 12개월 네모칸 그리드(월별 합계 표시) + 클릭 시 그 달 종목별 펼침 표(`#divMonthDetail`). 기존 종목별 리스트·막대 드릴 유지.

검증(venv test_client + 세션 주입): item/상세페이지(PID 주입) 200 PASS. compute(amount 10M·weight 60/40 → SPY 수량 5.297·price>0·history keys, amount 0 → history empty) PASS. dividends-preview(458730 100% → events 2026 12개) PASS — events 키는 JSON 직렬화로 문자열("2026"), JS는 `events[number]` 자동 문자열변환이라 정상. 기존 `/api/portfolio/history` 회귀 200 PASS. JS `node --check` 3파일 OK. ⚠️ 실브라우저(Playwright) 검증 미수행 — 로그인 E2E 필요.

## [2026-06-14] fix | 배당차트 — 빈 달 예측 채움 + 일정 종목별 묶기

오너: ① 5월 비어있음(corporate_actions 실데이터가 ~3·4월까지만 → 실데이터 없는 중간/미래 달이 빈칸). ② 일정 리스트가 종목×지급일마다 행 → 너무 길다.

- **빈 달 예측 채움:** 현재연도 예측 조건에서 `m >= cur_month` 제거 → **실데이터 없는 모든 달**(과거 미반영분 포함)을 직전연도 같은 달 ×(1+CAGR)로 채움. 실데이터 있는 달은 그대로. (예: 458730 월배당 — 1~4월 실적, 5~12월 예측.)
- **일정 종목별 묶기:** `renderList`가 종목별 1행으로 집계(연 합계 + 지급월 목록 `1월·2월…` + 예측배지). 행 수 = 종목 수.

검증: `test_dividend_history.py` 7 PASS(올해혼합 단언=실/예측 달 중복없음으로 완화) + `test_dividend_chart_browser.js` 16 PASS. 변경 = `modules/dividend_history.py`·`templates/myassets.html`.

## [2026-06-14] feature | 배당차트 후속 — 캘린더→리스트 + 혼합연도 모델

오너 피드백: ① 캘린더 비직관적(호버해야 정보) → **리스트**로. ② 올해(2026)를 통째 예측하지 말고 **실데이터 있는 달까지는 실적, 이후만 예측** + **내년(2027) 전체 예측**.

- **연도 모델 변경:** years = 과거3년 실적 + **올해(실적+예측 혼합)** + **내년(전체 예측)**. 올해 = corporate_actions 실데이터(이번 달 이전 달) + 안 들어온 달(>=이번 달, 실데이터 없는 달)은 직전연도×(1+CAGR)로 채움. 내년 = 직전연도×(1+CAGR)². 이벤트별 `projected` 플래그. 기본 선택 = 올해.
- **막대 색:** 월별 예측여부로 색 분기(실적 파랑/예측 주황). 혼합연도(올해)는 한 차트에 파랑+주황.
- **배당 일정 = 리스트**(캘린더 제거): 날짜·종목명·금액 인라인 + 예측 배지. hover 불필요.
- 반환 필드 `current_year`/`full_proj_year`/`default_year`(=올해). 토글·드릴다운·CAGR·FX·가정 안내 유지.

검증: `test_dividend_history.py` 7 PASS(연도모델·올해혼합·이벤트필드·세율·FX·금skip) + `test_dividend_chart_browser.js` **16 PASS**(로컬 — 5탭·올해진행/내년예측 라벨·기본올해·혼합·리스트(날짜+금액 인라인·예측배지)·내년 전체예측·세후감소·외화환산·JS에러0). 변경 = `modules/dividend_history.py`·`templates/myassets.html`.

## [2026-06-14] feature | 내자산 배당금 차트 재설계 (연도선택+드릴다운+캘린더)

오너 재피드백: 전 연도 그룹막대(fb50d2c)가 아니라 ① **연도 선택기**로 한 해씩 보고 ② **월 막대 클릭→그 달 종목별 배당 드릴다운** ③ **차트 밑 배당 일정 캘린더(실제 달력 그리드)** 를 원했음.

- 백엔드 **이벤트 기반 재설계**(`build_dividend_chart`): 연도별 배당 이벤트 `{date·month·day·code·name·krw_pre·krw_post·usd_pre·usd_post·projected}` 반환 → 프론트가 막대(월별합)·드릴다운(월 필터·종목합)·캘린더(날짜맵) 전부 파생. 종목명 = symbol_master 조회.
- 프론트: 연도 선택기(과거3+예측1, 기본=직전 완료연도) / 단일연도 12개월 막대(클릭→하단 종목별 패널) / 12개월 미니 캘린더 그리드(배당일 마킹+hover 툴팁) / 세전·세후 × 원화·외화 토글 전부 반영.
- FX·세율·CAGR 예측·가정 안내문구는 기존 규약 유지.

검증: `test_dividend_history.py` 6 PASS(구조·이벤트필드·KR15.4%·ISA비과세·US15%+FX·예측플래그/성장·금skip) + `test_dividend_chart_browser.js` **13 PASS**(로컬 로그인 — 연도탭4·예측라벨·기본직전연도·12개월·단일막대·드릴다운·캘린더12+마킹·연도전환·세후감소·외화환산·안내·JS에러0). 변경 = `modules/dividend_history.py`·`templates/myassets.html`.

## [2026-06-14] feature | 내자산 배당금 월별 차트 (B-DIV)

오너 요청: 내자산 탭 자산추이 밑에 월별 배당금 차트. (내포트폴리오 클릭→백테/계산기 화면은 보류 — 오너가 "그건 백테/투자계산기 기능"이라 판단.)

- **레이아웃:** 연도별 그룹 막대(x=1~12월, 시리즈=연도). 과거 3년 실적 + 미래 1년(현재연도) 예측(주황 강조).
- **세전/세후 × 원화/외화 토글**(기본 세전·원화). 세후 = 일반계좌 KR 15.4%/US 15%, ISA·연금·IRP 운용중 비과세.
- **FX:** 원화보기=외화배당×ex-date 환율, 외화($)보기=원화배당÷ex-date 환율, 미래예측=현재환율.
- **미래 예측:** 종목별 최근 5년 배당 CAGR로 직전연도 월별 패턴 투영(클램프 -50~+100%).
- **가정:** 거래내역 없음 → 과거도 현재 보유수량 그대로 가정. 안내문구 명시 + 정밀분석은 백테/투자계산기 탭 유도.
- 백엔드 = `modules/dividend_history.py`(`build_dividend_chart`) + `/api/myassets/dividends`. 프론트 = `myassets.html` 카드(전용 `.div-tgl` 클래스 — `setHistoryPeriod`의 `.ma-period-btn` 일괄 active 해제와 충돌 회피).

검증: `test_dividend_history.py` 6 PASS(구조·KR 15.4%·ISA 비과세·US 15%+FX·예측 성장·금/빈 skip) + `test_dividend_chart_browser.js` 12 PASS(로컬, mint_session 로그인 — 카드·12개월·4시리즈·예측라벨·세후감소·외화환산·안내 3종·JS에러 0).

## [2026-06-14] feature | A4 후속2 — 간격별 기본 배율 + 거래량 + 1시간봉 안내

오너 피드백:
- **간격별 기본 보이는 창**(데이터는 전체 로드, 초기 줌만 — 스크롤/줌으로 전체 확인): 1시간=1~2일, 1일=~75일(2~3개월), 1주=1년, 1개월=~7년, 1년=전체. `CANDLE_DEFAULT_DAYS` + `timeScale().setVisibleRange`(일봉=날짜문자열·시간봉=unix초), 실패시 fitContent 폴백.
- **거래량 히스토그램**: 캔들차트 하단 26% 영역(별도 priceScale 'vol'), 봉 색과 동일(상승 초록/하락 빨강). 백엔드가 일봉(`get_symbol_data`)·시간봉(`get_intraday_data`) prices에 `volume` 추가, 리샘플은 합산. (라인=Chart.js는 거래량 미추가 — 빠른 가격조회용, 깔끔 유지.)
- **1시간봉 안내문구**: 캔들 1시간 선택 시 `#chartHint`에 "⚠ …시간봉은 데이터 제공 한계로 최근 약 730일(2년)까지만 표시됩니다."

검증: `test_symbol_browser.js` **31/31 PASS**(로컬) — +volume API 포함·1일봉 기본배율 일부만(75<전체)·1시간 730일 안내문구. `test_symbol_api.py` 8 PASS. 변경 = `modules/price_loader.py`·`templates/symbol.html`.

## [2026-06-14] feature | A4 후속 — 캔들/라인 탭 의미 분리 + 전체화면

오너 피드백: 라인과 캔들의 탭 의미가 달라야 함.
- **라인 탭 = 표시 기간** (1일/1주=시간봉, 1개월/3개월/1년/전체=일봉). 1일 클릭 = 하루 가격변동.
- **캔들 탭 = 캔들 1개의 간격, 기간은 항상 전체** (1시간/1일/1주/1개월/1년).
  - 1일 = `price_daily` 일봉 raw, 1주/1개월/1년 = 일봉 클라 JS 리샘플(O=첫 open·H=max·L=min·C=끝 close).
  - **1시간 = yfinance 1h 730일치 fetch**(오너 결정 — 전체 8400일은 1h 상한으로 불가, 최대 2년). `get_intraday_data(range='max')` + `_fetch_intraday(period='730d')`, price_hourly 캐시(30일 이전 row 있으면 재fetch 생략).
- **⛶ 전체화면 버튼**: Fullscreen API(`chartCard.requestFullscreen`), fullscreenchange→차트 리사이즈. 라인·캔들 공통.
- 탭 세트는 모드별 동적 렌더(`renderTabs`). KRX_GOLD 등 close-only는 캔들 토글 자동 비활성.

검증: `test_symbol_browser.js` **28/28 PASS**(로컬) — 라인/캔들 탭 세트 교체·라인 1일 시간봉·캔들 전체기간·1주 리샘플 봉수<1일·1시간 730일 봉>100·전체화면 버튼·토글 복귀·JS 에러 0. `test_symbol_api.py` 8 PASS(+max 730일 스모크 3466봉/728일). 변경 = `modules/price_loader.py`·`app.py`·`templates/symbol.html`.

## [2026-06-13] feature | A4 종목 상세 개선 + 캔들차트 + 시간봉

PHASE4 A4 전체(a/b/c/d). 오너 결정: full 범위 + Lightweight Charts CDN + 타겟+Playwright+라이브 검증.

- **A4-a/b 분류+지표(`price_loader.get_symbol_data`):** symbol_master `is_etf`+country로
  `asset_type`(INDEX/CRYPTO/KR_ETF/KR_STOCK/US_ETF/US_STOCK) 산출(없으면 보수율/AUM/KR ETF 휴리스틱
  폴백). 일봉 `prices`에 OHLC 추가(yfinance 폴백 경로도 보존). 개별주식 기초지표
  (market_cap/per/pbr/sector) yfinance `.info`에서 반환. 기존 버그(6자리=무조건 ETF 취급 →
  KR 개별주식 "KR ETF" 오표기 + 운용사/보수율 표시) 해소.
- **A4-c 캔들(`symbol.html`):** Lightweight Charts(MIT) CDN. 라인/캔들 토글 + 타입별 지표 그리드
  분기(주식=시총/PER/PBR/섹터 vs ETF=운용사/보수율/카테고리/AUM). OHLC 없는 종목(KRX_GOLD 등)은
  캔들 토글 자동 비활성+라인 강제.
- **A4-d 시간봉:** 신규 `price_hourly` 테이블 + `get_intraday_data`(온디맨드 yfinance interval=1h
  fetch+캐시, 같은 날 캐시 있으면 재사용) + `/api/symbol/<code>/intraday?range=1d|1w`. 기간 탭에
  1일/1주 추가(앞), 시간봉은 candle/line 모두 지원.
- **데이터 소스 판단:** KR 주식 기초지표는 yfinance `.info` 사용(삼성 PER/시총/섹터 정상 취득 확인).
  KRX 종목기본정보 신규 엔드포인트는 미구현(키·디버그노이즈·리스크 → 단순성 우선). KR 주식 일부는
  yfinance `.info` 희소 가능 = 알려진 한계.

검증: `tests/test_symbol_api.py` 8 PASS(분류 5종·OHLC·기초지표 키·시간봉 캐시) +
`tests/test_symbol_browser.js` 23/23 PASS(SPY ETF·삼성 주식·^KS11 캔들·KRX_GOLD 비활성·1일/1주 시간봉·
라인↔캔들 토글·JS 에러 0, 실서버 라이브) + intraday 라우트 e2e(curl) 확인.
변경 = `modules/price_loader.py`·`app.py`·`templates/symbol.html`.

## [2026-06-13] fix | BUG-KOSPI-CHART 코스피 차트 봉합 깨짐

오너 라이브 발견(홈→코스피 클릭): ^KS11 차트가 중간 급등 불연속 + 52주 최저 ₩387 비정상.
원인 = `get_symbol_data._INDEX_DB_ALIAS`가 `^KS11`(코스피)을 `KS200`(코스피200, 다른 지수·스케일)로
별칭 → DB 과거분(KS200) + yfinance 최근분(실 ^KS11) 봉합 → 스케일 불일치 점프.
수정 = `^KS11` 별칭 제거(KRW=X→USD/KRW만 유지) → 전 구간 yfinance 실코스피 일관 조회.
is_index 이름/카테고리 폴백 추가(symbol_master에 없어도 "코스피 (KOSPI)" 유지).
검증(로컬) = 40%+ 인접 점프 0개·52w저 2895(가짜 387 제거)·name 정상, ^GSPC·KRW=X 회귀 없음.
`modules/price_loader.py` 단일 파일.

## [2026-06-13] feature | D4 fast-follow ② 은퇴·배당 거래수수료 롤아웃

오너 결정: 은퇴+배당 둘 다, 은퇴 fee = **적립+인출 양 단계**. 배당 합성 경로는 거래 없는
순수 자산수학 → fee 미적용(기술 강제, 실데이터 경로만).

- **은퇴 적립:** AccumulationAnalyzer·MultiAccountAnalyzer는 이미 fee 파라미터 보유(D4 v1) →
  `retirement_logic`이 body fee_enabled→fee_rate·stock_tickers 전달(단일·멀티).
- **은퇴 인출:** `withdrawal_analyzer`에 fee_rate/stock_tickers 신규 — `_run_one_withdrawal`이
  SimulationConfig(세금경로)·Portfolio(비세금경로)에 주입, 케이스별 total_fees → run() 중앙값.
  `retirement_planner`가 적립 분포 중앙값 + 인출 샘플 중앙값 합산해 report['total_fees'].
- **멀티 가구인출:** `multi_account_withdrawal._build_account_runtime` Portfolio에 spec.fee_rate 주입,
  window→rolling→samples로 total_fees 스레딩(합성 윈도우 포함, 동일 엔진 경유).
- **인출기(standalone):** `run_withdrawal_logic` 단일(WithdrawalAnalyzer)·멀티(가구인출) fee 패스스루.
  retirement.html이 은퇴설계+인출기 2모드 1템플릿이라 fee UI 공유 → 양쪽 다 동작해야 일관.
- **배당:** `dividend_simulator._simulate_one` Portfolio/TaxTrackedPortfolio fee 주입 +
  `_fees_cache`/`get_total_fees`(실측·백필 윈도우 중앙값). `dividend_multi`는 MultiAccountSimulationLoop
  per-account fee + stock_tickers, result.total_fees 캡처. `dividend_logic` 단일·멀티 total_fees surface.
- **UI:** retirement.html·dividend_target.html에 거래수수료 섹션(opt-in+프리셋 키움/삼성/토스/직접+율%) +
  toggleFeePanel(멀티 재렌더)·applyFeePreset·renderFeeSummary·payload fee_enabled/fee_rate +
  계좌 payload 빌더(buildRet/buildWd/buildDt) per-card fee_rate. 공용 `_mmFeeField`가 feeEnabledChk로 카드 노출.
- **검증:** `tests/test_d4_fee_retire_div.py` **3 PASS**(배당 단일·멀티 fee 흐름·≤ 불변식, 결정론) +
  변경 모듈 기존 타겟 **74 PASS**(fee=0 회귀 무변경) + Python·템플릿 JS 문법 OK.
- **배포(cfee467)·라이브 probe 3 PASS:** 배당 단일 fee 배너 ₩87,410 · 은퇴 단일 fee 배너 ₩78,338 ·
  콘솔에러 0(두 엔진 fee 라이브 흐름 확인, 스샷 육안 확인). 공유 엔진 변경이라 전체 회귀(pytest tests/)는 오너 확인 후.

## [2026-06-13] fix | D4 계좌별 수수료 — 직접입력 시 프리셋 라벨 동기화

per-card 육안 검증 중 발견: 율을 직접 타이핑하면 프리셋 select가 last 값에 멈춰 라벨 불일치
(계좌2 율=0.5인데 드롭다운은 "키움 0.015%" 표시). `updateAccountFeeRate`가 프리셋 select
(id `accountFeePreset{i}`)도 동기화 — 매칭 율이면 그 증권사, 아니면 "직접입력". 재렌더 없이 DOM 한 줄
(커서 유지 정책 유지). 캐시 `?v=20260613feecard2`. `test_fee_card_dom.js` +2 = **16 PASS**.
**배포(8d621e4)·라이브 집중 스샷 육안 확인**(계좌2 = 직접입력/0.5 정상 표시·콘솔에러 0).

## [2026-06-13] feature | D4 fast-follow ① 계좌별 거래수수료 UI

탭레벨 v1(전 계좌 공통율)을 **계좌 카드별 수수료율 입력**으로 확장 — 증권사가 계좌마다 다른 점 반영.
백엔드는 D4 v1에서 이미 계좌별 `fee_rate` 수신·집행(`multi_account_loop` L634 → `Portfolio.buy/sell`,
`normalize_multi_accounts` 계좌별 값 우선·미지정 시 탭레벨 폴백). 이번엔 **UI만** 추가.

- **공용 `static/js/multi_account_ui.js`:** `_mmFeeField(acc, i)` 추가 — 증권사 프리셋(키움/삼성/토스/직접)
  + 율% 입력. **`feeEnabledChk` 켜진 경우에만 렌더** → 그 체크박스 없는 은퇴·배당 탭은 자동 미표시(미배선 보호).
  상태 `acc.fee_rate_pct`(%), 미지정이면 탭레벨 `feeRateInput` 시드. `updateAccountFeePreset`(상태+입력칸 동기화),
  `updateAccountFeeRate`(재렌더 없이 상태만 — 커서 유지 정책). 카드0·카드 i>0 둘 다 삽입.
- **계산기·백테:** `toggleFeePanel`에 멀티계좌 재렌더 추가(필드 노출/숨김). payload 빌더 2곳
  (`buildCalculatorAccountsPayload`·백테 inline)이 계좌마다 `fee_rate`(decimal, `_mmAccountFeePct/100`) 부착(opt-in 시).
- **캐시버전:** `?v=20260613feecard`(multi_account_ui 4탭 + calculator.js).
- **검증:** 신규 `tests/test_fee_card_dom.js` jsdom **14 PASS**(fee OFF→필드 미표시·ON→프리셋+율 렌더·탭 시드 기본·
  탭값=프리셋 selected·계좌별 상태 갱신·음수 클램프·타계좌 무영향·프리셋 DOM 동기화·custom 무변경) +
  `test_d4_fee_logic` **4 PASS**(신규 2 = normalize 계좌별 우선·disabled→0) + JS 문법 OK.
- **배포(61e0993)·라이브 probe 6 PASS:** per-card(`probe_fee_percard_live.js` 3 — 2계좌 카드별 입력
  렌더·차등율 실행 총수수료 ₩194,705·콘솔에러 0) + 탭레벨 회귀(`probe_fee_live.js` 3 — 계산기 ₩23,514·
  백테 ₩2,002 무변경). 잔여 fast-follow ② 은퇴·배당 탭 롤아웃(백엔드 미배선).

## [2026-06-13] feature | D4 거래수수료 — 계산기·백테 (탭레벨 v1)

오너 결정: 롤아웃 계산기+백테 먼저 · 수수료율 1개 통합(매수=매도) · 슬리피지 미구현 ·
프리셋+직접입력 · 국내주식 매도 거래세 0.18% 자동가산 · 결과 총수수료만 · 기본 OFF(opt-in).
UI는 **탭레벨 v1**(전 계좌 공통율, 계좌별 차등은 fast-follow).

- **엔진(`modules/core/portfolio.py`):** `Portfolio.buy/sell` 최저 집행층에 수수료 주입 —
  매수 `cost×율`, 매도 `proceeds×(율+거래세)`, 개별주식(`stock_tickers`=국내 is_etf=0)만
  거래세 0.18%(`STOCK_SELL_TAX`). `total_fees` 누적. 기본 0 → 전 경로 동작 무변경.
- **배선:** taxable_runner(단일·config 폴백)·multi_account_loop(계좌별 fee_rate)·portfolio_engine·
  SimulationConfig·AccumulationAnalyzer·MultiAccountAnalyzer 전부 fee 패스스루 + total_fees(중앙값) surface.
  fee_engine 신규 `build_stock_tickers`(국내주식 거래세 대상 조회).
- **logic:** calculator/backtest_logic이 body `fee_enabled`+`fee_rate`(decimal) → 엔진, 결과에 `total_fees`.
  normalize_multi_accounts가 계좌별 값 없으면 body 탭레벨 율 공통 적용.
- **UI:** 계산기·백테 입력에 "거래수수료" 섹션(opt-in 체크 + 증권사 프리셋 키움/삼성/토스/직접 + 율%) +
  결과 하단 "총 지불 거래수수료 ₩X"(`renderFeeSummary`). calculator.js v20260613fee.
- **검증:** `test_portfolio_fee` 6 + `test_d4_fee_logic` 2 PASS(매수/매도/거래세/취득가무관/게이팅 +
  백테 관통 total_fees>0·종료값 하락) + 멀티 회귀 50 PASS(fee=0 무변경). **배포·라이브 probe 3 PASS**
  (`probe_fee_live.js`: 계산기 ₩23,514·백테 ₩2,002 배너·콘솔에러 0). 4탭 중 계산기·백테 라이브.
- **잔여(fast-follow):** 계좌 카드별 수수료(증권사 다름) · 은퇴·배당 탭 롤아웃.

## [2026-06-13] feature | 납입 한도 초과 = 차단 → soft 경고(진행 선택) 전 탭 통일

오너 결정: 연금/IRP/ISA 연납입 한도 초과 설정 시 에러로 막던 것을 **안내 + 진행 여부(예/아니오) +
"오늘 하루 다시 묻지 않기" + 결과 하단 경고 배너**로 교체. 4탭(계산기·백테·은퇴·배당) 공유.

- **백엔드 수집기(`modules/multi_account_common.py` 신규):** `collect_limit_violations(accounts, routing_enabled)` —
  ISA 계좌당 2,000만 / 연금저축+IRP 합산 1,800만(초기자본은 라우팅 무관, 월납은 라우팅 OFF일 때만)
  위반 전수 수집. `enforce_contribution_limits(body, accounts, routing_enabled)` — `allow_limit_override`
  없으면 `limit_confirm` 에러(violations 동봉) raise, 있으면 경고 리스트 반환.
- **백엔드 배선:** calculator/retirement/backtest/dividend_logic 단일+멀티 경로 전부 옛 하드체크
  (`validate_isa_contribution`·`_validate_initial_capital_limits`·연금 단일 raise) → `enforce_contribution_limits`
  교체, 결과에 `limit_warnings` 동봉. transfers/distribution_policy ON이면 `routing_enabled=True`(월납 cascade 합법).
- **프런트 모듈(`static/js/limit_guard.js` 신규):** `window.MMLimit` — `confirm()`(예/아니오 모달 + 오늘하루
  스킵 체크박스 localStorage), `skipToday()`, `parseError()`(task FAILURE 문자열서 limit_confirm 파싱),
  `attach()`(결과 컨테이너 하단 빨간 경고 배너). 4탭 템플릿 script 포함(`?v=20260613lim`).
- **프런트 배선:** 4탭 `run*()`에 `_limitOverride` 인자 + skipToday면 `allow_limit_override` 동봉.
  catch/FAILURE에서 `limit_confirm` → `MMLimit.confirm` → 예면 override 재요청, 결과에 배너 attach.
- **정리:** 죽은 옛 에러 핸들러 제거(calculator.js `isa_contribution_limit` 등 분기·retirement.html),
  고아 import 제거(calculator_logic/retirement_logic), 옛 테스트 import 재지정(multi_account_common 직접).
  `validate_initial_capital_limits` 함수·테스트는 보존(pre-existing).
- **검증:** `tests/test_limit_soft_warning.py` **3 PASS**(수집기 룰 + override 왕복 + dividend 통합)
  + 옛 `test_l2_initial_capital_limit_validation` PASS. import 정상성·JS 문법 OK.
- **배포·라이브검증:** push(25d4009)→Hetzner 자동배포→4탭 전부 `limit_guard.js?v=20260613lim` 라이브 서빙.
  `tests/e2e_multitax/probe_limit_soft_live.js`(계산기 풀 동작) **6 PASS**: 모달 위반문구(ISA 2,000만)·
  예→override→하단 배너·아니오 닫힘·"오늘 하루 묻지 않기" 스킵 기록·스킵 당일 모달 생략·콘솔에러 0. 스크린샷 3종.
  `probe_limit_soft_live3.js`(백테·은퇴·배당 3탭) **4 PASS**: 각 탭 모달 위반문구→예→override→하단 배너 + 콘솔에러 0.
  → **4탭 전부 라이브 검증 완료.**

## [2026-06-13] feature | 배당계산기 멀티계좌 (G5-E) — 멀티계좌 전 탭 완성

오너 결정: ① **자동 역산 지원** — 역산 변수(시드/월납) = 계좌 1(상단) 값, 나머지 고정.
② **G2 풀 라우팅** — ISA 한도 cascade·풍차·연금 G3/G4 = `MultiAccountSimulationLoop` 그대로.

- **엔진(`modules/dividend_multi.py` 신규):** `MultiDividendSimulator(DividendSimulator)` —
  역산/곡선/시나리오 레이어 부모 상속, `_simulate_one`만 멀티 루프(월별 주입 — divrefactoring 수법,
  멀티 루프도 dates 주도라 무수정)로 교체. 무청산(`apply_final_liquidation=False`) + 가구 합산
  `dividend_income` 마지막 1년. 합성 폴백 = 계좌별 단일 합성의 합(G2 라우팅 미모델 근사, 라벨).
  절세 = `_finalize_account` 필드 surface → 계좌별 p50 + 합산(G5 규약).
- **배선(`dividend_logic.py`):** `accounts ≥ 2` → `_run_multi_dividend_logic`(backtest_logic 패턴 미러 —
  normalize·initial_capital 한도·계좌별 규제검증·DistributionPolicy). 응답 `multi_account` + `savings`.
- **UI(`dividend_target.html`):** 공용 `multi_account_ui.js` 이식(계좌 카드 + 즐겨찾기 select 자동 포함).
  구 dtAccount 라디오 제거 → 카드의 유형 select로 통일. MMTAX 결합 = dtTickers·dtSeedVal/dtMonthlyVal.
  멀티+자동 모드 안내 노트("역산 = 계좌 1"). 절세 패널 계좌별 분해 줄.
- **검증:** 손계산 결정론 `tests/test_div_multi.py` **7 PASS** — ① 멀티1==단일 ±1원(정합 앵커)
  ② 2계좌 == 단독 합 ③ 역산 변수 = 계좌1만(시드 0 → 계좌2 배당만 정확 일치) ④ 종합과세 개인합산
  (합동 < 단독합) ⑤ **G2 ISA 한도 cascade**(연 2,400만 납입 → 초과분 위탁 굴러 한도컷 단독보다 큼)
  ⑥ 절세 계좌별+합산·위탁 불변식 ⑦ logic 멀티 분기+역산 응답. 실브라우저 **13 PASS**(카드/노트/payload
  빌더/실DB sync API 멀티+절세 86윈도우/패널 분해/JS 에러 0) + 스크린샷 육안(ISA 절세 35만·위탁 0).

**▶ 멀티계좌 = 5탭 전부(계산기·백테·은퇴적립·은퇴인출·배당) 완성.**

_작성: Claude (Sonnet 4.6)_

## [2026-06-13] bugfix | BUG-DIV-YEARS — 배당계산기 기간 자동 크래시 (오너 라이브 발견)

오너 실사용 발견: 저장 포폴(SCHD/QQQM/GLD)·목표 100만·확률 50%·시드 1억·기간 자동 →
`오류: 'float' object cannot be interpreted as an integer`.

- **원인:** `_find_anchor_years`가 `float(yy)` 반환 → **서버는 QQQM 백필 없음** → 합성 보충 폴백 →
  `_simulate_synthetic`의 `range(years*12)`가 float 거부. 로컬은 QQQM 백필 23,305행 있어 합성 경로
  안 타서 재현 불가(서버-로컬 데이터 괴리의 전형). 기존 잠복 버그 — 오늘 엔진 통합과 무관(구 코드도 동일 경로).
- **수정:** `_run_rolling` 입구 `years = max(1, int(round(float(years))))` — 하류 전체(실측/합성/캐시)
  일괄 + 캐시 키 분열(`22.0` vs `22` 별도 키로 이중 계산) 부수 해결.
- **검증:** 신규 `test_float_years_with_synthetic_fallback`(짧은 데이터로 합성 폴백 강제 + float/int
  결과 동일) + 기존 10 PASS. 라이브 = 오너 시나리오 동일 호출 재검(배포 후).
- 곁가지 기록: 기간 자동(optimize) 중 진행률 % 미표시(모래시계만) — progress_callback이 anchor 탐색
  단계에서 미발행. 기능 무관 UX, 후속 후보.

_작성: Claude (Sonnet 4.6)_

## [2026-06-13] feature | P4 배당계산기 절세액 3종 — 마감 (절세액 전 탭 완성)

엔진 통합(divrefactoring) 직후 본체. 설계 = wd(인출기)와 동일 무청산 규약: 결과가 배당 흐름이라
end_value 미사용 → 잔여 미실현차익 가정/실제 양쪽 미가산 → 위탁 불변식(절세 0) 유지.

- **엔진(`dividend_simulator.py`):** `_GrossRecordingDividendEngine`(TaxedDividendEngine base 자리에
  끼워 gross 배당 가로챔) → `_simulate_one`이 윈도우별 절세 3종 산출(가정 = `estimate_brokerage_tax`
  (분류별 gross 배당 + executor `_brk_*`), 실제 = (Σgross−Σnet) + `total_cg_tax_paid`).
  `_run_rolling`이 `_savings_cache`에 병행 누적(실측 윈도우만 — 합성 보충 미포함, 3단 폴백 정합).
  공개 API = `get_savings_summary(seed, monthly, years)` → p50 3종 + n_windows(같은 캐시 키라
  시나리오 실행 후엔 공짜).
- **배선(`dividend_logic.py`):** 응답에 `savings`(대표 콤보 — 역산이면 solved 값) + `savings_account_type`.
  부가정보 규약: 절세 산출 실패가 본 결과를 막지 않음(try/except → None).
- **stale 통일 발견:** sync `/api/dividend-target/scenario` 라우트가 app.py 인라인 복제(세금 미배선!)
  → `run_dividend_scenario_logic` 위임으로 통일(celery 경로와 단일소스). + 디버깅 중 리스크리턴 세션의
  잔존 로컬 서버가 포트 점유 중이었던 것도 발견·정리.
- **UI(`dividend_target.html`):** `renderDtSavings` — 공용 절세 패널과 동일 포맷(초록 3칸) + 배당탭
  전용 각주(전 기간 누적·실측 N윈도우 중앙값·무청산·금종세 가산 미반영).
- **검증:** `tests/test_div_savings.py` **4 PASS** 손계산 — ① 위탁 불변식(가정==실제, 절세 0)
  ② ISA 절세 = Σgross×15.4% 독립재현(과세이연 → 실제 0) ③ p50 요약·합성 제외·무세금 None·캐시 정합
  ④ dividend_logic 응답 배선(+세금 OFF 시 키 없음). 실브라우저 7 PASS(패널 렌더·숨김·실서버 API:
  ISA 절세 321만/실제 0·위탁 절세 0/209윈도우·JS 에러 0). 타겟 회귀 15 PASS.

**▶ 절세액 표시 = 전 탭 완성(P1~P4). 다음 후보 = 배당탭 멀티계좌(G2 확장) OR PHASE4(D4·A4·D1·D2·C1·C2).**

_작성: Claude (Sonnet 4.6)_

## [2026-06-13] feature | 배당계산기 엔진 통합 (divrefactoring) — 게이트 PASS, P4 선행 완료

오너 결정 = 게이트 방식(3-1/3-2 → 벤치마크 게이트 → 통과 시에만 교체. 미달 시 즉시 중단·보고).

- **핵심 발견: 월별 모드 = 루프 무변경.** SimulationLoop이 dates 주도라 월말 리샘플 데이터 주입으로 끝 —
  신규 `modules/simulation/monthly_mode.py`(`to_monthly_price_data` + `last_year_dividend`). plan의
  "SimulationLoop 월별 모드 추가" 공정이 데이터 헬퍼로 축소, 기존 일별 경로 무위험.
- **게이트 (실데이터 458730 15y×40윈도우):** 속도 세금ON 동조건 **x2.14**(기준 5배), 드리프트 중앙
  **1%**·최대 **3.3%**(기준 5%) — **PASS.** 방향 = 신이 낮음(정확): 월내 배당→적립(ex-date 정합) +
  리밸 양도세 실부과(구는 무세금 수량조정).
- **교체:** `DividendSimulator._simulate_one` 내부만 메인 엔진 조립으로(자체 루프 ~120줄 제거). 상위
  역산·캐시·합성(선택지 A 유지) 무변경 → plan 3-3 별도 Runner 불필요. 세금 ON = 윈도우별 TaxSessionState
  공유 세션(종합과세 포함) — G2/절세 토대.
- **보너스 핫스팟 픽스:** `TaxEngine._classify_kr_etf` 호출마다 sqlite connect → 인스턴스 캐시.
  전 탭 세금 시뮬 ~10배 가속(벤치 세금ON 구엔진 1.53→0.15s, 신 1.73→0.32s).
- **검증:** test_monthly_mode 6(닫힌형 진리값 앵커 ±5원 포함) + 세금 영향권 35 + zero-weight PASS.
  시나리오 풀플로우: 확률 3.2s(189윈도우)·역산 solved_seed 1.91억/34s(구엔진 추정 30s급과 동급)·탐색 곡선.
  벤치 재실행 = `tests/bench_div_monthly.py`.

**▶ 다음 = P4 본체: 배당탭 절세액 3종 표시(이제 기존 패턴 복제). 그 뒤 후보 = 배당탭 멀티계좌(G2).**

_작성: Claude (Sonnet 4.6)_

## [2026-06-13] docs | 전체 동기화 — 플랜 파일 전수 점검 + 진행상황 통일 (오너 지시)

오너 "모든 플랜 파일 읽고 진행상황 동기화" → README 동기화 절차 전체 수행. 루트 plan 25개 + wiki 전부 정독,
코드 실상 대조(자동산출/_ytd_income/sim/tax_engine.py 삭제는 grep·파일 존재로 확인).

**종결 처리한 plan:** `trackG_multiaccount_plan.md`(L7 16/16 + GAP-DECUM-COMP 해소 — 미결 0) ·
`isafix.md`(BUG-1~5 + 세금 재검증까지) · `다계좌세금_E2E검증_plan.md`(기완료 표기 확인) ·
`리스크리턴도표_plan.md`(기완료). PHASE1/PHASE3 = 운영중 표기(과거 기록용).

**완료 정정(코드 확인 기반):** 세금리팩토링 plan frontmatter `phase1-tax-profile-api`·`phase2e`·`phase2f`
→ done(전부 2f 4100ecd로 충족 — 자동산출=`recurring_financial_income` 3탭, `_ytd_income`=account_tax:243,
전탭배선). 본문 표·갭 목록에 2026-06-13 정정 노트. bugs.md 기술부채 2건(_ytd_income·sim/tax_engine.py) ✅.
phases.md 2c/2e/2f/phase1-api/Stage B/PHASE4 줄 전부 최신화. dev-status.md 한줄요약·세금표·종합과세
실제상태(❌ 3건→✅)·다음트랙·사업일정(로그인+즐겨찾기 = 2개월 선행) 갱신. features.md 금종세 행 완료.
ideas.md 자동산출 미구현 주석·세금계산기·리스크리턴 정정.

**roadmap:** Last updated 06-13 + Source Plans 표 6행 갱신(PHASE4/isafix/trackG/절세액/리스크리턴/E2E +
합성상관·divrefactoring 행 신규) + Current blocker + Dependency Order(현재 위치 = PHASE4 잔여 + P4) +
Track E 표(B1·D6·E1 완료 반영) 재구성. PHASE4_PLAN 헤더 갱신. SYNTHETIC plan에 은퇴 체크박스·Stage B 추가 노트.
index.md plan 표 최신화.

**동기화 후 잔여 전모(미결 전부):** P4 배당 절세(선행 divrefactoring) / PHASE4 D4·B2-a·A4·D1·D2·C1·C2·B4·
C4·E2~E4 / 합성상관 서버검증 / 벤치마크 영속화 / KQ150 티커·갭채움 스케줄러 / ideas.md 인코딩 복구 /
ETF_BACKFILL V2 Ph.3+. 블로커 0.

_작성: Claude (Sonnet 4.6)_

## [2026-06-12] feature | 리스크-리턴 도표 (/risk-return) — P3, 즐겨찾기 후속

오너 결정 4건: 지표 = **CAGR(y) + 일간 std×√252(x), 총수익(배당 재투자)** / 기간 = **전 점 공통
겹침 구간**(3년 미만 ⚠) / 벤치마크 = **고정 5종(SPY·QQQ·GLD·069500·TLT) + 사용자 추가** / **독립 페이지**.

- **`risk_return_logic.py` 신규**: 시뮬 없이 고정비중 일별 근사(r_p = Σ w·r). 비중합<100% → 잔여 현금(수익 0),
  >100% → 합 정규화. 합집합 달력+ffill(휴장일 보합 — 전 점 동일 적용이라 상대 비교 보존). 상수수익률
  std 부동소수 잔차 가드(sharpe 폭주 방지). 데이터 없는 종목 → skipped + 의존 포폴 제외(부분 데이터 왜곡 방지).
- **API** `POST /api/risk-return`(로그인 전용): 저장 포폴 전체 + 기본 벤치마크 + body.benchmarks(최대 10).
- **UI** `/risk-return`(nav·사이드바 🎯, 내 포트폴리오 위): Chart.js scatter — 내 포폴 = 색점, 벤치마크 = 회색
  마름모. 호버 = 이름·CAGR·변동성·샤프. 기간 캡션 + 3년 미만 ⚠. 벤치마크 추가 = 검색→칩(페이지 세션 한정,
  영속화는 후속 — user_settings tax json에 끼우면 세금설정 저장 시 유실 위험이라 보류).
- **검증:** ① 손계산 결정론 `tests/test_risk_return.py` **7 PASS**(FakeLoader, DB 무접근 — 상수성장 CAGR 정확값
  ·50/50 혼합==현금드래그 등가·비중합>100 정규화·배당 총수익 재현 등치·공통기간/경고·skipped 제외·교대수익률
  vol/sharpe 손계산) ② 실브라우저 E2E `tests/test_risk_return_browser.js` **8 PASS**(mint_session, 실DB 산출 —
  게이팅·내 포폴 점·지표 유한값·벤치마크·기간 캡션·추가 칩·JS 에러 0) ③ 라이트/다크 스크린샷 육안 정상.
  실DB sanity: 26.4년 공통구간(백필 시계열 포함 — 의도된 설계), SPY 20.8%/9.3%·TLT 16.7%/3.2% 등 plausible.
  전체 pytest 미실행(테스트 실행 규칙 — 신규 모듈이라 타겟으로 충분).

_작성: Claude (Sonnet 4.6)_

## [2026-06-12] feature | 멀티계좌 카드 종목입력에 즐겨찾기 불러오기

오너 요청: 세금 적용 ON + 계좌 추가 시 나오는 계좌별 종목 입력 창에서도 저장 포트폴리오 선택.

- `multi_account_ui.js`(공용 모듈 — 계산기·백테·은퇴 3탭 + wd 모드 자동 적용): 계좌 2+ 카드의
  종목 검색 위에 `★ 즐겨찾기 불러오기` select. 선택 → `acc.tickers` 교체(weight % 반올림) → 재렌더.
- 목록 로드 = 멀티계좌 첫 렌더 시 1회(`/api/me` 선확인 — 비로그인 401 노이즈 방지, MMFav 패턴) +
  **select 포커스 시 재조회**(같은 페이지에서 방금 저장한 즐겨찾기 즉시 반영). 이름 옵션 `_mmEsc()` XSS 가드.
- 캐시 v20260612fav2 (calculator/backtest/retirement).
- **검증:** `test_myportfolios_browser.js`에 5b 추가 → **18 PASS**(기존 15 + 계좌 카드 select 표시·
  불러오기 60/40 상태 반영·종목 행 렌더). 실서버+실DB 로그인 E2E. 스크린샷 육안 정상.
  공용 모듈이라 계산기 검증 = 3탭 커버(동일 코드 경로).

_작성: Claude (Sonnet 4.6)_

## [2026-06-12] feature | 내 포트폴리오 관리 페이지 + 자산구성 파이차트

오너 요청 2건: ① "내 포트폴리오" 탭(사이드바 내 자산 위) — 즐겨찾기 생성·수정·삭제 관리 화면
② 내 자산 "자산 구성" 그래프를 가로바 → 파이차트로.

- **`/myportfolios` 신규** (`templates/myportfolios.html` + app.py 라우트 + base.html nav/사이드바 ⭐):
  서버 렌더 로그인 게이팅(myassets 패턴). 카드 목록(이름·수정일·종목 badge/code/비중바·합계),
  생성/수정 모달(종목 검색 + 비중 입력 + 균등분배, 동명 confirm 덮어쓰기), 삭제 confirm.
  기존 `/api/portfolio/*` 그대로 재사용(백엔드 무변경, 라우트 1개만 추가). 사용자 문자열 esc() 처리.
- **자산 구성 파이차트** (`myassets.html` renderWeightChart): type bar→pie, 고정높이 260px 래퍼 +
  maintainAspectRatio:false(모바일 차트 왜소 패턴 회피), legend right(모바일 bottom), 툴팁 `라벨: N%`.
  그룹별 합산·색상 로직 무변경.
- **검증:** 신규 `tests/test_myportfolios_browser.js` **15 PASS** — 실서버+실DB 로그인 E2E
  (신규 `tests/mint_session.py`로 dev 세션 쿠키 서명 — OAuth 우회, 로컬 전용):
  비로그인 게이팅 / 생성(균등 50/50)→카드 렌더 / 수정(이름+60/40) / **계산기 ★ 위젯 연동**
  (저장한 포폴이 드롭다운에 뜨고 불러오면 60/40 반영) / 삭제 / 파이차트 type·데이터 60/40 / JS 에러 0.
  + 기존 fav 스위트 재실행: 브라우저 31·jsdom 20·API 5 전부 PASS. 데스크탑/모바일/모달 스크린샷 육안 정상.
  (전체 pytest 회귀는 오너 지시로 미실행 — 백엔드 변경이 라우트 1개라 타겟 테스트로 충분.)

_작성: Claude (Sonnet 4.6)_

## [2026-06-12] feature | B1 포트폴리오 즐겨찾기 — 5탭 공용 위젯 (PHASE4)

오너 결정 4건: 저장 단위 = 종목+비중 1세트 / 로그인 전용(서버 저장) / 5탭 전부 / 한도 20개(요금제
차등 대비 하드코딩 금지 → `get_portfolio_limit()` 단일 변경점).

- **DB/CRUD** (`auth_manager.py`): `saved_portfolios`(user_id, name, tickers_json) + get/upsert/delete.
  신규 생성만 한도 체크(수정은 통과). `MAX_SAVED_PORTFOLIOS=20` + `get_portfolio_limit(user_id)`.
- **API** (`app.py`): GET `/api/portfolio/list` · POST `/api/portfolio/save` · DELETE `/api/portfolio/<id>`.
  myassets와 동일 401 패턴. 검증 = 이름 1~50자·종목 1~30개·code 필수·weight 숫자.
- **위젯** (`static/js/portfolio_favorites.js`, 신규): `MMFav.init({mount, getTickers, setTickers})`.
  규약 = [{code,name,badge,weight(%)}]. select(불러오기)+저장+삭제. 동명 저장 → confirm 후 기존 id
  덮어쓰기. 비로그인 = select 비활성+안내(`/api/me` 선확인 — list 401 콘솔 노이즈 방지).
  사용자 입력 이름은 전부 textContent(DOM API)로 — innerHTML 미사용(XSS 가드). CSS `.fav-*`(다크 변수).
- **5탭 배선**: 투자계산기(% 그대로)·백테스트/은퇴(내부 0~1 ↔ 위젯 % 변환)·배당(%)·ISA전환(IIFE 내부).
  각 탭 `#favBar` 마운트 + 어댑터. 캐시 v20260612fav.

**검증 4층:**
① API `tests/test_saved_portfolios.py` **5 PASS** — 401 3종 / 한글·badge·weight 왕복 / 검증 400 7케이스 /
   한도(신규만 차단·수정 허용, limit 패치로 단일 변경점 증명) / 소유권 격리(타인 id 삭제 무효).
   users.db는 임시 경로 패치(dev DB 무오염).
② 위젯 jsdom `tests/test_fav_dom.js` **20 PASS** — 비로그인 list 미호출·XSS 무해·깊은복사·
   저장 payload(trim/신규 id null/동명 덮어쓰기 id)·삭제 플로우·빈 구성 차단.
③ 실브라우저 Playwright `tests/test_fav_browser.js` 로컬 **31 PASS** — 5탭 위젯 렌더·비로그인 동작·
   JS 에러 0 + **어댑터 왕복**(route mock 로그인 위장: 불러오기 → 페이지 상태[60/40, bt·ret는 0.6/0.4] →
   저장 payload % 규약 재변환) + API 401.
④ 전체 회귀 **255 PASS**(250+5) + 스크린샷 육안(라이트/다크/모바일 정상).

⚠️ 로그인 실계정 저장 플로우는 OAuth 자동화 불가 — 라이브에서 오너 육안 1회 권장.
**▶ 다음 = 리스크리턴도표(선행조건 해소됨) OR P4 배당금계산기 절세.**

_작성: Claude (Sonnet 4.6)_

## [2026-06-12] verify | GAP-DECUM-COMP 해소 확인 — 감사 항목 stale, decum 종합과세 기배선 증명

오너 보류 해제("gap하자") → 코드 점검 결과 **구현할 게 없었음**. 감사(2026-06-09, 421ac71) 주장
"인출 중 위탁 배당 2천만 초과해도 종합과세 가산 안 함"은 코드 실상과 불일치 — C3.2(89c927a)부터
`simulate_household_window`가 `TaxSessionState`를 전 계좌 공유:
- 위탁 배당 gross → `TaxedDividendEngine.process`가 풀 누적 + `after_tax_dividend`(ytd) 초과분 가산
- KR_FOREIGN 인출/리밸 매도차익 → `TaxedOrderExecutor._calc_cg_tax`가 같은 풀 합산 + 가산
- 연도별 리셋(`session.touch`)·계좌간 개인 합산 전부 동작.

**검증 = 신규 `tests/test_decum_comprehensive.py` 4 PASS** (배선 검증 — 순수함수 정확값은 test_phase2f):
① 연 배당 3천만+근로 1억, 2개년: 종료값 == `after_tax_dividend` 순차 재현 합 ±1원 + 가산 실발생
② 임계 미만(연 120만): 플랫 15.4% 등치(스퓨리어스 가산 없음)
③ 위탁 2계좌 각 1,440만(합산 2,880만): 가구 합동 종료값 < 단독 합(개인 합산 풀 증명)
④ KRF 인출매도 차익: 타계좌 배당이 임계 채우면 동일 매도의 actual_tax 증가(풀 합산 증명).
전체 회귀 **250 PASS**(246+4).

잔여 = `other_financial_income=0` 베이스라인(외부 금융소득). 프런트가 필드 자체를 안 보냄(수동입력
금지 설계) → decum 고유 갭 아니라 기존 "other_financial_income 전탭 자동산출" 항목에 귀속.
bugs.md·roadmap·README 동기화. **로드맵/감사 stale 4번째 사례** — 착수 전 코드 실상 grep 관례 유효.

_작성: Claude (Sonnet 4.6)_

## [2026-06-12] feature | 절세액 P3 마감 — 인출기(wd) 절세 3종 패널

오너 지시 "P2/P3 구현됐는지부터 확인" → 점검 결과 P2(백테스트)·P3 적립기/연금수령세(1,500만 전액 16.5%,
06-03 결정)는 G5 복제로 기완료. 유일 갭 = 인출기(wd) 절세 패널 → 오너 결정 "구현".

- `order_executor.py`: 인출 매도(`sell_with_tax` 직접호출)도 위탁가정 `_brk_krf_gain`/`_brk_us_by_year` 누적.
  execute_orders 경로는 기존 `_accrue_brokerage_gain`과 이중집계 방지(`_suspend_brk_accrual` 플래그,
  내부를 `_execute_orders_inner`로 분리해 try/finally 보장). GH(`portfolio.sell` 직행)는 영향 없음.
- `multi_account_withdrawal.py`: 윈도우 루프에 gross 배당 분류별 + 실제 배당세(gross−net) + 계좌별
  연금소득세 누적 → 윈도우 종료 시 per_account 절세 3종. **잔여 미실현 미가산** — wd end_value는
  무청산(gross)이라 실제세금에도 청산세 없음 → 양쪽 다 제외해야 위탁 불변식(절세 0) 유지(설계 핵심).
  `analyze_household_withdrawal`: 계좌별 p50 + 합산(계좌별 p50 단순합, 적립 규약 동일) → `savings` 반환.
- `retirement_logic.py` wd 응답에 `savings`(build_savings_summary). `retirement.html` wd 모드도
  공용 절세 패널 렌더. `multi_account_ui.js` 각주 모드 분기(wd = "실제 세금에 연금소득세 포함").
- 검증: 신규 `tests/test_l_save_wd.py` 6 PASS 손계산 ±1원 — ① 위탁 차익 인출: 가정==실제(신규 누적이
  실제 과세와 정확 일치 증명) → 절세 0 ② 차익0 전부 0 ③ 연금 단독: 월 연금세 1,000,000×0.055/0.945 =
  58,201.06원 × 12회 정확, 절세 0 하한 ④ ISA 배당: 절세 = 500,000×15.4% = 77,000원 ⑤ 혼합 드레인 순서
  ⑥ 세금 OFF 필드 부재. 전체 회귀 246 PASS(L-SAVE 26 = 이중집계 없음 가드). 실데이터(위탁3억[미실현
  1억]+연금2억, 458730/069500, 10y): 위탁 절세 0 ✓ · 연금 절세 6,303,878원 · survival 1.0.
  jsdom 렌더 4체크 PASS. 라이브 probe = `probe_wd_savings_live.js`.

## [2026-06-12] feature | ISA 전환 계산기 신규 (/tax-switch) — P1 세금계산기 v1

오너 결정: ISA 연 2천만 한도 처리 = **(a) 분할 이전 모델**, UI = **독립 페이지**.
"지금 위탁 자산을 팔아(양도세) ISA로 옮길까 vs 위탁 유지?" — 두 전략 세후 정면 비교.

- 선행 정리: 로드맵 stale 수정 — "다음=금종세 완전구현(2e)"은 Phase 2f(4100ecd, 05-31)로 이미 완료였음.
- 엔진: `MultiAccountSimulationLoop` optional 확장(기본 OFF = 기존 G경로 무변경)
  - `carried_cost_basis`: 기보유 자산 취득가 주입 (day-0 매수 후 avg_cost 비례축소)
  - `switch_policy`: 연 1회 위탁 비례매도(sell_with_tax → 공유 세션 합산 = 종합과세 정확) → 순현금 ISA 이전.
    `ContributionLimitTracker` 연 2천만/총 1억. dest ISA 만기세 원금 = cycle_contribution(내부이전은 cash_flow 미기록).
  - `yearly_after_tax_snapshot`: 연말 가상청산 세후 combined → breakeven 산출 입력.
- `tax_switch_logic.py`: A(단일 위탁+취득가) vs B(위탁+ISA+switch)를 동일 롤링 윈도우로 페어 실행.
  출력 = A/B p25/50/75, 전환양도세, breakeven(역전 연차 중앙값 + 발생 비율), 연도별 세후 궤적, 대표 이전 스케줄.
- API: `/api/tax-switch/submit`(celery) + `/run`(sync 검증용). UI: `templates/tax_switch.html` + `static/js/tax_switch.js`
  (종목검색·비중·평가액/취득가/기간, Chart.js A vs B, 이전계획 표, 다크/모바일). nav·sidebar에 "ISA 전환" 추가.
- 검증: `tests/test_tax_switch.py` 8 PASS — 손계산 ±1원 (A 일괄 46,150,000 / B 분할 47,250,000 = 250만 공제
  3회로 정확히 +110만 / KR_FOREIGN flat A==B / 차익0 불변식 / 손실 전환세 0 / 총1억 한도 5년 중단 / 연말 스냅샷
  / 기본 OFF 무변경). 전체 회귀 240 PASS. 실데이터 로컬: 458730 5천만/3천만 5y → 686윈도우, B +405만,
  breakeven 1년차(98%, 로컬 stale DB 기준 — 서버는 4년차). 로컬 Playwright 스모크 + `test_responsive_dark.js` 186 PASS(신규 페이지 포함).

## [2026-06-11] fix | GAP-RET-KRDATA 해소 ①②③ + NaN race 가드 — E2E 16/16 PASS, P0 L7 완료

오너 결정("셋다 + race 가드까지") 구현. 커밋 9486eee, 배포·라이브 검증 완료.

**구멍 3개 (은퇴 sim만 "실데이터 최대 + 가상 피팅" 원칙 미배선이던 것):**
- **①** 은퇴 탭에 가상 데이터 체크박스 신설(계산기와 동일 문구·스타일) + sim body `use_synthetic` 배선. 단독 인출기는 기존대로 항상 합성 허용(변경 없음).
- **②** 인출 투영용 `prepare_scenario_data`를 적립 prep과 **별도로** 인출기간 기준 호출(단일 `run_retirement_logic`·멀티 `_run_multi_account_retirement_logic`). 적립 prep을 늘리지 않은 이유 = 적립 케이스 수가 범위에 비례 폭증(성능). `wd_data_start = min(적립 시작, 인출 prep 시작)`.
- **③** 실윈도우 0개면 하드에러 대신 **전량 GBM 합성 폴백** — 단일(`WithdrawalAnalyzer._run_rolling`)·멀티(`analyze_household_withdrawal`) 공통, 기존 MIN_CASES 패딩 메커니즘 재사용. 결과에 `n_windows_real/synthetic`(멀티 combined_summary)·`wd_n_real/synthetic`(단일) 노출 + 화면 `#retWdSynthNote` "실측 N + 가상 M" 경고 라벨(sim/wd 양쪽).

**race 가드 (BUG-WD-MULTI-LIVE 재발 방지):** `simulate_household_window` — 가격 유한성(`isfinite && >0`) 검사, 전 계좌 종목 가격이 유효해진 날부터 초기 매수(부분 데이터 가드), 종료가 유한 폴백. 합집합 달력 reindex+ffill의 리딩 NaN이 포트를 오염시키던 경로 차단.

**검증:** 신규 `tests/test_wd_synthetic_fallback.py` 3종(멀티/단일 0윈도우 폴백 + 리딩 NaN 가드) + 인출·은퇴 회귀 **104 PASS** + 로컬 브라우저 스모크 4 PASS(`tests/check_retirement_page.js` — 체크박스·body 배선·JS 에러 0). 라이브: C1 probe 해소(윈도우 0개 에러 → 생존율 100%·"실측 0+가상 30" 라벨) + **E2E C·D 재검 7/7 PASS**(`run_cd.js`, 4분) — D4 미실현차익 방향성도 라이브 작동(0=34,159만 vs 2억=33,694만 악화 ✓).

**→ E2E 16건 전부 PASS. 계획 §8 완료 기준 충족 = roadmap P0 "L7 실데이터 통합검증" 완료.** 잔여(소, 비차단): cleanup 스크립트 stale provenance 정리 · 로컬 DB 구체인 재빌드 · DB 합성 단일경로 다양화(기존 9.4 후순위) · `median_pension_tax` UI "/년" 라벨 정합 확인.

_작성: Claude (Fable 5)_

---

## [2026-06-11] investigate | DATA-458730-BACKFILL 서버 실측 — 데이터 버그 아님(설계 의도), 파생 이슈 4건 등록

오너 승인 받아 서버 SSH(읽기 전용 sqlite) 실측. 결론: **서버는 설계대로, 로컬이 낡은 쪽.**

**실측 사실:**
- 서버 458730 = 실측+DJUSDIV_PROXY 2003-11-07~2026(경계 연속, 합성 2003-09 ~2,600원→실측 2003-11 ~2,780원 — 단위점프 없음, anchor 수정 유효 확인) + 1981~2003 GBM 합성(`price_daily_synthetic` 분리 저장).
- 2003-11 경계 = `build_djdiv_proxy.py` **의도적 설계**: "^GSPC segment removed — 광역지수는 DJ 배당전략 대표 못함, no pre-DVY backfill"(Phase 6.0 Stage A). 체인 = SCHD(2011~)←SDY(2005~)←DVY(2003-11~). 끝.
- 05-30 12:01 `cleanup_synthetic_contamination.py` + 재백필 = 구체인(^GSPC 포함) 오염 제거 마이그레이션. 같은 날 아침 run들이 1928~를 썼던 건 구체인 잔재.
- **로컬 DB가 구버전 체인(1928~, 90년대 강세+환율로 연 15% 경로) 보유 — 로컬-서버 시뮬 괴리(위탁 p50 22억 vs 0)의 진짜 원인.** 라이브 비관 결과는 보수적 합성 설계의 정상 출력(가격 3.5%+배당 2.9% ≈ 총수익 6.5%/y).
- **race 물증**: backfill_runs 7a2cc0fa(synthetic_gbm_v1, 1981~2003, 5,846행) 완료시각 12:12:51 = E2E D2 실행 중. 생존율 0% 일시현상 = 생성-시뮬 경합 확정.

**파생 이슈 4건(bugs.md DATA-458730-BACKFILL 항목에 통합 기록):** ① RACE-LAZY-GEN 가드 필요 ② DB 합성 단일 고정 경로의 표본 편향(개선 선택) ③ cleanup 스크립트 price_daily_source 미정리(서버에 stale provenance 잔존) ④ 로컬 DB 재빌드 필요.

**남는 본선 문제 = GAP-RET-KRDATA 하나.** 이건 데이터가 아니라 구조(은퇴 sim이 인출 요구량을 데이터 준비에 전달 안 함 + synthetic 옵션 부재) — ①②③ 결정 대기 그대로.

_작성: Claude (Fable 5)_

---

## [2026-06-11] investigate | BUG-WD-MULTI-LIVE 조사 — 일시 현상으로 강등, 신규 DATA-458730-BACKFILL 등록

E2E에서 발견한 인출기 멀티 생존율 0% 조사 (오너 지시, 수정 없이 조사만).

**방법:** ① 로컬 재현(`tests/debug_wd_multi_live.py` — D2 body로 `run_withdrawal_logic` 직접) ② 라이브 API 직접 probe(`tests/e2e_multitax/probe_d2_live.js`·`probe_c1_live.js`) ③ 로컬 계측(`tests/debug_wd_d4_basis.py` — 취득가 스케일·자산분류·미실현차익 방향성).

**결론 4건:**
1. **생존율 0% = 일시 현상.** ~1h 후 동일 body 4회 연속 정상(생존율 100%·n_real 61·data_start 1981). 유력 메커니즘 = E2E가 (458730,360750,30y) 조합 최초 요청이라 lazy 백필+합성 생성 race/워커 캐시 stale 중에 시뮬. 초기 가설(DB 합성 USD anchor)은 기각(BUG-SYNTH-FX 때 양 경로 수정 확인).
2. **엔진 배선 정상.** 로컬 계측: 분류 KR_FOREIGN ✓, 취득가 스케일 작동(avg_cost 241.6→80.5) ✓, 미실현 2억 → combined p50 −2,420만 악화(방향 ✓).
3. **신규 발견 DATA-458730-BACKFILL:** 서버 458730 장기 백필 경로가 사실상 하락(라이브 단일 30y: 3억→중앙값 0.69억, OFF도 1.16억) vs 360750 연 ~9% 정상. 로컬 DB에선 위탁 p50 22억으로 건강 → 서버 백필 체인 품질 문제(환율/배당 미반영 프록시 의심). 라이브 D4 무효과(0 vs 2억 동일)도 이것의 파생(전부 손실 매도 → CG세 0).
4. **GAP-RET-KRDATA는 지속 재현 확인**(C1 probe 지금도 "롤링 윈도우 0개") — 진짜 갭, 해소 결정 대기 그대로.

**E2E 판정 갱신:** D2·D3·D4 invariant은 현재 라이브에서 전부 성립 → 잔여 FAIL은 C1·C2(+C3 SKIP)만, 원인 = GAP-RET-KRDATA 단일. **▶ 다음 = 오너 결정 2건: ① GAP-RET-KRDATA 방향(②+③ 조합 추천) ② DATA-458730-BACKFILL 서버 DB 실측 착수.**

_작성: Claude (Fable 5)_

---

## [2026-06-11] verify | 다계좌 세금 E2E 16건 실행 (P0 L7 실행판) — 11 PASS / 4 FAIL / 1 SKIP + 버그 2건 발견

`다계좌세금_E2E검증_plan.md` 16건을 Playwright로 라이브 서버에서 전부 실행. 신규 `tests/e2e_multitax/`(helpers + a/b/c/d 스위트 + run_all, 케이스별 진짜 클릭·API 캡처·불변식 판정). 세금 프로필은 비로그인 localStorage(서버 쓰기 없음). 소요 ~5분, 콘솔에러 0.

**PASS 11 (재검 1 포함):** 계산기 6/6 전부(A1 멀티+절세 375만·풍차만기 3회 / A2 ON 32,936만≤OFF 37,559만 / A3 ISA 2,100만 서버차단+배너 / A4 세액공제 환급 1,205만 / A5 금종세 자동판정 — 위탁 8억에 12개 연도+풍차 0회 / A6 OFF 패널 미표시), 백테 3/3(B1 멀티 스칼라+절세 / B2 재검 ON 4,012만≤OFF 4,824만 / B3 단일 회귀+분할매도 패널), 인출기 D1(모드 UI 배선)·D3(단일 ON 70%≤OFF 84%).

**테스트 설계 결함 1건(앱 정상):** B2/C2/D3 류 "ON/OFF 비교"는 OFF 런이 accounts 미부착이라 계좌2 자금이 빠짐 → 자금 실린 구성이면 불공정 비교. 단일계좌 대조로 대체(코드 수정 완료, 결과 md 명시).

**FAIL 4 → 발견 2건 (즉시 수정 금지 규칙 적용, bugs.md 등록):**
- **GAP-RET-KRDATA** (C1·C2): 은퇴 sim이 국내상장 ETF + 기본값(적립20y+인출30y)으로 "롤링 윈도우 0개" 하드에러. 은퇴 탭엔 synthetic 체크박스가 없어 `allow_synthetic` 항상 False + 데이터 범위가 적립 기준 → 인출 윈도우 부족. ISA·연금 멀티(국내상장 의무)와 구조 충돌. C3는 선행 실패로 SKIP.
- **BUG-WD-MULTI-LIVE** (D2·D4): 인출기 멀티(위탁3억+연금2억·월200만)가 라이브에서 생존율 0%·combined p50 0원(전 윈도우 사망, 미실현 0이어도 동일). 동일 조건 단일은 70% 정상. 유력 가설 = BUG-SYNTH-FX 미수정 DB 합성 경로(USD anchor) 잔재. L13 결정론은 mock이라 못 잡던 영역 — E2E가 의도대로 작동한 셈.

산출물: `tests/e2e_multitax/results/20260611_result.md` + 스크린샷 11장. **▶ 다음 = 오너 결정: GAP-RET-KRDATA 해소 방향(①은퇴 탭 synthetic 옵션 ②범위를 적립+인출년으로 ③가구인출 합성보충) + BUG-WD-MULTI-LIVE 원인 조사 착수 여부.** 둘 해소 후 C1~C3·D2·D4 재실행하면 L7 완료 처리 가능.

_작성: Claude (Fable 5)_

---

## [2026-06-11] fix | 모바일 후속 — 백테스트·내자산 잔여 깨짐 (오너 실기기 피드백)

오너 피드백: ① 내자산 칸이 넓어 좌우 스크롤 필요 ② 백테스트 우측 여백+애매한 가로 스크롤 ③ 결과 그래프 상하로 너무 짧음.

**원인 실측 (라이브 Playwright, 백테스트 SPY 실제 실행):**
- 가로 스크롤: scrollWidth 447 vs 뷰포트 390. `.bt-left` min-content 403px — `.date-row input[type=date]`가 flex item `min-width:auto` 기본값이라 내용 폭 이하로 축소 거부.
- 그래프 왜소: 차트 3종 전부 **300×130/100/80 고정** — canvas `height` 속성 + `maintainAspectRatio` 기본값(aspect 모드)이라 responsive 리사이즈 실패.

**수정:**
- backtest.html: date input `min-width:0`, `.bt-chart-wrap` 고정높이 래퍼(가치 280px/연간 220/낙폭 180, 모바일 240/190/160) + `maintainAspectRatio:false` 3곳, 모바일 `.bt-left/.bt-right max-width:100%`.
- style.css: 모바일 `.main-content > * { min-width:0; max-width:100% }` 일반 가드(同유형 재발 방지). 캐시 v20260611ui2.
- myassets.html: 보유종목 테이블(9열) → ≤768px **종목별 카드 스택**(renderHoldings td에 `data-label` 부여 + CSS grid 2열, 종목코드/수익률 상단·액션 하단), 리밸 밴드카드 wrap 허용, `.rebal-row` wrap, 탭 nowrap+가로스크롤.

**검증:** 로컬 myassets 샘플 주입 → overflow 0·카드형 렌더 스크린샷 확인. 배포 후 라이브 백테스트(SPY 실제 실행, 390px) 재측정 — **scrollWidth 447→390(오버플로 0), 차트 300×130/100/80 → 316×240/190/160.** 후속 발견 1건: 모바일 `.bt-card` 패딩 룰을 base 정의보다 앞에 넣어 cascade에서 밀려 미적용 → 스타일 블록 끝으로 이동(b368573). 커밋 71d7fe0·6ad717c·b368573.

_작성: Claude (Fable 5)_

---

## [2026-06-11] feature | 모바일 반응형 + 다크모드 + UX 개편 (전 페이지)

오너 요청: "모바일에서 다 깨짐 + 야간모드 없음 + UX/UI 불친절 — 부족한 부분 수정". 오너 결정 2건: 모바일 네비 = 햄버거 드로어, 다크모드 = 수동 토글 + 시스템 기본.

**① 반응형 (기존 미디어쿼리 0개 → 신설):**
- ≤1400px: 상단 nav 링크 9개 숨김(좌측 사이드바가 동일 메뉴 제공) → **BUG-NAV-1(1280px 글자 세로 깨짐) 해소**
- ≤1024px: 사이드바 → 햄버거(☰) 슬라이드 드로어 + 딤 오버레이(클릭/ESC 닫힘)
- ≤768px: `calc-layout` 1열(계산기/배당 공유), 입력패널 sticky 해제, 분포/지표 그리드 축소, 테이블 가로 스크롤, **input 16px(iOS 포커스 줌 방지)**, 시장지수 2열
- ≤480px: 로고 아이콘만 + "Google로 로그인"→"로그인" 축약(모바일 navbar 겹침 스크린샷서 발견·수정)
- symbol 2열→1열·헤더 세로 스택, myassets 탭 풀폭, backtest/retirement는 기존 860px 쿼리 활용

**② 다크모드:**
- `html[data-theme=dark]`에 전체 팔레트 재정의(bg #0E141C·card #18212E·텍스트·보더·블루 계열 라이트닝). 기본은 OS `prefers-color-scheme`, navbar 🌙 버튼으로 수동 전환(localStorage `mm-theme`), head 인라인 스크립트로 FOUC 방지. 토글 시 리로드(차트가 생성 시점에 색을 읽으므로 일괄 적용).
- Chart.js 전역 다크 기본색 + 페이지별 grid색 `MM_CHART_GRID` 상수화(charts.js). html2canvas 공유 이미지 배경도 테마 연동.

**③ 색상 변수화 (다크 전제조건):** 신규 변수 `--green-pale/--red-pale/--gold-pale/--blue-soft/--gold-deep/--input-bg/--navbar-bg` 추가 후 템플릿 9종 + calculator.js/multi_account_ui.js 인라인 하드코딩 라이트 색상 ~200곳을 var()로 치환. **share.html/share_img.html은 standalone(style.css 미로딩)이라 라이트 고정 유지** — share.html 오치환을 git diff 검수에서 발견해 원복.

**④ UX:** 동작 없던 ⚙ 버튼 제거 → 테마 토글로 교체.

**검증:** 신규 `tests/test_responsive_dark.js`(Playwright, 로컬 Flask) — 9페이지 × 3뷰포트(390/768/1280) × 2테마에서 가로 오버플로우 없음·테마 적용·JS 런타임 에러 0 + 드로어 열림/닫힘 + 1280px 링크 숨김/1500px 노출(BUG-NAV-1 회귀) + 테마 토글 전환 = **168 PASS / 0 FAIL**. 스크린샷 육안: 홈·계산기·은퇴·세금설정·계산기 세금패널(멀티계좌 폼) 다크/모바일 전부 정상. 기존 simple calc 25 + dom 35 PASS, 전 라우트 HTTP 200. 캐시버전 v20260611ui 일괄 갱신.

_작성: Claude (Fable 5)_

---

## [2026-06-10] decision | Playwright 도입 + 다계좌 세금 E2E 계획 + 세션 동기화

같은 날 간편계산기 배포 후 이어진 작업 3건 + 마무리 동기화.

**① Playwright 실브라우저 검증 체계 도입 (오너 지시).** `npm i playwright` + Chromium. 설치 중 npm이 package.json 부재로 jsdom 39패키지 prune하는 사고 → `package.json` 신설(devDeps: jsdom+playwright)로 재발 방지. 간편계산기 라이브 검증 10 PASS(`tests/test_simple_tools_browser.js` — 입력 재계산·과세 토글·탭 전환·차트 canvas·콘솔에러 0)로 체계 입증. **효과: 이제 "브라우저 육안 미확인" 잔여 항목을 Claude가 스크린샷 포함 직접 검증 가능.**

**② BUG-NAV-1 발견·등록.** 1280px 스크린샷서 navbar 링크 글자 세로 깨짐("계산기"→계/산/기). 원인 = 링크 9개("간편 계산기" 추가) overflow + `.nav-link`에 nowrap 없음. 수정 보류 — nowrap만 넣으면 우측 검색/로그인 밀려서 좁은 폭 처리(E1 모바일)와 같이 결정.

**③ 다계좌 세금 E2E 검증 계획 (오너 요청) = `다계좌세금_E2E검증_plan.md`.** 투자계산기(6)·백테스트(3)·은퇴sim(3)·인출기(4) = 16건. 라이브 서버 대상, 진짜 클릭 우선, 판정 3층(구조+API 응답 캡처+불변식: 세금ON≤OFF·절세액≥0·미실현차익↑→세금↑ 등). 셀렉터 전부 실측해 표로 고정. smoketestguide 손절차의 자동화+4탭 확장 = **roadmap P0 L7 실행판.** 실행 대기.

**④ 세션 동기화 (오너 "정리해"):** 간편계산기 ✅를 ideas.md·features.md·product/dev-status.md·trackG plan 끝·README 컨텍스트(05-30 stale였음)에 반영. GAP-DECUM-COMP 오너 재확인 = **계속 보류.** roadmap P0/다음액션 갱신(다음 = E2E 16건 실행 OR 세금계산기).

_작성: Claude (Fable 5)_

---

## [2026-06-10] feature | 간편 계산기 4종 신규 (/simple — P1 quick win)

오너 결정: 다음 작업 = P1 간편계산기(L7 실데이터검증·GAP-DECUM-COMP 보류 대신). 계획파일 `간편계산기_plan.md` 결정대기 4건 전부 확정 — ① 4종 전부 + 복리에도 세후·인플레조정 추가 ② 클라이언트 JS 전용 ③ 기존 배당금 계산기(롤링 역산)와 별개 신규 ④ 출력 자체 설계(입력만 잼투리식).

**구현:** 신규 `/simple` 페이지(app.py 라우트 + base.html nav/sidebar 링크 "간편 계산기").
- `templates/simple.html` — 탭 4종: 복리 / 배당 재투자 / 인플레 생활비 / 실질 구매력. 입력 변경 즉시 재계산(계산 버튼 없음).
- `static/js/simple_tools.js` — 순수 계산 함수 4종(stCompound/stInflationCost/stRealValue/stDividendReinvest) + 렌더·탭·Chart.js 라인차트(명목·실질·원금/누적배당). 서버 호출 0.
- 계산규약: 월초 적립 → 월복리(월율 = 연율 기하환산, CAGR 일치). 과세 15.4%(복리=세후 수익률, 배당=배당마다 원천징수 후 재투자). 실질 = 명목/(1+인플레)^년. 연증액률 = 매년 월적립 ×(1+g).
- 배당 모델(잼투리식 스노우볼): 주가는 배당성장률로 상승(시가배당률 일정 가정), 주기(분기/월)마다 평가액×수익률/지급횟수 지급 → 세후 전액 재투자.

**검증:** `tests/test_simple_tools_calc.js` 손계산 대조 **25 PASS**(거치식 P0(1+r)^N 정확 일치·r=0 평가=원금·과세 세후율·연증액 원금·월초적립 FV 공식·분기복리 1.01^4·월배당+성장 결합식·표 정합) + `tests/test_simple_tools_dom.js` jsdom **35 PASS**(Flask 렌더 HTML 주입: 초기렌더 14필드·탭전환·입력→재계산·과세토글 ON/OFF·주기 라디오·표 행수·런타임에러 0) + 전 라우트 8개 HTTP 200 회귀. jsdom 디버그 1건: 생성자 반환 시점 readyState='loading' → 테스트가 DOMContentLoaded 대기하도록 수정(프로덕션 코드 정상).

⚠️ 브라우저 육안·서버 배포 검증 남음. **▶ 다음 = 커밋·Hetzner 배포·서버검증.**

**[같은 날 추가] 배포·서버검증 완료:** 커밋 fe7c7af push → Hetzner 자동배포. 라이브 검증 PASS — `/simple` HTTP 200(20,617B), `simple_tools.js?v=20260610st` HTTP 200·로컬과 바이트 동일(diff 0), 홈/계산기/은퇴 nav 링크 노출, 4패널(compound/dividend/inflation/realvalue) HTML 존재. 잔여 = 브라우저 육안(오너).

_작성: Claude (Fable 5)_

---

## [2026-06-09] audit | 세금 커버리지 전탭 풀 매트릭스 감사

G5-D 후 오너 요청 — 세금 구현 완성도 실측 감사(기존 테스트 재실행 아님, 코드 경로 읽기로 탭×계좌×이벤트 대조).

**매트릭스 실측:**
- **적립 3탭(계산기·백테·은퇴적립)** = 단일소스 `MultiAccountSimulationLoop` 경유 확인. 계산기 세금ON 단일계좌도 멀티경로 라우팅(`run_calculator_logic:518`). 백테는 `MultiAccountSimulationLoop` 직접·계산기/은퇴적립은 `MultiAccountAnalyzer`(롤링 래퍼)지만 동일 루프. 세금이벤트 전부 단일소스: 배당세(`TaxedDividendEngine`)·리밸 양도세(`sell_with_tax`)·청산세(`apply_liquidation_tax`)·ISA만기(`_mature_isa`)·연납입공제(`annual_tax_deduction`)·이전공제(`_accrue_pension_credit`)·금종세(`comprehensive_years`). `apply_final_liquidation`=계산기/백테 True·은퇴적립 False(무청산 인계) 정확.
- **인출(은퇴인출)** 단일=`WithdrawalAnalyzer`(세금ON시 `TaxableSimulationRunner` 경유=배당세+CG+청산, 평탄 DividendEngine은 OFF분기만) / 멀티=`analyze_household_withdrawal`(`_build_account_runtime`이 TaxedDividendEngine+TaxedOrderExecutor). 양측 일관: 인출 매도 양도세·배당세·cost_basis 인계과세·연금소득세(`pension_separate_tax_annual`).
- **배당금 계산기** tax_engine 전달(`dividend_logic.py:82`)+`after_tax_dividend`(위탁 15.4%·ISA/연금 gross 반환=비과세/과세이연 정확).

**결과: 신규 배선버그 0.** 4탭 풀플래그 도달·단일↔멀티 일관·세율 정확. 과거 반복 패턴(TAX-1/2/3·WD-TAX) 이미 다 해소됨 — 처음 추정(1~2개 발견)보다 깨끗. 최근 G5-C/D가 인출측 꼼꼼히 배선한 덕.

**발견 갭 1개(버그 아닌 근사):** **GAP-DECUM-COMP** — 인출 중 금융소득 종합과세 미모델링(`multi_account_withdrawal.py:107` other_financial_income=0 하드코딩). 은퇴 중 위탁 배당 2천만 초과시 종합과세 가산 안 함 → 고액 위탁 보유자 과소과세 가능. **오너 결정: 판단 전 보류**(bugs.md 등록, 지금 구현 안 함).

**▶ 다음 = L7 실데이터 통합검증(브라우저 육안) OR 타작업.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-09] feat | G5-D 은퇴 인출기(standalone wd) 멀티계좌+세금 배선 구현

설계(2026-06-07) 구현 완료. 오너 결정: 공통 리밸(wdRebal/wdBand 상단 공통) 적용.

**백엔드(`retirement_logic.py`):** `run_withdrawal_logic`에 `accounts>1` 분기 + 신규 `_run_multi_account_withdrawal_logic`. 적립 분포 없는 인출기라 `analyze_household_samples`(sim용) 대신 **`analyze_household_withdrawal` 직접 호출**(시작 목돈=사용자 입력). 계좌별 spec: `value=initial_capital`, `cost_basis=목돈−미실현차익`(위탁·세금ON시; else None), 공통 rebal. 반환 매핑=`multi_account.accounts[].distribution.end_value`+`combined_summary`(survival/combined_end_value)+`median_pension_tax`. **단일 세금 갭(BUG-WD-TAX)은 백엔드 이미 배선됨(run_withdrawal_logic L694~705이 tax_engine 생성·WithdrawalAnalyzer 전달) — UI 갭이 유일 원인.** `normalize_multi_accounts`에 `unrealized_gain` 필드 추가(기본0, 기존 무영향).

**모듈(`multi_account_ui.js`):** `MMTAX.mode` 인식. `_mmAmountFields`(신규)·primary 카드가 mode='withdrawal'이면 **월적립 숨김·시작목돈 라벨·위탁 미실현차익칸**(primary 위탁 포함). calculator/적립기(accumulation 기본)는 무변경.

**UI(`retirement.html`):** `switchMode`가 MMTAX 모드 스왑(wd=wdSeed/withdrawal, sim=simSeed/simMonthly/accumulation)+renderTaxAccounts 재호출. wd body에 세금(`tax_enabled`/`account_type`/`gain_harvesting`/`user_settings`)+`buildWdAccountsPayload`(신규, 시작목돈·미실현차익·월적립 없음)+분배정책. renderRetirement가 wd 멀티 per-account 분포 렌더(renderMultiAccountSummary)+`median_pension_tax` 표시. 모듈 캐시 v20260607g5d.

**검증:** L13 백엔드 `test_g5_wd_household.py` **6종 PASS**(dispatch 단일/멀티·cost_basis=목돈−미실현차익·세금OFF시 None·반환shape·연금세 surface) + 광역 회귀 **71 PASS**(G5 인출·적립·백테 무손상) + **jsdom 14종 PASS**(wd 패널 월적립숨김·위탁 미실현차익·payload shape·sim 회귀) + E2E 실DB(458730 위탁+069500 연금: 멀티 생존율·계좌별 분포·median_pension_tax 6,121,986·tax ON/OFF).

⚠️ 미해결 가정: 계좌별 리밸=상단 wdRebal 공통(계좌별 리밸 UI 없음, 필요시 후속). 브라우저 육안 미확인(jsdom+E2E 커버).

**▶ 다음 = 커밋·Hetzner 배포·서버검증. 이후 G5 멀티계좌 UI 4탭(계산기·백테·은퇴적립·은퇴인출) 전부 완료 → L7 실데이터 통합검증 OR 타작업.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-07] design | G5-D 은퇴 인출기(standalone wd) 멀티계좌+세금 배선 설계

오너 지적: 은퇴시뮬(sim)=적립기+인출기, 인출 부분은 같은 엔진이어야 하는데 인출기 탭만 단일. **2단계서 "인출기 백엔드 미지원"이라 한 건 부정확 — 정정.** 멀티 인출 엔진 `analyze_household_withdrawal`(위탁→ISA→연금 순차소진+연금소득세+위탁 양도세)은 **이미 존재·sim서 작동 중**(내 E2E 생존율 0.6879가 그 결과). 다만 standalone `run_withdrawal_logic`이 옛 단일 `WithdrawalAnalyzer`만 호출 → 인출기만 단일. **추가 갭: 인출기 wd body가 세금 필드 자체를 안 보냄(단일조차 세금 OFF).**

**설계(plan §G5-D):** `run_withdrawal_logic`에 accounts 분기 → `analyze_household_withdrawal` 직접 호출(시작 목돈=사용자 입력, sim의 analyze_household_samples는 적립분포용이라 불필요). 모듈 `MMTAX.mode` 인식(wd 모드=월적립 숨김·위탁 미실현차익칸). UI switchMode MMTAX 스왑 + wd body 세금·accounts + 결과렌더.

**오너 결정:** Q1 공용패널 재사용(월적립 숨김) · Q2 취득가=계좌별 미실현차익 입력칸(cost_basis=목돈−미실현) · Q3 인출 시작 나이=wdPensionStartAge. 미해결: 계좌별 리밸은 상단 wdRebal 공통 가정.

**▶ 다음 = G5-D 구현(모듈 mode인식→run_withdrawal_logic 멀티+단일세금→UI→jsdom+E2E→배포). L13 검증.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-07] feat | G5 2단계 — 백테스트·은퇴 멀티계좌 UI 배선 (배포 완료)

1단계(공용모듈 추출) 후 2단계 = backtest·retirement 탭 배선. 공용 `multi_account_ui.js` 공유.

**모듈 config화:** `MMTAX`(portfolioTickers·totalInitId·totalMonId)로 탭별 결합점 파라미터화 → calculator는 기본값(tickers/initialCapital/monthlyContrib)으로 무변경. backtest=btTickers/btSeed/btMonthly, retirement=retTickers/simSeed/simMonthly 주입. `renderMultiAccountSummary`(분포 렌더)도 calculator.js→모듈 이동(계산기·은퇴 적립 공유).

**백테스트(2-A):** 단일 `account_type` 드롭다운 → 멀티계좌 패널. 멀티 페이로드 빌더 + **계좌별 스칼라 종료자산**(단일 역사윈도우라 분포 아님) + 절세 + g2 자체 렌더(`btRenderMultiAccount`). E2E 동기 `/api/backtest/run` 2계좌 → multi_account=True·accounts=2·savings.combined 반환.

**은퇴 적립기(2-B):** 단일 드롭다운 → 멀티계좌 패널. sim(적립기) accounts 페이로드 + `renderMultiAccountSummary`(calculator 동형 분포) 호출. updateRetTaxInfo 계좌유형을 taxAccounts[0]서 파생. **인출기(wd)는 단일 유지** — `run_withdrawal_logic`이 accounts 미지원(백엔드 한계, UI 범위 밖). E2E `run_retirement_logic` 직접 멀티호출 → multi_account.enabled=True·accounts=[위탁,연금저축]·생존율 0.6879·savings.combined(절세 1,632,510)·g2 반환.

**검증:** jsdom 3탭 스모크 **11/11 PASS·런타임에러0**(calc 회귀 — config+renderMASummary 이동 무손상 / bt 회귀 / ret 신규). E2E 백테(sync)·은퇴(직접) 둘 다 멀티 shape 확인. ✅ **커밋(fd41f65·9cface8)·푸시·Hetzner 배포 완료** — 라이브 3탭 모두 모듈 v20260607c 참조·HTTP 200(23,253 bytes).

⚠️ **잔여:** 브라우저 실클릭 미확인(jsdom+E2E로 커버되나 육안 아님). 인출기 멀티계좌는 백엔드 미지원(별도 엔진 과제). **▶ G5 멀티계좌 UI 3탭(투자계산기·백테·은퇴적립) 전부 완료. 다음 = L7 실데이터 통합검증 OR 인출기 멀티 엔진 OR 다른 작업.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-07] refactor | G5 1단계 — 멀티계좌 UI 공용모듈 추출(calculator)

오너 결정(공용모듈 b) 따라 1단계 착수. 신규 `static/js/multi_account_ui.js` — calculator.js 멀티계좌 입력 UI 16함수(ACCOUNT_TYPES·buildDistributionPolicy·계좌/종목 CRUD·renderTaxAccounts·checkTaxLimits·fmtTaxKRW) **순수 이동**(로직 무변경). calculator.js서 288줄 제거. calculator.html이 모듈을 calculator.js **앞에** 로드(v20260607extract).

**설계 근거:** classic script들은 전역 lexical 환경 공유 → 옮긴 함수가 calculator.js 잔류 전역(`tickers`·`badgeColor`·`fmtKRW`) 런타임 참조 정상. 호스트 계약(전역 `tickers`/`window.taxAccounts`, DOM id `initialCapital`/`monthlyContrib`/`taxAccountList` 등)을 모듈 헤더에 명시 — 2단계서 backtest/retirement가 충족해야 함. 결과렌더(`renderMultiAccountSummary`)·토글·프로필로드는 탭별 glue라 모듈서 제외.

**검증(정적):** node --check 모듈·calculator.js 둘 다 OK, 결합 파싱 재선언 충돌 0, calculator 중복정의 잔존 0, 호스트 전역 보존.

**검증(브라우저 스모크 — jsdom):** 로컬 Flask 기동 → 렌더된 실제 `/calculator` HTML에 두 JS를 classic script로 주입(전역 lexical 공유 재현) → 멀티계좌 흐름 실행. **8/8 PASS, 런타임 에러 0:** 모듈함수 전역 노출·calculator 전역(badgeColor/fmtKRW) 보존·fmtTaxKRW·addTaxAccount×2·renderTaxAccounts 리스트 채움·addAccountTicker 종목행 렌더·updateTaxAccountAmount+checkTaxLimits 무throw·buildDistributionPolicy 우선순위 정렬. **calculator 회귀 0 확정.**

**배포·서버검증:** 푸시(57e1fc4)→Hetzner 자동배포. 라이브 `moneymilestone.duckdns.org/calculator`가 신규 모듈 참조(v20260607extract), `/static/js/multi_account_ui.js` HTTP 200(15740 bytes, 로컬 동일).

**▶ 다음 = 2단계(backtest/retirement 배선, 은퇴적립→백테→은퇴인출). 각 탭은 모듈 헤더 호스트계약(전역 tickers/window.taxAccounts, DOM id initialCapital/monthlyContrib/taxAccountList 등) 충족 필요.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-07] plan | G5 프론트 UI 배선 — 탭별 차이 정리 + 공용모듈 결정

본선(Track G5 멀티계좌 UI) 복귀. 백엔드(G5-A/B/C 엔진+L10~L12) 완료, 남은 건 프론트 UI뿐. **코드 실측 차이 정리:**

- **현 상태:** calculator만 멀티계좌 UI 완비(외부 `calculator.js`). **backtest·retirement는 구형 단일계좌 드롭다운(`account_type`)만, 멀티 UI 전무.** 두 탭은 JS가 **HTML 인라인**(`backtest.html` L358~, `retirement.html` L589~)이라 calculator.js 외부파일 공유 불가.
- **레퍼런스 3구성:** DOM 패널(`calculator.html` L117~164) + JS 함수군(`calculator.js` L1128~1450, ~320줄, BUG-G1-2 커서회피 내장) + 페이로드빌더(L272~383) + 결과렌더 `renderMultiAccountSummary`(L623~).
- **탭별 결과렌더 갈림(핵심):** 은퇴 적립=calculator 동형 분포(렌더 재사용) / 백테스트=단일윈도우라 계좌별 **스칼라 종료값**(분포 아님, 적응) / 은퇴 인출=**생존율 분포** 신규 렌더.
- **권장 순서:** 은퇴적립→백테→은퇴인출(동형부터, 엔진순서와 반대).

**오너 결정 = 공용 JS 모듈 추출(b).** 인라인 3벌 복제는 드리프트(BUG-G1-2식 수정 3곳) 위험으로 기각. 신규 `static/js/multi_account_ui.js` → 3탭 `<script src>` 공유. 1단계=calculator에서 추출(회귀0 확인), 2단계=backtest/retirement 배선. 상세 = `trackG_multiaccount_plan.md` 「G5 프론트 UI 배선」.

_작성: Claude (Opus 4.8)_

---

## [2026-06-06] investigation | 합성 리밸런싱 현상 = 실제 금융(버그 아님) + FX 상관 오염 발견

BUG-SYNTH-CORR 배포 후 오너가 "합성 40년 리밸하면 자산↑·MDD 불변·밴드 넓힐수록 더↑(37→44억)" 이상현상 제기 → 심층 조사(서버 실DB·읽기전용 + 순수 numpy). 상세: [[합성_리밸런싱_조사]].

**핵심 결론 — 리밸 수익증가는 버그 아니라 실제 금융현상:**
- 집행 단계 가치보존 확정(코드): 트레이드가 가치 안 만듦. 종료자산↑는 누수 아니라 리밸 프리미엄.
- **순수 GLD+SPY 실데이터(합성 0) 2004~26:** always +17.0%(실제=셔플 동일=순수 변동성수확), **band30 +57.6%(실제) vs 셔플 +0.0%** → 넓은밴드 프리미엄은 **실제 금/주식 다년 로테이션 사이클**에서 100% 나옴. 합성(i.i.d.)은 이 사이클 못 살려 band 중앙값 0+고분산 노이즈 → 합성이 **과대 아니라 과소·불안정**.
- 실제 엔진 재현(GLD+SPY 40y 합성): 리밸 +15~23%·MDD ~2%p 변화(평탄) robust 재현. 단 band1%(잦음) 최고·band30 최저 → 오너의 "band30 최고" 순위는 **고분산 노이즈라 미재현**.
- 오너 직관 "리밸=수익↓·MDD↓"는 같은클래스/추세 자산엔 맞으나 **분산자산엔 안 맞음**(리밸 분산자산 = 역사적 free lunch).

**별건 발견 — FX 상관 오염:** 상관을 KRW(`apply_fx=True`)서 계산 → USD/KRW 공통인자가 모든 미국자산 상관을 양수로 부풀림. **TLT-SPY USD −0.16 → KRW +0.23**, GLD-SPY USD +0.06 → KRW +0.25, SCHD-SPY 0.89→0.91(고상관이라 영향 미미). 웹 확인: TLT-SPY 역사적 음상관. → **MDD가 안 줄어드는 핵심 = KRW 양상관이라 헤지 죽음.** USD 언더라잉 모델링하면 음상관 살아남(미결 결정).

**오너 결정:** 실데이터가 진짜이므로 **코드 수정 안 함**(손대면 신뢰도 훼손). 블록 부트스트랩(합성 사이클 보존)은 프리미엄을 없애는 게 아니라 합성 현실화일 뿐 → 보류. FX 상관공간(KRW vs USD)·합성 band 저신뢰 경고도 보류. **BUG-SYNTH-CORR 수정은 배포·유지**(같은클래스 정확, 분산자산은 FX-KRW 충실 재현).

_작성: Claude (Opus 4.8)_

---

## [2026-06-06] fix | BUG-SYNTH-CORR 조건부 다변량 합성 구현 — 합성구간 상관 복원

설계 플랜(업데이트48) 오너 결정 확정 후 구현. **결정: 9.1=a**(μ_S 캡 backstop)·**9.2=b**(쌍별 추정+nearest-PSD)·**9.3=a**(다변량-t)·**9.4=a**(DB경로 후순위).

**신규 `modules/retirement/synthetic_mvn.py`:**
- `estimate_joint_stats(tickers, raw_loader)` — 종목별 실데이터 전체 일일수익(get_price FX·KRW)으로 μ·σ, **쌍별(9.2=b) 최대겹침구간 상관** 산출 → 고유값 클리핑 **nearest-PSD 보정**(단위대각 복원) → cov. 표본<252 or 쌍 겹침<252면 경고/0가정, 종목 표본부족 시 `ok=False`(폴백 신호).
- `generate_joint_window(...)` — 윈도우별 조건부 다변량 합성 prefix + 실 suffix. actual_start 경계로 **세그먼트 분할**(구간마다 R=실범위·S=합성필요), `r_S = μ_S + B(a−μ_R) + L·z`(B=Σ_SR Σ_RR⁻¹, Σ_cond=Σ_SS−B Σ_RS, L=chol, z=표준t(df5)/T_SCALE). R 공집합이면 무조건 결합. μ_S만 일일캡(9.1=a), μ_R(centering)은 raw. FX anchor 역재구성(BUG-SYNTH-FX 유지).

**배선:** 단일 `_load_with_per_window_synthetic`·멀티 `_load_window_synthetic` 둘 다 함수 상단에 joint 분기 — raw_loader+tickers로 **lazy 1회 추정·캐시**(synthetic_params 플러밍 안 함, 실데이터에서만 유도) → `ok` 이면 `generate_joint_window` 반환, 실패(추정/생성 예외)면 **기존 종목별 독립 GBM 루프로 폴스루**(전부-joint 또는 전부-독립, 혼합 없음 → 회귀 0).

**핵심 디버그 — 역재구성 off-by-one:** 첫 테스트서 합성구간 corr 0.058(복원 실패). 원인 = `prices[i]=prices[i+1]/(1+r[i])` 역재구성이 r_i를 d_i→d_{i+1} 전이로 만들어 **pct_change가 1일 밀림** → r_i는 a_{d_i}에 조건부인데 corr 측정은 a_{d_{i+1}}과 매칭돼 상관 소멸. **수정:** 전이에 `r[i+1]` 사용 → day d_i pct_change = 조건부 r_i 정렬. (독립 폴백 경로는 상관 무관이라 미수정.)

**로컬 검증** `tests/test_synthetic_mvn.py` 5종: 인메모리 corr=0.8 합성데이터로 추정 **0.808** → `generate_joint_window` 합성구간 복원 **0.788**(독립이면 ≈0)·nearest-PSD 단위대각·경계점프 0.5~2·결정론(동일seed 동일가격)·표본부족 ok=False. 회귀: anchor-fx/data-preparer/accum 30 + 광역(rolling·multi·accum·synth·track_g·l_save·gate2·l3·backtest) **137 PASS**, 회귀 0.

✅ **커밋(4a48803)·Hetzner 배포·서버 검증 완료.** domino.service 배포 직후 재시작·HTTP 200. **서버 실데이터(읽기전용) 상관 복원 PASS:** SCHD real 2003-11~·SPY 1928~, 추정 corr SCHD-SPY=**0.913**(실 겹침), 합성구간 corr **0.03(수정전)→0.947(수정후)**(n=2084), SCHD 합성가격 2336~10897 KRW 비폭발(BUG-SYNTH-FX 회귀 무손상). 리밸 정상화(none↔band30 스프레드)는 브라우저 실측 잔여. DB경로(`generate_and_save`) 단일종목 독립이라 미수정(9.4=a 후순위, 캡·경고만).

_작성: Claude (Opus 4.8)_

---

## [2026-06-05] design | BUG-SYNTH-CORR 발견 + 조건부 다변량 합성 설계 플랜

BUG-SYNTH-FX(40년 폭발) 수정 후 오너가 밴드 리밸런싱 이상 발견: 합성 GLD+SCHD+SPY 33% 등비중
40년(초기 1천만·월 50만·세금OFF)서 **무리밸 33.2억 / 밴드1% 37.6억 / 밴드30% 40억** —
밴드 넓힐수록 최종자산이 오히려 늘고, MDD 평균은 22→20→21%로 거의 안 움직임. "리밸하면 보통
수익 줄어야 정상인데 늘고, 넓은 밴드가 더 많이 버는 건 말이 안 된다."

**조사(서버 DB 복사본 실측):**
- ① `OrderExecutor.execute_orders` 전후 포트 가치 계측 → net 변화 0(135회 전부 값보존). **리밸 로직 무죄.**
- ② 실데이터 QQQ+SPY 40년·GLD+SCHD+SPY 18년(상관 실데이터)은 리밸 거의 무효과(+0~3%, 단조, MDD 정상). **정상.**
- ③ 합성구간 vs 실데이터 **상관계수 실측:** 합성 SCHD-SPY=**0.03**·GLD-SPY=-0.05 / 실데이터 SCHD-SPY=**0.89**.

**원인 확정:** `_load_with_per_window_synthetic`이 합성 prefix를 **종목별 독립 시드**(`seed=hash(code+window)`)로
따로 생성 → 종목 간 상관 ≈ 0. 실제 SCHD·SPY는 둘 다 미국주식이라 0.89인데 합성은 무상관 독립 랜덤워크.
독립자산은 변동성 수확(리밸 보너스)이 비현실적으로 극대화 + 두꺼운꼬리 노이즈로 밴드 민감도 들쭉날쭉.
**이 백테스트의 핵심 목적이 상관계수 기반 분산효과 시험**이라 합성구간에선 그게 완전히 깨짐. **BUG-SYNTH-CORR** 등록.

**설계 플랜** `합성상관계수_plan.md`:
- **1차안(시장팩터 모델) 폐기** — 오너 지적: 시장지수 없는 ETF는 상관 못 구현.
- **확정 방향 = 완전 조건부 다변량:** 데이터(실+백필) 겹침구간서 상관행렬 Σ·μ 추정 → 합성일마다 종목을
  R(그날 실데이터 있음)·S(합성 필요)로 분할 → `r_S = μ_S + B(a−μ_R) + L·z` (B=Σ_SR·Σ_RR⁻¹, L=chol(조건부cov),
  z=다변량-t)로 **합성종목이 같은 날 실종목 등락을 상관행렬대로 추종**. synth-synth(결합)+synth-real(조건부) 둘 다 재현.
  시장지수 불필요. R/S는 actual_start 경계서만 바뀌어 ≤k구간 분할·벡터화 → O(k³)·k≤5 경량(오너 "종목 4~5개 이상 없다").
- 신규 `synthetic_mvn.py`(추정+조건부 생성기) + `_load_with_per_window_synthetic` 결합 호출 교체 + params 배선.
  anchor-FX(BUG-SYNTH-FX)·mu캡·seed 유지. DB경로(generate_and_save) 후순위.
- **오너 결정 4건**(플랜 §9, 설명 추가): μ_S 캡 backstop(추천)·공통구간 엄격교집합+수축폴백(추천)·다변량-t 꼬리(추천)·DB경로 후순위(추천).

⚠️ **미구현 — 결정 4건 확정 후 착수.** 리밸 로직·실데이터 경로는 정상이므로 합성구간 한정 문제.

_작성: Claude (Opus 4.8)_

---

## [2026-06-05] fix | BUG-SYNTH-FX 가상데이터 40년 폭발 — 합성 anchor USD/KRW 단위 불일치

BUG-CALC-40Y 수정으로 40년이 돌기 시작하자 오너가 **QQQ+GLD+SCHD 등비중 40년 = 2.9조**(SPY 40년 62억 대비 수백배) 발견. 명백히 틀림.

**진단(서버 DB 복사본 288M 실측):** ① get_price 직접호출은 GLD 245배(정상)인데 계산기 sim은 폭발 → sim이 합성을 다르게 읽음. ② dividend_mode hold도 폭발(배당 아님). ③ **종목별 격리(40년 보유):** QQQ(합성無)=144배 정상, **GLD=70,679배·SCHD=44,300배** — 합성 종목만 폭발.

**원인 = BUG-DIV-3 계열 잔재(계산기 윈도우 합성 경로 미수정):** `AccumulationAnalyzer._load_with_per_window_synthetic`이 합성 prefix를 stitch할 때 anchor를 `synthetic_params["anchor_price"]`(data_preparer가 raw `price_daily`로 잡은 **USD**)로 사용. 실 suffix는 `get_price(allow_synthetic=False)`라 **FX(KRW) 적용**(US자산 ×환율 ~1300). → `actual_start` 경계에서 USD(GLD 44)→KRW(48,400) **~환율배 점프** → buy-hold가 경계 넘으며 ~1300배 폭등. `build_window_synth_params`(C3 보충경로)는 이미 get_price(FX) anchor로 고쳤으나, 계산기는 data_preparer USD anchor를 넘겨 이 경로가 안 고쳐짐.

**수정:** ① **anchor FX 정합** — 합성 anchor를 `actual_start`의 FX 실가격(`get_price` 첫 종가)으로 잡아 실 suffix와 단위 일치(build_window_synth_params와 동일 방식). ② **합성 mu 캡** `MAX_SYNTH_MU_MONTHLY=0.0065`(≈연8.1% USD, SPY 1928~ 장기치 기준) — 짧은 불장 표본 mu(GLD 연12.6%)를 수십 년 외삽하는 비현실성 완화. 두 합성 경로(window·DB generate_and_save) 동일 적용.

**검증(서버 DB 복사본, 40년 1천만 매수보유):** GLD 70,679→**18배**, SCHD 44,300→**14배**, QGS 포트 38,696배(354억)→**62배(6.16억)**, 재투자 76배(7.63억). SPY 40년 64배(6.4억)와 동급 — 폭발 제거·현실화. QQQ(비합성) 144배 불변 = 비합성 경로 무손상. 회귀 `tests/test_synthetic_anchor_fx.py`(경계 점프<5배·prefix KRW단위) + 관련 스위트(data-prep·accum·rolling·C3) 43 PASS.

**정직한 한계:** 상장 전 합성은 본질적으로 D등급 추측이다. 단일 mu 캡은 자산별 장기특성(예 금 1980~2000 횡보)을 못 잡아 여전히 근사다. 진짜 정확도 향상 = 실 프록시 매핑(금→GC=F/KRX_GOLD, 배당주→배당지수)·로그공간 생성(크래시가드 상방편향 제거)이며 별도 과제로 남김.

_작성: Claude (Opus 4.8)_

---

## [2026-06-05] fix | BUG-CALC-40Y 원인 확정·수정 — 백필 ok-skip이 합성 폴스루 차단

투자계산기 장기(40·30년) "가상 데이터 생성 불가" 에러 추적. **로컬 재현 불가**(로컬 DB 깊음)라 **서버 DB 실측 필요** — 오너 승인하에 Hetzner(178.105.84.213) SSH **읽기전용** 조회.

**진단 경로:** ① 셸로우 DB 로컬 repro → 코드 자체는 20/30/40년 전부 합성 정상(코드 무죄). ② 서버 git HEAD==origin/main(424d568) → **배포 stale 아님**(deploy 성공). ③ 서버 `price_daily` 실측: QQQ 1928~deep·GLD 2004real+synth1971~·**SCHD real 2003~**(인덱스 프록시 백필 한계, synth 0). ④ 서버 DB 복사본에 실제 `prepare_scenario_data` verbose 실행 → **결정적 재현**.

**확정 원인:** SCHD가 binding(2003). DataPreparer 3단계 보완에서 `BackfillEngine.backfill("SCHD")`가 "이미 백필됨(21,046행)→스킵"으로 **status=='ok'** 반환 → `if status=='ok': ... continue`가 **합성 생성을 건너뜀** → SCHD 2003 갇힘 → effective_start=2003. **40년:** 2003+40>2026 → n_cases=**0** → `calculator_logic` ValueError. **20년:** 2003+20≤2026 → n_cases=11(>0 통과 → "20부터 됨"). 비대칭은 순전히 n_cases==0 임계값(코드·sim_years 무관).

**수정(`modules/retirement/data_preparer.py` 3a 분기):** 백필 ok라도 `new_start > 목표(_min_target = data_end - sim_years - TARGET_CASES×step)`면 `continue` 대신 합성 생성으로 폴스루 → 잔여 구간 보충. 백필 실데이터(프록시)는 닿는 데까지 우선 사용, 그 이전만 합성.

**검증(서버 DB 복사본 288M 실측):** 수정전 40y n_cases=0 → 수정후 **40y=61·30y=61·20y=60**(SCHD 1971/1981/1991까지 합성 보충). 20y도 11→60 개선(회귀 아님, 케이스 증가). 회귀테스트 `test_scenario_data_preparer::TestBackfillOkShallowFallsThroughToSynthetic` 2종(백필 ok-skip→합성 폴스루·단기 무영향) + 관련 스위트(data-prep·g5·engine·retirement·rolling·wd1) **79 PASS**.

⚠️ GLD stale(로컬 2020 종료)는 별개 데이터 갱신 과제로 잔존(서버 GLD 2026까지 정상). **C3와 무관.** ⚠️ **미커밋·미배포**(push=Hetzner 자동배포).

_작성: Claude (Opus 4.8)_

---

## [2026-06-04] deploy | G5-C C3 전체 푸시 (8ea885a..4a4f90c, 10커밋)

세션 전체 작업 origin/main 푸시 — `8ea885a..4a4f90c`(clean fast-forward, force-push 아님 → divergent 위험 없음). deploy.yml Hetzner 자동배포 트리거됨. 커밋: gate2a golden·BUG-WD-1·C3.1~3.3·강검증+off-by-one·리밸·합성보충·BUG-CALC-40Y기록·status45.

**검증 한계(정직):** 이 환경에 `gh` 없어 GitHub Action 결과 직접 확인 못 함. 서버(178.105.84.213) HTTP 응답함(nginx 살아있음, 0.47s)이나 라우트 구조 불명으로 앱레벨 배포 성공은 미확인. 변경이 **엔진+테스트(신규 엔드포인트·UI 없음)**라 기능 검증 대상은 없음. ▶ 오너가 GitHub Actions 배포 성공 + 앱 정상 확인 권장.

_작성: Claude (Opus 4.8)_

---

## [2026-06-04] feat | G5-C C3 합성 보충 — 실윈도우 부족 시 GBM 패딩 (마지막 한계 해소) + BUG-CALC-40Y 기록

**합성 보충(잔여 한계 #2 해소):** `analyze_household_withdrawal`이 실윈도우만 쓰던 것 → 단일 WithdrawalAnalyzer처럼 실윈도우 < `MIN_CASES_WD(30)`이면 GBM(Student-t df=5) 합성 윈도우로 패딩. **구현:** 티커별 실종가→월(mu,sigma)(`_ticker_return_stats`, 단일 `_get_return_stats` 동형, 폴백 7%/15%) → 티커별 독립 합성 가격경로 생성 → `_synthetic_household_window`이 그 경로로 `simulate_household_window` 재사용(드레인 순서·연금세·취득가·리밸 전부 보존). 결과에 `n_real`/`n_synthetic` surface. 종목간 상관은 독립 근사(단일도 미모델링). 검증 `test_g5_c3_verification` D 2종(짧은 히스토리→30 패딩·긴 히스토리→패딩0). 기존 롤링 결정론 3종은 step 12→3(실윈도우≥30)으로 패딩 회피 유지.

**BUG-CALC-40Y 기록(오너 발견, C3 무관):** 투자계산기 QQQ+GLD+SCHD 40·30년 시뮬이 가상데이터 체크해도 "가상 데이터 생성 불가" 실패(20년 정상). 에러 출처 `calculator_logic.py:268`(`prepare_scenario_data` n_cases==0). 로컬 재현 불가(로컬 DB는 백필 깊음→n_cases=60 정상) → **서버 DB(gitignore, lazy backfill) history 얕음 추정.** 추가로 로컬 GLD 데이터 2020-12-30 종료(stale). `bugs.md` BUG-CALC-40Y에 상세 기록 — 미해결(서버 DB 확인 필요). **C3와 완전 별개 트랙.**

**전체 회귀 PASS.** ⚠️ G5-C C3 잔여 한계 전부 해소(리밸·합성보충). dividend_mode 전역은 단일과 일관(무해).

_작성: Claude (Opus 4.8)_

---

## [2026-06-04] fix | G5-C C3 리밸런싱 한계 해소 — 인출 시뮬에 rebal_mode 배선

강검증 후 남긴 잔여 한계(리밸 미배선) 해소. 인출 시뮬레이터 `_build_account_runtime`이 `PeriodicRebalance(None)` 고정이라 인출 페이즈 리밸런싱 미발생 → 다종목+리밸모드 계좌가 단일 경로와 divergence. **수정:** 적립(multi_account_common/MultiAccountAnalyzer)과 동일 로직으로 계좌별 `rebal_mode`/`band_width`→전략(none/band/주기) 빌드. `analyze_household_samples`·`_run_multi_account_retirement_logic` account_specs에 rebal_mode/band_width 전파.

**검증 빡세게:** `test_g5_c3_verification` 9종(+2)으로 보강 — **리밸 실발생 증명**(2종목 발산가격, none vs quarterly 종료값 상이) + **리밸 포함 정합**(분기·밴드 단일 SimulationLoop == 멀티1 `simulate_household_window` **±1원 정확**). 단일종목·무리밸 경로 불변(default none). **전체 회귀 212 PASS.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-04] test | G5-C C3 강검증 — 정합 앵커·분수 생존율·실데이터 + off-by-one 수정

C3 검증이 평탄가격·단일종목·무배당에 치우친 구멍 지적받아 빡세게 보강. `test_g5_c3_verification` 7종 신규:
- **A 정합 앵커(플랜 골든):** 단일 SimulationLoop == 멀티1계좌 `simulate_household_window` — 성장(100→200)·하락(200→60) **±1원 정확**, 인플레이션 ±1만원. ⚠️ **off-by-one 발견·수정:** 멀티가 첫 달 인출(단일은 `last_withdrawal_month`=시작월로 첫 달 스킵)해 1회 더 인출 → 단일과 1개월 어긋남. 멀티도 첫 달 스킵하게 수정 → 정확 일치. (기존 C3.2a 절대값 3종 24→23회로 갱신.)
- **B 분수 생존율:** 전반 평탄·후반 급락 변동경로 → 0 < 생존율 < 1 (기존엔 1.0/0.0만).
- **C 배당/성장/리밸:** 배당 재투자 종료값↑·2종목 배분·고성장(100→300) 인출에도 자산증가 — 미검증 코드경로 커버.

**실데이터 스모크(run_retirement_logic 멀티, 069500+458730, 세금ON, 적립5+인출5년):** 53초, `withdrawal_pending=False`, 11샘플, **생존율 0.8405(분수)**, `sample_success_rates=[0.3,0.42,0.83,...,1.0]` **분위 단조증가**(낮은 적립분위→낮은 생존, 기대형태 정확), combined p50 7,222만, is_safe False(0.84<0.90 일관). 실데이터·성능·분수생존 구멍 동시 해소.

**전체 회귀 210 PASS.** off-by-one 수정은 multi_account_withdrawal.py(인출 페이즈)에 격리 — 적립/백테/계산기 무관.

_작성: Claude (Opus 4.8)_

---

## [2026-06-04] feat | G5-C C3 은퇴 인출 멀티계좌 — 가구 디큐뮬레이션 오케스트레이터 (생존율 완성)

멀티계좌 은퇴 인출(`withdrawal_pending` 스텁) 해소. 단일 RetirementPlanner→WithdrawalAnalyzer 흐름의 멀티 대응 신규 구축. 3 단계, 각 단계 손계산/결정론 검증 후 진행.

**C3.1 가구 인출 오케스트레이터** (`modules/retirement/household_withdrawal.py`): 월 가구 net 인출액을 **위탁→ISA→연금/IRP** 순 소진(오너 Q2). 위탁/ISA=net 인출(CG세 sell_with_tax 별도, BUG-TAX-2), 연금/IRP=gross-up(개인 합산 1500만 판정 `pension_separate_tax_annual`, 오너 Q3). 단일 WithdrawalEngine 매도 재사용 → 단일==멀티1계좌 정합. 검증 `test_g5_household_withdrawal` 6종(소진순서·연금 4.4%/16.5%·합산판정 15.6M→둘다16.5%·위탁CG 77원·고갈 불변식).

**C3.2 멀티 디큐뮬레이션** (`modules/retirement/multi_account_withdrawal.py`): `simulate_household_window`(N계좌 합동 1윈도우, 계좌별 배당·리밸 독립 + 가구인출 결합, 취득가 인계=C1 원리) + `analyze_household_withdrawal`(실가격 롤링→**합산 생존율**, 합산자산이 월인출 못대는 첫시점=실패=오너 Q4). 검증 윈도우 5종(생존9.6M·소진순서 위탁0→연금2.8M·고갈실패·연금세 생존하락·보존불변식)+롤링 3종(생존율1.0/0.0·분포·계좌별 surface). **C4(합산 생존율) 흡수.**

**C3.3 배선** (`analyze_household_samples` + `retirement_logic._run_multi_account_retirement_logic`): 적립 분포 11분위 샘플(계좌별 동일분위 시작값=오너결정) → 각 가구 인출 롤링 → 합성 생존율. `withdrawal_pending`/`sample_results`/`combined_summary` 실제 surface(단일 RetirementPlanner 형식 미러). 검증 `test_g5_retirement_withdrawal`(L12) 5종(생존 end-to-end·고갈·구조불변식·무입력 pending유지·연금세 생존≤OFF).

**전체 회귀 203 PASS.** ⚠️ UI 미배선(엔진 우선, 오너결정 — retirement.js 생존율 패널은 별도). ⚠️ 멀티 인출 롤링은 in-process 순차(합성보충 없음, 실윈도우만) — 실데이터 성능은 추후. ⚠️ BUG-WD-1(인출 2배 과소) 선수정으로 단일 은퇴 생존율도 정확해짐.

**▶ G5-C 엔진 핵심 완료(C1 위탁인출세·C2 연금세·C3 가구오케스트레이터·C4 합산생존). 다음 = UI 배선(retirement.js) OR L7 실데이터 통합.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-04] fix | BUG-WD-1 은퇴 인출 ~2배 과소인출 (현금흐름 버그, C3 전 발견)

**발견 맥락:** C3(가구 인출 오케스트레이터) 착수 전 인출 원시함수(`WithdrawalEngine`) 검토 중 발견. 가구 오케스트레이터를 이 위에 지으면 멀티도 동일 버그 상속하므로 먼저 수정(오너 승인).

**버그:** `WithdrawalEngine.process` 매도 경로 — `needed = withdrawal_amount - cash; cash = 0` 후 `needed`만큼 매도(`portfolio.sell` → proceeds를 cash에 가산)하나 **인출액을 cash에서 빼지 않고 종료.** → 매도월엔 자산→cash 이동만(실제 유출 0), 다음달 주차 cash로 충당(매도 없음) → 격월로만 실제 유출 → **유효 인출률 ≈ 50%.** 실증: 평탄가격 자산 12,000 → 월 1,000×12 인출(의도 12,000) → 종료 6,000(절반만 유출).

**영향:** 단일 은퇴 생존율 **과대평가**(인출 절반만 일어나 자산 더 오래 버팀). 지금까지 모든 은퇴 인출 결과. BUG-TAX-2/3와 별개(세금 아닌 현금흐름). 단일·멀티 인출 공유 원시함수라 C3도 위험했음.

**수정:** 매도 루프 후 `portfolio.cash = max(0.0, cash - outflow_from_sales)`(=매도로 충당할 인출분). CG세는 `sell_with_tax`가 별도 차감 → retiree net + 정부 세금 둘 다 정확 유출. 자산 부족 시 0 바닥(생존 실패).

**검증(재현 먼저=goal-driven):** `tests/test_bug_wd1_withdrawal_outflow.py` 4종 — ① 평탄 12개월×1000=정확 12,000 ② 기존cash 우선소비 후 매도 합계정확 ③ 인플레이션 Σ월별 inflated ④ 고갈 0바닥. 수정 전 3 FAIL→수정 후 4 PASS. **전체 회귀 184 PASS**(은퇴 테스트 불변식 기반이라 절대 생존율 골든 없음 → 자동 그린). ⚠️기존 단일 은퇴 생존율 바뀜(과대→정확, 하락).

**▶ 다음 = C3 가구 인출 오케스트레이터(이제 정확한 원시함수 위에).**

_작성: Claude (Opus 4.8)_

---

## [2026-06-04] test | gate2a stale golden 갱신 (BUG-TAX-1 배당세 반영)

전체 회귀서 `test_gate2a_runner_vs_legacy` 2종 FAIL(off/on) 확인 — Phase1 골든(off 38,415,192/on 41,990,905)이 BUG-TAX-1(단일경로 배당세 차감, 업데이트31) 이후 미갱신. 실제값 off **37,365,073**(−1,050,119)/on **40,913,520**(−1,077,385). 하락분 = SPY 재투자 배당 15.4% 배당소득세. 코드 회귀 아님(carried_cost_basis default None → calculator/backtest 불변). 골든 2개 + 사유주석 갱신. gate2a 4 PASS. (74c343c)

_작성: Claude (Opus 4.8)_

---

## [2026-06-03] fix | G5-C C2 연금소득세 인출 배선 (분리과세 전액 16.5%, BUG-PENSION-1 해소)

**C2:** 인출 연금소득세를 하이브리드(`pension_effective_rate`→`pension_monthly_after_tax`: 1500이하 저율+초과분만 16.5%, BUG-PENSION-1) → **`pension_separate_tax_annual`**(1500 이하 나이별 3.3~5.5%, 초과 시 **전액** 16.5%, 오너결정·현행 선택분리과세)로 교체.
- `WithdrawalAnalyzer._calc_gross_withdrawal`: gross-up 실효율 = `pension_separate_tax_annual(annual_est, age)/annual_est`. (연금 인출은 net 수령 위해 계좌서 gross 인출 → 그 차액이 세금.)
- `_calc_pension_tax_by_age`(표시): 나이 구간별 실효율도 분리과세 기준 → 1500만 초과면 전 구간 16.5%.
- pension_start_age = 인출시작 가정(Q3) → 인출 나이(withdrawal_start_age)가 곧 연금 수령나이라 단일계좌는 충돌 없음.

**검증 `tests/test_g5_pension_withdrawal_wiring.py` 3종:** 나이별 gross-up(55→5.5·70→4.4·80→3.3, 연1200만)·1500만 초과 전액16.5%(나이무관)·pension_tax_info 분리과세 반영. 회귀 **122 PASS**.

⚠️ 하이브리드 함수군(`pension_monthly_after_tax`/`pension_annual_tax`/`pension_effective_rate`/`_pension_excess_rate`) 이제 프로덕션 미사용(미삭제 — pre-existing 공개 API). ⚠️ `run_withdrawal_logic`·은퇴 인출 연금 결과 바뀜(과소→정확). **BUG-PENSION-1 해소.**

**▶ 다음 = C3 가구 인출 오케스트레이터(멀티, 위탁→ISA→연금 순차소진).**

_작성: Claude (Opus 4.8)_

---

## [2026-06-03] fix | G5-C C1 인출 과세 배선 + BUG-TAX-3 진단 정정 (취득가 인계)

**진단 정정 (오너에게 보고·동의):** 앞선 "은퇴 이중과세" 진단은 **부정확**했음. `run_retirement_logic`/`app.py:retirement_run`의 `wd_config`에 `tax_engine`이 없어 **인출투영은 원래 면세**였음(`_calc_gross_withdrawal`/`pension_tax`는 tax_engine 있을 때만 작동). 즉 적립끝 청산세가 **유일 세금**(이중 아님). ∴ BUG-TAX-3 수정(적립 무청산)만 하면 적립면세+인출면세 = **세금 0 회귀**. 오너 규칙 "은퇴 절대 일괄청산 금지"의 올바른 구현 = 적립끝 청산 제거(전반부) + **인출 과세 배선(후반부=C1)**.

**모델 확정 (오너):** 적립 종료 시 일괄과세 없음(무청산 gross 인계) → **인출하면서 과세.**

**C1 구현 (취득가 인계, 단일+멀티 공유 토대):**
- `carried_cost_basis` 플러밍: `RetirementPlanner(cost_basis=)` → `WithdrawalAnalyzer(cost_basis=)` → `config_dict` → `TaxableSimulationRunner.run(carried_cost_basis=)` → `SimulationLoop.run(carried_cost_basis=)`.
- `SimulationLoop`: day-1 매수 직후 `_avg_costs`를 `carried_cost_basis/invested` 비례축소 → 인출 종료자산(gross)을 받아도 적립차익이 취득가에 반영됨. 위탁만 영향(ISA/연금은 `sell_with_tax`가 과세이연 → CG 0, 무해).
- **`wd_config`에 tax_engine·account_type·user_settings·current_age·accumulation_years·gain_harvesting 배선** (이게 누락이라 인출 면세였음 — 회귀 해소). cost_basis = 적립 총납입(결정론).
- 단일 `run_retirement_logic` + `app.py:retirement_run` 양쪽.

**검증 `tests/test_g5_withdrawal_basis.py`:** ① 거치(인출0)·평탄가격 종료청산 손계산 ±1원 — gross 12M·취득가 6M → 내재차익 6M×15.4% = **924,000** 정확(avg_cost 재조정이 청산 unrealized_gain에 반영). ② 인출경로(BUG-TAX-2 sell_with_tax) 방향성 — carried < no-basis(인출 매도차익 과세). 회귀 **119 PASS**(calculator/backtest 불변=carried_cost_basis default None).

⚠️ **C1 = 위탁 인출세 토대.** 연금 인출세(C2 `pension_separate_tax_annual` 배선)·멀티 가구 인출 오케스트레이터(C3)·합산 생존율(C4) 잔여. ⚠️ 단일 은퇴 tax-ON 결과 바뀜(면세→인출과세, 정확해지는 방향).

**▶ 다음 = C2 연금소득세 인출 배선.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-03] fix | BUG-TAX-3 은퇴 이중과세 — 적립 무청산 인계 (apply_final_liquidation 플래그)

**오너 지적:** "투자계산기는 단일·멀티 일괄청산 맞음. 근데 은퇴 계산기는 절대 일괄청산 금지." — 정당. 코드추적 결과 기존 버그 확인.

**BUG-TAX-3:** `TaxableSimulationRunner`·`MultiAccountSimulationLoop`이 `tax_enabled`면 시뮬 끝에 무조건 `apply_liquidation_tax`(연금/IRP→`after_tax_withdrawal` 5.5% 전액·위탁→미실현차익 15.4/22% 일괄청산). 독립 투자계산기엔 맞다(스냅샷). 근데 은퇴는 `AccumulationAnalyzer` 적립종료값 → `RetirementPlanner`(11분위 샘플) → `WithdrawalAnalyzer` 인출. 적립종료값이 **이미 세후**라 인출단계서 또 과세 → **연금=명백한 이중과세**(적립끝 5.5% + 인출 gross-up 또 5.5%), 위탁=비현실적 전액 일괄청산 후 인출기 재과세.

**수정(오너결정 b: 단일+멀티 전부):** `apply_final_liquidation` 플래그 신설 — `TaxableSimulationRunner.run`·`MultiAccountSimulationLoop.run`·`AccumulationAnalyzer`·`MultiAccountAnalyzer`에 통과(기본 True=투자계산기·백테 불변). False면 최종 `apply_liquidation_tax` 스킵→gross 반환, 적립기 중간세(배당·리밸)는 유지. **은퇴 적립 전 경로 False:** `retirement_logic.run_retirement_logic`(단일)+`_run_multi_account_retirement_logic`(멀티)+`app.py:retirement_run`(병렬 sync 구현).

**검증:** L11 `test_l11_no_final_liquidation_gross_handoff` 추가(거치 위탁 배당0·리밸none → 적립 세금이벤트 0 → 무청산이므로 tax ON 종료값 == OFF, 청산세 미부과 증명). 기존 골든도 `apply_final_liquidation=False`로 갱신. **L11 5종 PASS.** **calculator/backtest 회귀 91 PASS(default True 불변):** G5-A·TrackG·L-save·withdrawal-cg·gate2b·pension. test_retirement_simulation은 pytest 형식 아님(스크립트 smoke, "no tests ran").

⚠️ **위탁 적립차익 과세 누락 잔존:** 인계가 스칼라(`initial_capital` 숫자 1개)라 인출 시뮬이 그 값을 새 취득가로 시작 → 적립기 미실현차익이 인출까지 과세 안 됨. **정확한 위탁 인출 양도세 = 계좌별 포지션+취득가 인계 필요 = G5-C 핵심**(스칼라→포지션 인계 교체). 연금은 gross 인계로 정확(인출 시 연금세가 전액 기준).

**▶ 다음 = G5-C:** 취득가 포지션 인계 + 가구 인출 오케스트레이터(위탁→ISA→연금 세금최적) + 연금소득세 + 합산 생존율.

_작성: Claude (Opus 4.8)_

---

## [2026-06-03] feat | G5-B 은퇴 적립단계 멀티계좌 (엔진 + L11)

**오너 지시:** "엔진 전부 다 한 다음에 UI." → G5-A UI 건너뛰고 엔진 순서로 G5-B 착수. "적립은 투자계산기랑 거의 같은 엔진" — 맞음, `MultiAccountAnalyzer` 그대로 공유.

**구현:** `retirement_logic._run_multi_account_retirement_logic` 신규 — `_run_multi_account_calculator_logic`를 은퇴 데이터관례로 적응. 공통모듈(`_normalize_multi_accounts`·`_validate_initial_capital_limits`·`_build_savings_summary`) import, `years=accumulation_years`, 데이터준비=`prepare_scenario_data`(price_provenance 대신, 단일 retirement와 동일), 계좌별 규제검증·ISA 1억캡(transfers OFF)·transfers(정책/풍차/연금)·롤링 후 combined+계좌별 분포+savings+g2+split_sale+accumulation_summary surface. `run_retirement_logic` 디스패치: `len(accounts)>1`→멀티, 단일→기존경로.

**오너 Q&A 결정 (착수 전 4문):**
- **Q1 인출투영(생존율) = G5-C로 완전 연기.** 멀티 응답은 `withdrawal_pending=True`·`sample_results=[]`·`combined_summary=None`. 발견한 충돌: calculator는 인출 없어 단일→멀티 라우팅 무손실이나, **retirement 단일경로는 RetirementPlanner로 생존율 생성** → 인출-연기 멀티경로로 보내면 기존 생존율 사라짐(회귀). ∴ **단일→멀티 합성(savings 패널·단일풍차 자동미러)은 인출 완성(G5-C)까지 연기**, 단일계좌는 기존경로 그대로.
- **Q2 분기 = calculator 미러** (len>1).
- **Q3 ISA 풍차 = 멀티서 transfers로 허용** (MultiAccountAnalyzer 기존 지원).
- **Q4 pension_start_age = G5-C로 연기** (적립은 연금 과세이연이라 무관, 인출 나이별 세율에만 사용).

**검증 `tests/test_g5_retirement_accum.py` L11 5종 PASS:** ① 골든 래퍼=엔진직접호출 ±1원(엔진→Runner 동치는 calculator L0 보증 → 전이적으로 래퍼=엔진=Runner) ② 불변식 combined=Σaccounts ③ 평탄가격·거치·세금OFF→종료값=초기합 8,000,000 ④ 계단가격 세금ON<OFF ⑤ 인출 pending·디스패치(2↑멀티/1단일). 결정론: `prepare_scenario_data`·`price_loader.load`·`_get_dividend_start`·`loader.get_price` 패치. **회귀 80(G5-A+TrackG+L-save+withdrawal-cg) + retirement 11 PASS.**

⚠️ UI 미배선(엔진 단계 후 B). ⚠️ 멀티 retirement 인출 결과는 G5-C 전까지 pending.

**▶ 다음 엔진 = G5-C 은퇴 인출 멀티계좌(L12):** 가구 단일 인출액 → 오케스트레이터(위탁→ISA→연금 세금최적 순차소진) + 연금소득세(`pension_separate_tax_annual` 토대 완료) + 합산 생존율 + `MultiAccountAnalyzer` withdrawal_amount 확장.

_작성: Claude (Opus 4.8)_

---

## [2026-06-03] docs | 전체 문서 최신화 — 마스터로드맵·wiki 동기화 + 우선순위

오너 요청 — 누적 작업을 마스터플랜·wiki 전반에 반영, 신규 기능 추가·우선순위 부여.

- **PROJECT_MASTER_ROADMAP.md:** Last updated 2026-06-03. Source Plans 표에 신규 플랜 7개 추가(trackG/절세액표시/금데이터백필/간편계산기/세금계산기/리스크리턴도표) + 상태. Current Recommended Next Action 재작성 — **P0 Track G5(진행)** / P1 간편계산기·세금전환계산기 / P2 절세액 P2·P3·종합과세 전탭배선 / P3 PHASE4(즐겨찾기→리스크리턴). BUG-PENSION-1 곁가지 기록.
- **wiki/index.md:** 플랜 파일 표 갱신(상태 컬럼 + 신규 7개).
- **wiki/product/features.md:** 다중계좌·절세액표시·금현물거래·풍차·G3/G4 ✅ 추가. 종합과세 상태 갱신. 신규 계획 도구 섹션(간편/세금전환/리스크리턴 + 우선순위).
- **wiki/product/dev-status.md:** 요약·Phase 표·다음트랙 G5 기준 갱신(Stage A 재검증 최우선 → G5로 교체). 다음 명령어 = "G5-C 은퇴 인출 엔진 구현해줘".
- **wiki/dev/ideas.md:** 금데이터백필 ✅완료 주석.
- status.md(업데이트 38)·bugs.md(BUG-TAX-2/PENSION-1/G1-2)는 이번 세션 작업 시 이미 최신.

**우선순위 확정:** P0 G5 다중계좌 복제 → P1 간편/세금 도구 → P2 절세액 P2/P3·종합과세 → P3 PHASE4.

_작성: Claude (Opus 4.8)_

---

## [2026-06-03] fix | BUG-TAX-2 위탁 인출 매도 양도세 누락 + G5(백테스트·은퇴 복제) 플랜

**오너 지적:** "왜 위탁 인출 양도세가 없어?" — 정당. 코드 추적 결과 **기존 버그 확인.**

**BUG-TAX-2 (높음):** 은퇴 인출(세금ON) 위탁이 인출하며 판 매도차익에 양도세 미부과. 원인 = `TaxableSimulationRunner`가 인출에 평범한 `WithdrawalEngine` 사용→`portfolio.sell()` 직행(TaxedOrderExecutor 우회), `TaxTrackedPortfolio`는 `sell` 미오버라이드라 세션 미누적. 최종 `apply_liquidation_tax`는 남은 보유분만 과세 → 인출로 판 차익이 양도세·청산세 둘 다 빠짐. BUG-TAX-1(배당세 누락) 계열.

**수정:** `TaxedOrderExecutor.sell_with_tax(portfolio, ticker, qty, price)` 추출 — 리밸런싱·인출 매도 **공유**(단일 소스, 드리프트 방지). `execute_orders` 위탁 루프가 이걸 호출하도록 리팩터(동작 동일). `WithdrawalEngine.process(executor=)` 신규 인자 → 위탁 인출 매도를 sell_with_tax 경유(세션에 실현차익 누적→양도세+종합과세). `SimulationLoop`·`MultiAccountSimulationLoop`이 executor 전달. 세금OFF/평범 OrderExecutor면 `hasattr` 가드로 직접 매도 fallback.

**검증:** 신규 `tests/test_withdrawal_cg_tax.py` 2종 — 위탁 인출(상승분 실현) `total_cg_tax_paid>0`·ISA 인출 `=0`(과세이연). 회귀 73 PASS + krx_gold 5 + 신규 2. **반복 검증:** 결정론 sim(KR_FOREIGN 100→200, 월인출) tax OFF 13,000,000 vs ON 11,781,910(양도세 효과 1,218,090).
- ⚠️ **기존 은퇴 인출(위탁) 결과 바뀜** — 지금까지 과소과세였고 이제 정확(BUG-TAX-1 전례와 동일 성격).
- ⚠️ **gate2a (test_gate2a_runner_vs_legacy) 2종 실패는 별건** — stash 후 실행해도 동일 실패(40,913,520) → 내 변경 무관. BUG-TAX-1(5ca9a96 배당세 중앙화) 이후 PHASE1 레거시 상수 미갱신 stale golden. 범위 밖이라 미수정(추후 골든 재기록 필요).

**G5 플랜 (`trackG_multiaccount_plan.md` 추가):** 백테스트·은퇴 멀티계좌 복제 설계. 탭별 성격 차이(백테스트=단일 역사윈도우/은퇴=적립롤링+인출디큐뮬레이션). 결정: 인출순서 세금최적자동, 연금 1500만 개인합산 16.5% 분리과세 근사, 순서 백테스트→은퇴적립→BUG-TAX-2(완료)→은퇴인출. L10~L12 검증계층.

**▶ 다음 = G5-A 백테스트 멀티계좌(공통 모듈 추출 먼저).**

_작성: Claude (Opus 4.8)_

---

## [2026-06-03] fix | BUG-G1-2 다중계좌 입력 커서 유실 + deploy.yml divergent 복구

**① deploy.yml (BUG-DEPLOY 후속):** 금 Phase 2 커밋을 amend+force-push했더니 서버 `git pull`이 divergent로 실패(`Need to specify how to reconcile divergent branches`, exit 128) → 미배포. `git pull origin main` → `git fetch` + `git reset --hard origin/main`로 교체(서버를 origin 단일진실에 강제일치, force-push/divergent에도 복구). 런타임 DB는 gitignore라 reset 무영향. **교훈: push 후 amend+force-push 금지.**

**② BUG-G1-2 (중간, 미해결이던 것):** 투자계산기 다중계좌 2번째 계좌 입력 시 커서 사라짐. 원인 = `oninput` 핸들러가 매 키스트로크 `renderTaxAccounts()` 전체 재렌더 → 입력칸 재생성 → 포커스 유실. (업데이트 25는 우선순위 입력칸만 고쳤음.)
- `updateTaxAccountAmount`(초기투자금·월적립액): 재렌더 제거, `checkTaxLimits()`만 호출(연금/IRP 한도경고는 `taxWarnings`만 갱신, 입력칸 안 건드림).
- `onAccountTickerWeightChange`(종목 비중): 재렌더 제거, 비중합계 경고를 전용 `acctWeightWarn{idx}` div만 갱신(`accountWeightWarnHtml` 헬퍼 분리).
- 우선순위 입력은 이미 onchange+무재렌더라 안전(기존).
- JS 문법 OK. cache v20260603cursorfix. ⚠️ 브라우저 육안 스모크 미검증.

**▶ 투자계산기 잔여 버그 해소. 다음 = 백테스트/은퇴 탭 복제(이제 커서버그 복제 안 됨).**

_작성: Claude (Opus 4.8)_

---

## [2026-06-03] feat | 금 ETF 상장전 2차 백필 — 현물=KRX_GOLD·선물=GC=F 갈래 라우팅 (금 Phase 2)

**오너 스펙:** "금현물 말고 금선물 ETF도 같이 백필. 어차피 그게 그거." → 짚음: 현물≠선물(콘탱고/헤지 다름). 단 **우리 소스는 가격 레벨뿐**이라 콘탱고 드래그(롤오버 손실)는 안 보임 → 상장전 합성구간은 현물·선물 거의 동일, 진짜 차이는 상장후 실제가에 반영. → 둘 다 백필 OK(상장전은 근사, 모든 백필 공통한계).

**발견:** 모든 금 ETF가 `index=GOLD`→`GC=F`(USD 금선물)로 매핑돼 현물조차 GC=F로 백필 중이었음. `fx_applied`는 `market=="US"` 요구 → 금 ETF는 `market=COMMODITY`라 환율 미적용. **현물(unhedged)** ETF는 실제가=금(USD)×원화인데 GC=F 환율없이 백필 → 상장전 원화변동 누락(형태 부정확). **선물(H)** 은 헤지라 GC=F 맞음.

**오너 결정:** ① 갈래별 라우팅(현물/국제금 unhedged→KRX_GOLD KRW/g 네이티브, 선물H→GC=F) ② 순수 금만(레버리지·인버스·혼합·금광주·커버드콜 제외).

**구현:**
- `price_loader.py`: KRX_GOLD KRW/g 빌더를 모듈함수 `build_krx_gold_krw_series(index_conn, usdkrw)`로 추출(`_build_krx_gold_series`는 호출만) — backfill_engine과 공유, BUG-DIV-3 ratio 로직 중복방지.
- `backfill_engine.py`: `_GOLD_KRX_SPOT={411060,0072R0,0064K0,0066W0}` → index_code 오버라이드 KRX_GOLD. `_load_index("KRX_GOLD")`가 공유빌더로 1971~ 시계열 빌드. `KRX_GOLD`를 `_NO_DIVIDEND_INDICES`에 추가(금=무배당).
- 선물 3종(132030·319640·139320)은 GC=F 유지, 변경 없음.

**검증(로컬):**
- 현물 4종 proxy=KRX_GOLD·**1971-08-16부터**(50년+) · 선물 3종 proxy=GC=F. backfill_runs 확인.
- 상장경계 점프 전부 ±2.5% 이내(411060 −0.39%·0072R0 −2.49%(금 1일변동)·132030 +0.78% 등) — BUG-DIV-3 폭발 없음.
- 411060 1990~2026 9177행 로드 정상.
- test_krx_gold **5종 PASS**(라우팅+공유빌더 일치 2종 신규) + 회귀 71 PASS(save/track_g/multi_account/krx_gold).

**미배포·미검증:** 서버 배포 + 서버 금 ETF 백테스트 실데이터 검증 남음. price_daily.db는 gitignore라 코드만 배포→서버가 lazy 재백필(서버 index_daily KRX_GOLD+GC=F+USD/KRW 기존 보유).

**▶ 다음 = 서버 배포·검증 OR 백테스트/은퇴 복제 플랜.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-03] feat | KRX 금현물 거래가능 시계열 + 위탁 전용 (금 Phase 1, 서버검증 PASS)

**버그:** KRX_GOLD가 `index_master`(지수)에만 있고 `price_daily`(거래가격)엔 없어 위탁 시뮬이 'portfolio_value' 에러로 안 돌았음(5년 잡아도). 

**수정 (5cc4c1a+ec7cfa2):**
- `price_loader._build_krx_gold_series`: KRX_GOLD를 연속 KRW/g 시계열로 — 2014~ KRX 금현물 + 2014이전 GC=F(USD/oz)×USD/KRW를 2014 경계서 **ratio 규격화**(oz↔g·통화 단위차는 경계 ratio 흡수). `get_price('KRX_GOLD')` 단락(yfinance·백필·FX 미적용).
- 위탁 전용: `validate_account_portfolio`가 ISA/연금/IRP의 KRX_GOLD 거부.
- `_get_price_start(KRX_GOLD)` = 시계열 시작(price_daily 조회 None → data_start 과거 → 빈 윈도우 크래시 방지) + analyzer 빈 dates 윈도우 스킵.

**오너 결정:** 2014이전=GC=F×USD/KRW · 위탁전용=KRX_GOLD만(금현물ETF는 ISA가능) · ratio 규격화 · **Phase 1만**(금현물 ETF 2차백필은 다음).

**검증:**
- 로컬: 시계열 1971~2026·2014 경계 점프 0(47,592→46,950)·2024년 86,940원/g(실제 KRX금 일치)·위탁 시뮬 정상·금 양도세 0. `test_krx_gold` 3종 + L-SAVE26+TrackG41 PASS.
- **서버:** 위탁 KRX_GOLD 8년 작동(cases 72·금 비과세 savings 0·패널 숨김) · ISA+KRX_GOLD → account_restrictions 거부. **PASS.**

**▶ 다음 = 금현물 ETF 2차 백필(ACE금현물 등) — `금데이터백필_plan.md` Phase 2.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-03] feat | 단일 풍차 ISA 자동 위탁계좌 생성 (에러 대신 정상 시뮬)

오너 요청: 단일 풍차 ISA가 `isa_windmill_disabled` 에러로 막히는 게 UX 나쁨(시뮬은 도는데). 막지 말고 자동 처리.

- **구현 (2ae53c6):** `run_calculator_logic`이 단일 ISA+풍차면 **같은 종목·비중의 위탁계좌(초기0·월0)를 자동 생성** + `distribution_policy [ISA, 위탁]` 합성 → 멀티경로. 멀티 엔진이 만기 목돈을 ISA(연 2천만 한도)까지 재입금, 초과분은 위탁으로 라우팅 → 풍차 정상 작동. 응답 `windmill_auto_brokerage=True` → 결과창 파란 안내박스("ISA 해지 시 전액 재입금 불가(연 2,000만원 한도) → 초과분 위탁계좌 운용"). JS 캐시 v20260603windmill.
- **서버검증:** 단일 풍차 ISA 458730 12년 → 에러 없음·**만기 3회**·계좌 ISA+위탁 자동·절세 2,245,158(위탁가정 4,453,973−실제 2,208,815)·종료 3,677만(평범 ISA 3,363만보다↑, 합당).
- 회귀: L-SAVE 26 + Track G 41 PASS. JS 문법 OK.

**▶ 절세액 P1 + 단일계좌 지원(풍차 포함) 전부 완료. 다음 = 백테스트/은퇴 복제 플랜.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-03] fix | 분할매도 패널 멀티경로 복구 + 풍차 단일ISA 회귀 수정 (BUG-SAVE-1 후속)

BUG-SAVE-1 A안(단일→멀티 라우팅) 부작용 정리.

- **① 분할매도(split_sale_plan) 복구 (124f82f):** A 라우팅 후 위탁 단일계좌서 분할매도 패널·종합과세 플래그가 사라졌던 것 복구. `MultiAccountAnalyzer`가 케이스별 `kr_foreign_unrealized_gain`·`financial_income_by_year` surface → 멀티 logic이 `compute_split_sale_plan` 호출(단일경로와 동일). **서버검증:** 단일 위탁 458730 초기2천만 → split_sale gain 3,747만·최적 2년분할, 위탁 절세 0.
- **회귀 수정:** A가 풍차(isa_renewal) 단일 ISA도 멀티로 보내 distribution_policy 부재로 풍차 미작동(서버 maturity 0 확인). 라우팅을 **'非풍차일 때만 멀티'**로 한정 → 풍차 단일 ISA는 단일경로 유지.
- **풍차 단일 ISA = 의도된 동작:** 단일경로가 `isa_windmill_disabled` 안내("재가입 한도초과, 멀티계좌 쓰세요") 반환 — 금액 무관 항상(설계). 즉 풍차는 멀티계좌(ISA+위탁 수신) 필요.
- **② ISA 조기해지(distribution_early_cancel):** 단일 풍차 ISA가 항상 차단되므로 단일계좌서 **원래 도달 불가능한 경로** → 복구할 것 없음(A가 잃은 진짜 패널은 split_sale뿐, 복구 완료).

**검증:** 평범 단일 ISA savings 1,628,586 · 위탁 split_sale · 풍차단일 안내 — 서버 PASS. L-SAVE 26 + Track G 41 PASS.

_작성: Claude (Opus 4.8)_

---

## [2026-06-02] fix | BUG-SAVE-1 수정 — 단일계좌 절세액 표시 (A안, 서버검증 PASS)

**원인:** `run_calculator_logic`이 `len(accounts) > 1`일 때만 멀티경로(savings 산출). 계좌 1개면 단일경로(`AccumulationAnalyzer`)로 빠져 savings 미생성 → 절세 패널 안 뜸. 프론트는 단일계좌일 때 `accounts[]` 없이 legacy 필드(tickers/account_type 등) 전송.

**수정 (f909c69, A안):** 세금 ON 단일계좌면 legacy 필드로 `accounts[1]` 합성 후 `_run_multi_account_calculator_logic` 호출 → savings 생성. 세금 OFF는 기존 단일경로 유지(절세 무의미).

**서버검증:** 단일 ISA(458730, 1천만, 12년, hold) → 위탁가정 4,005,640·실제 2,377,054·**절세 1,628,586**. 종료자산 3,363만(위탁 3,200만보다 높음 — ISA 배당이연·낮은 청산세 우위, 합당).

⚠️ **부작용:** 단일계좌 세금ON 결과에서 **분할매도·ISA조기해지 분포 패널 미표시**(멀티경로엔 해당 필드 없음). JS 가드되어 에러는 없음. 필요 시 멀티경로에 추가 검토.

**▶ 절세액 P1 관련 버그 2개(TAX-1·SAVE-1) 모두 수정·서버검증 완료.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-02] fix | BUG-TAX-1 수정 — 단일경로 배당소득세 미부과 (서버검증 PASS)

**근본원인:** `DividendEngine`(base)이 GROSS 배당을 `portfolio.cash`에 입금하는데, 단일경로 `SimulationLoop`은 배당세를 cash에서 차감하는 코드가 없었음 → 배당이 사실상 미과세. 멀티경로(`multi_account_loop`)는 루프가 직접 `cash -= (gross-net)` 차감해서 정상이었음(그래서 `test_l3` 통과·발견 지연).

**인출 모드 추가의문도 동일 원인:** 인출 땐 base가 gross 입금 → 미차감 → `cash -= net`(withdraw)이라 cash에 `+tax` 잔류 → 그 잔류분이 청산세와 상쇄돼 시세차익마저 과소로 보였음.

**수정 (5ca9a96):** `TaxedDividendEngine.process`가 세금(gross−net)을 `portfolio.cash`에서 직접 차감하도록 중앙화(단일·멀티 일관). 멀티의 외부 차감 라인은 이중차감 방지 위해 제거(보고용 `dividend_tax_paid`는 유지).

**서버검증 (배포 후 458730·초기1천만·12년·위탁):**
| 모드 | 버그 전 | 수정 후 | 이론값 |
|---|---|---|---|
| 보유 | 3,312만 | **3,200.5만** | 3,200만 ✓ |
| 인출 | 2,754만 | **2,584.7만** | 2,586만 ✓ |
| 재투자 | 3,846만 | 3,620만 | (복리) |

보유·인출 **손계산 이론값과 일치.** 회귀 `test_bug_tax1_single_path_dividend_taxed_{hold,reinvest}` 추가. L-SAVE 26 + Track G 41 + gate2c 4 PASS.

⚠️ **영향범위:** 단일계좌 투자계산기·백테스트의 **배당 실린 종목 위탁/ISA 결과가 바뀜**(이제 정확히 더 낮음). 기존 결과 신뢰 못함 — 재계산 필요.

**▶ 남은 것 = BUG-SAVE-1 (단일계좌 절세 패널 미표시).**

_작성: Claude (Opus 4.8)_

---

## [2026-06-02] bug | 위탁 계좌 세금 과소부과 발견 (BUG-TAX-1) + 단일계좌 절세 미표시 (BUG-SAVE-1)

브라우저 검증 중 오너 발견. **수정 전 데이터·분석 기록**(요청).

### 공통 조건
투자계산기, 종목 **458730 100%**, 초기자본 1,000만, 월납입 0, 투자기간 12년. (롤링 중앙값 p50)

### BUG-TAX-1 — 위탁 세금이 이론(15.4%)보다 적게 떼임

| 배당 모드 | 무세금 | 위탁(세금ON) | 실제세금 | 총수익 | 실효율 | 이론값 |
|---|---|---|---|---|---|---|
| 재투자(reinvest) | 4,251만 | 3,846만 | 405만 | 3,251만 | 12.5% | (복리라 계산난) |
| **현금보유(hold)** | 3,601만 | 3,312만 | **289만** | 2,601만 | **11.1%** | **400만 (3,200만)** |
| 인출(withdraw) | 2,874만 | 2,754만 | 120만 | 1,874만 | 6.4% | — |

**핵심 단서 = hold 모드(가장 깨끗, 복리 손실 없음):**
- 이론: 시세차익+배당 모두 15.4% → 2,601만 × 0.154 = **400만** 세금 → 세후 3,200만 (오너 이론값과 일치).
- 실제: 289만만 떼임 → **누락 111만 ≈ 배당분 × 15.4%** (배당현금 ~725만 × 0.154 ≈ 111만).
- ⇒ **배당소득세(15.4%)가 위탁에서 미부과 강하게 시사.** 시세차익(양도세)만 떼이는 듯.

**모드별 패턴:** 배당이 많이 "분리"될수록 실효율↓ (재투자 12.5 > 보유 11.1 > 인출 6.4).
배당세 누락 가설과 방향 일치(재투자는 배당이 포지션에 남아 시세차익으로 과세, 보유/인출은 배당 분리→미과세).

**남은 의문:** 인출 모드 실효율 6.4%는 시세차익(배당 제거됐으니 전액 시세차익)마저 15.4% 미만 → **인출 모드는 배당세 누락 외 추가 원인 존재**(시세차익 청산세도 과소?). per-window(run_id 40) 매칭 확인 = 6.34%, 중앙값 함정 아님(실제 현상).

**검증 단서:** 멀티경로(`MultiAccountSimulationLoop`)는 배당세 부과됨(`test_l3`: 위탁 458730 배당 10원→세금 15.4 = 15.4%). → **버그는 단일경로(`TaxableSimulationRunner`) 또는 두 경로 차이 의심.** 다음: 단일경로 배당세·청산세 흐름 추적.

### BUG-SAVE-1 — 절세 패널이 단일계좌(1개)에서 안 뜸
- `run_calculator_logic:555` `if len(accounts) > 1`일 때만 멀티경로(savings 산출). 계좌 1개면 단일경로 → savings 미생성 → 절세 패널 미표시.
- 절세 P1을 멀티경로에만 배선한 구현 갭. 단일계좌도 지원 필요.

### ▶ 다음
1. BUG-TAX-1 코드 추적·수정 (배당세 누락 + 인출 모드 추가원인). **최우선.**
2. BUG-SAVE-1 단일계좌 절세 배선.
※ BUG-TAX-1이 "실제세금"을 틀리게 하면 절세액(=위탁가정−실제)도 틀림 → BUG-TAX-1 먼저.

_작성: Claude (Opus 4.8)_

---

## [2026-06-02] feat | 절세액 표시 P1 (투자계산기) — 3종 표시 풀스택

`절세액표시_plan.md` P1 구현 완료. 결과 화면에 **위탁가정세금·실제세금·절세액** 3종(계좌별 + 합산).

### 오너 결정 (구현 전 확정)
- 연금/IRP **인출세는 은퇴 탭(P3)만** 적용 — 투자계산기·백테스트·배당금엔 미적용.
  → 이 탭 연금/IRP 절세액 = 적립기 위탁가정세금(배당+종료시 미실현차익), 실제=0.
- 기준값·표시 = **p50(중앙값) 단독**. **합산 = 계좌별 p50의 단순합**(화면 일치).
- (P3 전용) 연금 인출세 베이스 = 수익+세액공제원금, 3.3~5.5%+1500만초과 16.5%, 한도증가 무시.

### 구현
- **`modules/tax/saving_estimate.py`** 신규 — 순수함수 `estimate_brokerage_tax(배당by클래스, KRF차익, US차익by연도)`. 배당율 KR_FOREIGN/국내 15.4%·US 15%·금 0%, 양도 KRF 15.4%·US 250만공제후 22%·국내/금 0%.
- **`order_executor.py`** — `_accrue_brokerage_gain`: 계좌유형 무관 매도 실현차익 누적(`_brk_krf_gain`=이익분만, `_brk_us_by_year`=손익통산 연도별). GH 절세매도는 기준리셋이라 **미누적**(최종 미실현만 과세 → 위탁 절세 0 불변식 유지, L-SAVE3로 검증).
- **`multi_account_loop.py`** — 배당 자산분류별 누적(`cf_gross_div_by_class`) + 풍차만기·최종청산 미실현차익 누적 + finalize에서 `brokerage_assumed_tax`/`tax_saving=max(0,위탁가정−실제)`.
- **`multi_account_analyzer.py`** — 케이스별 surfacing + `_build_savings`(계좌별 p50 + 합산).
- **`calculator_logic.py`** — 응답 `savings`. **`static/js/calculator.js`** — 멀티계좌 요약에 절세 3종 패널(근사치·연금인출세 은퇴탭 안내).

### 4번째 숫자 — GH 절세 (오너 추가요청)
- "절세매도(GH)로 아낀 세금"도 **별도 표시** 요청. 기존 3종 절세액 = **껍데기(ISA/연금) 효과**라 위탁+GH 계좌는 0(불변식). GH 효과는 안 잡힘 → 4번째 숫자로 분리.
- `GH 절세 = (GH 안 했으면 US양도세) − (실제)`. 방법 A 분석근사: harvest로 실현·기준리셋한 누적차익(`_brk_us_harvested_total`)을 "GH 없었으면 최종 단일실현(250만 1회 공제)" 가정으로 되돌려 계산. `estimate_gain_harvest_saving`.
- **위탁+GH ON 전용** — 그 외 0 → UI 자동 숨김. `static/js/calculator.js`에 주황 박스.

### 오너 결정 2 — 연금/IRP 청산세 (현행 유지)
- 코드 확인: 투자계산기·백테스트 연금/IRP 최종청산은 `after_tax_withdrawal` 연금경로로 **이미 5.5%(나이무관 55세율) 전액 과세** 중(×0.945). → **현행 유지** 결정. 실제세금에 5.5% 포함, 절세액=위탁가정−(5.5%+기타). 종료자산 표시와 일관.

### 검증 (`tests/test_l_save.py` **24종 PASS**)
- L-SAVE0~8 + 3b(GH) + 4(연금/IRP) + DCA·재투자·다종목·종합과세가산·analyzer풍차·logic매핑.
- **손계산 ±1원:** 순수함수·ISA단일(858,000)·**풍차2사이클(2,830,168)**·GH절세(550,000)·**연금/IRP(550,000)**.
- **불변식:** 위탁 절세 0 (DCA·재투자·다종목·종합과세가산 모두 — 위탁가정==실제, 가산 케이스는 0하한으로 0).
- **배선:** 합산=Σ계좌·p50=median·풍차+transfers analyzer surfacing·`_build_savings_summary` 라운딩/None.
- Track G 41 회귀 PASS. 변경 모듈 import·JS 문법 OK.

### 배포 + 서버검증 (PASS, 03f28cb)
- push→GitHub Action→Hetzner 배포 완료. 서버 `?v=20260602save` JS 서빙 확인.
- `/api/calculator/run` 실데이터(458730 KR_FOREIGN, 5년 롤링, ISA+위탁 세금ON) → `savings` 반환:
  ISA 위탁가정 1,320,200·실제 650,700·**절세 669,500** / 위탁 1,302,825==1,302,825·**절세 0**(불변식 실데이터 원단위 일치) / 합산 절세 669,500=Σ계좌·위탁가정 2,623,025=Σ. **end-to-end PASS.**
- ⚠️ 유일 미검증 = 브라우저 패널 육안 렌더(JS 문법만 통과).

**▶ 다음 = 백테스트/은퇴 복제 플랜 작성 → P2/P3.**

_작성: Claude (Opus 4.8)_

---

## [2026-06-02] 세션 종료 요약 | Track G2 풀스택 + 절세액 계획

이번 세션(2026-06-01~02) 대량 진척. 상세는 아래 개별 항목들 참조.

**완료:**
- **엔진(L0~L9 결정론):** 2-2 만기분배(L5/L5b) · G3 연금이전공제(L6) · 2-4 금종세 풍차중단+공유세션 멀티배선(L5c) · G4 연납입공제(L8) · B1 logic 관통(L9). 죽은 v1(`multi_account.py`) 삭제.
- **배선/UI:** B1(analyzer+calculator_logic) · B2(API 서버검증, 실데이터 g2) · B3(투자계산기 UI: 계좌별 우선순위·ISA풍차토글·재투자토글·금종세 자동판정·결과 g2패널).
- **부수 수정:** BUG-DEPLOY-1(배포 무력화, index_master 추적+deploy.yml) · index_master 서버손상 복구(37코드 재수집) · ISA 연한도 하드거부 스킵 · 연금/IRP 합산초과 라우팅 · 초기자본 한도=에러 통일 · BUG-INF-1(Infinity JSON) · 마지막달 풍차 잔재 · 단일 연금/IRP 한도에러.
- 브라우저 스모크 ①②③⑦ 정상. 전체 스위트 **111 PASS**. 가이드 `smoketestguide.md`.

**계획 작성(미착수):** `절세액표시_plan.md` — 위탁가정세금·실제세금·절세액 3종 표시. 분석적 추정(러프), L-SAVE0~8 검증설계(풍차누적·절세매도·기준값p50 포함). KRX금 0%·ISA풍차 트래킹·GH 연도별 공제 반영.

**▶ 다음 세션 = (A) 절세액 P1(투자계산기) OR (B) G2 탭 복제(백테스트→은퇴+1500만 한도)+L7.** 곁가지: KQ150 티커·deploy.yml 정리·데이터 갭채움·배당금계산기.

_작성: Claude (Opus 4.8)_

---

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
