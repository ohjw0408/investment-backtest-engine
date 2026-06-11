/**
 * 다계좌 세금 E2E 검증 16건 — 순차 실행 + 결과 md 생성.
 * 실행: node tests/e2e_multitax/run_all.js [BASE_URL]   (기본: 라이브)
 * 계획: 다계좌세금_E2E검증_plan.md — 라이브 서버 대상, 읽기성 시뮬만(저장/로그인 없음).
 */
'use strict';
const H = require('./helpers');

const SUITES = [
  ['A 투자계산기', './a_calculator'],
  ['B 포트폴리오 분석', './b_backtest'],
  ['C 은퇴 시뮬레이션', './c_retirement_sim'],
  ['D 인출기', './d_retirement_wd'],
];

(async () => {
  const t0 = Date.now();
  console.log(`다계좌 세금 E2E 16건 — 대상: ${H.BASE}\n`);

  const { browser, page, consoleErrors, dialogs } = await H.newSession();
  const ctx = { page, consoleErrors, dialogs, H };

  try {
    await H.setupTaxProfile(page);
    console.log('세금 프로필 설정 완료: 나이40 · 연소득5,000만 · ISA일반형 (비로그인 → localStorage, 서버 쓰기 없음)\n');

    for (const [name, mod] of SUITES) {
      console.log(`── ${name} ──`);
      try {
        await require(mod)(ctx);
      } catch (e) {
        console.log(`스위트 중단(${name}): ${e.message}`);
      }
      console.log('');
    }
  } finally {
    await browser.close();
  }

  const file = H.writeResultsMd(consoleErrors);
  const cnt = s => H.results.filter(r => r.status === s).length;
  const mins = Math.round((Date.now() - t0) / 60000);
  console.log(`\n총 ${H.results.length}건: ${cnt('PASS')} PASS / ${cnt('FAIL')} FAIL / ${cnt('SKIP')} SKIP (${mins}분, 콘솔에러 ${consoleErrors.length}건)`);
  console.log(`결과: ${file}`);
  process.exit(cnt('FAIL') > 0 ? 1 : 0);
})().catch(e => {
  console.error('치명 오류:', e);
  process.exit(2);
});
