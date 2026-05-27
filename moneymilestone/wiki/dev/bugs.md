---
updated: 2026-05-28
tags: [dev, bug]
---

# 버그 목록

**에이전트: 버그 발견 시 여기에 추가. 수정 시 상태 업데이트.**

형식: `| 버그 | 원인 | 파일 | 날짜:커밋 | 상태 |`

---

## 활성 버그 목록

| 버그 | 원인 | 파일 | 상태 |
|---|---|---|---|
| DJUSDIV100 데이터 부족 | SCHD vs TIGER 미국배당다우존스 결과 불일치 | `modules/backfill_engine.py`, `data/meta/index_master.db` | ⏳ Track A에서 수정 예정 |
| `_fetch_fred()` 미정의 | index_loader에서 FRED 데이터 로드 실패 | `modules/index_loader_develop.py` | ⏳ Track A에서 수정 예정 |
| 백필 실패 코드가 완료 처리됨 | 실패한 ETF가 캐시에서 완료로 표시됨 | `modules/price_loader.py` | ⏳ Track A에서 수정 예정 |
| 배당 시뮬 미완료 연도 포함 | 현재 연도(작년~현재) 통계를 끝난 것처럼 포함 | `modules/dividend_simulator.py` | ⏳ Track A에서 수정 예정 |

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
| KRX 금현물 시세 오래된 데이터 | 자동 갱신 없음, 수동 실행만 지원 | Celery Beat 태스크 추가, 평일 16:30 KST 자동 실행 | `d56c5ee` | ✅ |
| 시장 지수 thundering herd | 캐시 만료 시 동시 요청이 모두 yfinance 호출 | Redis SETNX 락으로 1개 요청만 fetch | `d56c5ee` | ✅ |

---

## 미결 이슈 (버그는 아니지만 확인 필요)

| 이슈 | 상태 | 비고 |
|---|---|---|
| `volume=0`으로 백필/가격 오류 | ⚠️ 미확인 | 일부 종목에서 가격 대신 배당 표시 가능성 |
| provenance 테이블 없음 | ⚠️ 미확인 | 합성 데이터 출처 적재 제거됨 |
| ISA 계산기 Runner 통일 | ⏳ 미완료 | Phase 3에서 처리 |
| `TaxedDividendEngine._ytd_income` 초기값 0 | ⏳ 미완료 | `other_financial_income` 연동 필요 |
| `modules/sim/tax_engine.py` 덮어씀 | ⏳ 미완료 | Phase 2c 이후 정리 예정 |
| 은퇴 시뮬에도 짧은 히스토리 문제 있는지 | ⚠️ 확인 필요 | 배당 계산기와 동일 구조일 수 있음 |
