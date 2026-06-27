/** 비교 심화 아코디언5 — adhoc(비로그인) 렌더 + 합성글리치 축파괴 가드 검증. JS 에러 0. */
'use strict';
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const SHOT = process.argv[3] || 'rr_deep';

let pass = 0, fail = 0;
const ok = (n, c, x) => { if (c) { pass++; console.log('PASS  ' + n); } else { fail++; console.log('FAIL  ' + n + (x ? ' — ' + x : '')); } };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 1100 } });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(BASE + '/risk-return', { waitUntil: 'networkidle' });

  const result = await page.evaluate(async () => {
    const body = {
      portfolios: [
        { name: '주식60채권40', tickers: [{ code: 'SPY', weight: 60 }, { code: 'IEF', weight: 40 }] },
        { name: '배당SCHD', tickers: [{ code: 'SCHD', weight: 100 }] },
      ],
      benchmarks: [{ code: 'SHY', name: 'SHY' }, { code: 'IEF', name: 'IEF' }, { code: 'TLT', name: 'TLT' }],
    };
    const res = await fetch('/api/portfolio/compare', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!data.items || !data.items.length) return { err: data.error || 'no items' };
    window.rrItems = data.items;
    window.rrVisible = data.items.map(() => true);
    rrRenderAccordions(data);
    ['ret', 'vol', 'mdd', 'div', 'divg'].forEach(k => rrAccToggle(k));
    // 각 차트 데이터 절대 최대치(%) — 축파괴(>300%) 탐지
    const maxes = {};
    for (const k of ['ret', 'vol', 'mdd', 'div', 'divg']) {
      const ch = rrAccCharts[k];
      let mx = 0;
      if (ch) ch.data.datasets.forEach(ds => ds.data.forEach(v => { if (v != null && Math.abs(v) > mx) mx = Math.abs(v); }));
      maxes[k] = +mx.toFixed(1);
    }
    return { items: data.items.length, maxes,
             charts: Object.keys(rrAccCharts).length,
             names: data.items.map(i => i.name) };
  });

  ok('compare 응답 items>0', result.items > 0, result.err || JSON.stringify(result));
  ok('아코디언5 차트 생성', result.charts === 5, 'charts=' + result.charts);
  // 축파괴 가드: 어떤 차트도 |값|>300% 없어야 (SHY/IEF 합성글리치 +172%/+1726% 차단)
  const blown = Object.entries(result.maxes || {}).filter(([, v]) => v > 300);
  ok('축파괴 스파이크 없음(<300%)', blown.length === 0, 'blown=' + JSON.stringify(blown));
  console.log('  per-chart max% =', JSON.stringify(result.maxes));
  console.log('  items =', JSON.stringify(result.names));

  await page.screenshot({ path: `tests/${SHOT}_light.png`, fullPage: true });
  // 다크
  await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
    document.documentElement.classList.add('dark');
  });
  await page.waitForTimeout(300);
  await page.screenshot({ path: `tests/${SHOT}_dark.png`, fullPage: true });

  ok('JS/콘솔 에러 0', errors.length === 0, errors.slice(0, 5).join(' | '));

  console.log(`\n${fail === 0 ? 'ALL PASS' : 'HAS FAIL'}  pass=${pass} fail=${fail}`);
  await browser.close();
  process.exit(fail === 0 ? 0 : 1);
})();
