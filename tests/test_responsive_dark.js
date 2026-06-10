/**
 * 반응형 + 다크모드 실브라우저 검증 — 전 페이지 × 뷰포트 × 테마 스크린샷.
 * 실행: node tests/test_responsive_dark.js [BASE_URL] [SCREENSHOT_DIR]
 * 기본: http://127.0.0.1:5000, tests/shots
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const SHOT_DIR = process.argv[3] || path.join(__dirname, 'shots');
fs.mkdirSync(SHOT_DIR, { recursive: true });

const PAGES = [
  ['home', '/'],
  ['calculator', '/calculator'],
  ['dividend', '/dividend-target'],
  ['simple', '/simple'],
  ['retirement', '/retirement'],
  ['backtest', '/backtest'],
  ['myassets', '/myassets'],
  ['taxsettings', '/tax-settings'],
  ['search', '/search'],
];

const VIEWPORTS = [
  ['mobile390', { width: 390, height: 844 }],
  ['tablet768', { width: 768, height: 1024 }],
  ['laptop1280', { width: 1280, height: 800 }],
];

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name + (extra ? ' — ' + extra : '')); }
}

(async () => {
  const browser = await chromium.launch();

  for (const theme of ['light', 'dark']) {
    const ctx = await browser.newContext();
    // 테마 고정 (FOUC 스크립트가 localStorage 우선)
    await ctx.addInitScript(t => { try { localStorage.setItem('mm-theme', t); } catch (e) {} }, theme);

    for (const [vpName, vp] of VIEWPORTS) {
      const page = await ctx.newPage({ viewport: vp });
      await page.setViewportSize(vp);

      for (const [name, url] of PAGES) {
        const errors = [];
        page.on('pageerror', e => errors.push(String(e)));
        const consoleErrs = [];
        page.on('console', m => { if (m.type() === 'error') consoleErrs.push(m.text()); });

        try {
          await page.goto(BASE + url, { waitUntil: 'networkidle', timeout: 20000 });
        } catch (e) {
          await page.goto(BASE + url, { waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {});
        }
        await page.waitForTimeout(400);

        // 가로 오버플로우 검사 (스크롤 폭 > 뷰포트 폭 + 1)
        const overflow = await page.evaluate(() => {
          const d = document.documentElement;
          return d.scrollWidth - d.clientWidth;
        });
        ok(`${theme}/${vpName}/${name} 가로 오버플로우 없음`, overflow <= 1, `scrollWidth 초과 ${overflow}px`);

        // 테마 적용 확인
        const applied = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
        ok(`${theme}/${vpName}/${name} 테마 적용`, applied === theme, `actual=${applied}`);

        // JS 런타임 에러 0 (네트워크 4xx 콘솔 에러는 허용)
        const jsErrs = errors.filter(e => !/40[0-9]|50[0-9]|Failed to load resource/i.test(e));
        ok(`${theme}/${vpName}/${name} JS 에러 0`, jsErrs.length === 0, jsErrs.slice(0, 2).join(' | '));

        await page.screenshot({ path: path.join(SHOT_DIR, `${name}-${vpName}-${theme}.png`), fullPage: false });
        page.removeAllListeners('pageerror');
        page.removeAllListeners('console');
      }
      await page.close();
    }
    await ctx.close();
  }

  // 모바일 드로어 동작 검증
  const ctx2 = await browser.newContext();
  const p2 = await ctx2.newPage({ viewport: { width: 390, height: 844 } });
  await p2.setViewportSize({ width: 390, height: 844 });
  await p2.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  const burgerVisible = await p2.isVisible('#navHamburger');
  ok('모바일 햄버거 노출', burgerVisible);
  await p2.click('#navHamburger');
  await p2.waitForTimeout(350);
  const drawerOpen = await p2.evaluate(() => document.getElementById('sidebar').classList.contains('open'));
  ok('드로어 열림', drawerOpen);
  await p2.screenshot({ path: path.join(SHOT_DIR, 'drawer-open.png') });
  await p2.mouse.click(340, 420); // 드로어(250px) 바깥 영역 = 오버레이
  await p2.waitForTimeout(350);
  const drawerClosed = await p2.evaluate(() => !document.getElementById('sidebar').classList.contains('open'));
  ok('오버레이 클릭 닫힘', drawerClosed);

  // 데스크톱: 1280px에서 상단 링크 숨김(BUG-NAV-1), 1500px에서 노출
  await p2.setViewportSize({ width: 1280, height: 800 });
  await p2.waitForTimeout(200);
  ok('1280px 상단 링크 숨김', !(await p2.isVisible('.nav-links')));
  await p2.setViewportSize({ width: 1500, height: 800 });
  await p2.waitForTimeout(200);
  ok('1500px 상단 링크 노출', await p2.isVisible('.nav-links'));

  // 테마 토글 버튼 동작 (클릭 → 리로드 → data-theme 전환)
  await p2.click('#themeToggle');
  await p2.waitForLoadState('domcontentloaded');
  await p2.waitForTimeout(300);
  const toggled = await p2.evaluate(() => document.documentElement.getAttribute('data-theme'));
  ok('테마 토글 → dark 전환', toggled === 'dark', `actual=${toggled}`);

  await ctx2.close();
  await browser.close();

  console.log(`\n총 ${pass} PASS / ${fail} FAIL`);
  process.exit(fail > 0 ? 1 : 0);
})();
