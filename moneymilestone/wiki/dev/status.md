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
| 🔴 **Track G2 + 금종세자 ISA 풍차 중단** | 2f 트래킹을 입력으로 소비. transfer 엔진(현 NotImplementedError) 신규 + ISA 1억 리라우팅 + 풍차 중단·무한유지 | **2f 잔여 후 / G2** | `Track G2 구현해줘` |
| ⏸️ Track G | 다중계좌 — G1 ✅(Codex, 배당0은 Stage A로 해소). ② 커서 ③ UI + G2 자금이동 | 종합과세 후 | `Track G 재개해줘` |
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
