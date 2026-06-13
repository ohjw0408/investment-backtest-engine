/**
 * A4 종목 상세 실브라우저 검증 (로그인 불필요 — 공개 페이지).
 * 실행: node tests/test_symbol_browser.js [baseUrl]
 *
 * 검증: 자산타입별 배지/지표 분기, 라인/캔들 토글, 1일/1주 시간봉 탭, JS 에러 0.
 */
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:5000';

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}

async function loadSymbol(ctx, code) {
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(`${BASE}/symbol/${code}`, { waitUntil: 'networkidle' });
  await page.waitForSelector('.symbol-header', { timeout: 60000 });
  return { page, errors };
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();

  // ── 1. US ETF (SPY) ──────────────────────────────
  {
    const { page, errors } = await loadSymbol(ctx, 'SPY');
    const badge = (await page.textContent('.symbol-badge')).trim();
    ok('SPY 배지 = US ETF', badge === 'US ETF');
    const labels = await page.$$eval('.stat-label', els => els.map(e => e.textContent));
    ok('ETF 지표: 운용사 표시', labels.includes('운용사'));
    ok('ETF 지표: 보수율 표시', labels.includes('보수율'));
    ok('ETF 지표: PER 미표시', !labels.includes('PER'));
    ok('배당 내역 카드 존재(ETF)', !!(await page.$('.div-table, .symbol-card')));

    // 라인 차트 기본 — 라인 탭 = 표시기간(1일/1주/1개월/3개월/1년/전체)
    ok('라인 차트(Chart.js) 렌더', await page.evaluate(() => chartInst !== null));
    const lineTabs = await page.$$eval('#periodTabs .period-tab', els => els.map(e => e.textContent));
    ok('라인 탭 세트 = 표시기간', JSON.stringify(lineTabs) === JSON.stringify(['1일','1주','1개월','3개월','1년','전체']));

    // 라인 1일 — 시간봉(하루 변동)
    await page.click('.period-tab[data-period="1D"]');
    await page.waitForTimeout(3500);
    ok('라인 1일 = 시간봉 표시', await page.evaluate(() => chartInst !== null) &&
       (await page.textContent('#chartHint')).includes('시간봉'));

    // 캔들 토글 → 탭 세트가 "캔들 간격"으로 교체
    await page.click('.ctype-btn[data-ctype="candle"]');
    await page.waitForTimeout(800);
    const candleTabs = await page.$$eval('#periodTabs .period-tab', els => els.map(e => e.textContent));
    ok('캔들 탭 세트 = 캔들 간격', JSON.stringify(candleTabs) === JSON.stringify(['1시간','1일','1주','1개월','1년']));
    ok('캔들 차트(Lightweight) 렌더', await page.evaluate(() =>
      candleChart !== null && !!document.querySelector('#candleChart canvas')));
    ok('캔들 힌트 = 전체 기간', (await page.textContent('#chartHint')).includes('전체 기간'));

    // 캔들 1주 — 일봉 리샘플(전체기간, 캔들 하나=1주). 점수 < 1일 캔들 점수.
    const nDay = await page.evaluate(() => candleSeries.data().length);
    await page.click('.period-tab[data-period="1W"]');
    await page.waitForTimeout(800);
    const nWeek = await page.evaluate(() => candleSeries.data().length);
    ok('캔들 1주 = 1일보다 적은 봉수(리샘플)', nWeek > 0 && nWeek < nDay);

    // 캔들 1시간 — 730일 시간봉 fetch
    await page.click('.period-tab[data-period="1H"]');
    await page.waitForTimeout(8000);
    ok('캔들 1시간 렌더(730일 시간봉)', await page.evaluate(() =>
      candleChart !== null && candleSeries.data().length > 100));

    // 전체화면 버튼 존재
    ok('전체화면 버튼 존재', !!(await page.$('#fsBtn')));

    // 라인 복귀 — 탭 세트도 복귀
    await page.click('.ctype-btn[data-ctype="line"]');
    await page.waitForTimeout(600);
    const back = await page.$$eval('#periodTabs .period-tab', els => els.map(e => e.textContent));
    ok('라인 복귀 + 탭 세트 복귀', await page.evaluate(() => chartInst !== null) &&
       back[0] === '1일' && back.length === 6);

    ok('SPY JS 에러 0', errors.length === 0);
    if (errors.length) console.log('  errors:', errors.slice(0, 3));
    await page.close();
  }

  // ── 2. KR 주식 (삼성전자 005930) ──────────────────
  {
    const { page, errors } = await loadSymbol(ctx, '005930');
    const badge = (await page.textContent('.symbol-badge')).trim();
    ok('005930 배지 = KR 주식', badge === 'KR 주식');
    const labels = await page.$$eval('.stat-label', els => els.map(e => e.textContent));
    ok('주식 지표: PER 표시', labels.includes('PER'));
    ok('주식 지표: PBR 표시', labels.includes('PBR'));
    ok('주식 지표: 섹터 표시', labels.includes('섹터'));
    ok('주식 지표: 운용사 미표시', !labels.includes('운용사'));
    ok('주식 지표: 시가총액 표시', labels.includes('시가총액'));
    ok('005930 JS 에러 0', errors.length === 0);
    if (errors.length) console.log('  errors:', errors.slice(0, 3));
    await page.close();
  }

  // ── 3a. 지수 (^KS11) — price_daily OHLC 보유 → 캔들 정상 ──
  {
    const { page, errors } = await loadSymbol(ctx, '%5EKS11');
    const badge = (await page.textContent('.symbol-badge')).trim();
    ok('^KS11 배지 = 지수/선물', badge === '지수/선물');
    await page.click('.ctype-btn[data-ctype="candle"]');
    await page.waitForTimeout(800);
    ok('^KS11 캔들 렌더(OHLC 보유)', await page.evaluate(() =>
      candleChart !== null && !!document.querySelector('#candleChart canvas')));
    ok('^KS11 JS 에러 0', errors.length === 0);
    await page.close();
  }

  // ── 3b. KRX_GOLD — close만(OHLC 없음) → 캔들 토글 비활성 ──
  {
    const { page, errors } = await loadSymbol(ctx, 'KRX_GOLD');
    const disabled = await page.evaluate(() =>
      document.querySelector('.ctype-btn[data-ctype="candle"]').classList.contains('disabled'));
    ok('KRX_GOLD 캔들 토글 비활성(close만)', disabled);
    ok('KRX_GOLD JS 에러 0', errors.length === 0);
    await page.close();
  }

  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL  (${BASE})`);
  process.exit(fail ? 1 : 0);
})();
