/**
 * 납입 한도 soft 경고 라이브 probe — 백테·은퇴·배당 3탭 (2026-06-13).
 * 각 탭: ISA 단일 초기 3,000만(>2,000만 한도) → limit_confirm 모달 →
 *   예 → override 재요청 → 결과 하단 경고 배너. (모달/스킵/아니오 전체 동작은 계산기 probe서 입증 — 공용 MMLimit)
 * 실행: node tests/e2e_multitax/probe_limit_soft_live3.js [BASE_URL]
 */
'use strict';
const H = require('./helpers');

const YES = 'button:has-text("예, 진행합니다")';

async function setAcct0ISA(page) {
  const card = page.locator('#taxAccountList > div').first();
  await card.locator('select').first().selectOption('ISA');
}
async function waitModal(page, ms = 90000) {
  await page.locator(YES).waitFor({ state: 'visible', timeout: ms });
}
async function waitBanner(page, container, ms = 170000) {
  const sel = `#${container} #mmLimitWarn:has-text("납입 한도 초과 시뮬레이션")`;
  await page.locator(sel).waitFor({ state: 'visible', timeout: ms });
}
async function violationText(page) {
  return (await page.locator(YES).locator('xpath=ancestor::div[1]/preceding-sibling::div').allTextContents().catch(() => []))
    .join(' ');
}

async function armBt(page) {
  await H.gotoPage(page, 'bt');
  await H.addTopTicker(page, 'bt', '069500');
  await H.setTax(page, 'bt', true);
  await H.sleep(400);
  await setAcct0ISA(page);
  await page.fill('#btSeed', '30000000');
  await page.fill('#btMonthly', '0');
  await page.fill('#btStartDate', '2015-01-01');
}
async function armRet(page) {
  await H.gotoPage(page, 'ret'); // 기본 = 은퇴 시뮬(적립) 모드
  await H.addTopTicker(page, 'ret', '069500');
  await H.setTax(page, 'ret', true);
  await H.sleep(400);
  await setAcct0ISA(page);
  await page.fill('#simSeed', '30000000');
  await page.fill('#simMonthly', '0');
}
async function armDt(page) {
  await page.goto(H.BASE + '/dividend-target', { waitUntil: 'networkidle' });
  await page.fill('#dtSearchInput', '069500');
  await page.locator('#dtSearchDropdown .ticker-drop-item:has(.ticker-drop-code:text-is("069500"))').first().click({ timeout: 15000 });
  await page.click('#dtTaxToggle');
  await H.sleep(500);
  await setAcct0ISA(page);
  await page.fill('#dtSeedVal', '30000000');
}

const TABS = [
  { id: 'BT', name: '백테스트', arm: armBt, run: '#btRunBtn', container: 'btResultContent' },
  { id: 'RET', name: '은퇴 시뮬', arm: armRet, run: '#retRunBtn', container: 'retResultContent' },
  { id: 'DT', name: '배당 계산기', arm: armDt, run: '#dtRunBtn', container: 'dtResultContent' },
];

(async () => {
  const { browser, page, consoleErrors } = await H.newSession();
  let pass = 0, fail = 0;
  try {
    await H.setupTaxProfile(page);
    for (const t of TABS) {
      try {
        await page.evaluate(() => { try { localStorage.removeItem('mm_limit_skip_date'); } catch (e) {} });
        await t.arm(page);
        await page.click(t.run);
        await waitModal(page);
        const vt = await violationText(page);
        const hasViol = /2,000만/.test(vt) || /한도/.test(vt);
        await H.shot(page, `limit3_${t.id}_modal`);
        await page.click(YES);
        await waitBanner(page, t.container);
        await H.shot(page, `limit3_${t.id}_banner`);
        pass++; H.record(t.id, `${t.name}: 모달 위반문구→예→override→하단 배너`, 'PASS', hasViol ? '' : '위반문구 약함');
      } catch (e) {
        fail++; H.record(t.id, `${t.name} — ${e.message}`, 'FAIL');
        await H.shot(page, `limit3_${t.id}_fail`);
      }
    }
    H.record('ERR', `콘솔/페이지 에러 ${consoleErrors.length}`, consoleErrors.length === 0 ? 'PASS' : 'FAIL');
    consoleErrors.length ? fail++ : pass++;
  } finally {
    console.log(`\n==== ${pass} PASS / ${fail} FAIL ====`);
    if (consoleErrors.length) console.log('consoleErrors:', consoleErrors.slice(0, 10));
    await browser.close();
    process.exit(fail ? 1 : 0);
  }
})();
