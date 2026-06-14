/**
 * 미래 시나리오 부채꼴 프론트(renderFan/onFanSlider/_drawFan) jsdom 스모크.
 * Chart 모킹. 실행: node tests/test_fan_dom.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const src = fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'calculator.js'), 'utf8');

let pass = 0, fail = 0;
const ok = (n, c) => { if (c) { pass++; console.log('PASS  ' + n); } else { fail++; console.log('FAIL  ' + n); } };

// 그리드: percentiles 1..99, axis [0,1,2], bands[i] = [100, 100+i, 200+2i] (i단조)
const bands = [];
for (let i = 0; i < 99; i++) bands.push([100, 100 + i, 200 + 2 * i]);
const FAN = { axis: [0, 1, 2], percentiles: Array.from({ length: 99 }, (_, i) => i + 1), bands, n: 42 };

const vc = new VirtualConsole(); vc.on('jsdomError', () => {});
const dom = new JSDOM(`<body>
  <div id="fanCard" style="display:none;"></div>
  <canvas id="fanChart"></canvas>
  <input type="range" id="fanLo" min="1" max="99" value="25">
  <input type="range" id="fanHi" min="1" max="99" value="75">
  <b id="fanLoVal"></b><b id="fanHiVal"></b><span id="fanN"></span>
</body>`, { runScripts: 'outside-only', virtualConsole: vc });

const w = dom.window;
w.MM_CHART_GRID = '#ccc';
w.document.getElementById('fanChart').getContext = () => ({});
let lastCfg = null;
w.Chart = function (ctx, cfg) { lastCfg = cfg; this.destroy = () => {}; };
w.eval(src);

// ── 1. renderFan 기본(25/75) ──
w.renderFan(FAN);
ok('카드 표시', w.document.getElementById('fanCard').style.display !== 'none');
ok('시나리오 개수 표시', w.document.getElementById('fanN').textContent.includes('42'));
{
  const ds = lastCfg.data.datasets;
  ok('하단 = bands[24] (p25)', JSON.stringify(ds[0].data) === JSON.stringify(bands[24]));
  ok('상단 = bands[74] (p75)', JSON.stringify(ds[1].data) === JSON.stringify(bands[74]));
  ok('중앙 = bands[49] (p50)', JSON.stringify(ds[2].data) === JSON.stringify(bands[49]));
  ok('상단 dataset fill=-1 (밴드 채움)', ds[1].fill === '-1');
  ok('x 라벨 = 시작/1년차/2년차',
    JSON.stringify(lastCfg.data.labels) === JSON.stringify(['시작', '1년차', '2년차']));
}

// ── 2. 슬라이더 조정 → 밴드 갱신 ──
w.document.getElementById('fanLo').value = '10';
w.onFanSlider('lo');
ok('하단 p10 → bands[9]', JSON.stringify(lastCfg.data.datasets[0].data) === JSON.stringify(bands[9]));
ok('라벨값 갱신', w.document.getElementById('fanLoVal').textContent === '10');

// ── 3. 하단 ≥ 상단 강제 보정 ──
w.document.getElementById('fanLo').value = '90';   // 상단 75 넘김
w.onFanSlider('lo');
ok('하단>상단 시 상단 밀어올림', parseInt(w.document.getElementById('fanHi').value) === 91);

// ── 4. null/빈 fan → 카드 숨김 ──
w.renderFan(null);
ok('fan 없으면 카드 숨김', w.document.getElementById('fanCard').style.display === 'none');
w.renderFan({ bands: [[1, 2]] });   // 99행 아님
ok('비정상 그리드 → 숨김', w.document.getElementById('fanCard').style.display === 'none');

console.log(`\n${pass} PASS / ${fail} FAIL`);
process.exit(fail ? 1 : 0);
