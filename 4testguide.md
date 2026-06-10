---
  수동 테스트 가이드 (T1~T4)

  T1. 합성 데이터 경고 배너 — 계산기

  1. /calculator 접속
  2. 상장 짧은 ETF 입력 + 가상 데이터 허용 체크 ON
  3. 실행
  4. 결과 상단에 노란 배너 뜨면 PASS
    - ⚠ 가상 데이터 포함 — XXXXXX: 날짜~날짜 (OOO행 추정)
    - 실측 충분한 ETF는 배너 숨김

  ---
  T2. 종합과세 경고 + 분할매도 패널 — 백테스트

  1. /backtest 접속
  2. 458730(TIGER 미국배당다우존스) 또는 SCHD 선택
  3. 세금 ON, 계좌 = 위탁, 초기자금 5억+, 기간 10~20년
  4. 실행
  5. 결과 하단에 주황 패널 뜨면 PASS
    - ⚠ 금융소득 종합과세 주의 / 미실현이익 OOO만원
    - 슬라이더 움직이면 절감액 숫자 실시간 변경

  ---
  T3. Provenance DB 기록 — 서버 터미널

  서버에서:
  python -c "
  import sqlite3
  conn = sqlite3.connect('data/price_cache/price_daily.db')
  tables = [t[0] for t in conn.execute(\"SELECT name FROM sqlite_master WHERE
  type='table'\").fetchall()]
  print('테이블:', tables)
  print('backfill_runs 있음:', 'backfill_runs' in tables)
  "
  backfill_runs, price_daily_source, corporate_action_source 세 개 다 있으면 PASS
 ---
  T3 대체 — 앱 내에서 확인

  방법 1: 백필 엔진 새로 돌리고 결과 확인

  앱에서 아직 백필 안 된 ETF 검색하면 내부적으로 백필이 트리거됨. 그 후 로그에서 확인.

  근데 이것도 서버 로그 봐야 해서 비슷한 문제.

  ---
  현실적인 대안: T3은 스킵하고 나머지 3개만 테스트

  T3(Provenance)는 사용자 화면에 아무것도 안 뜨는 백엔드 전용 기능임. 잘못돼도 앱이 터지거나
  숫자가 틀리는 게 아니라 그냥 DB에 기록이 없는 것뿐.

  실용적 우선순위:
  - T1, T2, T4 — 화면에서 바로 확인 가능, 틀리면 사용자가 바로 봄 → 반드시 테스트
  - T3 — 백엔드 추적 기능, 앱 동작에 영향 없음 → 나중에 서버 접속 가능할 때 확인

  T3은 일단 패스하고 T1/T2/T4만 테스트해줘.
  ---
  T4. ISA 잔여 사이클 수정 + 중도해지 체크박스 — 계산기

  1. /calculator 접속
  2. 세금 ON, 계좌 = ISA, 풍차돌리기 ON
  3. 시뮬 기간 = 5년 (3의 배수 아닌 값)
  4. 실행
  5. 결과 상단에 주황 배너 + 체크박스 뜨면 PASS
    - ⚠ ISA 시뮬 기간이 3의 배수가 아닙니다 — 마지막 2년을 만기 해지(9.9%)로 가정
    - 체크박스 ON → p50 숫자 감소 (세금 더 냄)
    - 체크박스 OFF → 원래 숫자 복귀
  6. 기간 6년으로 바꿔서 실행 → 배너 없으면 추가 PASS