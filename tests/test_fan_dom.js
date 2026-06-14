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
  <div id="fanScrollX" class="fan-scroll disabled"><div id="fanThumbX"></div></div>
  <div id="fanScrollY" class="fan-scroll disabled"><div id="fanThumbY"></div></div>
  <b id="fanLoVal"></b><b id="fanHiVal"></b><span id="fanN"></span>
</body>`, { runScripts: 'outside-only', virtualConsole: vc });

const w = dom.window;
w.MM_CHART_GRID = '#ccc';
w.document.getElementById('fanChart').getContext = () => ({});
let lastCfg = null;
w.Chart = function (ctx, cfg) {
  lastCfg = cfg; this.data = cfg.data; this.options = cfg.options;
  this.scales = {
    x: { min: 0, max: cfg.data.labels.length - 1 },
    y: { min: cfg.options.scales.y.min, max: cfg.options.scales.y.max },
  };
  this.update = () => {}; this.resetZoom = () => {}; this.destroy = () => {};
  w.__lastChart = this;   // 테스트 훅: 인스턴스(scales) 접근용
};
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
  ok('줌 config 존재(Ctrl+휠)', lastCfg.options.plugins.zoom.zoom.wheel.modifierKey === 'ctrl');
  // y축 고정: bands[0]=[100,100,200] min=100, bands[98]=[100,198,396] max=396, pad=14.8
  ok('y축 min/max = 전체 p1~p99 범위 고정',
    Math.abs(lastCfg.options.scales.y.min - (100 - 14.8)) < 0.01 &&
    Math.abs(lastCfg.options.scales.y.max - (396 + 14.8)) < 0.01);
}

// ── 2. 슬라이더 조정 → 밴드 갱신 ──
w.document.getElementById('fanLo').value = '10';
w.onFanSlider('lo');
ok('하단 p10 → bands[9] (in-place 갱신)', JSON.stringify(lastCfg.data.datasets[0].data) === JSON.stringify(bands[9]));
ok('중앙선 불변(p50 그대로)', JSON.stringify(lastCfg.data.datasets[2].data) === JSON.stringify(bands[49]));
ok('y축 슬라이더 후에도 고정(프레임 불변)',
  Math.abs(lastCfg.options.scales.y.min - (100 - 14.8)) < 0.01);
ok('라벨값 갱신', w.document.getElementById('fanLoVal').textContent === '10');
ok('resetFanZoom 호출 무오류', (() => { try { w.resetFanZoom(); return true; } catch (e) { return false; } })());

// ── 3. 하단 ≥ 상단 강제 보정 ──
w.document.getElementById('fanLo').value = '90';   // 상단 75 넘김
w.onFanSlider('lo');
ok('하단>상단 시 상단 밀어올림', parseInt(w.document.getElementById('fanHi').value) === 91);

// ── 3b. 줌 초기화 = 현재 밴드(20~40)에 맞춰 y 규격화 ──
w.renderFan(FAN);   // 프레시 차트
w.document.getElementById('fanLo').value = '20';
w.document.getElementById('fanHi').value = '40';
w.onFanSlider('lo');
w.resetFanZoom();
{
  // bands[19]=[100,119,238] min=100, bands[39]=[100,139,278] max=278, pad=(278-100)*0.08=14.24
  const y = lastCfg.options.scales.y;
  ok('리셋: y.min ≈ 현재밴드 최저-pad', Math.abs(y.min - (100 - 14.24)) < 0.1);
  ok('리셋: y.max ≈ 현재밴드 최고+pad', Math.abs(y.max - (278 + 14.24)) < 0.1);
}

// ── 3c. 스크롤바 창 이동 = _fanPanTo (lastChart 훅으로 scales 조작) ──
{
  // 확대 시뮬: x창 [0,1] (전체 [0,2] 중 절반)
  w.__lastChart.scales.x.min = 0; w.__lastChart.scales.x.max = 1;
  w._fanPanTo('x', 1);   // 우측끝
  ok('팬 frac=1 → 창 우측끝(min=1,max=2)',
    lastCfg.options.scales.x.min === 1 && lastCfg.options.scales.x.max === 2);
  w.__lastChart.scales.x.min = 1; w.__lastChart.scales.x.max = 2;   // 갱신 반영
  w._fanPanTo('x', 0);   // 좌측끝
  ok('팬 frac=0 → 창 좌측끝(min=0)', lastCfg.options.scales.x.min === 0);
}

// ── 3d. _syncFanScroll: thumb 크기·활성/비활성 ──
{
  w.__lastChart.scales.x.min = 0; w.__lastChart.scales.x.max = 1;   // 확대됨(50%)
  w._syncFanScroll();
  ok('확대 시 스크롤바 활성', !w.document.getElementById('fanScrollX').classList.contains('disabled'));
  ok('thumb 크기 = 창 비율(50%)', w.document.getElementById('fanThumbX').style.width === '50%');
  w.__lastChart.scales.x.min = 0; w.__lastChart.scales.x.max = 2;   // 전체
  w._syncFanScroll();
  ok('전체 보기 시 스크롤바 비활성', w.document.getElementById('fanScrollX').classList.contains('disabled'));
}

// ── 4. null/빈 fan → 카드 숨김 ──
w.renderFan(null);
ok('fan 없으면 카드 숨김', w.document.getElementById('fanCard').style.display === 'none');
w.renderFan({ bands: [[1, 2]] });   // 99행 아님
ok('비정상 그리드 → 숨김', w.document.getElementById('fanCard').style.display === 'none');

console.log(`\n${pass} PASS / ${fail} FAIL`);
process.exit(fail ? 1 : 0);
