/**
 * 등락색 한국식 전환 검증 — 상승=적, 하락=청 / 상태색(성공=녹, 위험=적)은 분리 유지.
 * 실행: node tests/test_direction_colors.js [BASE_URL] [SHOT_DIR]
 * 기본: http://127.0.0.1:5000, tests/shots_direction
 *
 * 검증 방식: 실제 렌더된 페이지에 프로브 엘리먼트를 주입해 computed color 를 읽는다
 * (토큰이 실제로 적용되는지 = 하드코딩 잔재가 덮어쓰지 않는지 확인).
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const SHOT_DIR = process.argv[3] || path.join(__dirname, 'shots_direction');
fs.mkdirSync(SHOT_DIR, { recursive: true });

const PAGES = [
  ['home', '/'],
  ['myassets', '/myassets'],
  ['backtest', '/backtest'],
  ['calculator', '/calculator'],
  ['retirement', '/retirement'],
  ['dividend', '/dividend-target'],
  ['search', '/search'],
  ['market', '/market'],
  ['macro', '/macro'],
  ['calendar', '/calendar'],
  ['settings', '/settings'],
  ['symbol', '/symbol/005930'],
  ['examples', '/examples'],
  ['taxswitch', '/tax-switch'],
  ['alerts', '/alerts'],
  ['simple', '/simple'],
  ['riskreturn', '/risk-return'],
];

// 기대 색 (light / dark)
const EXPECT = {
  light: { up: 'rgb(224, 52, 44)', down: 'rgb(21, 101, 216)', ok: 'rgb(5, 177, 105)', danger: 'rgb(207, 32, 47)' },
  dark:  { up: 'rgb(255, 107, 107)', down: 'rgb(77, 155, 255)', ok: 'rgb(39, 194, 129)', danger: 'rgb(255, 90, 95)' },
};

let pass = 0, fail = 0;
const failures = [];
function ok(name, cond, extra) {
  if (cond) { pass++; }
  else { fail++; failures.push(name + (extra ? ' — ' + extra : '')); }
}

function mintCookie() {
  try {
    const out = execFileSync(path.join(__dirname, '..', 'venv', 'Scripts', 'python.exe'),
      [path.join(__dirname, 'mint_session.py')], { cwd: path.join(__dirname, '..'), encoding: 'utf-8' });
    return out.trim().split('\n').pop().trim();
  } catch (e) {
    console.log('WARN  세션 쿠키 발급 실패 — 로그인 페이지는 건너뜀: ' + e.message);
    return null;
  }
}

(async () => {
  const cookie = mintCookie();
  const browser = await chromium.launch();

  for (const theme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    if (cookie) {
      await ctx.addCookies([{ name: 'session', value: cookie, domain: '127.0.0.1', path: '/' }]);
    }
    const page = await ctx.newPage();
    const consoleErrors = [];
    page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });

    for (const [name, url] of PAGES) {
      try {
        await page.goto(BASE + url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      } catch (e) { ok(`${theme}/${name} load`, false, e.message); continue; }

      await page.evaluate(t => {
        document.documentElement.setAttribute('data-theme', t);
        try { localStorage.setItem('theme', t); } catch (e) {}
      }, theme);
      await page.waitForTimeout(400);

      // 토큰 프로브
      const got = await page.evaluate(() => {
        const mk = v => {
          const el = document.createElement('span');
          el.style.color = `var(${v})`;
          el.style.position = 'fixed'; el.style.left = '-9999px';
          document.body.appendChild(el);
          const c = getComputedStyle(el).color;
          el.remove();
          return c;
        };
        return {
          up: mk('--up'), down: mk('--down'), ok: mk('--ok'), danger: mk('--danger'),
          green: mk('--green'), red: mk('--red'),
        };
      });

      const exp = EXPECT[theme];
      ok(`${theme}/${name} --up=적`,     got.up === exp.up,         `got ${got.up}`);
      ok(`${theme}/${name} --down=청`,   got.down === exp.down,     `got ${got.down}`);
      ok(`${theme}/${name} --ok=녹`,     got.ok === exp.ok,         `got ${got.ok}`);
      ok(`${theme}/${name} --danger=적`, got.danger === exp.danger, `got ${got.danger}`);
      // 레거시 별칭이 상태색을 따라가는지 (등락색이 아니라)
      ok(`${theme}/${name} --green→ok`,  got.green === exp.ok,      `got ${got.green}`);
      ok(`${theme}/${name} --red→danger`,got.red === exp.danger,    `got ${got.red}`);

      // 실제 .up/.down 엘리먼트가 있으면 색 확인
      const live = await page.evaluate(() => {
        const out = [];
        document.querySelectorAll('.up, .down, .ds-up, .ds-down, .market-change, .portfolio-change, .symbol-change, .card-change, .hc-ret, .metric-value')
          .forEach(el => {
            if (!el.offsetParent) return;
            const cls = el.className.toString();
            if (/\bup\b/.test(cls)) out.push(['up', getComputedStyle(el).color]);
            else if (/\bdown\b/.test(cls)) out.push(['down', getComputedStyle(el).color]);
          });
        return out.slice(0, 40);
      });
      live.forEach(([dir, col], i) => {
        ok(`${theme}/${name} live .${dir}[${i}]`, col === exp[dir], `got ${col}`);
      });

      await page.screenshot({ path: path.join(SHOT_DIR, `${name}_${theme}.png`), fullPage: true });
    }

    if (consoleErrors.length) {
      console.log(`\n[${theme}] 콘솔 에러 ${consoleErrors.length}건:`);
      consoleErrors.slice(0, 10).forEach(e => console.log('   ' + e.slice(0, 200)));
    }
    await ctx.close();
  }

  await browser.close();
  console.log(`\nPASS ${pass} / FAIL ${fail}`);
  if (failures.length) { console.log('\n실패 목록:'); failures.forEach(f => console.log('  FAIL ' + f)); }
  process.exit(fail ? 1 : 0);
})();
