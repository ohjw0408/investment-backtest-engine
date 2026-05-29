# 인수인계 — 2026-05-29 (2차 업데이트)

## 완료된 작업

### Track F — ISA/계좌 규제 정합성 (커밋 e8b7c1e)
- ISA+SPY 등 불법 조합 → hard error (투자계산기/연금/배당금 계산기)
- IRP + 원자재 ETF → hard error
- ISA 초기/월 납입 한도 → hard error
- ISA 풍차돌리기 → hard error
- ISA 총 1억 초과 → 캡핑 + 주황 경고 배너

### PHASE4 빠른 항목들
- **F1** (1c5db23): 대기 UX — rank < 2 → "곧 시작됩니다"
- **B2-c** (1c5db23): 내자산 현재가 Redis 캐싱 + US 배치 조회
- **B2-b** (02cb3e8): 자산 추이 차트 (myassets 자산현황 탭)
- **B3** (02cb3e8): 리밸런싱 경고 밴드 5%
- **D5** (7182ad1): 인플레이션 생활비 인포박스 + 명목수익률 안내

---

## 지금 당장 할 일: Hetzner 배포

```bash
ssh -i ~/.ssh/hetzner_ed25519 root@5.78.209.211
cd /root/investment-backtest-engine
git pull --ff-only
systemctl restart domino domino-celery
```

---

## 직접 확인해야 할 항목 (브라우저 테스트)

### Track F 테스트 (T-F1 ~ T-F8)

| # | 위치 | 테스트 | 기대 결과 |
|---|------|--------|-----------|
| T-F1 | `/calculator` | 세금 ON + ISA + SPY + 시뮬 실행 | 빨간 에러 배너 |

# 오류: {"error": "account_restrictions", "violations": ["ISA 계좌는 해외 직접 상장 종목(SPY)을 보유할 수 없습니다. 국내 상장 ETF(예: TIGER 미국S&P500)를 이용하세요."], "disclaimer": null} 이런 오류가 팝업으로 뜬다. 그래도 뭐 성공이긴 해. 단지, 그래픽을 조금 예쁘게 수정하고싶긴 하네. 우선순위는 낮아.

| T-F2 | `/calculator` | 세금 ON + ISA + 458730(TIGER) + 시뮬 실행 | 정상 결과 |
# 여기도 뭐 잘 작동하고 (역시 팝업창으로 오류 메시지 출력)
| T-F3 | `/calculator` | 세금 ON + ISA + 초기금 3000만 | 빨간 에러 배너 (초과) |
# 대체로 잘 작동해 (역시 팝업창으로 오류 메시지 출력)
| T-F4 | `/calculator` | 세금 ON + ISA + 초기 1000만 + 월 100만 | 빨간 에러 배너 (83만 한도) |

# 오류: {"error": "isa_contribution_limit", "violations": ["ISA 월 납입금 840,000원이 가능한 한도(833,333원)를 초과합니다. 연간 한도 2,000만원에서 초기 납입금 10,000,000원을 제외한 잔여 10,000,000원을 12개월로 나눈 값입니다."]} (역시 팝업창으로 오류 메시지 출력)
| T-F5 | `/calculator` | 세금 ON + ISA + 초기 500만 + 월 50만 + 20년 | 주황 경고 배너 (1억 캡) |
# 이건 결과가 좀 의심스럽네. 너가 제시한 세팅값으로 했어. 근데 주황 경고배너 결과창에 안뜨고 결과는 비관적 1억 9천, 중간값 3억 천만원, 낙관적 5억 7천이야. cagr은 중앙값이 5.84프로고. 이게 배너만 안뜨고 값은 얼추 맞는건지 아님 배너도 적용안되고 값도 틀린건지 모르겠네. 일단, 위탁계좌로 돌렸을 땐 각각 2억 3천,3억7천, 6억7천 나오긴 했어.
| T-F6 | `/retirement` | 세금 ON + 연금저축 + SPY | 빨간 에러 배너 |
# (역시 팝업창으로 오류 메시지 출력) 작동은 함.
| T-F7 | `/retirement` 또는 `/calculator` | 세금 ON + IRP + 132030(KODEX 골드선물) | 빨간 에러 배너 |
# (역시 팝업창으로 오류 메시지 출력) 작동은 함.
| T-F8 | `/calculator` | 세금 ON + 연금저축 + 132030 | 정상 결과 (연금저축은 원자재 허용) |
# 오류: 연금 수령은 만 55세 이상만 가능합니다. (입력 나이: 40) 이건 뭔 그지같은 오류냐? 뭐 하드코딩되어있냐? 그리고 나이는 상관없지. 이게 수령시점에 자산이 얼마인지를 보고 싶어서 시뮬을 돌리는건데. 나이 상관없이 결과는 보여줘야해. 투자계산기나 배당금 계산기에선. 은퇴 계산기에서도 "연금 수령 시작 나이"를 사용자가 입력할 수 있게 해줘야지. 
### PHASE4 테스트

| # | 위치 | 테스트 | 기대 결과 |
|---|------|--------|-----------|
| T-B2b | `/myassets` | 자산현황 탭 하단 | 자산 추이 차트 표시 (1개월/3개월/1년/전체) |
# 이건 잘 보여. 이거 구매시점은 아직 구현 안한거지? 
| T-B3 | `/myassets` → 리밸런싱 탭 | 목표비중 설정된 그룹 있을 때 | 밴드 이탈 시 주황 경고, 정상 시 초록 OK |
# 목표 비중 하드코딩되어있는 듯? 사용자 계정에 연결해서 사용자가 입력할 수 있게 해야해.
| T-D5 | `/retirement` | 월 인출금/기간/인플레이션 입력 | 입력창 아래 "인플레이션 반영 생활비" 인포박스 실시간 갱신 |
# 인출 n년간 필요한 총 금액이 너무 적은듯. 예를 들어, 지금 월 300만원 기준 인플레 3퍼 잡고 20년 뒤에는 한 달에 950만원 필요하다는데 20년간 필요한 인출 총액이 명목 기준이라고 명시되어있는데도 1.0억원이래. 그리고 막 수치 바꾸면서 테스트해보는데 염병할 유효숫자가 1개야. 1.0억 다음에 바로 2.0억이 나와. 이거 수정해야해.
---

## 테스트 완료 후 보고 형식

```
T-F1: PASS / FAIL
T-F2: PASS / FAIL
T-F3: PASS / FAIL
T-F4: PASS / FAIL
T-F5: PASS / FAIL
T-F6: PASS / FAIL
T-F7: PASS / FAIL
T-F8: PASS / FAIL
T-B2b: PASS / FAIL
T-B3: PASS / FAIL
T-D5: PASS / FAIL
```

---

## 버그 / 미완료 항목 (2차 테스트 결과)

### BUG-1 미해결: 에러 여전히 alert 팝업
**상태:** 배너 밖으로 이동했는데도 alert 뜸.  
**실제 원인:** `pollTask`에서 `throw new Error(data.error)` 이후 catch에서 `JSON.parse(err.message)` 실패 가능성. pollTask 내부에서 직접 파싱해 Error 객체에 `_data` 속성으로 붙여야 함.  
**수정:** `pollTask` 내 FAILURE 처리 → `err._data = JSON.parse(data.error)`, catch에서 `err._data` 사용.  
**파일:** `static/js/calculator.js` (pollTask), `templates/retirement.html` (retPollTask)

### BUG-2 미해결: ISA 캡 배너 미표시 + 배당 0원
**상태:** 경고 배너 안 뜸. 결과값도 위탁과 동일. 배당 총 0원 표기.  
**원인 추정 1 (캡):** `tax_enabled` 또는 `account_type` 값이 프론트→백엔드 전달 중 누락될 수 있음. 브라우저 콘솔 F12 → `[ISA cap]` 로그 확인 필요.  
**원인 추정 2 (배당 0원):** ISA 계좌는 내부 배당 비과세이지만 UI에서 배당 표시를 0으로 처리하는 로직 있을 수 있음. 확인 필요.  
**수정:** 콘솔 로그 확인 후 원인 파악. 별도 작업.

### BUG-3 반쪽 해결: 연금 수령 시작 나이 입력 없음
**현재:** 55세 제한 오류는 없어졌으나 수령 시작 나이를 사용자가 입력할 수 없음.  
**필요한 것:**
- 은퇴 계산기 인출기 설정에 "연금 수령 시작 나이" 입력칸 추가
- 이 값을 `pension_start_age`로 backend에 전달
- `after_tax_withdrawal()` → `_pension_tax(age=pension_start_age)` 사용
- 현재는 `user_settings.age` (세금설정의 현재 나이) 사용 중  
**파일:** `templates/retirement.html`, `retirement_logic.py`, `modules/tax/liquidation.py`

### BUG-4 ✅ 해결됨

### BUG-5 ✅ 해결됨 (슬라이더 추가)

### BUG-6 신규: 밴드 슬라이더 떨림 + 1% UI 크기 변동
**증상:** 슬라이더 움직일 때 화면 심하게 떨림. 1% 값일 때만 레이아웃 크기 다름.  
**원인:** `renderRebalance()` 호출마다 전체 DOM 재생성 → 레이아웃 시프트. 1% 레이블 글자폭 차이(1자리 vs 2자리).  
**수정:** debounce 처리 (100ms). 레이블 min-width 고정.  
**파일:** `templates/myassets.html`

### BUG-7 신규: 밴드 슬라이더 옆 숫자 직접 입력 없음
**요구:** 슬라이더 + 숫자 입력창 함께 (0.5% 단위 정밀 입력). step=0.5로 변경.  
**파일:** `templates/myassets.html`

### 검증 필요: 인출 인플레이션 반영 여부
**현재 코드:** `withdrawal_analyzer.py:370` — `if self.inflation > 0 and (i+1)%12==0: withdrawal *= (1+self.inflation)` → 매년 인출액 인플레이션만큼 증가. **구현됨.**

### 검증 필요: 연금 세금 — 세액공제 원금 vs 비공제 원금 분리
**규칙:** 세액공제 받은 납입액 + 운용수익 → 수령 시 과세. 세액공제 못 받은 원금 → 수령 시 비과세(원금 반환).  
**예:** 연 1800만 납입, 600만만 세액공제 → 1200만은 비과세 반환.  
**현재 코드:** `base_tax.py _pension_tax()` 에 `non_deductible` 계산 로직 있음 (`annual_contribution`, `pension_years` 파라미터). `taxable_runner.py`에서 이 값을 실제로 전달하는지 확인 필요.  
**파일:** `modules/simulation/taxable_runner.py` — `isa_years_held` 전달처럼 `pension_years`, `annual_contribution` 전달 여부 확인.

---

## T-B2b 답변
구매 시점(취득가, 매수일) 표시는 B4(거래 트래킹) 구현 후 가능. 아직 미구현 맞음.

---

## 다음 작업 후보

1. **BUG-1/2/3/6/7 수정** — 위 버그들 차례로 fix
2. **연금 세금 검증** — pension_years/annual_contribution 전달 여부 확인 및 수정
3. **D4 거래수수료**: FeeEngine → simulation_loop.py 연결. 1~2일. 복잡함.
4. **D1 TDF**: TDF(Target Date Fund) 기능. 3~4일.
5. **Track G**: 다중 계좌 시뮬 엔진. Track F 완료됐으므로 시작 가능. 2~3주.

```text
# 버그 수정: "BUG-1,2,3,6,7 수정해줘"
# 연금세금 검증: "연금 세금 비공제 원금 구현 확인해줘"
# D4: "D4 거래수수료 설정 구현해줘"
# Track G: "PHASE4_PLAN.md § 4G G1부터 구현해줘"
```
