/**
 * 내자산 배당금 차트(연도선택+막대드릴다운+캘린더) 실브라우저 검증 (로그인 필요, 로컬).
 * 실행: node tests/test_dividend_chart_browser.js <sessionCookie> [baseUrl]
 */
const { chromium } = require('playwright');
const COOKIE = process.argv[2];
const BASE   = process.argv[3] || 'http://127.0.0.1:5000';
if (!COOKIE) { console.error('usage: node test_dividend_chart_browser.js <sessionCookie>'); process.exit(2); }

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  await ctx.addCookies([{ name: 'session', value: COOKIE, domain: new URL(BASE).hostname, path: '/' }]);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  // 시드: SCHD(US 일반) + 458730(KR ISA)
  await page.goto(BASE + '/myassets', { waitUntil: 'networkidle' });
  await page.evaluate(async () => {
    const items = await fetch('/api/myassets/data').then(r => r.json());
    for (const h of (items.holdings || []).filter(x => ['SCHD', '458730'].includes(x.code)))
      await fetch('/api/myassets/holding/' + h.id, { method: 'DELETE' });
    await fetch('/api/myassets/holding', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: 'SCHD', quantity: 100, account_type: '일반' }) });
    await fetch('/api/myassets/holding', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: '458730', quantity: 50, account_type: 'ISA' }) });
  });

  await page.goto(BASE + '/myassets', { waitUntil: 'networkidle' });
  await page.waitForFunction("typeof _divChart !== 'undefined' && _divChart !== null", { timeout: 30000 });

  // 연도 선택기 — 과거3 + 올해(혼합) + 내년(예측) = 5탭, 기본 = 올해
  const Y = new Date().getFullYear();
  const yearTabs = await page.$$eval('#divYearTabs .div-tgl', els => els.map(e => e.textContent));
  ok('연도 선택기 5개(과거3+올해+내년)', yearTabs.length === 5);
  ok('올해 (진행) 라벨', yearTabs[3].includes(String(Y)) && yearTabs[3].includes('진행'));
  ok('내년 (예측) 라벨', yearTabs[4].includes(String(Y + 1)) && yearTabs[4].includes('예측'));
  const defActive = await page.$eval('#divYearTabs .div-tgl.active', e => e.textContent);
  ok('기본 선택 = 올해', defActive.includes(String(Y)));
  // 올해 = 실적+예측 혼합
  ok('올해 이벤트 = 실적+예측 혼합', await page.evaluate(y => {
    const evs = _divData.events[y]; if (!evs || !evs.length) return false;
    return evs.some(e => !e.projected) && evs.some(e => e.projected);
  }, Y));

  // 단일 연도 12개월 막대 (단일 데이터셋)
  const chartInfo = await page.evaluate(() => ({
    months: _divChart.data.labels.length,
    datasets: _divChart.data.datasets.length,
    year: _divYear,
  }));
  ok('x축 = 12개월', chartInfo.months === 12);
  ok('단일 연도 막대(1 데이터셋)', chartInfo.datasets === 1);

  // 배당 있는 달 찾아서 드릴다운 호출
  const drillMonth = await page.evaluate(() => {
    const evs = _divData.events[_divYear];
    const m = evs.length ? evs[0].month : 1;
    renderDrill(m);
    return m;
  });
  await page.waitForTimeout(200);
  const drillTxt = await page.textContent('#divDrill');
  ok('막대 드릴다운 = 종목별 내역', drillTxt.includes(drillMonth + '월 배당') &&
     (drillTxt.includes('SCHD') || drillTxt.includes('Schwab') || drillTxt.includes('TIGER') || drillTxt.includes('₩')));

  // 배당 일정 = 리스트(캘린더 아님), 인라인 표시
  const list = await page.evaluate(() => ({
    items: document.querySelectorAll('#divCal .div-list-item').length,
    hasDate: !!document.querySelector('#divCal .div-list-date'),
    hasAmt: !!document.querySelector('#divCal .div-list-amt'),
    projBadge: document.querySelectorAll('#divCal .div-proj-badge').length,
  }));
  ok('배당 일정 = 리스트 항목', list.items > 0);
  ok('리스트 = 날짜+금액 인라인', list.hasDate && list.hasAmt);
  ok('올해 리스트에 예측 배지 존재', list.projBadge > 0);

  // 연도 전환 — 내년(전체 예측) 클릭
  await page.click(`#divYearTabs .div-tgl:last-child`);
  await page.waitForTimeout(300);
  ok('내년 전환 = 전체 예측', await page.evaluate(() =>
    _divYear === _divData.full_proj_year &&
    _divData.events[_divYear].every(e => e.projected)));

  // 세후 토글 → 합계 감소 (과거 실적연도 Y-1 선택 후)
  await page.click(`#divYearTabs .div-tgl:nth-child(3)`);
  await page.waitForTimeout(200);
  const preTotal = await page.evaluate(() =>
    _divChart.data.datasets[0].data.reduce((a, b) => a + b, 0));
  await page.click('[data-div-tax="posttax"]');
  await page.waitForTimeout(200);
  const postTotal = await page.evaluate(() =>
    _divChart.data.datasets[0].data.reduce((a, b) => a + b, 0));
  ok('세후 토글 → 합계 감소', postTotal < preTotal && postTotal > 0);

  // 외화 토글 → 달러 환산(원화보다 작음)
  await page.click('[data-div-cur="USD"]');
  await page.waitForTimeout(200);
  const usdTotal = await page.evaluate(() =>
    _divChart.data.datasets[0].data.reduce((a, b) => a + b, 0));
  ok('외화 토글 → 달러 환산', usdTotal > 0 && usdTotal < postTotal);

  // 안내문구
  const note = await page.textContent('#divNote');
  ok('안내: 보유수량 가정·예측·백테 유도',
     note.includes('현재 보유 수량') && note.includes('예측') && note.includes('백테스트') && note.includes('투자계산기'));

  ok('JS 에러 0', errors.length === 0);
  if (errors.length) console.log('  errors:', errors.slice(0, 3));

  // 정리
  await page.evaluate(async () => {
    const items = await fetch('/api/myassets/data').then(r => r.json());
    for (const h of (items.holdings || []).filter(x => ['SCHD', '458730'].includes(x.code)))
      await fetch('/api/myassets/holding/' + h.id, { method: 'DELETE' });
  });
  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL  (${BASE})`);
  process.exit(fail ? 1 : 0);
})();
