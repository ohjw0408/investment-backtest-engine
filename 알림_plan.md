# 알림 기능 plan (가격 트리거 + 신고가/신저가 + 리밸런싱)

작성: 2026-06-17. Owner 요청. 상태: **✅ P1~P4 구현·로컬검증 완료(2026-06-17).** 잔여 = P5(위키동기화·라이브검증).

## ▶ 구현 완료 기록 (2026-06-17)

- **P1 엔진+DB:** `modules/alerts/alert_engine.py`(순수 평가, 5룰타입+쿨다운/재무장) ·
  `modules/alerts/alert_store.py`(alert_rules/alert_events CRUD, users.db 재사용, 한도 50).
  검증 `tests/test_alert_engine.py` 19 PASS.
- **P2 API:** app.py `/api/alerts/rules`(GET·POST·PATCH·DELETE) + `/events`·`/unread-count`·`/events/<id>/read`·`/read-all`,
  `_validate_alert_payload` 서버검증. 검증 `tests/test_alerts_api.py` 28 PASS.
- **P3 평가:** `modules/alerts/alert_runner.py`(종목 dedup·윈도우별 1회 로드·리밸 비중계산) +
  tasks.py `evaluate_alerts`(장중게이트 `_any_market_open`) + celery_app beat `*/15 hour 0-6,13-20`.
  검증 `tests/test_alert_runner.py` 7 PASS(FakeLoader, 네트워크0).
- **P4 프론트:** `templates/alerts.html`(`/alerts` 룰생성·목록·수신함) + base.html 🔔 종(미읽음배지·드롭다운·60s폴링)+사이드바 링크.
  스모크: 로그인/비로그인 렌더 PASS.
- 설계 미세조정: 리밸런싱 = **holdings asset_groups 실제비중 vs target_pct만**(saved_portfolio는 실보유 없어 비중 비교 제외, 단 그 종목들은 symbol 룰 대상엔 포함). 일간변동률 기준 = **전일 종가 대비**.

### ▶ 후속: 토스풍 인라인 진입점 (2026-06-17, 오너 "토스 보고 배워와")

`/alerts` 허브는 유지하되, 알림 설정을 종목/포폴/자산 화면에서 바로 열도록 종(🔔) 진입점 추가.

- **공통 위젯** `static/js/alert_widget.js` — 바텀시트(모바일)/센터모달(PC), 자체 CSS 주입.
  `mmAlert.openSymbol(code,name)` / `openAssets()` / `openPortfolio(id)`. 비로그인=로그인 유도.
  종목 모달=기존 룰 목록(토글/삭제)+세그먼트 빠른추가(변동률·목표가·신고/신저). 그룹 모달=리밸런싱
  스위치(자산만)+구성종목 리스트(각 행→종목 모달, 설정된 알림 수 배지).
- **신규 API** `/api/alerts/context` — 내 종목(holdings/portfolios[+id·symbols]/watchlist).
- **진입점:** 네비 검색 드롭다운·`/search` 카드(🔔)·`/symbol/<code>` 헤더(🔔 알림)·`/myassets` 상단
  (🔔 알림 설정→리밸런싱+종목별)·`/myportfolios/<id>` 제목줄(🔔 알림→구성종목별). base.html에 위젯
  로드 + `window.MM_LOGGED_IN`.
- 검증: test_alerts_api 31 PASS(+context 3) + 4화면 렌더 스모크 PASS.

### ▶ 후속2: 저장 포트폴리오 = 일일 리밸 수익 추종 (2026-06-17, 오너 정정)

오너 정정: 저장 포폴 알림 = 개별종목/리밸런싱 아님 → **전체 포트폴리오 수익률**(매일 리밸런싱 가정).
추가 요청: `/myportfolios` 카드 알림 버튼, 종목 클릭→상세, 즐겨찾기(홈 위젯)에 포폴 추가.

- **일일 리밸 지수:** `alert_runner.compute_portfolio_index(loader, tickers, daily_rebal=True)` — 일별 가중
  수익률 복리(비중 고정 리밸), 원화환산(apply_fx=True) 실수익 추종. 단일 소스(알림+위젯 공용).
- **포폴 수익 룰:** scope='portfolio'+portfolio_id, rule_type ∈ {daily_pct·new_high·new_low}(target_price
  미지원). engine은 IDX 통화로 포인트 표기. runner가 (uid,pid)별 지수 1회계산→평가. `_validate_alert_payload`
  포폴 분기. (리밸런싱 밴드는 내 자산 holdings 전용 유지)
- **위젯 추종:** 홈 위젯 item `code='PF:<id>'` → `_portfolio_quote`(일일리밸 지수 최신값·일변동·스파크,
  사용자별·공유캐시 우회). `/api/home-config/add-portfolio`(myportfolios ⭐버튼). 위젯 클릭=PF→`/myportfolios/<id>`.
- **myportfolios:** 카드 🔔(openPortfolio 수익룰)·⭐(홈추가)·종목행 클릭→`/symbol/<code>`.
- 검증: engine 19 + runner 10(+포폴지수·발화) + api 37(+포폴검증·홈추가) = 66 PASS + 홈/포폴 렌더 스모크.

> 원안(아래)은 그대로 유지 — 참조용.

---


## 1. 목적

로그인 사용자가 **보유 종목(holdings) / 관심목록(watchlist·홈위젯) / 저장 포트폴리오**에 대해 직접
기준을 정해 두면, 조건 충족 시 **인앱 수신함(🔔)** 으로 알려준다.

알림 종류:
1. **일간 변동률** — 종목이 하루 ±N% 이상 오르거나 떨어짐 (방향: 상승/하락/양방향)
2. **목표가 도달** — 가격이 지정값 이상/이하 도달 (절대가격)
3. **신고가 갱신** — 윈도우(52주 / 전체기간) 내 최고가 경신
4. **신저가 갱신** — 윈도우(52주 / 전체기간) 내 최저가 경신
5. **리밸런싱 밴드 이탈** — 포트폴리오/보유자산 그룹 비중이 목표비중 대비 ±band% 초과

## 2. Owner 결정사항 (2026-06-17 확정)

| 항목 | 결정 |
|---|---|
| **전달 채널** | **인앱 수신함(🔔)만.** 웹푸시·이메일 인프라 불필요(추후 확장 가능). |
| **신고가/신저가 윈도우** | **52주 / 전체기간 = 룰별 사용자 선택.** |
| **평가 주기** | **장중 15~30분.** US/KR 장 시간대 beat 스케줄, yfinance 15분 지연 데이터. |

## 3. 기존 인프라 (재사용 — 신규 인프라 거의 없음)

| 부품 | 위치 | 알림에서의 역할 |
|---|---|---|
| Celery + Redis + **Beat(cron)** | `celery_app.py` / `tasks.py` | 평가 task를 beat 스케줄에 추가(기존 KRX금·거시 갱신과 동일 패턴) |
| 사용자 DB | `data/private/users.db` (`modules/auth_manager.py`) | 알림 룰·이벤트 테이블 추가. users.email 보유, holdings·asset_groups(`target_pct`) 존재 |
| 종목 경량 시세 | `app.py:_watchlist_quote` (Redis 종목별 캐시, 15분 floor, dedup) | 현재가·전일대비% 조회. **여러 룰의 같은 종목은 캐시로 1회만 API** = yfinance 밴 안전 |
| 과거가 | `modules/price_loader.py:get_price` | 신고가/신저가 윈도우 최고/최저 슬라이스(52주=최근 ~252행, 전체=풀히스토리) |
| 리밸 비중 | holdings(qty·manual_price) + `asset_groups.target_pct` | 그룹 현재비중 vs 목표비중 이탈 계산 |

⚠️ 구현 시 확인: 다중 관심목록(C1)·홈위젯 종목 저장 위치(user_settings.home_widgets JSON + 관심목록 테이블) —
룰 대상 종목 소스로 쓸 때 정확한 스키마 재확인.

## 4. 데이터 모델 (users.db, IF NOT EXISTS + ALTER 마이그레이션 패턴)

```sql
CREATE TABLE IF NOT EXISTS alert_rules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    scope        TEXT NOT NULL,          -- 'symbol' | 'portfolio'
    code         TEXT,                   -- 티커 (scope=symbol)
    portfolio_id INTEGER,                -- 저장 포폴/그룹 id (scope=portfolio, rebalance_band)
    rule_type    TEXT NOT NULL,          -- daily_pct | target_price | new_high | new_low | rebalance_band
    direction    TEXT,                   -- daily_pct: up|down|both / target_price: above|below
    threshold    REAL,                   -- 변동률% | 목표가 | 밴드%
    window       TEXT,                   -- new_high/low: '52w' | 'all'
    enabled      INTEGER NOT NULL DEFAULT 1,
    cooldown_h   INTEGER NOT NULL DEFAULT 24,   -- 재발화 최소 간격(시간)
    last_triggered_at TEXT,
    last_extreme REAL,                   -- new_high/low 재무장 추적용(직전 경신 극값)
    created_at   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS alert_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    rule_id    INTEGER,
    code       TEXT,
    title      TEXT NOT NULL,            -- 예: "TSLA 신고가 갱신"
    body       TEXT NOT NULL,            -- 예: "$430.12 — 52주 최고가 경신"
    meta       TEXT,                     -- json (price, pct, extreme 등)
    created_at TEXT NOT NULL,
    read_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_events_inbox ON alert_events(user_id, read_at, id);
```

쿨다운/재무장 규칙(스팸 방지):
- `daily_pct` : 하루 최대 1회(같은 거래일 재발화 금지).
- `target_price` : 1회 발화 후 cooldown_h 동안 침묵(가격이 반대편으로 넘어가면 재무장).
- `new_high`/`new_low` : `last_extreme` 갱신될 때만 발화 + cooldown_h 적용(매 틱 도배 방지).
- `rebalance_band` : 밴드 안으로 복귀 후 재이탈 시 재발화(또는 cooldown_h).

## 5. 평가 엔진 (순수 함수 — 네트워크/DB 분리, 결정론 테스트 가능)

신규 `modules/alerts/alert_engine.py`:

```
evaluate_rule(rule, quote, history_extreme, weights, now) -> AlertEvent | None
```
- `quote` = {cur, prev_close, change_pct} (주입; 실데이터는 _watchlist_quote)
- `history_extreme` = {'high': x, 'low': y} (윈도우별, 주입; 실데이터는 get_price 슬라이스)
- `weights` = 그룹별 {current_pct, target_pct} (rebalance_band)
- 순수 함수 → FakeProvider로 전 룰타입·쿨다운 단위테스트.

## 6. Celery 평가 task (`tasks.py`)

```python
@celery.task
def evaluate_alerts():
    # 1) 장중인지 체크(US 13:30-20:00 UTC / KR 00:00-06:30 UTC, mon-fri). 둘 다 닫힘 → 조기 return.
    # 2) enabled 룰 전부 로드(1쿼리).
    # 3) 대상 종목 합집합 산출(symbol 룰 + portfolio 룰의 holdings 확장).
    # 4) 종목별 quote 1회 조회(_watchlist_quote, 캐시 dedup). high/low 룰만 get_price로 극값.
    # 5) 룰별 evaluate_rule → 발화 시 alert_events insert + last_triggered_at/last_extreme update.
```

beat 스케줄(`celery_app.py`, UTC):
```python
'evaluate-alerts': {
    'task': 'tasks.evaluate_alerts',
    'schedule': crontab(minute='*/15', hour='0-6,13-20', day_of_week='mon-fri'),
},
```
(task 내부에서 정밀 장시간 재확인 → 빈 구간은 즉시 return으로 저비용.)

## 7. API (`app.py`, 전부 로그인 필요)

룰 CRUD:
- `GET    /api/alerts/rules` — 내 룰 목록
- `POST   /api/alerts/rules` — 생성(서버 검증: 임계값 범위·scope/type 정합)
- `PATCH  /api/alerts/rules/<id>` — 수정(on/off 토글 포함)
- `DELETE /api/alerts/rules/<id>`

수신함:
- `GET  /api/alerts/events?unread=1&limit=N`
- `GET  /api/alerts/unread-count` — 🔔 배지용(경량)
- `POST /api/alerts/events/<id>/read`
- `POST /api/alerts/read-all`

## 8. 프론트엔드

- **🔔 종(네비 공통):** 미읽음 배지. 페이지 로드 + N분 폴링으로 `/unread-count`. 드롭다운에 최근 이벤트, 클릭=읽음.
- **룰 추가 진입점:** 내자산 종목 행 / 관심목록 항목 / 포폴 카드에 작은 🔔 버튼 → 모달(룰타입·임계값·윈도우·방향).
- **`/alerts` 관리 페이지:** 전체 룰 리스트(편집/삭제/토글) + 수신함 전체 보기.
- 모바일/다크 = 기존 변수·패턴 준수.

## 9. 단계 (한 단계씩, 완료 후 커밋·검증)

| 단계 | 내용 | 검증 |
|---|---|---|
| **P1** | DB 테이블 + auth_manager CRUD 함수 + `alert_engine.evaluate_rule` 순수함수 | `tests/test_alert_engine.py` 전 룰타입·쿨다운 결정론(FakeProvider) |
| **P2** | 룰 CRUD API + 수신함 API | `tests/test_alerts_api.py`(mint_session) |
| **P3** | Celery task + beat 스케줄 + 종목 dedup 조회 배선 | 로컬 task 직접 실행 probe(룰 심어 발화 확인) |
| **P4** | 프론트(🔔 종·수신함 드롭다운·룰 모달·`/alerts`) | jsdom/Playwright + 라이브 probe |
| **P5** | 위키·로드맵 동기화 | features.md·status.md·log.md·이 plan |

## 10. 비목표 / 추후

- 웹푸시·이메일·SMS = 추후(인앱 안정화 후 `push_subscriptions` 테이블 + service worker 추가로 확장).
- 비로그인 알림 = 없음(룰 저장 불가).
- 인트라데이 실시간(<15분) = yfinance 지연·밴 위험으로 비목표.
- 캘린더 이벤트(실적·배당락) 알림 = `거시지표_캘린더_plan.md`가 "추후(리밸런싱 알림 때)"로 미뤘던 항목 → 이 인프라 위에 별 룰타입으로 추가 가능(후속).
