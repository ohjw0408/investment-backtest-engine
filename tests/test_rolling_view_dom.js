/**
 * 롤링 차트 보기 전환(최종자산/CAGR/연도별) jsdom 스모크 — calculator.js 단독 주입.
 * Chart 모킹으로 마지막 차트 config 캡처. 실행: node tests/test_rolling_view_dom.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const src = fs.readFileSync(
  path.join(__dirname, '..', 'static', 'js', 'calculator.js'), 'utf8');

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}

const GREEN = 'rgba(67,160,71,0.6)';
const RED   = 'rgba(239,83,80,0.6)';

// 입력 순서(start)와 cagr 순서를 일부러 어긋나게 → 정렬 검증
const CASES = [
  { start: '2010-01-01', cagr:  0.05, end_value: 1500 },
  { start: '2011-01-01', cagr: -0.03, end_value:  800 },
  { start: '2012-01-01', cagr:  0.12, end_value: 3000 },
  { start: '2013-01-01', cagr:  0.02, end_value: 1100 },
];

const vc = new VirtualConsole();
vc.on('jsdomError', () => {});
const dom = new JSDOM(`<body>
  <canvas id="rollingChart"></canvas>
  <div id="rollingTitle"></div>
  <button class="rchart-seg-btn active" data-mode="asset"></button>
  <button class="rchart-seg-btn" data-mode="cagr"></button>
  <button class="rchart-seg-btn" data-mode="year"></button>
</body>`, { runScripts: 'outside-only', virtualConsole: vc });

const w = dom.window;
w.MM_CHART_GRID = '#ccc';
w.document.getElementById('rollingChart').getContext = () => ({});

let lastCfg = null;
w.Chart = function (ctx, cfg) { lastCfg = cfg; this.destroy = () => {}; };

w.eval(src);

// ── 1. 기본(asset) — 최종자산, CAGR 오름차순 정렬, 전부 초록 ──
w.renderRollingChart(CASES);
{
  const d = lastCfg.data;
  ok('asset: 막대=최종자산, cagr 오름차순',
    JSON.stringify(d.datasets[0].data) === JSON.stringify([800, 1100, 1500, 3000]));
  ok('asset: labels도 cagr순(start 정렬)',
    JSON.stringify(d.labels) === JSON.stringify(['2011-01', '2013-01', '2010-01', '2012-01']));
  ok('asset: 전부 초록(최종자산은 음수 없음)',
    d.datasets[0].backgroundColor.every(c => c === GREEN));
}

// ── 2. CAGR 보기 — cagr%, 오름차순, 음수 빨강 ──
w.setRollingView('cagr');
{
  const d = lastCfg.data;
  ok('cagr: 막대=CAGR% 오름차순',
    JSON.stringify(d.datasets[0].data) === JSON.stringify([-3, 2, 5, 12]));
  ok('cagr: 음수만 빨강',
    JSON.stringify(d.datasets[0].backgroundColor) === JSON.stringify([RED, GREEN, GREEN, GREEN]));
  ok('cagr: 제목 갱신', w.document.getElementById('rollingTitle').textContent.includes('CAGR'));
  ok('cagr: 버튼 active 이동',
    w.document.querySelector('[data-mode="cagr"]').classList.contains('active') &&
    !w.document.querySelector('[data-mode="asset"]').classList.contains('active'));
}

// ── 3. 연도별 — 입력 순서 유지(정렬 안 함) ──
w.setRollingView('year');
{
  const d = lastCfg.data;
  ok('year: 막대=최종자산, 입력(start) 순서 유지',
    JSON.stringify(d.datasets[0].data) === JSON.stringify([1500, 800, 3000, 1100]));
  ok('year: labels 입력순',
    JSON.stringify(d.labels) === JSON.stringify(['2010-01', '2011-01', '2012-01', '2013-01']));
}

console.log(`\n${pass} PASS / ${fail} FAIL`);
process.exit(fail ? 1 : 0);
