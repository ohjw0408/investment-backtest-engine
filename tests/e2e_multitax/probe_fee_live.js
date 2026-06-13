/**
 * D4 거래수수료 라이브 probe (2026-06-13) — 계산기·백테 탭레벨 수수료.
 * 흐름: 거래수수료 opt-in 체크 → 수수료율(기본 0.015%) → 실행 → 결과 하단 "총 지불 거래수수료 ₩X" 배너(>0).
 * 실행: node tests/e2e_multitax/probe_fee_live.js [BASE_URL]
 */
'use strict';
const H = require('./helpers');

const FEE_BANNER = '#mmFeeSummary';

async function enableFee(page) {
  await page.check('#feeEnabledChk');
  await H.sleep(200);
  await page.fill('#feeRateInput', '0.015');
}

async function feeWon(page) {
  const txt = await page.locator(FEE_BANNER).textContent();
  const m = txt.replace(/[^0-9]/g, '');
  return Number(m || 0);
}

(async () => {
  const { browser, page, consoleErrors } = await H.newSession();
  let pass = 0, fail = 0;
  const ok = (id, cond, note) => { cond ? pass++ : fail++; H.record(id, note, cond ? 'PASS' : 'FAIL'); };
  try {
    // ── 계산기 ─────────────────────────────────────────
    await H.gotoPage(page, 'calc');
    await H.addTopTicker(page, 'calc', '069500');
    await enableFee(page);
    await page.click('#runBtn');
    await page.locator(FEE_BANNER).waitFor({ state: 'visible', timeout: 150000 });
    const cWon = await feeWon(page);
    ok('FEE-CALC', cWon > 0, `계산기: 총 지불 수수료 배너 ₩${cWon.toLocaleString()} (>0)`);
    await H.shot(page, 'fee_calc');

    // ── 백테스트 ───────────────────────────────────────
    await H.gotoPage(page, 'bt');
    await H.addTopTicker(page, 'bt', '069500');
    await page.fill('#btStartDate', '2015-01-01');
    await enableFee(page);
    await page.click('#btRunBtn');
    await page.locator(FEE_BANNER).waitFor({ state: 'visible', timeout: 150000 });
    const bWon = await feeWon(page);
    ok('FEE-BT', bWon > 0, `백테: 총 지불 수수료 배너 ₩${bWon.toLocaleString()} (>0)`);
    await H.shot(page, 'fee_bt');

    ok('ERR', consoleErrors.length === 0, `콘솔/페이지 에러 0 (실제 ${consoleErrors.length})`);
  } catch (e) {
    fail++; H.record('ERR', '예외 — ' + e.message, 'FAIL');
    await H.shot(page, 'fee_error');
  } finally {
    console.log(`\n==== ${pass} PASS / ${fail} FAIL ====`);
    if (consoleErrors.length) console.log('consoleErrors:', consoleErrors.slice(0, 8));
    await browser.close();
    process.exit(fail ? 1 : 0);
  }
})();
