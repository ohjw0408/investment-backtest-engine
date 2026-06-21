# 출시 선결 플랜 — 법적/규제(#1) + 보안/남용방지(#3)

작성: 2026-06-21 (Claude). 목적: **유료/규모 상용화 전 반드시 깔아야 할 법적 의무 + 공개 서비스 보안.**
범위 = 비기능 요건(기능 추가 아님). 수익화(#5)는 `MONETIZATION_PLAN.md` 별도.

현황 사실(코드 확인):
- 저장 개인정보: `users`(google_id·email·name·picture·created/last_login), `holdings`(보유종목·수량·평단·수동가·계좌유형), `asset_groups`, `saved_portfolios`, `user_settings`(세금설정).
- 인증 = Google OAuth. 세션 쿠키.
- 면책 문구는 페이지마다 흩어짐(backtest·macro·myassets·retirement·calculator.js). **약관/개인정보 페이지·footer·동의 플로우 없음**(라우트 0).
- celery+redis 설치됨 → rate limit 저장백엔드 재사용 가능. **flask-limiter 미설치.**
- 무거운 엔드포인트: `/api/{calculator,retirement,backtest,tax-switch,dividend-target}/submit`·`/run`·`/scenario`, `/api/search`, `/api/attribution/*`.

---

## PART 1 — 법적/규제 (게이팅, 사용자 받기 전)

### 1.1 개인정보처리방침 페이지 (`/privacy`)
- 정적 템플릿 `templates/legal/privacy.html`(base 상속). 라우트 `@app.route('/privacy')`.
- 필수 고지 항목(개인정보보호법):
  - **수집 항목**: 구글계정(google_id·email·name·picture), 보유자산(종목코드·수량·평단·수동가·계좌유형·그룹), 저장 포트폴리오, 세금설정, 접속로그(created_at·last_login).
  - **수집·이용 목적**: 로그인 식별, 포트폴리오 분석/시뮬 제공, 화면 개인화.
  - **보유·이용 기간**: 회원 탈퇴 시까지 / 탈퇴 즉시 파기(또는 법정 보존분만 분리).
  - **제3자 제공·처리위탁**: Google(OAuth 인증). 외부 시세(yfinance·FRED)는 개인정보 미전송 명시.
  - **이용자 권리**: 열람·정정·삭제·동의철회, 회원탈퇴(아래 1.5).
  - **파기 절차·방법**, **개인정보 보호책임자(연락처)**.
- ⚠️ 보유자산 = 민감 금융정보 성격 → 표현·보관 신중.

### 1.2 이용약관 페이지 (`/terms`)
- `templates/legal/terms.html`. 항목: 서비스 정의, 계정, 금지행위, **면책(투자 결과 비보장)**, 책임제한, 데이터 정확성 비보장(시세 지연·합성데이터 고지), 준거법·분쟁.

### 1.3 투자 면책 통합 + 유사투자자문 규제선 점검
- 흩어진 문구 → 공용 컴포넌트(`templates/_disclaimer.html` 또는 footer)로 일원화. 핵심 문구: **"본 서비스는 정보 제공 목적이며 투자자문·매수권유가 아닙니다. 과거 데이터 기반 시뮬레이션은 미래 수익을 보장하지 않습니다."**
- ⚠️ **유사투자자문업 규제 회피 점검**: 특정 종목의 매수/매도 타이밍을 단정·권유하는 표현 금지. 현재 "상승견인/하락방어", 배당 역산 등은 정보제공 범위로 보이나, **카피·UX가 "이 종목 지금 사라"로 읽히지 않는지** 법무 검토 권장(자본시장법 유사투자자문 신고 대상 여부).

### 1.4 가입 동의 플로우
- OAuth 콜백 후 최초 1회 약관·개인정보 동의 화면(체크 후 진행). 
- `users`에 `agreed_terms_at TEXT`, `agreed_privacy_at TEXT` 컬럼 추가(ALTER, 결정성·후방호환). 미동의 사용자는 동의 페이지로 리다이렉트.

### 1.5 회원탈퇴 / 데이터 삭제 (`/account/delete`)
- 이용자 권리 이행 필수. POST → 해당 user_id의 `holdings`·`asset_groups`·`saved_portfolios`·`user_settings`·home_widgets·`users` 전부 삭제 + 세션 파기.
- 확인 모달(브랜드 모달, 네이티브 confirm 금지 — 오너 규칙).

### 1.6 전역 footer (`base.html`)
- footer 추가: 약관·개인정보·면책 링크 + © + "시세 15분 지연·정보제공 목적". 현재 footer 전무 → 신설.

---

## PART 2 — 보안 / 남용방지 (공개 서비스 필수)

### 2.1 Rate Limiting (최우선 — 무거운 엔드포인트 보호)
- `flask-limiter` 추가, **storage = 기존 redis**(다중 워커 일관). 
- 정책(초안, 로그인 user_id 기준 + 비로그인 IP):
  - 글로벌 기본: 분당 60.
  - **무거운 시뮬**(`/submit`·`/run`·`/scenario`): user당 **분당 5~10 + 동시 1개**(celery task 중복 방지).
  - `/api/search`: 분당 30.
- 초과 시 429 + 브랜드 토스트. 비용 큰 MC를 소수가 두드려 1vCPU 박스 다운시키는 것 차단.

### 2.2 Task 큐 남용 방지
- 사용자당 동시 실행 task 1개 강제(진행 중이면 신규 거절/취소-후-재실행). 큐 길이 상한.
- 입력 상한: 종목 수·기간·MC 케이스 수 cap(일부 limit_confirm 존재 → 서버측 하드 cap 일원화).

### 2.3 CSRF 보호
- 상태변경 POST(holdings 저장/삭제, 설정, 포폴 저장, 회원탈퇴)에 CSRF 토큰(`flask-wtf` 또는 커스텀) + 쿠키 `SameSite=Lax`. OAuth state 파라미터 검증 점검.

### 2.4 보안 헤더 / 쿠키
- 세션 쿠키 `Secure`·`HttpOnly`·`SameSite` 확인/강제.
- 보안 헤더: HSTS, X-Frame-Options(클릭재킹), X-Content-Type-Options, 기본 CSP(외부 cdn 허용목록 — html2canvas·chart.js 등). flask-talisman 또는 수동 after_request.

### 2.5 비밀/설정 점검
- `SECRET_KEY`·OAuth secret·Sentry DSN 환경변수화 확인(코드 하드코딩 0). 디버그 모드 prod off.

---

## 단계 / 우선순위
1. **P-A(법적 게이팅)**: 1.1 개인정보 → 1.2 약관 → 1.6 footer → 1.4 동의 → 1.5 탈퇴 → 1.3 면책통합·규제검토. 사용자 받기 전 완료.
2. **P-B(보안)**: 2.1 rate limit → 2.2 큐cap → 2.4 헤더/쿠키 → 2.3 CSRF → 2.5 점검.
- 1.3 유사투자자문 규제선·약관 문구는 **법무(전문가) 검토 권장** — 코드로 못 끝냄.

## 검증
- 법적: 각 페이지 렌더(라이트/다크·모바일), 동의 없는 신규계정 → 동의 리다이렉트, 탈퇴 후 DB 잔존 0 확인.
- 보안: rate limit 초과 시 429(부하 스크립트), CSRF 토큰 없는 POST 거절, 헤더 응답 확인, 세션 쿠키 속성 확인.

## 리스크
- 동의 컬럼 추가 = 기존 사용자 마이그레이션(다음 로그인 시 동의 받기).
- rate limit 과하면 정상 사용 방해 → 수치 보수적 시작 후 조정.
- 규제(유사투자자문)는 판단 영역 → 전문가 확인 전엔 보수적 카피.
