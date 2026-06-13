# 포트폴리오 비교 탭 plan

상태: ✅ **완료·배포 (2026-06-14).** `/risk-return` = "포트폴리오 비교"로 확장. 11지표 수치표 + 리스크리턴 산점도 + 레이더(축 선택·설명·표시토글·불투명도 18%) + 🔗링크/📷이미지. 구현 = `risk_return_logic._metrics_full`+`compute_comparison` / `POST /api/portfolio/compare` / `risk_return.html` / nav 라벨.
후속 반영(2026-06-14): 스파이더 축 7후보 선택+설명, CAGR→수익률(CAGR), 모바일 표→항목카드(가로스크롤 제거). **잔여(추후) = 몬테카를로 미래 부채꼴**(대공사라 이번 제외).

기존 `/risk-return`(리스크-리턴 도표)을 **"포트폴리오 비교"** 탭으로 확장.

## 오너 결정 (2026-06-14)
- 몬테카를로 부채꼴 **제외**(별도 대공사 — 추후).
- 지표 = **필수+고급셋**: CAGR·연변동성·MDD·Sharpe·배당수익률 + Sortino·최고/최저 연도수익률·승률(양의 달 비율)·베타(SPY 대비).
- 비교 기간 = **공통 겹침 자동**(현행 로직 유지, 3년 미만 경고).
- 벤치마크 기본셋 = 현행 DEFAULT_BENCHMARKS(SPY·QQQ·GLD·069500·TLT), 사용자 삭제/추가 가능.
- 스파이더 + (몬테카를로 빠져) overlay 대상 = 스파이더만. 표시 토글 + 투명도 슬라이더.
- 이미지/링크 저장 = 계산기 share 패턴 재사용(html2canvas → /api/share/upload).

## 구성
1. **종목 선택**: 내 포트폴리오 체크박스(전체 기본 선택) + 벤치마크 칩(기본셋 + 검색 추가/✕ 삭제).
2. **[비교하기]** 버튼 → 결과.
3. **수치표**: 행=항목(포폴+벤치), 열=11지표.
4. **리스크-리턴 산점도**(현행 유지: x=변동성, y=CAGR).
5. **스파이더(레이더)**: 핵심 6축(CAGR·안정성=1−vol·MDD방어=1−|mdd|·배당률·Sharpe·Sortino, min-max 정규화·클수록 좋음). 항목별 표시 체크 + 전역 투명도 슬라이더.
6. **공유**: 🔗 링크 / 📷 이미지.

## 변경 파일
- `risk_return_logic.py`: `_metrics_full()` + `compute_comparison(portfolios, benchmarks, loader)`. 기존 `compute_risk_return` 보존.
- `app.py`: `POST /api/portfolio/compare` ({portfolio_ids, benchmarks}). 기존 `/api/risk-return` 보존.
- `templates/risk_return.html`: 비교 UI 전면 개편.
- `templates/base.html`: 네비 라벨 "리스크-리턴" → "포트폴리오 비교".

## 검증
- venv test_client: compare(포폴+벤치) → items 11지표·period·skipped. SPY 베타≈1 sanity.
- JS node --check.
- 라이브 probe 게이팅(401)·페이지 200.
