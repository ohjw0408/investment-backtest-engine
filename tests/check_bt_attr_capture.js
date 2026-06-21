/** 포트폴리오 분석 구간 카드 = 비중 무관 참여율/방어율 렌더 스모크. */
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

  await page.goto(BASE + '/backtest', { waitUntil: 'networkidle' });

  // 종목 2개 주입 후 구간 분석 직접 호출(검색 UI 우회 — 스모크 한정)
  await page.evaluate(() => {
    btTickers = [{ code: 'QQQ', weight: 20 }, { code: 'SCHD', weight: 80 }];
    document.getElementById('btAttrCard').style.display = '';
  });
  await page.evaluate(() => btAttrAnalyze('2021-01-01', '2024-01-01'));
  await page.waitForFunction(() => /방어율|데이터가 부족/.test(document.getElementById('btAttrBody').innerHTML), { timeout: 15000 });

  const body = await page.locator('#btAttrBody').innerHTML();
  ok('방어율 컬럼 렌더', /하락 방어율/.test(body) && /상승 참여율/.test(body), body.slice(0, 120));
  ok('비중 무관 문구', /비중과 무관/.test(body));
  ok('카드 제목 = 상승 참여·하락 방어', /상승 참여 · 하락 방어/.test(await page.locator('#btAttrCard .bt-card-title').first().innerText()));
  ok('브라우저 에러 0', errors.length === 0, errors.join(' | '));

  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
