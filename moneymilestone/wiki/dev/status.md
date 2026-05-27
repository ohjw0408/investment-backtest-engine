---
updated: 2026-05-27
tags: [dev]
---

# 현재 개발 상태

**에이전트: 코드 작업 완료 후 이 파일 반드시 업데이트.**

---

## 한 줄 요약

> 배당 계산기 세금 연동(Phase 2c) 구현 완료. 단, ETF 데이터 불일치로 검증 게이트 블로킹. 데이터 안정화(Track A)가 지금 1순위.

---

## 최근 완료된 작업 (Codex 세션 2026-05-27)

- ✅ 목표 배당금 계산기: 0%/짧은 히스토리 ETF가 합성 배당 통계를 왜곡하던 문제 수정
- ✅ 한국 ETF 가격 로더: `pykrx` fallback 제거. 한국 ETF 가격은 yfinance 경로만 사용
- ✅ 월납입금 자동 역산: 초기자금 증가 시 필요 월납입금이 역전되던 버그 수정
- ✅ KODEX 미국배당다우존스: 자동 역산 bracket 과도 확장으로 그래프 개형 볼록해 보이던 문제 수정
- ✅ 기간 자동 역산 탐색 범위: 1~70년으로 확장. 정확도는 기존 1년 단위 유지
- ⚠️ 확인 필요: 은퇴 시뮬레이션에도 유사한 짧은 히스토리/합성 통계 문제가 있는지 미검증

---

## 현재 블로커 ❌

| 블로커 | 원인 | 관련 파일 |
|---|---|---|
| SCHD vs TIGER 배당 결과 불일치 | DJUSDIV100 인덱스 데이터 부족 | `backfill_engine.py`, `index_loader_develop.py` |
| Phase 2c Gate 미통과 | 위 블로커 해결 전까지 | `dividend_logic.py`, `dividend_simulator.py` |
| `_fetch_fred()` 메서드 없음 | `index_loader_develop.py` 버그 | `modules/index_loader_develop.py` |
| 백필 실패 코드가 완료 처리됨 | `PriceLoader._backfilled_codes` | `modules/price_loader.py` |

---

## 완료된 것 ✅

### 세금 리팩토링
- Phase 1: 공통 세금 코어, 절세매도 12월 분리, 청산세 통일 (Gate 1 ✅)
- Phase 2a: `TaxableSimulationRunner` 구현, 백테스트 전환 (Gate 2a ✅)
- Phase 2b: 투자계산기 + 은퇴 적립 Runner 전환 (Gate 2b ✅)
- Phase 2c: 배당 역산 Runner 구현 완료 (Gate 검증 대기 중)
- 버그픽스: KR_FOREIGN 청산 손익통산 제거 (개별 15.4% 분리과세)
- 버그픽스: US_DIRECT 리밸런싱 손실 손익통산 반영

### 배당금 계산기 버그픽스
- 9.4억 폭증 버그 수정
- 5년 역전 버그 수정 (로지스틱)
- pykrx fallback 제거, yfinance 단일화
- 그래프 개형 볼록 문제 수정
- 역산 탐색 범위 1~70년 확장

### PHASE4 기능
- A1 검색 퍼지/오타 허용
- A2 종목명 우선 표시
- A3 검색 레이아웃 가로형
- A5 검색 탭 분리
- A6 암호화폐 데이터 추가
- B5 리밸런싱 기능 정확도 검증
- C3 시장 지수 클릭→차트
- C5 결과 공유 URL+이미지 (워터마크, OG태그)
- D3 세금설정 UI 개선

---

## 진행 중 / 대기 ⏳

| 트랙 | 내용 | 선행 조건 | 실행 명령어 |
|---|---|---|---|
| **Track A** | ETF 데이터/백필 안정화 | 없음 (지금 시작) | `마스터 로드맵의 Immediate Track A 진행해줘` |
| Track B | Phase 2c Gate 재검증 | Track A 완료 | `Phase 2c Gate 재검증해줘` |
| Track C | 합성 데이터 공통 facade | Track B 완료 | `SYNTHETIC_DATA_INTEGRATION_PLAN Phase 1부터 진행해줘` |
| Track D | 세금 Phase 2d (은퇴 인출 세금) | Track B 완료 | `세금 Phase 2d 진행해줘` |
| Track D | 세금 Phase 2e (종합과세 경고 패널) | Phase 2d 완료 | — |
| Track D | 세금 Phase 3 (정리·ISA Runner 통일) | Phase 2d+e 완료 | — |
| Track E | PHASE4 잔여 기능 | Track A 완료 후 안전한 것부터 | `PHASE4 다음 안전한 항목 진행해줘` |

---

## PHASE4 잔여 기능 체크리스트

**중단기 (세금/데이터 독립적 → 병렬 가능):**
- [ ] D4 거래수수료 설정 (1~2일) — Runner 안정 후
- [ ] D5 인플레이션 검증 + 실질 생활비 표시 (2~3일)
- [ ] A4 종목 상세 개선 + 시간봉 차트 (3~4일)
- [ ] B1 포트폴리오 즐겨찾기/저장 (2~3일)
- [ ] B2 자산 추이 스냅샷 + 홈 토글 (1~2일)
- [ ] B3 리밸런싱 경고 밴드 (1일, B2 선행)
- [ ] C1 홈 화면 watchlist (2~3일)
- [ ] C2 자산군별 수익률 비교 (2~3일)
- [ ] F1 대기 순위 UX 수정 (0.5일)

**복잡한 기능 (순서 중요):**
- [ ] B4 거래 트래킹 + 추가매수 고도화 (3~4일, B2/B3 선행)
- [ ] D1 TDF 기능 (3~4일, Phase 2d 선행)
- [ ] D2 연금 통합 계산기 (4~5일, Phase 2d 선행)
- [ ] D6 합성 데이터 백테스트 체크박스 (1~2일, Track C 선행)

**나중에:**
- [ ] C4 온보딩 튜토리얼 (전체 완료 후)
- [ ] E1 모바일 반응형 (전체 완료 후)
- [ ] E2 코드 최적화 (프로파일링 후)

---

## 사업 일정 대비

| 기간 | 계획 | 현황 |
|---|---|---|
| 2026.06 | 시뮬레이션 엔진 개발 | ⏳ Track A/B 완료해야 |
| 2026.07 | 배당/알림/은퇴/TDF 기능 | ⏳ 대기 |
| 2026.08 | 로그인, 계정, 즐겨찾기 | ⏳ 대기 |
| 2026.09 | iOS/Android 안정화 | ⏳ 대기 |
| 2026.10 | 수익 모델 구현 | ⏳ 대기 |
| 2026.11 | 마케팅 + 앱스토어 배포 | 🎯 목표 |

→ 상세 Phase 기록: [[dev/phases]]
→ 버그 목록: [[dev/bugs]]
→ 아이디어: [[dev/ideas]]
