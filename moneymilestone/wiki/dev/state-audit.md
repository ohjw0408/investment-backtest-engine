---
updated: 2026-07-03
tags: [dev, ux, audit]
---

# 3-상태 전수 감사 (출시완성도 F-1)

전 페이지 × 4상태 Playwright 자동 감사. 스크립트 = 세션 scratchpad `audit_states.js`
(재실행 시 재작성 필요 — 방법론은 아래).

## 방법론

- **상태 4종**: ①data(보유/포폴 있는 유저) ②empty(신규 빈 유저) ③anon(비로그인)
  ④apifail(`page.route('**/api/**', abort)` = 서버/네트워크 다운 시뮬)
- **수집 신호**: HTTP status, JS 예외(pageerror), native dialog(alert/confirm — 0이어야),
  본문 텍스트 길이(<80 = 빈 흰 화면), 멈춘 스피너(class *spin/load* visible),
  에러 UI 존재(오류/실패/불러오지 텍스트)
- 세션 쿠키 = `tests/mint_session.py` 방식 2벌(data/empty)

## 결과 (2026-07-03, 22페이지 × 4상태 = 88셀)

- **data / empty / anon = 66셀 전부 클린.** native dialog 0, 빈 흰 화면 0, 5xx 0,
  JS 에러 0, 비로그인 리다이렉트/온보딩 정상.
- **apifail = 5셀 문제 → 전부 수정**:

| 페이지 | 증상 | 수정 |
|---|---|---|
| `/` 홈 | `loadPortfolio` fetch 미가드 + 위젯 "불러오는 중..." 영구 | try/catch — 포폴카드 숨김 + 위젯 에러 문구 교체 |
| `/myassets` | `loadAll` fetch 미가드 → 빈 화면 | try/catch → `holdingsTableWrap`에 안내 문구 |
| `/alerts` | `loadRules`/`loadEvents` 미가드 ×2 | try/catch → 각 리스트에 안내 문구 |
| `/symbol/*` | `loadSymbol` 미가드 | try/catch → symbolContent 안내 문구 |
| `/macro` | (오탐) `.mc-loading` 클래스가 에러 메시지 컨테이너 — 이미 "불러오기 실패" 표시 | 무변경 |

공통 카피: **"일시적으로 불러오지 못했어요. 잠시 후 새로고침 해주세요."**

## 재검 (수정 후)

- apifail 5페이지: JS 에러 0·에러 UI 표시·영구 "불러오는 중" 0 (alerts는 비활성 탭
  안이라 innerText 검출만 안 될 뿐 양 컨테이너 렌더 확인)
- 정상 상태 회귀: 수정 4페이지 JS 에러 0·오발 에러문구 0·콘텐츠 정상

## 유지보수 규칙

- 신규 페이지의 로드 fetch는 **반드시 try/catch + 컨테이너 에러 문구** (이 감사가 잡은 패턴).
- 초기 placeholder("불러오는 중")는 실패 시 반드시 교체 — 영구 방치 금지.
