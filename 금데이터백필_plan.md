# KRX 금현물 데이터 이중처리 + 백필 계획 (아이디어 기록)

작성: 2026-06-03 (Claude, 오너 스펙). 상태: **Phase 1 완료(서버검증 PASS) · Phase 2 완료(로컬검증 PASS, 서버 미검증).**

> **Phase 2 (2026-06-03 완료):** 금 ETF 상장전 백필 갈래 라우팅. 현물/국제금(411060·0072R0·0064K0·0066W0, unhedged) → KRX_GOLD(KRW/g 네이티브, FX 포함) · 환헤지 선물(132030·319640·139320) → GC=F 유지. KRX_GOLD 빌더를 `price_loader.build_krx_gold_krw_series` 모듈함수로 추출해 backfill_engine 공유. 순수 금만(레버리지·인버스·혼합·금광주·커버드콜 제외 — 오너 결정). 로컬 검증: 현물 1971~·경계점프 ±2.5%이내·test_krx_gold 5+회귀 71 PASS. ⚠️ 서버 배포·실데이터 검증 남음.

---

## 현재 버그 (근본원인 규명됨)

- **KRX_GOLD는 `index_master.db`(index_daily, 지수)에만 존재, `price_daily.db`(거래가격)엔 없음.**
- 계산기/백테스트 시뮬은 `price_loader`가 **price_daily에서 가격 로드** → KRX_GOLD 없음 → 빈 history → `'portfolio_value'` KeyError(단일경로) / "시뮬레이션 날짜가 없습니다"(멀티). **5년 잡아도 안 돎.**
- 즉 KRX_GOLD는 **홈 화면 시세 타일용(지수)으로만** 살아있고, **포트폴리오 보유자산(가격)으로는 미지원.**

## 오너 규칙 (확정)

1. **KRX_GOLD = 위탁 전용.** 금현물계좌에서만 매수 가능 → 프로그램상 **ISA·연금·IRP에선 매수 불가, 무조건 위탁.** → 검증 추가(ISA/연금/IRP에 KRX_GOLD 넣으면 거부).
2. **KRX_GOLD는 지수이자 주식가격 — 이중처리.** index(시세 타일) + price_daily(거래가능 시계열) 둘 다.

## 백필 설계 (오너 스펙)

KRX_GOLD를 **거래가능 가격 시계열**로 만들고, 금현물 ETF들의 상장 전 역사를 2차 백필:

- **KRX_GOLD price_daily 시계열 구축:**
  - 2014~현재: index_master의 KRX 금현물(1g) 가격 사용(이미 2989행 보유).
  - **2014 이전:** 국제 금가격지수 × USD/KRW 환율 → **KRX 금가격 스케일로 규격화(normalize)** 후 경계(2014)에서 이어붙임.
- **금현물 ETF 2차 백필 (ACE 금현물 등):**
  - ETF 상장 전 구간 = KRX_GOLD 가격을 **그 ETF 가격 스케일로 규격화**해서 이어붙임.
  - (배당 ETF 백필이 프록시로 잇는 것과 같은 패턴 — `backfill_engine.py` 참고.)

→ 결과: KRX_GOLD = 장기 거래가능 시계열(국제금×환율 → KRX금), 금현물 ETF = 충분한 백테스트 역사 확보.

## 구현 지점 (추정)

- `modules/backfill_engine.py`: KRX_GOLD 매핑/체인 추가(현재 KRX_GOLD 미처리 → skip).
- `modules/price_loader.py`: KRX_GOLD를 price_daily에 구축(국제금×환율 prefix + KRX gold). `get_price('KRX_GOLD')`가 시계열 반환하도록.
- 검증: KRX_GOLD/USD_KRW/국제금(GC=F?) 데이터 출처 정합 + 규격화 경계 점프 없음(BUG-DIV-3 1181배 점프 전례 — 환율 스케일 주의).
- `account_tax.validate_account_portfolio`: KRX_GOLD가 비-위탁 계좌면 거부.

## 검증 (까다로움)

- **규격화 경계 무점프:** 2014 경계(국제금×환율 ↔ KRX금)·ETF 상장 경계서 가격 연속성(±몇% 이내). BUG-DIV-3(합성 anchor 1181배 점프) 교훈 — 환율 단위 일치 필수.
- KRX_GOLD 위탁 단독 5년/10년 시뮬 정상 종료(에러 없음) + 금 양도세 0(비과세) 유지.
- ISA/연금에 KRX_GOLD → 거부 메시지.
- 금현물 ETF 백필 후 롤링 케이스 수 증가 확인.

## 결정 대기 (오너)

1. 2014 이전 소스: 국제금 = `GC=F`(yfinance) vs 별도 국제금가격지수? (index_master에 GC=F 있음 — 재사용?)
2. 규격화 기준점: 경계일 가격 일치(ratio scaling) vs 수익률 체인?
3. 금현물 ETF 목록(ACE금현물·KODEX골드선물 등 — 선물 ETF는 다름 주의: 금현물 ≠ 금선물).
4. price_daily 구축 시점: 사전 배치 vs `get_price` 최초 호출 시 lazy.

## 단계 제안

1. **(빠른 응급)** KRX_GOLD 위탁 시뮬이 최소한 **돌게**: index_daily(2014+)를 price_daily로 노출 → 'portfolio_value' 에러 해소(2014+ 한정). 위탁-only 검증 추가.
2. **(본작업)** 국제금×환율 pre-2014 백필 + 금현물 ETF 2차 백필 + 규격화 검증.
