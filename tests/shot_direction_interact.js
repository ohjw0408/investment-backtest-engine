/**
 * 등락색/상태색 분리 — 인터랙션 후 상태 캡처(탭 전환·토스트·경고).
 * 실행: node tests/shot_direction_interact.js [BASE_URL]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const DIR = path.join(__dirname, 'shots_direction_interact');
fs.mkdirSync(DIR, { recursive: true });

function mintCookie() {
  const out = execFileSync(path.join(__dirname, '..', 'venv', 'Scripts', 'python.exe'),
    [path.join(__dirname, 'mint_session.py')], { cwd: path.join(__dirname, '..'), encoding: 'utf-8' });
  return out.trim().split('\n').pop().trim();
}

(async () => {
  const cookie = mintCookie();
  const browser = await chromium.launch();

  for (const theme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await ctx.addCookies([{ name: 'session', value: cookie, domain: '127.0.0.1', path: '/' }]);
    await ctx.addInitScript(t => { try { localStorage.setItem('theme', t); } catch (e) {} }, theme);
    const page = await ctx.newPage();
    const errs = [];
    page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    const shot = n => page.screenshot({ path: path.join(DIR, `${n}_${theme}.png`), fullPage: true });

    // ── 내 자산: 리밸런싱 / 그룹 관리 탭 ──
    await page.goto(BASE + '/myassets', { waitUntil: 'networkidle' });
    await page.evaluate(t => document.documentElement.setAttribute('data-theme', t), theme);
    await page.waitForTimeout(4000);
    for (const [idx, name] of [[2, 'ma_rebal'], [4, 'ma_group'], [3, 'ma_purchase']]) {
      await page.click(`.ma-tabs .ma-tab:nth-child(${idx})`).catch(e => console.log('  tabclick fail ' + name + ': ' + e.message));
      await page.waitForTimeout(3000);
      const active = await page.$eval('.ma-tab.active', el => el.textContent.trim()).catch(() => '?');
      console.log(`  [${theme}] ${name} active tab = ${active}`);
      await shot(name);
    }

    // ── 토스트(성공=녹) ──
    await page.evaluate(() => { if (window.mmToast) window.mmToast('저장되었습니다', 'ok'); });
    await page.waitForTimeout(700);
    await shot('toast_ok');
    await page.evaluate(() => { if (window.mmToast) window.mmToast('저장에 실패했습니다', 'err'); });
    await page.waitForTimeout(700);
    await shot('toast_err');

    // ── 계산기: 비중 합계 초과 경고(=위험 적색) ──
    await page.goto(BASE + '/calculator', { waitUntil: 'networkidle' });
    await page.evaluate(t => document.documentElement.setAttribute('data-theme', t), theme);
    await page.waitForTimeout(2500);
    const w = page.locator('input.weight-input, input[class*="weight"]').first();
    if (await w.count()) { await w.fill('180').catch(() => {}); await w.dispatchEvent('input').catch(() => {}); await page.waitForTimeout(900); }
    await shot('calc_weight_over');

    // ── 설정: 위험 영역(탈퇴/삭제 버튼) ──
    await page.goto(BASE + '/settings', { waitUntil: 'networkidle' });
    await page.evaluate(t => document.documentElement.setAttribute('data-theme', t), theme);
    await page.waitForTimeout(2000);
    await shot('settings');

    // ── 백테스트 입력 화면(취소/경고 버튼 색) ──
    await page.goto(BASE + '/backtest', { waitUntil: 'networkidle' });
    await page.evaluate(t => document.documentElement.setAttribute('data-theme', t), theme);
    await page.waitForTimeout(2000);
    await shot('backtest_input');

    if (errs.length) { console.log(`[${theme}] console errors ${errs.length}`); errs.slice(0, 10).forEach(e => console.log('   ' + e.slice(0, 200))); }
    else console.log(`[${theme}] console errors 0`);
    await ctx.close();
  }
  await browser.close();
  console.log('shots -> ' + DIR);
})();
