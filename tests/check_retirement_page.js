/** 은퇴 탭 가상데이터 체크박스 배선 스모크 — 로컬 Flask 대상, JS 에러 0 + 요소 존재 + body 필드. */
'use strict';
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:5000';

let pass = 0, fail = 0;
const ok = (n, c, x) => { if (c) { pass++; console.log('PASS  ' + n); } else { fail++; console.log('FAIL  ' + n + (x ? ' — ' + x : '')); } };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(BASE + '/retirement', { waitUntil: 'networkidle' });

  ok('체크박스 존재', await page.isVisible('#retUseSyntheticCheck'));
  ok('가상 윈도우 노트 요소 존재(숨김)', (await page.locator('#retWdSynthNote').count()) === 1);

  // body 빌드 경로 — 체크 시 use_synthetic=true로 submit 페이로드에 실림 (fetch 가로채기)
  await page.check('#retUseSyntheticCheck');
  const captured = await page.evaluate(async () => {
    let body = null;
    const orig = window.fetch;
    window.fetch = async (url, opts) => {
      if (String(url).includes('/api/retirement/submit')) {
        body = JSON.parse(opts.body);
        return new Response(JSON.stringify({ task_id: null, error: 'smoke' }), { status: 429 });
      }
      return orig(url, opts);
    };
    // 종목 1개 주입 후 실행 (검색 경유 없이 전역 직접 — 스모크 한정)
    retTickers.push({ code: '360750', name: 'T', weight: 1.0 });
    try { await runRetirement(); } catch (e) {}
    window.fetch = orig;
    return body;
  });
  ok('sim body.use_synthetic = true', captured && captured.use_synthetic === true);
  ok('브라우저 에러 0', errors.length === 0, errors.join(' | '));

  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
