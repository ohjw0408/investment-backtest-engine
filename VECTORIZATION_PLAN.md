# 시뮬레이션 엔진 벡터화 계획 (멀티계좌 포함)

작성: 2026-06-21 (Claude). 오너 지시: 4탭(투자계산기·포트폴리오 백테·은퇴·배당금) +
**멀티계좌까지** 공용 엔진 벡터화로 속도 단축. 결과는 불변(또는 오너 허용 5% 이내·모든 퍼센타일).

## 배경 / 현황

- 배당 역산 20케이스 = 5분35초(≈16초/케이스). 윈도우 캐시·통계/MVN 피팅 캐시로 더 못 줄임.
- 병목 = **경로의존 date 루프**: sim 1회 = 일별/월별 dates 순차 루프, 역산/MC는 이를 수천~수만 번.
- cProfile: cash_allocator·simulation_loop.run·history_recorder·portfolio.total_value 가 핫.
  미세최적화(cash_allocator incremental 등)는 효과 0으로 측정됨 → 구조적 접근 필요.

## 엔진 구조 (벡터화 대상)

| 엔진 | 줄수 | 사용 탭 | 난이도 |
|---|---|---|---|
| `simulation/simulation_loop.py` (SimulationLoop) | 210 | 투자계산기·백테·은퇴인출·배당 (단일계좌) | 중 |
| `simulation/multi_account_loop.py` (MultiAccountSimulationLoop) | 1131 | 멀티계좌(가구) 전부 | **최고** |

루프 내부 컴포넌트(매 step 호출):
- `dividend_engine`(41) · `contribution_engine`(19) · `withdrawal_engine`(104)
- `execution/cash_allocator`(144) · `execution/order_executor`(397, 세금·리밸·손익통산·GH)
- `core/portfolio`(156) · `core/position`(71) · `rebalance/periodic`(93)
- `simulation/history_recorder`(60) · `simulation/monthly_mode`(70)

호출 경로:
- 투자계산기/은퇴축적: `AccumulationAnalyzer` → SimulationLoop (+ MVN: `_load_with_per_window_synthetic`)
- 백테: `taxable_runner.TaxableSimulationRunner` → SimulationLoop (단일기간 1회)
- 은퇴 인출: `withdrawal_analyzer` → SimulationLoop (+ MVN: `_run_mvn_cases`, mc_paths 경로)
- 배당: `dividend_simulator` → SimulationLoop (역산 = 수천 윈도우)
- 멀티계좌: `multi_account_analyzer` / `multi_account_withdrawal` / `dividend_multi` → MultiAccountSimulationLoop

## 벡터화 원리 — "경로축(paths) 동시화"

완전 벡터화는 불가(경로의존 상태기계: 복리·재투자·리밸·인출·연도별 세금한도). 하지만
**여러 독립 경로(MC paths / 롤링 윈도우)를 paths축으로 묶어 동시 처리**할 수 있다:

- 상태를 스칼라→배열: `cash[P]`, `qty[P,K]`, `avg_cost[P,K]` (P=경로수, K=종목수)
- days축만 순차(경로의존), **paths축은 numpy 벡터** → days 루프 1회에 P경로 전부 진행
- 조건분기(리밸·세금)는 path별 mask/where로 벡터화
- 이론상 P배 (현재 케이스당 16초 → 묶음당 16초로 P케이스)

핵심 제약: 경로가 **독립·동일 길이·동일 일정**이어야 batch. MC 합성(동일 horizon)·동일기간 롤링은 적합.
실측 롤링(윈도우마다 시작/길이 다름)은 패딩+마스크 필요(중간 난이도).

## 기술 선택: numpy 2D vs Numba vs C

| 방법 | 속도 | 노력 | 결정 |
|---|---|---|---|
| **numpy 경로축 2D** | 높음(P배) | 중~대 | **1순위** — 벡터 연산 자연스러움, 의존성 0 |
| **Numba `@njit`** | C급 | 중 | 경로축 묶기 애매한 순차 핵(세금 상태기계)에 보완 적용 |
| Cython | C급 | 대 | 빌드 복잡, Numba 대비 이득 적음 — 보류 |
| 순수 C/Rust 확장 | 최고 | 최대 | prod 빌드·배포·유지보수 복잡, 이득 < 비용 — **비채택** |

결론: **numpy 경로축 벡터화 주력 + 세금 상태기계는 Numba 보조**. C 직접 작성은 안 함.

## 단계 계획 (위험 낮은 순 — 각 단계 독립 배포·검증)

### P0. 골든 마스터 하니스 (선행 필수)
- 4탭 + 멀티 대표 시나리오(세금 ON/OFF, 리밸 none/주기/밴드, ISA/연금/위탁, MVN 발동/실측)의
  **현재 결과(퍼센타일 p5/25/50/75/95·anchor·생존율·end_value)를 JSON으로 고정**.
- 모든 후속 단계는 이 골든 대비 **불변(또는 5% 이내 전 퍼센타일)** 자동 검증.
- 없으면 벡터화 회귀를 못 잡음 → 1순위.

### P1. MC 합성경로 벡터 엔진 (가장 안전·큰 효과)
- 대상: `_run_mvn_cases`(은퇴 인출)·`_run_mvn_div_cases`(배당)·멀티 합성 — 현재 path마다 SimulationLoop.
- 신규 `modules/simulation/vector_engine.py`: 동일 horizon·동일 일정의 P경로를 2D로 동시 시뮬
  (배당재투자·인출·드리프트 리밸까지). **기존 SimulationLoop은 그대로** → 실측 경로 무영향(회귀 위험↓).
- 세금: 1차는 **세금 OFF 경로만** 벡터(세전 분포). 세금 ON은 P3로.
- 결과 불변: 동일 난수 시드·동일 로직 → 비트동일 목표(부동소수 누적순서 차이 시 5% 이내 검증).
- 기대: MC 케이스(합성 보충·mc_paths) P배. 배당 역산의 합성 보충 구간 직격.

### P2. 동일기간 롤링 벡터화
- 실측 롤링(같은 step, 윈도우만 다름)을 paths=윈도우로 묶어 vector_engine 재사용.
- 윈도우별 시작 다름 → 공통 달력에 패딩 + 유효구간 마스크. 중간 난이도.
- 배당 역산(실측 롤링이 다수)·계산기 롤링 직격.

### P3. 세금 경로 벡터화 (Numba 보조)
- order_executor의 연도별 세션(ISA/연금 과세이연·손익통산·gain harvest)을 path배열화.
- 복잡한 분기 → numpy mask + 연도경계 segment 처리, 또는 핵심 루프 `@njit`.
- 위험 높음 → 골든 대비 세금 시나리오 집중 검증.

### P4. 멀티계좌 벡터화 (최고 난도, 마지막)
- MultiAccountSimulationLoop(1131줄): 계좌간 이체·ISA 만기 갱신·연금 적립크레딧·드레인 순서.
- 계좌간 의존(전환·합산 인출)이라 paths축과 accounts축 2중. 단계적:
  - (a) 계좌별 독립 구간을 vector_engine으로, 계좌간 동기점(이체/만기/인출충당)만 순차.
  - (b) ISA갱신·연금크레딧·드레인순서는 연 1회/이벤트성 → 벡터 부담 작음, 보존.
- 가장 회귀 위험 큼 → 멀티 골든(가구 생존율·계좌별 분포) 비트단위 검증.

### P5. 정리·튜닝
- 경로수(P) 메모리 vs 속도 균형(1vCPU·4GB prod). 청크 batch(P를 256씩 등).
- Numba 워밍업 캐시(`cache=True`)로 첫 호출 JIT 비용 상쇄.

## 결과 불변 전략 (오너 절대조건)
- P0 골든 마스터가 게이트. 각 단계 후 4탭+멀티 전 시나리오 퍼센타일 5% 이내(전 퍼센타일) 자동 확인.
- 부동소수 누적순서 차이(벡터 reduce vs 순차)는 불가피한 미세차 — 5% 이내면 허용(오너 합의).
- 난수: MC 시드 경로별 고정(seed_base+p) 유지 → 벡터화해도 같은 난수열 → 분포 동일.
- 세금 경계(연도·한도)는 비트단위 일치 목표(여기 틀리면 큰 차이).

## 리스크
- 공용 엔진 재설계 = 전 탭 회귀 위험 → **신규 vector_engine 병행**(기존 보존), 단계별 전환.
- 멀티계좌(P4)는 1131줄 상태머신 → 가장 위험, 마지막. 효과 대비 위험 크면 보류 옵션.
- 메모리: P경로 × T일 × K종목 2D 배열 — prod 4GB 한계, 청크 필요.
- 노력: P0~P2 = 중, P3 = 대, P4 = 대~매우대. 전체 수주 규모.

## 우선순위 추천
1. **P0**(골든) → **P1**(MC 합성 벡터, 세금OFF) → **P2**(롤링 벡터). 여기까지가 배당 역산·MC 직격, 위험 낮음.
2. P3(세금)·P4(멀티)는 P1·P2 효과 측정 후 필요시. 멀티는 위험·노력 대비 판단.

> ⚠️ 16초/케이스가 MC(합성)인지 실측 롤링인지에 따라 P1 vs P2 우선순위 갈림 — 오너 케이스
> 설정(종목·기간·세금·가상데이터 ON 여부) 확인 후 착수 순서 확정.
