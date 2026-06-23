/**
 * 롤링 차트 보기 전환 라이브 실브라우저(Playwright) — 실 Chart.js + onclick 배선.
 * fake cases 주입 → 버튼 클릭 → chartInstances 검사. 실 계산 없이 렌더만 검증.
 * 실행: node tests/test_rolling_view_live.js [BASE_URL] [SHOT_DIR]
 */
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'https://moneymilestone.co.kr';
const SHOT = process.argv[3] || null;

let pass = 0, fail = 0;
const ok = (n, c) => { if (c) { pass++; console.log('PASS  ' + n); } else { fail++; console.log('FAIL  ' + n); } };

const CASES = [
  { start: '2010-01-01', cagr:  0.05, end_value: 1500 },
  { start: '2011-01-01', cagr: -0.03, end_value:  800 },
  { start: '2012-01-01', cagr:  0.12, end_value: 3000 },
  { start: '2013-01-01', cagr:  0.02, end_value: 1100 },
];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

  await page.goto(BASE + '/calculator', { waitUntil: 'networkidle' });

  // 버튼 3개 존재
  ok('버튼 3개 렌더', (await page.locator('.rchart-seg-btn').count()) === 3);
  ok('setRollingView 정의', await page.evaluate(() => typeof setRollingView === 'function'));

  // fake cases 주입 → 기본(asset) 렌더
  const inject = (cs) => page.evaluate(c => window.renderRollingChart(c), cs);
  const chartData = () => page.evaluate(() => {
    const ch = chartInstances['rollingChart'];
    return {
      data: ch.data.datasets[0].data, bg: ch.data.datasets[0].backgroundColor, labels: ch.data.labels,
      xTicks: ch.options.scales.x.ticks.display, xTitle: ch.options.scales.x.title.display,
    };
  });
  const GREEN = 'rgba(67,160,71,0.6)', RED = 'rgba(239,83,80,0.6)';

  // 결과 카드는 계산 전 display:none → 실클릭 위해 조상 노출
  await page.evaluate(() => {
    let el = document.getElementById('rollingChart');
    while (el) { if (el.style && el.style.display === 'none') el.style.display = ''; el = el.parentElement; }
  });

  await inject(CASES);
  let d = await chartData();
  ok('asset: 최종자산 cagr오름차순', JSON.stringify(d.data) === JSON.stringify([800, 1100, 1500, 3000]));
  ok('asset: 전부 초록', d.bg.every(c => c === GREEN));
  ok('asset: x축 연도라벨 숨김 + 제목 표시', d.labels.every(l => l === '') && d.xTicks === false && d.xTitle === true);

  // CAGR 버튼 클릭 (실 onclick)
  await page.click('[data-mode="cagr"]');
  d = await chartData();
  ok('cagr: CAGR% 오름차순', JSON.stringify(d.data) === JSON.stringify([-3, 2, 5, 12]));
  ok('cagr: 음수만 빨강', JSON.stringify(d.bg) === JSON.stringify([RED, GREEN, GREEN, GREEN]));
  ok('cagr: 버튼 active', await page.evaluate(() =>
    document.querySelector('[data-mode="cagr"]').classList.contains('active')));
  ok('cagr: 제목 갱신', (await page.textContent('#rollingTitle')).includes('CAGR'));

  // 연도별 버튼
  await page.click('[data-mode="year"]');
  d = await chartData();
  ok('year: 입력순 유지', JSON.stringify(d.data) === JSON.stringify([1500, 800, 3000, 1100]));
  ok('year: 연도라벨 표시 + 제목 없음',
    JSON.stringify(d.labels) === JSON.stringify(['2010-01', '2011-01', '2012-01', '2013-01']) && d.xTitle === false);

  // 최종자산 복귀
  await page.click('[data-mode="asset"]');
  ok('asset 복귀 active', await page.evaluate(() =>
    document.querySelector('[data-mode="asset"]').classList.contains('active')));

  ok('콘솔/페이지 에러 0', errs.length === 0);
  if (errs.length) console.log('  ERRORS:', errs.slice(0, 5));

  if (SHOT) { await page.click('[data-mode="cagr"]'); await page.screenshot({ path: SHOT + '/rolling_cagr.png' }); }

  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
})();
