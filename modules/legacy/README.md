# modules/legacy — 1세대 분석기 보관소

성능최적화 플랜(2026-06)에서 "프로덕션 미경유 死코드"로 판정된 1세대 분석기.
ARCHITECTURE.md의 "1세대 삭제 금지" 원칙에 따라 삭제 대신 이곳으로 이동 (출시완성도 D-2, 오너 승인 2026-07-02).

- engine_rolling_analyzer.py / portfolio_analyzer.py / retirement_analyzer.py / rolling_scenario_analyzer.py
- 프로덕션 경로는 `modules/simulation`·`modules/retirement`의 2세대 엔진 사용.
- 참조하는 곳 = 레거시 테스트뿐 (import 경로 `modules.legacy.*`로 함께 수정됨).
