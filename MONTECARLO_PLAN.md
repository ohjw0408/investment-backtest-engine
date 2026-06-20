# 몬테카를로(MVN) 시뮬 통일 계획

작성: 2026-06-20 (Claude). 오너 지시: 실데이터 부족 시 단일 합성경로 롤링 대신
**종목별 mu/sigma + 상관 피팅 몬테카를로**로 통일. 은퇴·계산기·배당금 전부.

## 배경 / 문제

은퇴 **인출** 결과가 비현실적: 5억 시작·월 300만(연 7.2%) 인출인데 하위10%도 30년 후 93억,
**고갈 0/61건**, p50 순CAGR 11.9%. 원인 = deep history가 **단일 합성 GBM 경로**이고
61개 "시나리오"는 그 한 경로를 30년 윈도우로 겹쳐 자른 것(독립 아님) → 거짓으로 좁고 전부 높음.

prod 동기 probe로 검증한 올바른 분포(독립 MC 50경로): p10 **0(고갈)**·p50 8.4억·p90 99.5억,
**고갈 40%**. = 현실적. (SCHD 실mu 8.2%/yr.)

## 이미 있는 자산 (재사용)

`modules/retirement/synthetic_mvn.py` — **정석 MVN MC가 이미 구현됨**:
- `estimate_joint_stats(tickers, raw_loader)`: 종목별 mu/sigma(일일) + **쌍별 상관행렬**(nearest-PSD) + cov + actual_start.
- `generate_joint_window(tickers, joint_stats, ws, we, raw_loader)`: 윈도우 1개의 **조건부 다변량-t 합성 prefix + 실 suffix** → `(price_data{code:df}, dates)`. 합성 drift 상한(`MU_DAILY_CAP`) backstop. seed = hash(codes+window_start)로 윈도우별 독립.
- 종목별 변동성·기대수익 경향 + 상관(QQQ-SCHD 동조, GLD 헤지) 반영. = 오너가 원한 "피팅된 MC".

**현황**:
- ✅ `AccumulationAnalyzer._load_with_per_window_synthetic` → estimate_joint_stats + generate_joint_window 사용(폴백=종목별 독립 GBM). 윈도우별 독립.
- ✅ `MultiAccountAnalyzer` 동일 사용.
- ❌ `WithdrawalAnalyzer` — 옛 단일종목(`_get_return_stats` tickers[0]) + `_simulate_synthetic_case`(단일자산 GBM). + 단일 합성경로 롤링.
- ❌ `dividend_simulator._simulate_synthetic` — 단일종목 GBM(`div_stats` 1종목).

## 사용처 매핑

| 탭/경로 | 분석기 | MVN MC | 작업 |
|---|---|---|---|
| 계산기 단일 | AccumulationAnalyzer | ✅ | 검증만 |
| 계산기 멀티 | MultiAccountAnalyzer | ✅ | 검증만 |
| 은퇴 축적 | AccumulationAnalyzer | ✅ | 검증만 |
| **은퇴 인출(단일)** | WithdrawalAnalyzer | ❌ | **이식(핵심)** |
| 은퇴 인출(멀티) | multi_account_withdrawal | ⚠️ | 확인 |
| **배당금** | dividend_simulator | ❌ | **이식** |
| 백테스트 | TaxableRunner+롤링 | ⚠️ | 확인 |

## 작업 (단계)

### P1. 은퇴 인출 — WithdrawalAnalyzer MVN 이식 (핵심)
- `_run_rolling`에서 실 독립 데이터 < 인출기간이면 **per-window MVN 합성** 생성 경로 추가.
  AccumulationAnalyzer 패턴(`_joint_stats` 캐시 + `generate_joint_window` 윈도우별, 폴백 독립 GBM) 미러.
- 각 합성 윈도우 = 인출기간 길이의 독립 경로 → 기존 인출 sim(SimulationLoop/TaxableRunner) 그대로 실행 → metrics(yearly_ratios·배당·고갈) 수집.
- 단일종목 `_simulate_synthetic_case` / `_get_return_stats`(tickers[0]) **제거 또는 폴백 강등**.
- `allow_synthetic` 게이팅 정리: 인출 투영은 horizon>실데이터면 항상 MC(축적과 동일 결).
- ⚠️ 병렬 워커(`_run_wd_case` 전역 `_w_price_data`) 구조 — per-window 합성은 순차 생성 후 워커에 주입하거나, 축적처럼 순차 실행 경로 분리.

### P2. 배당금 — dividend_simulator MVN 이식
- `_simulate_synthetic`/`_run_synthetic_rolling` 단일종목 GBM → estimate_joint_stats + generate_joint_window 기반 다종목 상관 합성으로 교체.
- 배당 통계도 종목별 실 yield 유지(이미 div_stats 있음 — 종목별로 확장).

### P3. 계산기·백테스트 검증
- 계산기: AccumulationAnalyzer가 use_synthetic 시 MVN 쓰는지 prod 실측(이미 ✅로 보임). 단일 합성경로 아님 확인.
- 백테스트: 롤링 분포가 단일 합성경로 슬라이스인지 확인. 그렇다면 P1과 동일 처리.

### P4. 공통 정리
- `MAX_SYNTH_MU_MONTHLY`(drift 상한) 적정성 검토 — forward-looking 보수성.
- MC 표본수: 좋은 p10/p90 위해 충분히(예 300~500). 1vCPU 성능 고려(은퇴 perf 메모 참조).

## 검증 (각 단계)
- prod ssh 동기 probe(`ssh -i ~/.ssh/hetzner_ed25519 root@178.105.84.213`)로 분포 현실성 확인:
  실패율 존재·p10~p90 폭넓음·극단 인출 시 전건 고갈.
- 결정론 타겟 테스트(`tests/test_g5_retirement_*`, dividend 테스트) PASS.
- 골든 케이스: SCHD50/QQQ20/GLD30, 5억, 월300만, 30년 → 고갈률 ~30-40%대·p50 한 자릿수 억대 기대.
- 로컬은 실 백필이 깊어 MC 미발현 가능 → **prod 검증 필수**.

## 리스크
- 큰 엔진 변경 → 단계별 커밋·prod 검증. 한 번에 안 함.
- 성능: MVN 다종목 × 수백 경로 × 인출 sim = 무거울 수 있음. 워커/표본수 튜닝.
- 결과 수치 전면 변동(실패율 생기고 중앙값 하락) — 의도된 현실화. UI 문구(가상데이터 경고) 유지.
