/**
 * 간편 계산기 실브라우저(Playwright Chromium) 검증 — 라이브 서버 대상.
 * 실행: node tests/test_simple_tools_browser.js [BASE_URL] [SCREENSHOT_DIR]
 * 기본: https://moneymilestone.duckdns.org, 스크린샷 저장 안 함(인자 주면 저장)
 */
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'https://moneymilestone.duckdns.org';
const SHOT_DIR = process.argv[3] || null;

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const consoleErrors = [];
  page.on('pageerror', e => consoleErrors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });

  await page.goto(BASE + '/simple', { waitUntil: 'networkidle' });

  // 1. 초기 렌더: 복리 탭 기본값 계산 완료
  const cpFinal = await page.textContent('#stCpFinal');
  ok('초기렌더 복리 만기 평가액 표시', cpFinal && cpFinal !== '—');

  // 2. 입력 변경 → 즉시 재계산 (거치식 1,000만·7%·10년 = ₩1,967만)
  await page.fill('#stCpMonthly', '0');
  await page.fill('#stCpReturn', '7');
  await page.fill('#stCpYears', '10');
  await page.fill('#stCpInitial', '10000000');
  ok('복리 거치식 = ₩1,967만', (await page.textContent('#stCpFinal')) === '₩1,967만');

  // 3. 과세 토글 → 값 변경
  await page.check('#stCpTaxed');
  ok('복리 과세 ON = ₩1,777만', (await page.textContent('#stCpFinal')) === '₩1,777만');
  await page.uncheck('#stCpTaxed');

  // 4. 차트 canvas가 실제로 그려짐 (Chart.js 인스턴스 → canvas 크기 > 0)
  const chartDrawn = await page.evaluate(() => {
    const c = document.getElementById('stCpChart');
    return c && c.width > 0 && c.height > 0;
  });
  ok('복리 차트 canvas 렌더', chartDrawn);
  if (SHOT_DIR) await page.screenshot({ path: SHOT_DIR + '/simple_compound.png', fullPage: true });

  // 5. 탭 전환 4종 — 패널 표시 + 대표 출력값 채워짐
  const tabs = [
    ['dividend', '#stDvFinal'],
    ['inflation', '#stInfFuture'],
    ['realvalue', '#stRvReal'],
    ['compound', '#stCpFinal'],
  ];
  for (const [tab, sel] of tabs) {
    await page.click(`.st-tab-btn[data-tab="${tab}"]`);
    const visible = await page.isVisible(`#stPanel-${tab}`);
    const val = await page.textContent(sel);
    ok(`탭 ${tab}: 패널 표시 + 값 채워짐`, visible && val && val !== '—');
    if (SHOT_DIR && tab !== 'compound') await page.screenshot({ path: `${SHOT_DIR}/simple_${tab}.png`, fullPage: true });
  }

  // 6. 배당 탭 주기 라디오 재계산
  await page.click('.st-tab-btn[data-tab="dividend"]');
  await page.fill('#stDvInitial', '100000000');
  await page.fill('#stDvMonthly', '0');
  await page.fill('#stDvYield', '4');
  await page.fill('#stDvGrowth', '0');
  await page.fill('#stDvYears', '1');
  await page.uncheck('#stDvTaxed');
  const qVal = await page.textContent('#stDvFinal');
  await page.check('input[name="stDvFreq"][value="monthly"]');
  const mVal = await page.textContent('#stDvFinal');
  ok('배당 주기 전환 재계산 (분기→월)', qVal !== mVal && mVal === '₩1억 407만');

  // 7. JS 콘솔/페이지 에러 0
  ok('브라우저 에러 0', consoleErrors.length === 0);
  if (consoleErrors.length) console.log(consoleErrors.join('\n'));

  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL  (대상: ${BASE})`);
  process.exit(fail ? 1 : 0);
})();
