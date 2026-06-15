# 거시경제 지표 탭 + 나만의 증시 캘린더 계획

작성: 2026-06-15 (Claude, 오너 아이디어). 상태: ✅ **지표 목록 전체 확정 (오너 승인 2026-06-15) — 구현 착수 가능.**

> **범위 결정 (오너, 2026-06-15):**
> - ②거시지표 + ③캘린더 **합본 1개 플랜**.
> - **알림 기능 제외** → 추후 리밸런싱 알림 만들 때 같이. 캘린더는 일단 **읽기 전용 뷰**.
> - 지표: 한·미 "지표란 지표 다" (수백 개만 아니면 OK). **아래 목록 = 초안, 오너가 읽고 선정·확정.**
> - 지표 설명: **LLM 생성 + 오너 검수**(교육·정보용, 투자자문 아님 면책 표기).
> - 캘린더 이벤트: 배당 + 지표 발표일 + **실적 발표일 포함**.

---

## 기존 자산 (재활용 — 조사 완료 2026-06-15)

| 자산 | 위치 | 용도 |
|---|---|---|
| FRED **공식 API** 수집 `fetch_series(key,series_id)` | `scripts/fetch_us_credit_rates.py:32` | JSON + 메타 + 릴리스일정. 키 = `data/meta/fred_api_key.txt` **존재(32자)**. US 지표·캘린더 발표일 둘 다 재활용. (구 `_fetch_fred` fredgraph.csv는 폴백) |
| ECOS 수집 패턴 | `scripts/fetch_kr_rates.py` | 한국 지표. 키 = `data/meta/ecos_api_key.txt` 존재 |
| Celery beat 스케줄 | `celery_app.py` `beat_schedule` | 자동 갱신 → task 추가만 |
| 배당 ex-date | `corporate_actions` 테이블 | 배당 캘린더 데이터 확보됨 |
| 즐겨찾기 종목 | `saved_portfolios` / watchlist(`user_settings.home_widgets`) | 캘린더 필터 소스 |
| 테이블 생성 패턴 | `auth_manager.init_db` `CREATE TABLE IF NOT EXISTS` | 신규 테이블 패턴 |
| 라우트/탭 추가 패턴 | `app.py` + 사이드바/nav | 신규 `/macro`·`/calendar` 탭 |

**신규 필요:** ① `macro_series`/`macro_observations` 스키마 + 한·미 수집 확장 + 카테고리 + 설명 콘텐츠. ② 캘린더 이벤트 소스 = 지표 발표일정(FRED releases API) + 실적 발표일(yfinance, 신규).

---

# PART A — 거시경제 지표 탭 (`/macro`)

## A1. 데이터 스키마

저장 위치: `data/meta/index_master.db` (기존 시계열 DB 재사용) 또는 신규 `macro.db`. → **권장: index_master.db 신규 테이블**(백업·운영 일원화).

```sql
CREATE TABLE IF NOT EXISTS macro_series (
  code TEXT PRIMARY KEY,        -- 내부코드 (예: US_FEDFUNDS, KR_BASE_RATE)
  name_ko TEXT,                 -- 표시명 한글
  name_en TEXT,
  category TEXT,                -- 카테고리 (금리/인플레이션/고용/...)
  country TEXT,                 -- US / KR
  unit TEXT,                    -- % / index / 천명 / 십억$ ...
  freq TEXT,                    -- D/W/M/Q (갱신주기)
  source TEXT,                  -- fred:FEDFUNDS / ecos:722Y001/0101000 / kosis:...
  description TEXT,             -- 1~2줄 설명 (LLM생성+검수)
  higher_is TEXT,               -- 'good'/'bad'/'neutral' (색상 힌트, 선택)
  last_update TEXT
);
CREATE TABLE IF NOT EXISTS macro_observations (
  code TEXT, date TEXT, value REAL,
  PRIMARY KEY (code, date)
);
```

## A2. 지표 목록 (✅ 오너 전체 승인 2026-06-15 — ⚠️ = 코드/소스 구현 시 실호출 검증 필요)

> 코드 = FRED series id(미국, 키 불필요) / ECOS stat·item(한국) / KOSIS(통계청). 확실치 않은 건 ⚠️.
> 전 항목 승인됨. ⚠️ 표기는 "지표 제외"가 아니라 "코드 검증 대상" — 착수 1단계에서 전부 실호출 확인.

### 미국 (FRED)

**금리·통화정책**
| 코드 | 지표 | FRED |
|---|---|---|
| 연방기금 실효금리 | Fed Funds Effective | FEDFUNDS |
| 기준금리 목표 상/하단 | Target upper/lower | DFEDTARU / DFEDTARL |
| SOFR | 담보부 익일물 | SOFR |
| EFFR | 실효 연방기금(일별) | EFFR |
| 국채금리 만기별 | 1M~30Y | DGS1MO DGS3MO DGS6MO DGS1 DGS2 DGS3 DGS5 DGS7 DGS10 DGS20 DGS30 |
| 장단기 금리차 10Y-2Y | 침체 시그널 | T10Y2Y |
| 장단기 금리차 10Y-3M | | T10Y3M |
| 10년 실질금리 | TIPS | DFII10 |
| 5년 실질금리 | | DFII5 |
| 기대 인플레 10Y(BEI) | breakeven | T10YIE |
| 기대 인플레 5Y | | T5YIE |
| 5y5y forward | | T5YIFR |

**인플레이션**
| 지표 | FRED |
|---|---|
| CPI (전체) | CPIAUCSL |
| 근원 CPI | CPILFESL |
| PCE 물가 | PCEPI |
| 근원 PCE (Fed 타깃) | PCEPILFE |
| PPI | PPIACO |
| 에너지 CPI | CPIENGSL |

**고용**
| 지표 | FRED |
|---|---|
| 실업률 | UNRATE |
| U6 광의실업률 | U6RATE |
| 비농업 고용(레벨) | PAYEMS |
| 신규 실업수당 청구 | ICSA |
| 계속 청구 | CCSA |
| 시간당 평균임금 | CES0500000003 |
| 임금상승률(생산직) | AHETPI |
| 경제활동참가율 | CIVPART |
| 구인건수 JOLTS | JTSJOL |

**통화·유동성**
| 지표 | FRED |
|---|---|
| M1 | M1SL |
| M2 | M2SL |
| 통화유통속도 M2V | M2V |
| Fed 총자산(B/S) | WALCL |
| 역레포 잔액 | RRPONTSYD |
| 지급준비금 | WRESBAL |

**신용·리스크·스프레드**
| 지표 | FRED |
|---|---|
| 하이일드 OAS | BAMLH0A0HYM2 |
| IG 회사채 OAS | BAMLC0A0CM |
| VIX | VIXCLS |
| Baa - 10Y 스프레드 | BAA10Y |
| Moody's Baa / Aaa | DBAA / DAAA |
| 세인트루이스 금융스트레스 | STLFSI4 |
| 모기지 연체율 ⚠️분기 | DRSFRMACBS |
| 신용카드 연체율 ⚠️분기 | DRCCLACBS |
| 전체 대출 연체율 ⚠️분기 | DRALACBS |

**경기·성장·심리**
| 지표 | FRED |
|---|---|
| 실질 GDP ⚠️분기 | GDPC1 |
| 산업생산지수 | INDPRO |
| 설비가동률 | TCU |
| 소매판매 | RSAFS |
| 미시간대 소비자심리지수(전미) | UMCSENT |
| 주택착공 | HOUST |
| 건축허가 | PERMIT |
| Case-Shiller 주택가격 | CSUSHPINSA |
| 내구재 주문 | DGORDER |
| 경기선행지수(OECD 미국 CLI) ⚠️ | USALOLITONOSTSAM |

**시장·원자재·환율**
| 지표 | FRED |
|---|---|
| WTI 유가 | DCOILWTICO |
| Brent 유가 | DCOILBRENTEU |
| 달러지수(broad) | DTWEXBGS |
| 금 현물(런던) ⚠️ | GOLDAMGBD228NLBM |
| 원/달러 환율 | DEXKOUS |

### 한국 (ECOS 단일 — ✅ 전 항목 ECOS 존재 검증 2026-06-15, KOSIS 불필요)

> ECOS API 실호출(`KeyStatisticList` + `StatisticTableList` 834표)로 아래 ⚠️ 항목 전부 ECOS에 존재 확인 — 선행지수(경기종합)·기대인플레·산업생산·실업/고용/취업자·주택매매가격·BSI·CSI 포함. ⚠️ = 정확 STAT_CODE/ITEM은 착수 1단계에서 `StatisticItemList`로 확정.

**금리** (이미 `fetch_kr_rates.py`에 일부 수집 중)
| 지표 | 소스 |
|---|---|
| 한국은행 기준금리 | ecos 722Y001 ⚠️ |
| 국고채 1/2/3/10/20/30Y | ecos 817Y002 (KTB*) ✅수집중 |
| CD 91일 / KOFR | ecos 817Y002 ✅수집중 |
| 회사채 AA-/BBB- 3Y | ecos 817Y002 ✅수집중 |

**물가**
| 지표 | 소스 |
|---|---|
| 소비자물가 CPI | ecos 901Y009 ⚠️ |
| 근원물가 | ecos 901Y009 ⚠️ |
| 생산자물가 PPI | ecos 404Y014 ⚠️ |
| 기대인플레이션 | ecos ⚠️ |

**고용** (ECOS 수록 확인 ✅)
| 지표 | 소스 |
|---|---|
| 실업률 | ecos ✅(코드 ⚠️) |
| 고용률 | ecos ✅(코드 ⚠️) |
| 경제활동참가율 | ecos ✅(코드 ⚠️) |
| 취업자수 증감 | ecos ✅(코드 ⚠️) |

**통화·성장·심리**
| 지표 | 소스 |
|---|---|
| M1 / M2 통화량 | ecos 102Y00x ✅ |
| 실질 GDP | ecos 200Y10x ✅ |
| 산업생산지수 | ecos ✅(코드 ⚠️) |
| 경기선행지수(경기종합) | ecos ✅(코드 ⚠️) |
| 소비자심리지수 CSI | ecos ✅(코드 ⚠️) |
| 기업경기실사 BSI | ecos ✅(코드 ⚠️) |

**대외·부동산**
| 지표 | 소스 |
|---|---|
| 원/달러 환율 | ecos 731Y001 ⚠️ |
| 경상수지 | ecos ✅(코드 ⚠️) |
| 수출/수입 (금액지수) | ecos ✅(코드 ⚠️) |
| 주택매매가격지수 | ecos ✅(코드 ⚠️) |
| 가계신용(가계부채) | ecos ✅(코드 ⚠️) |

> 합계 대략 미국 ~55 + 한국 ~25 ≈ 80종. "수백 개" 아님 — OK 범위. **오너 선정 후 코드 검증 단계에서 ⚠️ 전부 실호출 확인.**

## A3. 수집 파이프라인

- `modules/macro_loader.py` 신규: `fetch_fred(series_id)`(공식 API, `fetch_us_credit_rates.fetch_series` 패턴·키 사용) + `fetch_ecos(stat,item)` → `macro_observations` upsert(`INSERT OR IGNORE`/증분). **KOSIS 불필요.**
- `scripts/backfill_macro.py`: 전체 초기 적재(시리즈 메타 시드 + 전 기간 백필). `macro_series` 메타는 코드에 dict로 정의 → 시드.
- 증분 갱신 = 마지막 날짜 이후만 fetch.
- 소스 = 미국 FRED(키X) + 한국 ECOS(키 있음) 둘 뿐. 추가 키/계정 발급 없음.

## A4. 자동 갱신 (Celery beat)

- `tasks.py`에 `refresh_macro_daily` / `refresh_macro_monthly` 추가.
- `celery_app.py beat_schedule`에 등록: 일별 시리즈 = 매 영업일 1회(미국 장 마감 후), 월별 지표 = 발표 후 주기 폴링.
- 무료 소스(FRED CSV·ECOS) → rate-limit 여유. 시리즈당 1회/주기.

## A5. UI (`/macro`)

- 사이드바/nav "거시지표" 추가.
- **카테고리 탭/섹션**(금리·인플레·고용·통화·신용·경기·시장).
- 지표 카드 = 미니 스파크라인 + 최신값 + 전기대비 + **설명 옆에 짤막**(툴팁/접기).
- **한·미 비교**: 같은 카테고리 지표 한·미 나란히, 또는 토글(예: CPI 한 vs 미). 정규화는 단위 다르면 인덱스(=100 기준) 또는 별도 축.
- 클릭 → 지표 상세(전체 기간 차트, 침체 음영 등 후속).
- "⚠️ 시세 15분 지연" 류 면책 + "교육·정보용, 투자자문 아님" 문구.

## A6. 설명 콘텐츠

- 오너가 지표 확정 → Claude가 지표당 1~2줄 한글 설명 생성 → 오너 검수 → `macro_series.description` 시드.

---

# PART B — 나만의 증시 캘린더 (`/calendar`, 읽기 전용)

## B1. 이벤트 소스

| 이벤트 | 소스 | 상태 |
|---|---|---|
| 배당 ex-date / 지급일 | `corporate_actions` 테이블 | ✅ 존재 |
| 지표 발표 일정 | FRED 공식 API `/fred/releases/dates` (키 `fred_api_key.txt`) | 신규 ⚠️구현 시 확인 |
| 실적 발표일 | yfinance `Ticker.calendar` / `earnings_dates` | 신규. **무료 = 부정확·누락 가능** 면책 표기 |

> 실적발표일 = 무료 소스 한계 명시(예상일·변동 가능). 정확도 필요 시 추후 유료 API(FMP 등) 검토 — 일단 yfinance.

## B2. 스키마

```sql
CREATE TABLE IF NOT EXISTS market_events (
  id INTEGER PRIMARY KEY,
  event_type TEXT,        -- dividend / earnings / macro_release
  symbol TEXT,            -- 종목코드 (지표면 macro code)
  event_date TEXT,
  title TEXT,
  meta TEXT,              -- JSON (예상치/실제치/배당액 등)
  UNIQUE(event_type, symbol, event_date)
);
```
- 배당은 `corporate_actions`에서 직접 읽어도 됨(중복 저장 회피) → 캘린더 조회 시 UNION. 실적·지표발표만 신규 테이블.

## B3. UI

- 사이드바 "내 캘린더" 추가(로그인 전용 — 즐겨찾기 기반).
- **월별 그리드** + 리스트 토글. 이벤트 = 색상 구분(배당/실적/지표).
- 필터: 내 즐겨찾기 종목(`saved_portfolios`/watchlist) + 내 즐겨찾기 지표만 vs 전체.
- 이벤트 클릭 → 상세(종목/지표 페이지 링크).
- **알림 없음**(이번 범위). 다가오는 이벤트 강조 정도만.

---

# PART C — 겹쳐보기(오버레이) 고도화 + 포트폴리오 비교탭 통합

> 오너 피드백(2026-06-15): 겹쳐보기 기능이 강력함. 구간 설정·다축·포트폴리오 비교탭 통합 요청.

## C1. 비교 구간 사용자 설정 (겹쳐보기) — ✅ 구현 완료 (2026-06-15)
- 시작일/종료일 date 입력 → 그 구간으로 차트 잘라 보기.
- 정규화 시작점 = 사용자가 고른 **구간 시작일** 값 기준 = 100 (기존: 공통 최소 시작일 고정).

## C2. N≥3 다축 옵션 (겹쳐보기) — ✅ 구현 완료 (2026-06-15)
- 기존: 3개 이상 = 자동 정규화 고정(Chart.js 축 좌·우 2개 한계로 폴백).
- 변경: 정규화 ↔ **원값(개별 y축)** 토글을 전 N개에서 제공. 원값 모드 = 시리즈마다 자체 y축(좌우 교대 배치).

## C3. 포트폴리오 비교탭(/risk-return) 오버레이 통합 — 💡 큰 작업 (계획만)
- 목표: 저장 포트폴리오 자산추이 + 벤치마크 지수 + **거시지표**를 한 차트에 겹쳐 추세 비교.
- 겹쳐보기 엔진 재사용(`/api/macro/multi` 확장 또는 공용화):
  - 토큰 확장: `PF:<id>`(저장 포트폴리오 시계열, `_compute_portfolio_history` 재사용) + 기존 `SYM:<종목>` + 거시지표 코드.
  - 벤치마크 선택 UI에 **거시지표도 추가**(현재 종목/ETF만) — 검색에 거시 90종 포함.
- 정규화/구간/다축(C1·C2)도 동일 적용.
- 비교탭 기존 기능(스파이더·산점도·11지표 표)은 **그대로 두고** 오버레이 차트 카드 **추가**.
- ⚠️ 결정 필요: 포폴 시계열은 비중 고정 일별 근사(risk_return_logic) vs 실제 리밸 — 추세 비교용이라 근사로 충분 추정. 구현 시 확정.

---

## 미해결 결정 / 오너 입력 대기

1. ~~A2 지표 목록 확정~~ — ✅ **전체 승인 (2026-06-15).**
2. ~~KOSIS 키~~ — ✅ **불필요 확정 (실호출 검증 2026-06-15).** 한국 전 지표 ECOS 단일소스 가능(고용·산업생산·선행지수·주택가격·BSI 전부 ECOS 수록 확인). 기존 ECOS 키로 충분. **오너 별도조치 없음.**
3. 한·미 비교 정규화 방식(인덱스100 vs 별도축) — 구현 시 결정 가능.
4. 실적발표일 정확도 — yfinance 무료로 시작 합의됨(면책).

## 위험

- yfinance 실적일 누락/오류 → 면책 + 가능하면 다중 소스 폴백.
- ECOS 정확 STAT_CODE/ITEM 코드는 착수 1단계 `StatisticItemList`로 확정(존재는 검증됨, 세부 코드만 ⚠️).
- 지표 70~80종 백필 = 1회성 시간 소요(시리즈당 수초). 증분은 가벼움.

## 단계별 구현 순서 (지표 확정 후)

1. ✅ **완료 (2026-06-15)** 스키마(`macro_series`/`macro_observations` in index_master.db) + `modules/macro_loader.py`(SERIES 레지스트리 86종 + `fetch_fred`/`fetch_ecos` + `backfill`/`validate`) + 코드 전수 실호출 검증. **결과: 86/86 적재 = 283,536행.** FRED 66 + ECOS 20.
   - 제외: `GOLDAMGBD228NLBM`(FRED 폐지 HTTP400 → 금은 앱 기존 KRX_GOLD/yfinance), `USALOLITONOSTSAM`(OECD 미국 CLI, FRED 최신 2024-01 stale → 한국 선행지수는 ECOS로 대체 보유). 2차원 통계표: 한국 산업생산 `901Y033/[A00,1]`, BSI `512Y008/[BA,99988]`, GDP `200Y107/10601` 검증 완료.
2. ✅ **완료** 전체 백필 = `python -m modules.macro_loader --backfill` (별도 스크립트 불필요). verify: 86종 카테고리×국가 전부 적재 확인.
3. ⏳ Celery beat 갱신 task(`tasks.py` + `celery_app.py`) → verify: 증분 1회 실행 마지막날짜 갱신.
4. ✅ **완료 (2026-06-15)** `/macro` UI(레이아웃 A: 국가토글 US/KR/비교 + 카테고리 섹션 + 카드그리드). 카드=값·등락·SVG 스파크라인, 클릭→상세 모달(전체 시계열 Chart.js+기간토글). 비교=한·미 오버레이(**단위 자동: %·%p는 원값, 그 외 시작=100 정규화**) + 한국 국채금리 4종 추가. 라우트 `/macro`+`/api/macro/{overview,series/<code>,compare}`, `templates/macro.html`, `static/js/macro.js`, base.html nav/사이드바. **verify: 라이브 엔드포인트 4종 + Playwright(US 67카드·KR 23·상세/비교 캔버스·12쌍·콘솔에러 0).** 로컬만, 미배포.
5. ⏳ 설명 콘텐츠(LLM생성+검수) → `macro_series.description` 시드. (현재 desc 빈값 → 모달 설명 숨김.)
6. ⏳ PART B: `market_events` + 실적(yfinance)/지표발표(FRED `/releases/dates`) 수집 → `/calendar` UI.

---

*레퍼런스 스타일: `간편계산기_plan.md`, `PHASE4_PLAN.md`. 작업 완료 시 `moneymilestone/wiki/dev/status.md`·`phases.md`·`log.md` 동기화.*
