/**
 * 내자산 배당금 월별 차트 실브라우저 검증 (로그인 필요 — 로컬 전용).
 * 실행: node tests/test_dividend_chart_browser.js <sessionCookie> [baseUrl]
 *   sessionCookie = tests/mint_session.py 출력값.
 */
const { chromium } = require('playwright');
const COOKIE = process.argv[2];
const BASE   = process.argv[3] || 'http://127.0.0.1:5000';
if (!COOKIE) { console.error('usage: node test_dividend_chart_browser.js <sessionCookie>'); process.exit(2); }

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  await ctx.addCookies([{ name: 'session', value: COOKIE, domain: new URL(BASE).hostname, path: '/' }]);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  // ── 테스트 보유종목 시드: SCHD(US 일반) + 458730(KR ISA) ──
  await page.goto(BASE + '/myassets', { waitUntil: 'networkidle' });
  await page.evaluate(async () => {
    const items = await fetch('/api/myassets/data').then(r => r.json());
    for (const h of (items.holdings || []).filter(x => ['SCHD', '458730'].includes(x.code)))
      await fetch('/api/myassets/holding/' + h.id, { method: 'DELETE' });
    await fetch('/api/myassets/holding', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: 'SCHD', quantity: 100, account_type: '일반' }) });
    await fetch('/api/myassets/holding', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: '458730', quantity: 50, account_type: 'ISA' }) });
  });

  await page.goto(BASE + '/myassets', { waitUntil: 'networkidle' });
  await page.waitForFunction("typeof _divChart !== 'undefined' && _divChart !== null", { timeout: 30000 });

  // 카드 + 차트
  ok('배당금 카드 존재', !!(await page.$('#divCard')));
  const info = await page.evaluate(() => ({
    datasets: _divChart.data.datasets.map(d => d.label),
    months: _divChart.data.labels.length,
    pastYears: _divData.past_years, proj: _divData.proj_year,
    hasForeign: _divData.has_foreign,
    pretaxKRW: _divData.past_years.reduce((s, y) => s + _divData.series.KRW.pretax[y].reduce((a, b) => a + b, 0), 0),
  }));
  ok('x축 = 12개월', info.months === 12);
  ok('시리즈 = 과거3년+예측1년', info.datasets.length === 4);
  ok('예측 연도 라벨 표시', info.datasets[3].includes('예측'));
  ok('해외자산 감지', info.hasForeign === true);
  ok('과거 배당 > 0', info.pretaxKRW > 0);

  // 세후 토글 → 값 감소 (US 일반 15% 과세분)
  const before = await page.evaluate(() =>
    _divChart.data.datasets[2].data.reduce((a, b) => a + b, 0));
  await page.click('[data-div-tax="posttax"]');
  await page.waitForTimeout(400);
  const after = await page.evaluate(() =>
    _divChart.data.datasets[2].data.reduce((a, b) => a + b, 0));
  ok('세후 토글 → 값 감소', after < before && after > 0);

  // 외화 토글 → 값 변화(달러 환산, 원화보다 작음)
  await page.click('[data-div-cur="USD"]');
  await page.waitForTimeout(400);
  const usd = await page.evaluate(() =>
    _divChart.data.datasets[2].data.reduce((a, b) => a + b, 0));
  ok('외화($) 토글 → 달러 환산(원화보다 작음)', usd > 0 && usd < after);

  // 안내문구
  const note = await page.textContent('#divNote');
  ok('안내: 현재 보유 수량 가정', note.includes('현재 보유 수량'));
  ok('안내: 예측치(CAGR)', note.includes('예측'));
  ok('안내: 백테스트·투자계산기 유도', note.includes('백테스트') && note.includes('투자계산기'));

  ok('JS 에러 0', errors.length === 0);
  if (errors.length) console.log('  errors:', errors.slice(0, 3));

  // 정리
  await page.evaluate(async () => {
    const items = await fetch('/api/myassets/data').then(r => r.json());
    for (const h of (items.holdings || []).filter(x => ['SCHD', '458730'].includes(x.code)))
      await fetch('/api/myassets/holding/' + h.id, { method: 'DELETE' });
  });
  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL  (${BASE})`);
  process.exit(fail ? 1 : 0);
})();
