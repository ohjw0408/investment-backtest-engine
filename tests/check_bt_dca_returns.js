/** 적립식 백테스트 지표 스모크 — 연간수익률·MDD가 납입금에 오염되지 않는지 실브라우저 확인.
 *  버그(2026-08-05): 적립식 2006년 +1000%, 2008년 +11% (잔고 기준 계산). */
'use strict';
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:5000';
let pass = 0, fail = 0;
const ok = (n, c, x) => { if (c) { pass++; console.log('PASS  ' + n); } else { fail++; console.log('FAIL  ' + n + (x ? ' — ' + x : '')); } };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  // 로컬엔 celery 워커가 없으므로 submit/poll을 동기 엔드포인트로 우회(렌더 경로는 그대로 탄다)
  let submitted = null;
  await page.route('**/api/backtest/submit', async route => {
    submitted = JSON.parse(route.request().postData());
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ task_id: 'local', status: 'PENDING' }) });
  });
  await page.route('**/api/task/local', async route => {
    const r = await page.request.post(BASE + '/api/backtest/run', { data: submitted, timeout: 300000 });
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'SUCCESS', result: await r.json() }) });
  });

  await page.goto(BASE + '/backtest', { waitUntil: 'networkidle' });

  await page.evaluate(() => {
    btTickers = [{ code: 'SPY', name: 'SPY', weight: 1 }];
    document.getElementById('btStartDate').value = '2006-01-01';
    document.getElementById('btEndDate').value   = '2025-12-31';
    document.getElementById('btSeed').value      = '100000';
    document.getElementById('btMonthly').value   = '1000000';
  });
  await page.click('#btRunBtn');
  await page.waitForSelector('#btResultContent', { state: 'visible', timeout: 300000 });
  await page.waitForFunction(() => btCharts.annual && btCharts.annual.data.datasets[0].data.length, { timeout: 30000 });

  const annual = await page.evaluate(() => ({
    labels: btCharts.annual.data.labels,
    values: btCharts.annual.data.datasets[0].data,
    dd:     btCharts.drawdown.data.datasets[0].data,
  }));
  const hero    = await page.locator('#btHeroSub').innerText();
  const metrics = await page.locator('#btMetrics').innerText();
  console.log('hero:', hero.replace(/\n/g, ' '));
  console.log('metrics:', metrics.replace(/\n/g, ' '));
  console.log('annual:', annual.labels.map((l, i) => l + ' ' + annual.values[i].toFixed(1) + '%').join(' | '));

  const y = (yr) => annual.values[annual.labels.indexOf(yr + '년')];
  ok('연간수익률 전부 |r| < 60% (납입금 오염 없음)', annual.values.every(v => Math.abs(v) < 60),
     JSON.stringify(annual.values));
  ok('2008년 하락(원화 SPY) — 잔고기준이면 +로 나옴', y(2008) < 0, String(y(2008)));
  ok('2022년 하락', y(2022) < 0, String(y(2022)));
  ok('2006년 부분연도 정상범위', Math.abs(y(2006)) < 30, String(y(2006)));
  ok('MDD ≤ -20% (2008 반영)', /-(2|3|4|5)\d(\.\d+)?%/.test(metrics), metrics.replace(/\n/g, ' '));
  ok('낙폭 차트 최저 ≤ -20%', Math.min(...annual.dd) <= -20, String(Math.min(...annual.dd)));
  ok('브라우저 에러 0', errors.length === 0, errors.join(' | '));

  await page.screenshot({ path: 'tests/shots/bt_dca_returns.png', fullPage: true });
  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
