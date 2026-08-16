/**
 * 투자대가 시점별(point-in-time) 재현 실브라우저 검증 (비로그인 — 세션 불필요).
 *
 * 확인 대상:
 *  1. /examples 투자대가 카드 → 모달 → 시뮬 대상 상위 N 표시
 *  2. "분석하기" → /backtest 프리로드에 guru 슬러그·첫 공시일이 실림
 *  3. 백테 입력 화면에 시점별 재현 배너
 *  4. 종목을 건드리면 배너 해제(고정 비중으로 강등) — 거짓 표기 방지
 *  5. 실제 실행 결과에 guru_pit 배지 + 결과 배너
 *  6. 라이트/다크 스샷, 콘솔 에러 0
 *
 * 선행: venv/Scripts/python.exe tests/make_guru_pit_sample.py  (결과 샘플 생성)
 * 실행: node tests/test_guru_pit_browser.js [baseUrl]
 */
const { chromium } = require('playwright');
const fs = require('fs');

const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const SHOT = process.env.SHOT_DIR || 'tmp';

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name + (extra ? '  << ' + extra : '')); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  if (!fs.existsSync(SHOT)) fs.mkdirSync(SHOT, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  // ── 1. 투자대가 탭 · 모달 ──
  await page.goto(BASE + '/examples?tab=guru', { waitUntil: 'networkidle' });
  const guruCards = await page.$$('[data-ex-card][data-type="guru"]');
  ok('투자대가 카드 렌더', guruCards.length >= 5, 'cards=' + guruCards.length);

  const firstFiled = await page.$eval('[data-ex-card][data-type="guru"]', el => el.dataset.firstfiled);
  ok('카드에 첫 공시일 실림', /^\d{4}-\d{2}-\d{2}$/.test(firstFiled || ''), 'firstfiled=' + firstFiled);

  await guruCards[0].click();
  await sleep(400);
  ok('상세 모달 열림', await page.$eval('#exModal', el => !el.hidden));
  const simTags = await page.$$('#exmBody .exm-sim');
  ok('시뮬 대상 표시(상위 N)', simTags.length > 0 && simTags.length <= 12, 'simTags=' + simTags.length);
  await page.screenshot({ path: SHOT + '/guru_pit_modal_light.png' });

  // ── 2. 분석하기 → 백테 프리로드 ──
  await page.click('#exmActs .ex-btn[data-act="analyze"]');
  await page.waitForURL('**/backtest', { timeout: 15000 });
  await page.waitForLoadState('networkidle');
  await sleep(600);

  const noteVisible = await page.$eval('#btGuruNote', el => el.style.display !== 'none');
  ok('백테 입력에 시점별 재현 배너', noteVisible);
  const startVal = await page.$eval('#btStartDate', el => el.value);
  ok('시작일 = 첫 공시일', startVal === firstFiled, 'start=' + startVal + ' expect=' + firstFiled);
  await page.screenshot({ path: SHOT + '/guru_pit_input_light.png' });

  // ── 3. 다크 모드 ──
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await sleep(300);
  await page.screenshot({ path: SHOT + '/guru_pit_input_dark.png' });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
  await sleep(200);

  // ── 4. 결과 렌더 검증 (시점별) ──
  // 실행 자체는 celery 큐를 타므로(로컬엔 redis/worker 없음), 엔진이 실제로 뱉은
  // 결과 JSON(tmp/guru_pit_sample.json = run_backtest_logic 원본)을 렌더 경로에 그대로 흘린다.
  const sample = JSON.parse(fs.readFileSync('tmp/guru_pit_sample.json', 'utf-8'));
  ok('샘플이 시점별 결과', !!(sample.result && sample.result.guru_pit),
     JSON.stringify(sample.result && sample.result.guru_pit));
  await page.evaluate(s => { window._btLastBody = s.body; renderBacktest(s.result); }, sample);
  await sleep(800);

  const cond = await page.$eval('#btCondSummary', el => el.textContent);
  ok('조건 요약에 시점별 배지', cond.includes('시점별 13F 재현'), cond.slice(0, 160));
  ok('조건 요약에 공시일 리밸 횟수', /공시일 리밸 \d+회/.test(cond), cond.slice(0, 160));
  const resNote = await page.$eval('#btGuruResultNote', el => ({ vis: el.style.display !== 'none', txt: el.textContent }));
  ok('결과 배너 노출', resNote.vis);
  ok('결과 배너에 13F 한계 명시', resNote.txt.includes('미국 상장 주식 롱'), resNote.txt.slice(0, 120));
  await page.screenshot({ path: SHOT + '/guru_pit_result_light.png', fullPage: false });

  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await sleep(400);
  await page.screenshot({ path: SHOT + '/guru_pit_result_dark.png' });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));

  // ── 5. 구성 편집 → 시점별 해제 ──
  await page.click('#btEditBtn').catch(() => {});
  const editBtn = await page.$('[onclick*="btEditConditions"], #btEditConditions');
  if (editBtn) await editBtn.click();
  else await page.evaluate(() => btShowInput());
  await sleep(400);
  await page.evaluate(() => btRemoveTicker(0));
  await sleep(300);
  const noteAfter = await page.$eval('#btGuruNote', el => el.style.display !== 'none');
  ok('종목 편집 시 시점별 재현 해제', !noteAfter);
  const guruAfter = await page.evaluate(() => btGuru);
  ok('내부 슬러그도 해제', guruAfter === null, 'btGuru=' + guruAfter);

  // ── 6. 비교 오버레이: 가격 기준으로 바꿔도 시점별 곡선 유지 + 경고 ──
  await page.goto(BASE + '/examples?tab=guru', { waitUntil: 'networkidle' });
  await page.click('[data-ex-card][data-type="guru"][data-slug="guru-warren-buffett"] .ex-btn[data-act="compare"]');
  await sleep(400);
  await page.goto(BASE + '/risk-return', { waitUntil: 'networkidle' });
  await page.waitForSelector('#rrOvCtrl input[name=rrovbasis]', { timeout: 60000 });
  await sleep(1500);
  const trSeries = await page.evaluate(() => Object.values(rrOv.raw).map(s => ({ pit: !!s.point_in_time, basis: s.basis, n: s.points.length })));
  ok('총수익 기준: 대가 곡선 = 시점별', trSeries.some(s => s.pit && s.n > 100), JSON.stringify(trSeries));

  await page.click('#rrOvCtrl input[name=rrovbasis][value="price"]');
  await page.waitForFunction(() => Object.keys(rrOv.raw || {}).length > 0, null, { timeout: 60000 });
  await sleep(800);
  const priceSeries = await page.evaluate(() => Object.values(rrOv.raw).map(s => ({ pit: !!s.point_in_time, mm: !!s.basis_mismatch, n: s.points.length })));
  ok('가격 기준: 후견편향 곡선으로 갈아타지 않음', priceSeries.some(s => s.pit), JSON.stringify(priceSeries));
  const warn = await page.$eval('#rrOvCtrl', el => el.textContent);
  ok('기준 불일치 경고 노출', warn.includes('항상'), warn.slice(-140));
  await page.screenshot({ path: SHOT + '/guru_pit_overlay_light.png' });

  // ── 7. 콘솔 에러 ──
  const real = errors.filter(e => !/favicon|net::ERR_|Failed to load resource/i.test(e));
  ok('콘솔 에러 0', real.length === 0, real.slice(0, 3).join(' | '));

  console.log(`\n결과: ${pass} PASS / ${fail} FAIL`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})();
