/**
 * 리스크-리턴 도표 실브라우저 검증 (로컬 전용 — 로그인 세션 필요, 실서버+실DB 산출).
 * 실행: node tests/test_risk_return_browser.js <sessionCookie> [baseUrl]
 */
const { chromium } = require('playwright');

const COOKIE = process.argv[2];
const BASE = process.argv[3] || 'http://127.0.0.1:5000';
if (!COOKIE) { console.error('usage: node test_risk_return_browser.js <sessionCookie>'); process.exit(2); }

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}

(async () => {
  const browser = await chromium.launch();

  // ── 1. 비로그인 게이팅 ──
  {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    await p.goto(BASE + '/risk-return', { waitUntil: 'domcontentloaded' });
    ok('비로그인 게이팅', !!(await p.$('.login-required')));
    await ctx.close();
  }

  // ── 2. 로그인: 저장 포폴 + 기본 벤치마크 산출 ──
  const ctx = await browser.newContext();
  await ctx.addCookies([{ name: 'session', value: COOKIE, domain: new URL(BASE).hostname, path: '/' }]);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  // 테스트 포폴 저장 (실DB에 가격 있는 069500/458730)
  await page.goto(BASE + '/myportfolios', { waitUntil: 'networkidle' });
  await page.evaluate(async () => {
    const items = await fetch('/api/portfolio/list').then(r => r.json());
    for (const p of items.filter(x => x.name.startsWith('E2E')))
      await fetch('/api/portfolio/' + p.id, { method: 'DELETE' });
    await fetch('/api/portfolio/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'E2E도표', tickers: [
        { code: '069500', name: 'KODEX 200', badge: 'KR ETF', weight: 60 },
        { code: '458730', name: 'TIGER 미국배당다우존스', badge: 'KR ETF', weight: 40 }] }) });
  });

  await page.goto(BASE + '/risk-return', { waitUntil: 'networkidle' });
  await page.waitForFunction("typeof rrChart !== 'undefined' && rrChart !== null", { timeout: 60000 });
  const info = await page.evaluate(() => ({
    ports: rrChart.data.datasets[0].data.map(d => ({ name: d.name, x: d.x, y: d.y, sharpe: d.sharpe })),
    benches: rrChart.data.datasets[1].data.map(d => d.name),
    period: document.getElementById('rrPeriod').textContent,
  }));
  const myPoint = info.ports.find(p => p.name === 'E2E도표');
  ok('내 포폴 점 표시', !!myPoint);
  ok('지표 유한값 (CAGR·변동성·샤프)', myPoint &&
     isFinite(myPoint.x) && isFinite(myPoint.y) && isFinite(myPoint.sharpe) && myPoint.x > 0);
  ok('벤치마크 점 1개 이상', info.benches.length >= 1);
  ok('기간 캡션 표시', info.period.includes('비교 기간'));

  // ── 3. 벤치마크 추가(검색 mock → 실산출 재호출) ──
  await page.route('**/api/search**', r => r.fulfill({ json: [
    { code: '069500', name: 'KODEX 200', badge: 'KR ETF' }] }));
  const before = info.benches.length;
  await page.fill('#rrSearch', 'kodex');
  await page.waitForSelector('.rr-dd-item[data-code]', { timeout: 5000 });
  await page.click('.rr-dd-item[data-code="069500"]');
  await page.waitForTimeout(3000);   // 재산출 대기 (실DB 로드)
  const after = await page.evaluate(() => ({
    benches: rrChart.data.datasets[1].data.map(d => d.name),
    chips: document.querySelectorAll('.rr-chip').length,
  }));
  ok('벤치마크 추가 칩 표시', after.chips === 1);
  // 069500은 기본 셋에 이미 있음 → 점 수 동일(중복 제거)이거나, 없었다면 +1
  ok('벤치마크 추가 반영(중복 제거 포함)', after.benches.length >= before);

  ok('JS 에러 0', errors.length === 0);
  if (errors.length) console.log('  errors:', errors.slice(0, 3));

  // 정리
  await page.evaluate(async () => {
    const items = await fetch('/api/portfolio/list').then(r => r.json());
    for (const p of items.filter(x => x.name.startsWith('E2E')))
      await fetch('/api/portfolio/' + p.id, { method: 'DELETE' });
  });
  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL  (${BASE})`);
  process.exit(fail ? 1 : 0);
})();
