/**
 * 홈 동적 위젯 라이브(Playwright) — PC 표 + 모바일 캐러셀 렌더(비로그인 기본값).
 * 실행: node tests/test_home_widgets_live.js [BASE_URL]
 */
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'https://moneymilestone.duckdns.org';

let pass = 0, fail = 0;
const ok = (n, c) => { if (c) { pass++; console.log('PASS  ' + n); } else { fail++; console.log('FAIL  ' + n); } };

(async () => {
  const browser = await chromium.launch();

  // ── PC (1280) ──
  const pc = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errsPc = [];
  pc.on('pageerror', e => errsPc.push(String(e)));
  pc.on('console', m => { if (m.type() === 'error') errsPc.push(m.text()); });
  await pc.goto(BASE + '/', { waitUntil: 'networkidle' });
  await pc.waitForSelector('.widget-table .widget-row', { timeout: 15000 }).catch(() => {});

  ok('PC: 위젯 카드 존재', (await pc.locator('#widgetCard').count()) === 1);
  const rows = await pc.locator('.widget-table .widget-row').count();
  ok('PC: 표 행 = 기본 6종', rows === 6);
  ok('PC: ^GSPC 행 존재', (await pc.locator('.widget-row[data-code="^GSPC"]').count()) === 1);
  const firstVal = await pc.locator('.widget-table .wt-val').first().textContent();
  ok('PC: 첫 행 값 채워짐(— 아님)', firstVal && firstVal.trim() !== '—');
  ok('PC: 콘솔 에러 0', errsPc.length === 0);
  if (errsPc.length) console.log('  PC ERRORS:', errsPc.slice(0, 3));

  // ── 모바일 (390) ──
  const mo = await browser.newPage({ viewport: { width: 390, height: 800 } });
  const errsMo = [];
  mo.on('pageerror', e => errsMo.push(String(e)));
  mo.on('console', m => { if (m.type() === 'error') errsMo.push(m.text()); });
  await mo.goto(BASE + '/', { waitUntil: 'networkidle' });
  await mo.waitForSelector('.widget-carousel .market-item', { timeout: 15000 }).catch(() => {});

  ok('모바일: 캐러셀 존재', (await mo.locator('.widget-carousel').count()) === 1);
  ok('모바일: 종목 아이템 렌더', (await mo.locator('.widget-carousel .market-item').count()) >= 1);
  ok('모바일: 도트 인디케이터 존재', (await mo.locator('.widget-dots .wdot').count()) >= 1);
  const carVisible = await mo.evaluate(() => {
    const c = document.querySelector('.widget-carousel');
    return c && getComputedStyle(c).overflowX === 'auto';
  });
  ok('모바일: 캐러셀 가로 스크롤 가능', carVisible);
  ok('모바일: 콘솔 에러 0', errsMo.length === 0);
  if (errsMo.length) console.log('  MO ERRORS:', errsMo.slice(0, 3));

  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
})();
