# 출시 완성도 개선 마스터플랜

작성: 2026-07-02 (Claude Opus 4.8, 코드베이스 전수 감사 기반)
목표: **토스/도미노 급 완성도로 정식 출시(Google Play + 웹).**
전제: 기존 플랜(GOOGLE_PLAY_RELEASE_PLAN, LAUNCH_LEGAL_SECURITY_PLAN, 성능최적화_plan)과 중복 없이,
그 플랜들이 안 다루는 갭 + 남은 항목을 통합 조율한다.

---

## 0. 절대 규칙 — "A 고치다 B 깨짐" 방지 프로토콜

모든 항목에 공통 적용. 이 규칙을 안 지키면 어떤 항목도 done 처리 금지.

1. **결과 불변 검증**: 시뮬/엔진 경로를 건드리면 `scripts/perf_golden.py check` + `scripts/perf_ab.py`
   (실 DB 18 시나리오)로 숫자 byte-동일 확인. 이미 구축된 하니스 재사용.
2. **타겟 테스트만**: 전체 pytest 금지(오너 규칙). 변경 모듈의 테스트 파일만.
   공유 엔진(`modules/simulation`, `modules/tax`, `modules/execution`) 변경 시 → 오너에게 먼저 물을 것.
3. **프론트 변경 = 실클릭 검증**: 로컬 서버 + Playwright로 모든 버튼/모달/차트 실동작,
   라이트+다크 스샷, 콘솔에러 0. (`moneymilestone/wiki/dev/frontend-verification.md`)
4. **한 PR/커밋 = 한 관심사**: 리팩토링과 기능 수정을 같은 커밋에 섞지 않는다.
   diff가 크면 배포 전 단계별로 쪼갠다.
5. **배포 후 라이브 probe**: prod ssh 동기 probe(`run_*_logic` 직접 호출)로 실데이터 확인.
   로컬 정상 ≠ prod 정상 (로컬 백필이 prod 버그를 가린 전례 다수).
6. **읽기경로 전수 원칙**: 가격 데이터를 만지면 `get_price` 경유 경로뿐 아니라
   **raw SQL로 price_daily를 직접 읽는 경로 전부**를 같이 점검 (BUG-OVERLAY-SPIKE 재발 교훈).

---

## 우선순위 총괄

| Tier | 의미 | 카테고리 |
|---|---|---|
| **P0** | 출시 전 필수 (사고 나면 서비스/데이터 죽음) | C-1 백업, C-2 WAL, B-1 합성손상, I 출시게이팅 |
| **P1** | 출시 직후 2주 내 (운영 안정성) | C-3 CI, C-4 로깅/모니터링, A 보안 잔여, H 테스트체계 |
| **P2** | 완성도 (토스급 체감 품질) | F UX/UI 전수 감사, B-2 데이터 파이프라인, E 프론트 위생 |
| **P3** | 장기 구조 개선 (기능 멈춤 없이 점진) | D 백엔드 리팩토링, E-3 번들링, G 성능 P3 |

---

# A. 보안 (Security)

현황: **기반은 이미 양호.** flask-limiter(redis, HEAVY_LIMIT 12/min) + CSRF origin 체크 +
보안헤더(CSP/HSTS/XFO/nosniff) + 쿠키(HttpOnly/SameSite=Lax/prod Secure) + Sentry(env 게이팅) +
법적 페이지(/privacy /terms /consent, 탈퇴) 전부 배선 확인됨. SQL은 placeholder 파라미터화 확인
(f-string은 `?` 갯수 빌드용 — 안전). 남은 것은 마감 수준.

### A-1. XSS escape 일관성 전수 점검 — P1
- 문제: `esc()` 헬퍼가 **10개 파일에 각자 복붙**돼 있고, 빠진 곳 존재.
  확인된 예: `templates/myassets.html:1427` — 그룹 select option에 `${g.name}` 비이스케이프
  (본인 소유 데이터라 self-XSS 수준이지만, 공유 기능 생기는 순간 stored XSS로 승격).
- 방법:
  1. `static/js/common.js`(신설 또는 기존 공용 파일)에 `esc()` 단일 정의 → 각 파일 로컬 정의 제거.
  2. 전 템플릿/JS의 innerHTML 삽입점(228곳+)을 grep 전수 → 사용자 입력 유래 문자열
     (그룹명·포폴명·메모·검색결과 name)이 esc 경유하는지 표로 체크.
  3. 서버 유입 시점 방어 추가: 그룹명/포폴명 저장 API에 길이 제한 + 제어문자 스트립.
- 검증: 그룹명을 `<img src=x onerror=alert(1)>`로 저장 → 전 화면(내자산·리밸런싱·알림·비교)에서
  텍스트로만 렌더되는지 Playwright 확인.
- 영향 범위: 렌더 문자열만. 계산 로직 0.

### A-2. CSP 강화 (unsafe-inline 제거) — P3 (장기, E-3과 함께)
- 현황: `script-src 'unsafe-inline'` — 인라인 JS 17k줄 구조상 불가피.
- 인라인 JS 외부 파일화(E-3)가 끝나야 가능. 그 전엔 **nonce 방식 부분 적용도 비용 대비 낮음** → 보류.
- 오너 결정점 아님. E-3 완료 후 자동 후속.

### A-3. 의존성 취약점 스캔 — P1
- `requirements.txt` 98개 전부 버전 고정(양호). 단 스캔 이력 없음.
- 방법: `pip-audit` 1회 실행 → 취약 패키지 목록화 → 패치 버전 올릴 것만 선별
  (major 업그레이드는 금지 — pandas/numpy 등은 결과 불변 하니스 통과 필수).
- CI에 월 1회 pip-audit 잡 추가(C-3과 함께).

### A-4. 소소한 마감 — P1
- `app.py:3660` `debug=True`: `__main__` 블록이라 prod(gunicorn) 무관이지만,
  실수로 서버에서 `python app.py` 실행하면 디버거 노출. → `debug=os.environ.get('FLASK_DEBUG')=='1'`로.
- 세션 30일 고정 → 재로그인 UX와 보안 균형. 현행 유지 OK (변경 불필요, 기록만).
- `deploy.yml`에 서버 IP 하드코딩 → secrets로 이동(코스메틱, 낮음).
- rate limit 수치 재점검: 출시 후 실트래픽 보고 조정 (지금 건드리지 말 것).

---

# B. 데이터 무결성 (이 서비스의 생명선)

버그 이력상 **가장 재발이 잦은 카테고리** (SPY 스파이크 2회, 005930 오염, KOSPI alias, NULL홀 점프,
SHY/IEF 합성 손상). 개별 픽스는 돼 있으나 구조적 방어가 부족.

### B-1. 손상 합성백필 처리 — P0 · ⚠️ **오너 결정점**
- 현황: SHY·IEF 등 단기채 ETF의 합성 pre-history가 손상(2008 구간 close 0.00↔190 진동,
  일변동성 실데이터 20×). 비교탭(P3a)은 게이트로 우회했지만 **분석탭 P2 롤링·백테스트·계산기는
  여전히 손상 합성을 읽을 수 있음.**
- 선택지:
  - (a) **손상 합성 전량 DELETE 후 재생성** — 합성 생성 로직(`synthetic_price_generator`) 버그를
    먼저 찾아 고쳐야 재생성 의미 있음. 근본 해결. 권장.
  - (b) 비교탭 게이트(`_clean_deep_points` 손상 판정)를 전 읽기경로에 이식 — 빠르지만 read-time 마스킹은
    BUG-BACKTEST-SPY-SPIKE 재발 패턴(경로 하나 빠지면 재발) 그 자체.
  - (c) 손상 종목만 합성 비활성(real-only) — 짧은 이력 종목의 롤링 케이스 수 감소 감수.
- 방법(a 기준): ① 손상 원인 규명(진동 패턴상 anchor/스케일 봉합 버그 의심 — BUG-DIV-3 유사)
  ② 손상 스캔 스크립트(전 합성 구간 일변동성 vs 실구간 비율 > 2.5× 검출) ③ DELETE→재생성→재스캔 0건
  ④ 골든마스터 + 분석/비교/백테 대표 포폴 Playwright.
- 영향 범위: `use_synthetic` 경로 전부(계산기·은퇴·배당·분석). 재생성 후 숫자 달라지는 건
  **의도된 수정**임을 오너에게 사전 고지.

### B-2. 데이터 품질 상시 방어 파이프라인 — P2
개별 버그픽스(스파이크 필터, purge beat)를 **체계**로 승격:
1. **쓰기 시 검증 일원화**: `fetch_from_api` 저장 직전 단일 `validate_rows()` 훅
   (스파이크·NULL·미래날짜·0/음수가·거래량0 합성징후). 현재 필터가 함수별로 흩어짐.
2. **일일 무결성 beat 확장**: 기존 `purge_price_spikes`(10:00 UTC)에 추가 —
   내부 NULL홀 검출(pad 점프 원인), 주요 지수 last_date 신선도, 합성 손상 스캔(B-1의 스크립트 재사용).
   이상 발견 시 Sentry 이벤트 + 오너 알림(기존 알림 인프라 재사용).
3. **raw SQL 직접 읽기 경로 인벤토리**: `price_daily`/`index_daily`를 PriceLoader 우회로 읽는 곳
   전수 목록화(문서) → 신규 코드는 PriceLoader 경유 강제(코드리뷰 체크리스트).
- 검증: 오염행 인위 주입 → beat가 검출·삭제·알림하는지 스테이징 확인.

### B-3. INSERT OR IGNORE 정책 감사 — P2
- `INSERT OR IGNORE`는 오염행이 한 번 박히면 영구 잔존하는 원인(005930 사례).
- 전 저장 지점 목록화 → "실데이터가 합성/구데이터를 이길 수 있는가?" 기준으로
  IGNORE vs REPLACE vs 조건부 UPSERT 재판정. 합성은 IGNORE 유지(실데이터 보호), 실데이터 갱신은 REPLACE 계열.

---

# C. 인프라 / 운영 (Ops)

### C-1. DB 백업 — **P0, 최우선. 현재 백업 0으로 추정** ⚠️ 확인 필요
- `users.db`(계정·보유자산·포폴·동의이력)가 Hetzner 단일 박스에만 존재.
  repo/deploy 어디에도 백업 언급 없음. 디스크 사고 = **전 유저 데이터 영구 소실 + 법적 문제**(개인정보 유실).
- 방법:
  1. 서버에서 기존 cron 유무 먼저 확인(`crontab -l`, `/etc/cron.*`) — 있으면 이 항목 종료.
  2. 없으면: 일일 cron — `sqlite3 users.db ".backup ..."`(WAL 안전 온라인 백업) →
     날짜별 파일 → **오프박스 업로드**(Hetzner Storage Box 또는 rclone→외부). 보존 30일 로테이션.
  3. `price_daily.db`/`index_master.db`는 재생성 가능하나 백필 비용 큼 → 주 1회 백업.
  4. **복구 리허설 1회 필수**: 백업 파일로 로컬 복원 → 로그인/보유종목 조회 확인. 리허설 없는 백업은 백업 아님.
- 오너 결정점: 오프박스 저장 위치(Hetzner Storage Box 유료 vs 기타). 비용 월 몇 유로 수준.

### C-2. SQLite 동시성 설정 — P0
- 현황: **WAL/busy_timeout 설정이 코드 어디에도 없음.** gunicorn(멀티 요청) + celery worker 2 +
  beat가 같은 SQLite 파일들에 동시 쓰기 → 유저 늘면 `database is locked` 산발 에러 확정 경로.
- 방법: DB 연결 헬퍼 일원화 지점(auth_manager, price_loader, alert_store 등 connect 지점)에
  `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;` 적용. WAL은 파일 단위 1회 설정으로 영속.
- 주의: WAL 전환 시 `-wal`/`-shm` 파일 생성 → 백업 스크립트(C-1)는 반드시 `.backup` API 사용(파일 cp 금지).
  NFS류 마운트면 WAL 불가(Hetzner 로컬디스크라 무관).
- 검증: 동시 쓰기 부하 스크립트(스레드 20개 holdings upsert)에서 locked 에러 0.
- 영향 범위: 전 DB 접근. 단 PRAGMA는 읽기/쓰기 의미 불변 — 회귀는 스모크 수준으로 충분.

### C-3. CI에 테스트 게이트 추가 — P1
- 현황: 테스트 파일 125개 있는데 **CI는 배포만 함**(deploy.yml). 깨진 코드도 push=배포.
- 방법: deploy.yml 앞단(또는 별도 test.yml, main push 시)에 **빠른 서브셋만**(<3분):
  `py_compile` 전 모듈 + 핵심 결정론 테스트 큐레이션(엔진 integrity·tax·saved_portfolios·alerts API 등
  10~15파일) + 골든마스터 check. 실패 시 배포 중단.
- 오너 결정점: 서브셋 목록 확정(제안 목록은 착수 시 제시). 전체 pytest는 CI에서도 금지 유지? (10분이지만
  GitHub Actions는 무료 — **CI에서만 전체 실행**하는 選 추천. 로컬 금지 규칙과 충돌 없음.)
- 선행: BUG-SAVEDPF-ROUNDTRIP(테스트 부채, 오너 보류 중) 해결 없이는 전체 실행 시 상시 1 fail →
  서브셋에서 제외하거나 픽스처 동기화 먼저.

### C-4. 로깅/모니터링 정리 — P1
- 현황: Sentry는 env 게이팅으로 배선됨(⚠️ prod에 SENTRY_DSN 실제 설정됐는지 확인 필요 — 오너/ssh).
  앱 로그는 `print()` 8곳 + celery 로그 산재. 구조화 로깅 없음.
- 방법:
  1. `print()` → `logging` 전환(포맷: 시간·레벨·모듈). gunicorn/systemd journald로 수집되니 파일 핸들러 불요.
  2. `except Exception` 70곳 중 **조용히 삼키는 곳** 선별 → 최소 `logger.warning(exc_info=True)` 추가.
     (동작 변경 금지 — 로그만 추가. 폴백 로직은 그대로.)
  3. 외부 업타임 모니터(UptimeRobot 무료 등)로 `/` + `/api/market` 5분 체크 → 오너 알림.
     ⚠️ 오너 결정점: 모니터 서비스 선택·알림 채널(이메일/텔레그램).
- 검증: 의도적 예외 발생 → Sentry 이벤트 수신 + journald 로그 확인.

### C-5. 운영 가시성 기술부채 — P2
- `domino-celery.service` 등 systemd 파일 repo 커밋(TECH-CELERY-CONCURRENCY 잔여).
- gunicorn 워커 수/타임아웃도 서버에만 있음 → `deploy/`에 커밋해 코드리뷰 가시화.
- `OPENFIGI_API_KEY` prod/CI 등록(투자대가 P5 자동갱신 선결) — 오너 액션.

---

# D. 백엔드 코드 구조 (점진 리팩토링)

원칙: **구조 개선은 기능 동결 상태에서 기계적 이동만.** 로직 수정 섞기 금지.

### D-1. app.py 분할 — P3 · ⚠️ 오너 결정점 (착수 여부)
- 현황: 3,660줄 / 라우트 116개 단일 파일. 헬퍼·SQL·비즈니스 로직 혼재.
  당장 죽는 문제는 아니나, 앞으로 모든 작업의 충돌 표면 + AI 에이전트 컨텍스트 비용.
- 방법(안전 순서): Flask Blueprint로 **도메인별 기계적 이동** — 한 번에 한 도메인만, 배포 사이클 분리.
  1. `routes/legal.py`(작고 독립 — 파일럿) → 2. `routes/alerts.py` → 3. `routes/assets.py`(myassets/그룹)
  → 4. `routes/market.py`(시세/검색/심볼) → 5. `routes/sim.py`(계산기·은퇴·백테·배당 submit/poll)
  → app.py엔 앱 팩토리 + 공용 미들웨어만 잔존.
- 각 단계 검증: 라우트 맵 diff 0(`app.url_map` 전후 비교 스크립트), 해당 도메인 API 테스트, 라이브 probe.
- 리스크: 순환 import, before_request/limiter 데코레이터 누락. → 단계당 diff 최소화로 관리.
- **미착수 대안**: 분할 안 하고 섹션 주석 + 헬퍼만 `modules/web/` 추출하는 절충도 가능. 오너 선택.

### D-2. 죽은 코드/파일 위생 — P2 (쉬움, 오너 승인 후 일괄)
- `templates/base.html.bak`, `index.html.bak` 삭제.
- `modules/analyzer/` 레거시 4종(engine_rolling·portfolio·retirement·rolling_scenario) —
  성능플랜에서 "프로덕션 미경유 死코드" 판정 완료. 단 ARCHITECTURE.md "1세대 삭제 금지" 원칙과 충돌
  → **삭제 대신 `modules/legacy/`로 이동 + README 표기** 절충.
- 루트 계획파일 ~30개 → `docs/plans/` 이동(완결된 것만), 진행 중인 것은 루트 유지.
- `debug_*.py`, `imp.py`, `4testguide.md` 등 루트 산재 스크립트 → `tools/` 또는 `tests/`로.
- 검증: `grep -rn` import 참조 0 확인 후 이동. 위키 링크 경로 갱신.

### D-3. 배당 엔진 Runner 통합 (divrefactoring.md) — P3
- 기존 플랜 존재·미착수. 배당계산기와 공용 엔진 이원화 해소. D-1보다 후순위.
- 착수 시 골든마스터에 배당 시나리오 추가 먼저.

---

# E. 프런트엔드 위생

### E-1. 공용 JS 유틸 통합 — P2
- `esc()` 10곳, `fmtKRW`류 포맷터·토스트·모달 헬퍼가 템플릿마다 복붙.
- `static/js/common.js` 신설: esc/포맷/토스트/fetch 래퍼(에러 토스트 일원화)/debounce.
  템플릿별 로컬 정의를 **한 파일씩** 제거(한 번에 전부 금지 — 페이지당 Playwright 검증).
- A-1(XSS)과 같은 작업 흐름으로 묶어 진행.

### E-2. 캐시버스팅 자동화 — P2
- 현황: `?v=20260701nav2` 수동 문자열 — 갱신 누락하면 유저가 구버전 JS/CSS(재발성 사고 패턴).
- 방법: Jinja 전역 함수 `static_v(filename)` = 파일 mtime(또는 git hash) 쿼리 자동 부착.
  전 템플릿의 수동 `?v=` 치환. 서버 재배포 시 자동 무효화.
- 검증: 응답 HTML의 asset URL이 배포마다 바뀌는지 + 브라우저 강새로고침 없이 갱신 반영.

### E-3. 인라인 JS 외부 파일화 — P3 (대형, 점진)
- 템플릿 17.5k줄의 대부분이 인라인 `<script>`(backtest 2,376줄·myassets 1,912줄).
  영향: CSP unsafe-inline 강제(A-2), 브라우저 캐시 불가(HTML no-cache라 매번 재전송), diff 지옥.
- 방법: 페이지당 1개 `static/js/<page>.js`로 기계적 이동(이미 calculator.js·macro.js 등 선례 있음).
  Jinja 변수 의존부는 `<script type="application/json" id="page-data">`로 데이터만 인라인.
- 순서: 작은 페이지부터(settings→alerts→…→backtest 최후). 페이지당 frontend-verification 풀체크.
- 완료 시 A-2(CSP nonce/외부화) 자동 해금 + HTML 페이로드 대폭 감소(모바일 체감).

### E-4. 프론트 성능 측정 기반 마련 — P2
- Lighthouse(모바일 프로필) 홈·내자산·계산기 3페이지 베이스라인 측정 → 수치 기록.
- 확실한 저비용 개선만: Chart.js 등 CDN 스크립트 `defer`, 이미지 lazy, 폰트 display=swap.
  (번들러 도입은 하지 않는다 — 규모 대비 과함.)

---

# F. UX/UI 완성도 (토스급 체감)

디자인 아키타입 이식(코인베이스 룩)은 진행돼 있으므로, 여기선 **상태(state) 완성도**와
**전수 감사**에 집중. "기능은 있는데 거칠다"를 잡는 카테고리.

### F-1. 3-상태(로딩/빈/에러) 전수 감사 — P2 (체감 효과 최대)
- 전 페이지 × {로딩, 데이터 없음, API 실패, 비로그인} 매트릭스 표 작성 후 실측(Playwright + 네트워크 차단).
- 기준: 로딩=스켈레톤/스피너(레이아웃 점프 없음), 빈=행동 유도 문구+CTA(선례: 내자산 "종목 추가"),
  에러=브랜드 토스트/배너 + 재시도(alert() 잔존 0 — BUG-1 패턴 재점검), 비로그인=로그인 유도.
- 산출물: 매트릭스 표를 위키에 커밋 → 미달 셀을 개별 픽스(페이지당 커밋 분리).

### F-2. 모바일(앱 WebView) 실기기 UX 스윕 — P1 (출시 게이팅과 연동)
- GOOGLE_PLAY_RELEASE_PLAN Phase 1 실기기 검증과 **한 세션에 묶어** 진행:
  기능 체크리스트 + UX 관점(터치 타깃 44px, 하단 탭바와 컨텐츠 겹침, 키보드 올라올 때 입력 가림,
  가로 스크롤 유출, safe-area, 차트 터치 조작감).
- 발견사항은 bugs.md에 등록 후 개별 처리 — 실기기 없이 못 하는 유일 카테고리이므로 오너 폰 세션 필요.

### F-3. 첫사용 경험(온보딩) — P2 · 기존 모바일홈_출시준비_plan과 연동
- 신규 가입 직후 빈 화면 문제: 내자산 0종목·포폴 0개 상태에서 "뭘 해야 하는지" 안내 동선.
- 기존 플랜(압축 3도어 홈·튜토리얼)이 커버 — 이 플랜에서는 **웹 신규 유저**도 같은 동선 타는지만 확인 항목으로.

### F-4. 용어/문구 일관성 + 면책 — P2
- 같은 개념 다른 표기(예: 적립/납입, 수익률 표기 소수점 자리) 전 페이지 스타일 시트(위키 문서) 작성 후 일괄 정리.
- 유사투자자문 규제선 카피 재점검(LAUNCH plan 1.3): "추천/사라" 뉘앙스 문구 0 확인. 법무 검토는 오너 몫.

### F-5. 접근성 최소선 — P3
- 폰트 확대(브라우저 125%)에서 레이아웃 붕괴 없는지, 키보드 탐색으로 주요 플로우 완주 가능한지,
  아이콘 버튼 aria-label. 전면 대응은 과함 — 스토어 심사/일반 사용 최소선만.

### F-6. 페이지별 디자인 크리틱 패스 — P2 (오너 추가 2026-07-03) ⭐
결함 잡기(F-1)와 별개로 **능동적 디자인 개선**. "오류는 없는데 거칠다/못생겼다"를 잡는 작업.
기준선 = 디자인통일_plan의 코인베이스 아키타입 + 토스급 밀도/위계. 리스킨 금지 —
아키타입 재구성 원칙(오너 피드백 2026-06-18) 유지.

- **3폼팩터 필수** (오너 지시): 한 곳에서 멀쩡한 디자인이 다른 곳에서 깨지거나 못생겨질 수 있음.
  1. **데스크탑 웹** (1280·1920)
  2. **모바일 웹** (390 — 브라우저, 주소창 있음)
  3. **모바일 앱** (Capacitor WebView — 하단 탭바와 컨텐츠 겹침, safe-area, 주소창 없음.
     Playwright 390 뷰포트 + 탭바 높이 고려로 근사, 최종은 실기기)
  × 라이트/다크 = 페이지당 6컷 스크린샷 세트.
- **크리틱 항목**: 시각 위계(무엇이 먼저 보여야 하나), 여백/정렬 리듬(4/8px 그리드 이탈),
  타이포 스케일 일관성, 카드/버튼 스타일 통일(같은 의미=같은 모양), 정보 밀도(스크롤 대비 내용),
  차트 가독성(축·범례·색), 터치 타깃(모바일 44px), 첫 화면에 핵심 지표 보이는지.
- **진행 방식**: 페이지 단위 배치(우선순위: 홈 → 내자산 → 계산기/백테 → 은퇴/배당 → 비교/분석 →
  나머지). 배치당: ①6컷 스샷 + 크리틱 목록 → ②**오너에게 개선안 제시(스샷 비교)** →
  ③승인분만 구현 → ④frontend-verification 풀체크(실클릭+6컷 재촬영).
  디자인은 취향 영역 — **오너 승인 없이 대규모 시각 변경 금지.**
- 산출물: 위키 `dev/design-critique.md`에 페이지별 크리틱·결정·전후 스샷 경로 기록.

---

# G. 성능 (잔여)

성능최적화_plan P0~P2 완료·배포됨. 잔여만:

### G-1. P3 백로그 (기존 플랜) — P3
- 후처리 pandas 중복 제거·synthetic 벡터화·무세금 fast-path. 오너가 체감 불만 시에만 착수.
- 착수 조건: 골든마스터 통과 필수(기존 하니스).

### G-2. 첫 요청 콜드스타트 — P2
- 무거운 시뮬 첫 실행 시 가격 로드+백필로 수십 초 걸리는 종목 조합 존재 가능.
  → 진행률 UX(폴링 중 단계 표시: "데이터 준비 중 → 시뮬레이션 중")로 체감 완화.
  엔진 개선이 아니라 F-1과 연동된 프론트 작업.

---

# H. 테스트/검증 체계

### H-1. 테스트 분류 정리 — P1
- `tests/` 125파일에 pytest·단독 스크립트·debug·probe·js가 혼재 → 서브디렉토리 분류
  (`tests/unit/`, `tests/browser/`, `tests/live_probe/`, `tests/debug/`) + README.
  C-3 CI 서브셋 선정의 선행 작업.
- 이동 시 import 경로·CI 참조만 주의. 테스트 내용 무변경.

### H-2. 스모크 스위트 공식화 — P1
- "배포 전 5분 스모크" 단일 명령: 핵심 결정론 테스트 + 골든마스터 + 주요 페이지 Playwright 스크린샷.
  `scripts/smoke.py` 하나로. 지금은 지식이 smoketestguide*.md 등 문서에 분산 — 실행 가능하게.

---

# I. 출시 게이팅 (기존 플랜 포인터 — 중복 작성 안 함)

| 항목 | 플랜 | 상태 |
|---|---|---|
| 실기기 Android 검증 (F-2와 병행) | GOOGLE_PLAY_RELEASE_PLAN Phase 1 | **다음 액션. 오너 폰 필요** |
| Google OAuth Console redirect URI 등록 | domain-cutover 잔여 | ⚠️ 오너. 안 하면 로그인 死 |
| Play Console 계정·앱 등록·스토어 폼 | GOOGLE_PLAY Phase 2·3 | 오너 수동 |
| 스크린샷 2~8장 | GOOGLE_PLAY Phase 3 | 오너 수동 |
| 12명×14일 비공개 테스트 가능성 | GOOGLE_PLAY Phase 4 | 신규 개인계정이면 필수 |
| /account-deletion 공개 안내 페이지 | GOOGLE_PLAY 권장 | 소형 — 이 플랜에서 처리 가능 |
| `android:allowBackup="false"` 검토 | GOOGLE_PLAY 권장 | 소형 |
| Search Console 등록·색인 요청 | domain-cutover 잔여 | 오너 |

---

## 실행 순서 제안 (권장 로드맵)

```
주차 1 (P0):  C-1 백업(+복구 리허설) → C-2 WAL → B-1 오너 결정 후 합성 손상 처리
              └ 병행(오너): I 실기기 검증 + OAuth URI + Play Console
주차 2 (P1):  C-3 CI 게이트 → H-1 테스트 분류 → C-4 로깅/Sentry 확인 → A-1 XSS 전수 → A-3 pip-audit
주차 3~4 (P2): F-1 3-상태 전수 감사 → E-1 공용 JS + E-2 캐시버스팅 → B-2 데이터 파이프라인 → F-4 문구
이후 (P3):    D-1 app.py 분할(오너 승인 시) → E-3 인라인 JS 외부화 → A-2 CSP → D-3 배당 Runner
```

## 오너 결정점 모음 (한눈에)

| # | 결정 | 기본 권장 |
|---|---|---|
| 1 | B-1 합성 손상: (a)재생성 / (b)전경로 게이트 / (c)real-only | **(a) 근본 재생성** |
| 2 | C-1 백업 오프박스 위치 (Storage Box 등 소액 유료) | Storage Box |
| 3 | C-3 CI에서 전체 pytest 허용 여부 (로컬 금지 규칙과 별개) | **허용** (CI는 공짜 시간) |
| 4 | C-4 업타임 모니터 서비스·알림 채널 | UptimeRobot 무료 + 이메일 |
| 5 | D-1 app.py Blueprint 분할 착수 여부 | 출시 후 착수 |
| 6 | D-2 레거시 analyzer 4종 → modules/legacy/ 이동 | 이동 승인 |
| 7 | BUG-SAVEDPF-ROUNDTRIP 픽스처 동기화(보류 중) | 동기화 승인 (C-3 선행) |

---

## 이 플랜이 다루지 않는 것 (명시적 제외)

- 수익화(MONETIZATION_PLAN 별도), 신규 기능(PHASE4 잔여), Tier2 한국 거시지표(보류 확정),
  iOS 앱, 웹푸시(미채택 결정), 번들러/프레임워크 도입(규모 대비 과함 판정).
