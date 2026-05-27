# Log

연대순 기록. Append-only. 삭제하지 말 것.

---

## [2026-05-28] plan | ETF_BACKFILL_ARCHITECTURE_PLAN 단일종목 레버리지/규제완화 대응 추가

- `### Leveraged / Inverse ETFs` 섹션 확장: 광지수/단일종목/인버스 별 policy + 등급 명시
- 신규 섹션 `### Regulatory Expansion ETFs (2025~ Korean Market)` 추가
  - 트리거: 신규 ETF → `etf_proxy_map` 조회 → 없으면 `needs_review` (코드 수정 불필요)
  - 단일종목 레버리지(삼성/SK하이닉스/TSLA 2X 등), 테마, 커버드콜, 버퍼형 등 분류표
  - 핵심 원칙: 새 ETF 추가 = `etf_proxy_map` 행 삽입, `backfill_engine.py` 수정 금지
- `Priority ETF Families`에 Korean Single-Stock Leveraged/Inverse 패밀리 추가

---

## [2026-05-27] ingest | 창업계획서.pdf + 5개 개발 계획서

**소스:**
- `창업계획서.pdf` — 사업계획서 (대학원생 Tech-up 창업동아리)
- `PROJECT_MASTER_ROADMAP.md` — 전체 개발 로드맵 조율 문서
- `PHASE4_PLAN.md` — 제품 기능 로드맵 (5개 그룹: 검색/내자산/홈/계산기/인프라)
- `세금에서시작된완전리팩토링계획.plan.md` — 세금·시뮬 정확도 리팩토링
- `ETF_BACKFILL_ARCHITECTURE_PLAN.md` — ETF 데이터 백필 아키텍처
- `SYNTHETIC_DATA_INTEGRATION_PLAN.md` — 합성 데이터 통합 계획

**생성된 페이지:**
- `wiki/overview.md`
- `wiki/product/features.md`
- `wiki/product/dev-status.md`
- `wiki/business/competitors.md`
- `wiki/business/target-users.md`
- `wiki/business/revenue-model.md`
- `wiki/index.md`
- `wiki/log.md` (이 파일)

**핵심 인사이트:**
- 현재 최대 블로커: SCHD vs TIGER 미국배당다우존스 데이터 불일치 → ETF 백필 데이터 품질 문제
- 대부분 계산기 기능은 완료됨. 세금 정확도 + 데이터 품질이 현재 핵심 과제
- 사업계획서 기준 런칭 목표: 2026년 11월 앱스토어 배포

---

## [2026-05-28] feature | US ETF 리스트 162개 → 4593개 확장

- ETFdb.com API로 전체 수집 (4595개 중 4593개, 중복 2개 제외)
- symbol_master.db 업데이트 (전체 심볼 15,008개)
- MSTY(YieldMax), JEPI, JEPQ 등 신규 인기 ETF 포함
- 카테고리: US Equity / Fixed Income / Commodity / Real Estate / Multi-Asset 등
- 커밋: ec788da

---

## [2026-05-27] feature | 홈화면 가격불러오기 안정성 및 정시성 추가

- market_quote_service: Redis SETNX 락으로 thundering herd 방지 (캐시 만료 시 yfinance 중복 호출 차단)
- tasks.py: refresh_krx_gold Celery Beat 태스크 추가
- celery_app.py: beat_schedule 추가 (평일 16:30 KST = 07:30 UTC 자동 실행)
- deploy/domino-celery-beat.service: systemd Beat 서비스 파일 repo에 추가
- deploy.yml: 배포 시 Beat 서비스 자동 등록/재시작 (이후 수동 SSH 불필요)
- KRX 금현물은 장 마감 후에만 당일 데이터 생성됨 (API 특성)

---

## [2026-05-28] feature | Track A Step 4~8 완료

- Step 4: KOSDAQ150→KQ150 매핑, KQ150 6284행(KODEX229200←^KQ11) index_master.db 저장 (40696f5)
- Step 5: index_loader_develop.py _fetch_fred() def 선언 누락 1줄 수정 (e1a4d6e)
- Step 6: PriceLoader 백필 실패 시 _backfilled_codes에 추가 안 하도록 수정, _backfill_skip_codes 분리 (a761750)
- Step 7: backfill_engine 인덱스 100행 미만 시 거부 (index_insufficient) (e33eeeb)
- Step 8: dividend_simulator._calc_div_stats() yield/freq 계산 시 현재 미완료 연도 제외 (ec56455)

---

## [2026-05-28] feature | Track A Step 2-3: DJUSDIV_PROXY 프록시 체인 구축

- 문제: DJUSDIV100 index_master.db에 1행뿐 (2026-03-18) → DJ 배당 ETF 백필 불가
- ^DJDVP (Yahoo Finance) 역사 데이터 미지원 확인
- 해결: SCHD(2011~) <- SDY(2005~) <- DVY(2003~) <- ^GSPC(1928~) adj close 체인 구성
- SCHD/SDY/DVY 상관계수: SDY 0.948, DVY 0.937 (SCHD 기준)
- scripts/build_djdiv_proxy.py 생성, DJUSDIV_PROXY 24,714행 index_master.db 저장
- backfill_engine.py: DJ_US_DIVIDEND -> DJUSDIV_PROXY, _NO_DIVIDEND_INDICES 추가
- us_etf_list.csv: SCHD->Dividend, VIG/DVY/SDY/etc->Dividend Growth, JEPI/JEPQ->Covered Call
- 458730/446720/402970 재백필 성공, 접합점 연속성 확인
- Step 9 선행 검증: price_return_mean 4종(SCHD/TIGER/ACE/SOL) 9.61~9.63% 수렴 확인
- 커밋: 7b1dc6f

---

## [2026-05-27] bugfix | 배당금 계산기 세션 메모 wiki 갱신
이 세션의 기억을 바탕으로 wiki를 갱신함. 확실히 확인된 내용만 반영:
- 목표 배당금 계산기 9.4억 폭증 버그 수정 기록.
- 한국 ETF 가격 로더에서 pykrx fallback 제거 및 yfinance 사용 결정 기록.
- 월납입금 자동 역산 5년 역전 버그 수정 기록.
- KODEX 미국배당다우존스 그래프 개형 볼록함 수정 기록.
- 기간 자동 역산 범위 1~70년 확장 기록.
- 은퇴 시뮬레이션 유사 문제는 확인 필요 항목으로만 기록.

---

## [2026-05-28] decision | Codex ETF 백필 자동화 검토 반영

- `ETF_BACKFILL_ARCHITECTURE_PLAN.md`에 `Codex Review Notes: Automation Risks and Practical Rollout` 섹션 추가.
- 판단: 프록시 매핑 자동화는 완전 자동 정답 선택기가 아니라, 자동 후보 제안 + 검증된 좁은 패밀리만 자동 승인 + 나머지는 `needs_review`로 멈추는 운영 시스템이어야 함.
- 주요 우려:
  - `underlying_symbol`이 비어 있거나 불완전하면 단일종목/레버리지 자동화의 입력으로 사용할 수 없음.
  - 이름/카테고리 기반 추론은 triage에는 유용하지만 최종 프록시 근거로는 위험함.
  - 커버드콜, 테마/액티브, missing-underlying 레버리지 상품은 명시적 reject 정책이 먼저 필요함.
  - provenance 없이 ETF 타입을 넓히면 잘못 생성된 장기 히스토리를 audit/delete/regenerate 하기 어려움.
- 현실적 단계:
  1. diagnostics
  2. provenance tables
  3. minimal `etf_proxy_map`
  4. `BackfillEngine` reads `etf_proxy_map` first
  5. explicit reject policies
  6. reviewed-underlying daily-reset leverage
  7. selected-family holdings/regression
  8. bond/covered-call models later
- 서명: Codex가 이 부분을 검토하고 수정함.
