# tests/ 분류 가이드 (출시완성도 H-1)

125개 파일이 4가지 스타일 혼재. **파일 이동은 하지 않는다** (import·위키 참조 파손 리스크 > 정리 이득 — 분류는 이 문서로).

## 1. pytest 단위/회귀 (CI 후보 — DB-독립인 것만)

`python -m pytest tests/test_X.py` 로 실행. **CI(deploy.yml test job)에 포함된 DB-독립 서브셋:**

- `test_engine_integrity.py` · `test_basic_simulation.py` · `test_cash_and_dividend_engine.py`
- `test_dca_engine.py` · `test_engine_dca_simulation.py` · `test_band_dca_dividend.py`
- `test_d4_fee_logic.py` · `test_saved_portfolios.py` (임시 users.db 패치)
- `scripts/perf_golden.py check` (골든마스터 — 엔진 결과불변, _FakeLoader라 DB 0)

나머지 pytest 파일은 로컬 `price_daily.db`/네트워크 의존 가능 → 로컬 타겟 실행 전용.
CI 추가 기준: **`data/price_cache`·`data/private` 없는 상태에서 PASS** (검증 방법: 두 폴더 임시 리네임 후 실행).

## 2. 스크립트식 자체 러너 (`python tests/test_X.py` 직접 실행)

pytest로 돌리면 수집 단계에서 SystemExit — **반드시 python 직접 실행.**
예: `test_alerts_api.py`(39), `test_alert_runner.py`(10, CI 포함), `test_home_widgets.py`(18), `test_push_consent.py`, tax 계열(`tax_truth_test.py` 등).

## 3. 브라우저 검증 (Node/Playwright/jsdom)

`node tests/test_X.js` 또는 Playwright 세션. 예: `check_*.js`, `test_*_dom.js`, `test_fan_live.js`, `e2e_multitax/`.
프론트 변경 시 필수 — `moneymilestone/wiki/dev/frontend-verification.md` 절차.

## 4. 라이브 probe / 디버그 (자동화 금지)

prod·실데이터 대상 일회성 진단: `probe_*.py`, `debug_*.py`, `diag_*`, `datatest.py`, `shots*/`.
CI·정기 실행 금지. `mint_session.py` = dev 세션 쿠키 서명(로컬 OAuth 우회 도구).

## 실행 규칙 (오너 지시)

- **전체 `pytest tests/` 회귀 금지**(로컬 ~10분). 변경 범위 타겟만.
- 공유 엔진(`modules/simulation`·`tax`·`execution`) 변경 시 전체 회귀는 오너에게 먼저 확인.
- 엔진 최적화/리팩토링 = `scripts/perf_golden.py check` + `scripts/perf_ab.py` 필수.
