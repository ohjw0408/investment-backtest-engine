# Money Milestone — Wiki 운영 매뉴얼

**모든 AI 에이전트 (Claude, Codex, 기타)가 이 파일을 먼저 읽을 것.**

---

## 이 vault가 하는 일

Money Milestone 프로젝트(자산배분 투자 계산기 앱)의 **지식베이스 + 개발 상태 추적 시스템**.

- AI 에이전트들이 공동으로 읽고 쓰는 단일 진실 공급원(single source of truth)
- 개발 진행 상황, 버그, 아이디어, 결정 기록
- 사업 기획 + 경쟁사 + 유저 분석 (참고용)

오너(비개발자)는 읽기만 함. 쓰기는 AI 에이전트가 함.

---

## 핵심 소스 파일 경로

```
창업계획서:
  C:\Users\ohjw4812\Documents\카카오톡 받은 파일\창업계획서.pdf

개발 계획서 (코드 repo):
  C:\Users\ohjw4812\Documents\investment_projects\investment-backtest-engine\
    PROJECT_MASTER_ROADMAP.md          ← 전체 조율 문서, 먼저 읽을 것
    PHASE4_PLAN.md                     ← 제품 기능 로드맵
    세금에서시작된완전리팩토링계획.plan.md  ← 세금/시뮬 리팩토링
    ETF_BACKFILL_ARCHITECTURE_PLAN.md  ← ETF 데이터 아키텍처
    SYNTHETIC_DATA_INTEGRATION_PLAN.md ← 합성 데이터 통합

코드베이스 (이 vault의 상위 폴더 = ../):
  C:\Users\ohjw4812\Documents\investment_projects\investment-backtest-engine\
```

---

## Wiki 폴더 구조

```
moneymilestone/
├── README.md         ← 이 파일. 에이전트 운영 매뉴얼.
├── CLAUDE.md         ← Claude Code용 alias (README 읽을 것)
├── AGENTS.md         ← Codex용 alias (README 읽을 것)
├── raw/              ← 소스 문서 참조 목록 (원본 변경 금지)
└── wiki/
    ├── index.md      ← 전체 페이지 카탈로그 (항상 최신 유지)
    ├── log.md        ← 연대순 기록 (append-only, 절대 삭제 금지)
    ├── dev/          ← 개발 상태 (가장 중요)
    │   ├── status.md     현재 완료/진행/블로커 한눈에
    │   ├── phases.md     Phase별 세부 진행 상황
    │   ├── bugs.md       알려진 버그 목록
    │   └── ideas.md      기능 아이디어 + 미결 결정
    ├── product/      ← 기능 명세
    │   └── features.md
    ├── business/     ← 경쟁사, 유저, 수익 모델
    └── overview.md
```

---

## 에이전트 행동 규칙

### 파일 수정 / 인코딩 규칙

- 모든 markdown 파일은 반드시 UTF-8 인코딩을 유지한다.
- 파일 전체를 덮어쓰기 전에 반드시 기존 내용을 UTF-8로 읽고, 필요한 부분만 최소 수정한다.
- `wiki/log.md`는 append-only다. 기존 항목을 삭제하거나 재작성하지 말고 새 항목만 추가한다.
- 한글이 깨져 보이면 바로 수정하지 말고, 먼저 터미널/도구의 출력 인코딩 문제인지 확인한다.
- 인코딩이 불확실한 상태에서는 파일 저장을 중단하고 사용자에게 확인한다.

### 세션 시작 시 반드시

1. 이 `README.md` 읽기
2. `wiki/index.md` 읽기 → 관련 페이지 파악
3. `wiki/log.md` 최근 3~5개 항목 읽기 → 최근 맥락 파악
4. 작업 관련 wiki 페이지 읽기

### 코드 작업 완료 후 반드시 (세션 마무리 기다리지 말고 작업 완료 즉시)

1. `wiki/dev/status.md` 업데이트 (완료된 항목 ✅ 표시)
2. `wiki/dev/bugs.md` 업데이트 (새 버그 발견 or 수정된 버그)
3. `wiki/log.md`에 항목 추가
4. `wiki/index.md` 업데이트 (새 페이지 생성했을 경우)
5. **wiki 변경사항 git commit + push (코드 커밋에 포함하거나 별도 커밋)**

### 오너가 "정리할 거 정리해"라고 하면 (세션 마무리 동기화 — **필수 규칙**)

오너가 세션 끝나기 전 **"정리할 거 정리해"** (또는 유사 표현)라고 말하면, 다음을 **전부** 수행한다. 부분 동기화 금지.

1. **모든 계획 파일 정독** (코드 repo 루트):
   - `PROJECT_MASTER_ROADMAP.md`, `PHASE4_PLAN.md`, `세금에서시작된완전리팩토링계획.plan.md`,
     `ETF_BACKFILL_ARCHITECTURE_PLAN.md`, `SYNTHETIC_DATA_INTEGRATION_PLAN.md`, `isafix.md`,
     `trackG_multiaccount_plan.md`, `handoff.md` 등 활성 계획 전부.
2. **모든 wiki 파일 정독**: `wiki/dev/*` (status/phases/bugs/ideas), `wiki/product/*`,
   `wiki/log.md`, `wiki/index.md`.
3. **실제 코드/진행 상황과 대조**해 각 파일의 진행상태를 **정확히** 최신화한다:
   - 거짓 "완료" 주장 금지. done / 부분구현 / 미검증 / 블로커를 사실대로 표기.
   - 파일 간 모순(한 파일은 완료, 다른 파일은 대기)을 발견하면 실제 상태로 통일.
   - 새로 발견된 블로커·갭을 owner 계획 파일에 기록.
4. **그 다음** `PROJECT_MASTER_ROADMAP.md`를 같은 방식으로 최신화 (현재 위치 + 다음 할 일 + 블로커).
5. `wiki/log.md`에 동기화 항목 추가 + 변경사항 git commit + push.

> 목적: 다음 세션(또는 다른 에이전트)이 어느 파일을 봐도 **일관되고 정확한** 현재 상태를 알 수 있게. 계획 파일이 서로 stale·모순되는 상태를 방지.

### 새 소스 ingest 시

1. 소스 읽기
2. 관련 wiki 페이지 업데이트 또는 신규 생성
3. `wiki/index.md` 갱신
4. `wiki/log.md` 항목 추가: `## [YYYY-MM-DD] ingest | 소스명`

### 아이디어/결정 발생 시

- `wiki/dev/ideas.md`에 바로 기록
- 채팅에서 논의한 내용이 사라지면 손실 → wiki가 기억

### 테스트 실행 규칙 (오너 지시, 2026-06-12)

- **전체 pytest 회귀(`pytest tests/`) 금지** — ~10분 소요. 변경 범위에 맞는 **타겟 테스트만** 실행.
- 예외: 여러 탭이 공유하는 엔진 코드(`modules/simulation`·`modules/tax`·`modules/execution` 등)
  변경 시에만 전체 회귀 고려 — 그때도 **오너에게 먼저 확인**.
- 검증 중심 = 결정론 타겟 테스트 + 실브라우저(Playwright) + 라이브 probe.
  로그인 E2E는 `tests/mint_session.py`(dev 세션 쿠키, 로컬 전용)로 OAuth 우회.
- 상세는 repo 루트 `CLAUDE.md` "테스트 실행 규칙" 참조.

---

## 페이지 포맷

### 상태 표시
- ✅ 완료
- ⏳ 진행 중 / 대기
- ❌ 블로커 / 차단됨
- 💡 아이디어 / 미검증
- ⚠️ 주의 필요 / 버그

### YAML 프론트매터 (선택)
```yaml
---
updated: YYYY-MM-DD
sources: [파일명]
tags: [dev, product, business, bug, idea]
---
```

### 크로스 링크
`[[페이지명]]` 형식. Obsidian 그래프 뷰에서 시각화됨.

### log.md 항목 형식
```
## [YYYY-MM-DD] <타입> | <제목>
타입: ingest | bugfix | feature | decision | idea
```

### 작성자 서명 규칙 (**필수**)

**모든 wiki 항목에는 작성자를 명시한다.** 에이전트/사람 구분 없이 적용.

`log.md` 항목 끝에 한 줄 추가:
```
_작성: Claude_ 또는 _작성: Codex_ 또는 _작성: 오너_
```

`status.md`, `bugs.md` 등 테이블 업데이트 시에는 셀 안에 `(Claude)` / `(Codex)` 괄호 표기:
```
| ✅ 수정 완료 (Claude) |
```

계획 문서(`ETF_BACKFILL_ARCHITECTURE_PLAN.md` 등) 섹션 추가 시에는 섹션 하단에:
```
_검토/추가: Codex, 2026-05-28_
```

**서명 없는 항목은 나중에 누가 썼는지 알 수 없다. 반드시 남길 것.**

---

## 현재 프로젝트 컨텍스트 (2026-06-10 갱신)

**앱**: Flask 웹앱 + Celery 비동기 계산 + Redis + SQLite × 4개 DB.  
**배포**: Hetzner VPS Ubuntu, SSH키 `~/.ssh/hetzner_ed25519`, IP `178.105.84.213`.
라이브 `https://moneymilestone.co.kr` (main push = 자동배포).
**언어**: Python (백엔드) + HTML/JS (프론트, 프레임워크 없음).
**JS 테스트 도구**: `package.json` devDependencies — jsdom(DOM 스모크) + **Playwright Chromium**(실브라우저·스크린샷, 2026-06-10 도입).

**현재 상태**: 블로커 없음. (2026-06-13 전체 동기화)
- P0~P3 전부 마감: G5 4탭 + L7 E2E 16/16 + 절세액 P1~P3 + `/simple` + `/tax-switch` + B1 즐겨찾기(`/myportfolios`+5탭 위젯) + `/risk-return` + 모바일·다크.
- GAP-DECUM-COMP·BUG-PENSION-1 = 기해소 확인(stale 정리). trackG·isafix·E2E plan 종결.
- → 최신 상세는 항상 `wiki/dev/status.md` 한 줄 요약 최상단.

**다음 액션** (오너 결정 대기):
```
P4 배당 절세 (선행=divrefactoring.md) OR PHASE4 잔여(D4/B2-a/A4/D1/D2/C1/C2)
```
