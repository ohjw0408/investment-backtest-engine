/**
 * 등락색 육안 확인용 스샷 — 데이터가 실제로 그려질 때까지 기다린 뒤 캡처.
 * 실행: node tests/shot_direction_visual.js [BASE_URL]
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const DIR = path.join(__dirname, 'shots_direction_visual');
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

    const go = async (url, waitMs) => {
      await page.goto(BASE + url, { waitUntil: 'networkidle', timeout: 60000 }).catch(() => {});
      await page.evaluate(t => document.documentElement.setAttribute('data-theme', t), theme);
      await page.waitForTimeout(waitMs || 3000);
    };
    const shot = n => page.screenshot({ path: path.join(DIR, `${n}_${theme}.png`), fullPage: true });

    await go('/', 6000);            await shot('home');
    await go('/myassets', 8000);    await shot('myassets');
    await go('/market', 6000);      await shot('market');
    await go('/symbol/005930', 9000); await shot('symbol_line');
    // 캔들 탭
    const candle = await page.$('text=캔들');
    if (candle) { await candle.click().catch(() => {}); await page.waitForTimeout(5000); await shot('symbol_candle'); }
    await go('/macro', 8000);       await shot('macro');
    await go('/calendar', 6000);    await shot('calendar');
    await go('/search?q=삼성', 6000); await shot('search');
    await go('/settings', 4000);    await shot('settings');

    if (errs.length) {
      console.log(`[${theme}] console errors ${errs.length}`);
      errs.slice(0, 12).forEach(e => console.log('   ' + e.slice(0, 220)));
    } else console.log(`[${theme}] console errors 0`);
    await ctx.close();
  }
  await browser.close();
  console.log('shots -> ' + DIR);
})();
