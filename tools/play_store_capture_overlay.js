// 추세 겹쳐보기(비교) 화면을 Play Store promo용으로 캡처.
// 로컬 서버(실 price_daily) 필요. usage: node tools/play_store_capture_overlay.js <sessionCookie>
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const RAW = path.join(ROOT, 'store-assets', 'play-store-graphics-20260704', 'raw');
const BASE = 'http://127.0.0.1:5000';
const COOKIE = process.argv[2];
if (!COOKIE) { console.error('need session cookie'); process.exit(2); }

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2,
    isMobile: true, hasTouch: true, locale: 'ko-KR',
  });
  await ctx.addCookies([{ name: 'session', value: COOKIE, url: BASE, sameSite: 'Lax' }]);
  await ctx.addInitScript(() => { localStorage.setItem('mm-theme', 'light'); localStorage.setItem('mm-accent', 'orange'); });
  const page = await ctx.newPage();

  await page.goto(`${BASE}/risk-return`, { waitUntil: 'networkidle' });
  // 깨끗한 3종목만
  await page.evaluate(() => { rrOv.items = []; rrOv.raw = {}; });
  await page.evaluate(() => {
    rrOvAdd('SYM:069500', '코스피200');
    rrOvAdd('SYM:458730', '미국배당다우존스');
    rrOvAdd('SYM:GLD', '금');
  });
  // 스피너 사라지고(로딩 완료) 실데이터(연도>2005) 들어올 때까지 대기
  await page.waitForFunction(() => {
    const sp = document.getElementById('rrOvSpinner');
    const hidden = !sp || getComputedStyle(sp).display === 'none';
    const ch = window.rrOv && rrOv.chart;
    const labs = ch && ch.data.labels;
    const okLabels = labs && labs.length > 20 && (+new Date(labs[labs.length - 1]) > +new Date('2005-01-01'));
    return hidden && okLabels;
  }, undefined, { timeout: 120000 });
  await page.waitForTimeout(700);

  // 전체화면(도구 닫힘) — 차트가 화면을 꽉 채운 우리 신기능 그대로
  await page.evaluate(() => rrOvEnterFullscreen());
  await page.waitForTimeout(700);
  try { await page.evaluate(() => document.fonts && document.fonts.ready); } catch (_) {}
  await page.screenshot({ path: path.join(RAW, 'phone-07-overlay.png'), fullPage: false });
  console.log('saved raw/phone-07-overlay.png');
  await browser.close();
})();
