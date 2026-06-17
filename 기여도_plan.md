# 기여도(Attribution) 분석 plan

작성: 2026-06-17. Owner 요청. 상태: ✅ **전체 구현·배포(2026-06-17).**

## ▶ 완료 기록 (2026-06-17)

- 엔진 `modules/attribution.py` — aligned_series(date컬럼 정렬)·daily_returns·regime_masks·
  contributions·shares + analyze_window/regime/rolling. 단위테스트 14 PASS. **원화 기준(apply_fx)** = 환율 포함 실수익.
- **내 자산**: `/api/myassets/attribution`(보유 비중) → 자산현황 탭 텍스트(지분% 중심). 견인/방어 1줄씩.
- **백테스트**: 값 추이 그래프 가로 드래그(chartjs-zoom) → `/api/attribution/window` → 다이버징 막대+지분%. 구간 해제 버튼.
- **투자계산기**: `/api/attribution/rolling`(롤링 168윈도우) → 결과 하단 표(상승 견인/하락 방어 평균±p25~p75).
- 실시세 검증: SPY/TLT — 2022구간 TLT 낙폭 96%, 롤링 SPY 견인/TLT 방어 우위. 전부 라이브 배포.

---


## 목적

포트폴리오 수익을 종목별로 분해 → **상승 견인 / 하락 방어 지분**을 보여준다.

핵심 수학(부호 가법 분해):
```
포폴 일간수익 r_p(t) = Σ 비중ᵢ × 종목수익ᵢ(t)
종목 i 기여(구간) = Σ_{t∈구간} 비중ᵢ × 종목수익ᵢ(t)
→ Σ 종목기여 = 구간 포폴 누적수익(일간합)   # 정확히 100% 분해
```
- 상승장 구간 합산 → 큰 놈 = 견인왕
- 하락장 구간 합산 → 덜 마이너스/플러스 = 방어왕
- "지분%" = 기여 / (같은 부호 기여 합)

## 화면별 사양 (Owner 결정 2026-06-17)

| 화면 | 사양 |
|---|---|
| **내 자산** | 텍스트 한 줄씩만: "상승에는 OO이 OO%p 기여 / 하락장에선 OO이 OO%p 방어". 보유 비중 기준, 최근 N년. |
| **백테스트** | **사용자 지정 구간.** 자산/낙폭 그래프에서 드래그(범위 선택)→그 구간 기여 지분(다이버징 막대 + %). |
| **투자계산기** | 롤링 시뮬 → **분포.** 윈도우별 기여 계산해 종목별 평균(±p25/p75) 상승기여·하락방어. |

## 공용 엔진 `modules/attribution.py` (순수 계산, loader 주입)

- `aligned_series(loader, codes, start, end, apply_fx=True)` → (dates, {code:[close]}). get_price의 `date` 컬럼 정렬(포폴지수 버그 교훈).
- `daily_returns(dates, series)` → (pdates, {code:[ret]}).
- `regime_masks(pdates, rets, weights)` → (up_idx, down_idx, port_daily).
- `contributions(rets, weights, idxs)` → {code: Σ 기여}. 비중은 codes로 재정규화.
- `analyze_window(loader, codes, weights, start, end)` → {up, down, total, period, n_up, n_down} (백테 구간용).
- `analyze_regime(loader, codes, weights, years)` → 상승/하락 구간 분해 (내자산용).
- `analyze_rolling(loader, codes, weights, window_days, step)` → 종목별 상승기여·하락방어의 분포(mean·p25·p75) (계산기용).

비중: v1 = 고정(입력 비중/보유 비중). 드리프트 정밀판은 후속.
구간 부호: 포폴 자체 일간 등락 기준(자기완결). (벤치마크 기준은 후속 옵션.)

## API

- `POST /api/attribution/window` {tickers[code,weight], start, end} → 백테 구간 기여.
- `GET  /api/myassets/attribution` → 내자산 보유 기준 상승/하락 요약.
- 계산기 분포는 계산기 결과 payload에 합치거나 별도 `POST /api/attribution/rolling`.

## 단계

1. 엔진 + 단위테스트(결정론 합성).
2. 내 자산 텍스트(API + UI).
3. 백테스트 구간 선택(드래그) + 다이버징 막대 (chartjs-plugin-zoom 이미 로드됨).
4. 투자계산기 분포.
5. 위키 동기화.
