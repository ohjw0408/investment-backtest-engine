/**
 * 결과 뷰(백테·계산기·은퇴·배당) 등락색 프로브.
 * 결과 화면은 celery 워커가 있어야 렌더돼서 로컬에서 실행할 수 없다 → 결과 뷰가 쓰는
 * 셀렉터를 페이지에 직접 심어 CSS 계약(.up=적 / .down=청)이 성립하는지 확인한다.
 * (JS 쪽은 클래스명만 붙이므로 — fmtPctClass 등 — 색은 전적으로 이 CSS가 결정한다.)
 *
 * 실행: node tests/probe_result_view_colors.js [BASE_URL]
 */
const { chromium } = require('playwright');
const path = require('path');
const { execFileSync } = require('child_process');

const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const EXP = {
  light: { up: 'rgb(224, 52, 44)', down: 'rgb(21, 101, 216)' },
  dark:  { up: 'rgb(255, 107, 107)', down: 'rgb(77, 155, 255)' },
};

// [페이지, 부모 마크업, 검사할 자식 클래스, 상승 클래스, 하락 클래스]
// 페이지마다 상승/하락 클래스명이 다르다(백테=up/down, 계산기·배당=opt/pess).
const CASES = [
  ['/backtest',        '<div class="metric-card">',   'metric-value', 'up',  'down'],
  ['/backtest',        '<div class="bt-hero-sub2">',  '',             'up',  'down'],
  ['/calculator',      '<div class="bt-hero-sub2">',  '',             'opt', 'pess'],
  ['/dividend-target', '<div class="bt-hero-sub2">',  '',             'opt', 'pess'],
  ['/myassets',        '<div class="ps-row">',        '',             'up',  'down'],
  ['/search',          '<div class="sp-card">',       'card-change',  'up',  'down'],
  ['/market',          '<div class="mk-item">',       'mk-item-chg',  'up',  'down'],
];

function mintCookie() {
  const out = execFileSync(path.join(__dirname, '..', 'venv', 'Scripts', 'python.exe'),
    [path.join(__dirname, 'mint_session.py')], { cwd: path.join(__dirname, '..'), encoding: 'utf-8' });
  return out.trim().split('\n').pop().trim();
}

(async () => {
  const cookie = mintCookie();
  const browser = await chromium.launch();
  let pass = 0, fail = 0;

  for (const theme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await ctx.addCookies([{ name: 'session', value: cookie, domain: '127.0.0.1', path: '/' }]);
    await ctx.addInitScript(t => { try { localStorage.setItem('theme', t); } catch (e) {} }, theme);
    const page = await ctx.newPage();

    for (const [url, wrapper, childCls, upCls, downCls] of CASES) {
      await page.goto(BASE + url, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
      await page.evaluate(t => document.documentElement.setAttribute('data-theme', t), theme);
      await page.waitForTimeout(600);

      const got = await page.evaluate(([w, c, uc, dc]) => {
        const host = document.createElement('div');
        const cls = c ? c + ' ' : '';
        host.innerHTML = `${w}<span class="${cls}${uc}" id="_pu">+1.0%</span>` +
                         `<span class="${cls}${dc}" id="_pd">-1.0%</span></div>`;
        document.body.appendChild(host);
        const r = { up: getComputedStyle(host.querySelector('#_pu')).color,
                    down: getComputedStyle(host.querySelector('#_pd')).color };
        host.remove();
        return r;
      }, [wrapper, childCls, upCls, downCls]);

      const e = EXP[theme];
      const label = `${theme} ${url} ${wrapper.match(/class="([^"]+)"/)[1]}${childCls ? '>' + childCls : ''} (${upCls}/${downCls})`;
      for (const dir of ['up', 'down']) {
        if (got[dir] === e[dir]) pass++;
        else { fail++; console.log(`  FAIL ${label} .${dir}  got=${got[dir]} want=${e[dir]}`); }
      }
    }
    await ctx.close();
  }
  await browser.close();
  console.log(`\nPASS ${pass} / FAIL ${fail}`);
  process.exit(fail ? 1 : 0);
})();
