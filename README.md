# Domino Invest — 투자 백테스트 엔진

Flask 기반 종합 투자 포트폴리오 분석·백테스트·은퇴 계획 웹 애플리케이션.  
한국(KRW) 및 미국(USD) 자산을 동시 지원하며 세금 계산·배당 시뮬레이션·몬테카를로식 롤링 시나리오 분석을 제공합니다.

---

## 목차

1. [기능 개요](#1-기능-개요)
2. [프로젝트 구조](#2-프로젝트-구조)
3. [시스템 아키텍처](#3-시스템-아키텍처)
4. [데이터 레이어](#4-데이터-레이어)
5. [핵심 시뮬레이션 엔진](#5-핵심-시뮬레이션-엔진)
6. [리밸런싱 전략](#6-리밸런싱-전략)
7. [은퇴 계획 모듈](#7-은퇴-계획-모듈)
8. [배당 시뮬레이터](#8-배당-시뮬레이터)
9. [세금 엔진](#9-세금-엔진)
10. [인증 시스템](#10-인증-시스템)
11. [API 엔드포인트](#11-api-엔드포인트)
12. [핵심 계산 알고리즘](#12-핵심-계산-알고리즘)
13. [데이터베이스 스키마](#13-데이터베이스-스키마)
14. [성능 최적화](#14-성능-최적화)
15. [의존성](#15-의존성)
16. [실행 방법](#16-실행-방법)

---

## 1. 기능 개요

| 메뉴 | 경로 | 설명 |
|---|---|---|
| **홈** | `/` | 실시간 시장 지수 (S&P500·NASDAQ·KOSPI·금·USD/KRW) |
| **투자 계산기** | `/calculator` | 포트폴리오 롤링 백테스트. CAGR·MDD·Sharpe·MWR 분포 계산 |
| **배당 계산기** | `/dividend-target` | 목표 월배당 달성을 위한 시드·월납입·기간 역산 및 확률 분석 |
| **은퇴 설계** | `/retirement` | 적립기(DCA) + 인출기(SWR) 2단계 시뮬레이션. 생존율 분포 제공 |
| **포트폴리오 분석** | `/backtest` | 단일 기간 전통적 백테스트 |
| **내 자산** | `/myassets` | 자산 현황 관리 |
| **세금 설정** | `/tax-settings` | 계좌 유형·국가별 세율 설정 |

---

## 2. 프로젝트 구조

```
investment-backtest-engine/
│
├── app.py                           # Flask 앱 진입점 + 모든 API 라우터
├── requirements.txt
│
├── modules/
│   ├── core/
│   │   ├── portfolio.py             # Portfolio (포지션 + 현금 관리)
│   │   └── position.py              # Position (수량·평균단가·실현PnL)
│   │
│   ├── config/
│   │   └── simulation_config.py     # SimulationConfig 데이터클래스
│   │
│   ├── execution/
│   │   ├── order_executor.py        # 가치 기반 주문 → 수량 거래 변환
│   │   └── cash_allocator.py        # 잔여 현금을 목표 비중대로 배분
│   │
│   ├── simulation/
│   │   ├── simulation_loop.py       # 일별 시뮬레이션 메인 루프
│   │   ├── dividend_engine.py       # 배당금 처리 (DPS × 보유수량)
│   │   ├── contribution_engine.py   # 월납입 현금 추가 (월 1회)
│   │   ├── withdrawal_engine.py     # 인플레이션 조정 인출
│   │   ├── price_data_loader.py     # 가격 로드 + 날짜 합집합 + ffill
│   │   └── history_recorder.py      # 일별 포트폴리오 스냅샷 기록
│   │
│   ├── rebalance/
│   │   ├── base_strategy.py         # 리밸런싱 전략 기반 인터페이스
│   │   └── periodic.py              # 주기적·밴드·없음 전략 구현
│   │
│   ├── retirement/
│   │   ├── accumulation_analyzer.py # 적립기 롤링 + GBM 합성 케이스
│   │   ├── withdrawal_analyzer.py   # 인출기 성공률 분석
│   │   ├── retirement_planner.py    # 2단계 오케스트레이터 (11 percentile)
│   │   ├── data_preparer.py         # 데이터 준비 파이프라인
│   │   ├── ticker_stats_cache.py    # 종목별 mu/sigma 통계 캐시
│   │   └── synthetic_price_generator.py  # GBM + Student-t 가상 가격 생성
│   │
│   ├── analyzer/
│   │   ├── rolling_scenario_analyzer.py  # 단순 롤링 윈도우 분석
│   │   ├── portfolio_analyzer.py
│   │   ├── dividend_projection_analyzer.py
│   │   ├── wealth_projection_analyzer.py
│   │   └── retirement_analyzer.py
│   │
│   ├── sim/
│   │   ├── tax_engine.py            # 세금 계산 (계좌유형·국가·누진세)
│   │   └── fee_engine.py            # 거래 수수료 계산
│   │
│   ├── krx/
│   │   └── krx_client.py            # KRX 금현물 시세 클라이언트
│   │
│   ├── portfolio_engine.py          # PortfolioEngine 오케스트레이터 + 캐시
│   ├── dividend_simulator.py        # 배당 역산 시뮬레이터
│   ├── backfill_engine.py           # KR/US ETF 인덱스 기반 백필
│   ├── auth_manager.py              # Google OAuth 사용자 DB 관리
│   ├── price_loader.py              # 가격 통합 접근 레이어
│   ├── data_engine.py               # yfinance 기반 시장 지수 데이터
│   ├── info_engine.py               # 퍼지 심볼 검색
│   └── db_builder.py                # DB 초기화 도구
│
├── templates/
│   ├── base.html                    # 마스터 레이아웃 (네비바 + 사이드바 + 검색)
│   ├── index.html                   # 홈 대시보드
│   ├── calculator.html              # 투자 계산기
│   ├── dividend_target.html         # 배당 역산기
│   ├── retirement.html              # 은퇴 설계
│   ├── backtest.html                # 포트폴리오 분석
│   ├── myassets.html                # 내 자산
│   └── tax_settings.html            # 세금 설정
│
├── static/css/style.css
│
├── tests/                           # 20+ 테스트 파일
│
└── data/
    ├── meta/
    │   ├── index_master.db          # 시장 지수 일별 종가 (S&P500·KOSPI·금·USD/KRW 등)
    │   ├── kr_etf_list.csv          # KR ETF 메타 (기초지수·레버리지·환헤지)
    │   └── us_etf_list.csv          # US ETF 메타 (카테고리→지수 매핑)
    ├── price_cache/
    │   └── price_daily.db           # 일별 OHLCV + 배당 + 분할 데이터
    └── private/
        └── users.db                 # 사용자 계정 + 세금 설정 (Google OAuth)
```

---

## 3. 시스템 아키텍처

### 3.1 전체 데이터 흐름

```
[브라우저]  HTTP POST /api/calculator/run
     │
     ▼
[app.py]  JSON 파싱 → strategy_factory 생성 → AccumulationAnalyzer 호출
     │
     ▼
[DataPreparer]  (은퇴 계획기만 해당)
  ├─ 종목별 데이터 범위 확인
  ├─ BackfillEngine → 인덱스 기반 백필
  └─ SyntheticPriceGenerator → GBM 합성 가격 생성
     │
     ▼
[AccumulationAnalyzer / WithdrawalAnalyzer]
  ├─ PriceDataLoader.load() → 전체 범위 1회 로드
  ├─ 롤링 윈도우 목록 생성 (3개월 간격 슬라이딩)
  │
  ├─ [multiprocessing.Pool — N_WORKERS=8]
  │   각 윈도우마다 _run_acc_case() / _run_wd_case() 실행
  │   ┌─────────────────────────────────────────────┐
  │   │ SimulationLoop.run() — 일별 루프              │
  │   │   DividendEngine    ← 배당 수취              │
  │   │   ContributionEngine ← 월납입 현금 추가       │
  │   │   WithdrawalEngine  ← 인출 (인플레이션 반영) │
  │   │   PeriodicRebalance ← 리밸런싱 필요 판단     │
  │   │   OrderExecutor     ← 매도→매수 실행         │
  │   │   CashAllocator     ← 잔여 현금 Greedy 배분  │
  │   │   HistoryRecorder   ← 일별 스냅샷 저장       │
  │   └─────────────────────────────────────────────┘
  │
  ├─ 케이스 < 30개 시 → GBM + Student-t 합성 케이스 보충
  │
  └─ 분위수 집계 (p10/p25/p50/p75/p90)
     │
     ▼
[RetirementPlanner]  (은퇴 설계)
  ├─ AccumulationAnalyzer.run() → end_value 분포
  ├─ 11개 percentile (p5~p95) 추출
  └─ 각각을 initial_capital로 WithdrawalAnalyzer.run() 실행
     │
     ▼
[JSON 응답] → Chart.js 시각화
```

---

### 3.2 모듈 의존 관계

```
app.py
  ├─ PortfolioEngine
  │     ├─ PriceLoader           (price_daily.db + yfinance)
  │     ├─ PriceDataLoader       (PriceLoader 래퍼)
  │     ├─ SimulationLoop
  │     │     ├─ DividendEngine
  │     │     ├─ ContributionEngine
  │     │     ├─ WithdrawalEngine
  │     │     ├─ OrderExecutor
  │     │     └─ CashAllocator
  │     └─ HistoryRecorder
  │
  ├─ AccumulationAnalyzer
  │     └─ (Pool worker) → SimulationLoop 직접 인스턴스화
  │
  ├─ WithdrawalAnalyzer
  │     └─ (Pool worker) → SimulationLoop 직접 인스턴스화
  │
  ├─ RetirementPlanner
  │     ├─ AccumulationAnalyzer
  │     └─ WithdrawalAnalyzer (11회)
  │
  ├─ DataPreparer
  │     ├─ BackfillEngine        (index_master.db)
  │     ├─ TickerStatsCache
  │     └─ SyntheticPriceGenerator
  │
  └─ DividendSimulator
        └─ TaxEngine (선택)
```

---

## 4. 데이터 레이어

### 4.1 PriceLoader (`modules/price_loader.py`)

모든 가격 데이터에 대한 단일 접근 레이어. 여러 소스를 자동 폴백합니다.

**데이터 소스 우선순위:**
1. `price_daily.db` — SQLite 로컬 캐시 (가장 빠름)
2. yfinance API — 캐시 미스 시 자동 다운로드 후 저장
3. FinanceDataReader — KRX 데이터

**종목 유형 판별:**
- 6자리 숫자 → KR ETF (예: `069500` = KODEX 200)
- 알파벳 → 미국 자산 (예: `SPY`, `QQQ`, `^GSPC`)

**USD→KRW 변환:**  
미국 자산은 `get_price(apply_fx=True)` 시 `close × USD/KRW 환율`로 원화 환산.  
환율 데이터 최초 가용일: **1964-05-04** (`USD_KRW_START` 상수)

---

### 4.2 PriceDataLoader (`modules/simulation/price_data_loader.py`)

PriceLoader를 감싸 멀티 티커 날짜 정합성을 보장합니다.

**처리 과정:**
1. 각 티커의 DataFrame을 로드
2. 모든 티커의 날짜 **합집합** 계산 (`set.union`)
3. 합집합 인덱스로 `reindex`
4. 가격 컬럼(`open/high/low/close/volume`) → `ffill` (이전 유효값으로 채움)
5. `dividend` → `fillna(0)` (배당 없는 날 0으로 처리)
6. `split` → `fillna(1)` (분할 없는 날 1.0으로 처리)

---

### 4.3 BackfillEngine (`modules/backfill_engine.py`)

KR ETF·US ETF의 **상장 이전** 가격 데이터를 기초지수로부터 역산합니다.

**알고리즘:**
1. ETF 메타 로드 (`kr_etf_list.csv`, `us_etf_list.csv`)
2. `INDEX_MAP`으로 기초지수 코드 결정
3. `index_master.db`에서 기초지수 일별 시계열 로드
4. 레버리지 배수 적용: 일간 수익률 × leverage 후 누적곱 재구성
5. 환노출형(KR ETF, market=US, hedge=unhedged): 기초지수 × USD/KRW
6. ETF 상장 첫날 가격에 **스케일 맞춤** (ETF 첫날가 / 지수 첫날값)
7. 상장 이전 구간만 `INSERT OR IGNORE`로 저장

**지수 매핑 (KR ETF 예시):**

| ETF 코드 | ETF 이름 | 기초지수 | index_master 코드 |
|---|---|---|---|
| 069500 | KODEX 200 | KOSPI200 | KS200 |
| 360750 | TIGER 미국S&P500 | SP500 | ^GSPC |
| 133690 | TIGER 나스닥100 | NASDAQ100 | ^NDX |
| 453850 | ACE 미국30년국채 | US_TREASURY_30Y | DGS30 |

**US ETF 카테고리 매핑 (예시):**

| 카테고리 | 매핑 지수 |
|---|---|
| US Equity - Large Cap Blend | ^GSPC |
| US Equity - Dividend | DJUSDIV100 |
| US Bond - Long Treasury | DGS30 |
| Commodity - Gold | GC=F |

---

### 4.4 SyntheticPriceGenerator (`modules/retirement/synthetic_price_generator.py`)

역방향 GBM + Student-t 분포로 가상 과거 가격 시계열을 생성합니다.

**생성 원리 (역방향):**
```
실제 첫 거래일 가격 P0을 anchor로 역방향 재구성:
  P[-1] = P0 / (1 + r[-1])
  P[-2] = P[-1] / (1 + r[-2])
  ...
→ anchor_price와 연속성 보장
```

**수익률 모델:**
```python
raw  = standard_t(df=5, size=n_days)
rets = (raw / sqrt(5/(5-2))) * sigma_daily + mu_daily
# Student-t(df=5): 팻 테일 반영 (정규분포보다 극단값 자주 발생)
```

**저장:** `INSERT OR IGNORE` → 실제 데이터 덮어쓰기 없음

---

### 4.5 DataPreparer (`modules/retirement/data_preparer.py`)

은퇴 계획 시뮬레이션 전 데이터 준비 파이프라인.

```
1단계: 종목별 데이터 시작일 확인
2단계: 포트폴리오 유효 시작일 = max(종목별 시작일)
       USD_KRW_START(1964-05-04)보다 앞이면 캡 적용
3단계: 롤링 케이스 수 계산
       충분하면(≥30) 즉시 반환
4단계: 케이스 부족 시 종목별 보완
   4a. BackfillEngine.backfill() → 인덱스 백필 시도
   4b. 실패 시 TickerStatsCache → mu/sigma 계산
       → SyntheticPriceGenerator → 가상 데이터 생성
5단계: 유효 시작일 재계산 후 반환
```

**반환값:** `{data_start, n_cases, synthetic_info, backfilled}`

---

## 5. 핵심 시뮬레이션 엔진

### 5.1 SimulationConfig (`modules/config/simulation_config.py`)

시뮬레이션의 모든 파라미터를 담는 불변 데이터클래스.

```python
@dataclass
class SimulationConfig:
    start_date:           str           # 시작일
    end_date:             str           # 종료일
    tickers:              List[str]     # 종목 리스트
    target_weights:       Dict[str, float]  # 목표 비중 (합 = 1.0)
    initial_capital:      float         # 초기 자본
    monthly_contribution: float = 0     # 월 납입금
    withdrawal_amount:    float = 0     # 월 인출금
    dividend_mode:        str = "reinvest"  # reinvest / cash / withdraw
    rebalance_frequency:  str = "monthly"
    inflation:            float = 0.0   # 연간 인플레이션율
```

---

### 5.2 SimulationLoop (`modules/simulation/simulation_loop.py`)

**일별(trading day) 처리 순서:**

```
for date in dates:
  1. price_dict 조회 (numpy 배열에서 해당 날짜 종가 추출)
  2. 인플레이션 경과월 업데이트
  3. [첫날만] initial_capital → CashAllocator.allocate_cash()
  4. DividendEngine.process()
      → 보유수량 × DPS → portfolio.cash += dividend_cash
      → dividend_mode='withdraw' 시 portfolio.cash -= dividend_total
  5. ContributionEngine.process()
      → 새 월이면 portfolio.cash += monthly_contribution
  6. CashAllocator.allocate_cash()  (납입 직후)
      → 납입금을 바로 목표 비중대로 투자
  7. WithdrawalEngine.process()
      → 새 월이면 인플레이션 조정 후 인출
      → 현금 부족 시 over-weight 포지션 순으로 매도
  8. PeriodicRebalance.should_rebalance()
      → True: OrderExecutor.execute_orders()
  9. CashAllocator.allocate_cash()  (배당 재투자 + 리밸런싱 후 잔여 현금 정리)
 10. HistoryRecorder.record()
```

**핵심 최적화:**
```python
# 루프 시작 전 numpy 배열 캐싱 (dict lookup 대신 직접 인덱싱)
price_array[ticker] = df["close"].values
valid_index[ticker] = df.index
```

---

### 5.3 Portfolio + Position (`modules/core/`)

**Portfolio:**
```python
class Portfolio:
    cash: float
    positions: Dict[str, Position]

    buy(ticker, quantity, price)     # cash -= cost, position.buy()
    sell(ticker, quantity, price)    # cash += proceeds, position.sell()
    total_value(price_dict)          # cash + Σ(quantity × price)
    current_weights(price_dict,      # 현재 비중 계산 (현금 포함/제외 선택)
                    include_cash=True)
```

**Position:**
```python
class Position:
    quantity:     float   # 보유 수량
    avg_price:    float   # 가중평균 매입가
    realized_pnl: float   # 누적 실현손익

    buy(qty, price)     # avg_price 가중평균 업데이트
    sell(qty, price)    # realized_pnl += (price - avg_price) × qty
    market_value(price) # quantity × price
    unrealized_pnl(price) # (price - avg_price) × quantity
```

---

### 5.4 OrderExecutor (`modules/execution/order_executor.py`)

**목표 비중 기반 주문 실행:**

```
orders = {ticker: target_value - current_value}
  → 음수 = 매도, 양수 = 매수

실행 순서:
  1. 매도 먼저 → 현금 확보
  2. 매수 → 확보된 현금으로 진행

정수 수량 제약: quantity = floor(abs(order_value) / price)
```

---

### 5.5 CashAllocator (`modules/execution/cash_allocator.py`)

잔여 현금을 목표 비중에 맞게 Greedy 방식으로 배분합니다.

```
1차 패스 - deficit 채우기:
  deficit[t] = total_value × weight[t] - current_value[t]
  deficit 내림차순 정렬 후 순차 매수

2차 패스 - 1원 단위 잔여 처리:
  while cash > 0:
    deficit 재계산 → 가장 부족한 종목에 1주 매수
    price > cash 이면 중단
```

---

### 5.6 WithdrawalEngine (`modules/simulation/withdrawal_engine.py`)

**인플레이션 반영 인출:**

```python
adjusted = base_amount × (1 + inflation/12)^elapsed_months
```

**매도 순서 (현금 부족 시):**
1. 현재 비중과 목표 비중의 차이(`overweight`) 계산
2. **초과 보유량이 가장 많은 순으로** 매도
3. `ceil(needed / price)` 수량으로 한 번에 처리 (잔여 현금 최소화)

---

### 5.7 DividendEngine (`modules/simulation/dividend_engine.py`)

```python
dividend_cash = DPS × position.quantity  # DPS: 주당 배당금
portfolio.cash += dividend_cash          # 모든 모드에서 일단 현금 입금

# withdraw 모드: SimulationLoop에서 cash -= dividend_total 차감
```

---

### 5.8 HistoryRecorder (`modules/simulation/history_recorder.py`)

일별로 포트폴리오 전체 상태를 기록합니다.

**기록 컬럼:**
```
date, portfolio_value, asset_value, cash, dividend_income, cash_flow,
{ticker}_value, {ticker}_quantity, {ticker}_dividend, {ticker}_weight
```

`cash_flow`: 해당 월의 납입(+)/인출(-)  → MWR(화폐가중수익률) 계산에 사용

---

## 6. 리밸런싱 전략

### BaseRebalanceStrategy (`modules/rebalance/base_strategy.py`)

```python
orders[t] = (total_value × target_weight[t]) - current_value[t]
```

### PeriodicRebalance (`modules/rebalance/periodic.py`)

**판단 조건 (우선순위 순):**

| 조건 | 설명 |
|---|---|
| 최초 거래 | 항상 True (last_rebalance가 None) |
| 밴드 리밸런싱 | `∣current_weight - target_weight∣ > drift_threshold` |
| 월별 (`monthly`) | 월이 바뀌면 |
| 분기별 (`quarterly`) | 월이 바뀌고 `month % 3 == 1` (1·4·7·10월) |
| 연간 (`yearly`) | 연이 바뀌면 |
| 없음 (`None`) | 항상 False |

---

## 7. 은퇴 계획 모듈

### 7.1 전체 파이프라인

```
사용자 입력: 티커·비중·초기자본·납입금·적립기간·인출금·인출기간·인플레이션

[DataPreparer]
  → 데이터 준비 (백필 + 합성)

[AccumulationAnalyzer]
  → 적립기 롤링 시뮬레이션
  → end_value 분포 (30~수백 케이스)

[RetirementPlanner]
  → 11개 percentile(p5,p10,p20,...,p90,p95) 추출
  → 각 percentile을 initial_capital로 WithdrawalAnalyzer 실행
  → 11개 성공률 평균 = 전체 생존율
  → 종료자산 분위수 계산

JSON 응답: accumulation_summary, sample_results, combined_summary, message
```

---

### 7.2 AccumulationAnalyzer (`modules/retirement/accumulation_analyzer.py`)

**롤링 윈도우 병렬 실행:**
```python
windows = [(start, start+years, run_id) for start in date_range(step=3M)]
Pool(N_WORKERS=8).map(_run_acc_case, task_args)
```

**합성 케이스 보충 (실제 케이스 < MIN_CASES=30):**
```python
mu, sigma = 실제 데이터에서 추출 (없으면 fallback: 7%/yr, 15%/yr)
_simulate_synthetic_case() → GBM + Student-t(df=5)
```

**계산 지표 (history DataFrame 기반):**

| 지표 | 계산 방법 |
|---|---|
| **CAGR** | MWR 우선, 없으면 `(end/total_contribution)^(1/years) - 1` |
| **MDD** | `min((pv - pv.cummax()) / pv.cummax())` |
| **Sharpe** | `mean(daily_ret) / std(daily_ret) × √252` |
| **Sortino** | `mean(daily_ret) / downside_std × √252` |
| **Calmar** | `CAGR / abs(MDD)` |
| **MWR** | Newton-Raphson IRR (현금흐름 기반 수익률) |
| **배당 CAGR** | 연간 DPS 기반 성장률 (fully-completed 연도만) |
| **취득가 배당수익률** | `last_year_dividend / total_contribution` |

**MWR 계산 상세 (Newton-Raphson IRR):**
```python
# cash_flow: 납입(+) / 최종 포트폴리오가치(+) / 인출(-)
# 월별 IRR → 연환산
for _ in range(200):  # 최대 200회 반복
    npv  = Σ cf_i / (1+rate)^i
    dnpv = Σ -i × cf_i / (1+rate)^(i+1)
    rate -= npv / dnpv
mwr = (1 + rate)^12 - 1
```

---

### 7.3 WithdrawalAnalyzer (`modules/retirement/withdrawal_analyzer.py`)

AccumulationAnalyzer와 동일한 병렬 롤링 구조. 인출기 특화 지표 계산.

**케이스별 메트릭:**

| 지표 | 설명 |
|---|---|
| `success` | 기간 종료 시 포트폴리오 > 0 |
| `end_value` / `end_value_ratio` | 종료 자산 / 초기 자본 대비 비율 |
| `years_to_depletion` | 고갈까지 연수 (성공 시 = withdrawal_years) |
| `mdd` | 인출기 최대 낙폭 |
| `total_dividend` | 인출기 전체 수령 배당금 |
| `withdrawal_coverage` | 배당금 / 전체 인출금 (배당이 인출을 얼마나 커버하나) |
| `sequence_risk` | 전반기 CAGR - 후반기 CAGR (순서 위험) |
| `dividend_mdd` | 배당금의 연간 최대 낙폭 |

**성공률:** `sum(case["success"]) / len(cases)`

---

### 7.4 RetirementPlanner (`modules/retirement/retirement_planner.py`)

11개 percentile 샘플링 방법:

```python
SAMPLE_PERCENTILES = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95]

acc_values = accumulation_analyzer.run()["distribution"]["end_value"]["values"]
for pct in SAMPLE_PERCENTILES:
    initial_capital = np.percentile(acc_values, pct)
    wd_result = WithdrawalAnalyzer(initial_capital=initial_capital, ...).run()
    results.append({"percentile": pct, "success_rate": wd_result["success_rate"], ...})

# 전체 생존율 = 11개 성공률의 산술 평균
survival_rate = mean([r["success_rate"] for r in results])
```

---

## 8. 배당 시뮬레이터

### DividendSimulator (`modules/dividend_simulator.py`)

**목적:** 목표 월배당을 달성하기 위한 3가지 변수(시드·납입·기간) 중 하나를 역산

**핵심 메서드:**

| 메서드 | 동작 |
|---|---|
| `get_probability(seed, monthly, years, target)` | 달성 확률 반환 |
| `get_probability_curve(seed, monthly, years, targets[])` | 목표 배열의 확률 커브 |
| `solve(target, probability, seed, monthly, years)` | None인 변수 역산 |
| `run_scenario(target, probability, seed_cfg, monthly_cfg, years_cfg)` | 시나리오 매트릭스 |

**`solve()` 로직 - None 개수에 따라 분기:**
- None=0: `get_probability()` 호출
- None=1: 해당 변수 역산 + 확률 커브 반환
- None=2: 등위곡선(isocurve) 반환
- None=3: ValueError

**앵커 탐색 알고리즘:**
```
1. 고정 스텝 8번 스윕 (선형 탐색)
2. 못 찾으면 지수 탐색으로 범위 확장
3. 로지스틱 피팅으로 정확한 임계값 추출
```

**로지스틱 피팅 (`_logistic_fit`):**
```python
logit(p) = log(p / (1-p))
선형 회귀: logit(prob) = k * x + b
→ x = (logit(target_prob) - b) / k
```

**시뮬레이션 루프:**
```
월별 반복:
  1. monthly 납입 → 비중대로 매수 (searchsorted로 O(log n) 조회)
  2. 배당 이벤트 처리 (itertuples로 3~5배 빠름)
     a. 세금 차감 (TaxEngine 연결 시)
     b. reinvest 모드: 배당금으로 추가 매수
  3. 마지막 1년 배당 합계 추적 → 반환값
```

**케이스 보충 전략:**
- 실제 롤링 케이스 < 30개 → `_run_synthetic_rolling()`
- 실제 DPS 통계에서 div_yield_mean/std, price_return_mean 추출
- GBM으로 자산가치 경로 생성 → 배당수익률 적용

---

## 9. 세금 엔진

### TaxEngine (`modules/sim/tax_engine.py`)

**계좌 유형 × 지역 세율:**

| 계좌 \ 지역 | KR 배당 | US 배당 | 양도차익 |
|---|---|---|---|
| **일반** | 15.4% | 15% | 해외 22% (250만 공제) |
| **ISA** | 0% (운용중) | 0% (운용중) | 0% |
| **연금** | 0% (과세이연) | 0% (과세이연) | 0% |

**금융소득 종합과세:**
- 연간 금융소득 합계 > 2,000만원 → 초과분 근로소득에 합산
- 누진세율 적용 후 원천징수 기납부분 차감

**누진세율표:**
```
~1,200만원:  6%
~4,600만원: 15%
~8,800만원: 24%
~1.5억원:   35%
~3억원:     38%
~5억원:     40%
5억원 초과: 42%
```

**ISA 만기 정산:**
- 일반형: 200만원 비과세, 초과분 9.9%
- 서민형: 400만원 비과세, 초과분 9.9%
- 중도해지: 15.4% 일반과세

**연금 수령:**
- 연금 형태: 나이별 3.3~5.5% (55~70세: 5.5%, 70~80세: 4.4%, 80세+: 3.3%)
- 일시금/중도해지: 16.5%

**절세매매 (Tax Loss Harvesting):**
- 연말 손익통산 → 순손익에 대해서만 과세
- 250만원 공제 후 22% 적용

---

## 10. 인증 시스템

### AuthManager (`modules/auth_manager.py`)

Google OAuth 2.0 기반 사용자 인증.

**인증 플로우:**
```
/auth/google
  → google.authorize_redirect()
  → Google 계정 선택
/auth/google/callback
  → token 수신 → userinfo 추출
  → get_or_create_user(google_id, email, name, picture)
  → session['user_id'] = user['id']
  → redirect('/')
```

**DB 구조 (`data/private/users.db`):**
```sql
users(id, google_id UNIQUE, email, name, picture, created_at, last_login)
user_settings(user_id PK FK, tax TEXT JSON, updated_at)
```

**세금 설정:** 계좌 유형·국가·세율 등을 JSON으로 `user_settings.tax`에 저장

**템플릿 자동 주입:** `@app.context_processor` → 모든 템플릿에 `user` 변수 노출

---

## 11. API 엔드포인트

### 시장 데이터

| 경로 | 메서드 | 설명 |
|---|---|---|
| `/api/market` | GET | S&P500·NASDAQ·KOSPI·금·USD/KRW 현재값 + 스파크라인 |
| `/api/search?q=` | GET | 티커/이름 퍼지 검색 (최대 20개) |

**`/api/market` 응답 구조:**
```json
[
  {"id": "sp500", "name": "S&P 500", "value": "5,832", "change": "+0.42%",
   "up": true, "spark": [5100, 5150, ..., 5832], "tag": "S&P"},
  ...
]
```

---

### 투자 계산기

**`POST /api/calculator/run`**

```json
// 요청
{
  "tickers": [{"code": "SPY", "weight": 0.6}, {"code": "QQQ", "weight": 0.4}],
  "initial_capital": 10000000,
  "monthly_contribution": 500000,
  "years": 20,
  "rebal_mode": "quarterly",    // none / monthly / quarterly / yearly / band
  "band_width": 0.05,           // band 모드 시 drift threshold
  "dividend_mode": "reinvest"   // reinvest / cash / withdraw
}

// 응답
{
  "cases": [{"run_id": 1, "start": "2005-01-01", "end": "2025-01-01",
             "end_value": 150000000, "cagr": 0.089, "mdd": -0.52}],
  "cases_count": 82,
  "distribution": {
    "cagr":  {"p10": 0.06, "p25": 0.075, "p50": 0.09, "p75": 0.11, "p90": 0.14},
    "mdd":   {"p50": -0.42, ...},
    "sharpe": {...}
  }
}
```

---

### 배당 계산기

| 경로 | 메서드 | 설명 |
|---|---|---|
| `/api/dividend-target/probability` | POST | 특정 조건의 달성 확률 |
| `/api/dividend-target/probability-curve` | POST | 목표 배열에 대한 확률 커브 |
| `/api/dividend-target/solve` | POST | 시드/납입/기간 역산 |
| `/api/dividend-target/scenario` | POST | 2변수 시나리오 매트릭스 |

**`/api/dividend-target/solve` 요청 (시드 역산 예시):**
```json
{
  "tickers": [{"code": "SCHD", "weight": 1.0}],
  "target_monthly_div": 1000000,
  "probability": 0.90,
  "seed": null,           // ← 역산할 변수 (null)
  "monthly": 500000,
  "years": 20,
  "dividend_mode": "reinvest"
}
```

---

### 은퇴 설계

**`POST /api/retirement/run`** — 적립기 + 인출기 통합

```json
// 요청
{
  "tickers": [{"code": "SCHD", "weight": 0.6}, {"code": "QQQ", "weight": 0.4}],
  "initial_capital": 0,
  "monthly_contribution": 1000000,
  "accumulation_years": 25,
  "dividend_mode": "reinvest",
  "monthly_withdrawal": 3000000,
  "withdrawal_years": 30,
  "inflation": 0.02,
  "target_percentile": 0.90
}

// 응답
{
  "accumulation_summary": {"end_value": {"p50": 1200000000, ...}},
  "sample_results": [
    {"percentile": 50, "initial_capital": 1200000000,
     "success_rate": 0.87, "end_value_p50": 800000000}
  ],
  "combined_summary": {"survival_rate": 0.82, ...},
  "message": {"text": "...", "is_safe": false},
  "data_start": "2000-01-01",
  "synthetic_info": {},
  "backfilled": []
}
```

**`POST /api/retirement/withdrawal`** — 인출기만 단독 실행

---

## 12. 핵심 계산 알고리즘

### CAGR (연평균 복리 수익률)

```python
# 1순위: MWR (월납입 있을 때)
mwr = (1 + monthly_irr)^12 - 1

# 2순위: 총납입금 대비
cagr = (end_value / (initial + monthly × months))^(1/years) - 1

# 3순위: 초기자본 대비 (납입 없을 때)
cagr = (end_value / start_value)^(1/years) - 1
```

### MDD (최대 낙폭)

```python
cummax = portfolio_value.cummax()
drawdown = (portfolio_value - cummax) / cummax
mdd = drawdown.min()   # 음수 (예: -0.45 = 45% 최대 낙폭)
```

### MWR (화폐가중수익률) — Newton-Raphson IRR

```python
# cash_flow 시계열: 납입(-), 인출(+), 최종자산(+)
cfs = [-c for c in contributions] + [final_value]

rate = 0.01  # 초기값
for _ in range(200):
    npv  = Σ cfs[i] / (1+rate)^i
    dnpv = Σ -i × cfs[i] / (1+rate)^(i+1)
    if abs(dnpv) < 1e-12: break
    rate_new = rate - npv / dnpv
    if abs(rate_new - rate) < 1e-8: break
    rate = rate_new

mwr = (1 + rate)^12 - 1   # 월간 → 연환산
```

### GBM + Student-t 합성 수익률

```python
t_scale = sqrt(df / (df - 2))        # df=5 → t_scale ≈ 1.291
raw = standard_t(df=5, size=n)
rets = (raw / t_scale) * sigma + mu  # 스케일 조정 → E[X^2] = sigma^2
```

### Sortino 비율

```python
downside = daily_returns[daily_returns < 0]
downside_vol = downside.std() × √252
sortino = mean(daily_returns) / downside_vol × √252
```

### 배당 CAGR

```python
# 완전한 연도만 사용 (12개월 데이터 있는 연도)
annual_dps = (연간배당 / 연평균보유수량).by_year
dividend_cagr = (annual_dps[-1] / annual_dps[0])^(1/(n_years-1)) - 1
```

---

## 13. 데이터베이스 스키마

### price_daily.db

```sql
CREATE TABLE price_daily (
    code    TEXT NOT NULL,
    date    TEXT NOT NULL,
    open    REAL,
    high    REAL,
    low     REAL,
    close   REAL NOT NULL,
    volume  REAL,
    PRIMARY KEY (code, date)
);

CREATE TABLE corporate_actions (
    code      TEXT NOT NULL,
    date      TEXT NOT NULL,
    dividend  REAL DEFAULT 0,   -- 주당 배당금 (원 또는 달러)
    split     REAL DEFAULT 1,   -- 주식분할 비율
    PRIMARY KEY (code, date)
);
```

### index_master.db

```sql
CREATE TABLE index_daily (
    code  TEXT NOT NULL,
    date  TEXT NOT NULL,
    close REAL NOT NULL,
    PRIMARY KEY (code, date)
);
-- 코드 예시: ^GSPC, ^NDX, KS200, GC=F, USD/KRW, DGS30, KRX_GOLD
```

### users.db

```sql
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    google_id   TEXT UNIQUE NOT NULL,
    email       TEXT,
    name        TEXT,
    picture     TEXT,
    created_at  TEXT NOT NULL,
    last_login  TEXT NOT NULL
);

CREATE TABLE user_settings (
    user_id    INTEGER PRIMARY KEY,
    tax        TEXT,           -- JSON 직렬화 세금 설정
    updated_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## 14. 성능 최적화

| 최적화 기법 | 위치 | 효과 |
|---|---|---|
| **NumPy 배열 캐싱** | SimulationLoop | pandas `.loc` 반복 회피 → 3~5배 향상 |
| **multiprocessing.Pool(8)** | AccumulationAnalyzer, WithdrawalAnalyzer | 롤링 케이스 병렬 처리 |
| **워커 전역 상태** (`_init_worker`) | Pool initializer | price_data 재전송 없이 공유 → pickle 오버헤드 최소화 |
| **itertuples()** | DividendSimulator | `iterrows()` 대비 3~5배 빠름 |
| **searchsorted()** | DividendSimulator | 날짜 인덱스 O(log n) 조회 |
| **price_data ffill 전처리** | PriceDataLoader | 루프 내 결측값 처리 불필요 |
| **전체 범위 1회 로드** | AccumulationAnalyzer | 각 케이스별 DB 쿼리 없이 슬라이싱만 수행 |
| **PortfolioEngine 캐시** | PortfolioEngine._price_cache | 같은 범위 재실행 시 로드 스킵 |
| **_sim_cache** | DividendSimulator | 동일 파라미터 반복 계산 방지 |
| **순차 fallback** | _run_parallel | Pool 실패 시 자동 순차 실행 (Windows freeze_support) |

---

## 15. 의존성

주요 패키지:

```
Flask>=3.0.0          웹 프레임워크
Authlib>=1.3.0        Google OAuth 2.0 클라이언트
python-dotenv>=1.0.0  환경변수 관리

pandas==2.3.3         DataFrame 처리
numpy==2.4.2          수치 연산
scipy>=1.17.1         통계·최적화

yfinance==1.2.0       미국 주식·ETF·지수 데이터
FinanceDataReader     KRX·한국 금융 데이터

plotly==6.5.2         인터랙티브 차트
matplotlib==3.10.8    정적 차트
altair==6.0.0         선언형 시각화

python-dateutil==2.9.0  상대날짜 계산 (relativedelta)
pytz==2025.2          시간대 처리
gunicorn>=21.2.0      프로덕션 WSGI 서버
```

---

## 16. 실행 방법

### 환경 변수 (`.env`)

```bash
FLASK_SECRET_KEY=your-secret-key-here
GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
```

### 실행

```bash
# 가상환경 생성 (최초 1회)
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 서버 실행
python app.py
# → http://localhost:5000
```

### 데이터 초기화 (최초 1회)

```python
# price_daily.db 초기화 후 주요 ETF 백필
from modules.backfill_engine import BackfillEngine
engine = BackfillEngine(verbose=True)
engine.backfill_all()
```

---

## 설계 패턴 요약

| 패턴 | 위치 | 내용 |
|---|---|---|
| **팩토리 패턴** | `_make_strategy_factory()` | 리밸런싱 전략 지연 생성 |
| **전략 패턴** | `BaseRebalanceStrategy` + `PeriodicRebalance` | 리밸런싱 알고리즘 교체 가능 |
| **의존성 주입** | `PortfolioEngine(loader)`, `SimulationLoop(engines...)` | 각 엔진 독립 교체 |
| **커맨드 패턴** | `OrderExecutor.execute_orders(orders)` | 주문을 값 객체로 전달 |
| **옵저버 패턴** | `HistoryRecorder` | 시뮬레이션 루프 상태 수집 |
| **템플릿 메서드** | `AccumulationAnalyzer` / `WithdrawalAnalyzer` | 롤링 구조 공유, 지표 계산 오버라이드 |
| **캐시 패턴** | `PortfolioEngine._price_cache`, `DividendSimulator._sim_cache` | 메모이제이션 |
| **파이프라인** | `DataPreparer.prepare()` | 4단계 데이터 준비 체인 |
| **오케스트레이터** | `RetirementPlanner` | 여러 분석기를 조합하는 조율 계층 |
