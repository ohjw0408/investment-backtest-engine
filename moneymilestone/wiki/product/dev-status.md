---
updated: 2026-06-13
sources: [PROJECT_MASTER_ROADMAP.md, trackG_multiaccount_plan.md, 세금에서시작된완전리팩토링계획.plan.md]
tags: [product, tech]
---

# 개발 현황 + 블로커

마지막 업데이트: 2026-06-13 기준. (최신 상세는 [[dev/status]]가 항상 우선)

## 현재 상태 한 줄 요약

> ✅ **P0~P3 전부 마감 (2026-06-13 동기화).** Track G5 4탭 + L7 E2E 16/16 + 절세액 P1~P3 + 간편계산기(`/simple`) + ISA전환(`/tax-switch`) + B1 즐겨찾기(`/myportfolios`+5탭 위젯) + 리스크리턴도표(`/risk-return`) + 모바일·다크모드 전부 완료·배포. GAP-DECUM-COMP·BUG-PENSION-1 = 기해소 확인(stale 정리). 블로커 없음. **다음 후보 = P4 배당 절세(`divrefactoring.md` 선행) OR PHASE4 잔여(D4·B2-a·A4·D1·D2·C1·C2) — 오너 결정.** 상세 = [[dev/status]].

## 세금 리팩토링 진행 상황

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 1 | 세금 공통 코어, 절세매도 분리, 청산세 통일 | ✅ 완료 (Gate 1 통과) |
| Phase 2a | TaxableSimulationRunner + 백테스트 | ✅ 완료 (Gate 2a 통과) |
| Phase 2b | 투자계산기 + 은퇴 적립 Runner 전환 | ✅ 완료 (Gate 2b 통과) |
| Phase 2c | 배당 역산 Runner 전환 | ✅ 완료 (Gate 2c 재검증 PASS, 2026-05-31) |
| Phase 2d | 은퇴 인출 세금 주입 | ✅ 완료 (Gate 2d 5/5) ⚠️ BUG-TAX-2: 인출 매도 위탁 양도세 누락은 수정됨(공유 sell_with_tax) |
| Phase 2e/2f | 금융소득 종합과세 + 분할매도 패널 | ✅ 완료 (4100ecd) — 자동산출·전탭배선·_ytd_income 주입·인출(decum) 경로까지 확인(06-12) |
| Phase 3 | 정리, ISA Runner 통일, 문서화 | ✅ 완료 |
| phase1-api | TaxProfile API 통일 (other_financial_income 주입) | ✅ 완료 (2026-06-13 정리 — 2f로 충족) |

**종합과세(Phase 2e/2f) 실제 상태** (2026-06-13 코드 재확인):
- ✅ 계산 엔진 (`base_tax._comprehensive_tax`/2천만 임계/비례공제) — `tax_truth_test` 단위검증 통과
- ✅ 시뮬 내 당해연도 배당+KR_FOREIGN 실현차익 YTD 합산 (공유 `TaxSessionState`)
- ✅ 분할매도/종합과세 패널 — backtest·calculator·retirement 배선 (배당탭만 별도엔진 제외)
- ✅ `other_financial_income` 자동산출 (`recurring_financial_income`, 직전 완료년도)
- ✅ `_ytd_income` 주입 (`account_tax.py:243`)
- ✅ 인출(decum) 경로 — `test_decum_comprehensive.py` 4 PASS (2026-06-12)

## ✅ 해결된 블로커: 배당 데이터 근본 버그

**기존 증상**: TIGER 미국배당다우존스(458730) 배당 지표 전부 0, SCHD 다수 0. 단일·다중계좌 공통.

**근본 원인** (`debug_dividend.py` 실측 2026-05-30):
1. 백필 가격은 프록시 체인으로 1928년까지 존재(458730 97%, SCHD 85%가 volume=0 백필).
2. 실측 배당(`corporate_actions`)은 ETF 상장 후만(SCHD 2011~, 458730 2023~). 백필 가격 구간에 배당 row 없음.
3. DJUSDIV_PROXY가 **adj-close(total-return)**라 배당이 가격에 임베딩 → 별도 액수 안 나옴 (`_NO_DIVIDEND_INDICES`에 의도적 제외).
4. `data_start`=1928 → 20년 롤링 윈도우 대부분 배당 이전 시대 → `_fit_distribution` p50=0.
5. 백필 provenance 전부 0행 (가격 백필이 `BackfillEngine` 우회).

**해결 방향** (`ETF_BACKFILL_ARCHITECTURE_PLAN.md § Phase 6.0` — 범용 배당 백필 재설계):
- 모든 백필을 'price-return 가격 + 명시적 배당' 표준으로 통일 (total-return 임베딩 폐기, 이중계산 차단).
- Stage A 주식/배당형 먼저 → Stage B 채권/MMF(필수, Phase 7).

**적용 결과** (2026-05-30, Codex):
- Stage A 서버 적용 완료: SCHD/458730/446720/402970 재백필 + 명시 배당 주입.
- 서버 `stage_a_verify.py`, `debug_dividend.py`, 계산기 직접 실행에서 배당 p50 > 0 확인.
- UI가 `div_real_start`/`div_backfill_start` 기준 실측/추정 구분 표시.

## 다음 실행 트랙 (2026-06-13 — P0~P3 전부 마감)

```
✅ [P0] Track G5 + L7 E2E 16/16        ✅ [P1] 간편계산기 + ISA전환 계산기
✅ [P2] 절세액 P1~P3 + 금종세(2f)       ✅ [P3] B1 즐겨찾기 + 리스크리턴도표
✅ [추가] D4 수수료 전탭 · A4 종목상세(캔들/시간봉) · C1 홈위젯·관심목록·설정(2026-06-14)
✅ [2026-06-15] C1 후속: 지수 캔들 회귀복구(index_ohlc) · 새로고침 버튼(내자산/홈/검색) · 내자산 수동가격
남은 후보 — 오너 결정:
  · P4 배당금계산기 절세 (선행 = divrefactoring.md 엔진 통합)
  · PHASE4 잔여: D1 TDF / D2 연금통합 / C2 자산군비교 / B4 거래트래킹  (C1·A4·D4 완료 / B2-a=skip)
  · 곁가지: KQ150 티커, 데이터 갭채움 스케줄러, 합성상관 서버검증, 벤치마크 영속화
```

### 다음 실행 명령어
```
(오너 결정 대기 — 예: "P4 배당 절세 하자" / "D1 TDF 하자")
```

## 사업 일정 대비 현재 위치

| 기간 | 계획 | 현황 |
|---|---|---|
| 2026.06 | 시뮬레이션 엔진 개발 | ✅ 사실상 완료 (세금 리팩·다중계좌·E2E 검증까지) — 일정 선행 |
| 2026.07 | 기타 엔진 (배당, 알림, TDF) | ⏳ 배당 엔진 통합(divrefactoring)·D1 TDF 후보로 준비됨 |
| 2026.08 | 로그인, 개인 계정, 즐겨찾기 | ✅ 로그인·계정·즐겨찾기 완료 (2026-06-12, 일정 2개월 선행) |
| 2026.09 | 코드 안정화 (Windows/iOS/Android) | ⏳ 대기 (모바일 웹 반응형은 완료) |
| 2026.10 | 수익 모델 (구독, 광고) | ⏳ 대기 (즐겨찾기 한도 = `get_portfolio_limit()` 요금제 차등 지점 준비됨) |
| 2026.11 | 마케팅 + 앱스토어 배포 | 🎯 목표 |

→ 전체 기능 목록: [[product/features]]
