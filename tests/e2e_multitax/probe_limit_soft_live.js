/**
 * 납입 한도 soft 경고 라이브 probe (2026-06-13) — 계산기 탭 풀 동작.
 * 흐름: ISA 단일 초기 3,000만(>2,000만 한도) → limit_confirm 모달 →
 *   ① 예 → override 재요청 → 결과 하단 배너
 *   ② 아니오 → 모달 닫힘·결과 없음
 *   ③ 오늘 하루 묻지 않기 체크+예 → 이후 재실행은 모달 없이 바로 배너
 * 실행: node tests/e2e_multitax/probe_limit_soft_live.js [BASE_URL]
 */
'use strict';
const H = require('./helpers');
const { chromium } = require('playwright');

const BASE = process.argv[2] || H.BASE;
const sleep = H.sleep;

const YES = 'button:has-text("예, 진행합니다")';
const NO = 'button:has-text("아니오")';
const MODAL_TITLE = 'text=⚠️ 납입 한도 초과';
const BANNER = '#mmLimitWarn';

async function arm(page) {
  // 계산기: 종목 추가 + 세금 ON + 계좌0 ISA + 초기 3천만(한도초과) + 월0
  await H.gotoPage(page, 'calc');
  await H.addTopTicker(page, 'calc', '069500');
  await H.setTax(page, 'calc', true);
  await sleep(400);
  await H.setAccountType(page, 0, 'ISA');
  await page.fill('#initialCapital', '30000000');
  await page.fill('#monthlyContrib', '0');
}

async function clickRun(page) { await page.click('#runBtn'); }

async function waitModal(page, ms = 70000) {
  await page.locator(YES).waitFor({ state: 'visible', timeout: ms });
}

async function waitBanner(page, ms = 150000) {
  await page.locator(BANNER).waitFor({ state: 'attached', timeout: ms });
  await page.locator(`${BANNER}:has-text("납입 한도 초과 시뮬레이션")`).waitFor({ state: 'visible', timeout: ms });
}

(async () => {
  const { browser, page, consoleErrors } = await H.newSession();
  let pass = 0, fail = 0;
  const ok = (id, cond, note) => { if (cond) { pass++; H.record(id, note, 'PASS'); } else { fail++; H.record(id, note, 'FAIL'); } };
  try {
    await H.setupTaxProfile(page);
    await page.evaluate(() => { try { localStorage.removeItem('mm_limit_skip_date'); } catch (e) {} });

    // ── ① 예 → override → 배너 ──────────────────────────
    await arm(page);
    await clickRun(page);
    await waitModal(page);
    const vtext = (await page.locator('div').filter({ hasText: '2,000만원' }).first().textContent().catch(() => '')) || '';
    ok('L1', /2,000만원|2,000만/.test(vtext), '모달 위반문구 표시(ISA 2,000만 한도)');
    await H.shot(page, 'limit_01_modal');
    await page.click(YES);
    await waitBanner(page);
    const bannerTxt = await page.locator(BANNER).textContent();
    ok('L2', /한도 초과/.test(bannerTxt), '예→override→결과 하단 경고 배너');
    await H.shot(page, 'limit_02_banner');

    // ── ② 아니오 → 모달 닫힘·결과 없음 ──────────────────
    await arm(page);
    await clickRun(page);
    await waitModal(page);
    await page.click(NO);
    await sleep(800);
    const modalGone = (await page.locator(YES).count()) === 0;
    ok('L3', modalGone, '아니오→모달 닫힘(진행 안 함)');

    // ── ③ 오늘 하루 묻지 않기 → 이후 모달 생략 ──────────
    await arm(page);
    await clickRun(page);
    await waitModal(page);
    await page.locator('input[type="checkbox"]').last().check();
    await page.click(YES);
    await waitBanner(page);
    const skipSet = await page.evaluate(() => { try { return !!localStorage.getItem('mm_limit_skip_date'); } catch (e) { return false; } });
    ok('L4', skipSet, '"오늘 하루 묻지 않기" 체크+예 → localStorage 스킵 기록');

    // 재실행: 모달 없이 바로 배너(override 자동)
    await arm(page);
    await clickRun(page);
    let modalShown = false;
    try { await page.locator(YES).waitFor({ state: 'visible', timeout: 6000 }); modalShown = true; } catch (e) {}
    await waitBanner(page);
    ok('L5', !modalShown, '스킵 당일 재실행 → 모달 생략·배너 직행');
    await H.shot(page, 'limit_03_skipday');

    ok('L6', consoleErrors.length === 0, `콘솔/페이지 에러 0 (실제 ${consoleErrors.length})`);
  } catch (e) {
    fail++; H.record('ERR', '예외 — ' + e.message, 'FAIL');
    await H.shot(page, 'limit_error');
  } finally {
    console.log(`\n==== ${pass} PASS / ${fail} FAIL ====`);
    if (consoleErrors.length) console.log('consoleErrors:', consoleErrors.slice(0, 10));
    await browser.close();
    process.exit(fail ? 1 : 0);
  }
})();
