/**
 * D4 fast-follow ① 계좌별 거래수수료 라이브 probe (2026-06-13).
 * 흐름: 세금 ON + 2계좌 + 거래수수료 opt-in → 카드별 #accountFeeRate{0,1} 노출 →
 *       계좌마다 다른 율 입력 → 실행 → 총 지불 수수료 배너(>0).
 * 검증: ① 카드별 수수료 입력 렌더(2개) ② 다른 율로 멀티 실행 → total_fees>0 ③ 콘솔에러 0.
 * 실행: node tests/e2e_multitax/probe_fee_percard_live.js [BASE_URL]
 */
'use strict';
const H = require('./helpers');

const FEE_BANNER = '#mmFeeSummary';

(async () => {
  const { browser, page, consoleErrors } = await H.newSession();
  let pass = 0, fail = 0;
  const ok = (id, cond, note) => { cond ? pass++ : fail++; H.record(id, note, cond ? 'PASS' : 'FAIL'); };
  try {
    // 세금 프로필(localStorage — 라이브 서버 쓰기 없음)
    await H.setupTaxProfile(page);

    // 계산기: 상단 069500 · 2계좌(계좌1 위탁 / 계좌2 위탁 360750)
    await H.gotoPage(page, 'calc');
    await H.addTopTicker(page, 'calc', '069500');
    await page.fill('#initialCapital', '10000000');
    await page.fill('#monthlyContrib', '1000000');
    await H.setRange(page, '#yearsSlider', 12);
    await H.setTax(page, 'calc', true);
    await H.setAccountType(page, 0, '위탁');
    await H.addAccount(page);
    await H.setAccountType(page, 1, '위탁');
    await H.setAccountAmount(page, 1, '초기 투자금', 5000000);
    await H.addAccountTicker(page, 1, '360750');

    // 거래수수료 opt-in → 카드별 입력 노출(toggleFeePanel → renderTaxAccounts)
    await page.check('#feeEnabledChk');
    await H.sleep(300);
    const r0 = await page.isVisible('#accountFeeRate0');
    const r1 = await page.isVisible('#accountFeeRate1');
    ok('FEE-PC-RENDER', r0 && r1, `카드별 수수료 입력 렌더(계좌1=${r0}, 계좌2=${r1})`);

    // 계좌마다 다른 율: 계좌1 0.015% / 계좌2 0.5%(차등 반영 확인)
    await page.fill('#accountFeeRate0', '0.015');
    await page.fill('#accountFeeRate1', '0.5');
    await H.shot(page, 'fee_percard_input');

    // 실행 → 총 지불 수수료 배너 > 0
    await page.click('#runBtn');
    await page.locator(FEE_BANNER).waitFor({ state: 'visible', timeout: 150000 });
    const txt = await page.locator(FEE_BANNER).textContent();
    const won = Number((txt || '').replace(/[^0-9]/g, '') || 0);
    ok('FEE-PC-RUN', won > 0, `멀티계좌 차등율 실행 → 총 지불 수수료 ₩${won.toLocaleString()} (>0)`);
    await H.shot(page, 'fee_percard_result');

    ok('ERR', consoleErrors.length === 0, `콘솔/페이지 에러 0 (실제 ${consoleErrors.length})`);
  } catch (e) {
    fail++; H.record('ERR', '예외 — ' + e.message, 'FAIL');
    await H.shot(page, 'fee_percard_error');
  } finally {
    console.log(`\n==== ${pass} PASS / ${fail} FAIL ====`);
    if (consoleErrors.length) console.log('consoleErrors:', consoleErrors.slice(0, 8));
    await browser.close();
    process.exit(fail ? 1 : 0);
  }
})();
