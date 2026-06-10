# Track G — 다중 계좌 시뮬레이션 엔진 상세 구현 계획

작성일: 2026-05-30 (v2 — 단일 엔진 구조 + 사용자 분배 정책으로 개정)
소유 로드맵: `PROJECT_MASTER_ROADMAP.md` → Track G / `PHASE4_PLAN.md § 4G`
선행 조건: Track F (ISA/계좌 규제 정합성) — ✅ 완료 (2026-05-30)

---

## Context

현실의 투자자는 ISA + 위탁 + 연금저축/IRP를 동시에 운용한다. 현재 시뮬레이터는 계좌 1개만 선택 가능해 비현실적이다. ISA는 연 2,000만 / 총 1억 납입 한도가 있어 한도를 넘는 자금은 반드시 다른 계좌로 흘러가야 하는데 현재는 이를 표현할 수 없다. ISA 풍차돌리기(3년 만기 → 재가입)도 만기 수령액이 한도를 초과하므로 다중 계좌 구조 없이는 제대로 구현 불가하다.

현재 `_run_isa_renewal_cycle`(`modules/retirement/accumulation_analyzer.py:223`)은 만기 수령액 **전체**를 다음 사이클 초기자본으로 재투자하는 비현실적 동작을 한다. 실제로는 2,000만만 새 ISA로 들어가고 나머지는 연금 이전 또는 위탁으로 가야 한다.

목표: 여러 계좌를 동시에 시뮬레이션하고, 계좌 간 자금 흐름을 **사용자가 정의한 분배 정책**대로 현실적으로 처리하는 엔진을 만든다.

---

## 확정된 설계 결정

### 결정 1 — 엔진은 하나. 단계는 기능 플래그.

G1/G2/G3는 **서로 다른 엔진이 아니다.** "모든 계좌의 포트폴리오를 동시에 들고 시간축을 따라 도는 통합 루프" **하나**를 만들고, 단계별로 기능을 켠다.

```
통합 다중 계좌 시간 루프 (단일 엔진)
  ├─ G1: 자금이동 OFF  → 계좌 N개 병렬 운용 + 시나리오별 합산
  ├─ G2: 자금이동 ON   → 분배 정책에 따라 계좌 간 이동 처리
  └─ G3: 이동 종류에 "연금 이전(세액공제)" 추가
```

G1에서 만든 루프를 G2/G3가 그대로 쓴다. **버리는 코드 없음.** "G1 먼저"의 이유는 별도 엔진이라서가 아니라, 위험한 부분(계좌 간 결합)을 끄고 토대(루프 정확성 + UI + 합산)부터 검증하기 위함이다.

> 단일 계좌 시뮬을 N번 따로 돌려 합산하는 방식은 채택하지 않는다. 그렇게 하면 G2에서 통째로 버려야 하기 때문이다. 처음부터 통합 루프로 간다.

### 결정 2 — 입력은 계좌별 독립 수동 입력.

현재 `taxAccounts`의 "단일 총액을 %로 분할" 모델(`static/js/calculator.js:874~`)을 폐기. 계좌마다 **초기자본 / 월적립금 / 종목 + 비중 / 계좌유형**을 독립 입력. 계좌별 투자 가능 종목이 규제로 다르기 때문(ISA는 US_DIRECT 불가 등).

### 결정 3 — 자금 흐름 = 사용자 설정 분배 정책 (고정 프리셋 아님).

ISA 한도 초과분·만기 목돈을 **어디로 얼마나 어떤 순서로** 보낼지 사용자가 직접 정의한다. 고정된 전략 A/B/C 프리셋을 두지 않는다. 월 납입 초과분과 만기 목돈은 **같은 분배 정책 메커니즘**으로 처리한다(아래 G2 참조). 이게 프리셋 3개보다 단순하면서 유연하다.

### 결정 4 — UI는 투자계산기 / 백테스트 / 은퇴 3개 탭에 적용. (배당금 제외)

세금 설정 영역의 "계좌 추가" 버튼으로 계좌를 늘리면 각 계좌마다 초기자본·월적립금·종목 입력란이 펼쳐진다. 계좌 1개일 때는 기존과 거의 같게 보이고, 추가 시 점진적으로 확장.

> **배당금 계산기는 Track G 범위에서 제외 — 단일 계좌 유지.** 배당금 계산기는 `DividendSimulator` 자체 루프를 쓰며 `TaxableSimulationRunner`/`SimulationLoop`을 공유하지 않는다(세금 엔진만 Phase 2c에서 공유). 통합 엔진(`MultiAccountSimulationLoop`)을 못 쓰므로 다중 계좌를 적용하려면 별도 중복 구현 또는 풀 통합 리팩토링이 필요한데, 후자는 역산 루프 속도 위험으로 보류 결정됨(`divrefactoring.md`). 배당금 계산기의 다중 계좌는 우선순위가 낮아 Track G에서 다루지 않는다.

### 결정 5 — G1 세부 (2026-05-30 확정)

- **5A 합산 지표 범위:** 종료값 분포 + 합산 위험지표(CAGR/MDD). `MultiAccountSimulationLoop`이 매일 합산 총액을 기록 → 윈도우별 합산 경로 → `_calc_metrics` 재사용. 계좌별 지표도 별도 보관.
- **5B 공유 윈도우 시작일:** 전 계좌·전 종목 데이터 시작일 중 **max**. 모든 계좌가 같은 기간을 커버해야 시나리오별 합산이 성립. 짧은 종목은 백필/합성 opt-in으로 연장(기존과 동일).
- **5C 단일계좌 회귀 기준:** 계좌 1개를 `MultiAccountLoop`로 돌린 결과가 기존 `TaxableSimulationRunner` 경로와 **종료값 ±1원, CAGR/MDD ±0.01%** 일치(골든 테스트 앵커).

### 결정 6 — 테스트 가능성 설계 제약 (필수)

검증 가능하게 만들기 위해 엔진은 결정론적 데이터 주입을 받아야 한다.
- `MultiAccountSimulationLoop`: `price_data` dict 주입 (기존 `TaxableSimulationRunner`와 동일하게 이미 가능).
- `MultiAccountAnalyzer`: **주입 가능한 price provider** 또는 윈도우별 사전계산 데이터를 받을 수 있게 설계. 이게 없으면 롤링 계층 정확값 테스트(L1/L5) 불가.

---

## 공통 개념: 분배 정책 (Distribution Policy)

계좌 간 자금이 넘칠 때(월 납입 초과 or 만기 목돈) "어디로 얼마나"를 정하는 **순서가 있는 규칙 목록**. 사용자가 정의. 한 가지 메커니즘으로 두 상황(월 초과·만기)을 모두 처리한다.

정책 = 우선순위 순 목적지 목록. 각 목적지는 `(대상 계좌, 상한)`:

```
예시 정책:
  1순위: 새 ISA      상한 = min(잔액, 2,000만)
  2순위: 연금 이전   상한 = 연금 잔여 연한도 (세액공제 별도 계산)
  3순위: 위탁         상한 = 무제한 (나머지 전부)
```

엔진은 자금을 1순위부터 상한까지 채우고, 넘으면 다음 순위로 캐스케이드. 마지막은 보통 위탁(무제한). 사용자가 순서·상한을 조정.

이 정책 하나로:
- **월 납입 초과** (ISA 연 2,000만 / 총 1억 도달 시 그 달 납입금) → 정책대로 분배
- **만기 목돈** (풍차돌리기 3년차 출금액) → 정책대로 분배

---

## G1 — 다중 계좌 통합 루프 (자금이동 OFF) + UI

### 핵심 원칙: 퍼센타일 단순 덧셈 금지

```
[틀림]  계좌A p10 + 계좌B p10 = 합산 p10   (같은 최악 시나리오가 아님)
[옳음]  시나리오 i마다 combined_i = Σ 계좌_i  →  combined 분포에서 p10/p50/p90
```

계좌 간 종목이 다르면 시나리오별 상관관계가 낮아져 단순 덧셈은 p10을 왜곡. 반드시 **동일 롤링 윈도우 공유** → 시나리오 단위 합산 → 분포.

### 구조 (2계층)

**신규 파일 1 — `modules/simulation/multi_account_loop.py`**
`MultiAccountSimulationLoop`: 한 시나리오(시작일 1개 → 종료) 동안 **N개 계좌 포트폴리오를 동시에** 들고 일자별로 순회.
- 매 시점 각 계좌: 배당 → 적립 → 리밸런싱 (기존 `DividendEngine`/`ContributionEngine`/`OrderExecutor` 등 컴포넌트 그대로 재사용, 오케스트레이션만 N개로 확장)
- `transfers_enabled=False`(G1): 계좌 간 이동 단계 생략 → 사실상 N개 독립 운용
- `transfers_enabled=True`(G2): 매 시점/연/만기 트리거에서 분배 정책 적용
- 세금: 계좌별 `account_type`에 맞는 엔진(`TaxedDividendEngine`/`TaxedOrderExecutor`/`TaxTrackedPortfolio`) 사용. 기존 `TaxableSimulationRunner` 조립 로직 참고.

**신규 파일 2 — `modules/retirement/multi_account_analyzer.py`**
`MultiAccountAnalyzer`: 롤링 래퍼. 윈도우 순회를 직접 주도.
- **공유 시작일** = 모든 계좌·모든 종목 데이터 시작일 중 max.
- 윈도우 한 번 순회. 각 윈도우마다 `MultiAccountSimulationLoop` 1회 실행 → 계좌별 종료값 + `combined_i = Σ`.
- 전 윈도우 `combined_i` 배열 → 분포. 계좌별 분포도 별도 보관.

### 재사용 대상
- 컴포넌트 엔진들(`modules/simulation/*_engine.py`, `order_executor.py`) — 그대로.
- `TaxableSimulationRunner`의 계좌별 엔진 조립 패턴(`taxable_runner.py:46~62`) — 참고/추출.
- `contribution_end_months` (BUG-4) — ISA 1억 캡 계좌별 독립 적용.
- `validate_account_portfolio` / `validate_isa_contribution` / `check_contribution_limits` (`account_tax.py`) — 계좌별 + 합산 검증.

### 결과 데이터 구조 (제안)
```
{
  "combined": { "p10":…, "p50":…, "p90":…, "mean":…, "values":[…] },
  "accounts": [ { "account_id":0, "type":"ISA", "distribution":{…}, "cases":[…] }, … ],
  "contribution_warnings": […],
  "cases_count": N,
}
```

### G1 입력 스키마 (백엔드 body)
```
{
  "accounts": [
    { "type":"ISA",  "initial_capital":…, "monthly_contribution":…,
      "tickers":[{code,weight},…], "rebal_mode":…, "isa_renewal":false },
    { "type":"위탁", "initial_capital":…, "monthly_contribution":…, "tickers":[…], "rebal_mode":… }
  ],
  "years":…, "dividend_mode":…, "tax_enabled":true, "user_settings":{…},
  "distribution_policy": null   // G1은 미사용. G2에서 채움.
}
```

### G1 범위
1. 계좌 목록 입력 UI (추가/제거, 계좌별 초기금·월납입·종목·비중·유형)
2. `MultiAccountSimulationLoop` (transfers OFF) + `MultiAccountAnalyzer`
3. 계좌별 종목·납입 검증 (Track F 재사용)
4. 결과 화면: 계좌별 + 합산 분포 동시 표시
5. **회귀:** 계좌 1개 = 기존 단일 계좌 결과와 ±1원 일치

**난이도:** 높음 (2~3주).

---

## G2 — 자금이동 ON (분배 정책 적용)

> 같은 `MultiAccountSimulationLoop`에 `transfers_enabled=True`. 새 엔진 아님.
> G1과 다른 점: 계좌가 자금 이동으로 결합되므로 독립 합산이 불가 — 통합 루프가 필수인 이유가 여기서 실현됨(G1에서 이미 통합 루프로 지어놨으므로 추가 작업은 "이동 트리거 + 분배 정책 적용"뿐).

### 2-1. ISA 한도 초과분 라우팅
ISA가 연 2,000만 또는 총 1억 도달 → 그 달 ISA로 갈 납입금을 **분배 정책**대로 처리.
- 위탁 목적지 → 무제한 흡수.
- 연금/IRP 목적지 → 연 한도(연금+IRP 합산 1,800만) 확인. 초과분은 정책 다음 순위(보통 위탁)로 캐스케이드.
- 연금/IRP 합산 한도는 `check_contribution_limits` 로직 재사용.

### 2-2. 풍차돌리기 만기 목돈 분배
ISA 3년 만기 → 전체 출금(세후) → 목돈 발생 → **분배 정책**대로:
- 사용자가 "새 ISA 얼마(상한 2,000만), 연금 이전 얼마, 위탁 얼마"를 정책으로 지정.
- 엔진은 정책 순서·상한대로 목돈을 배분하고 다음 사이클 진행.
- 연금 이전분은 세액공제 발생(→ G3에서 정밀 계산).

### 2-3. 트리거 종류
- **매달:** 월 납입 초과 체크 (2-1)
- **매년:** 연 한도 리셋, 연금/IRP 연납입 정산
- **3년마다(ISA 만기):** 목돈 분배 (2-2)

각 이동은 매도(위탁이면 양도세 이벤트) → 수신 계좌 매수로 처리. 기존 `OrderExecutor`/`TaxedOrderExecutor` 재사용.

### 2-4. 금융소득종합과세자 ISA 처리 — 가입불가 → 풍차 중단·무한유지 (오너 결정 2026-05-31)

**규칙(한국 실제):** 직전 3개 과세기간 중 1회라도 금융소득종합과세 대상자였으면 ISA **신규가입·만기연장**
불가. 단 **기존 보유 ISA는 강제해지 아님** — 만기까지(사실상 무기한) 유지 가능.

**오너 통찰 — 풍차돌리기의 진실:** 3년마다 "재가입"하는 건 만기가 3년이라서가 아니라 **의무가입기간이
3년**이라서다. 만기일을 사실상 무한(9999)으로 두고 1억 한도를 채우면 **영원히 운용 가능.** 금종세 대상자가
되면 신규/연장이 막힐 뿐, 기존 ISA는:
- 1억 한도 채우고 **추가납입 중단** → 그 달부터 ISA로 갈 납입금은 분배 정책(2-1)대로 리라우팅.
- **해지하지 않고 죽을 때까지 유지.** 비과세한도 리셋(풍차 이득)은 못 받지만 계속 굴림.
- 나중에 해지 시: 전액 연금이전 가능 / 그냥 해지해도 9.9% 분리과세 / 가입 당시 서민형이면 400만 비과세 한도 유지.

**구현해야 하는 핵심 = 단 하나:**
> ISA 풍차돌리기 선택된 다중계좌 시뮬에서, **금융소득종합과세 대상자가 되는 순간부터 3년 사이클 해지·재가입을
> 멈추고 기존 ISA를 무한유지**(만기 ∞, 한도 차면 추가납입 0 → 리라우팅)하도록 `_run_isa_renewal_cycle`/
> 통합 루프 분기. 해지·재가입(풍차)은 비대상 기간에만.

**입력:** Phase 2f의 **연도별 종합과세 대상 트래킹**(`comprehensive_years`) + 수동 오버라이드
(`manual_comprehensive_years`, 오너 결정 2026-06-01: 자동+수동 둘 다). 계좌간 금융소득 집계 =
위탁 배당 + KR_FOREIGN 실현차익(ISA/연금 제외) → **개인** 단위 연도별 2천만 초과 판정
(금종세는 법적으로 개인 과세 — 시뮬 내 전 위탁계좌 합산. 구 "가구 단위" 표현 정정).

**동작:**
- 매년: 직전 3년 중 1회라도 대상 → `isa_eligible=False`. ISA 신규가입/풍차 재가입 차단, 기존 ISA 무한유지.
- 3년 **연속 비대상** → `isa_eligible=True` 복귀 → 풍차 재개 허용(동적 토글).
- 한도 초과·중단된 납입금 → 분배 정책: **연금 한도 우선 → 위탁**(오너 결정 Q4).

**상태:** ❌ 미구현. 계좌간 금융소득 집계·종합과세 트래킹·풍차 중단 전부 신규. G2 분배 정책과 함께 구현.

> **순서 (오너 합의 2026-05-31): Phase 2f 먼저 완료 → 그 다음 이 G2/2-4.** 2-4는 2f의 "연도별 종합과세 대상
> 트래킹"을 입력으로 먹으므로 2f 선행 강제. 또한 리라우팅/cascade는 `multi_account_loop` `transfers_enabled`가
> 현재 `NotImplementedError` — **G2 transfer 엔진 신규 구축이 선행**(ISA 1억 자동중단·연금 1800만 cascade 포함
> 전부 미구현, `check_contribution_limits`는 정적 검증만).

**의존성:** G1 완료 + **Phase 2f(종합과세 트래킹) 완료** + G2 transfer 엔진. **난이도:** 매우 높음 (1~2주).

---

## G3 — ISA → 연금 이전 제도 (핵심, 옵션 아님)

> 사용자 정정(2026-05-30): 연금계좌 이전 제도가 풍차돌리기 목돈 처리의 **핵심 경로**. 기존 v1 계획의 "전략 C(위탁 임시운용 + 매달 매도 + 연단위 재충전)"는 이 제도로 대체되어 **불필요 → 폐기**.

ISA 만기 자금을 연금계좌로 직접 이전하면 이전액의 10%(최대 300만) 추가 세액공제. G2의 분배 정책에서 "연금 이전" 목적지를 선택하면 발동.

구현 범위:
1. 분배 정책 "연금 이전" 목적지 활성화
2. 이전액 10% 세액공제 계산 (연 300만 상한, 연금 연 한도 확인)
3. 세액공제 환급금 재투자 옵션 연동 (`taxDeductionReinvest` 기존 체크박스 참고)

**의존성:** G2 분배 정책 골격. **실질적으로 G2와 함께 구현됨** (별도 단계라기보다 분배 목적지의 한 종류).

**상태:** ✅ 완료(업데이트18, L6). `_accrue_pension_credit` min(전환액×10%, 연300만). 재투자는 G4로 통합.

---

## G4 — 연 납입 세액공제 (연금/IRP 매년 납입 환급) — 신규 (2026-06-01 설계)

G3(ISA→연금 *전환* 10%/300만)와 **별개.** 매년 연금/IRP에 *납입*하면 세액공제 환급:
환급액 = `min(합산납입, 공제한도) × 공제율`. 계산식 = `TaxEngine.annual_tax_deduction`(이미 구현·tax_truth 8케이스 검증).
- 공제한도: 연금저축 단독 600만 / 연금+IRP 합산 900만.
- 공제율: 총급여 5,500만↓ 16.5% / 초과 13.2% (종합소득자 4,500만 기준).

### 확정 설계 (오너 결정 2026-06-01)
- **별도 한도:** G3 전환공제(300만)와 연납입공제(900만)는 독립. 같은 해 둘 다 가능(최대 1200만 공제).
- **공제 base = external 연금/IRP 납입만** — 직접 월납입 + 2-1 ISA초과 라우팅분(둘 다 external).
  **ISA 만기 전환분(internal)은 제외**(그건 G3 10% 대상, 이중공제 방지).
- **900/600만 한도 = 연금+IRP 계좌 간 공유** — 연도별 external 납입을 연금·IRP 분리 집계.
- **환급금 재투자 = 분배 정책(`DistributionPolicy`) cascade 그대로** (오너: 별도 목적지 안 만들고
  이미 정한 우선순위 따라감). `route_overflow`(정상 한도, pension_unlimited=False — 납입이라 한도 소비).
  토글 1개(`reinvest_tax_credit`, run 레벨) — G3 전환공제 환급 + 연납입공제 환급 **통합 제어**.
- **재투자 타이밍:** 연납입공제 = 직전 해 전체 납입 알아야 계산 → **다음 해 연경계서 재투입**(현실:
  익년 정산). 마지막 해분은 보고만(이후 연도 없음). G3 전환공제 = 만기월 즉시(기존).
- **세금 OFF면 미적용**(세금 기능).

### 폐기된 v1 — `modules/tax/multi_account.py`
연납입공제가 배선돼 있던 `MultiAccountSimulator`(계좌 독립시뮬 후 합산)는 §결정1이 폐기한 v1.
호출처 0개 = 죽은 코드 → **삭제**(2026-06-01). 계산식(`annual_tax_deduction`)·재투자 파라미터
패턴만 통합 루프(`multi_account_loop.py`)로 이식.

---

## B — 배선 & UI 단계 (G2 엔진 → 화면) — 2026-06-01 설계

엔진 계층(L0~L8)은 완료됐으나 `MultiAccountAnalyzer`/`*_logic.py`가 G2 기능
(풍차·정책·금종세·재투자)을 **하나도 안 넘기고 있음** — 현재 logic은 transfers OFF(G1)만 작동.
배선을 3단계로 나누고, 검증 강한 것(B1·B2)부터 한다. **투자계산기 탭 먼저 완성→은퇴/백테스트 복제**(§G1 탭 순서 동일).

### 현재 배선 갭 (2026-06-01 코드 확인)
- `multi_account_analyzer.py`: 루프 호출에 `isa_renewal`(계좌별)·`manual_comprehensive_years`·
  `reinvest_tax_credit` 미전달. 결과(`transfer_log`/`comprehensive_years`/`financial_income_by_year`/
  `annual_deduction_credit`/`pension_transfer_credit_total`) 윈도우 위로 미surfacing. `__init__` 신규 파라미터 없음.
- `calculator_logic.py`: `_normalize_multi_accounts`가 `isa_renewal` 미독해. body→`DistributionPolicy`
  미구성. `transfers_enabled`/신규 파라미터 미전달. 신규 결과필드 API 응답 미적재.

### B1 — 백엔드 배선 (analyzer + calculator_logic 관통) **[검증 강함]**
**범위:**
- `MultiAccountAnalyzer.__init__`에 `manual_comprehensive_years`·`reinvest_tax_credit` 추가, `.run()` 호출에
  전달. `loop_accounts`에 계좌별 `isa_renewal` 포함.
- 결과 surfacing: 대표 윈도우(또는 case별) `transfer_log`·`comprehensive_years`·`annual_deduction_credit`·
  `pension_transfer_credit_total`을 분석 결과 dict로 올림.
- `_normalize_multi_accounts`: `isa_renewal` 독해. `_run_multi_account_calculator_logic`: body의
  `distribution_policy`(→`DistributionPolicy.from_dict`)·`manual_comprehensive_years`·`reinvest_tax_credit`
  파싱→analyzer 전달. `transfers_enabled` = (정책 有 or 임의 계좌 isa_renewal). 신규 결과필드 응답 적재.

**검증 — L9 (logic 관통, 결정론):** 결정6(analyzer `price_provider` 주입) 활용. 4종:
1. **정상경로 관통:** body(accounts+policy+isa_renewal+manual+reinvest)→`_run_multi_account_calculator_logic`
   결과 dict에 만기이동·환급·종합과세연도가 **엔진 손계산값(L5/L6/L8/L5c 재현) ±1원**으로 도달.
2. **경계:** ① policy 無 & isa_renewal 無 → G1과 동일(transfers OFF 회귀) ② isa_renewal=false → 만기 0
   ③ manual_comprehensive_years 반영 ④ accounts 1개 → 단일계좌 경로 불변.
3. **세금 ON/OFF:** 양쪽 관통(세금ON시 청산세·만기세·공제 결과 일치).
4. **불변식:** 결과 combined = Σ account end_value, 자금보존(=L계층 헬퍼 재사용 or 동등 어서트).

### B2 — API 응답 surfacing **[검증 강함]**
**범위:** `/api/calculator/submit` 응답에 신규 필드(만기 이동 요약·종합과세 연도·연납입공제 환급·이전공제
환급) 프론트 소비 가능 형태로 포함. (은퇴/백테스트는 복제 단계서.)
**검증:** 서버 submit(결정론 or 실데이터 body, 다계좌+정책+풍차) → HTTP 200 + 응답 JSON에 신규 필드
존재·타입·부호 확인. 회귀: 기존 단일계좌/G1 응답 불변(필드 누락·변경 없음). Hetzner 서버 검증.

### B3 — 프론트 UI **[검증 약함 — 육안 스모크]**
**범위:** ① 분배정책 우선순위 에디터(목적지 순서 지정) ② 계좌별 ISA 풍차(`isa_renewal`) 토글
③ 금종세 수동 연도 입력(`manual_comprehensive_years`) ④ 세액공제 환급 재투자 토글(기존 `taxDeductionReinvest`
재사용) ⑤ 결과 표시(만기 자금이동·연도별 환급·종합과세 대상연도). 계좌 1개=기존과 동일, 추가 시 점진 확장(§5).
**검증:** 브라우저 스모크 — 계좌 2개+정책 입력→submit→결과 렌더 육안. **가능한 부분은 JS 단위 어서트**
(정책 순서가 body에 정확히 직렬화되는지). UI 정확성(드래그·렌더)은 스모크 한계 명시.

### 단계 순서 & 게이트
B1(관통+L9 4종 통과) → B2(API+서버검증) → B3(UI 스모크). 각 단계 검증 통과 전 다음 금지.
투자계산기 탭 B1~B3 완료 → 은퇴·백테스트 복제. **L7(실데이터 통합 불변식)은 B2 후 실데이터로 수행.**

---

## 위험 / 우려사항

1. **퍼센타일 합산 오류는 눈에 안 보인다.** 잘못 구현해도 그럴듯한 숫자. 합산은 시나리오 단위로. "독립 합산 ≠ 퍼센타일 덧셈" 단위 테스트로 명시 검증.

2. **통합 루프를 처음부터 짓는 부담.** G1에서 단일 계좌 재사용+합산이라는 쉬운 길의 유혹이 있으나, 그러면 G2에서 버려야 함. G1부터 통합 루프로 가되, 자금이동만 끈다. (결정 1)

3. **검증 난이도.** 단일 계좌는 손계산 검증 쉬웠으나 다중·이동은 어려움. 단계적 검증: ① 1계좌=기존결과 → ② 2계좌 이동없음=합산 → ③ 월 초과 라우팅 → ④ 만기 분배.

4. **속도.** 계좌 N개 → 윈도우당 비용 N배. 계좌 3~4개 시 응답 시간 주의. `record_history` 최소화, 진행률 콜백 유지.

5. **UI 복잡도 폭발.** 계좌마다 종목검색·비중·초기금·월납입. 계좌 1개=기존과 동일, 추가 시 점진 확장으로 혼란 최소화.

6. **분배 정책 UI 난이도.** "순서 있는 목적지 + 상한" 입력을 사용자가 직관적으로 설정하게 만드는 게 과제. 기본 정책(ISA→연금→위탁) 프리셋을 제공하고 고급 사용자만 커스텀하게.

7. **연금/IRP 합산 한도 계좌 간 의존.** 두 계좌가 1,800만 합산 한도 공유. 라우팅·검증 시 합산 판단 필수(`check_contribution_limits` 재사용).

---

## 파일 변경 지도

| 파일 | 변경 |
|------|------|
| `modules/simulation/multi_account_loop.py` | **신규.** 통합 다중 계좌 시간 루프. transfers 플래그 |
| `modules/retirement/multi_account_analyzer.py` | **신규.** 롤링 래퍼 + 시나리오별 합산 |
| `modules/tax/account_tax.py` | 분배 정책 적용·캐스케이드 헬퍼 추가(한도 상수·검증 재사용) |
| `*_logic.py` (calculator/retirement/backtest) | `accounts` 배열 + `distribution_policy` 입력 분기. 단일 계좌면 기존 경로. **dividend_logic.py 제외** |
| `static/js/*.js` + `templates/*.html` | 계좌별 독립 입력 + 분배 정책 UI. 기존 `taxAccounts` %분할 폐기 |

**건드리지 않음:** `AccumulationAnalyzer` 본체(단일 계좌 경로), `TaxableSimulationRunner`(패턴 참고만).

---

## 테스트 설계 (검증 전략)

세금·자금이동이 포함된 루프는 불변식만으로 검증 불가("장부는 맞는데 금액이 틀린" 버그를 못 잡음). 핵심 전략: **결정론적 가격 주입 + 계층별 손계산값 비교.**

> 현재 repo 테스트는 전부 실데이터(yfinance) + 불변식 검증이다(예: `tests/test_portfolio_accounting.py`). 이는 L0/L7로 유지하되, Track G는 정확값 검증을 위해 **결정론적 픽스처 하네스를 신설**한다. 결정 6(테스트 가능성 제약)이 이를 가능케 한다.

### 픽스처 종류 (전부 손계산 가능)

| 픽스처 | 정의 | 검증 대상 |
|--------|------|----------|
| 평탄가격 | price=100 고정, 배당0 | 기여금 회계, 한도 라우팅 (수익·세금 노이즈 0) |
| 고정성장 | price=100·(1+r)^t | 복리 종료값 폐형식 |
| 단일배당 | 특정일 1회 배당 | 배당세 정확값 |
| 계단가격 | 한 번 점프 | 실현이익 → 양도세/이전세 정확값 |

### 검증 원칙 (엄밀성 규약 — 2026-05-31 오너 지시)

**모든 기능에 대응하는 L계층이 반드시 존재해야 한다.** 검증 계획 없는 기능(2-4 같은 누락) 금지.
각 L계층은 아래 4종을 **모두** 만족해야 "완전 검증"으로 인정:
1. **정상경로 손계산** — 결정론 픽스처로 정확값 어서트(±1원).
2. **경계/엣지** — 한도 정확 도달, 0 입력, 정책 미흡수(leftover), cap 적중 등.
3. **세금 ON/OFF 양쪽** — 세금 켠 조합도 별도 케이스(라우팅·분배+청산세 동시).
4. **공통 불변식** — 자금보존·음수잔액0·한도위반0을 매 케이스 어서트(헬퍼 `assert_invariants`로 공통화).

### 계층별 테스트 (각 계층 = 위 4종 충족)

| 계층 | 기능 | 정상경로 손계산 | 경계/엣지 | 세금 ON |
|------|------|------|------|------|
| **L0 회귀** | 1계좌=Runner | 종료값±1원/CAGR·MDD±0.01% (골든) | 월적립有/無 양쪽 | 세금ON 골든도 일치 |
| **L1 합산** | 2계좌 합산 | `combined_i==A_i+B_i` | 퍼센타일(합산)≠퍼센타일덧셈 증명 | — (세금OFF 전용) |
| **L2 기여금** | 평탄 적립 | `종료값==초기+Σ월납입` | ISA stop_months 정확(예 190개월=1억) | n/a |
| **L3 세금단위** | 배당/양도/청산세 | 배당세·양도세·ISA청산세 손계산 | 비과세한도 경계, 서민형/일반형 | (본질이 세금ON) |
| **L4 한도라우팅 (2-1)** | 월 초과분 cascade | ISA 연2천만 흡수→연금1800만→위탁 | ①연한도리셋 ②총1억캡 ③자동싱크 ④**정책cap 적중** ⑤**leftover>0**(위탁 미포함 정책) ⑥**연금+IRP 동시 1800만 풀공유** | **L4-tax: 라우팅+청산세 동시**(위탁 수신분 KR_FOREIGN 22%·국내 15.4% 정확) |
| **L5 만기분배 (2-2)** | 3년 만기 목돈 | 목돈 정책대로 새ISA/연금/위탁 배분, 잔액 정확 | 만기액<2천만(전액 ISA), >1억(총한도) | **L5-tax: ISA 청산세 후 목돈으로 분배** |
| **L5b 다중사이클 풍차 (2-2)** | 9년 3사이클 | 매 만기 ①2천만 재가입 ②비과세리셋 ③나머지 분배 ④3사이클 누적 정확 | 마지막 사이클 remainder(3배수 아님) | **L5b-tax: 사이클별 청산세 누적** |
| **L5c 금종세 ISA중단 (2-4)** | 풍차중단·무한유지 | `comprehensive_years` 주입→대상연도부터 풍차 정지·기존ISA 유지(만기∞), 한도참시 추가납입0→2-1 리라우팅 | ①3년연속 비대상→풍차재개(동적토글) ②대상↔비대상 전환경계 ③개인 과세단위 2천만 판정 | **L5c-tax: 위탁배당+KR_FOREIGN실현 합산이 2천만 판정 입력과 일치**(공유세션 멀티배선 검증) |
| **L6 연금이전공제 (G3)** | ISA→연금 이전 | 공제=min(X·0.1,300만), 연금연한도 내 | 이전액 연한도 초과분 처리 | **L6-tax: 공제 환급금 재투자** |
| **L8 연납입공제 (G4)** | 연금/IRP 매년 납입 | 연금600+IRP300·저소득→900만×16.5%=148.5만 | 연금단독 800만(600만만)·합산>900만·0납입·고소득13.2% | **L8-tax: 환급금 정책 cascade 재투입(ON/OFF), G3공제와 별도한도 합산** |
| **L9 logic 관통 (B1)** | body→logic→analyzer→engine | 결과 dict의 만기·환급·종합과세연도 = 엔진 손계산(L5/L6/L8/L5c) ±1원 | policy無&renewal無→G1동일·renewal=false→만기0·manual반영·1계좌 불변 | **세금ON/OFF 양쪽 관통**(청산세·만기세·공제 결과 일치) |
| **L7 통합** | 실데이터 다계좌 이동ON | (손계산 불가) | — | **불변식만**: 자금보존·음수0·ISA≤1억·연금+IRP≤1800만 |

### 전 계층 공통 불변식 (매 케이스 어서트 — `assert_invariants` 헬퍼)
- **자금 보존:** Σ계좌종료값 = Σ투입 + Σ수익 − Σ세금 (transfer는 내부이동이므로 보존 유지)
- 음수 잔액 없음 / 한도 위반 없음 (ISA ≤ 총 1억, 연금+IRP 연 ≤ 1800만)

### 검증 순서 (구현과 맞물림)
L0 → L1 → L2 → L3 (G1) → L4(+tax) → L5 → L5b → L5c (G2) → L6 (G3) → L8 (G4) → **L9 (B1 배선)** → L7 (통합).
각 계층 4종 전부 통과 전 다음 단계 금지. L0~L3=G1 합격, L4~L5c=G2, L6=G3, L8=G4, **L9=B1 배선**, L7=최종(B2 후 실데이터).

### 진행 상태 (2026-06-01 갱신)
- ✅ **L0~L4 완료**(업데이트17): `assert_invariants` 헬퍼 신설, L4 구멍 4개 메꿈(정책cap·leftover·연금IRP합산·L4-tax).
- ✅ **L5/L5b 완료(2-2 만기분배, 업데이트18):** 풍차 만기 청산→세후 목돈→정책 재배분. 외부/내부 자금분리, 사이클 원가추적. 정상경로·경계(<2천만/>1억)·세금ON·다중사이클·remainder 검증.
- ✅ **L6 완료(G3 연금이전공제, 업데이트18):** ISA→연금 이전 `min(10%,300만)` 공제+재투자옵션. 만기 전환은 1800만 한도 별도(`pension_unlimited`).
- ✅ **L5c 완료(2-4 금종세 풍차중단, 업데이트19):** 공유세션 멀티배선(전 위탁계좌 금융소득 개인합산)+`manual_comprehensive_years` 오버라이드. 직전3년 롤링 재평가로 대상연도엔 만기 스킵(무한유지)·비대상 복귀시 풍차재개. 정상(중단→재개)·무한유지·1억리라우팅·세금ON 라이브배당판정 검증.
- ✅ **L8 완료(G4 연납입 세액공제, 업데이트20):** `annual_tax_deduction` 통합루프 배선. 연금/IRP external 납입 연도별 집계→연경계 정산. 재투자=정책 cascade 통합토글(G3+G4). 정상·연금단독cap·고소득·합산cap·0납입·재투자 검증.
- ✅ **B1 완료(배선, 업데이트21):** analyzer/calculator_logic이 isa_renewal·distribution_policy·manual_comprehensive_years·reinvest 수신→엔진 전달, 결과(transfer_log·comprehensive_years·환급) surfacing. 풍차 거부 제거, transfers ON시 정적 ISA cap 스킵. L9 4종(만기 surfacing·G4공제+금종세·G1회귀·정규화).
- ✅ **연금/IRP 월납입 합산한도(1800만) 초과 라우팅(업데이트26):** 기존엔 연금/IRP 월납입이 합산 1800만 풀 초과 시 초과분을 **드롭**(ISA는 라우팅하는데 연금만 누락)했음. 수정: ISA처럼 `overflow_total`에 합산→정책 cascade 라우팅. 검증 `test_l4_pension_combined_overflow_routes`(연금100+IRP100/월→공유풀 m0~m8 1800만, m9~m11 600만 위탁 라우팅, 자금보존). 첫해 한도=1800만−초기자본은 tracker가 이미 처리(초기 record).
  - ✅ **초기자본 > 연한도 = 에러로 통일(업데이트27, 오너 결정):** 초기자본은 라우팅 아니라 실제 입금이므로 한도 초과 불가(라우팅하면 입금된 느낌 줌). `_validate_initial_capital_limits`(calculator_logic) — ISA 각 ≤2천만, **연금저축+IRP 합산 ≤1800만(공유)**. transfers 무관 항상 하드체크. 프론트 `initial_capital_limit` 에러배너. 검증 `test_l2_initial_capital_limit_validation`. (이전 ISA-G1만 에러/ISA-G2 앉음/연금 무검증 비일관 해소.) **월 초과분은 라우팅(다른 규칙), 초기자본은 에러 — 구분.**
- ✅ **B1 후속(업데이트22): 순수 연금/IRP 공제 정리.** `transfers_enabled`에 `(세금ON & 연금/IRP 존재)` 추가 → 정책 없는 순수 연금/IRP도 연납입공제 산출. 한도 내 연금/IRP는 transfers ON/OFF 종료값 동일(등가성 테스트로 증명)이라 안전. ISA 공존 시 ISA도 transfers 경로(연한도 엔진 동적처리, 한도 내 무차이·더 정확).
- ❌ **B2 API surfacing** + **B3 프론트 UI**(풀커스텀 분배정책 에디터·풍차토글·금종세입력·재투자토글) — 다음.

### 성능
계좌 3개 × 20년 롤링 응답 시간 측정(허용 기준 사전 합의). `record_history` 최소화, 진행률 콜백 유지.

---

## 구현 순서

```
G1 (통합 루프 transfers OFF + 합산 + UI + 회귀)
  → G2 (transfers ON + 분배 정책: 월 초과 라우팅 + 만기 분배)
      └─ G3 (연금 이전 목적지 + 세액공제) — G2와 함께 구현
```

G2는 G1 완성 후 **실제 코드 기준으로 분배 정책·트리거 설계를 한 번 더 정밀화**하고 착수(현재 계획은 "무엇"까지, "어떻게"의 시점별 디테일은 G1 이후 보강).

### G1 탭 적용 순서 (한 탭 완성 → 검증 → 확장)

결정 4는 최종적으로 3개 탭(투자계산기/백테스트/은퇴, 배당금 제외) 적용이지만, G1 구현은 **투자계산기 1개 탭을 먼저 완성하고 L0~L3 검증을 통과시킨 뒤 나머지 탭으로 복제**한다. 이유:
- 엔진(`MultiAccountSimulationLoop`/`MultiAccountAnalyzer`)·결과 스키마·UI 패턴을 한 탭에서 확정하면 나머지는 복제·연결 작업.
- 검증된 토대 위에서 확장 → 여러 탭에 동시에 같은 버그가 퍼지는 위험 제거.

순서: 투자계산기 엔진+UI+검증 통과 → (재사용 가능한 공통 모듈 추출) → 은퇴 → 백테스트.

---

## G1 후속 보완 (2026-05-30 브라우저 실검증 피드백)

투자계산기 다중계좌 G1이 실데이터로 정상 작동 확인됨. 발견된 보완 항목(중요도 순):

### 1. [버그] 배당 지표 0 — ⚠️ 다중계좌 문제 아님으로 정정 (2026-05-30 진단)
**증상:** TIGER 미국배당다우존스(458730) 배당 지표 전부 0, SCHD 0 다수. 단일계좌에서도 발생.
**정정된 근본 원인 (`debug_dividend.py` 실측):** 다중계좌 합산 문제가 아님. 데이터 레이어 + 롤링 윈도우 집계 문제. 가격은 프록시 체인 백필로 1928년까지 존재하나 실측 배당(`corporate_actions`)은 ETF 상장 후만 존재(SCHD 2011~, 458730 2023~). 백필 가격 구간에 배당 row가 없어, `data_start`가 1928로 잡히며 20년 롤링 윈도우 대부분이 배당 이전 시대 → `_fit_distribution`이 0 윈도우 포함 전체 퍼센타일 계산 → p50=0. 어린 ETF일수록 심함.
**조치 (확정 — 범용 재설계):** 모든 백필을 'price-return 가격 + 명시적 배당' 표준으로 통일(total-return 임베딩 폐기). DJUSDIV_PROXY 등 adj-close 체인은 raw-close로 교체해 배당 분리. **Stage A 주식/배당형은 2026-05-30 서버 적용 완료**(SCHD/458730/446720/402970 + UI 실측/추정). Stage B 채권/MMF 후속(필수). 상세 계획: `ETF_BACKFILL_ARCHITECTURE_PLAN.md § Phase 6.0` + Phase 7. 다음은 세금 2c/2e 재검증 후 Track G 재개.

### 2. [UX] 계좌 입력란 커서 사라짐
**증상:** 두 번째 계좌의 월 납입금/초기자산 입력 시 숫자 하나 입력하면 커서가 사라져 다시 클릭해야 함.
**추정 원인:** 입력 `oninput`/`onchange`에서 `renderTaxAccounts()` 전체 재렌더 → DOM 교체로 포커스 유실. (BUG-6 리밸런싱 슬라이더 떨림과 동일 패턴.)
**조치:** 입력 중 전체 재렌더 회피. 값만 상태에 반영하고 DOM 재생성 안 하거나, 재렌더 후 포커스/커서 위치 복원. 우선순위 중.

### 3. [미적] 계좌별 입력 UI 통일성·위계
**증상:** 추가된 계좌 입력 영역이 첫 계좌와 시각적으로 통일되지 않아, 아래쪽 입력이 덜 중요해 보임(실제로는 동등하게 중요).
**조치:** 계좌 카드 디자인 통일, 모든 계좌를 동등한 시각 위계로. 프론트 재설계. 우선순위 낮음(기능 영향 없음, 미관).

> **#2 커서 사라짐 = ✅ 수정 완료 (2026-06-03, BUG-G1-2).** `updateTaxAccountAmount`·`onAccountTickerWeightChange`가 oninput마다 전체 재렌더하던 것 제거(금액→`checkTaxLimits`만, 비중→전용 `acctWeightWarn{idx}` div만). 로컬 수정·미육안검증.

---

## G5 — 백테스트 · 은퇴 탭 복제 (2026-06-03 설계)

투자계산기 탭 B1~B3 완료. 이제 나머지 2개 탭(백테스트·은퇴)에 멀티계좌 적용.
**복제가 균일하지 않음** — 세 탭의 시뮬 성격이 근본 다르기 때문(오너 통찰: "적용이 조금씩 다르다").

### 탭별 성격 차이 (코드 확인 2026-06-03)

| 탭 | logic | 시뮬 성격 | 인출 | 멀티계좌 복제 난이도 |
|---|---|---|---|---|
| 투자계산기 | `calculator_logic._run_multi_account_calculator_logic` | **롤링 몬테카를로**(다수 윈도우→분포) | 없음 | ✅ 완료(레퍼런스) |
| 백테스트 | `backtest_logic.run_backtest_logic` | **단일 역사윈도우**(start→end, `TaxableSimulationRunner` 직접) | 없음(`withdrawal_amount=0`) | 중 |
| 은퇴 적립 | `retirement_logic.run_retirement_logic` | 롤링(calculator와 동일) | 없음 | 하 |
| 은퇴 인출 | `retirement_logic.run_withdrawal_logic` + `WithdrawalAnalyzer` | **롤링 디큐뮬레이션**(생존율 분포) | 있음 + **연금소득세** | 상(신규) |

### 확정 결정 (오너 2026-06-03)

- **Q1 인출단계 세금:** 오너 통찰 — "인출 때는 연금소득세 딱 하나만." **부분 정정 필요(2026-06-03 코드 추적):**
  - 적립 중 위탁 양도세·ISA 청산세·배당세는 계좌별 `TaxedOrderExecutor`/`TaxedDividendEngine`이 처리 ✓.
  - 연금/IRP는 적립 때 과세이연 → 인출 때만 **연금소득세**(3.3~5.5%) 부과 = 신규 세금 ✓.
  - ❌ **BUG-TAX-2 (위탁 인출 양도세 누락) — 기존 단일계좌 버그.** `TaxableSimulationRunner`가 인출에 평범한 `WithdrawalEngine` 사용 → `portfolio.sell()` 직행(`TaxedOrderExecutor` 우회), `TaxTrackedPortfolio`는 `sell` 미오버라이드라 세션에 실현차익 미누적. 최종 `apply_liquidation_tax`는 **남은 보유분만** 과세. **인출하며 판 위탁 매도차익이 양도세·청산세 둘 다 빠져나감 = 비과세.** 인출 비중 큰 은퇴 시뮬에서 과소과세 큼. `_calc_gross_withdrawal` line 503 "위탁/ISA 인출 중 CG세 없음"이 그 잘못된 가정.
  - **수정(필수, 단일+멀티 공유):** 인출 매도를 `TaxedOrderExecutor` 경유로 라우팅 → 실현차익이 세션에 누적되어 위탁 양도세(국내 15.4%/해외 22%·기본공제·종합과세 합산) 정상 부과. ISA 인출은 ISA 청산세 규칙. **기존 은퇴 인출 결과 바뀜**(BUG-TAX-1 전례처럼 정확해지는 방향). G5-C 전에 또는 함께 수정.
- **Q2 인출 순서 = 세금최적 자동.** 과세 적은 계좌부터: **위탁·ISA 먼저 소진 → 연금/IRP 마지막**(연금세·과세이연 최대한 유지). 사용자 지정 순서 UI 안 만듦.
- **Q3 연금소득 1500만 = 16.5% 분리과세 근사.** 개인 연금저축+IRP 인출액 **연 합산** 1500만 초과 시 16.5% 적용(2024 개정 선택제 반영). 1500만 이하는 나이별 3.3~5.5%. (종합과세 누진 정밀은 안 함.) 멀티계좌는 1500만 판정을 **개인 합산**으로(금종세 개인합산과 동형).
- **Q4 구현·검증 순서 = 백테스트 → 은퇴 적립 → 은퇴 인출.** 쉬운 것부터, 각 단계 검증 통과 후 다음.

### G5-A 백테스트 멀티계좌 (단일 역사윈도우)

`run_backtest_logic`은 롤링이 아니라 `TaxableSimulationRunner`로 **단일 윈도우 1회** 실행 → 시계열 차트.
멀티계좌 = `MultiAccountSimulationLoop`을 **1회** 실행(롤링 `MultiAccountAnalyzer`는 부적합/과함).
- 입력: calculator와 동일 `accounts`/`distribution_policy` 스키마 재사용. `_normalize_multi_accounts` 공유.
- 단일 윈도우 드라이버 필요(신규 thin wrapper 또는 루프 직접 호출) — 계좌별 + 합산 **일별 history** surface(차트용).
- transfers: calculator와 동일(정책/풍차/연납입공제). 인출 없음.
- 결과: 합산 경로 + 계좌별 분해(투자계산기 결과 스키마 준용). **표시 디폴트 = 합산+계좌별**(별도 오너 결정 없으면 calculator 따름).
- **검증 L10:** 단일 계좌 백테스트 = 기존 `TaxableSimulationRunner` 결과 ±1원(골든 회귀). 2계좌 합산 = Σ. 세금 ON/OFF. 결정론 픽스처.

### G5-B 은퇴 적립단계 멀티계좌

calculator의 롤링 멀티계좌와 사실상 동일. `run_retirement_logic`(적립부) → `MultiAccountAnalyzer` 재사용.
- 차이: `pension_start_age` 처리(기존), 적립 종료 후 **최종자산을 인출단계로 인계**(계좌별 평가액·취득가 유지).
- **검증 L11:** 단일 계좌 적립 = 기존 경로 ±1원. calculator L0~L9 회귀가 대부분 커버(엔진 공유). 은퇴 특화(pension_start_age) 경계만 추가.

### G5-C 은퇴 인출단계 멀티계좌 (신규 핵심)

> **오너 결정 확정 (2026-06-03, 착수 전 4문):**
> - **취득가 인계 = 스칼라 2개(gross 가치 + 취득가).** 적립30+인출30=60년 연속윈도우는 실데이터 거의 0 →
>   현 11분위 스칼라 샘플링 유지(데이터 타당). 적립 종료 시 gross가치 + **총납입(취득가, 결정론적·시뮬불요)**를
>   인출단계로 인계. 위탁 인출 매도세 = (매도액 − 비례취득가). 종목별 정밀 아닌 계좌 평균취득가 근사이나 위탁
>   과세누락(BUG-TAX-3 잔여) 해소. `sell_with_tax` 경로 재사용. ❌ 포지션 연속인계(60년 윈도우)는 데이터 비현실적이라 기각.
> - **단일+멀티 함께 적용.** 단일 은퇴(`run_retirement_logic`)도 위탁 적립차익 과세누락 잔존 → 공유 경로로 동시 수정.
> - **연금 수령나이 = 은퇴(인출)시작 가정.** pension_start_age ≤ 인출시작 강제/경고 → 위탁/ISA가 연금 수령나이
>   전에 고갈되는 충돌 없음(연금 조기인출 페널티 모델링 안 함).
> - **결과 = 윈도우별 생존율 분포.** RetirementPlanner 구조를 멀티로 확장. combined_summary 동일 형식.
> - **도출 디테일(Claude 디폴트):** 멀티 인출 시작값 = 계좌별 분포의 동일 분위 p값 합(`_build_savings` 동형).
>   가구 인출 오케스트레이터 = 루프 레벨, 매달 위탁→ISA→연금 순 평가액 소진, 같은 유형 다계좌는 인덱스 순.

롤링 디큐뮬레이션 + 계좌별 인출 + 연금소득세. `MultiAccountAnalyzer`는 현재 `withdrawal_amount=0` 하드코딩 →
인출 지원 확장 OR 멀티계좌 인출 분석기. 루프는 `WithdrawalEngine` 배선 보유(확장 지점 명확).
- **인출 순서(세금최적 자동, 오너 결정=가구 단일 인출액):** 사용자는 월 생활비 1개 입력. 신규 **가구 인출 오케스트레이터**(루프 레벨)가 그 금액을 **위탁→ISA→연금/IRP** 순으로 계좌 평가액 소진하며 충당. 현 루프는 계좌별 독립 인출(각 config.withdrawal_amount)이라 가구 단일액 순차분배는 신규.
- **위탁/ISA 인출세(BUG-TAX-2 수정):** 인출 매도를 `TaxedOrderExecutor` 경유로 → 위탁 양도세·ISA 청산세 정상 부과. 단일+멀티 공유 경로에서 고침.
- **연금소득세(✅ 토대 완료):** `TaxEngine.pension_separate_tax_annual(annual, age)` — 1500만 이하 나이별 3.3~5.5%, 초과 **전액 16.5%**(오너 결정·현행법). 연 개인합산(전 연금/IRP 인출액 합)으로 판정. 정확값 7종 검증(`test_pension_withdrawal_tax`). ⚠️ 기존 `pension_monthly_after_tax`(단일계좌)는 '1500이하 저율+초과분만 16.5%' 하이브리드 — 본 함수와 다름. 단일계좌 정밀화=BUG-PENSION-1 후보(G5-C 범위 밖).
- **생존율:** 기존 `WithdrawalAnalyzer.success_rate` 개념을 합산 자산 기준으로(전 계좌 합산 고갈 시점). `pension_tax_info`는 계좌별→합산.
- **검증 L12:** ① 단일 위탁 인출 = 양도세 손계산(인출 매도차익 과세, BUG-TAX-2 수정 확인) ② 단일 연금/IRP 인출 = 나이별 세율·1500만 플래그 ③ 위탁+연금 2계좌: 위탁 먼저 소진→연금 인출 시작 시점·연금세 정확 ④ 1500만 개인합산 16.5% 경계(연금+IRP 합산 1499만/1501만) ⑤ 세금 ON/OFF ⑥ 불변식(합산 자금보존·음수0).

### 공통 모듈 추출

세 탭이 `accounts`/`distribution_policy`/결과 surfacing을 공유 → calculator_logic의 멀티계좌 헬퍼
(`_normalize_multi_accounts`·`_validate_initial_capital_limits`·`_build_savings_summary`·정책 파싱)를
**공용 모듈로 추출**(예 `modules/multi_account_common.py`) 후 3개 logic이 import. 중복·드리프트 방지.

### 파일 변경 지도 (G5 추가분)

| 파일 | 변경 |
|------|------|
| `backtest_logic.py` | `accounts` 분기 + 단일윈도우 멀티계좌 드라이버. 단일계좌면 기존 경로 |
| `retirement_logic.py` | 적립=MultiAccountAnalyzer, 인출=멀티계좌 디큐뮬레이션 + 연금소득세 |
| `modules/retirement/multi_account_analyzer.py` | `withdrawal_amount=0` 하드코딩 해제, 인출 지원 + 생존율 |
| `modules/simulation/multi_account_loop.py` | `WithdrawalEngine`을 계좌 우선순위 인식으로 확장 + 연금/IRP 인출 연금소득세 |
| `modules/(신규) multi_account_common.py` | calculator_logic 멀티계좌 헬퍼 추출(3 logic 공유) |
| `static/js/backtest.js`·`retirement.js` + 템플릿 | calculator.js 멀티계좌 UI 패턴 복제(커서버그 이미 수정됨, 안전) |

### 구현 순서 & 게이트

```
공통 모듈 추출
  → G5-A 백테스트 (L10 통과)
  → G5-B 은퇴 적립 (L11 통과)
  → BUG-TAX-2 수정 (인출 매도 → TaxedOrderExecutor, 단일계좌 먼저, 기존 은퇴 인출 회귀)
  → G5-C 은퇴 인출 멀티계좌 (L12 통과)  ← 인출순서 + 연금소득세 신규
  → 각 탭 B2(API 서버검증)·B3(UI 스모크)
```
각 단계 검증 통과 전 다음 금지(B 단계 게이트 규약 동일). L7(실데이터 통합)은 인출까지 끝난 후.

### G5 검증 계층 L10~L12 — 4종 규약 (정상 손계산±1원 / 경계 / 세금ON·OFF / 불변식)

> §검증원칙(line 353) 그대로. 방향성(>0) 금지 — **결정론 픽스처로 정확값 어서트**.
> 픽스처: 평탄가격(100 고정)=세금노이즈0, 계단가격(100→200)=실현차익 정확, 고정성장=복리 폐형식.
> BUG-TAX-2(위탁 인출 양도세)는 ✅ 완료 — `tests/test_withdrawal_cg_tax.py` 10종(정확값 5 + 통합 5).

**L10 — 백테스트 단일윈도우 멀티계좌**
- **정상 손계산:** ① 1계좌(위탁, 계단 100→200, 거치) `MultiAccountSimulationLoop` 1회 종료값 = 기존 `TaxableSimulationRunner` 동일입력 **±1원**(골든 회귀, sell_with_tax 경유 동일). ② 2계좌(위탁A+ISA B, 평탄가격+월적립) combined 종료값 = `초기합 + Σ월적립`(수익0이므로 정확).
- **경계:** ① 계좌 1개 → 단일경로와 비트identical ② 비중<100%(현금 잔여) ③ 빈 윈도우/데이터 부족 에러.
- **세금 ON/OFF:** OFF=수익만, ON=위탁 배당세+리밸CG+청산세 정확값(계단가격으로 실현차익 손계산). 백테스트는 인출0이라 BUG-TAX-2 무관.
- **불변식:** combined = Σ account end_value. 음수잔액0.

**L11 — 은퇴 적립단계 멀티계좌** — ✅ 완료(업데이트39). `retirement_logic._run_multi_account_retirement_logic`(투자계산기 멀티함수를 은퇴 데이터관례로 적응, `MultiAccountAnalyzer` 공유). 디스패치 len>1. 인출투영(생존율)은 오너결정으로 G5-C 완전연기(`withdrawal_pending`). `tests/test_g5_retirement_accum.py` 5종(골든 래퍼=엔진±1원·combined=Σ·평탄8M·세금ON<OFF·인출pending+디스패치).
- **정상 손계산:** ① 1계좌 적립 = 기존 `AccumulationAnalyzer`/Runner 경로 ±1원(골든). ② 고정성장 픽스처로 복리 종료값 폐형식 일치. ③ calculator L0~L9 회귀 전수 통과(엔진 공유 — 적립은 calculator와 동일 루프).
- **경계:** ① `pension_start_age` 경계(적립 종료=수령 시작 나이 정합) ② ISA 1억캡 적립 중단(`contribution_end_months`) ③ 적립→인출 자산 인계 시 계좌별 평가액·취득가 보존(±1원).
- **세금 ON/OFF:** 적립기 세금(배당·리밸·연납입공제) calculator와 동일 결과.
- **불변식:** 자금보존(Σ투입−세금+수익), 연금+IRP 연≤1800만.

**L12 — 은퇴 인출단계 멀티계좌 (신규 핵심)**
- **정상 손계산(세금별 격리 — 평탄가격 100 고정으로 위탁CG=0, 연금세만):**
  - ① **연금소득세 나이별:** 연금저축 단독, 월수령 100만(연1200만<1500만), 나이60 → 전구간 5.5% → 연 세금 = 12,000,000×5.5% = **660,000**(±1원). 나이70→4.4%, 80→3.3% 구간전환 정확.
  - ② **1500만 초과 전액 16.5%(오너 결정):** 연 수령 1,800만(>1500만) → 전액 ×16.5% = **2,970,000**(±1원). 1500만 이하 분리과세(나이별)와 분기.
  - ③ **개인합산 1500만 판정:** 연금저축 월80만 + IRP 월50만 = 연 1,560만 > 1500만 → **합산**으로 전액 16.5%(계좌 따로면 각 960/600만<1500만이라 저율 — 합산 안 하면 틀림).
  - ④ **위탁 인출 양도세(BUG-TAX-2):** 계단가격, 위탁 인출 매도차익 = sell_with_tax 손계산(KR_FOREIGN 15.4%·US 250만공제후22%·국내0). 이미 단위검증됨.
- **경계:** ① 1500만 합산 경계(1,499만→저율 / 1,501만→전액16.5%) ② 나이 구간경계(69→70세 전환월) ③ 인출순서: 위탁 소진 시점 → 그 다음달부터 연금 인출 시작(세금최적 자동) ④ 합산 자산 고갈월(생존 실패 판정).
- **세금 ON/OFF:** OFF=세전 인출만(생존율), ON=연금세+위탁CG 차감 후 생존율 하락 정확.
- **불변식:** Σ계좌 자금보존(인출=외부유출), 음수잔액0, 인출액=계좌합 충당(부족시 고갈 플래그).
- **생존 정의(오너 결정):** 전 계좌 **합산** 자산이 월 인출액 못 대는 첫 시점=실패. 윈도우별 성공/실패 → 생존율.

**테스트 파일 배치:** `tests/test_g5_backtest_multi.py`(L10) · `tests/test_g5_retirement_accum.py`(L11) · `tests/test_g5_retirement_withdraw.py`(L12). 결정론 픽스처 하네스 재사용(`assert_invariants`).

---

## G5 프론트 UI 배선 — 탭별 작업목록 (2026-06-07 코드 실측 차이 정리)

> 백엔드(G5-A/B/C 엔진+L10~L12) 전부 완료. **남은 작업 = 프론트 UI뿐.** 아래는 calculator(레퍼런스) vs backtest/retirement 현 코드 실측 diff + 탭별 작업항목.

### 현 상태 실측 (파일 구조)

| 탭 | JS 위치 | 멀티계좌 UI |
|---|---|---|
| 투자계산기 | **외부** `static/js/calculator.js` (1513줄) | ✅ 완비 (레퍼런스) |
| 백테스트 | **인라인** `backtest.html` `<script>` L358~ (~758줄) | ❌ 없음 — 구형 단일 드롭다운만 |
| 은퇴 | **인라인** `retirement.html` `<script>` L589~ (~833줄) | ❌ 없음 — 구형 단일 드롭다운만 |

⚠️ backtest/retirement는 JS가 **HTML 인라인**이라 calculator.js 외부파일을 `<script src>`로 공유 불가. → 멀티계좌 함수군을 **복제**하거나 공용 JS 모듈로 추출해야 함.

### 레퍼런스 = calculator 멀티계좌 UI 3구성

1. **DOM 블록** (`calculator.html` L117~164): `taxProfileInfo` · `+계좌추가` 버튼 · `taxAccountList`(div, JS가 채움) · `taxWarnings` · `isaRenewalSection` · `taxDeductionSection` · `gainHarvestingSection` + 에러배너(`accountRestrictBanner`/`isaLimitErrorBanner`).
2. **JS 함수군** (`calculator.js` L1128~1450, 약 320줄): `addTaxAccount`/`removeTaxAccount`/`updateTaxAccountType`/`updateTaxAccountAmount`/`updateTaxAccountPriority` · 계좌별 종목관리(`ensureAccountTickers`/`redistributeAccountWeights`/`add·removeAccountTicker`/`onAccountTickerWeightChange`/`onAccountTickerSearch`/`accountWeightWarnHtml`/`renderAccountTickerList`) · `renderTaxAccounts`(핵심 렌더, 단일/멀티 분기) · `checkTaxLimits` · `fmtTaxKRW`. **BUG-G1-2(커서유실) 회피 패턴 내장** — oninput은 상태만 갱신, 입력칸 재생성 안 함.
3. **페이로드 빌더** (`calculator.js` L272~383): `buildCalculatorAccountsPayload`(accs→accounts[] + 비중검증) · `buildDistributionPolicy`(우선순위 cascade) · submit에서 `accounts`/`distribution_policy`/`reinvest_tax_credit`/`manual_comprehensive_years` 부착.
4. **결과 렌더** (`calculator.js` L623~): `renderMultiAccountSummary(multiAccount, g2, savings, autoWindmill)` — 계좌별 **p10/p50/p90 분포** + g2(풍차·세액공제) + savings(절세 3종).

### 백테스트 탭 작업항목 (난이도 중)

- **제거:** `backtest.html` L223~231 단일 `btTaxAccount` 드롭다운 + `updateBtTaxAccount` (L548~549 페이로드 `account_type`).
- **추가 DOM:** calculator L117~164 패널 블록 복제(id 충돌 없으니 동일 id 재사용 가능 — backtest엔 멀티 UI 부재).
- **추가 JS:** 멀티계좌 함수군(위 2)을 인라인 스크립트에 복제. backtest 종목상태 변수명 확인 필요(`tickers` 공유 여부).
- **페이로드:** `buildAccountsPayload` 복제 → submit body에 `accounts`/`distribution_policy` 부착. backtest는 인출 없음(`withdrawal_amount=0`).
- **⚠️ 결과 렌더 = 갈림지점.** backtest는 **단일 역사윈도우**라 계좌별 결과가 **스칼라 종료값**(분포 아님). `renderMultiAccountSummary`의 p10/p50/p90 **그대로 복제 불가** → 계좌별 **단일 end_value** 표시로 적응. combined 경로는 기존 차트 유지, 그 아래 계좌별 분해 카드 추가.

### 은퇴 탭 작업항목 (적립=하 / 인출=상)

- **제거:** `retirement.html` L401~ 단일 `retTaxAccount` 드롭다운 (L752~753 `account_type`).
- **추가 DOM/JS:** calculator 패널+함수군 복제(적립은 calculator와 동일 롤링이라 거의 그대로).
- **적립 결과:** calculator와 동형 분포(p10/p50/p90) → `renderMultiAccountSummary` **거의 그대로 재사용 가능**.
- **⚠️ 인출 결과 = 신규.** 엔진이 `sample_results`/`combined_summary`(윈도우별 **생존율 분포**) surface → calculator·backtest엔 없는 표시(생존율·고갈시점·연금소득세). 신규 렌더 필요. 가구 단일 인출액 입력 1개 + 인출순서(위탁→ISA→연금 자동) 안내.

### 공용화 결정 (오너 2026-06-07) — ✅ (b) 공용 JS 모듈 추출

- ~~(a) 복제~~ — 드리프트 위험으로 기각.
- **✅ (b) 공용 JS 모듈 추출**(`static/js/multi_account_ui.js`) → 3탭 `<script src>` 공유. 단일소스, 버그수정 1곳.
  - 1단계: calculator.js 멀티계좌 함수군(L1128~1450 + L272~325 빌더 + L623~ 렌더)을 신규 모듈로 이동, calculator.html이 모듈+calculator.js 둘 다 로드 → **calculator 회귀 0 확인**(기존 배포본 동작 보존).
  - 2단계: backtest/retirement 템플릿이 모듈 로드 + 구형 단일 드롭다운 제거 + 탭별 thin glue(페이로드 부착·결과렌더 적응).

### 권장 순서

```
오너: 복제 vs 공용모듈 결정
  → 은퇴 적립 먼저 (calculator와 동형 = 가장 안전, renderMultiAccountSummary 재사용)
  → 백테스트 (결과 스칼라 적응)
  → 은퇴 인출 (생존율 신규 렌더, 가장 복잡)
  → 각 탭 배포 + 브라우저 스모크 (smoketestguide.md 패턴)
  → L7 실데이터 통합 검증
```
(엔진 순서 백테→은퇴와 반대 — UI는 동형부터가 안전. 오너 판단.)

### ✅ 구현 결과 (2026-06-07 완료·배포)

- **결정 = 공용 JS 모듈 추출(b).** `MMTAX` config로 탭별 결합점 파라미터화(calculator 무변경).
- **1단계(커밋 57e1fc4):** 멀티계좌 입력 UI 16함수 calculator.js→`multi_account_ui.js` 추출. jsdom 8/8.
- **2단계-A 백테(fd41f65):** 멀티패널 + 계좌별 **스칼라 종료자산**(단일윈도우)+절세+g2 자체렌더. E2E `/api/backtest/run` 확인.
- **2단계-B 은퇴 적립기(9cface8):** 멀티패널 + sim accounts + `renderMultiAccountSummary`(calculator 동형 분포, 모듈로 이동해 공유). E2E `run_retirement_logic` 직접 멀티(생존율 0.6879·절세 1,632,510).
- **인출기(standalone wd) 멀티 = 미배선(정정):** ~~"백엔드 미지원"은 부정확.~~ 멀티 인출 엔진(`analyze_household_withdrawal`)은 **이미 존재**하고 sim(적립→인출)에서 작동 중. 다만 standalone `run_withdrawal_logic`이 이 엔진을 안 부르고 옛 단일 `WithdrawalAnalyzer`를 부름 → 인출기 탭만 단일. **추가 갭: 인출기 wd body가 세금 필드 자체를 안 보냄(단일조차 세금 OFF).** → G5-D에서 배선(아래).
- **검증:** jsdom 3탭 11/11·런타임에러0 + E2E 백테·은퇴. 라이브 v20260607c 배포.
- **잔여:** 브라우저 육안 스모크(jsdom+E2E로 커버) · L7 실데이터 통합검증 · **G5-D 인출기 멀티+세금 배선(아래)**.

---

## G5-D — 은퇴 인출기(standalone wd) 멀티계좌 + 세금 배선 (2026-06-07 설계)

**문제:** 은퇴시뮬(sim) = 적립기 + 인출기. 인출 부분은 멀티계좌+세금 엔진 `analyze_household_withdrawal`(위탁→ISA→연금 순차소진 + 연금소득세 + 위탁 양도세)로 이미 작동. 그러나 **standalone 인출기 탭**(`run_withdrawal_logic`)은 이 엔진을 안 쓰고 옛 단일 `WithdrawalAnalyzer`만 호출 → 멀티 ✗ + (UI가 세금 필드 미전송이라) 세금 ✗. sim과 wd는 같은 인출 엔진을 써야 함.

### 엔진 확인 (코드)
- `modules/retirement/multi_account_withdrawal.analyze_household_withdrawal(accounts, price_data, all_dates, data_start, data_end, withdrawal_years, monthly_net, *, tax_engine, withdrawal_start_age, inflation, dividend_mode, step_months)` — **단일 시작 가구**(계좌별 시작 목돈)에서 실가격 롤링 윈도우 → 생존율 + combined/계좌별 분포 + median_pension_tax. 실윈도우<MIN이면 GBM 합성 패딩.
- `accounts` 항목 = `{account_id, type, value(시작목돈), cost_basis(opt), target_weights, rebal_mode, band_width}`. `_build_account_runtime`이 cost_basis로 위탁 취득가 인계(양도세).
- **인출기는 적립 분포가 없으므로** `analyze_household_samples`(sim용, per_account_values=적립 분포) 대신 **`analyze_household_withdrawal` 직접 호출**(시작 목돈 = 사용자 입력).

### 오너 결정 (2026-06-07)
- **Q1 패널 = 공용 패널 재사용**, wd 모드선 '월 적립액' 칸 숨김(초기투자금=시작 목돈).
- **Q2 취득가 = 계좌별 미실현차익 입력칸.** 위탁계좌에 미실현차익 입력 → `cost_basis = initial_capital − unrealized_gain`. (ISA/연금은 cost_basis 무의미 → 미표시.)
- **Q3 인출 시작 나이 = `wdPensionStartAge`** 입력값(세금설정 나이 아님). `withdrawal_start_age`로 전달 → 연금소득세 나이별 세율·1500만 판정 기준.

### 백엔드 변경 (`retirement_logic.run_withdrawal_logic`)
- `if len(body.get('accounts') or []) > 1` 분기 추가(단일계좌는 기존 `WithdrawalAnalyzer` 경로 유지).
- 멀티: account_specs 구성 — 계좌별 `value=initial_capital`, `cost_basis = initial_capital − unrealized_gain`(위탁·tax_enabled시; else None), `target_weights`(계좌 종목), `rebal_mode`/`band_width`(wdRebal/wdBand 공통 또는 계좌별). 전 계좌 종목 union으로 price_data 로드(`prepare_scenario_data` purpose='withdrawal').
- `analyze_household_withdrawal(account_specs, price_data, dates, data_start, data_end, withdrawal_years, monthly_net=wdWithdraw, tax_engine=TaxEngine(user_settings) if tax_enabled, withdrawal_start_age=pension_start_age, inflation, dividend_mode)`.
- 반환 매핑(UI 소비형): `multi_account.accounts[].distribution.end_value`(per_account dist) + `combined_summary`(survival_rate, combined_end_value) + `median_pension_tax`. sim 반환과 키 정합.
- **단일 세금 갭 동시 수정:** 단일 경로도 wd body가 세금 보내면 정상 과세(이미 `WithdrawalAnalyzer` tax_engine 받음 — UI만 고치면 됨).

### 모듈 변경 (`multi_account_ui.js`) — mode 인식
- `MMTAX.mode`('accumulation'|'withdrawal') 추가. `renderTaxAccounts`가:
  - mode='withdrawal'이면 계좌 카드의 **'월 적립액' 입력 숨김**.
  - mode='withdrawal' & 계좌 type='위탁'이면 **'미실현차익' 입력칸 표시**(`updateTaxAccountAmount(idx,'unrealized_gain',...)`). 계좌 객체에 `unrealized_gain` 필드.
- calculator/적립기(mode 미설정/accumulation)는 무변경.

### UI 변경 (`retirement.html`)
- `switchMode`: wd 모드 진입 시 `MMTAX = {portfolioTickers: retTickers, totalInitId:'wdSeed', mode:'withdrawal'}`, sim 모드 복귀 시 기존(simSeed/simMonthly/accumulation)으로 스왑 + `renderTaxAccounts()` 재호출. (세금 패널은 공통이라 모드별 MMTAX 토글.)
- wd body(현재 세금 필드 없음)에 추가: `tax_enabled`/`account_type`(taxAccounts[0])/`isa_renewal`/`gain_harvesting`/`user_settings`. + `buildWdAccountsPayload`로 `accounts`(계좌별 initial_capital·unrealized_gain·tickers·rebal·priority, **월적립 없음**)·`distribution_policy`. `monthly_withdrawal`=wdWithdraw(가구 단일).
- 결과 렌더(wd 멀티): `renderMultiAccountSummary(data.multi_account, null, null, false)`(계좌별 분포) + 기존 생존율 바 + `median_pension_tax` 표시(연금세).

### 검증 (L13 — 4종 규약)
- **정상 손계산:** ① 단일 위탁 인출(평탄가격) tax_engine 경유 = WithdrawalAnalyzer 단일과 동일(세금 배선 회귀). ② 2계좌(위탁+연금) 가구 인출 — 위탁 먼저 소진→연금 인출, 연금세 나이별 정확(wdPensionStartAge 기준). ③ 미실현차익 입력 → 위탁 양도세 = (매도−(목돈−미실현)) 손계산.
- **경계:** 합산 자산 고갈월=생존 실패 · 1500만 합산 16.5% 경계 · 데이터부족 윈도우0.
- **세금 ON/OFF.**
- **불변식:** Σ계좌 자금보존, 음수0, 생존율∈[0,1].
- **jsdom:** wd 모드 패널(월적립 숨김·위탁 미실현차익칸·buildWdAccountsPayload shape) + 3탭 회귀.
- **E2E:** `run_withdrawal_logic` 멀티 직접호출(로컬 Celery 없음) → multi_account/combined_summary survival/median_pension_tax. 단일 세금 경로도.

### 파일 변경 지도
| 파일 | 변경 |
|------|------|
| `retirement_logic.py` | `run_withdrawal_logic` accounts 분기 + `analyze_household_withdrawal` 호출 + 반환 매핑. 단일 세금 경로 유지 |
| `static/js/multi_account_ui.js` | `MMTAX.mode` 인식 — 월적립 숨김/미실현차익칸(위탁) |
| `templates/retirement.html` | switchMode MMTAX 스왑 + wd body 세금·accounts + buildWdAccountsPayload + wd 멀티 결과렌더 |
| `tests/test_g5_wd_household.py` | L13 결정론 검증 |

### 순서 & 게이트
```
모듈 mode 인식 추가 (calculator/적립기 회귀 0 확인)
  → run_withdrawal_logic 멀티 분기 + 단일 세금 (L13 백엔드 검증)
  → UI 배선(switchMode·wd body·결과렌더) + jsdom 스모크
  → E2E(run_withdrawal_logic 직접) + 배포 + 서버검증
```

### ⚠️ 미해결/확인 필요
- 계좌별 rebal_mode를 wd 단일 컨트롤(wdRebal/wdBand) 공통 적용 vs 계좌별 — 현 적립기 패널은 계좌별 종목만, 리밸은 상단 공통. **wd도 상단 wdRebal 공통 적용 가정**(계좌별 리밸 UI 없음). 필요시 후속.
- 인출 순서 = 세금최적 자동(위탁→ISA→연금), 가구 단일 인출액. sim과 동일 — 사용자 지정 순서 UI 없음(오너 기결정 G5-C Q2).

### ✅ G5-D 구현 완료 (2026-06-09 · 커밋 759e393 · 배포됨)

설계대로 구현·검증·배포 완료. 오너 결정 = 공통 리밸(wdRebal/wdBand 상단).

- **백엔드(`retirement_logic.py`):** `run_withdrawal_logic`에 `accounts>1` 분기 + 신규 `_run_multi_account_withdrawal_logic`. 적립 분포 없는 인출기라 `analyze_household_withdrawal` 직접 호출(시작목돈=사용자 입력). 계좌별 spec: `value=initial_capital`, `cost_basis=목돈−미실현차익`(위탁·세금ON; else None), 공통 rebal. 반환 매핑 = `multi_account.accounts[].distribution.end_value` + `combined_summary`(survival/combined_end_value) + `median_pension_tax`. 단일 세금 갭(BUG-WD-TAX)은 백엔드 이미 배선됨(L694~705) — UI 갭이 유일 원인. `normalize_multi_accounts`에 `unrealized_gain` 필드 추가(기본0, 기존 무영향).
- **모듈(`multi_account_ui.js`):** `MMTAX.mode` 인식 — `_mmAmountFields`(신규)·primary 카드가 wd 모드면 월적립 숨김·시작목돈 라벨·위탁 미실현차익칸. calculator/적립기(accumulation 기본) 무변경.
- **UI(`retirement.html`):** `switchMode` MMTAX 모드 스왑(wd=wdSeed/withdrawal·sim=simSeed/simMonthly/accumulation) + `renderTaxAccounts` 재호출. wd body 세금 필드 + `buildWdAccountsPayload`(신규) + 분배정책. renderRetirement가 wd 멀티 per-account 분포(renderMultiAccountSummary) + `median_pension_tax` 렌더. 캐시 v20260607g5d.
- **검증:** L13 `test_g5_wd_household.py` **6종 PASS** + 광역 회귀 **71 PASS** + jsdom **14종 PASS** + E2E 실DB(458730 위탁+069500 연금: 멀티 생존율·계좌별 분포·median_pension_tax 6,121,986·tax ON/OFF).
- **버그 해소:** BUG-WD-TAX(인출기 세금 미적용) + GAP-WD-MULTI(인출기 멀티 미배선) 둘 다 ✅.

### ✅ 세금 커버리지 전탭 감사 (2026-06-09 · 커밋 421ac71)

G5-D 후 오너 요청 — 세금 구현 완성도 실측 감사(탭×계좌×이벤트 코드경로 대조).
- **적립 3탭(계산기·백테·은퇴적립)** = 단일소스 `MultiAccountSimulationLoop` 경유. 세금이벤트 전부 단일소스(배당세·리밸 양도세·청산세·ISA만기·연납입공제·이전공제·금종세). `apply_final_liquidation`=계산기/백테 True·은퇴적립 False(무청산 인계) 정확.
- **인출(은퇴인출)** 단일=`WithdrawalAnalyzer`(세금ON시 `TaxableSimulationRunner`) / 멀티=`analyze_household_withdrawal`. 양측 일관: 매도 양도세·배당세·cost_basis 인계과세·연금소득세.
- **결과: 신규 배선버그 0.** 4탭 풀플래그 도달·단일↔멀티 일관·세율 정확.
- **발견 갭 1개(버그 아닌 보수적 근사) = GAP-DECUM-COMP** — 인출 중 금융소득 종합과세 미모델링(`multi_account_withdrawal.py:107` other_financial_income=0 하드코딩). 고액 위탁 보유자 과소과세 가능. **오너 결정: 판단 전 보류**(bugs.md 등록, 미구현).

### ▶ G5 전체 완료. 다음 후보 (2026-06-10 갱신)
- **L7 실데이터 통합 검증** — Playwright 도입(2026-06-10)으로 자동화 가능해짐. **실행 계획 = `다계좌세금_E2E검증_plan.md`**(4탭 16건, 셀렉터 실측 완료, 실행 대기).
- **GAP-DECUM-COMP** — 오너 재확인(2026-06-10): **계속 보류.**
- **신규 간편 도구** — `간편계산기_plan.md` ✅ **완료**(2026-06-10, `/simple` 4종 배포·실브라우저 검증) · `세금계산기_plan.md`(위탁→ISA 전환 결정) 💡 미착수.

_갱신: Claude, 2026-06-10_
