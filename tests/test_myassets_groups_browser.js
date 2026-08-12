/**
 * 그룹 탭에서 보유 종목 담기 실브라우저 검증 (로컬 전용 — 로그인 세션 필요).
 * 실행: node tests/test_myassets_groups_browser.js <sessionCookie> [baseUrl]
 *   sessionCookie = tests/mint_session.py 출력값. baseUrl 기본 http://127.0.0.1:5000
 * 전제: 보유 종목(같은 코드가 여러 계좌에 걸친 것 포함) + 그룹 1개 이상 시드.
 * 검증: 미분류 배너 → 담기 모달(검색·필터·일괄선택) → 저장 시 계좌 전체 반영 → 칩 ×로 빼기.
 */
const { chromium } = require('playwright');

const COOKIE = process.argv[2];
const BASE = process.argv[3] || 'http://127.0.0.1:5000';
if (!COOKIE) { console.error('usage: node test_myassets_groups_browser.js <sessionCookie>'); process.exit(2); }

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name + (extra ? '  ← ' + extra : '')); }
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await ctx.addCookies([{ name: 'session', value: COOKIE, domain: new URL(BASE).hostname, path: '/' }]);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(BASE + '/myassets', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.holdings && window.holdings.length > 0 || (typeof holdings !== 'undefined' && holdings.length > 0), null, { timeout: 20000 });

  // 시작 상태를 결정적으로: 모든 보유를 미분류로 되돌린다
  const codes = await page.evaluate(() => [...new Set(holdings.map(h => String(h.code)))]);
  await page.evaluate(async (codes) => {
    await fetch('/api/myassets/holdings/group', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_id: null, codes })
    });
  }, codes);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof groups !== 'undefined' && groups.length > 0, null, { timeout: 20000 });

  await page.click('.ma-tab:has-text("그룹 관리")');
  await page.waitForSelector('#tab-groups .grp-block', { timeout: 10000 });

  ok('미분류 배너 노출', await page.isVisible('#groupsUnassigned .grp-hint'));
  ok('그룹 카드마다 종목 담기 버튼', (await page.$$('.grp-members .gm-add')).length === (await page.evaluate(() => groups.length)));
  ok('초기 상태 = 담긴 종목 없음', (await page.$$('.gm-tag')).length === 0);

  // ── 담기 모달 ──
  await page.click('#groupsUnassigned .grp-hint button');
  await page.waitForSelector('#modalAssign.show');
  ok('배너 진입 시 미분류 필터 활성', await page.evaluate(() =>
    document.querySelectorAll('#modalAssign .asg-chip')[1].classList.contains('active')));

  const rowsAll = await page.$$('#assignList .asg-row');
  ok('종목이 코드 단위로 1행씩 (계좌 중복 없음)', rowsAll.length === codes.length,
     `rows=${rowsAll.length} codes=${codes.length}`);

  // 계좌 요약이 행에 보이는지(여러 계좌 보유 종목)
  const multiAcct = await page.evaluate(() =>
    [...document.querySelectorAll('#assignList .ar-sub')].some(e => e.textContent.includes('·')));
  ok('여러 계좌 보유 종목의 계좌 요약 표시', multiAcct);

  // 검색 필터
  await page.fill('#assignSearch', codes[0]);
  await page.waitForTimeout(120);
  ok('검색 필터 동작', (await page.$$('#assignList .asg-row')).length === 1);
  await page.fill('#assignSearch', '');
  await page.waitForTimeout(120);

  // 일괄 선택 → 저장
  await page.click('.asg-bulk button:has-text("보이는 항목 모두 선택")');
  ok('선택 개수 표시', (await page.textContent('#assignCount')).includes(String(codes.length)));
  const targetGroup = await page.evaluate(() => document.getElementById('assignGroupSel').selectedOptions[0].textContent);
  await page.click('#modalAssign .btn-primary');
  await page.waitForSelector('#modalAssign.show', { state: 'hidden', timeout: 10000 });
  await page.waitForFunction(() => document.querySelectorAll('.gm-tag').length > 0, null, { timeout: 15000 });

  ok('저장 후 그룹 카드에 종목 칩', (await page.$$('.gm-tag')).length === codes.length);
  const allAssigned = await page.evaluate(() => holdings.every(h => !!h.group_id));
  ok('여러 계좌 행이 전부 그룹에 반영(한 번에)', allAssigned);
  ok('미분류 배너 사라짐', !(await page.isVisible('#groupsUnassigned .grp-hint')));

  // ── 칩 ×로 빼기 ──
  await page.click('.gm-tag button');
  await page.waitForFunction(n => document.querySelectorAll('.gm-tag').length === n - 1,
                             codes.length, { timeout: 15000 });
  ok('칩 ×로 그룹에서 빼기', (await page.$$('.gm-tag')).length === codes.length - 1);
  ok('빠진 종목은 미분류로 복귀', await page.isVisible('#groupsUnassigned .grp-hint'));

  await page.screenshot({ path: 'tests/shots/groups_assign_light.png', fullPage: true });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.waitForTimeout(200);
  await page.screenshot({ path: 'tests/shots/groups_assign_dark.png', fullPage: true });

  // ── 모바일 ──
  const mctx = await browser.newContext({ viewport: { width: 390, height: 780 }, isMobile: true, hasTouch: true });
  await mctx.addCookies([{ name: 'session', value: COOKIE, domain: new URL(BASE).hostname, path: '/' }]);
  const mp = await mctx.newPage();
  mp.on('pageerror', e => errors.push('mobile:' + e));
  await mp.goto(BASE + '/myassets', { waitUntil: 'domcontentloaded' });
  await mp.waitForFunction(() => typeof groups !== 'undefined' && groups.length > 0, null, { timeout: 20000 });
  await mp.click('.ma-mtab[data-mtab="groups"]');
  await mp.waitForSelector('.grp-members .gm-add');
  await mp.click('.grp-members .gm-add');
  await mp.waitForSelector('#modalAssign.show');
  const box = await mp.$eval('.asg-box', e => e.getBoundingClientRect().width);
  ok('모바일 모달 뷰포트 내', box <= 390);
  await mp.screenshot({ path: 'tests/shots/groups_assign_mobile.png', fullPage: false });
  await mctx.close();

  ok('콘솔 에러 0', errors.length === 0, errors.slice(0, 3).join(' | '));

  await browser.close();
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
