/**
 * ISA 전환 계산기 라이브 E2E — 실브라우저 풀플로우 (검색→입력→실행→결과 렌더 검증)
 * 실행: node tests/e2e_multitax/live_tax_switch.js [BASE_URL]
 */
'use strict';
const { chromium } = require('playwright');
const path = require('path');

const BASE = process.argv[2] || 'https://moneymilestone.duckdns.org';
const SHOTS = path.join(__dirname, 'results', 'shots');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

  const out = { base: BASE, checks: {}, api: null };

  // API 응답 캡처
  page.on('response', async (res) => {
    if (res.url().includes('/api/task/') && res.status() === 200) {
      try {
        const data = await res.json();
        if (data.status === 'SUCCESS' && data.result && data.result.ok) out.api = data.result;
      } catch (_) {}
    }
  });

  await page.goto(BASE + '/tax-switch', { waitUntil: 'networkidle' });
  out.checks.pageLoaded = (await page.title()).includes('ISA 전환');

  // 종목 검색 → 458730 추가
  await page.fill('#tsSearchInput', '458730');
  await page.waitForSelector('#tsDropdown .ts-dd-item[data-code]', { timeout: 10000 });
  await page.locator('#tsDropdown .ts-dd-item[data-code]').first().click();
  out.checks.tickerAdded = (await page.locator('.ts-ticker-row').count()) === 1;

  // 입력: 평가액 5천만 / 취득가 3천만 / 5년
  await page.fill('#tsCurrentValue', '50000000');
  await page.fill('#tsCostBasis', '30000000');
  await page.fill('#tsYears', '5');

  // 실행 → 결과 대기 (최대 5분)
  await page.click('#tsRunBtn');
  await page.waitForSelector('#tsResults', { state: 'visible', timeout: 300000 });

  out.checks.verdict = await page.locator('#tsVerdictHeadline').textContent();
  out.checks.aEnd = await page.locator('#tsAEnd').textContent();
  out.checks.bEnd = await page.locator('#tsBEnd').textContent();
  out.checks.diff = await page.locator('#tsDiff').textContent();
  out.checks.switchTax = await page.locator('#tsSwitchTax').textContent();
  out.checks.breakeven = await page.locator('#tsBreakeven').textContent();
  out.checks.scheduleRows = await page.locator('#tsScheduleTable tr').count();
  out.checks.chartRendered = await page.evaluate(() => {
    const c = document.getElementById('tsChart');
    return !!(c && c.width > 0 && c.height > 0);
  });
  await page.screenshot({ path: path.join(SHOTS, 'tax_switch_live_result.png'), fullPage: true });

  // API 불변식: cases_count>0, a/b p50>0, 입력 에코 일치
  if (out.api) {
    out.checks.apiCases = out.api.cases_count;
    out.checks.apiInvariant =
      out.api.cases_count > 0 &&
      out.api.a.p50 > 0 && out.api.b.p50 > 0 &&
      out.api.inputs.current_value === 50000000 &&
      out.api.inputs.cost_basis === 30000000 &&
      Math.abs((out.api.b.p50 - out.api.a.p50) - out.api.diff.p50) < 1e6;
  }

  // 다크모드 결과 화면
  await page.evaluate(() => localStorage.setItem('mm-theme', 'dark'));
  await page.reload({ waitUntil: 'networkidle' });
  await page.screenshot({ path: path.join(SHOTS, 'tax_switch_live_dark.png') });

  out.errors = errors;
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
  const pass = out.checks.pageLoaded && out.checks.tickerAdded && out.checks.chartRendered
    && out.checks.apiInvariant && errors.length === 0;
  console.log(pass ? 'RESULT: PASS' : 'RESULT: FAIL');
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error('FATAL', e); process.exit(1); });
