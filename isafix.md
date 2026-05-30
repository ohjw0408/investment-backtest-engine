# 계좌 유형 제한 + ISA 납입 한도 강제 구현 계획

> **상태 (2026-05-30):** ✅ 백엔드 완료(e8b7c1e) + BUG-1~5 전부 수정(2026-05-30). ISA+SPY/IRP+원자재/ISA 납입한도/풍차돌리기 hard error 작동, ISA 1억 캡 = 납입중단 방식 재설계(7dd75a4), 연금 수령 나이 입력 추가, 밴드 슬라이더 직접입력 추가.
>
> ⚠️ **잔여 (우선순위 낮음, handoff.md 사용자 피드백):** ① 에러가 인라인 배너 아닌 팝업으로 뜨는 케이스 잔존(기능은 정상, 미관) ② T-F5 ISA 1억 캡 배너 표시 + 결과값 — 배당 0은 `ETF_BACKFILL Phase 6.0` 버그가 원인. ③ T-B3 리밸런싱 목표비중 하드코딩 → 사용자 계정 연동 필요(B 그룹 작업).

## Context

투자계산기/연금 시뮬에서 ISA 계좌에 SPY(미국 직접상장 ETF)를 담아도 아무 제한 없이 실행된다. 실제 규제 위반이다. 또한 ISA 풍차돌리기 기능이 연간/총 납입 한도를 무시하고 무한 납입을 허용한다.

백테스트(`backtest_logic.py`)에는 이미 종목 제한 검증이 있지만, 투자계산기·연금 시뮬에는 없다.

**목표:**
1. 계좌 유형별 종목 제한을 투자계산기·연금 시뮬에도 적용
2. ISA 납입 규칙 강제 (초기/월 납입 한도 HARD ERROR, 총 1억 캡 + 경고)
3. IRP에 원자재 ETF 추가 제한
4. 원자재 ETF 종목 분류 추가

---

## 한국 규제 규칙 (계좌별 종목 제한)

| 계좌 | 허용 | 금지 |
|------|------|------|
| **위탁** | 모든 종목 | — |
| **ISA** | KR_DOMESTIC, KR_FOREIGN | US_DIRECT |
| **연금저축** | KR_DOMESTIC ETF, KR_FOREIGN ETF, 원자재 ETF | US_DIRECT, 개별주식(한국/미국), 레버리지, 인버스 |
| **IRP** | KR_DOMESTIC ETF, KR_FOREIGN ETF (안전자산 30%+ 조건) | US_DIRECT, 개별주식, 레버리지, 인버스, **원자재 ETF** |

> IRP 안전자산 30%+ 조건: 채권형 ETF/펀드 없이 위험자산만 담으면 차단 (이미 구현됨 — `validate_irp_weights()`)

## ISA 납입 한도 규칙

| 항목 | 한도 | 위반 시 |
|------|------|---------|
| 초기 납입 | ≤ 2,000만원 | HARD ERROR |
| 월 납입 | ≤ (2,000만 − initial) / 12 | HARD ERROR |
| 총 납입 | ≤ 1억원 (5년 통산) | 소프트 캡 + 결과 경고 배너 |
| **풍차돌리기** | **불가** | **HARD ERROR** |

> **풍차돌리기 불가 이유**: ISA 만기 시 수령액은 투자 수익으로 인해 연간 납입 한도(2,000만원)를 대부분 초과하므로, 만기 후 재납입 자체가 불가. 풍차돌리기 기능 자체를 지원하지 않음.

> **월 납입 공식**: 연도 1 기준. `initial + monthly × 12 ≤ 2,000만원` 조건 → `monthly ≤ (2,000만 − initial) / 12`. 연도 2+는 매년 2,000만 한도 리셋이지만, 이 공식이 더 엄격(initial ≥ 0)하므로 년차 무관하게 적용.

---

## 이미 구현된 것 (건드리지 않음)

- `modules/tax/account_tax.py:validate_account_portfolio()` — US_DIRECT, STOCK, LEVERAGED/INVERSE ETF 제한 (완성) → IRP에 COMMODITY_ETF 추가만 필요
- `modules/tax/account_tax.py:check_contribution_limits()` — 연금 합산 납입 경고 (완성)
- `backtest_logic.py:65-74` — 백테스트에서 validate_account_portfolio() 호출 (완성)
- `modules/tax/base_tax.py:classify_asset()` — KR_DOMESTIC/KR_FOREIGN/US_DIRECT 분류 (완성)
- `modules/tax/base_tax.py:validate_irp_weights()` — IRP 위험자산 70% 한도 (완성)
- `modules/tax/account_tax.py:ACCOUNT_LIMITS` — 상수 정의 (완성)

---

## 구현 계획

### Step 1 — base_tax.py: COMMODITY_ETF 분류 추가

**파일:** `modules/tax/base_tax.py`

`classify_instrument_type()` 함수에 COMMODITY_ETF 케이스 추가.

기존 반환값: `'ETF' | 'LEVERAGED_ETF' | 'INVERSE_ETF' | 'STOCK' | 'UNKNOWN'`
추가 반환값: `'COMMODITY_ETF'`

이름 기반 키워드 탐지 (name 필드 또는 종목명 확인):
```python
COMMODITY_KEYWORDS = [
    "금선물", "원유선물", "원자재", "귀금속", "천연가스",
    "구리", "농산물", "GOLD", "OIL", "CRUDE", "SILVER",
    "COMMODITY", "COMMODIT", "NATURAL GAS",
]
```

기존 `classify_instrument_type()` 흐름에서 ETF로 판별된 이후, 이름 기반으로 COMMODITY_ETF 여부 추가 판별.

---

### Step 2 — account_tax.py: IRP에 COMMODITY_ETF 제한 추가

**파일:** `modules/tax/account_tax.py`

`validate_account_portfolio()` 내 연금저축·IRP 블록 분리 및 IRP에 COMMODITY_ETF 추가:

현재: `elif account_type in ("연금저축", "IRP"):` 하나로 묶임 → **분리 필요**

```python
elif account_type == "연금저축":
    # US_DIRECT, STOCK, LEVERAGED_ETF, INVERSE_ETF 금지 (원자재 ETF 허용)
    if market == "US_DIRECT": ...
    elif inst == "STOCK": ...
    elif inst in ("LEVERAGED_ETF", "INVERSE_ETF"): ...

elif account_type == "IRP":
    # 연금저축 동일 + COMMODITY_ETF 추가 금지
    if market == "US_DIRECT": ...
    elif inst == "STOCK": ...
    elif inst in ("LEVERAGED_ETF", "INVERSE_ETF"): ...
    elif inst == "COMMODITY_ETF":
        violations.append(
            f"IRP 계좌는 원자재 ETF({ticker})를 보유할 수 없습니다. "
            f"주식형·채권형 ETF만 투자 가능합니다."
        )
```

---

### Step 3 — account_tax.py: ISA 납입 한도 검증 함수 추가

**파일:** `modules/tax/account_tax.py`

새 함수 `validate_isa_contribution(initial, monthly)` 추가:

```python
ISA_ANNUAL_LIMIT = 20_000_000

def validate_isa_contribution(initial: float, monthly: float) -> list[str]:
    """
    ISA 납입 규칙 하드 체크.
    위반 시 오류 메시지 리스트 반환 (비어 있으면 유효).
    """
    errors = []
    if initial > ISA_ANNUAL_LIMIT:
        errors.append(
            f"ISA 초기 납입금 {initial:,.0f}원이 연간 납입 한도(2,000만원)를 초과합니다. "
            f"ISA는 개설 후 연간 최대 2,000만원까지만 납입 가능합니다."
        )
        return errors  # 이하 월 납입 체크 의미 없음

    annual_remaining = ISA_ANNUAL_LIMIT - initial
    monthly_max = annual_remaining / 12  # 잔여 연간 한도 / 12개월
    if monthly > monthly_max:
        errors.append(
            f"ISA 월 납입금 {monthly:,.0f}원이 가능한 한도({monthly_max:,.0f}원)를 초과합니다. "
            f"연간 한도 2,000만원에서 초기 납입금 {initial:,.0f}원을 제외한 "
            f"잔여 {annual_remaining:,.0f}원을 12개월로 나눈 값입니다."
        )
    return errors
```

---

### Step 4 — calculator_logic.py: 종목 제한 + ISA 납입 체크

**파일:** `calculator_logic.py`

`run_calculator_logic()` 진입 직후 추가 (backtest_logic.py:65-74 패턴):

**4a. 종목 제한 검증**
```python
if tax_enabled and account_type != '위탁':
    from modules.tax.account_tax import validate_account_portfolio
    _te = TaxEngine(user_settings)
    _check = validate_account_portfolio(account_type, tickers, weights, _te)
    if not _check['valid']:
        raise ValueError({
            'error': 'account_restrictions',
            'violations': _check['violations'],
            'disclaimer': _check.get('disclaimer'),
        })
```

**4b. ISA 풍차돌리기 하드 차단**
```python
if account_type == 'ISA' and tax_enabled and isa_renewal:
    raise ValueError({
        'error': 'isa_windmill_disabled',
        'violations': [
            "ISA 풍차돌리기를 지원하지 않습니다. "
            "ISA 만기 후 수령액은 연간 납입 한도(2,000만원)를 대부분 초과하여 "
            "재납입이 불가합니다. ISA 계좌를 일반 모드로 선택하거나 위탁 계좌를 이용하세요."
        ],
    })
```

**4c. ISA 납입 하드 체크**
```python
if account_type == 'ISA' and tax_enabled:
    from modules.tax.account_tax import validate_isa_contribution
    isa_errors = validate_isa_contribution(initial, monthly)
    if isa_errors:
        raise ValueError({
            'error': 'isa_contribution_limit',
            'violations': isa_errors,
        })
```

**4d. ISA 총 1억원 캡 계산**
```python
isa_cap_info = None
if account_type == 'ISA' and tax_enabled:
    ISA_TOTAL_LIMIT = 100_000_000
    planned_total = initial + monthly * 12 * accumulation_years
    if planned_total > ISA_TOTAL_LIMIT:
        remaining_after_initial = max(0.0, ISA_TOTAL_LIMIT - initial)
        monthly_months = accumulation_years * 12
        monthly = remaining_after_initial / monthly_months if monthly_months > 0 else 0
        isa_cap_info = {
            'capped': True,
            'original_total': round(planned_total),
            'capped_total': ISA_TOTAL_LIMIT,
            'original_monthly': round(body.get('monthly_contribution', 0)),
            'adjusted_monthly': round(monthly),
        }
```

**4e. 반환값에 isa_cap_info 포함**

---

### Step 5 — retirement_logic.py: 종목 제한 + ISA 납입 체크

**파일:** `retirement_logic.py`

Step 4와 동일 패턴 (`run_retirement_logic()` 진입 직후).

---

### Step 5b — dividend_logic.py: ISA 납입 체크

**파일:** `dividend_logic.py`

배당금 계산기에도 동일한 ISA 납입 체크 적용:

```python
if account_type == 'ISA' and tax_enabled:
    from modules.tax.account_tax import validate_isa_contribution
    isa_errors = validate_isa_contribution(initial, monthly)
    if isa_errors:
        raise ValueError({'error': 'isa_contribution_limit', 'violations': isa_errors})
```

`validate_account_portfolio()`도 동일하게 적용 (종목 단일 입력).

---

### Step 6 — accumulation_analyzer.py: 풍차돌리기 제거

**파일:** `modules/retirement/accumulation_analyzer.py`

`_run_isa_renewal_cycle()` 함수 자체는 유지.

풍차돌리기 진입 조건(`account_type == "ISA" and isa_renewal`)이 calculator_logic.py / retirement_logic.py에서 이미 차단되므로 이 파일 수정 불필요.

> `_run_isa_renewal_cycle()`은 호출되지 않게 됨. 코드 삭제 여부는 이후 결정.

---

### Step 7 — Frontend: 에러/경고 배너

**파일:** `templates/calculator.html`, `templates/retirement.html`

**7a. 종목 제한 에러 배너** (빨간):
```html
<div id="accountRestrictBanner" style="display:none;background:#FFEBEE;border:2px solid #E53935;border-radius:8px;padding:14px 18px;margin-bottom:14px;font-size:0.85rem;color:#B71C1C;">
  <strong>⛔ 계좌 유형 제한 위반</strong>
  <div id="accountRestrictDetail" style="margin-top:6px;line-height:1.7;"></div>
</div>
```

**7b. ISA 납입 한도 초과 에러 배너** (빨간):
```html
<div id="isaLimitErrorBanner" style="display:none;background:#FFEBEE;border:2px solid #E53935;border-radius:8px;padding:14px 18px;margin-bottom:14px;font-size:0.85rem;color:#B71C1C;">
  <strong>⛔ ISA 납입 한도 초과</strong>
  <div id="isaLimitErrorDetail" style="margin-top:6px;line-height:1.7;"></div>
</div>
```

**7c. ISA 총 1억원 캡 경고 배너** (주황, 결과창 상단에 크게):
```html
<div id="isaCapBanner" style="display:none;background:#FFF3E0;border:2px solid #F57C00;border-radius:8px;padding:16px 20px;margin-bottom:16px;font-size:0.92rem;color:#E65100;">
  <strong>⚠ ISA 총 납입 한도 적용 — 시뮬레이션이 조정되었습니다</strong>
  <div id="isaCapDetail" style="margin-top:8px;line-height:1.8;"></div>
</div>
```

**7d. JavaScript (calculator.js, retirement.js)**

에러 핸들링 (현재 `alert()` 대신 배너):
```javascript
if (data.error_type === 'account_restrictions' || data.error_type === 'isa_contribution_limit'
    || data.error_type === 'isa_windmill_disabled') {
    const bannerId = data.error_type === 'isa_contribution_limit' || data.error_type === 'isa_windmill_disabled'
        ? 'isaLimitErrorBanner' : 'accountRestrictBanner';
    const detailId = bannerId.replace('Banner', 'Detail');
    const banner = document.getElementById(bannerId);
    banner.querySelector('#' + detailId).innerHTML =
        (data.violations || []).map(v => `<div>• ${v}</div>`).join('');
    banner.style.display = 'block';
    resultsSection.style.display = 'none';
}
```

renderResult에서 ISA 캡 경고:
```javascript
const capInfo = data.isa_cap_info;
if (capInfo && capInfo.capped) {
    const banner = document.getElementById('isaCapBanner');
    const orig = Math.round(capInfo.original_total / 10000).toLocaleString();
    const origM = Math.round(capInfo.original_monthly / 10000).toLocaleString();
    const adjM  = Math.round(capInfo.adjusted_monthly / 10000).toLocaleString();
    banner.querySelector('#isaCapDetail').innerHTML =
        `ISA 납입 한도(5년 총 1억원)를 초과하여 월 납입금이 자동 조정되었습니다.<br>` +
        `계획 총 납입 <strong>${orig}만원</strong> → 시뮬레이션 적용 <strong>1억원</strong><br>` +
        `월 납입금: <strong>${origM}만원</strong> → <strong>${adjM}만원</strong>으로 조정`;
    banner.style.display = 'block';
}
```

---

## 수정 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `modules/tax/base_tax.py` | COMMODITY_ETF 분류 추가 (`classify_instrument_type`) |
| `modules/tax/account_tax.py` | IRP에 COMMODITY_ETF 제한; 연금저축·IRP 블록 분리; `validate_isa_contribution()` 신규 함수 |
| `calculator_logic.py` | 종목 제한 + 풍차돌리기 차단 + ISA 납입 하드 체크 + 총 1억 캡 |
| `retirement_logic.py` | 종목 제한 + ISA 납입 하드 체크 + 총 1억 캡 |
| `dividend_logic.py` | 종목 제한 + ISA 납입 하드 체크 |
| `modules/retirement/accumulation_analyzer.py` | 변경 없음 (풍차돌리기 진입 상위에서 차단) |
| `templates/calculator.html` | 에러 배너 3종 추가 |
| `templates/retirement.html` | 에러 배너 3종 추가 |
| `static/js/calculator.js` | 에러 핸들링 + renderResult ISA캡 처리 |
| `static/js/retirement.js` | 동일 |

**건드리지 않는 파일:**
- `backtest_logic.py` (이미 완성)
- `modules/tax/base_tax.py:validate_irp_weights()` (IRP 70% 한도 이미 완성)

---

## 재사용할 기존 함수

- `account_tax.py:validate_account_portfolio()` → 수정하여 재사용
- `base_tax.py:classify_asset()`, `classify_instrument_type()` → 후자에 COMMODITY_ETF 추가
- `base_tax.py:validate_irp_weights()` → 그대로 재사용
- `backtest_logic.py:65-74` → calculator/retirement에 동일 패턴 복사

---

## 검증 방법

1. **ISA + SPY**: 투자계산기/배당금 계산기에서 SPY + ISA → 빨간 에러 배너 (시뮬 차단)
2. **IRP + 원자재 ETF**: IRP + KODEX금선물 → 빨간 에러 배너
3. **연금저축 + 원자재 ETF**: 연금저축 + KODEX금선물 → 정상 통과 (연금저축은 허용)
4. **ISA 초기 3000만원**: ISA + initial=3000만 → 빨간 에러 배너 "연간 한도 초과"
5. **ISA 초기 1000만 + 월 100만**: `(2000만-1000만)/12 = 83.3만 < 100만` → 빨간 에러 배너
6. **ISA 초기 0 + 월 167만**: `(2000만-0)/12 = 166.7만 < 167만` → 빨간 에러 배너
7. **ISA 총 1억 초과**: ISA + initial=500만 + 월 50만 + 10년 = 1.1억 → 시뮬 실행, 주황 경고 배너
8. **ISA 풍차돌리기 ON**: ISA + 풍차돌리기 ON → 빨간 에러 배너 "풍차돌리기 불가"
9. **배당금 계산기 ISA 체크**: dividend_logic.py 동일 검증
10. **backtest 무영향**: 기존 backtest ISA 검증 동일하게 동작
