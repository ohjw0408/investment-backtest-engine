# 연산 성능 최적화 계획 (Performance Optimization Plan)

작성: 2026-06-15
대상: 시뮬레이션 엔진(백테스트·투자계산기·은퇴 적립/인출·ISA 전환·배당) + 가격 로더 + 세금 + 겹쳐보기 등 **연산이 들어가는 전 경로**
제약: **서버 = 가상 CPU 1개 + RAM 약 4GB.**

> 절대 원칙: **결과(숫자)를 바꾸지 않는다.** 모든 최적화는 "같은 입력 → 같은 출력(±부동소수 오차)"을 골든마스터로 검증한 뒤에만 머지. 속도와 정확성을 타협하지 않는다.

---

## 0. 1 vCPU / 4GB가 의미하는 것 (전략 토대)

- **CPU-bound 코드(시뮬 루프·세금·통계)**: 코어가 1개 → **스레드·멀티프로세스로 빨라지지 않는다**(GIL + 단일 코어). 오히려:
  - `multiprocessing.Pool` = 프로세스마다 데이터 복사(fork) → **RAM 폭증(4GB 한계)** + 직렬화/fork 오버헤드 → **1 vCPU에선 역효과**.
  - Celery 워커 2개로 CPU-bound 작업 동시 처리 = 컨텍스트 스위칭만 늘고 총 처리량 동일, 지연만 악화.
  - → CPU-bound는 **일의 양을 줄이는 것만**이 답: 중복 제거·벡터화·알고리즘·캐시.
- **I/O-bound 코드(yfinance 네트워크·DB)**: 대기 중 코어가 논다 → **스레드(ThreadPool)가 1코어에서도 이득**. 네트워크 N건 병렬 OK.
- **RAM 4GB**: 대형 DataFrame 반복 로드·프로세스 복제·무한 증식 캐시 금지. 풀히스토리는 1벌만 들고 슬라이스 재사용.

핵심 분류: **시뮬은 CPU-bound → 중복연산 제거가 본질. 시세조회는 I/O-bound → 병렬화가 본질.**

---

## 1. 코드 정독 결과 — 연산 인벤토리 & 핫스팟

| 모듈 | 역할 | 연산 성격 | 상태 |
|---|---|---|---|
| `simulation/simulation_loop.py` | per-day 메인 루프 | CPU, 최내곽(윈도우×일) | 일부 numpy 캐싱됨, 잔여 핫스팟 |
| `core/portfolio.py` | buy/sell/value | CPU, dict 연산 | 가벼움(문제 없음) |
| `simulation/taxable_runner.py` | 과세 시뮬 래퍼 | CPU | loop 위임 |
| `retirement/accumulation_analyzer.py` | 롤링(계산기·은퇴적립 메인) | CPU, 윈도우 수백 | ❌ **윈도우마다 재로드** |
| `retirement/multi_account_analyzer.py` | 멀티계좌·tax-switch | CPU, 윈도우×계좌 | ❌ 윈도우마다 `_load_prices` |
| `retirement/withdrawal_analyzer.py` | 인출 롤링 | CPU | ✅ **전체 1회 로드+슬라이스** (모범) / ⚠️ Pool(1vCPU 부적합) |
| `simulation/price_data_loader.py` | load+reindex+ffill | CPU+I/O | 윈도우마다 호출되면 중복 |
| `price_loader.py` | DB/yfinance 가격 | I/O | gap-fill 0행도 네트워크 침 |
| `analyzer/engine_rolling_analyzer.py` | (백테 계열) 롤링 | CPU | 윈도우마다 run_simulation, IRR 200iter |
| `dividend_simulator.py` | 배당 롤링 | CPU | ✅ `_preload_all` 보유 |
| `tax/base_tax.py` | 배당/양도/연금세 | CPU | ✅ `_classify_cache` 보유 |
| `retirement/synthetic_*` | 합성 가격 생성 | CPU+난수 | 윈도우별 생성 |
| app.py `_portfolio_index_series`(C3) | 겹쳐보기 포폴지수 | I/O | ❌ 보유종목마다 `get_symbol_data`(~2s) |
| app.py `watchlist_quotes` | 홈/위젯 시세 | I/O | ❌ 코드별 순차 |

### 실측 (2026-06-15, 로컬)
- `get_price` 45일창: 0.3~0.8s (로컬 DB; gap-fill 시 네트워크 1회 추가)
- `get_symbol_data` 전체: **1.8~2.1s** (전체 히스토리 6651행 + 메타 `.info`)
- `price_loader.load`(윈도우당): 종목별 DB read + to_datetime + set_index + union + reindex + ffill

### 결정적 대조 (최적화가 안전·유효함의 증거)
- **WithdrawalAnalyzer._run_rolling(:226)**: "전체 범위 1회 로드" 후 윈도우 슬라이스 — **이미 올바른 패턴**.
- **AccumulationAnalyzer._run_rolling(:170)**: 동일 작업을 **윈도우 while 루프 안에서 매번** `price_loader.load(...)` — 수백 회 재로드.
- → 같은 엔진군 안에서 한쪽은 최적, 한쪽은 미적용. **미적용 분석기를 모범 패턴으로 끌어올리면 됨(결과 불변).**

---

## 2. 최적화 백로그 (우선순위)

각 항목: 문제 / 증거 / 수정 / 예상이득 / 위험 / 결과안전성 / 검증.

### 🔴 P0-1. 롤링 윈도우 가격 재로드 제거 (최대 레버)
- **문제**: AccumulationAnalyzer(`:170`)·MultiAccountAnalyzer(`_load_prices :490`)가 윈도우마다 `price_loader.load`(DB read + reindex + ffill)를 재실행. 50년 데이터·20년 horizon = 약 수백 윈도우 → 수백 회 중복 풀로드.
- **증거**: WithdrawalAnalyzer는 같은 작업을 1회만 함(`:226`).
- **수정**: 분석기 진입 시 `[roll_start, data_end]` **1회 로드 + reindex/ffill 1회** → `dates`를 numpy 배열로, 종목별 `close/dividend/...`를 numpy 배열로 보관. 윈도우 경계는 `np.searchsorted(dates, start/end)`로 **정수 오프셋** 산출 → per-window는 numpy **슬라이스 뷰**만 전달(복사·재로드·pandas 마스킹 0).
- **예상이득**: 롤링 시간의 지배적 비중 → DB·pandas 재작업 5~20× 감소.
- **위험**: 中. ffill 정렬·합성 보충(`_load_with_per_window_synthetic`)·ISA 풍차 경로의 슬라이싱 의미를 정확히 보존해야. 합성 보충 윈도우는 별도 처리(roll_start 확장분).
- **결과안전성**: 동일 데이터·동일 윈도우 → 퍼센타일 **완전 동일**.
- **검증**: 골든마스터(대표 입력 5종) p10/p50/p90·case 수 before==after(±1원). 벤치 wall-time.

### 🔴 P0-2. portfolio_engine.run 윈도우 슬라이싱 pandas 제거
- **문제**(`portfolio_engine.py:88-94`): 윈도우마다 `[d for d in dates if start<=d<=end]`(O(전체일수) 파이썬 루프) + 종목별 `df.loc[boolean mask]`(O(n) pandas). 수백 윈도우 반복.
- **수정**: P0-1의 공유 numpy/searchsorted 오프셋 사용. EngineRollingAnalyzer 경로도 동일.
- **이득/위험/검증**: P0-1과 묶음.

### 🟠 P1-1. 1 vCPU에서 multiprocessing.Pool 제거/가드 (RAM·역효과)
- **문제**(`withdrawal_analyzer.py:223` `from multiprocessing import Pool`): Pool이 워커마다 `full_price_data` 복제 → **4GB에서 OOM 위험** + 1코어라 병렬 속도이득 0 + fork/pickle 오버헤드.
- **수정**: `os.cpu_count()` 기반 분기 — 코어 1개면 **인프로세스 루프**(P0의 numpy 슬라이스로 충분히 빠름), 멀티코어 배포에서만 Pool(workers=cpu-1). 환경변수 `SIM_MAX_WORKERS`로 상한.
- **예상이득**: 프로덕션 OOM·fork 오버헤드 제거 + 1코어 실측 더 빠름.
- **결과안전성**: 동일(실행 방식만). **검증**: 결과 동일 + peak RSS·wall-time 측정.

### 🟠 P1-2. per-day 루프 멤버십 테스트 제거
- **문제**(`simulation_loop.py:61`): `if date not in valid_index[ticker]`(DatetimeIndex 해시 멤버십)을 일×종목마다. ~180만 반복 × 종목수.
- **수정**: 데이터가 이미 union 인덱스로 reindex됨(`price_data_loader`) → 전 종목 동일 날짜축. 멤버십 대신 가격 NaN 여부(`price==price`/`np.isnan`)로 결측 판정. 정수 인덱스 `i` 직접 사용.
- **이득**: 최내곽 상수항 절감 × 수백만 반복. **위험**: 低. **검증**: 결과 동일.

### 🟠 P1-3. 엔진 가격캐시 무한 증식 방지 (RAM)
- **문제**(`portfolio_engine.py:_find_cached_or_load`): 윈도우마다 distinct (start,end) 키로 캐시 적재 → 한 롤링 실행 내에서 수백 벌 누적(재사용 0). 4GB 위협.
- **수정**: 롤링은 P0로 캐시 불필요(분석기가 1벌 보유). 엔진 캐시는 요청 종료 시 `clear_cache()` + 엔트리 수 LRU 상한(예: 8).
- **결과안전성**: 동일. **검증**: peak RSS.

### 🟡 P2-1. C3 겹쳐보기 포폴지수 경량화 + 병렬 (방금 출시, 체감 큼)
- **문제**(`app.py _portfolio_index_series`): 보유종목마다 `get_symbol_data`(~2s, 전체 히스토리+`.info` 메타) 호출. 10종목 = ~20s, 기본 프리셋(포폴 2~3) = 40~60s.
- **수정**: 메타·전체히스토리 불필요 → **가격 전용 경로**(`get_price` 필요창)만, `.info`/52w/dividends 스킵. 종목 fetch는 **ThreadPool**(I/O-bound, 1코어도 이득).
- **예상이득**: 40~60s → ~2~3s. **위험**: 低(가격만 쓰므로). **검증**: 동일 지수곡선(±오차) + wall-time.

### 🟡 P2-2. watchlist_quotes 병렬화 (홈 첫인상)
- **문제**(`app.py:1168`): 코드별 `_watchlist_quote` **순차**. 콜드캐시 12~20종목 = 5~15s.
- **수정**: ThreadPool(maxworkers~8)로 `_watchlist_quote` 병렬(캘린더 FRED 병렬과 동일 패턴). Redis 캐시·15분 floor 유지.
- **이득**: 5~15s → 1~2s(콜드). 웜은 이미 즉시. **위험**: 低. **검증**: 동일 시세 + wall-time.

### 🟡 P2-3. get_price gap-fill 네트워크 단락
- **문제**(`price_loader.py`): DB가 최신이어도 get_price마다 yfinance gap-fill 시도(실측 "백필 완료 SPY 0행" = 네트워크 1회 낭비). 위젯·롤링서 누적.
- **수정**: 코드별 "오늘자 최종 시도" 마커(메모리/Redis) → 같은 날 재시도 스킵. 또는 DB 최종일==직전영업일이면 네트워크 생략.
- **이득**: 위젯/롤링 콜드경로 네트워크 호출 수 감소. **위험**: 中(최신성 규약 — 15분 floor와 정합). **검증**: 시세 최신성 + 호출 수.

### 🟢 P3-1. 윈도우 후처리 pandas 중복 제거
- **문제**(`engine_rolling_analyzer.py`): `resample("ME")` 2회(`:86`,`:149`)·`to_datetime`·`set_index`·`copy` 윈도우마다. IRR Newton 200iter(`:121`)는 수렴 시 break 있음(양호)이나 npv가 파이썬 sum.
- **수정**: resample 1회 재사용, npv/dnpv numpy 벡터화, history 후처리 numpy화.
- **이득**: 윈도우당 상수 절감 × 수백. **위험**: 低. **검증**: 지표 동일.

### 🟢 P3-2. (고급·후순위) 최내곽 루프 JIT
- per-day 루프를 Numba/Cython화 검토. 단 루프가 파이썬 엔진객체(executor·tax)를 호출 → JIT 난도 高. **무세금·무리밸·일시납·재투자** 단순경로에 한해 벡터화 fast-path(누적수익률) 신설 = 겹쳐보기/비교 등 비과세 추세계산 대량 가속 가능. 위험 中(경로 분기 정확성). 후순위.

---

## 3. 횡단 항목 (인프라)

- **Celery 동시성**: 1 vCPU + CPU-bound 시뮬 → 시뮬 큐 `concurrency=1` 권장(2워커는 지연·RAM만 악화). I/O성 작업(시세·캘린더)은 분리 큐에서 스레드 활용. → `celery_app.py`/배포 설정 검토.
- **RAM 가드**: `_price_cache` LRU 상한 + 요청 종료 `clear_cache`; Pool 복제 제거(P1-1); HistoryRecorder 누적 자료 슬림화 검토.
- **벤치 하니스(선행 작업)**: 최적화 전에 **골든마스터 + 타이밍 하니스** 먼저 구축 — 대표 입력(단일/멀티/은퇴적립/인출/배당/tax-switch)별 결과 스냅샷 저장 → 매 최적화가 숫자 불변임을 자동 확인 + wall-time·peak RSS 기록. **이게 "타협 없음"의 안전장치.**

---

## 4. 권장 실행 순서

1. **벤치 하니스 + 골든마스터** (선행, 필수). 없으면 "결과 불변" 보장 불가.
2. **P0-1 + P0-2** (롤링 재로드 제거) — 최대 이득, 결과 불변.
3. **P1-1** (Pool 1vCPU 가드) — 프로덕션 OOM/역효과 제거.
4. **P1-2 / P1-3** (per-day 멤버십 / 캐시 RAM).
5. **P2-1 / P2-2** (겹쳐보기·홈 시세 병렬 — 체감 큰 I/O).
6. **P2-3 / P3** (gap-fill 단락 / 후처리 / fast-path).

각 단계: 골든마스터 통과 → wall-time·RSS 기록 → 커밋. 한 번에 하나씩.

---

## 5. 하지 말 것 (제약·정확성)

- ❌ 결과를 바꾸는 근사·표본 축소·윈도우 감소(정확성 타협 금지).
- ❌ 1 vCPU에서 multiprocessing/스레드로 CPU-bound 가속 시도(이득 0·RAM↑).
- ❌ 골든마스터 없이 핫패스 리팩토링.
- ❌ 풀히스토리 여러 벌 상주(4GB 초과 위험).

---

*레퍼런스: `PROJECT_MASTER_ROADMAP.md`(조정), `PHASE4_PLAN.md`. 작업 완료 시 `moneymilestone/wiki/dev/status.md`·`log.md` 동기화. 측정 수치는 본 파일 §1에 갱신.*
