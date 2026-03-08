# 투자 백테스트 엔진 - ARCHITECTURE.md
Version: 1.0 (Stable Baseline)
목적: 리빌딩 참사 방지 + 레이어 명확화
문서 아래에 있는 내용이 최신 내용이다. 참고 할 수 있도록.
-------------------------------------------------
## 🎯 프로젝트 최종 목표

- 증권사 제안 가능한 자산운용 시뮬레이션 시스템 구축
- 수량 기반 포트폴리오 엔진
- 전략 분리 구조
- 세금/계좌 확장 가능 구조
- 장기 데이터 (1950~) 확장 가능 구조

-------------------------------------------------
# 🧱 전체 시스템 레이어 구조

이 프로젝트는 5개의 레이어로 구성된다.

1️⃣ Data Infrastructure Layer  
2️⃣ Metadata Infrastructure Layer  
3️⃣ Analytical Engine (1세대, 수익률 기반)  
4️⃣ Simulation Engine (2세대, 수량 기반)  
5️⃣ Dev / Utility Layer  

각 레이어는 서로 책임이 다르며, 섞지 않는다.

-------------------------------------------------
# 1️⃣ Data Infrastructure Layer

## price_loader.py
역할:
- SQLite 기반 가격 캐시
- 요청 구간만 API 호출
- 데이터 영속성 유지

하지 않는 것:
- 수익률 계산
- 리밸런싱 판단
- 세금 계산

상태:
- 현재 모든 분석 엔진의 핵심 의존성
- 삭제 금지


## data_engine.py
역할:
- FDR 기반 장기 시계열 다운로드
- ETF 상장 전 지수 백필링
- 환율 통합
- 통합 수익률 생성

하지 않는 것:
- 포트폴리오 상태 관리
- 리밸런싱
- 세금 계산

상태:
- 장기 확장용 데이터 엔진
- 현재 2세대 엔진과 직접 연결되어 있지 않음
- 삭제 금지


-------------------------------------------------
# 2️⃣ Metadata Infrastructure Layer

## db_builder.py
역할:
- symbol_master.db 구축
- 미국 주식 + ETF 수집
- 중복 제거

## info_engine.py
역할:
- 종목 검색
- 퍼지 검색
- 종목 메타데이터 조회

하지 않는 것:
- 가격 계산
- 수익률 계산
- 리밸런싱
- 세금 계산

상태:
- UI/검색 전용 레이어
- 분석 엔진과 독립


-------------------------------------------------
# 3️⃣ Analytical Engine (1세대, 수익률 기반)

목적:
- 빠른 벡터 기반 분석
- 전략 비교
- 지표 계산
- sanity check 용

## backtest_engine.py
단일 종목 분석 엔진
포함 지표:
- Total Return
- CAGR
- MDD
- Volatility
- Sharpe

수량 추적 없음
세금 없음
리밸런싱 없음


## portfolio_engine.py
다중 종목 가중치 기반 분석
포함:
- 자산 기여도
- MDD 구간 분석
- 회복일 계산

수량 추적 없음
세금 없음
리밸런싱 없음

⚠️ 주의:
지표 계산 로직은 나중에 PerformanceEngine으로 분리 가능.


-------------------------------------------------
# 4️⃣ Simulation Engine (2세대, 수량 기반)

목적:
- 실제 운용 시뮬레이션
- 리밸런싱 전략 적용
- 향후 세금/거래비용 반영

## core/

### position.py
역할:
- 개별 자산 수량 추적
- 평균단가 계산
- 실현/미실현 손익 계산

하지 않는 것:
- 세금 계산
- 전략 판단


### portfolio.py
역할:
- 현금 관리
- Position 관리
- 총 자산 계산
- 비중 계산 (현금 포함/미포함 옵션)

하지 않는 것:
- 세금 계산
- 리밸런싱 전략 판단


## rebalance/

### base_strategy.py
리밸런싱 전략 인터페이스 정의


### periodic.py
목표 비중 기반 단순 리밸런싱
- 금액 기준 주문 차이 계산
- 수량 변환은 아직 없음


## tax/
현재는 base_tax.py 인터페이스만 존재
세금 계산은 아직 구현하지 않음


-------------------------------------------------
# 5️⃣ Dev / Utility Layer

## plot_result.py
- BacktestEngine 결과 시각화
- 개발 테스트용

## analyzer.py
- FDR 기반 단순 가격 조회
- 향후 DataEngine으로 통합 가능


-------------------------------------------------
# 🔥 설계 원칙 (절대 깨지 말 것)

1. 상태(Core)와 전략(Rebalance)을 분리한다.
2. 세금 계산은 Core에 포함하지 않는다.
3. 데이터 레이어는 계산 레이어와 분리한다.
4. 1세대 분석 엔진은 삭제하지 않는다.
5. 수량 기반 엔진은 기존 엔진을 덮어쓰지 않는다.
6. 레이어 간 책임을 절대 섞지 않는다.


-------------------------------------------------
# 📍 현재 단계

✅ Position 구현 완료  
✅ Portfolio 구현 완료  
✅ 현금 포함 비중 계산 구현 완료  
✅ Periodic 리밸런싱 금액 계산 완료  
✅ 1세대 엔진 안정  

아직 구현하지 않은 것:
- 금액 → 수량 변환
- 주문 실행 로직
- 거래 비용
- 세금 정책
- Threshold 전략
- Hybrid 전략

## 2026-03-02

- Repository flattened (removed nested investment_app_v2 folder)
- Standardized Python 3.11 environment
- Enforced venv usage
- requirements.txt is single source of truth


## ---2026-03-04

# 📁 Data Directory Structure

프로젝트는 데이터 레이어를 다음 두 종류로 분리한다.

## data/meta/

정적 메타데이터 저장 위치

포함 파일:

* symbol_master.db
  종목 마스터 데이터베이스
  (티커, 이름, 시장, 국가, ETF 여부 등)

* us_etf_list.csv
  ETF 초기 데이터 소스
  db_builder가 symbol_master 생성 시 사용

특징:

* 정적 데이터
* Git에 포함됨
* 프로젝트 실행에 필수

## data/price_cache/

시장 가격 캐시 저장 위치

포함 파일:

* price_daily.db
  SQLite 기반 가격 캐시
  price_loader.py가 자동 생성

저장 데이터:

* code
* date
* close
* dividend

특징:

* 실행 중 자동 생성
* API 호출 최소화를 위한 캐시
* Git에서 제외 (.gitignore)

## 데이터 흐름

yfinance API
↓
price_loader.py
↓
SQLite cache (price_daily.db)
↓
data_engine.py
↓
장기 백테스트 데이터 생성 (백필링 포함)

## 설계 목적

1. 메타데이터와 시장 데이터를 분리
2. 가격 캐시는 Git 저장소에서 제외
3. 데이터 레이어와 분석 엔진을 분리
4. 장기 백테스트용 synthetic series 생성 기반 마련

# QuantMaster Architecture

## 1. Data Layer

가격 데이터를 외부 API에서 가져오고 로컬 캐시에 저장한다.

modules
 ├─ price_loader.py
 └─ data_engine.py

price_loader
- Yahoo Finance API 호출
- price_daily.db 캐싱
- 필요한 기간만 다운로드

data_engine
- 백필링
- 환율 처리
- 데이터 정규화


--------------------------------------------

## 2. Metadata Layer

종목 메타데이터 관리

modules
 ├─ db_builder.py
 └─ info_engine.py

symbol_master.db 구조

symbols
- code
- name
- market
- country
- is_etf
- underlying_symbol

underlying_symbol은 ETF 백필링에 사용됨


--------------------------------------------

## 3. Portfolio State Layer

포트폴리오 상태를 관리

modules/core

 ├─ portfolio.py
 └─ position.py

Position
- quantity
- avg_price
- realized_pnl

Portfolio
- cash
- positions
- total_value
- weight calculation


--------------------------------------------

## 4. Execution Layer

주문 실행

modules/execution

 └─ order_executor.py

기능

- 매수
- 매도
- 포트폴리오 업데이트


--------------------------------------------

## 5. Strategy Layer

리밸런싱 전략

modules/rebalance

 ├─ base_strategy.py
 └─ periodic.py

BaseRebalanceStrategy

- target_weights
- generate_orders()


--------------------------------------------

## 6. Backtest Engines

두 종류의 백테스트 엔진 존재

### 1️⃣ BacktestEngine

단일 자산 분석

metrics

- Total Return
- CAGR
- MDD
- Volatility
- Sharpe

--------------------------------------------

### 2️⃣ PortfolioEngine

멀티 자산 포트폴리오 분석

vectorized 방식

기능

- portfolio return
- contribution
- MDD analysis
- recovery analysis


--------------------------------------------

## 7. Analyzer Layer

분석 도구

modules/analyzer.py

기능

- 자산 기여도
- drawdown 분석
- rolling 분석


--------------------------------------------

## 8. Future Expansion

예정 기능

- ETF 백필링
- dividend reinvestment
- tax simulation
- advanced rebalance strategies

---

# Analyzer Layer (New)

A new analyzer layer has been added to evaluate portfolio performance
and retirement sustainability.

## PortfolioAnalyzer

Calculates core portfolio statistics from simulation history.

Metrics:

- CAGR
- Maximum Drawdown (MDD)
- Volatility
- Sharpe Ratio
- Drawdown period analysis (start / bottom / recovery)

Input:
Portfolio history DataFrame from PortfolioEngine

Output:
Dictionary containing performance statistics.

---

## RetirementAnalyzer

Simulates retirement withdrawals using historical rolling windows.

Purpose:
Evaluate sustainability of a withdrawal strategy.

Inputs:

- portfolio history
- initial capital
- monthly withdrawal
- simulation years
- inflation

Outputs:

- success probability
- best terminal wealth
- median terminal wealth
- worst terminal wealth

This allows users to evaluate sequence-of-return risk.

---

# Current Engine Flow

PriceLoader  
↓  
PortfolioEngine  
↓  
OrderExecutor  
↓  
Portfolio History  
↓  
Analyzer Layer

    ├ PortfolioAnalyzer  
    └ RetirementAnalyzer

---

# Next Planned Improvements

1️⃣ Store asset-level values in history

Example future structure:


 date
portfolio_value
cash
QQQ_value
TLT_value
QQQ_weight
TLT_weight


This will enable:

- rebalance verification
- asset contribution analysis
- detailed risk decomposition

2️⃣ Dividend reinvestment toggle

3️⃣ Transaction cost model

4️⃣ Tax module

5️⃣ Inflation-adjusted retirement simulation

6️⃣ Large ETF universe support


2026 03 07 추가한 내용
portfolio analyzer, retirement analyzer, portfolio simulation engine 추가

여러가지 테스트를 한번에 진행할 수 있는 파일들을 만듦. ex-test_cash_and_dividend.py,engine_integrity.py 등등

Implement dividend modes (reinvest/cash/withdraw), greedy cash allocator, withdrawal logic and integration tests