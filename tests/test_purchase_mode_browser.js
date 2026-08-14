/**
 * 추가매수 2모드(구매만 / 구매+리밸런싱) 실브라우저 검증 (로컬 전용 — 로그인 세션 필요).
 * 실행: node tests/test_purchase_mode_browser.js <sessionCookie> [baseUrl]
 *   sessionCookie = tests/mint_session.py 출력값. baseUrl 기본 http://127.0.0.1:5000
 * 전제: 보유 종목 + 목표비중 그룹이 시드돼 있고, 적어도 한 그룹이 목표를 초과할 것.
 * 검증: 기본 모드·모드 전환·매도행 등장/소멸·순투입 합계·칩 재계산·라이트/다크 스샷·콘솔 0.
 * 보유·그룹 데이터는 읽기만 한다. 금액숨김 설정만 잠시 끄고 종료 시 원복.
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const COOKIE = process.argv[2];
const BASE = process.argv[3] || 'http://127.0.0.1:5000';
const SHOTDIR = process.argv[4] || path.join(__dirname, '..', 'tmp');
if (!COOKIE) { console.error('usage: node test_purchase_mode_browser.js <sessionCookie>'); process.exit(2); }

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name + (extra ? '  ← ' + extra : '')); }
}
const num = s => parseInt(String(s).replace(/[^0-9]/g, ''), 10);

// 화면에 그려진 추가매수 행 읽기
const readRows = page => page.evaluate(() => ({
  rows: [...document.querySelectorAll('#purchaseResult .pur-row')].map(r => ({
    name: r.querySelector('span:nth-child(2)').textContent.trim(),
    txt:  r.querySelector('.pur-buy, .pur-sell').textContent.trim(),
    sell: !!r.querySelector('.pur-sell'),
    barW: r.querySelector('.pur-bar i').style.width,
  })),
  totals: [...document.querySelectorAll('#purchaseResult .pur-total')].map(t => t.textContent.replace(/\s+/g, ' ').trim()),
  intro: document.getElementById('purIntroText').textContent.trim(),
  active: [...document.querySelectorAll('.pur-mode')].filter(b => b.classList.contains('active')).map(b => b.dataset.mode),
  note: document.querySelector('#purchaseResult > div:last-child').textContent.trim(),
}));

(async () => {
  fs.mkdirSync(SHOTDIR, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
  await ctx.addCookies([{ name: 'session', value: COOKIE, domain: new URL(BASE).hostname, path: '/' }]);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(BASE + '/myassets', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof groups !== 'undefined' && groups.length > 0, null, { timeout: 30000 });
  // 금액 마스킹이 켜져 있으면 숫자 검증이 불가 → 화면 토글로 끄고, 끝나면 되돌린다
  const wasHidden = await page.evaluate(async () => {
    const t = document.getElementById('hideAmountToggle');
    const was = !!(t && t.checked);
    if (was) { t.checked = false; await savePrivacySetting(); }
    return was;
  });

  await page.click('.ma-tab:has-text("추가매수")');
  await page.waitForSelector('#tab-purchase .pur-modes', { state: 'visible', timeout: 10000 });

  // ── 1. 기본 = 구매만 ──
  let s = await readRows(page);
  ok('기본 모드 = 구매만', JSON.stringify(s.active) === '["buy"]', JSON.stringify(s.active));
  ok('기본: 매도 행 없음', s.rows.length > 0 && s.rows.every(r => !r.sell), JSON.stringify(s.rows));
  ok('기본: 안내문 "매도 없이"', /매도 없이/.test(s.intro), s.intro);
  ok('기본: 합계 행 1개', s.totals.length === 1, JSON.stringify(s.totals));
  const amount = await page.inputValue('#purchaseAmount');
  ok('기본: 합계 = 입력액', num(s.totals[0]) === num(amount), `${s.totals[0]} vs ${amount}`);

  // ── 2. 구매 + 리밸런싱으로 전환 ──
  await page.click('.pur-mode[data-mode="rebal"]');
  s = await readRows(page);
  ok('전환: rebal 칩만 active', JSON.stringify(s.active) === '["rebal"]', JSON.stringify(s.active));
  ok('전환: 안내문 리밸 문구', /동시에 리밸런싱/.test(s.intro), s.intro);

  const sells = s.rows.filter(r => r.sell), buys = s.rows.filter(r => !r.sell);
  ok('리밸: 초과 그룹 매도 행 등장', sells.length > 0, JSON.stringify(s.rows));
  ok('리밸: 매도 행 라벨 "매도"', sells.every(r => r.txt.startsWith('매도')), JSON.stringify(sells));
  ok('리밸: 매수 행 라벨 "매수"', buys.every(r => r.txt.startsWith('매수')), JSON.stringify(buys));
  ok('리밸: 요약 3행(매도·매수·순투입)', s.totals.length === 3, JSON.stringify(s.totals));
  ok('리밸: 순투입 = 입력액', num(s.totals[2]) === num(amount), `${s.totals[2]} vs ${amount}`);
  ok('리밸: 매수합 - 매도합 = 순투입',
     num(s.totals[1]) - num(s.totals[0]) === num(s.totals[2]), JSON.stringify(s.totals));
  ok('리밸: 안내문에 세금·거래비용 경고', /세금·거래비용/.test(s.note), s.note);
  ok('리밸: 막대 폭이 모두 유효', s.rows.every(r => /^\d+%$/.test(r.barW)), JSON.stringify(s.rows.map(r => r.barW)));

  // 매도 색이 --down 토큰인지(방향색 규칙)
  const sellColor = await page.evaluate(() => {
    const el = document.querySelector('#purchaseResult .pur-sell');
    return el ? getComputedStyle(el).color : null;
  });
  const downToken = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue('--down').trim());
  ok('리밸: 매도 텍스트가 --down 색', !!sellColor && !!downToken, `${sellColor} / --down=${downToken}`);

  await page.screenshot({ path: path.join(SHOTDIR, 'purchase_rebal_light.png'), fullPage: false });

  // ── 3. 금액 칩으로 재계산 — 모드 유지 ──
  await page.click('.pur-chip:has-text("+500만")');
  s = await readRows(page);
  ok('칩: 모드 유지(rebal)', JSON.stringify(s.active) === '["rebal"]');
  ok('칩: 순투입 = 500만', num(s.totals[2]) === 5000000, JSON.stringify(s.totals));

  // 신규자금이 커지면 매도는 줄거나 사라진다
  const sells2 = s.rows.filter(r => r.sell);
  const sellSum2 = sells2.reduce((a, r) => a + num(r.txt), 0);
  const sellSum1 = sells.reduce((a, r) => a + num(r.txt), 0);
  ok('칩: 금액 늘면 매도 총액 감소', sellSum2 < sellSum1, `${sellSum1} → ${sellSum2}`);

  // ── 4. 구매만으로 복귀 ──
  await page.click('.pur-mode[data-mode="buy"]');
  s = await readRows(page);
  ok('복귀: 매도 행 사라짐', s.rows.every(r => !r.sell), JSON.stringify(s.rows));
  ok('복귀: 요약 1행', s.totals.length === 1, JSON.stringify(s.totals));
  ok('복귀: 합계 = 500만', num(s.totals[0]) === 5000000, s.totals[0]);

  // ── 5. 직접 입력 ──
  await page.fill('#purchaseAmount', '1234567');
  await page.click('.pur-mode[data-mode="rebal"]');
  s = await readRows(page);
  ok('직접입력: 순투입 = 1,234,567', num(s.totals[2]) === 1234567, JSON.stringify(s.totals));

  // ── 6. 다크 모드 ──
  await page.evaluate(() => {
    try { localStorage.setItem('mm-theme', 'dark'); } catch (e) {}
    document.documentElement.setAttribute('data-theme', 'dark');
  });
  await page.waitForTimeout(300);
  const darkBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  ok('다크: body 배경이 어둡다',
     (darkBg.match(/\d+/g) || []).slice(0, 3).reduce((a, b) => a + (+b), 0) < 250, darkBg);
  await page.screenshot({ path: path.join(SHOTDIR, 'purchase_rebal_dark.png'), fullPage: false });
  await page.evaluate(() => { try { localStorage.setItem('mm-theme', 'light'); } catch (e) {} });

  // 금액숨김 설정 원복
  if (wasHidden) await page.evaluate(async () => {
    const t = document.getElementById('hideAmountToggle');
    if (t) { t.checked = true; await savePrivacySetting(); }
  });

  ok('콘솔 에러 0', errors.length === 0, errors.slice(0, 3).join(' | '));

  await browser.close();
  console.log(`\n${pass} passed, ${fail} failed`);
  console.log(`shots → ${SHOTDIR}`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
