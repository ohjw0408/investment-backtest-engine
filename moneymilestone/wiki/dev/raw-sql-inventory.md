# raw SQL 직접 접근 경로 인벤토리 (price_daily / index_daily)

작성: 2026-07-03 (출시완성도 B-2③). PriceLoader(`get_price`)를 우회해 가격 테이블을
직접 읽고/쓰는 경로 전수 목록. **BUG-OVERLAY-SPIKE·BUG-KOSPI-NIGHT-NULL 재발 교훈**:
읽기 마스킹·쓰기 필터는 PriceLoader에만 있으므로, 우회 경로는 오염 데이터를 그대로 만난다.

## 원칙 (신규 코드 체크리스트)

1. **가격 시계열 읽기는 PriceLoader.get_price 경유가 기본.** raw SELECT가 불가피하면
   `close IS NOT NULL` 가드 + 스파이크 가능성 인지(아래 방어망 참조).
2. **price_daily/index_daily에 raw INSERT 금지.** 불가피하면 `_validate_price_rows()`
   (modules/price_loader.py, B-2①) 통과 후 저장 — NaN close·0/음수·미래날짜 차단.
3. 이 문서는 경로 추가/삭제 시 갱신한다 (코드리뷰 체크 항목).

## 상시 방어망 (우회 경로가 만든 오염의 안전망)

| 레이어 | 무엇 | 주기 |
|---|---|---|
| 쓰기 훅 | `_validate_price_rows` — 스파이크·NULL·0/음수·미래날짜 (fetch_from_api·ECOS USD/KRW) | 쓰기 시 |
| beat `purge_price_spikes` | 고립 오틱 행 DELETE self-heal | 매일 10:00 UTC |
| beat `data_integrity_scan` (B-2②) | NULL close 삭제 + USD/KRW·KRX_GOLD·price_daily 신선도 + 합성 손상 스캔 → 오너 알림+Sentry | 매일 10:30 UTC |

## 쓰기 경로 (오염 유입 리스크 — 우선 관리 대상)

| 위치 | 무엇 | 검증 상태 |
|---|---|---|
| `modules/price_loader.py` fetch_from_api → `_insert_ignore` | 주 페치 경로 | ✅ `_validate_price_rows` 훅 (B-2①) |
| `modules/price_loader.py` `_auto_update_usdkrw` | ECOS USD/KRW → index_daily | ✅ 동일 훅 적용 (B-2①) |
| `app.py:~1218` `_compute_portfolio_history` KR 폴백 | yfinance→price_daily INSERT OR REPLACE | ✅ Close dropna 추가 (07-03 — 무결성 beat가 로컬서 NULL 18행 실검출한 유입원) |
| `modules/krx/fetch_krx_stocks.py:100` | KRX 시세→price_daily INSERT OR REPLACE | ⚠️ 자체 검증 없음(KRX 공식 소스라 리스크 낮음, beat 안전망 의존) |
| `modules/krx/fetch_krx_gold.py:117` | KRX 금현물→index_daily (DELETE 후 전량 재삽입) | ⚠️ 동일 |
| `modules/backfill_engine.py` (다수) | 합성/백필 저장 | 합성 전용 — B-1 손상 스캔이 감시 |
| `modules/retirement/synthetic_price_generator.py:119` | price_daily_synthetic 저장 | 합성 전용 테이블(실데이터 비오염) |
| `modules/provenance.py:183` | 백필 롤백 DELETE | 관리용 도구 |
| `modules/datadownlader.py` | SCHD/DJUSDIV 일회성 스크립트 | 레거시 수동 도구 |
| `tasks.py` purge/integrity beat | self-heal DELETE | 방어망 자신 |

## 읽기 경로 (스파이크/NULL 마스킹 우회 — close IS NOT NULL 가드 여부)

| 위치 | 용도 | 비고 |
|---|---|---|
| `app.py:633~689` | 종목 최신가/전일가 배치 조회 | MAX(date) 기반 — NULL행 beat가 제거 |
| `app.py:782, 1205` | min date·포폴 추이 시계열 | 추이는 `close IS NULL` 행 없다는 전제(beat 보장) |
| `app.py:1169, 2381` (외 다수) | USD/KRW 최신값 | LIMIT 1 — 신선도는 beat 감시 |
| `app.py:1194, 1318~1432` | KRX_GOLD 시계열/스파크 | index_daily |
| `app.py:3056` | 심볼 차트 데이터 | |
| `modules/alerts/live_quote.py:70` | 지수 알림 현재가 | `close IS NOT NULL` 가드 ✅ |
| `modules/market_quote_service.py:119,144` | 홈 시장지수 위젯 | BUG-KOSPI-NIGHT-NULL 픽스로 읽기가드 6곳 적용됨 |
| `modules/data_engine.py:46` | 지수 시계열 | |
| `modules/tr_index.py:31` | TR 지수 재구성 | volume 함께 읽음(합성 구분) |
| `modules/dividend_simulator.py:664` / `retirement/withdrawal_analyzer.py:535` | 실데이터 시작일(MIN date, volume>0) | 메타 조회 — 오염 무관 |
| `modules/retirement/data_preparer.py` (다수) / `scenario_data_preparer.py:54` / `synthetic_mvn.py:39` / `ticker_stats_cache.py:101` / `synthetic_price_generator.py:62` | 합성 생성·시뮬 데이터 준비 | 대부분 MIN/MAX 메타 또는 합성 테이블 |

## 히스토리

- 2026-07-03: 최초 작성 (B-2③). B-2① 쓰기 훅·B-2② 무결성 beat와 동시 배포.
