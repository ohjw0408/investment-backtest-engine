---
updated: 2026-05-29
tags: [dev, bug]
---

# 버그 목록

**에이전트: 버그 발견 시 여기에 추가. 수정 시 상태 업데이트.**

형식: `| 버그 | 원인 | 파일 | 날짜:커밋 | 상태 |`

---

## 활성 버그 목록

> updated: 2026-05-31

| # | 버그 | 원인 | 파일 | 상태 |
|---|---|---|---|---|
| BUG-1 | TF1/TF6/TF7 — 에러가 인라인 배너 대신 alert() 팝업으로 표시 | `pollTask` FAILURE 시 `_e._data` 미설정 or null → catch에서 `_handled=false` → `alert()` fallback | `static/js/calculator.js` (pollTask), `retirement.html` 에러 핸들링 없음 | ✅ 수정 (f35a611) |
| BUG-2 | retirement.html — 에러/캡 배너 3종 미존재 | TF6/TF7(retirement 페이지) 에러가 모두 팝업으로 표시됨. ISA 캡 경고도 없음 | `templates/retirement.html`, 대응 JS | ✅ 확인 — 배너 이미 존재, BUG-1 fix로 함께 해결 |
| BUG-3 | 연금 수령 시작 나이 입력 불가 | 은퇴 계산기에 "연금 수령 시작 나이" 입력칸 없음. `user_settings.age`(현재 나이) 사용 중 | `templates/retirement.html`, `retirement_logic.py`, `modules/tax/liquidation.py` | ✅ 수정 완료 |
| BUG-4 | ISA 1억 캡 로직 오류 — 월 납입금 균등 축소 | 전 기간 월납입을 줄이는 방식. 올바른 동작: 납입 지속 → 1억 도달 시점부터 납입 0원 | `calculator_logic.py`, `retirement_logic.py`, `modules/retirement/accumulation_analyzer.py`, `static/js/calculator.js` | ✅ 수정 (7dd75a4) |
| BUG-5 | 밴드 슬라이더 숫자 직접 입력 불가 | 슬라이더만 있고 0.5% 단위 정밀 입력 불가 | `templates/myassets.html` | ✅ 수정 완료 |
| BUG-G1-2 | Track G 다중계좌 2번째 계좌 입력 커서 사라짐 | 입력 중 `renderTaxAccounts()` 전체 재렌더 → 포커스 유실 (BUG-6 패턴) | `static/js/calculator.js` | ✅ 수정 (2026-06-03): `updateTaxAccountAmount`(초기/월적립 oninput)·`onAccountTickerWeightChange`(비중 oninput)가 전체 재렌더하던 것 제거. 금액→`checkTaxLimits()`만(한도경고 유지), 비중→전용 `acctWeightWarn{idx}` div만 갱신(`accountWeightWarnHtml` 분리). 입력칸 비재생성→커서 유지. JS 문법 OK. cache v20260603cursorfix. ⚠️브라우저 육안 미검증 |
| BUG-DIV-1 | 배당금 계산기 역산 SCHD≠458730 (구 4x 차이) | ① `_find_real_data_start()` 배당간격 휴리스틱이 월배당 ETF(458730)를 synthetic 경로로, 분기배당(SCHD)을 백필 실롤링 경로로 분기시킴. ② `_run_rolling` all-or-nothing — 실 케이스<30이면 실데이터 버리고 가상 30개로 교체 | `modules/dividend_simulator.py` (`_find_real_data_start`/`_run_rolling`) | ✅ 수정 완료 (97ac6ab + cfdd151): 휴리스틱→`volume>0` 결정값 교체(4/4 OK), 롤링 3단 폴백(실측 유지+부족분만 가상). 역산 4x→1.05x 수렴. cfdd151=mock loader conn 가드(회귀수정). 회귀 6/6 PASS, HTTP 200 (Claude) |
| BUG-DIV-2 | 배당 계산기 슬라이더 라벨/위치/계산 불일치 (라벨 50%인데 90% 동작) | `dtRestoreForm`이 stale localStorage(이전 90% 결과) 복원 시 슬라이더 value만 세팅하고 라벨 미갱신(input 이벤트 미발생) | `templates/dividend_target.html` | ✅ 수정 (06bd19f): 복원 시 라벨 수동 동기화 (Claude) |
| BUG-DIV-3 | 투자계산기 가상보충 시 가격 폭발 (CAGR 860억배) | 합성 prefix anchor를 raw price_daily(USD)로 잡았는데 실 suffix는 `get_price`(USD ETF→KRW ×환율 ~1181) → 2003 경계에서 1181배 점프 | `modules/retirement/synthetic_price_generator.py` (`build_window_synth_params`) | ✅ 수정 (4f.. anchor를 get_price(FX)로 산출, 7af4c05까지): end_value 정상 검증 (Claude) |
| BUG-MAA-1 | MultiAccountAnalyzer `cagr` 필드 garbage (1e10 수준) | `cagr=(final/positive_cf)**(1/years)-1`에서 positive_cf 비정상(초기금만·월납0 시) 추정. use_synthetic 무관(기존). 분포는 `end_value` 사용이라 화면 무영향 | `modules/retirement/multi_account_analyzer.py` | ⚠️ 미해결(낮음) — 화면 영향 없음, 추후 확인 (Claude) |
| BUG-INF-1 | 멀티계좌 결과 JSON에 Infinity → 클라 "Unexpected token I ... not valid JSON" | 만기 internal 이동만 받는 계좌(초기0·월0 위탁)는 외부 cash_flow=0 → IRR(mwr) 발산 → cagr=inf → 분포 mean inf → jsonify가 Infinity 출력(유효 JSON 아님) → JSON.parse 깨짐. 브라우저 스모크 테스트①②서 발견 | `modules/retirement/multi_account_analyzer.py` | ✅ 수정 (90053b7 다음): mwr/cagr 비유한 가드(→0) + _fit_distribution v 비유한 제거. 회귀 `test_l9_no_infinity_in_result`(strict JSON). (Claude) |
| BUG-DEPLOY-1 | 자동배포 무력화 — Action success인데 코드 미반영 | `data/meta/index_master.db` 추적됨 + 서버 런타임이 씀 → `git pull` abort. deploy.yml이 pull 실패 미체크(systemctl is-active만 봄)라 success 오판. 오늘 커밋 전부 미배포였음 | `.github/workflows/deploy.yml`, `data/meta/index_master.db` | ✅ 수정 (d581cc3): git rm --cached DB + deploy.yml set -e + pull 전 git checkout. 배포·B2 서버검증 PASS (Claude) |
| BUG-TAX-1 | **위탁 계좌 세금 과소부과** — 배당 실린 종목이 이론(15.4%)보다 적게 떼임 | `DividendEngine`(base)이 GROSS를 cash 입금하나 단일경로 `SimulationLoop`이 배당세 미차감 → 배당 사실상 미과세. 인출 모드는 미차감세가 cash 잔류→청산세와 상쇄(시세차익까지 과소로 보임, 동일 원인). 멀티경로는 루프가 직접 차감해 정상 | `modules/tax/account_tax.py`(TaxedDividendEngine) | ✅ 수정 (5ca9a96): `TaxedDividendEngine.process`가 배당세 차감 중앙화 + 멀티 이중차감 제거. **서버검증 PASS** — 보유 3200만·인출 2585만(이론 일치). 회귀 2종 추가 (Claude) |
| BUG-PENSION-1 | 단일계좌 은퇴 인출 연금소득세 1500만 초과 처리 = 하이브리드(저율+초과분 16.5%) | `pension_monthly_after_tax`가 1500만 이하 저율 + 초과분만 16.5%로 계산. 현행법(선택분리과세)은 1500만 초과 시 **전액** 16.5%라 과소과세 가능 | `modules/tax/base_tax.py`, `modules/retirement/withdrawal_analyzer.py` | ✅ 수정 (2026-06-03, G5-C C2): 인출 경로(`_calc_gross_withdrawal` gross-up + `_calc_pension_tax_by_age` 표시)를 하이브리드 `pension_effective_rate` → `pension_separate_tax_annual`(전액 16.5%)로 교체. 검증 `test_g5_pension_withdrawal_wiring`(나이별 3.3~5.5%·1500만 초과 전액16.5% 나이무관). ⚠️하이브리드 함수군(`pension_monthly_after_tax`/`pension_annual_tax`/`pension_effective_rate`/`_pension_excess_rate`)은 이제 프로덕션 미사용(미삭제 — pre-existing 공개 API, 추후 정리 가능). run_withdrawal_logic·retirement 인출 연금 결과 바뀜(과소→정확) |
| BUG-TAX-2 | **위탁/ISA 인출 매도 양도세 누락** — 은퇴 인출(세금ON) 위탁이 인출하며 판 매도차익에 양도세 안 뗌 | `TaxableSimulationRunner`가 인출에 평범한 `WithdrawalEngine` 사용 → `portfolio.sell()` 직행(TaxedOrderExecutor 우회). `TaxTrackedPortfolio`는 `sell` 미오버라이드라 세션에 실현차익 미누적. 최종 `apply_liquidation_tax`는 남은 보유분만 과세 → 인출로 판 차익은 양도세·청산세 둘 다 빠짐. `_calc_gross_withdrawal:503` "위탁/ISA 인출 중 CG세 없음"이 잘못된 가정 | `modules/execution/order_executor.py`, `modules/simulation/withdrawal_engine.py`, `simulation_loop.py`, `multi_account_loop.py` | ✅ 수정 (2026-06-03): `TaxedOrderExecutor.sell_with_tax` 추출(리밸런싱·인출 매도 공유 — 단일 소스). `WithdrawalEngine.process(executor=)` 받아 위탁 인출 매도를 sell_with_tax 경유→양도세·종합과세 세션 누적. 루프 2곳이 executor 전달(세금OFF/평범 executor면 fallback). 검증 `test_withdrawal_cg_tax`(위탁 total_cg_tax_paid>0·ISA=0). 회귀 73 PASS(`sell_with_tax` 추출은 동작 동일). ⚠️기존 은퇴 인출(위탁) 결과 바뀜(과소→정확). ⚠️gate2a는 별건 stale golden(BUG-TAX-1 이후 미갱신, 내 변경과 무관 확인) |
| BUG-TAX-3 | **은퇴 세금 모델 = 적립끝 일괄과세 → 인출 과세로 교체** (⚠️초기 "이중과세" 진단은 부정확 — 정정) | **정정된 실태:** `run_retirement_logic`/`app.py:retirement_run`의 `wd_config`엔 `tax_engine`이 **없어 인출투영이 원래 면세**였음. 즉 적립끝 청산세(연금 5.5%·위탁 청산)가 **유일 세금**(이중과세 아님 — 인출 면세). 오너 규칙 "은퇴 절대 일괄청산 금지" = 적립끝 청산 제거 + **인출 시 과세로 이전.** 단 적립 청산만 제거하면(전반부) 인출 미배선이라 **세금 0 회귀** → 인출 과세 배선(C1)이 필수 후반부 | `modules/simulation/{taxable_runner,multi_account_loop,simulation_loop}.py`, `modules/retirement/{accumulation_analyzer,multi_account_analyzer,withdrawal_analyzer,retirement_planner}.py`, `retirement_logic.py`, `app.py` | ✅ 수정 (2026-06-03, 오너결정, 2단계): **①무청산** `apply_final_liquidation` 플래그(기본 True=계산기·백테 불변), 은퇴 적립 전경로 False → gross 인계. **②인출 과세 배선(G5-C C1)** `carried_cost_basis`(=적립 총납입) 플러밍 RetirementPlanner→WithdrawalAnalyzer→Runner→SimulationLoop, day-1 매수 직후 avg_cost 비례축소 → 위탁 인출 매도가 적립차익 과세. `wd_config`에 tax_engine·account_type·user_settings 배선(인출 과세 켜기, 면세 회귀 해소). 검증 `test_g5_withdrawal_basis`(거치 종료청산 손계산 ±1원=924,000·인출경로 방향성) + `test_l11_no_final_liquidation_gross_handoff`. 회귀 119 PASS. ⚠️연금 인출세는 C2(`pension_separate_tax_annual` 배선)·멀티 가구 오케스트레이터는 C3/C4 잔여 |
| BUG-SAVE-1 | 절세액 패널 단일계좌(1개)에서 미표시 | `run_calculator_logic`이 `len(accounts) > 1`일 때만 멀티경로(savings 산출). 계좌 1개면 단일경로(`AccumulationAnalyzer`)로 빠져 savings 미생성 | `calculator_logic.py` | ✅ 수정 (f909c69+124f82f, A안): 세금ON·非풍차 단일계좌를 멀티경로로. 분할매도 패널 멀티경로 복구(analyzer가 kr_foreign_gain·금융소득 surface). 풍차 단일은 단일경로 유지(회귀방지). **서버검증 PASS**(단일 ISA 절세 1,628,586·위탁 split_sale gain 3747만·풍차단일=의도된 멀티계좌 안내). early_cancel은 단일계좌서 원래 도달불가(풍차단일 차단)라 무관. (Claude) |
| BUG-WD-1 | **은퇴 인출 ~2배 과소인출** (현금흐름 버그, 세금 아님) — 단일 은퇴 생존율 과대평가 | `WithdrawalEngine.process` 매도 경로가 `needed`만큼 매도해 proceeds를 cash에 가산하나 **인출액을 cash에서 빼지 않음** → 매도월엔 자산→cash 이동만(실제 유출 0), 다음달 주차 cash 소비로 충당 → 격월로만 유출 → 유효 인출률 ≈ 50%. 단일·멀티 인출 모두 이 원시함수 사용 | `modules/simulation/withdrawal_engine.py` | ✅ 수정 (2026-06-04, C3 전 발견): 매도 루프 후 `portfolio.cash = max(0, cash - outflow_from_sales)`로 인출분 실제 유출(CG세는 sell_with_tax 별도 차감 — net+세금 둘 다 유출 정확). 재현 테스트 `test_bug_wd1_withdrawal_outflow`(평탄가격 12개월×1000=정확12000·기존cash우선·인플레이션 Σ·고갈0바닥). 회귀 184 PASS(은퇴 테스트는 불변식 기반이라 절대 생존율 골든 없음 → 자동 그린). ⚠️기존 단일 은퇴 생존율 바뀜(과대→정확, 하락 방향) |
| BUG-CALC-40Y | **투자계산기 장기(30·40년) 시뮬 실패** — 가상데이터 체크해도 "가상 데이터 생성 불가: 실제 데이터가 너무 적습니다" 에러. 20년은 정상. (오너 발견, 2026-06-04) | **증상:** QQQ+GLD+SCHD 포트, `use_synthetic=True`인데 40년·30년 실패, 20년 작동. **에러 출처 확정:** `calculator_logic.py:268`(멀티) / 대응 단일경로 — `prepare_scenario_data`가 **`n_cases == 0`** 반환 시 발생(`"가상 데이터 생성 불가: {tickers}의 실제 데이터가 너무 적습니다 (최소 1년 필요)..."`). 합성 경로(`allow_synthetic=True`)는 `DataPreparer.prepare`→`_calc_rolling_cases`로 윈도우 수 산출. **로컬 재현 안 됨(핵심 단서):** 로컬 DB는 QQQ 1971~2026·GLD 1971~2020·SCHD 1928~2026까지 **이미 백필**돼 40년 `prepare_scenario_data`가 n_cases=60 정상 반환(에러 없음). **`price_daily.db`는 gitignore라 서버 DB가 로컬과 다름** — 서버는 lazy backfill이라 QQQ/GLD/SCHD history가 얕을 가능성(실제 상장 GLD 2004·SCHD 2011). 40/30년 윈도우엔 합성 백필 필요한데 서버에서 그 생성이 실패해 `n_cases=0` → 에러. 20년은 실데이터로 충분 → 작동(오너 "20부터 된다"와 정합). ⚠️ **추가 발견:** 로컬 GLD 실데이터가 **2020-12-30에서 끝남**(2021~2026 누락, stale 다운로드) — 별도 데이터 갱신 필요. | `modules/retirement/data_preparer.py`(3a 백필 ok 분기) | ✅ **수정 (2026-06-05, 서버 DB 실측으로 원인 확정).** **확정 원인:** 서버 `price_daily` 상태 = QQQ 1928~(deep)·GLD 2004 real+synth 1971~·**SCHD real 2003~**(인덱스 프록시 백필이 2003까지만 닿음). SCHD가 binding. DataPreparer 3단계 보완에서 `BackfillEngine.backfill("SCHD")`가 "이미 백필됨(21,046행) → 스킵"으로 **status=='ok'** 반환 → `if status=='ok': ... continue`가 **합성 생성을 건너뜀** → SCHD가 2003에 갇힘 → effective_start=2003. **40년:** 2003+40>2026 → n_cases=**0** → 에러. **20년:** 2003+20≤2026 → n_cases=11(>0 통과). 비대칭=순전히 n_cases==0 임계값(코드/데이터 자체 정상, sim_years 무관). **수정:** 백필 ok라도 `new_start > 목표(_min_target)`면 `continue` 대신 합성 생성으로 폴스루(잔여 구간 보충). **서버 DB 복사본(288M) 실측 검증:** 수정전 40y n_cases=0 → 수정후 **40y=61·30y=61·20y=60**(SCHD 1991/1981/1971까지 합성 보충). 20년도 11→60으로 개선(회귀 아님). 회귀 `tests/test_scenario_data_preparer.py::TestBackfillOkShallowFallsThroughToSynthetic` 2종(백필 ok-skip→합성 폴스루·단기 무영향). ⚠️ **GLD stale(로컬 2020 종료)는 별개 데이터 갱신 과제로 잔존**(서버 GLD는 2026까지 정상). **C3와 무관.** (Claude) |

**이전 "활성"에서 해결된 항목들:**

| 버그 | 상태 |
|---|---|
| DJUSDIV100 데이터 부족 | ✅ DJUSDIV_PROXY 체인으로 해결 (7b1dc6f) |
| `_fetch_fred()` 미정의 | ✅ def 선언 추가 (e1a4d6e) |
| 백필 실패 코드가 완료 처리됨 | ✅ _backfill_skip_codes 분리 (a761750) |
| 배당 시뮬 미완료 연도 포함 | ✅ complete_div 필터 추가 (ec56455) |

---

## 수정 완료 버그 목록

| 버그 | 수정 내용 | 날짜 | 커밋 |
|---|---|---|---|
| 절세매도 체크박스 오류 | 비용공제, 12월 분리에서 분리 실행 | ~2026-05 | ✅ |
| 청산세 근사 오류 | 정확한 계산으로 공통화, 통일 | ~2026-05 | ✅ |
| KR_FOREIGN 손익통산 | 개별 15.4% 분리과세 처리 | ~2026-05 | ✅ |
| US_DIRECT 리밸 손실 오류 | `_ytd_us_gains`에 리밸 손실 반영, 손익통산 수정 | ~2026-05 | ✅ |
| 9.4억 폭증 버그 | 0%/짧은 히스토리 ETF 통계 왜곡 수정 | ~2026-05 | fed40a4 |
| 5년 역전 버그 | 로지스틱 적용, bracket 이분탐색으로 변경 | ~2026-05 | db590a0 |
| 배당금 계산기 개형 볼록함 | step 단위 narrowing 후 이분탐색 | ~2026-05 | 6a1191d |
| pykrx fallback 혼선 | pykrx 제거, yfinance 단일화 | ~2026-05 | cfeb217 |
| KRX 금현물 홈 가격 stale | 서버 API 키 누락 + Redis `mq:krx_gold` 캐시 미무효화. 키 업로드, 15일 fallback, 다회 Beat, 저장 후 캐시 삭제로 보강 | 2026-05-28 | ✅ 진행/배포 대기 (Codex) |
| 지수 `download_all()` stale | 기존 행이 하나라도 있으면 최신 누락 구간을 스킵 | 2026-05-28 | ✅ `get()` 기반 누락 구간 보강으로 수정 (Codex) |
| 투자 계산기 T1 — 479080 `float(None)` | 서버 DB에 2025-11-13 배당 이벤트 row(`close=NULL`) 존재. 현재 코드는 NULL 필터가 있어 정상이나, systemd worker 외 수동 Celery worker가 함께 떠 stale worker가 큐를 소비할 수 있던 상태 | 2026-05-29 | ✅ 수동 worker 종료, 479080 `/api/calculator/submit` synthetic ON PASS (`cases_count=61`) |
| 백테스트 T2 — `Object of type bool is not JSON serializable` | `split_sale_plan.over_threshold`가 `numpy.float64` 비교 결과인 `numpy.bool_`로 반환되어 Celery 결과 JSON 저장 실패 | 2026-05-29 | ✅ `bool(...)` 캐스팅, 서버 배포, 458730 `/api/backtest/submit` 과세 ON PASS |
| 백테스트 T2 — 기존 금융소득 미반영/세후금액 미표시 | `backtest_logic.py`가 분할매도 계획 호출 시 `other_financial_income=0.0` 고정. 결과에는 세금만 있고 세후 이익 필드가 없었음 | 2026-05-29 | ✅ `other_financial_income` 입력/저장/전달, 일괄·분할·최적 세후 이익 반환/표시 |
| Track G G1 — 다중 계좌 배당세 단위 테스트 | 신규 `MultiAccountSimulationLoop`에서 위탁 계좌 배당세가 현금 잔액에 반영되어야 L3 손계산과 일치. 공통 `TaxedDividendEngine` 전역 수정은 기존 Gate 2a 골든 회귀를 깨서 제외 | 2026-05-30 | ✅ 다중 계좌 루프 내부에서 gross-net 차이를 현금 차감, L3 PASS (Codex) |
| BUG-G1-1 — 배당 지표 0 | 다중계좌 문제가 아니라 데이터 레이어 문제. DJUSDIV_PROXY total-return 체인 + 백필 구간 배당 row 부재 | 2026-05-30 | ✅ Stage A 서버 적용 완료: price-return proxy 재구축, 명시 배당 주입, UI 실측/추정 구분, 서버 검증 PASS (Codex) |

---

## 2026-05-27 세션 상세 기록 (Codex)

| 버그 | 증상 | 원인 | 수정 요약 | 커밋 | 상태 |
|---|---|---|---|---|---|
| 배당금 계산기 9.4억 폭증 | `458730` 100%는 약 3.2~3.4억인데, `0083S0` 0% 추가 시 약 9.4억 필요로 계산됨 | 0%/짧은 히스토리 ETF가 실제 기간과 합성 배당 통계를 왜곡. 단일 배당 이벤트의 `NaN` 표준편차도 합성 수익률을 망가뜨림 | 0% ticker 제외, 배당 통계 finite 처리, 무배당 ticker 연간 배당률 0 처리, 합성 배당률을 포트폴리오 연간 배당률 기반 월 배분으로 변경 | `09e1e50` | ✅ |
| 한국 ETF 가격 fallback 혼선 | pykrx가 가격 경로에 남아 혼란 | `PriceLoader.fetch_from_api()`가 yfinance 실패 시 pykrx fallback 호출 | pykrx fallback 제거. yfinance만 사용 | `09e1e50` | ✅ |
| 5년 월납입금 역전 | 시드 1억보다 2억의 필요 월납입금이 더 크게 나옴 | 자동 역산 anchor에서 logistic fit으로 bracket 밖 과대추정 발생 | 직전 실패~첫 성공 bracket 이분탐색으로 변경 | `db590a0` | ✅ |
| 배당금 계산기 그래프 개형 볼록함 | 시드 1억 지점 월납입금 과대추정 | 실패 후 2배 확장으로 bracket이 과도하게 넓어짐 | step 단위 narrowing 후 이분탐색. 기간 역산 최대 70년 확장 | `6a1191d` | ✅ |

---

## 2026-05-27~28 세션 수정 (Claude)

| 버그 | 원인 | 수정 | 커밋 | 상태 |
|---|---|---|---|---|
| OAuth MismatchingStateError | 브라우저 전환(카카오톡→삼성인터넷→크롬) 중 state 불일치 → 500 에러 | `google_callback`에서 Exception catch → `/auth/google` redirect | `b23e04e` | ✅ |
| **가상 데이터 DB 오염 (중대 버그)** | `SyntheticPriceGenerator.generate_and_save()`가 `price_daily`(실데이터 테이블)에 직접 저장. `retirement_logic.py`에서 `allow_synthetic=True` 하드코딩 → 유저 옵트인 없이도 가상 데이터 생성·저장됨 | 별도 테이블 `price_daily_synthetic` / `corporate_actions_synthetic` 신설. `allow_synthetic` 플래그를 전체 콜체인에 전파. 기존 오염 199,581행 서버에서 수동 클린업 스크립트 실행 제거. | `374f0a5` | ✅ |
| KRX 금현물 시세 오래된 데이터 | 자동 갱신 없음, 수동 실행만 지원 | Celery Beat 태스크 추가, 평일 16:30 KST 자동 실행 | `d56c5ee` | ✅ |
| 시장 지수 thundering herd | 캐시 만료 시 동시 요청이 모두 yfinance 호출 | Redis SETNX 락으로 1개 요청만 fetch | `d56c5ee` | ✅ |

---

## 2026-05-28 세션 수정 (Claude)

| 버그 | 원인 | 수정 | 커밋 | 상태 |
|---|---|---|---|---|
| 투자 계산기 — 가상 데이터 ON 시 "롤링 케이스가 0개" 에러 | 상장 1년 미만 ETF: TickerStatsCache None → 가상 데이터 스킵 → effective_start 최근일 → 롤링 0 | `calculator_logic.py`: n_cases=0 시 "가상 데이터 생성 불가" 명확한 에러. `data_preparer.py`: warnings에 이유 추가 | 2151db1 | ✅ |
| 투자 계산기 — 종목 첫 실행 시 "준비 중" 장시간 | BackfillEngine이 PriceLoader(get_price)와 DataPreparer 두 곳에서 중복 실행. 준비 단계 동안 진행률 업데이트 없음 | `backfill_engine.py`: volume=0 행 있으면 즉시 ok 반환(재계산 스킵). `tasks.py`: 준비 시작 시 PROGRESS 전송. `calculator.js`: "데이터 준비 중" 표시 | 90afb15 | ✅ |

**중복 백필 fix(90afb15)는 BackfillEngine 자체 수정이므로 백테스트/은퇴 탭도 자동 적용됨.**

**미해결 — "데이터 준비 중" UI가 백테스트/은퇴/배당금 계산기에는 미적용.** 백테스트·은퇴는 단발성 시뮬이라 체감 덜함. 필요 시 `tasks.py`의 `run_backtest_task` / `run_retirement_task`에 동일하게 preparing 상태 전송 추가하면 됨.

**새 종목 첫 실행은 yfinance 다운로드가 불가피** (어떤 탭이든). 최초 1회 후 캐시되어 빠름.

---

## 2026-05-28 세션 수정 2차 (Claude)

| 버그 | 원인 | 수정 | 커밋 | 상태 |
|---|---|---|---|---|
| 투자 계산기 — `used_synthetic=False` early return 시 항상 False | DataPreparer n_cases≥MIN_CASES early return이 `_used_synth=False` 하드코딩 | early return 전 `price_daily_synthetic` 존재 확인 후 반환 | `3a190b5` | ✅ |
| 가상 데이터 차트 — 2007 시작이 항상 최고 수익 | `seed=hash(code)` 단일 결정론적 경로를 60개 윈도우가 공유 → 경로 저점에 걸린 윈도우 항상 높은 수익 | `AccumulationAnalyzer._load_with_per_window_synthetic()` 추가 — 윈도우별 `seed=hash(code+start_date)` 독립 경로 생성 | `cccda40` | ✅ |
| 가상 데이터 시뮬 — `float() argument must be a string or a real number, not 'NoneType'` | `_load_with_per_window_synthetic()`에서 `sigma_monthly` None 체크 누락 | None 가드에 `sigma_monthly` 추가, fallback `allow_synthetic=True` | `86d6a39` | ✅ |
| 가상 데이터 시뮬 — `float()` NoneType (KOFR 등 flat ETF) | `TickerStatsCache` `closes = np.array([float(r[1]) for r in rows])` — close NULL 행 필터 없음. `DataPreparer` `_anchor_price = float(_ap_row[0])` — NULL close 미처리 | `TickerStatsCache`: NULL close 행 사전 필터링. `DataPreparer`: `_ap_row[0] is not None` 체크 추가 | `786831f` | ✅ |

---

## 미결 이슈 (버그는 아니지만 확인 필요)

| 이슈 | 상태 | 비고 |
|---|---|---|
| `volume=0`으로 백필/가격 오류 | ⚠️ 미확인 | 일부 종목에서 가격 대신 배당 표시 가능성 |
| **백필 provenance 전부 0행** | ✅ Stage A에서 해결 (2026-05-30, Codex) | SCHD/458730/446720/402970 백필 가격·배당 provenance 기록 확인. 과거 run_id 없는 백필 이력은 서버 재백필로 교체됨 |
| provenance 테이블 없음 | ⚠️ 미확인 | 합성 데이터 출처 적재 제거됨 |
| `TaxedDividendEngine._ytd_income` 초기값 0 | ⏳ 미완료 | `other_financial_income` 연동 필요 |
| `modules/sim/tax_engine.py` 덮어씀 | ⏳ 미완료 | Phase 2c 이후 정리 예정 |
| T1~T4 수동 테스트 미완료 | ⚠️ 미확인 | T1 배너, T2 종합과세 패널, T4 ISA 풍차 체크박스 — 브라우저 직접 확인 필요 |
