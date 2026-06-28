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

  const setup = await page.evaluate(async () => {
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
    document.getElementById('rrResults').style.display = 'block';
    rrRenderAccordions(data);
    document.getElementById('rrAccordions').scrollIntoView();
    const divStats = {};
    const annualStats = {};
    const rollingStats = {};
    for (const it of data.items) {
      const divRows = (it.annual_div || []).filter(a => !a.partial);
      const divVals = divRows.map(a => a.dyield).filter(Number.isFinite).sort((a, b) => a - b);
      const growthYears = ((it.divgrowth || {}).yoy || []).map(y => y.year);
      const mid = divVals.length ? divVals[Math.floor(divVals.length / 2)] : null;
      const annualRows = it.annual || [];
      const horizonRows = Object.values((it.rolling_return || {}).horizon_table || {});
      divStats[it.name] = {
        firstFullDivYear: divRows.length ? divRows[0].year : null,
        medianDivYield: mid,
        firstGrowthYear: growthYears.length ? growthYears[0] : null,
      };
      annualStats[it.name] = {
        rows: annualRows.length,
        dirty: annualRows.filter(a => a.partial || (a.syn_frac || 0) > 0).length,
      };
      rollingStats[it.name] = {
        rows: horizonRows.length,
        dirty: horizonRows.filter(r => r.n > 0 && r.syn_frac !== 0).length,
      };
    }
    return { items: data.items.length, names: data.items.map(i => i.name), divStats, annualStats, rollingStats };
  });

  ok('compare 응답 items>0', setup.items > 0, setup.err || JSON.stringify(setup));
  ok('SCHD 배당성장 실제구간만 사용', setup.divStats?.['배당SCHD']?.firstFullDivYear >= 2012 && setup.divStats?.['배당SCHD']?.firstGrowthYear >= 2013,
    JSON.stringify(setup.divStats?.['배당SCHD']));
  ok('SCHD 배당률이 60/40보다 높게 산출', setup.divStats?.['배당SCHD']?.medianDivYield > setup.divStats?.['주식60채권40']?.medianDivYield,
    JSON.stringify(setup.divStats));
  ok('가격 기반 연도지표 합성/부분연도 제외', Object.values(setup.annualStats || {}).every(s => s.rows > 0 && s.dirty === 0),
    JSON.stringify(setup.annualStats));
  ok('롤링 손실확률 합성 윈도우 제외', Object.values(setup.rollingStats || {}).every(s => s.rows > 0 && s.dirty === 0),
    JSON.stringify(setup.rollingStats));

  for (const k of ['ret', 'vol', 'mdd', 'div', 'divg']) {
    await page.click(`.rr-acc[data-acc="${k}"] .rr-acc-head`);
  }
  await page.waitForTimeout(500);

  const result = await page.evaluate(() => {
    // 각 차트 데이터 절대 최대치(%) — 축파괴(>300%) 탐지
    const maxes = {};
    for (const k of ['ret', 'vol', 'mdd', 'div', 'divg']) {
      const ch = rrAccCharts[k];
      let mx = 0;
      if (ch) {
        const meta = ch._rrBoxMeta || ch.options?.plugins?.rrBoxWhisker?.meta || [];
        meta.forEach(d => {
          if (!d) return;
          [d.lo, d.hi, d.med].forEach(v => { if (Number.isFinite(v) && Math.abs(v) > mx) mx = Math.abs(v); });
        });
      }
      maxes[k] = +mx.toFixed(1);
    }
    const types = Object.fromEntries(Object.entries(rrAccCharts).map(([k, ch]) => [k, ch.config.type]));
    const whiskers = Object.fromEntries(Object.entries(rrAccCharts).map(([k, ch]) => [
      k, (ch._rrBoxMeta || []).filter(Boolean).length,
    ]));
    return { maxes, types, whiskers, charts: Object.keys(rrAccCharts).length };
  });

  ok('아코디언5 차트 생성', result.charts === 5, 'charts=' + result.charts);
  ok('아코디언5 오차막대 차트', Object.values(result.types || {}).every(t => t === 'bar'), 'types=' + JSON.stringify(result.types));
  ok('오차막대 수염 메타 존재', Object.values(result.whiskers || {}).every(n => n > 0), 'whiskers=' + JSON.stringify(result.whiskers));
  // 축파괴 가드: 어떤 차트도 |값|>300% 없어야 (SHY/IEF 합성글리치 +172%/+1726% 차단)
  const blown = Object.entries(result.maxes || {}).filter(([, v]) => v > 300);
  ok('축파괴 스파이크 없음(<300%)', blown.length === 0, 'blown=' + JSON.stringify(blown));
  console.log('  per-chart max% =', JSON.stringify(result.maxes));
  console.log('  items =', JSON.stringify(setup.names));

  await page.screenshot({ path: `tests/${SHOT}_light.png`, fullPage: true });
  await page.locator('#rrAccordions').screenshot({ path: `tests/${SHOT}_acc_light.png` });
  // 다크
  await page.evaluate(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
    document.documentElement.classList.add('dark');
  });
  await page.waitForTimeout(300);
  await page.screenshot({ path: `tests/${SHOT}_dark.png`, fullPage: true });
  await page.locator('#rrAccordions').screenshot({ path: `tests/${SHOT}_acc_dark.png` });

  ok('JS/콘솔 에러 0', errors.length === 0, errors.slice(0, 5).join(' | '));

  console.log(`\n${fail === 0 ? 'ALL PASS' : 'HAS FAIL'}  pass=${pass} fail=${fail}`);
  await browser.close();
  process.exit(fail === 0 ? 0 : 1);
})();
