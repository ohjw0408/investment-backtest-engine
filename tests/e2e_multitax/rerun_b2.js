/** B2 단독 재실행 — 본 런에서 테스트 설계 결함(불공정 비교)으로 FAIL → 단일계좌 대조로 수정 후 재검. */
'use strict';
const H = require('./helpers');
const { num, fmtMan } = H;

(async () => {
  const { browser, page, consoleErrors, dialogs } = await H.newSession();
  try {
    await H.setupTaxProfile(page);

    await H.gotoPage(page, 'bt');
    await H.addTopTicker(page, 'bt', '458730');
    await page.fill('#btSeed', '10000000');
    await page.fill('#btMonthly', '0');
    await page.fill('#btStartDate', '2015-01-01');
    await H.setTax(page, 'bt', true);               // 계좌1 = 위탁(기본) 단일

    const resOn = await H.withRetry(() => H.runSim(page, 'bt', { dialogs }), 'B2-ON');
    if (!resOn.ok) throw new Error('ON 시뮬 실패: ' + resOn.error);
    const onEnd = ((resOn.result || {}).metrics || {}).end_value;

    await H.setTax(page, 'bt', false);
    const resOff = await H.withRetry(() => H.runSim(page, 'bt', { dialogs }), 'B2-OFF');
    if (!resOff.ok) throw new Error('OFF 시뮬 실패: ' + resOff.error);
    const offEnd = ((resOff.result || {}).metrics || {}).end_value;

    const pass = num(onEnd) && num(offEnd) && onEnd <= offEnd;
    console.log(`${pass ? 'PASS' : 'FAIL'} B2(재검·단일계좌 대조)  ON=${fmtMan(onEnd)} OFF=${fmtMan(offEnd)}`);
    console.log(`콘솔에러 ${consoleErrors.length}건`);
    process.exit(pass ? 0 : 1);
  } finally {
    await browser.close();
  }
})().catch(e => { console.error('오류:', e.message); process.exit(2); });
