# C1 — 홈 화면 위젯 + 관심목록 + 설정 페이지 (✅ 완료·배포)

2026-06-14 수립. 오너 결정 반영. PHASE4 C1 확장판.

> ✅ **완료·배포·검증 (2026-06-14, 커밋 adc2ae0→2a65515→180c0b2→040a19c).**
> 백엔드(`user_settings.home_widgets` JSON + `/api/home-config` + `/api/watchlist/quotes`), 홈 동적 위젯 렌더
> (모바일 스와이프 캐러셀 / PC 탭+그리드), 설정 페이지 `/settings`(위젯 CRUD·이름·순서·검색모달/프리셋). 검증 = `test_home_widgets.py`
> 16 PASS + 라이브 검증.
>
> **후속 (2026-06-15, 커밋 7394171→8be53b9→6ccf735→ed2ac9d):**
> - **지수 캔들 회귀 복구:** `index_daily`가 종가만이라 지수 캔들 비활성됐던 것. 신규 `index_ohlc`(code,date,OHLCV) 테이블 +
>   `scripts/backfill_index_ohlc.py`(시장지수 12종 yfinance) + `get_symbol_data` 지연 백필(첫 진입 자동적재, 테이블 없으면
>   `CREATE TABLE IF NOT EXISTS`+yfinance, **수동 서버작업 불필요**). 라인=index_daily 유지, 1H=intraday 온디맨드, KRX_GOLD만 close-only.
> - **PC 홈 위젯:** 좁은 `<table>` → `.market-grid` 3칸(큰 값+스파크).
> - **설정 PC:** `.main-content` 2칸그리드 308칸에 끼던 wrap → `grid-column:1/-1` 풀폭 + `#weList` 멀티컬럼.
> - **홈 시세 경량화:** 무거운 `get_symbol_data` → `_wl_recent_closes`(인덱스=index_master 25행/주식=get_price 45일창).
> - **새로고침 버튼(내자산·홈·검색):** 공유 Redis 캐시 + **TTL 15분 고정 = floor**(yfinance 15분 지연과 동일 → 헛호출/밴 방지,
>   종목당 TTL 1회만 API). 검색 🔄 = 보이는 종목을 `/api/watchlist/quotes` 라이브로 덮어씀.
> - **내자산 수동 가격 override:** `holdings.manual_price` 컬럼 + `POST /api/myassets/manual-price`(null=해제) + 현재가 ✎/↺/"수동" 배지.
> - 전 화면 "⚠ 시세 약 15분 지연" 문구.
>
> **이 기능군은 완료 상태. 재구현·재제안 금지. 다음 작업은 PHASE4 잔여(D1·D2·C2·B4).**

## 목표
홈 화면의 고정 "시장 지수" 6종을 **사용자 구성 가능한 위젯 캐러셀**로 교체.
- 위젯 = 시장지수(기본) + 관심목록1, 2, ... (사용자 추가)
- 각 위젯: 이름 변경 가능, 담는 종목(주식/ETF/지수/환율/금/크립토) 자유 구성
- 홈 표시 순서 사용자 지정
- 모바일: 스와이프로 위젯 전환, 위젯당 6개/페이지(넘으면 다음 페이지로 스와이프)
- PC: 상단 탭 전환 + TradingView-lite 표(종목·현재가·등락%·미니스파크)
- 비로그인/첫방문: 기본값 = 현재 홈 6종(S&P·나스닥·코스피·금국제·금KRX·환율). 편집은 로그인 유도
- 설정 페이지 `/settings` 신규(확장성: 계정/로그아웃/탈퇴/일반설정 향후). 그 안 "홈화면 설정" 섹션에서 위젯 CRUD·이름·종목·순서

## 오너 결정 (확정)
- 비로그인: 기본값 표시만, 편집=로그인 유도(myportfolios 패턴)
- PC 다중 위젯: **상단 탭 전환**
- 종목 추가: 기존 `/api/search` 재사용 + 시장지수 5종 프리셋(지수/환율) 빠른추가
- 진입점: 사이드바 "설정" → `/settings` → "홈화면 설정" 섹션(확장형)

## 데이터 모델
로그인 사용자별 JSON config (auth_manager). 신규 저장:
```json
{ "widgets": [
  { "key": "w_market", "name": "시장 지수",
    "items": [ {"code":"^GSPC","name":"S&P 500"}, ... ] },
  { "key": "w_2", "name": "관심목록1", "items": [ {"code":"TLT","name":"美 장기국채"}, ... ] }
] }
```
- 순서 = 배열 순서. 첫 위젯도 일반 위젯과 동일(이름/종목 편집 가능, 기본명 "시장 지수").
- item.code = 시세 조회 키(yfinance 티커 또는 KRX_GOLD/KR 6자리). name = 표시명.
- 저장: `user_settings` 테이블(또는 users.home_config TEXT). 확장성 위해 범용 `user_settings(user_id, key, value_json)` 권장 → key='home_widgets'. 향후 일반설정도 같은 테이블.

## 기본값 (DEFAULT_WIDGETS)
현재 홈 6종 그대로 단일 위젯:
```
[{key:"w_market", name:"시장 지수", items:[
  ^GSPC S&P 500, ^IXIC NASDAQ, ^KS11 코스피, GC=F 금(국제), KRX_GOLD 금(KRX), KRW=X 환율 ]}]
```

## 시세 소스
`portfolio_engine.loader.get_symbol_data(code)` = 통합(KR .KS / US / 지수^ / 선물 / KRX_GOLD / 크립토). 
- 경량 변환: current_price·prev_price·prices[-20:] → {value(포맷), change%, up, spark[]}.
- Redis 캐시(mq:wl:<code>) market_quote_service Redis 재사용, TTL = 장중15분/장외4h.
- 신규 엔드포인트 `/api/watchlist/quotes?codes=a,b,c` → 코드별 quote 배열(미스만 조회·캐시).

## 엔드포인트
- `GET  /api/home-config` — 로그인 시 저장 config, 아니면 DEFAULT_WIDGETS
- `POST /api/home-config` — 저장(로그인 필수, 검증: 위젯 1~10개·이름 1~20자·위젯당 종목 1~30개)
- `GET  /api/watchlist/quotes?codes=` — 시세 배열(캐시)

## 프론트
### 홈 (index.html)
- 정적 market 카드 → 동적 위젯 컨테이너.
- 공통: home-config fetch → 각 위젯 quotes fetch → 렌더.
- **모바일(≤768)**: 가로 스와이프 캐러셀(위젯 단위) + 위젯 내 6개 초과 시 페이지(점 인디케이터). 터치 스와이프 + 좌우 도트.
- **PC**: 위젯 탭 바 + 선택 위젯을 TradingView-lite 표로. 행 클릭 → /symbol/<code>.
- 비로그인: 기본값 렌더 + "로그인하면 편집 가능" 안내 + 설정 링크.

### 설정 `/settings` (신규)
- 확장형 레이아웃: 섹션 카드들. 1단계 = "홈화면 설정"만(이후 계정/일반 등 추가 자리).
- 홈화면 설정 섹션: 위젯 리스트(드래그 or ▲▼ 순서) · 위젯 추가/삭제 · 이름 인라인 편집 · 위젯별 종목 리스트(검색 모달 추가 + 프리셋 칩 + 삭제) · 저장 버튼.
- 로그인 필수(비로그인 → 로그인 유도).

## 단계 (각 단계 타겟테스트 + 배포 + 라이브 검증)
1. **백엔드**: user_settings 저장(auth_manager) + DEFAULT_WIDGETS + /api/home-config GET·POST + /api/watchlist/quotes. → verify: pytest 타겟(저장 왕복·검증·기본값·quote 변환).
2. **홈 렌더**: 동적 위젯(모바일 스와이프+페이지 / PC 탭+표). 정적 market 제거. → jsdom + 라이브.
3. **설정 페이지**: /settings + 홈화면 설정 섹션(위젯 CRUD·이름·종목검색/프리셋·순서). → jsdom + 라이브(로그인 mint_session).
4. **마감**: 비로그인 안내·반응형·다크·캐시버전·wiki.

## 미해결/리스크
- KR 종목 라이브 시세: get_symbol_data가 .KS yfinance 호출 — 속도/실패 시 폴백(price_daily.db 최신). N종목 직렬 조회 성능 → Redis 캐시로 완화, 미스만 조회.
- /api/search에 지수^·환율 없음 → 프리셋 칩으로 보강(결정됨).
- 드래그 정렬은 모바일 까다로움 → ▲▼ 버튼 우선, 드래그는 추후.
