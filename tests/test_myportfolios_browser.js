/**
 * 내 포트폴리오 페이지 + myassets 파이차트 실브라우저 검증 (로컬 전용 — 로그인 세션 필요).
 * 실행: node tests/test_myportfolios_browser.js <sessionCookie> [baseUrl]
 *   sessionCookie = tests/mint_session.py 출력값. baseUrl 기본 http://127.0.0.1:5000
 * 검증: 비로그인 게이팅 / 생성→수정→계산기 위젯 연동→삭제 풀플로우(실서버+실DB) / 자산구성 pie.
 */
const { chromium } = require('playwright');

const COOKIE = process.argv[2];
const BASE = process.argv[3] || 'http://127.0.0.1:5000';
if (!COOKIE) { console.error('usage: node test_myportfolios_browser.js <sessionCookie>'); process.exit(2); }

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}

const SEARCH_MOCK = [
  { code: '069500', name: 'KODEX 200', badge: 'KR ETF' },
  { code: '458730', name: 'TIGER 미국배당다우존스', badge: 'KR ETF' },
];

(async () => {
  const browser = await chromium.launch();

  // ── 1. 비로그인: 서버 렌더 게이팅 ──
  {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    await p.goto(BASE + '/myportfolios', { waitUntil: 'domcontentloaded' });
    ok('비로그인 게이팅(로그인 안내)', !!(await p.$('.login-required')));
    ok('비로그인 목록 미렌더', !(await p.$('#mpList')));
    await ctx.close();
  }

  // ── 2. 로그인 컨텍스트 ──
  const ctx = await browser.newContext();
  const host = new URL(BASE).hostname;
  await ctx.addCookies([{ name: 'session', value: COOKIE, domain: host, path: '/' }]);

  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.route('**/api/search**', r => r.fulfill({ json: SEARCH_MOCK }));

  // 잔여 테스트 데이터 정리
  await page.goto(BASE + '/myportfolios', { waitUntil: 'networkidle' });
  await page.evaluate(async () => {
    const items = await fetch('/api/portfolio/list').then(r => r.json());
    for (const p of items.filter(x => x.name.startsWith('E2E')))
      await fetch('/api/portfolio/' + p.id, { method: 'DELETE' });
  });
  await page.reload({ waitUntil: 'networkidle' });
  ok('로그인 페이지 렌더(목록 영역)', !!(await page.$('#mpList')));

  // ── 3. 생성 ──
  await page.click('button.btn-primary');                       // + 새 포트폴리오
  await page.fill('#mpName', 'E2E생성');
  await page.fill('#mpSearch', 'kodex');
  await page.waitForSelector('.mp-dd-item[data-code]', { timeout: 5000 });
  await page.click('.mp-dd-item[data-code="069500"]');
  await page.fill('#mpSearch', 'tiger');
  await page.waitForSelector('.mp-dd-item[data-code="458730"]', { timeout: 5000 });
  await page.click('.mp-dd-item[data-code="458730"]');
  const rows = await page.$$('.mp-edit-row');
  ok('모달 종목 2개 추가(균등 50/50)', rows.length === 2 &&
     await page.$eval('.mp-edit-row input', i => i.value) === '50');
  await page.click('.modal-actions .btn-primary');              // 저장
  await page.waitForSelector('.mp-card', { timeout: 5000 });
  const cardName = await page.$eval('.mp-card .mp-name', e => e.textContent);
  ok('생성 → 카드 렌더', cardName === 'E2E생성');
  const totalTxt = await page.$eval('.mp-card .mp-total span:last-child', e => e.textContent);
  ok('카드 비중 합계 100%', totalTxt.includes('100%'));

  // ── 4. 수정 (이름 + 비중 60/40) ──
  await page.click('.mp-card .icon-btn[title="수정"]');
  await page.fill('#mpName', 'E2E수정');
  const inputs = await page.$$('.mp-edit-row input');
  await inputs[0].fill('60');
  await inputs[1].fill('40');
  await page.click('.modal-actions .btn-primary');
  await page.waitForFunction(() =>
    document.querySelector('.mp-card .mp-name')?.textContent === 'E2E수정', { timeout: 5000 });
  ok('수정 → 이름 반영', true);
  const weights = await page.$$eval('.mp-card .mp-weight', els => els.map(e => e.textContent));
  ok('수정 → 비중 60/40 반영', weights[0] === '60%' && weights[1] === '40%');

  // ── 5. 계산기 위젯 연동: 저장한 포폴이 ★ 드롭다운에 뜨고 불러와짐 ──
  const calc = await ctx.newPage();
  await calc.goto(BASE + '/calculator', { waitUntil: 'networkidle' });
  const optTexts = await calc.$$eval('#favBar .fav-select option', els => els.map(e => e.textContent));
  ok('계산기 ★ 드롭다운에 표시', optTexts.includes('E2E수정'));
  await calc.selectOption('#favBar .fav-select', { label: 'E2E수정' });
  await calc.waitForTimeout(200);
  const state = await calc.evaluate('tickers.map(t=>[t.code,t.weight])');
  ok('계산기 불러오기 → 60/40', state.length === 2 && state[0][1] === 60 && state[1][1] === 40);

  // ── 5b. 멀티계좌(세금 ON + 계좌 추가) 카드에서도 즐겨찾기 불러오기 ──
  await calc.evaluate(() => {
    if (!window.taxEnabled) toggleTax();   // 계좌 1 자동 생성
    addTaxAccount();                       // 계좌 2 → 종목 입력 카드
  });
  await calc.waitForSelector('.acct-fav-select', { timeout: 5000 });
  // 비동기 목록 로드 후 옵션 채워질 때까지 대기
  await calc.waitForFunction(() =>
    document.querySelector('.acct-fav-select')?.options.length > 1, { timeout: 5000 });
  const acctOpts = await calc.$$eval('.acct-fav-select option', els => els.map(e => e.textContent));
  ok('계좌 카드 즐겨찾기 select에 표시', acctOpts.includes('E2E수정'));
  await calc.selectOption('.acct-fav-select', { label: 'E2E수정' });
  await calc.waitForTimeout(200);
  const acctState = await calc.evaluate('window.taxAccounts[1].tickers.map(t=>[t.code,t.weight])');
  ok('계좌 카드 불러오기 → 60/40', acctState.length === 2 &&
     acctState[0][0] === '069500' && acctState[0][1] === 60 && acctState[1][1] === 40);
  ok('계좌 카드 종목 행 렌더', (await calc.$$eval('#taxAccountList input[type="number"]',
     els => els.length)) > 0);
  await calc.close();

  // ── 6. 삭제 ──
  page.on('dialog', d => d.accept());
  await page.bringToFront();
  await page.click('.mp-card .icon-btn[title="삭제"]');
  await page.waitForSelector('.mp-empty', { timeout: 5000 });
  ok('삭제 → 빈 상태', true);

  // ── 7. myassets 자산 구성 = 파이차트 ──
  const ma = await ctx.newPage();
  const maErrors = [];
  ma.on('pageerror', e => maErrors.push(String(e)));
  await ma.goto(BASE + '/myassets', { waitUntil: 'networkidle' });
  const chartInfo = await ma.evaluate(() => {
    holdings = [
      { code: 'AAA', quantity: 1, avg_price: 1, group_name: '주식', group_color: '#1976D2' },
      { code: 'BBB', quantity: 1, avg_price: 1, group_name: '채권', group_color: '#2E7D32' },
    ];
    prices = { AAA: 600000, BBB: 400000 };
    renderWeightChart(1000000);
    return {
      type: weightChart.config.type,
      data: weightChart.data.datasets[0].data,
      labels: weightChart.data.labels,
    };
  });
  ok('자산 구성 차트 type = pie', chartInfo.type === 'pie');
  ok('파이 데이터 60/40', chartInfo.data[0] === 60 && chartInfo.data[1] === 40 &&
     chartInfo.labels.join() === '주식,채권');
  ok('myassets JS 에러 0', maErrors.length === 0);
  await ma.screenshot({ path: 'tests/_ma_pie.png', clip: { x: 0, y: 0, width: 1280, height: 900 } });
  await ma.close();

  ok('myportfolios JS 에러 0', errors.length === 0);
  if (errors.length) console.log('  errors:', errors.slice(0, 3));

  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL  (${BASE})`);
  process.exit(fail ? 1 : 0);
})();
