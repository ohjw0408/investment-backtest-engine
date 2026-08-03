/**
 * 포트폴리오 비교 — 벤치마크 상한 완화(12→20) 실브라우저 검증.
 *
 * 배경(2026-08-03): rrAddBench가 상한 초과 시 **무음 return** 이라 사용자에겐
 * "10개쯤부터 버튼이 안 먹는다"로 보였다. 상한을 20으로 올리고 초과 시 토스트를 띄운다.
 *
 * 실행: node tests/test_compare_bench_cap_browser.js <sessionCookie> [baseUrl]
 */
const { chromium } = require('playwright');

const COOKIE = process.argv[2];
const BASE = process.argv[3] || 'http://127.0.0.1:5000';
if (!COOKIE) { console.error('usage: node test_compare_bench_cap_browser.js <sessionCookie>'); process.exit(2); }

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name + (extra ? '  → ' + extra : '')); }
}

// 개별종목 + ETF + 지수 혼합 (오너 시나리오: "개별종목이랑 etf랑 지수랑 막 섞어서")
const MIX = ['AAPL','MSFT','NVDA','TSLA','AMZN','GOOGL','META','JPM','V','MA',
             'IWM','VTI','SCHD','IEF','^DJI','^RUT','^SOX','^IXIC','KO','PEP',
             'XOM','WMT'];

(async () => {
  const browser = await chromium.launch();
  for (const theme of ['light', 'dark']) {
    const ctx = await browser.newContext({ colorScheme: theme });
    await ctx.addCookies([{ name: 'session', value: COOKIE, domain: new URL(BASE).hostname, path: '/' }]);
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

    await page.goto(BASE + '/risk-return', { waitUntil: 'networkidle' });

    // 상한 상수가 실제로 20인가
    const cap = await page.evaluate(() => (typeof RR_MAX_BENCH !== 'undefined' ? RR_MAX_BENCH : null));
    ok(`[${theme}] RR_MAX_BENCH === 20`, cap === 20, 'cap=' + cap);

    const before = await page.evaluate(() => rrBench.length);
    ok(`[${theme}] 기본 벤치마크 5개`, before === 5, 'len=' + before);

    // 상한까지 추가 — 실제 rrAddBench 경로(검색 드롭다운이 부르는 그 함수)로
    const atCap = await page.evaluate((mix) => {
      for (const c of mix) { if (rrBench.length >= 20) break; rrAddBench(c, c); }
      return rrBench.length;
    }, MIX);
    ok(`[${theme}] 20개까지 추가됨 (기존 12 상한이면 12에서 멈춤)`, atCap === 20, 'len=' + atCap);

    // 칩이 실제로 20개 렌더됐는가 (DOM 확인 — 상태만 바뀌고 화면이 안 따라오면 실패)
    const chips = await page.locator('#rrChips .rr-chip').count();
    ok(`[${theme}] 칩 20개 렌더`, chips === 20, 'chips=' + chips);

    // 21번째 = 거부 + 토스트(무음 실패 금지)
    const over = await page.evaluate(() => { rrAddBench('__OVER__', '__OVER__'); return rrBench.length; });
    ok(`[${theme}] 21번째는 거부`, over === 20, 'len=' + over);
    const toast = await page.locator('text=최대 20개까지').first();
    ok(`[${theme}] 상한 초과 토스트 노출(무음 실패 아님)`, await toast.isVisible().catch(() => false));

    // 제거 후 재추가 가능 (상한 로직이 한 번 걸리면 영구 잠기지 않는지)
    const reAdd = await page.evaluate(() => {
      rrRemoveBench(0);
      const afterRemove = rrBench.length;
      rrAddBench('__NEW__', '__NEW__');
      return [afterRemove, rrBench.length];
    });
    ok(`[${theme}] 제거 후 재추가 가능`, reAdd[0] === 19 && reAdd[1] === 20, JSON.stringify(reAdd));

    await page.screenshot({ path: `design-shots/compare-bench-cap-${theme}.png`, fullPage: false });
    ok(`[${theme}] 콘솔 에러 0`, errors.length === 0, errors.slice(0, 3).join(' | '));
    await ctx.close();
  }

  // 서버 상한도 20인가 — 프런트만 올리면 서버가 조용히 잘라 "일부만 나온다"가 된다
  {
    const ctx = await browser.newContext();
    await ctx.addCookies([{ name: 'session', value: COOKIE, domain: new URL(BASE).hostname, path: '/' }]);
    const page = await ctx.newPage();
    await page.goto(BASE + '/risk-return', { waitUntil: 'domcontentloaded' });
    // portfolio_ids:[] 로 저장 포폴을 배제해야 벤치마크만 남는다
    // (키 자체를 빼면 서버가 "전체 저장 포폴"로 해석해 items에 섞인다)
    const res = await page.evaluate(async (mix) => {
      const codes = mix.slice(0, 20);
      const r = await fetch('/api/portfolio/compare', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ portfolio_ids: [], benchmarks: codes.map(c => ({ code: c, name: c })) }),
      }).then(x => x.json());
      const names = (r.items || []).map(i => i.name);
      return { total: names.length, missing: codes.filter(c => !names.includes(c)) };
    }, MIX);
    ok('서버가 벤치마크 20개 전부 산출 (15 상한이면 5개 누락)',
       res.missing.length === 0, 'missing=' + JSON.stringify(res.missing) + ' total=' + res.total);
    await ctx.close();
  }

  await browser.close();
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
