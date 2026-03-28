/**
 * Domino Invest — Shared chart utilities
 */

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
