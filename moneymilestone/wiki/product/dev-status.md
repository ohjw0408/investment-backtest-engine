---
updated: 2026-05-27
sources: [PROJECT_MASTER_ROADMAP.md, 세금에서시작된완전리팩토링계획.plan.md]
tags: [product, tech]
---

# 개발 현황 + 블로커

마지막 업데이트: 2026-05-27 기준.

## 현재 상태 한 줄 요약

> 배당금 계산기 세금 연동(Phase 2c)까지 구현 완료했으나, ETF 데이터 품질 문제로 검증 게이트 통과 못 함. 데이터 안정화가 현재 1순위.

## 세금 리팩토링 진행 상황

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 1 | 세금 공통 코어, 절세매도 분리, 청산세 통일 | ✅ 완료 (Gate 1 통과) |
| Phase 2a | TaxableSimulationRunner + 백테스트 | ✅ 완료 (Gate 2a 통과) |
| Phase 2b | 투자계산기 + 은퇴 적립 Runner 전환 | ✅ 완료 (Gate 2b 통과) |
| Phase 2c | 배당 역산 Runner 전환 | ✅ 구현 완료 / ❌ Gate 블로커 |
| Phase 2d | 은퇴 인출 세금 주입 | ⏳ 대기 (2c 선행 필요) |
| Phase 2e | 금융소득 종합과세 경고 + 분할매도 패널 | ⏳ 대기 |
| Phase 3 | 정리, ISA Runner 통일, 문서화 | ⏳ 대기 (Phase 2 전체 완료 후) |

## ❌ 현재 블로커: ETF 데이터 불일치

**증상**: SCHD와 TIGER 미국배당다우존스(458730)가 같은 입력으로 완전히 다른 배당 시뮬 결과 반환.

**근본 원인** (4가지):
1. `DJUSDIV100` 인덱스 데이터가 불완전하거나 너무 짧음
2. 한국 상장 U.S. Dividend ETF들이 실제 데이터가 짧아서 합성 통계로 너무 빨리 fallback
3. `DividendSimulator._calc_div_stats()`가 현재 미완료 연도를 통계에 포함 (가격수익률 왜곡)
4. 백필/합성 row 구분 weak (`volume=0`만으로는 부족, provenance 테이블 없음)

**해결 방향** (Track A: ETF 백필 안정화):
1. 진단 스크립트로 현재 백필 현황 파악
2. `DJUSDIV100` 인덱스 데이터 보강 (신뢰할 수 있는 소스로)
3. `index_loader_develop.py` `_fetch_fred()` 메서드 수정
4. `PriceLoader` 실패한 백필을 세션에서 완료 처리하지 않도록 수정
5. `dividend_simulator._calc_div_stats()` 미완료 연도 제외
6. SCHD vs TIGER 비교 재실행

## 다음 실행 트랙 (의존성 순서)

```
Track A: ETF 데이터 안정화 (현재 최우선)
  → Track B: Phase 2c Gate 재검증
  → Track C: 합성 데이터 공통 facade
  → Track D: 세금 Phase 2d (은퇴 인출)
  → Track E: PHASE4 제품 기능 계속
```

### Track A 실행 명령어
```
마스터 로드맵의 Immediate Track A 진행해줘
```

### Track B 실행 명령어
```
Phase 2c Gate 재검증해줘
```

## 사업 일정 대비 현재 위치

| 기간 | 계획 | 현황 |
|---|---|---|
| 2026.06 | 시뮬레이션 엔진 개발 | ⏳ 세금 리팩 완성 필요 |
| 2026.07 | 기타 엔진 (배당, 알림, TDF) | ⏳ 배당 세금 연동 블로커 |
| 2026.08 | 로그인, 개인 계정, 즐겨찾기 | ⏳ 대기 |
| 2026.09 | 코드 안정화 (Windows/iOS/Android) | ⏳ 대기 |
| 2026.10 | 수익 모델 (구독, 광고) | ⏳ 대기 |
| 2026.11 | 마케팅 + 앱스토어 배포 | 🎯 목표 |

→ 전체 기능 목록: [[product/features]]
