/**
 * ETF 상세검색 실브라우저 검증 (비로그인 페이지 — 세션 불필요).
 * 실행: node tests/test_etf_search_browser.js [baseUrl]
 */
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:5000';

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(BASE + '/search', { waitUntil: 'networkidle' });
  ok('모드 탭 렌더', !!(await page.$('#spModeAll')) && !!(await page.$('#spModeEtf')));
  ok('통합 모드: 패싯 패널 숨김', !(await page.$eval('#spFacetPanel', el => el.style.display !== 'none' && getComputedStyle(el).display !== 'none')));

  // ── 1. 통합검색 자연어: "미국 단기채" ──
  await page.fill('#searchInput', '미국 단기채');
  await page.waitForSelector('.result-card[data-code]', { timeout: 20000 });
  await sleep(400);
  let badges = await page.$$eval('#searchResults .result-card .result-badge', els => els.map(e => e.textContent));
  ok('자연어: KR ETF 카드 존재', badges.includes('KR ETF'));
  ok('자연어: US ETF 카드 존재', badges.includes('US ETF'));
  let sub = await page.$$eval('.card-code', els => els.map(e => e.textContent).join(' '));
  ok('자연어: 패싯 부제목(채권) 노출', sub.includes('채권'));

  // ── 2. ETF 상세검색 모드 전환 ──
  await page.click('#spModeEtf');
  await sleep(600);
  ok('ETF 모드: 패싯 패널 표시', await page.$eval('#spFacetPanel', el => getComputedStyle(el).display !== 'none'));
  ok('ETF 모드: 기존 필터 숨김', await page.$eval('#spFilters', el => getComputedStyle(el).display === 'none'));
  ok('ETF 모드: 채권 조건행 초기 숨김', await page.$eval('#spRowBondDur', el => getComputedStyle(el).display === 'none'));
  await page.waitForSelector('.result-card[data-code]', { timeout: 20000 });
  ok('ETF 모드: 브라우즈 결과 로드(검색어 없음)', (await page.$$('.result-card[data-code]')).length > 0);

  // ── 3. 채권 → 조건행 노출 → 미국 + 단기·초단기 ──
  await page.click('.sp-chip[data-g="asset"][data-v="bond"]');
  await sleep(500);
  ok('채권 선택: 만기·종류 행 노출', await page.$eval('#spRowBondDur', el => getComputedStyle(el).display !== 'none'));
  await page.click('.sp-chip[data-g="region"][data-v="US"]');
  await page.click('.sp-chip[data-g="bdur"][data-v="short"]');
  await page.click('.sp-chip[data-g="bdur"][data-v="ultrashort"]');
  await sleep(800);
  await page.waitForSelector('.result-card[data-code]', { timeout: 20000 });
  badges = await page.$$eval('#searchResults .result-card .result-badge', els => els.map(e => e.textContent));
  ok('미국 단기채 필터: KR+US 혼재', badges.includes('KR ETF') && badges.includes('US ETF'));
  let codes = await page.$$eval('.result-card[data-code]', els => els.map(e => e.dataset.code));
  ok('미국 단기채 필터: 대표 종목 포함', codes.some(c => ['329750', '440650', 'SGOV', 'BIL', 'SHV'].includes(c)));

  // ── 4. 상장시장 국내만 ──
  await page.click('.sp-chip[data-g="market"][data-v="KR"]');
  let allKR = false;
  try {
    await page.waitForFunction(() => {
      const b = [...document.querySelectorAll('#searchResults .result-card .result-badge')].map(e => e.textContent);
      return b.length > 0 && b.every(x => x === 'KR ETF');
    }, { timeout: 15000 });
    allKR = true;
  } catch (e) {}
  ok('국내 상장 필터: 전부 KR ETF', allKR);

  // ── 5. 레버리지 단일선택 토글 ──
  await page.click('.sp-chip[data-g="lev"][data-v="inv"]');
  await sleep(300);
  ok('인버스 칩 active', await page.$eval('.sp-chip[data-g="lev"][data-v="inv"]', el => el.classList.contains('active')));
  await page.click('.sp-chip[data-g="lev"][data-v="lev"]');
  await sleep(300);
  ok('레버리지 선택 시 인버스 해제(단일선택)',
     await page.$eval('.sp-chip[data-g="lev"][data-v="inv"]', el => !el.classList.contains('active')));
  await page.click('.sp-chip[data-g="lev"][data-v="lev"]');   // 해제
  await sleep(300);

  // ── 6. 검색어 + 패싯 병합 (ETF 모드에서 타이핑) ──
  await page.click('.sp-chip-reset:not(#spReset)');   // 채권 필터 잔류 제거(covcall∧bond=공집합 방지)
  await sleep(600);
  await page.fill('#searchInput', '커버드콜');
  await sleep(900);
  await page.waitForSelector('.result-card[data-code]', { timeout: 20000 });
  sub = await page.$$eval('.card-code', els => els.map(e => e.textContent).join(' '));
  ok('ETF 모드 검색어: 커버드콜 부제목', sub.includes('커버드콜'));
  await page.fill('#searchInput', '');
  await sleep(900);

  // ── 7. 필터 초기화 ──
  await page.click('.sp-chip-reset:not(#spReset)');
  await sleep(600);
  const activeCnt = await page.$$eval('#spFacetPanel .sp-chip.active', els => els.length);
  ok('필터 초기화: active 0', activeCnt === 0);
  ok('필터 초기화: 조건행 재숨김', await page.$eval('#spRowBondDur', el => getComputedStyle(el).display === 'none'));

  // ── 8. 페이지네이션 (전체 브라우즈 = 6천+건 → 페이저 필수) ──
  await page.waitForSelector('.sp-pg', { timeout: 20000 });
  const pgBtns = await page.$$('.sp-pg');
  ok('페이지네이션 렌더', pgBtns.length > 3);
  await page.click('.sp-pg:nth-child(4)');   // « ‹ 1 [2]
  await page.waitForSelector('#searchResults .result-card[data-code]', { timeout: 20000 });
  ok('2페이지 이동', await page.$eval('.sp-pg.active', el => el.textContent === '2'));

  // ── 9. 통합검색 복귀 ──
  await page.click('#spModeAll');
  await sleep(500);
  ok('통합 복귀: 기본화면(인기 종목)', await page.$eval('#spDefault', el => getComputedStyle(el).display !== 'none'));
  ok('통합 복귀: 패싯 패널 숨김', await page.$eval('#spFacetPanel', el => getComputedStyle(el).display === 'none'));

  // ── 10. 스크린샷 라이트/다크 ──
  await page.click('#spModeEtf');
  await page.click('.sp-chip[data-g="asset"][data-v="bond"]');
  await sleep(800);
  await page.screenshot({ path: 'tests/_etf_search_light.png', fullPage: false });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await sleep(300);
  await page.screenshot({ path: 'tests/_etf_search_dark.png', fullPage: false });

  ok('콘솔 에러 0', errors.length === 0);
  if (errors.length) console.log('ERRORS:', errors.slice(0, 5));

  await browser.close();
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
