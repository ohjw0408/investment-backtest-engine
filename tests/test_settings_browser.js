/**
 * 설정 페이지 — 홈화면 위젯 매니저 실브라우저 (로컬 전용, 로그인 세션 필요).
 * 실행: node tests/test_settings_browser.js <sessionCookie> [baseUrl]
 *   sessionCookie = tests/mint_session.py 출력. baseUrl 기본 http://127.0.0.1:5000
 */
const { chromium } = require('playwright');
const COOKIE = process.argv[2];
const BASE = process.argv[3] || 'http://127.0.0.1:5000';
if (!COOKIE) { console.error('usage: node test_settings_browser.js <cookie>'); process.exit(2); }

let pass = 0, fail = 0;
const ok = (n, c) => { if (c) { pass++; console.log('PASS  ' + n); } else { fail++; console.log('FAIL  ' + n); } };

(async () => {
  const browser = await chromium.launch();

  // ── 1. 비로그인: 로그인 게이트 ──
  {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    await p.goto(BASE + '/settings', { waitUntil: 'networkidle' });
    ok('비로그인: 로그인 게이트 표시', await p.evaluate(() =>
      document.getElementById('loginGate').style.display !== 'none'));
    ok('비로그인: 에디터 숨김', await p.evaluate(() =>
      document.getElementById('widgetEditor').style.display === 'none'));
    await ctx.close();
  }

  // ── 2. 로그인 컨텍스트 ──
  const ctx = await browser.newContext();
  await ctx.addCookies([{ name: 'session', value: COOKIE, domain: new URL(BASE).hostname, path: '/' }]);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  // 초기화: e2e 유저를 기본 단일 위젯으로 리셋
  await page.goto(BASE + '/settings', { waitUntil: 'networkidle' });
  await page.evaluate(() => fetch('/api/home-config', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ widgets: [{ key: 'w_market', name: '시장 지수', items: [{ code: '^GSPC', name: 'S&P 500' }] }] }),
  }));
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('#widgetEditor .we-widget', { timeout: 8000 }).catch(() => {});

  ok('로그인: 에디터 표시', await page.evaluate(() =>
    document.getElementById('widgetEditor').style.display !== 'none'));
  ok('위젯 1개 렌더', (await page.locator('.we-widget').count()) === 1);

  // 위젯 추가
  await page.click('.we-add-widget');
  ok('위젯 추가 → 2개', (await page.locator('.we-widget').count()) === 2);

  // 이름 변경(2번째)
  await page.locator('.we-name-input').nth(1).fill('내 관심1');

  // 2번째 위젯에 종목 추가(프리셋 모달)
  await page.locator('.we-widget').nth(1).locator('.we-add-item').click();
  ok('검색 모달 열림', await page.evaluate(() =>
    document.getElementById('weModal').classList.contains('open')));
  await page.locator('.we-preset').first().click();   // S&P 500 프리셋
  await page.locator('.we-modal-close').click();
  ok('2번째 위젯 칩 1개 추가', (await page.locator('.we-widget').nth(1).locator('.we-chip').count()) === 1);

  // 저장
  await page.click('#weSaveBtn');
  await page.waitForFunction(() =>
    document.getElementById('weStatus').textContent.includes('저장'), { timeout: 5000 }).catch(() => {});
  ok('저장 성공 상태', await page.evaluate(() =>
    document.getElementById('weStatus').classList.contains('ok')));

  // 재로드 → 반영 확인
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('.we-widget', { timeout: 8000 }).catch(() => {});
  ok('재로드 후 위젯 2개 유지', (await page.locator('.we-widget').count()) === 2);
  ok('재로드 후 이름 유지', (await page.locator('.we-name-input').nth(1).inputValue()) === '내 관심1');

  // 삭제
  await page.locator('.we-widget').nth(1).locator('.we-del').click();
  ok('위젯 삭제 → 1개', (await page.locator('.we-widget').count()) === 1);

  ok('콘솔 에러 0', errors.length === 0);
  if (errors.length) console.log('  ERRORS:', errors.slice(0, 4));

  // 정리: 기본 단일 위젯으로 되돌림
  await page.evaluate(() => fetch('/api/home-config', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ widgets: [{ key: 'w_market', name: '시장 지수', items: [{ code: '^GSPC', name: 'S&P 500' }] }] }),
  }));

  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
})();
