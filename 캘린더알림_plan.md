# 증시 캘린더 알림 — 플랜

> ✅ **P1~P5 구현·검증 완료 (2026-06-25, 커밋 예정).** 잔여=prod 배포 후 celery beat 재시작 + 실기기/라이브 확인. 푸시는 prod FCM 키 있을 때 전송(없으면 인앱만).


오너 결정(2026-06-25):
1. **알림 시점** = 이벤트 **당일 아침 한 번**
2. **대상 종목**(실적·배당락) = **알림 전용 별도 선택**(캘린더 설정과 독립)
3. **경제지표·통화정책 범위** = **알림에서 사용자가 직접 선택**(별도)
4. **발화 시각** = 매일 **08:00 KST** (= 23:00 UTC)

## 개요
알림 탭(/alerts)에 "증시 캘린더 알림" 섹션 신설. 사용자가 ① 이벤트 종류(경제지표·실적·통화정책·배당락) on/off, ② 알림받을 경제지표 개별 선택, ③ 실적·배당락 대상 종목(소스/개별) 을 **알림 전용으로** 설정. 매일 08:00 KST에 그날 일정이 있으면 인앱 수신함 + FCM 푸시.

기존 자산:
- `market_calendar.events_for(codes, loader, econ_ids, show_earnings, show_dividend, names)` — econ/policy/earnings/dividend 이벤트. **재사용.**
- `alert_store.add_event(uid,title,body,code,rule_id,meta)` + `push_sender.send_to_user(...)` — 발화 패턴. **재사용.**
- `_calendar_grouped(uid)` → (groups, names, labels) 동적 소스(holdings·pf:id·watchlist). **재사용**(알림 전용 prefs로 필터).
- celery beat(UTC tz) + `tasks.evaluate_alerts`(가격, 15분). 캘린더는 **별도 daily task**.

## 데이터 모델 — 신규 테이블 `cal_alert_prefs`
alert_store.py DDL에 추가. user_id PK(1:1).
```
cal_alert_prefs(
  user_id PRIMARY KEY,
  enabled        INTEGER DEFAULT 0,   -- 마스터 on/off
  show_econ      INTEGER DEFAULT 1,
  show_earnings  INTEGER DEFAULT 1,
  show_policy    INTEGER DEFAULT 1,
  show_dividend  INTEGER DEFAULT 1,
  econ_ids       TEXT,   -- JSON [release_id...] 알림받을 경제지표(별도)
  sources        TEXT,   -- JSON {group_key: bool} 종목 소스(holdings·pf:id·watchlist)
  excluded       TEXT,   -- JSON [code...] 개별 제외
  last_sent_date TEXT,   -- 'YYYY-MM-DD' 당일 중복 발화 방지(보조)
  updated_at     TEXT
)
```
store 함수: `get_cal_alert_prefs(uid)`, `save_cal_alert_prefs(uid, prefs)`, `get_all_cal_alert_enabled()`(발화 task용 — enabled=1 사용자).

## 발화 로직 — `modules/alerts/calendar_alert_runner.py`
순수/오케스트레이션 분리(기존 alert_runner 결 따름). Flask import 없이 워커서 동작.
```
def run_calendar_alerts(loader, today_kst=None):
    오늘(KST) 날짜.
    for each user in get_all_cal_alert_enabled():
        prefs = get_cal_alert_prefs(uid)
        codes = _user_alert_codes(uid, prefs)   # prefs.sources/excluded 적용(알림 전용)
        econ_ids = set(prefs.econ_ids) if prefs.show_econ else set()
        evs = events_for(codes, loader, econ_ids=econ_ids,
                         show_earnings=prefs.show_earnings,
                         show_dividend=prefs.show_dividend, names=...)
        # policy는 events_for가 항상 포함 → show_policy=0이면 type=='policy' 제거
        todays = [e for e in evs if e['date']==today and 종류켜짐(e)]
        if not todays: continue
        # 묶음 1건 OR 이벤트별? → 당일 묶음 1건(요약) + 상세는 body. 중복=last_sent_date==today면 skip
        제목 "📅 오늘의 증시 일정 N건", body= "미국 CPI · AAPL 실적 · ..." (최대 몇 개)
        add_event + push_sender. prefs.last_sent_date=today.
    return 발화 사용자 수
```
**종목 코드**: `_user_alert_codes`는 app.py `_calendar_user_codes`와 동일 로직이나 prefs(알림 전용)로. 워커는 app.py import 불가 → `_calendar_grouped`도 워커서 못 씀(auth_manager 기반이라 OK? get_holdings/get_portfolios/get_home_widgets는 auth_manager — 워커 가능). calendar_alert_runner에서 그룹 수집 자체 구현(auth_manager 직접) or app 로직 복제. **결정: runner 안에서 auth_manager로 그룹 수집**(app.py 의존 제거).

**중복 방지**: `last_sent_date == today` 면 그날 재발화 안 함(beat 1일 1회라 사실상 안전망). 묶음 1건이라 이벤트별 중복 신경 불필요.

## celery task + beat
- `tasks.py`: `@celery.task evaluate_calendar_alerts()` → loader 준비 후 `calendar_alert_runner.run_calendar_alerts(loader)`.
- `celery_app.py beat_schedule`: `'evaluate-calendar-alerts': {'task':'tasks.evaluate_calendar_alerts', 'schedule': crontab(hour=23, minute=0)}`  # 08:00 KST. 매일(주말 포함 — 배당락/공시 주말 거의 없지만 무해).

## API (app.py)
- `GET /api/alerts/calendar-prefs` → `{prefs, available_econ:[{id,label}], symbols:{group:[{code,name}]}, group_labels, group_order, logged_in}` (캘린더 config GET과 유사).
- `POST /api/alerts/calendar-prefs` → 저장(enabled·show_*·econ_ids·sources·excluded 검증).

## UI (alerts.html)
"증시 캘린더 알림" 섹션 추가(가격 알림 영역과 구분). 구성:
- 마스터 토글(증시 일정 알림 받기) — 매일 아침 8시 안내.
- 종류 토글 4개: 경제지표 / 실적 발표 / 통화정책 / 배당락.
- 경제지표 개별 체크 그리드(available_econ) — show_econ 켤 때만.
- 종목 소스 카드(holdings·각 포폴·watchlist) + 개별 제외 — show_earnings|show_dividend 켤 때(캘린더 설정 UI와 동일 패턴, 알림 전용 저장).
- 저장 버튼.
- JS는 settings 캘린더 패널 렌더 로직과 거의 동일(group_order/labels 순회).

## 단계 + 검증
- **P1** DB+store: cal_alert_prefs DDL + CRUD. → 단위(라운드트립).
- **P2** runner: run_calendar_alerts 순수 로직. → 단위(가짜 prefs+이벤트 주입, 오늘 일정 → add_event 호출 확인. push는 키없음 no-op).
- **P3** task+beat: tasks.evaluate_calendar_alerts + beat 등록. → task 함수 직접 호출.
- **P4** API GET/POST. → test_client 라운드트립.
- **P5** UI alerts.html 섹션 + JS. → Playwright(로그인 강제렌더) 라이트/다크, 토글·저장 동작, 콘솔0.
- **P6** 전체: 로그인 유저 prefs 저장 → runner 직접 실행 → 수신함 이벤트 생성 확인(test_client).

⚠️ 실제 매일 발화는 prod celery beat 필요(로컬 미가동). task/runner 함수는 직접 호출로 검증. 푸시는 prod FCM 키 있을 때만 실제 전송(없으면 인앱만).

## 미결/주의
- 묶음 1건(요약) vs 이벤트별 N건 → **묶음 1건**(아침에 알림 폭주 방지). 상세는 body + 알림 탭/캘린더서 확인.
- 비로그인·prefs 없음 → 기본 disabled(마스터 off). 명시적 켜야 발화.
- 종목 0개여도 econ/policy만으로 발화 가능.
