# 다계좌 세금 E2E 검증 계획 (Playwright 실브라우저)

작성: 2026-06-10 (Claude). 상태: ✅ **완료 (2026-06-11) — 최종 16/16 PASS, §8 완료 기준 충족 = P0 L7 완료.**
결과: `tests/e2e_multitax/results/20260611_result.md`. 첫 실행 11 PASS / 4 FAIL / 1 SKIP → 발견 2건(GAP-RET-KRDATA, BUG-WD-MULTI-LIVE) 당일 조사·수정(9486eee) 후 C·D 재검 7/7 PASS. 재실행: `node tests/e2e_multitax/run_all.js` (C·D만 = `run_cd.js`).
대상: **투자계산기 · 포트폴리오 분석(백테스트) · 은퇴 설계(시뮬레이션 + 인출기)** 4개 화면의 멀티계좌 세금 배선.

---

## 1. 배경 / 이 계획이 메우는 구멍

| 기존 검증 | 커버 | 안 커버 |
|---|---|---|
| 결정론 테스트 L0~L13 (200+ PASS) | 엔진 수학 정확성 (손계산 ±1원) | UI→API→엔진 실배선 |
| jsdom 스모크 | UI 렌더·페이로드 빌드 | 실브라우저·실서버·Celery 큐·차트 |
| 세금 커버리지 감사 (2026-06-09) | 코드 경로 읽기 (배선버그 0) | 실행 증거 아님 |
| smoketestguide.md 9종 | 절차 정의 | **사람 손 필요 → 한 번도 실행 안 됨** |

→ **이 계획 = roadmap P0 "L7 실데이터 통합검증"의 실행판.** Playwright(Chromium headless)로
Claude가 직접 실행. smoketestguide의 손절차를 자동화 + 은퇴/백테스트 탭으로 확장.

## 2. 방법 / 원칙

- **대상 서버: 라이브** `https://moneymilestone.co.kr` (실데이터·실Celery — 진짜 E2E).
  로컬 Flask는 Celery 없어 계산기/은퇴 submit 경로 검증 불가.
- **진짜 클릭 우선**: 토글·계좌추가·실행버튼은 실제 DOM 클릭. 배선 검증이 목적이므로
  `page.evaluate`로 내부 함수 직접 호출은 최후 수단(쓰면 테스트명에 표기).
- **판정 3층**:
  1. **구조** — 패널/배너/필드가 뜨는가 (smoketestguide 방식)
  2. **API 응답** — `page.waitForResponse`로 JSON 캡처 → `multi_account.enabled`,
     `accounts[].distribution`, `savings`, `g2`, `median_pension_tax` 등 필드 존재·형태
  3. **불변식** — 정확 금액은 결정론 테스트 영역이므로 여기선 **방향성만**:
     - 세금 ON 종료자산 ≤ OFF (동일 입력)
     - 계좌별 결과 N개 = 입력 계좌 수
     - 절세액 = (실제 세후) − (위탁 가정 세후) ≥ 0 (ISA/연금 포함 시)
     - 미실현차익↑ → 인출기 위탁 결과 악화(세금↑)
- **실데이터 가변성**: 정확한 ₩는 매번 다름 → 금액 하드코딩 금지, 구조·부호·대소만.
- **라이브 부하 주의**: 시뮬 1회 수십 초(과거 실측 53s). 테스트당 타임아웃 180s,
  순차 실행(동시 submit 금지), 저장/로그인 액션 없음(읽기성 시뮬만).

## 3. 공통 사전조건

1. **세금 프로필**: `/tax-settings`에서 나이 40 · 연 근로소득 50,000,000 · ISA 일반형.
   (테스트 시작 시 1회 확인, 다르면 설정 후 저장. ⚠️ 저장이 로그인 필요하면 중단하고 오너 보고)
2. **종목**: 국내상장만 — `458730`(TIGER 미국배당다우존스, 배당 있음) ·
   `360750`(TIGER 미국S&P500). ISA·연금·IRP는 US 직접상장 불가 규칙 때문.
3. **기간 12년** (풍차 3년×4회 관찰), 배당 재투자, 리밸 없음 — 별도 지정 없으면.

## 4. 셀렉터 레퍼런스 (2026-06-10 실측)

| 화면 | 요소 | 셀렉터 |
|---|---|---|
| 공통(계좌카드) | 계좌 목록 컨테이너 | `#taxAccountList` |
| | 계좌 유형 select | `#taxAccountList select` (i번째 카드, `updateTaxAccountType`) |
| | 초기자본/월적립/미실현차익 input | 카드 내 input (`updateTaxAccountAmount` oninput) |
| | 우선순위 input | 카드 헤더 (`updateTaxAccountPriority`) |
| | 계좌별 종목검색 | `#accountTickerSearch{i}` |
| | JS 상태(검증용 읽기) | `window.taxAccounts` |
| 계산기 | 세금 토글 / 라벨 | `#taxToggleWrap` 클릭 / `#taxToggleLabel` =ON/OFF |
| | 종목검색/드롭다운 | `#tickerSearchInput` / `#tickerDropdown` |
| | 초기·월적립(상단) | `#initialCapital` / `#monthlyContrib` |
| | 실행 / 결과 | `#runBtn` / `#multiAccountSummary` |
| 백테스트 | 세금 토글 | `#btTaxWrap` / `#btTaxLabel` |
| | 종목검색 / 금액 | `#btSearchInput` / `#btSeed` `#btMonthly` `#btStartDate` `#btEndDate` |
| | 실행 / 멀티 결과 | `#btRunBtn` / `#btMultiAccountSummary` |
| 은퇴 | 모드 탭 | `#tabRetSim`(적립+인출 시뮬) / `#tabRetWd`(인출기) |
| | 세금 토글 | `#retTaxWrap` / `#retTaxLabel` |
| | sim 금액 | `#simSeed` / `#simMonthly` |
| | wd 금액/기간/나이 | `#wdSeed` / `#wdYears`(hidden, 슬라이더 `#wdYearsSlider`) / `#wdPensionStartAge` |
| | 실행 / 멀티 결과 | `#retRunBtn` / `#multiAccountSummary` |

계좌 추가 버튼: `renderTaxAccounts()`가 동적 렌더 — `#taxAccountList` 내 "+ 계좌 추가" 텍스트 버튼 클릭.
카드 내부 input은 동적이라 **순서 기반 셀렉터**(`#taxAccountList .acct-card:nth(i) input[...]`) 사용,
구현 시 실DOM 덤프로 확정.

## 5. 테스트 매트릭스

### A. 투자계산기 (`/calculator`) — 6건

| # | 시나리오 | 구성 | PASS 기준 |
|---|---|---|---|
| A1 | 멀티 기본 + 절세액 | ISA(1천만,월100만,458730,순위1,풍차✅) + 위탁(0,0,순위2), 세금ON, 12년 | 에러 없음 · `#multiAccountSummary` 계좌별 p10/p50/p90 2세트 · 절세액 ≥0 표시 · g2 패널(풍차 만기 ≥3회) |
| A2 | 세금 ON ≤ OFF | A1 구성으로 ON 1회·OFF 1회 | API 응답 combined p50: ON ≤ OFF |
| A3 | ISA 초기자본 한도 ⛔ | ISA 초기 21,000,000 + 위탁 | 빨간 에러 배너("연 납입한도 2,000만원 초과") · 시뮬 미실행 |
| A4 | 연금 풀세트 공제 | ISA(월100만,풍차)+연금저축(월50만,360750)+위탁, 12년 | g2에 "연 납입 세액공제 환급" 줄 >0 · 풍차 만기 줄 |
| A5 | 자동 금종세 풍차중단 ⭐ | ISA(1천만,월100만,풍차) + 위탁 **8억**(458730), 12년 | 수동입력 없이 "금융소득종합과세 대상연도" 표시 + 만기횟수 < A1. 미달 시 10억 재시도 1회 |
| A6 | 세금 OFF 대조 | 계좌 2개 + 세금 OFF | G2 컨트롤/절세 패널 미표시, 일반 멀티 결과만 |

### B. 포트폴리오 분석 (`/backtest`) — 3건

| # | 시나리오 | 구성 | PASS 기준 |
|---|---|---|---|
| B1 | 멀티 2계좌 + 절세 | ISA(1천만,458730) + 위탁(1천만,458730), 세금ON, 2015-01-01~ | `#btMultiAccountSummary`에 계좌별 **스칼라 종료자산** 2개 + combined + 절세액. API `multi_account.enabled=true, accounts=2` |
| B2 | 세금 ON ≤ OFF | B1 구성 ON/OFF | combined 종료자산 ON ≤ OFF |
| B3 | 단일 회귀 | 계좌 1개 위탁 세금ON | 기존 단일 결과 화면 정상(분할매도 패널 포함) — 멀티 배선이 단일 안 깨뜨림 |

### C. 은퇴 시뮬레이션 (`/retirement` sim 모드) — 3건

| # | 시나리오 | 구성 | PASS 기준 |
|---|---|---|---|
| C1 | 멀티 적립+인출 투영 | 위탁(1천만,월50만,458730) + 연금저축(0,월50만,360750), 세금ON | `#multiAccountSummary` 계좌별 분포 + 생존율 표시. API `multi_account.enabled=true` + `combined_summary.survival` ∈ (0,1] |
| C2 | 세금 ON ≤ OFF | C1 구성 ON/OFF | 적립 종료자산(또는 생존율) ON ≤ OFF |
| C3 | 무청산 인계 확인 | C1 세금ON 응답 | 적립끝 일괄청산세 항목 없음(은퇴는 무청산 인계 = BUG-TAX-3 회귀 방지). API에 액수로 직접 안 보이면 생존율>0 구조 확인으로 대체하고 한계 기록 |

### D. 인출기 (`/retirement` wd 모드) — 4건

| # | 시나리오 | 구성 | PASS 기준 |
|---|---|---|---|
| D1 | wd 모드 UI 전환 | `#tabRetWd` 클릭 + 세금ON + 계좌 2개 | 계좌카드: **월적립칸 숨김** · 시작목돈 라벨 · 위탁 카드에 **미실현차익칸** 표시 (G5-D 배선) |
| D2 | 멀티 인출 실행 | 위탁(3억, 미실현 1억, 458730) + 연금저축(2억, 360750), 월인출 200만, 30년, 수령나이 65 | 계좌별 분포 + 생존율 + **연금소득세(median_pension_tax) 표시** · API `combined_summary` 존재 |
| D3 | 세금 ON vs OFF | D2 구성 ON/OFF | 생존율 ON ≤ OFF (인출세 부담만큼 악화 또는 동일) |
| D4 | 미실현차익 방향성 | D2에서 위탁 미실현차익 0 vs 2억 | 차익 2억 쪽 결과 악화(양도세↑) — combined 종료자산 또는 생존율 하락 |

**총 16건.** 우선순위: A1→D2(신규 배선 핵심)→A3(에러차단)→B1→C1→나머지.

## 6. 구현 구조

```
tests/e2e_multitax/
  helpers.js        # 공통: 브라우저 기동, 세금토글, 계좌 셋업(클릭), 종목검색·추가,
                    #       실행+API응답 캡처(waitForResponse /api/**), 스크린샷, ok()/결과집계
  a_calculator.js   # A1~A6
  b_backtest.js     # B1~B3
  c_retirement_sim.js # C1~C3
  d_retirement_wd.js  # D1~D4
  run_all.js        # 순차 실행 + 결과 md 생성
```

- 실행: `node tests/e2e_multitax/run_all.js [BASE_URL]` (기본 라이브)
- 산출물: `tests/e2e_multitax/results/YYYYMMDD_result.md`(케이스별 PASS/FAIL + API 필드 발췌)
  + 스크린샷 `results/shots/*.png` (FAIL 시 + 대표 화면)
- 케이스당 타임아웃 180s, 전체 ~30분 예상(시뮬 16회 × 큐 대기).

## 7. 리스크 / 알려진 함정

- **Celery 큐 대기**: 라이브 트래픽과 겹치면 지연 — 타임아웃은 넉넉히, 실패 시 1회 재시도.
- **A5 금종세 임계**: 458730 배당수익률·윈도우에 따라 8억으로 미달 가능 → 10억 1회 재시도,
  그래도 안 뜨면 "임계 미도달(정상)"로 기록(FAIL 아님).
- **동적 계좌카드 셀렉터**: 클래스/구조 변경에 취약 — helpers에 격리, 깨지면 한 곳만 수정.
- **세금 프로필 저장**: 로그인 의존이면 프로필 단계 스킵하고 기본 프로필로 진행 + 명시 기록.
- **라이브 = prod**: 절대 저장/삭제/로그인 액션 없음. 시뮬 실행만.
- 결과 불일치 발견 시 **즉시 수정 금지** — bugs.md 등록 + 오너 보고 먼저(기존 규칙).

## 8. 완료 기준

- 16건 전부 실행되어 PASS/FAIL/SKIP(사유) 판정 기록.
- FAIL = 배선버그 후보 → bugs.md 등록 + 재현 스크린샷.
- 전부 PASS면 roadmap **L7 실데이터 통합검증 = 완료** 처리 가능(브라우저 육안 잔여 해소).

_작성: Claude, 2026-06-10_
