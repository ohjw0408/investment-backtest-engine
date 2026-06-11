/** C·D 스위트만 재실행 (GAP-RET-KRDATA 수정 검증용). */
'use strict';
const H = require('./helpers');

(async () => {
  const t0 = Date.now();
  console.log(`다계좌 세금 E2E — C·D 재검, 대상: ${H.BASE}\n`);
  const { browser, page, consoleErrors, dialogs } = await H.newSession();
  const ctx = { page, consoleErrors, dialogs, H };
  try {
    await H.setupTaxProfile(page);
    for (const [name, mod] of [['C 은퇴 시뮬레이션', './c_retirement_sim'], ['D 인출기', './d_retirement_wd']]) {
      console.log(`── ${name} ──`);
      try { await require(mod)(ctx); } catch (e) { console.log(`스위트 중단(${name}): ${e.message}`); }
      console.log('');
    }
  } finally {
    await browser.close();
  }
  const cnt = s => H.results.filter(r => r.status === s).length;
  console.log(`\n총 ${H.results.length}건: ${cnt('PASS')} PASS / ${cnt('FAIL')} FAIL / ${cnt('SKIP')} SKIP (${Math.round((Date.now() - t0) / 60000)}분, 콘솔에러 ${consoleErrors.length}건)`);
  process.exit(cnt('FAIL') > 0 ? 1 : 0);
})().catch(e => { console.error('치명 오류:', e); process.exit(2); });
