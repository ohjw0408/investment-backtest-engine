/**
 * 절세액 P3 라이브 probe — 인출기(wd) 멀티계좌 절세 패널 (위탁3억+미실현1억 / 연금2억).
 * 실행: node tests/e2e_multitax/probe_wd_savings_live.js [BASE_URL]
 */
'use strict';
const path = require('path');
const H = require('./helpers');

(async () => {
  const ctx = await H.newSession();
  const { page, dialogs } = ctx;
  const out = { checks: {}, api: null };
  try {
    await H.setupTaxProfile(page);
    page.on('response', async (res) => {
      if (res.url().includes('/api/task/') && res.status() === 200) {
        try {
          const d = await res.json();
          if (d.status === 'SUCCESS' && d.result && d.result.savings !== undefined) out.api = d.result;
        } catch (_) {}
      }
    });

    await H.gotoPage(page, 'ret');
    await H.addTopTicker(page, 'ret', '458730');
    await page.click('#tabRetWd');
    await H.setTax(page, 'ret', true);
    await H.addAccount(page);
    await H.setAccountType(page, 1, '연금저축');
    await page.fill('#wdSeed', '300000000');
    await H.setAccountAmount(page, 0, '미실현 차익', 100000000);
    await H.setAccountAmount(page, 1, '시작 목돈', 200000000);
    await H.addAccountTicker(page, 1, '360750');
    await page.fill('#wdWithdraw', '2000000');
    await H.setRange(page, '#wdYearsSlider', 30);
    await page.fill('#wdPensionStartAge', '65');

    const res = await H.withRetry(() => H.runSim(page, 'ret', { dialogs }), 'WD-SAVE');

    const summaryHtml = await page.locator('#multiAccountSummary').innerHTML();
    out.checks.panelVisible = summaryHtml.includes('세금 절감 효과');
    out.checks.wdNote = summaryHtml.includes('연금소득세 포함');
    const sav = (out.api || res || {}).savings || null;
    out.checks.apiSavings = !!sav;
    if (sav) {
      const brk = (sav.accounts || []).find(a => a.type === '위탁') || {};
      out.checks.brokerageInvariantZero = (brk.tax_saving || 0) === 0;
      out.checks.combinedSaving = sav.combined ? sav.combined.tax_saving : null;
      out.checks.combinedIsSum = sav.combined
        ? Math.abs(sav.combined.tax_saving
            - (sav.accounts || []).reduce((s, a) => s + (a.tax_saving || 0), 0)) <= 2
        : false;
    }
    await H.shot(page, 'wd_savings_live');
    console.log(JSON.stringify(out.checks, null, 2));
    const pass = out.checks.panelVisible && out.checks.wdNote && out.checks.apiSavings
      && out.checks.brokerageInvariantZero && out.checks.combinedIsSum;
    console.log(pass ? 'RESULT: PASS' : 'RESULT: FAIL');
    process.exitCode = pass ? 0 : 1;
  } catch (e) {
    console.error('FATAL', e);
    process.exitCode = 1;
  } finally {
    await ctx.browser.close();
  }
})();
