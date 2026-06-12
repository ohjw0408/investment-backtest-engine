/**
 * 즐겨찾기 위젯(B1) 실브라우저 검증 — 5탭 렌더 + 비로그인 동작 + JS 에러 0.
 * 실행: node tests/test_fav_browser.js [baseUrl]   (기본 http://127.0.0.1:5000)
 * 비로그인 관점만 자동화(구글 OAuth 자동화 불가) — 로그인 플로우는 API·jsdom 테스트가 커버.
 */
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const PAGES = ['/calculator', '/backtest', '/retirement', '/dividend-target', '/tax-switch'];

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();

  for (const path of PAGES) {
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

    await page.goto(BASE + path, { waitUntil: 'networkidle', timeout: 30000 });

    const bar = await page.$('#favBar .fav-bar');
    ok(`${path} 위젯 렌더`, !!bar);

    const sel = await page.$('#favBar .fav-select');
    const disabled = sel ? await sel.isDisabled() : null;
    const phText = sel ? await sel.evaluate(s => s.options[0].textContent) : '';
    ok(`${path} 비로그인 select 비활성+안내`, disabled === true && phText.includes('로그인'));

    // 비로그인 저장 클릭 → 로그인 안내 다이얼로그
    let dlg = '';
    page.once('dialog', async d => { dlg = d.message(); await d.dismiss(); });
    await page.click('#favBar .fav-btn');
    await page.waitForTimeout(300);
    ok(`${path} 저장 클릭 → 로그인 안내`, dlg.includes('로그인'));

    ok(`${path} JS 에러 0`, errors.length === 0);
    if (errors.length) console.log('  errors:', errors.slice(0, 3));
    await page.close();
  }

  // API 비로그인 401
  const page = await ctx.newPage();
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  const st = await page.evaluate(async () => {
    const r = await fetch('/api/portfolio/list');
    return r.status;
  });
  ok('API /api/portfolio/list 비로그인 401', st === 401);
  await page.close();

  // ── 어댑터 왕복: route mock으로 로그인 위장 → 불러오기 → 페이지 상태 → 저장 payload ──
  const SAVED = [{
    id: 1, name: '검증용',
    tickers: [
      { code: '069500', name: 'KODEX 200', badge: 'KR ETF', weight: 60 },
      { code: '458730', name: 'TIGER 미국배당', badge: 'KR ETF', weight: 40 },
    ],
  }];
  // stateExpr: 불러온 뒤 페이지 내부 상태의 [code, weight] 추출식 (tax-switch는 closure → DOM로 검증)
  const ADAPTERS = [
    { path: '/calculator',      stateExpr: 'tickers.map(t=>[t.code,t.weight])',   weights: [60, 40] },
    { path: '/backtest',        stateExpr: 'btTickers.map(t=>[t.code,t.weight])', weights: [0.6, 0.4] },
    { path: '/retirement',      stateExpr: 'retTickers.map(t=>[t.code,t.weight])',weights: [0.6, 0.4] },
    { path: '/dividend-target', stateExpr: 'dtTickers.map(t=>[t.code,t.weight])', weights: [60, 40] },
    { path: '/tax-switch',      stateExpr: null,                                  weights: [60, 40] },
  ];

  for (const a of ADAPTERS) {
    const p = await ctx.newPage();
    let savedBody = null;
    await p.route('**/api/me', r => r.fulfill({ json: { logged_in: true, name: 't' } }));
    await p.route('**/api/portfolio/list', r => r.fulfill({ json: SAVED }));
    await p.route('**/api/portfolio/save', async r => {
      savedBody = r.request().postDataJSON();
      await r.fulfill({ json: { ok: true } });
    });
    await p.route('**/api/settings/tax', r => r.fulfill({ json: {} }));
    await p.goto(BASE + a.path, { waitUntil: 'networkidle', timeout: 30000 });

    await p.selectOption('#favBar .fav-select', '1');
    await p.waitForTimeout(200);

    if (a.stateExpr) {
      const state = await p.evaluate(a.stateExpr);
      ok(`${a.path} 불러오기 → 상태 반영`,
         state.length === 2 && state[0][0] === '069500' &&
         Math.abs(state[0][1] - a.weights[0]) < 1e-9 &&
         Math.abs(state[1][1] - a.weights[1]) < 1e-9);
    } else {
      const rows = await p.$$eval('#tsTickerList .ts-ticker-row',
        els => els.map(e => [e.dataset.code, Number(e.querySelector('.ts-weight').value)]));
      ok(`${a.path} 불러오기 → 상태 반영`,
         rows.length === 2 && rows[0][0] === '069500' &&
         rows[0][1] === 60 && rows[1][1] === 40);
    }

    // 저장 왕복 — prompt에 새 이름 입력 → POST payload가 % 규약(60/40)으로 normalize
    p.on('dialog', async d => {
      if (d.type() === 'prompt') await d.accept('왕복저장');
      else await d.accept();
    });
    await p.click('#favBar .fav-btn');
    await p.waitForTimeout(400);
    ok(`${a.path} 저장 payload % 규약 왕복`,
       savedBody && savedBody.name === '왕복저장' &&
       savedBody.tickers.length === 2 &&
       savedBody.tickers[0].weight === 60 && savedBody.tickers[1].weight === 40);
    await p.close();
  }

  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL  (${BASE})`);
  process.exit(fail ? 1 : 0);
})();
