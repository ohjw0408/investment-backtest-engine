---
updated: 2026-06-17
tags: [dev, perf]
sources: [성능최적화_plan.md]
---

# 연산 성능 최적화 (2026-06-16~17, Claude)

> 레퍼런스 계획: repo 루트 `성능최적화_plan.md`. 이 페이지 = 실제 적용·측정·검증 결과 종합.

## 1. 목표·제약·대원칙

- **목표**: 시뮬레이션(투자계산기·은퇴 적립/인출·멀티계좌·배당) + 가격로더 + 세금 연산 속도 단축. 출시 준비.
- **서버 토폴로지**: **2 vCPU + 4GB RAM. 메인엔진 = Celery worker concurrency=2** (`worker_prefetch_multiplier=1` → 2 동시처리, 초과분 대기열). ⚠️ worker concurrency 설정은 서버 systemd `domino-celery.service`에만 있고 **repo 미포함** → 코드만 봐선 안 보임([[#7-발견된-버그·기술부채|기술부채]] 참조).
- **대원칙(절대)**: **결과(숫자)를 바꾸지 않는다.** 모든 최적화는 "같은 입력 → 같은 출력"을 검증 후에만 머지. **死코드 제거·pandas→numpy·無매수 단락 등 "증명상 byte 동일" 변환만** 적용. 정확성 민감 알고리즘(매수 배분·평가)은 미변경.

## 2. 전략 (CPU-bound vs I/O-bound)

- **CPU-bound(시뮬 루프·세금·통계)**: 코어 2개 + Celery가 이미 요청 병렬성 제공 → 요청 안에서 추가 멀티프로세스/스레드는 역효과(오버서브스크립션·RAM 복제). **답 = 일의 양을 줄이기**(중복 제거·numpy·캐시).
- **I/O-bound(yfinance·DB)**: 대기 중 코어가 놂 → ThreadPool 병렬이 이득.

## 3. 변경 내역 (파일별 상세)

### 3-1. 가격로드 — 롤링 윈도우 재로드 제거 (P0)
- **파일**: `modules/retirement/accumulation_analyzer.py`, `modules/retirement/multi_account_analyzer.py`
- **문제**: 롤링 분석기가 윈도우마다 `price_loader.load`(DB read + reindex + ffill)를 재실행. 50년 데이터·20년 horizon = 수백 윈도우 × 종목 → 수백 회 중복 풀로드.
- **수정**: 분석기 진입 시 `[roll_start, data_end]` **1회 로드** → 윈도우는 `_slice_window`(numpy/pandas 슬라이스)로 잘라 전달. `WithdrawalAnalyzer`가 이미 쓰던 모범 패턴을 미적용 분석기에 적용.
- **제외 경로(안전)**: ① per-window 합성(synthetic prefix) 경로는 윈도우별 독립 생성이라 그대로. ② MultiAccount의 **주입 `price_provider` 경로**(tax-switch·테스트)는 윈도우별 date-range 의미가 달라 제외 — 프로덕션 `price_loader.load` 경로만.
- **결과안전성**: 슬라이스는 이미 union·reindex·ffill된 전체에서 잘라냄 = per-window load와 동일.
- **측정**: 가격로드 부분만 (실 DB, 3종목 20윈도우) **1.95s → 0.037s = 53×** (중복 DB read 제거). 웜 수치 — 콜드/네트워크는 더 큼.

### 3-2. 배당엔진 per-day pandas 제거 (시뮬연산 핵심)
- **파일**: `modules/simulation/dividend_engine.py`, `modules/tax/account_tax.py`(TaxedDividendEngine), `modules/dividend_simulator.py`(래퍼), `modules/simulation/simulation_loop.py`, `modules/simulation/multi_account_loop.py`
- **문제(프로파일로 확정)**: `DividendEngine.process`가 **매일·종목마다** ① `date not in price_data[t].index`(union reindex라 **항상 True인 死코드**) + ② `price_data[t].loc[date,"dividend"]`(비싼 pandas 스칼라 룩업) 수행. 배당은 1년 몇 번뿐인데 **모든 날** 비싼 인덱싱. **세금ON 롤링 총시간의 64%.**
- **수정**: close처럼 dividend도 **numpy 정수인덱스**로 추출. `SimulationLoop`/`MultiAccountSimulationLoop`이 `dividend_array[t] = df["dividend"].values` 만들고, per-day `dividend_today = {t: dividend_array[t][i]}` 구성해 엔진에 전달(`dividend_today` 선택 인자). 엔진은 pandas `.loc` 대신 dict 룩업.
  - `MultiAccountSimulationLoop`은 `_gross_dividend_by_ticker`(세금 gross)도 numpy화 + `_price_dict_for_account`의 死코드 멤버십 제거(가격 NaN 필터는 유지).
  - `TaxedDividendEngine`·`DividendSimulator 래퍼`는 `dividend_today`를 `base/inner.process`로 전달만.
- **결과안전성**: `df["dividend"].values[i] == df.loc[dates[i],"dividend"]` (reindex로 dates[i]=date) → **byte 동일**. 死코드 멤버십은 항상 True라 제거해도 무변.
- **측정**: 실 DB 롤링(세금ON 3종목 15년 20윈도우) **3.13s → 1.41s = 2.21×**. 프로파일 총합 10.6s→3.26s.

### 3-3. simulation_loop per-day 멤버십 死코드 제거 (P1-2)
- **파일**: `modules/simulation/simulation_loop.py`
- **문제**: `if date not in valid_index[ticker]: continue`을 일×종목마다. 전 종목이 union 인덱스로 reindex돼 **항상 True**(프로덕션은 effective_start 공통이라 NaN도 없음) = 死코드.
- **수정**: 제거. NaN-check로 바꾸지 **않음**(late-start NaN 흐름 보존 = 결과불변). 생성된 orphan `valid_index` 정리.
- **결과안전성**: 항상 True인 분기 제거 = 결과 무변.

### 3-4. cash_allocator 無매수 조기탈출
- **파일**: `modules/execution/cash_allocator.py`
- **문제(프로파일)**: 무세금 투자계산기 총시간의 **65%**가 `allocate_cash`. 재투자/적립 후 남는 **잔돈**(cash>0이나 최저 주가 미만)이 매일 dividend sweep의 allocate_cash를 풀가동(deficit 빌드+sort)시키며 **0주 매수**.
- **수정**: 살 수 있는 종목 최저가 > cash면 어차피 0주(1차 `int(min(deficit,cash)/price)=0`, 2차 `cash<price→break`) → deficit·sort 스킵.
- **결과안전성**: **매수 결정이 0인 경우에만 단락** — greedy 매수 알고리즘 자체는 무변경. byte 동일.
- **측정**: 무세금 계산기 1.35s → 0.94s = 1.44×. total_value 호출 385k→115k로 급감.

### 3-5. Pool 1 vCPU 가드 (P1-1)
- **파일**: `modules/retirement/withdrawal_analyzer.py`
- **문제**: `WithdrawalAnalyzer`가 `multiprocessing.Pool`을 무조건 사용. 2 vCPU + Celery concurrency=2에서 **동시 2요청 시 2(Celery)+4(Pool) 프로세스가 2코어 경합 + `full_price_data` 4벌 복제 → 4GB OOM 위험**. 작은 작업엔 Pool spawn/pickle 오버헤드가 역효과.
- **수정**: `_effective_workers()` — **기본 인프로세스(1)**, 환경변수 `SIM_MAX_WORKERS>1` 명시할 때만 Pool(비-Celery 다코어 배치용). 워커=1이면 Pool 미생성.
- **이력**: 처음엔 플랜의 "1 vCPU" 문구만 믿고 `min(cpu_count,6)`으로 잘못 구현 → 오너 지적으로 토폴로지(2 vCPU + concurrency=2) 정정 후 기본 인프로세스로 수정.
- **결과안전성**: 실행 방식만 변경(`SIM_MAX_WORKERS=1`·`=2` 둘 다 결과 동일 확인).

### 3-6. 엔진 가격캐시 LRU 상한 (P1-3, RAM)
- **파일**: `modules/portfolio_engine.py`
- **문제**: `_price_cache`가 윈도우마다 distinct (tickers,start,end) 키 적재(재사용 0) → ISA 풍차(run_simulation) 등에서 무한증식 → 4GB 위협.
- **수정**: 상한 8 + 초과 시 가장 오래된 엔트리 축출. 순수 메모이제이션이라 미스 시 재로드 = 결과 무변.

### 3-7. I/O ThreadPool 병렬 (P2)
- **파일**: `app.py`, `modules/price_loader.py`
- **P2-1** `_portfolio_index_series`(겹쳐보기 포폴지수): 보유종목별 `get_symbol_data`(~2s, I/O 지배) 순차 → `ThreadPoolExecutor(min(8,n))`. **데이터 출처 무변경** + `series` dict 삽입순서=tickers순(ex.map 순서보존)=원본 합산순서 → 지수곡선 float 동일.
- **P2-2** `watchlist_quotes`: 코드별 `_watchlist_quote` 순차 → ThreadPool. ex.map 순서보존 + None 필터 → 결과 동일.
- **P2-3** `get_price` 트레일링 gap-fill: DB 최종일=직전영업일이면 매 호출 yfinance fetch가 0행(낭비). 코드별 같은 `end_date` 오늘 이미 시도면 트레일링 api_call 스킵(historical 보충은 유지). 첫 시도 0행→DB 불변→재시도 동일 = 결과불변.
- **검증**: 골든·실DB A/B로 검증 불가(네트워크/데이터경로) → 라이브 배포 + 페이지 200 probe + watchlist 라이브 응답 확인.

## 4. 탭별 속도 (실측 — 원본 91806c7 vs 현재, 같은 실 DB·머신)

| 탭 | 원본 | 현재 | 배수 |
|---|---|---|---|
| 투자계산기 (무세금) | 5.52s | 0.97s | **5.7×** |
| 투자계산기 (세금) | 9.17s | 1.04s | **8.8×** |
| 은퇴 인출 | 4.49s | 0.51s | **8.8×** |
| 멀티계좌 (세금) | 7.28s | 0.98s | **7.4×** |
| 배당계산기 | 6.47s | 4.76s | **1.36×** |

(투자계산기 3종목 15년 20윈도우 / 멀티 2계좌 12년 / 인출 15년)

- 인출 8.8×에는 원본 `Pool` 오버헤드(Windows spawn + full_price_data 복제) 제거분 포함.
- **배당계산기는 1.36×만** — 핫스팟이 per-day 배당이 아닌 다른 곳(시나리오 그리드/합성). 현재 4.76s로 최대 잔여. 추가 최적화는 보류(오너 결정).
- ⚠️ dev 머신 기준. 프로덕션(2 vCPU·DB 콜드)은 절대값 다를 수 있으나 "일 줄이기" 효과는 동일.

## 5. 검증 방법론 (대원칙 = 결과불변)

3중 검증, 매 변경마다:

1. **골든마스터 `scripts/perf_golden.py`** (합성 FakeLoader, DB·네트워크 0): 대표 4종 분포 스냅샷 `save` → 매 최적화 후 `check`로 ±rel 1e-9 비교 + wall-time. 결정론(BBB 종목 2000 시작 = union/ffill 경계 커버).
2. **실 DB A/B `scripts/perf_ab.py`** (실 종목·실 분류·세금 분기): **18 시나리오** 원본 vs 최적화 byte 동일 — 세금(ON/OFF) × 계좌(위탁/ISA/연금저축/IRP) × 자산(US ETF·KR ETF·KR주식·금·지수·혼합) × 모드(accum/withdrawal/multi) × 배당모드(reinvest/withdraw/hold) × gain_harvest · ISA풍차 · 월배당. `dump`로 지문 산출, `cmp`로 비교.
3. **전체 pytest**: 298 passed (1 failed = 저장포폴 사전존재버그, perf 무관 — 7장 참조).

> ⚠️ 골든 wall_s는 한 프로세스서 무거운 시뮬 4개 연속 실행이라 **절대 벤치로는 노이즈**. 본분(결과불변)은 정확. 절대시간은 격리 측정(위 4장)으로.

## 6. 안 한 것 (의도적 — 결과불변 원칙)

- **`cash_allocator` greedy 1주매수 알고리즘 변경**: 매수 순서·수량이 달라져 결과 변경 위험.
- **`portfolio.total_value` 산술 / per-day 루프 전체 벡터화·JIT**: 결과 변경 위험 + 大공사. 세금·리밸·배당 분기 정확성 보존 난도 高.
- → 더 짜내려면 **무세금·무리밸 단순경로 한정 벡터화 fast-path**가 유일한 길(별도 大작업·위험). 보류.

## 7. 발견된 버그·기술부채

- **BUG(사전존재): 저장 포트폴리오 round-trip 테스트 실패** — `test_saved_portfolios.py::test_save_list_update_delete_roundtrip`. API `portfolio_save`(app.py)가 저장 전 종목을 정규화하며 `quantity:0.0` 필드 추가 + weight를 float화. 테스트 `TICKERS` 픽스처는 그 전 모양(quantity 없음)이라 `==` 실패. **`quantity` 필드는 2026-06-14 update 77(총투자금액→비중) 때 의도 추가** → 테스트 동기화 누락. **사용자 영향 0**(quantity:0.0 합당한 기본값). pre-perf 91806c7서도 동일 실패 = perf 무관. → 오너 판단: 수정 보류.
- **기술부채: Celery worker concurrency가 repo 밖**(서버 systemd `domino-celery.service`만) → 코드 리뷰로 동시성/코어 토폴로지 안 보임. P1-1 초기 오판의 원인. **권장: service 파일 repo 커밋.**
- **死코드 정리**: per-day 멤버십 테스트 4곳(simulation_loop·dividend_engine·multi_account_loop·_price_dict_for_account)이 union reindex 탓 항상 True. 제거함.

## 8. 검증 도구 사용법

```bash
# 골든마스터(합성, 빠름)
python scripts/perf_golden.py save      # 최적화 전 스냅샷 기록
python scripts/perf_golden.py check     # 변경 후 결과불변 + wall-time

# 실 DB A/B(원본 vs 변경 byte 비교)
python scripts/perf_ab.py dump new.json
git checkout <old> -- <변경파일>; python scripts/perf_ab.py dump old.json; git checkout HEAD -- <변경파일>
python scripts/perf_ab.py cmp old.json new.json
```

## 9. 커밋 (전부 배포 완료, main)

| 커밋 | 내용 |
|---|---|
| 927e8eb | P0 롤링 재로드 제거 + P1 Pool 가드·캐시 LRU·死코드 |
| 91252dc | P2 I/O ThreadPool(겹쳐보기·watchlist·gap-fill) |
| 015632d | P1-1 토폴로지 정정(2 vCPU + Celery concurrency=2) |
| 9b9dc60 | 배당엔진 numpy(SimulationLoop) |
| bfed3a6 | 멀티계좌 루프 배당 numpy |
| f84e51c | 실 DB A/B 하니스 + 문서 |
| 95d1c74 | cash_allocator 無매수 단락 |
| 1d0e58f | 문서 |

관련: [[status]] · [[bugs]] · repo `성능최적화_plan.md` · `scripts/perf_golden.py` · `scripts/perf_ab.py`
