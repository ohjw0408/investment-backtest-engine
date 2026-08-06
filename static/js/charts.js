/**
 * Domino Invest — Shared chart utilities
 */

// 테마 공용 상수 — 페이지 차트 스크립트보다 먼저 로드됨
const MM_DARK = document.documentElement.getAttribute('data-theme') === 'dark';
const MM_CHART_GRID = MM_DARK ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.04)';

// 다크모드일 때 Chart.js 전역 기본색 조정 (페이지 차트 생성 전에 실행)
(function () {
  if (typeof Chart === 'undefined' || !MM_DARK) return;
  Chart.defaults.color = '#8FA3B8';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.09)';
  if (Chart.defaults.scale && Chart.defaults.scale.grid) {
    Chart.defaults.scale.grid.color = 'rgba(255,255,255,0.09)';
  }
})();

// 전역 hover/툴팁: 선에 핀포인트로 안 대도 같은 x축 값이 뜨도록 (index 모드, 교차 불요)
// → 라인/영역/바 차트 어디든 마우스만 근처에 가면 해당 시점 값 표시. 파이/도넛은 자체 override 권장.
(function () {
  if (typeof Chart === 'undefined') return;
  Chart.defaults.interaction = Object.assign({}, Chart.defaults.interaction, { mode: 'index', intersect: false });
  Chart.defaults.plugins = Chart.defaults.plugins || {};
  Chart.defaults.plugins.tooltip = Object.assign({}, Chart.defaults.plugins.tooltip, { mode: 'index', intersect: false });
})();

/**
 * 스파크라인 그리기
 * @param {string} canvasId
 * @param {number[]} data
 * @param {boolean} isUp
 */
function drawSparkline(canvasId, data, isUp) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  ctx.clearRect(0, 0, w, h);
  ctx.beginPath();

  data.forEach((v, i) => {
    const x = (i / (data.length - 1)) * (w - 4) + 2;
    const y = h - ((v - min) / range) * (h - 6) - 3;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });

  ctx.strokeStyle = isUp ? '#43A047' : '#EF5350';
  ctx.lineWidth = 1.8;
  ctx.lineJoin = 'round';
  ctx.stroke();

  // 끝 점
  const lastX = w - 2;
  const lastY = h - ((data[data.length - 1] - min) / range) * (h - 6) - 3;
  ctx.beginPath();
  ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
  ctx.fillStyle = isUp ? '#43A047' : '#EF5350';
  ctx.fill();
}
