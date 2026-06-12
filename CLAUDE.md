# Money Milestone — Claude Code 운영 지침

이 프로젝트는 `moneymilestone/` 폴더를 지식베이스(wiki)로 사용한다.

## 세션 시작 시 반드시

1. `moneymilestone/README.md` 읽기 — 전체 운영 규칙
2. `moneymilestone/wiki/index.md` 읽기 — 페이지 목록
3. `moneymilestone/wiki/log.md` 최근 3~5개 항목 읽기 — 최근 맥락
4. 작업 관련 wiki 페이지 읽기

## 코드 작업 완료 후 반드시 (세션 마무리 기다리지 말고 작업 완료 즉시)

- `moneymilestone/wiki/dev/status.md` 업데이트 (완료 ✅ 표시)
- `moneymilestone/wiki/dev/bugs.md` 업데이트 (버그 추가/수정)
- `moneymilestone/wiki/log.md` 항목 추가
- 새 페이지 만들었으면 `moneymilestone/wiki/index.md` 갱신
- **wiki 변경사항 git commit + push (코드 커밋에 포함하거나 별도 커밋)**

## 테스트 실행 규칙 (오너 지시, 2026-06-12)

- **전체 pytest(`pytest tests/`) 회귀 금지.** ~10분 소요 — 변경 범위에 맞는 타겟 테스트만 실행한다.
  - API/라우트 변경 → 해당 API 테스트 (예: `tests/test_saved_portfolios.py`)
  - 특정 엔진/모듈 변경 → 그 모듈의 테스트 파일만
  - UI/템플릿/JS 변경 → jsdom·Playwright 스위트 (브라우저 검증이 주력)
- 예외: 공유 엔진 코드(`modules/simulation`, `modules/tax`, `modules/execution` 등 여러 탭이 공유하는
  경로) 변경 시에만 전체 회귀를 고려하되, **돌리기 전에 오너에게 먼저 물을 것.**
- 검증의 중심은 결정론 타겟 테스트 + 실브라우저(Playwright) + 라이브 probe.
  로그인 필요한 E2E는 `tests/mint_session.py`(dev 세션 쿠키 서명, 로컬 전용)로 OAuth 우회 가능.

## 인코딩 규칙

- 모든 wiki 파일은 UTF-8. 파일 전체 덮어쓰기 금지.
- 기존 내용 보존, 필요한 부분만 최소 수정 또는 append.
- 확실하지 않은 내용은 사실처럼 쓰지 말고 `⚠️ 확인 필요` 로 남길 것.
