/**
 * 실제 렌더된 등락 표기 엘리먼트의 computed color 전수 프로브.
 * 실행: node tests/probe_direction_dom.js [BASE_URL]
 * "+숫자%" 는 적, "-숫자%" 는 청 이어야 한다(상태 뱃지·중립 제외).
 */
const { chromium } = require('playwright');
const path = require('path');
const { execFileSync } = require('child_process');

const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const UP = 'rgb(224, 52, 44)', DOWN = 'rgb(21, 101, 216)';
const UP_D = 'rgb(255, 107, 107)', DOWN_D = 'rgb(77, 155, 255)';

const PAGES = ['/', '/myassets', '/market', '/symbol/005930', '/macro', '/search?q=삼성'];

function mintCookie() {
  const out = execFileSync(path.join(__dirname, '..', 'venv', 'Scripts', 'python.exe'),
    [path.join(__dirname, 'mint_session.py')], { cwd: path.join(__dirname, '..'), encoding: 'utf-8' });
  return out.trim().split('\n').pop().trim();
}

(async () => {
  const cookie = mintCookie();
  const browser = await chromium.launch();
  let bad = 0, seen = 0;

  for (const theme of ['light', 'dark']) {
    const up = theme === 'light' ? UP : UP_D, down = theme === 'light' ? DOWN : DOWN_D;
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await ctx.addCookies([{ name: 'session', value: cookie, domain: '127.0.0.1', path: '/' }]);
    await ctx.addInitScript(t => { try { localStorage.setItem('theme', t); } catch (e) {} }, theme);
    const page = await ctx.newPage();

    for (const url of PAGES) {
      await page.goto(BASE + url, { waitUntil: 'networkidle', timeout: 60000 }).catch(() => {});
      await page.evaluate(t => document.documentElement.setAttribute('data-theme', t), theme);
      await page.waitForTimeout(5000);

      const rows = await page.evaluate(() => {
        const out = [];
        const walk = document.querySelectorAll('span, td, div, b, strong');
        walk.forEach(el => {
          if (el.children.length) return;                 // leaf 만
          const t = (el.textContent || '').trim();
          // "+1.23%" / "-1.23%" / "▲ ... %" / "▼ ... %" 형태만
          const m = /^([+\-▲▼↑↓])\s*[₩$]?[\d,.]+%?/.exec(t);
          if (!m) return;
          if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') return;
          const cs = getComputedStyle(el);
          out.push({ sign: m[1], text: t.slice(0, 24), color: cs.color,
                     cls: (el.className || '').toString().slice(0, 40) });
        });
        return out;
      });

      rows.forEach(r => {
        const isUp = ['+', '▲', '↑'].includes(r.sign);
        const want = isUp ? up : down;
        seen++;
        // inherit(=본문색) 은 의도적 중립일 수 있어 경고만
        if (r.color !== want) {
          bad++;
          console.log(`  MISMATCH [${theme}] ${url}  "${r.text}"  cls=${r.cls}  got=${r.color}  want=${want}`);
        }
      });
    }
    await ctx.close();
  }
  await browser.close();
  console.log(`\n검사 ${seen}건 / 불일치 ${bad}건`);
})();
