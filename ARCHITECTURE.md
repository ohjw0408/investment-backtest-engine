# 투자 백테스트 엔진 - ARCHITECTURE.md
Version: 1.0 (Stable Baseline)
목적: 리빌딩 참사 방지 + 레이어 명확화

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