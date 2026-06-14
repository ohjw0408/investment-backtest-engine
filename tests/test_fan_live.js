/**
 * 미래 시나리오 부채꼴 라이브 실브라우저(Playwright) — 실 Chart.js + 슬라이더 onclick.
 * fake fan 주입 → 슬라이더 조정 → chartInstances 검사. 실 계산 없이 렌더만.
 * 실행: node tests/test_fan_live.js [BASE_URL]
 */
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'https://moneymilestone.duckdns.org';

let pass = 0, fail = 0;
const ok = (n, c) => { if (c) { pass++; console.log('PASS  ' + n); } else { fail++; console.log('FAIL  ' + n); } };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

  await page.goto(BASE + '/calculator', { waitUntil: 'networkidle' });

  ok('fanCard 존재', (await page.locator('#fanCard').count()) === 1);
  ok('renderFan 정의', await page.evaluate(() => typeof renderFan === 'function'));

  // 결과 컨테이너는 계산 전 display:none → 실조작 위해 조상 노출
  await page.evaluate(() => {
    let el = document.getElementById('fanCard');
    while (el) { if (el.style && el.style.display === 'none') el.style.display = ''; el = el.parentElement; }
  });

  // 카드 숨김 상태(계산 전) 해제 위해 직접 렌더
  const fanReady = await page.evaluate(() => {
    const bands = [];
    for (let i = 0; i < 99; i++) bands.push([100, 100 + i, 200 + 2 * i]);
    const FAN = { axis: [0, 1, 2], percentiles: Array.from({ length: 99 }, (_, i) => i + 1), bands, n: 42 };
    renderFan(FAN);
    return document.getElementById('fanCard').style.display !== 'none';
  });
  ok('renderFan 후 카드 표시', fanReady);

  const ds = () => page.evaluate(() => {
    const ch = chartInstances['fanChart'];
    return ch.data.datasets.map(d => d.data);
  });

  let d = await ds();
  ok('기본 p25/p75/p50 = bands[24]/[74]/[49]',
    JSON.stringify(d[0]) === JSON.stringify([100, 124, 248]) &&
    JSON.stringify(d[1]) === JSON.stringify([100, 174, 348]) &&
    JSON.stringify(d[2]) === JSON.stringify([100, 149, 298]));

  // 슬라이더 조정(실 oninput) — 하단 10
  await page.fill('#fanLo', '10');
  await page.dispatchEvent('#fanLo', 'input');
  d = await ds();
  ok('하단 p10 → bands[9]', JSON.stringify(d[0]) === JSON.stringify([100, 109, 218]));
  ok('하단 라벨 갱신', (await page.textContent('#fanLoVal')) === '10');

  ok('콘솔/페이지 에러 0', errs.length === 0);
  if (errs.length) console.log('  ERRORS:', errs.slice(0, 5));

  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
})();
