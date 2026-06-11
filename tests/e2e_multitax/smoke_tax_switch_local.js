const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const page = await browser.newPage();
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

  await page.goto('http://127.0.0.1:5000/tax-switch', { waitUntil: 'networkidle' });
  const checks = {};
  checks.title = await page.title();
  checks.navLink = await page.locator('.nav-link', { hasText: 'ISA 전환' }).count();
  checks.runBtn = await page.locator('#tsRunBtn').count();
  checks.inputs = await page.locator('#tsCurrentValue, #tsCostBasis, #tsYears').count();
  checks.profileInfo = (await page.locator('#tsProfileInfo').textContent()).slice(0, 40);

  // 종목 검색 동작
  await page.fill('#tsSearchInput', '미국배당');
  await page.waitForTimeout(1200);
  checks.dropdownItems = await page.locator('#tsDropdown .ts-dd-item[data-code]').count();
  if (checks.dropdownItems > 0) {
    await page.locator('#tsDropdown .ts-dd-item[data-code]').first().click();
    checks.tickerRows = await page.locator('.ts-ticker-row').count();
  }
  await page.screenshot({ path: 'tests/e2e_multitax/results/shots/tax_switch_local_light.png', fullPage: true });

  // 다크모드
  await page.evaluate(() => { localStorage.setItem('mm-theme', 'dark'); });
  await page.reload({ waitUntil: 'networkidle' });
  checks.darkApplied = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
  await page.screenshot({ path: 'tests/e2e_multitax/results/shots/tax_switch_local_dark.png', fullPage: true });

  // 모바일 뷰포트
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: 'networkidle' });
  checks.hamburgerVisible = await page.locator('#navHamburger').isVisible();
  await page.screenshot({ path: 'tests/e2e_multitax/results/shots/tax_switch_local_mobile.png', fullPage: true });

  console.log(JSON.stringify({ checks, errors }, null, 2));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
