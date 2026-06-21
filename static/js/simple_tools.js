/**
 * Money Milestone — 간편 계산기 묶음 (simple tools)
 *
 * 가정 기반 결정론 프로젝션. 서버 호출 없음 — 전부 클라이언트 계산.
 * 무거운 롤링 백테스트 엔진(calculator/backtest/retirement)과 별개.
 *
 * 계산 규약 (4종 공통):
 * - 월 단위 루프. 월 수익률 = (1+연율)^(1/12) − 1 (기하 환산, CAGR 일치).
 * - 적립금은 월초 납입(그 달부터 수익 발생).
 * - 연증액률 g%: 매년 1월(13개월째)부터 월적립 ×(1+g).
 * - 과세 ON = 수익/배당에 15.4% 원천징수 가정.
 * - 실질가치 = 명목 / (1+인플레)^경과년수.
 */

const ST_TAX_RATE = 0.154;

// ───────────────────────── 순수 계산 함수 ─────────────────────────

/** 복리 계산기. 과세 ON이면 연수익률에 15.4% 과세(세후 수익률) 적용. */
function stCompound(p) {
  const annualNet = p.taxed ? p.annualReturn * (1 - ST_TAX_RATE) : p.annualReturn;
  const rm = Math.pow(1 + annualNet, 1 / 12) - 1;
  let value = p.initial;
  let principal = p.initial;
  let monthly = p.monthly;
  const yearly = [];
  for (let m = 1; m <= p.years * 12; m++) {
    value = (value + monthly) * (1 + rm);
    principal += monthly;
    if (m % 12 === 0) {
      const y = m / 12;
      yearly.push({
        year: y,
        principal: principal,
        value: value,
        real: value / Math.pow(1 + p.inflation, y),
      });
      monthly *= (1 + p.annualIncrease);
    }
  }
  const final = yearly.length ? yearly[yearly.length - 1].value : p.initial;
  return {
    final: final,
    principal: principal,
    gain: final - principal,
    realFinal: final / Math.pow(1 + p.inflation, p.years),
    yearly: yearly,
  };
}

/** 인플레이션 생활비 계산기. 현재 월생활비가 N년 후 얼마가 되는지. */
function stInflationCost(p) {
  const yearly = [];
  let cumulative = 0;
  for (let y = 1; y <= p.years; y++) {
    const monthly = p.monthlyCost * Math.pow(1 + p.inflation, y);
    cumulative += monthly * 12;
    yearly.push({ year: y, monthly: monthly, annual: monthly * 12, cumulative: cumulative });
  }
  return {
    futureMonthly: p.monthlyCost * Math.pow(1 + p.inflation, p.years),
    totalCumulative: cumulative,
    yearly: yearly,
  };
}

/** 실질 구매력 계산기. 지금 금액이 N년 후 얼마 가치인지. */
function stRealValue(p) {
  const yearly = [];
  for (let y = 1; y <= p.years; y++) {
    yearly.push({ year: y, real: p.amount / Math.pow(1 + p.inflation, y) });
  }
  const real = p.amount / Math.pow(1 + p.inflation, p.years);
  return {
    real: real,
    lossPct: 1 - real / p.amount,
    yearly: yearly,
    // 역방향: 현재 구매력을 유지하려면 N년 후 필요한 명목 금액
    requiredNominal: p.amount * Math.pow(1 + p.inflation, p.years),
  };
}

/**
 * 배당 재투자 계산기 (잼투리식 스노우볼).
 * 모델: 주가는 배당성장률로 상승(시가배당률 일정 가정), 배당은 주기마다
 * 평가액 × (배당수익률/연지급횟수)로 지급 → 과세 후 전액 재투자.
 */
function stDividendReinvest(p) {
  const periods = p.frequency === 'monthly' ? 12 : 4;   // 월배당 | 분기배당
  const gm = Math.pow(1 + p.divGrowth, 1 / 12) - 1;
  let value = p.initial;
  let principal = p.initial;
  let monthly = p.monthly;
  let cumDiv = 0;
  let yearDiv = 0;
  const yearly = [];
  for (let m = 1; m <= p.years * 12; m++) {
    value = (value + monthly) * (1 + gm);
    principal += monthly;
    const isPayout = p.frequency === 'monthly' ? true : (m % 3 === 0);
    if (isPayout) {
      const gross = value * (p.divYield / periods);
      const net = p.taxed ? gross * (1 - ST_TAX_RATE) : gross;
      value += net;
      cumDiv += net;
      yearDiv += net;
    }
    if (m % 12 === 0) {
      const y = m / 12;
      yearly.push({
        year: y,
        value: value,
        real: value / Math.pow(1 + p.inflation, y),
        annualDiv: yearDiv,
        cumDiv: cumDiv,
        monthlyDiv: yearDiv / 12,                                   // 그 해 월평균 배당(명목)
        monthlyDivReal: (yearDiv / 12) / Math.pow(1 + p.inflation, y), // 월 배당(실질, 인플레 조정)
      });
      yearDiv = 0;
      monthly *= (1 + p.annualIncrease);
    }
  }
  const last = yearly[yearly.length - 1];
  return {
    final: last ? last.value : p.initial,
    realFinal: last ? last.real : p.initial,
    principal: principal,
    cumDividends: cumDiv,
    lastYearDividends: last ? last.annualDiv : 0,
    lastYearMonthlyAvg: last ? last.annualDiv / 12 : 0,
    yearly: yearly,
  };
}

// ───────────────────────── 포맷/유틸 ─────────────────────────

function stFmtKRW(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const sign = v < 0 ? '-' : '';
  const abs = Math.abs(v);
  const uk = Math.floor(abs / 1e8);
  const man = Math.floor((abs % 1e8) / 1e4);
  if (uk > 0 && man > 0) return sign + '₩' + uk.toLocaleString() + '억 ' + man.toLocaleString() + '만';
  if (uk > 0) return sign + '₩' + uk.toLocaleString() + '억';
  if (abs >= 1e4) return sign + '₩' + Math.floor(abs / 1e4).toLocaleString() + '만';
  return sign + '₩' + Math.round(abs).toLocaleString();
}

function stNum(id, fallback) {
  const el = document.getElementById(id);
  const v = parseFloat(el && el.value);
  return isNaN(v) ? fallback : v;
}

function stChecked(id) {
  const el = document.getElementById(id);
  return !!(el && el.checked);
}

// ───────────────────────── 탭 전환 ─────────────────────────

function stSwitchTab(name) {
  document.querySelectorAll('.st-tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === name);
  });
  document.querySelectorAll('.st-panel').forEach(pn => {
    pn.style.display = pn.id === 'stPanel-' + name ? '' : 'none';
  });
}

// ───────────────────────── 렌더 ─────────────────────────

const stCharts = {};

function stCssVar(name, fb) { return (getComputedStyle(document.documentElement).getPropertyValue(name) || '').trim() || fb; }
function stHexA(hex, a) {
  const h = hex.replace('#', ''); const n = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
  return `rgba(${parseInt(n.slice(0,2),16)},${parseInt(n.slice(2,4),16)},${parseInt(n.slice(4,6),16)},${a})`;
}

function stDrawChart(canvasId, labels, datasets, yFmt) {
  if (typeof Chart === 'undefined') return;   // jsdom 등 차트 없는 환경
  const el = document.getElementById(canvasId);
  if (!el) return;
  const fmt = yFmt || stFmtKRW;   // 기본 KRW, 배당목표 등은 년수 포맷 주입
  if (stCharts[canvasId]) stCharts[canvasId].destroy();
  stCharts[canvasId] = new Chart(el, {
    type: 'line',
    data: { labels: labels, datasets: datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { font: { size: 11 } } },
        tooltip: { callbacks: { label: c => c.dataset.label + ': ' + (c.parsed.y == null ? '미달' : fmt(c.parsed.y)) } },
      },
      scales: {
        y: { ticks: { callback: v => fmt(v), font: { size: 10 } } },
        x: { ticks: { font: { size: 10 } } },
      },
    },
  });
}

function stRenderCompound() {
  const r = stCompound({
    initial: stNum('stCpInitial', 0),
    monthly: stNum('stCpMonthly', 0),
    annualReturn: stNum('stCpReturn', 0) / 100,
    years: Math.max(1, Math.min(70, Math.round(stNum('stCpYears', 20)))),
    annualIncrease: stNum('stCpIncrease', 0) / 100,
    taxed: stChecked('stCpTaxed'),
    inflation: stNum('stCpInflation', 0) / 100,
  });
  document.getElementById('stCpFinal').textContent = stFmtKRW(r.final);
  document.getElementById('stCpPrincipal').textContent = stFmtKRW(r.principal);
  document.getElementById('stCpGain').textContent = stFmtKRW(r.gain);
  document.getElementById('stCpReal').textContent = stFmtKRW(r.realFinal);
  document.getElementById('stCpTable').innerHTML =
    '<tr><th>연차</th><th>납입원금</th><th>평가액</th><th>실질가치</th></tr>' +
    r.yearly.map(y =>
      `<tr><td>${y.year}년</td><td>${stFmtKRW(y.principal)}</td><td>${stFmtKRW(y.value)}</td><td>${stFmtKRW(y.real)}</td></tr>`
    ).join('');
  stDrawChart('stCpChart', r.yearly.map(y => y.year + '년'), [
    { label: '평가액(명목)', data: r.yearly.map(y => y.value), borderColor: stCssVar('--brand', '#0052ff'), backgroundColor: stHexA(stCssVar('--brand', '#0052ff'), 0.08), fill: true, pointRadius: 0, borderWidth: 2 },
    { label: '실질가치', data: r.yearly.map(y => y.real), borderColor: '#7B1FA2', borderDash: [5, 4], pointRadius: 0, borderWidth: 2 },
    { label: '납입원금', data: r.yearly.map(y => y.principal), borderColor: '#9E9E9E', borderDash: [2, 3], pointRadius: 0, borderWidth: 1.5 },
  ]);
}

function stRenderInflation() {
  const r = stInflationCost({
    monthlyCost: stNum('stInfCost', 0),
    inflation: stNum('stInfRate', 0) / 100,
    years: Math.max(1, Math.min(70, Math.round(stNum('stInfYears', 20)))),
  });
  document.getElementById('stInfFuture').textContent = stFmtKRW(r.futureMonthly);
  document.getElementById('stInfTotal').textContent = stFmtKRW(r.totalCumulative);
  document.getElementById('stInfTable').innerHTML =
    '<tr><th>연차</th><th>월 생활비</th><th>연간</th><th>누적</th></tr>' +
    r.yearly.map(y =>
      `<tr><td>${y.year}년 후</td><td>${stFmtKRW(y.monthly)}</td><td>${stFmtKRW(y.annual)}</td><td>${stFmtKRW(y.cumulative)}</td></tr>`
    ).join('');
}

function stRenderRealValue() {
  const r = stRealValue({
    amount: stNum('stRvAmount', 0),
    inflation: stNum('stRvRate', 0) / 100,
    years: Math.max(1, Math.min(70, Math.round(stNum('stRvYears', 20)))),
  });
  document.getElementById('stRvReal').textContent = stFmtKRW(r.real);
  document.getElementById('stRvLoss').textContent = (r.lossPct * 100).toFixed(1) + '%';
  document.getElementById('stRvRequired').textContent = stFmtKRW(r.requiredNominal);
  document.getElementById('stRvTable').innerHTML =
    '<tr><th>연차</th><th>실질가치</th></tr>' +
    r.yearly.map(y =>
      `<tr><td>${y.year}년 후</td><td>${stFmtKRW(y.real)}</td></tr>`
    ).join('');
}

function stRenderDividend() {
  const r = stDividendReinvest({
    initial: stNum('stDvInitial', 0),
    monthly: stNum('stDvMonthly', 0),
    annualIncrease: stNum('stDvIncrease', 0) / 100,
    divYield: stNum('stDvYield', 0) / 100,
    divGrowth: stNum('stDvGrowth', 0) / 100,
    frequency: (document.querySelector('input[name="stDvFreq"]:checked') || {}).value || 'quarterly',
    taxed: stChecked('stDvTaxed'),
    inflation: stNum('stDvInflation', 0) / 100,
    years: Math.max(1, Math.min(70, Math.round(stNum('stDvYears', 20)))),
  });
  document.getElementById('stDvFinal').textContent = stFmtKRW(r.final);
  document.getElementById('stDvReal').textContent = stFmtKRW(r.realFinal);
  document.getElementById('stDvCum').textContent = stFmtKRW(r.cumDividends);
  document.getElementById('stDvLastYear').textContent = stFmtKRW(r.lastYearDividends);
  document.getElementById('stDvMonthlyAvg').textContent = stFmtKRW(r.lastYearMonthlyAvg);
  document.getElementById('stDvTable').innerHTML =
    '<tr><th>연차</th><th>평가액</th><th>연배당(세후)</th><th>누적배당</th><th>실질가치</th></tr>' +
    r.yearly.map(y =>
      `<tr><td>${y.year}년</td><td>${stFmtKRW(y.value)}</td><td>${stFmtKRW(y.annualDiv)}</td><td>${stFmtKRW(y.cumDiv)}</td><td>${stFmtKRW(y.real)}</td></tr>`
    ).join('');
  stDrawChart('stDvChart', r.yearly.map(y => y.year + '년'), [
    { label: '월 배당금(명목)', data: r.yearly.map(y => y.monthlyDiv), borderColor: stCssVar('--brand', '#0052ff'), backgroundColor: stHexA(stCssVar('--brand', '#0052ff'), 0.08), fill: true, pointRadius: 0, borderWidth: 2 },
    { label: '월 배당금(실질)', data: r.yearly.map(y => y.monthlyDivReal), borderColor: '#7B1FA2', borderDash: [5, 4], pointRadius: 0, borderWidth: 2 },
  ]);
}

/** 배당 목표 역산 — 주어진 (초기금, 월적립)으로 목표 월배당 달성 첫 년수. 미달이면 null. */
function stDivGoalYears(base, initial, monthly, target, basis) {
  const r = stDividendReinvest({ ...base, initial, monthly, years: 70 });
  for (const y of r.yearly) {
    const md = basis === 'real' ? y.monthlyDivReal : y.monthlyDiv;
    if (md >= target) return y.year;
  }
  return null;
}

// 배당 목표 역산 축(원 단위) — 사용자가 칸 단위로 추가/삭제/편집
const stDgAxes = {
  monthly: [0, 250000, 500000, 750000, 1000000, 1500000, 2000000, 3000000],
  initial: [0, 50000000, 100000000, 200000000, 300000000, 500000000],
};

function stRenderAxisChips(axis) {
  const wrap = document.getElementById(axis === 'monthly' ? 'stDgMonthlyChips' : 'stDgInitialChips');
  if (!wrap) return;
  wrap.innerHTML = stDgAxes[axis].map((v, i) =>
    `<span class="st-axis-chip"><input type="number" min="0" step="${axis === 'monthly' ? 100000 : 10000000}" value="${v}" data-axis="${axis}" data-i="${i}"><button type="button" class="st-axis-del" data-axis="${axis}" data-i="${i}" title="삭제">×</button></span>`
  ).join('');
}

function stRenderDividendGoal() {
  const base = {
    annualIncrease: stNum('stDgIncrease', 0) / 100,
    divYield: stNum('stDgYield', 0) / 100,
    divGrowth: stNum('stDgGrowth', 0) / 100,
    frequency: (document.querySelector('input[name="stDgFreq"]:checked') || {}).value || 'quarterly',
    taxed: stChecked('stDgTaxed'),
    inflation: stNum('stDgInflation', 0) / 100,
  };
  const target = stNum('stDgTarget', 0);
  const basis  = (document.querySelector('input[name="stDgBasis"]:checked') || {}).value || 'nominal';

  // 축: 사용자 칸 입력(원) — 음수/중복 제거 + 오름차순(차트·표용).
  const clean = arr => [...new Set(arr.filter(v => !isNaN(v) && v >= 0))].sort((a, b) => a - b);
  const monthlys = clean(stDgAxes.monthly);
  const initials = clean(stDgAxes.initial);
  const palette = ['#0052ff', '#05b169', '#7B1FA2', '#E8830C', '#C62828', '#0097A7', '#00897B', '#5E35B1', '#D81B60', '#3949AB'];

  const datasets = initials.map((init, i) => ({
    label: '초기 ' + stFmtKRW(init),
    data: monthlys.map(m => stDivGoalYears(base, init, m, target, basis)),
    borderColor: palette[i % palette.length],
    backgroundColor: 'transparent',
    pointRadius: 3, borderWidth: 2, spanGaps: false, tension: 0.2,
  }));
  stDrawChart('stDgChart', monthlys.map(m => stFmtKRW(m)), datasets, v => Math.round(v) + '년');

  // 표: 행 = 초기금, 열 = 월적립, 값 = 년수
  const head = '<tr><th>초기금 \\ 월적립</th>' + monthlys.map(m => `<th>${stFmtKRW(m)}</th>`).join('') + '</tr>';
  const rows = initials.map((init, i) =>
    `<tr><td>${stFmtKRW(init)}</td>` +
    datasets[i].data.map(v => `<td>${v == null ? '—' : v + '년'}</td>`).join('') + '</tr>'
  ).join('');
  document.getElementById('stDgTable').innerHTML = head + rows;
}

// ───────────────────────── 초기화 ─────────────────────────

function stInit() {
  document.querySelectorAll('.st-tab-btn').forEach(b => {
    b.addEventListener('click', () => stSwitchTab(b.dataset.tab));
  });
  const wire = (panelId, renderFn) => {
    document.querySelectorAll('#' + panelId + ' input').forEach(el => {
      el.addEventListener('input', renderFn);
      el.addEventListener('change', renderFn);
    });
    renderFn();
  };
  wire('stPanel-compound', stRenderCompound);
  wire('stPanel-inflation', stRenderInflation);
  wire('stPanel-realvalue', stRenderRealValue);
  wire('stPanel-dividend', stRenderDividend);

  // 배당 목표 역산 — 동적 축 칸 (입력 편집·삭제·추가는 위임)
  stRenderAxisChips('monthly');
  stRenderAxisChips('initial');
  ['stDgMonthlyChips', 'stDgInitialChips'].forEach(id => {
    const wrap = document.getElementById(id);
    if (!wrap) return;
    wrap.addEventListener('input', e => {
      const inp = e.target.closest('input[data-axis]'); if (!inp) return;
      stDgAxes[inp.dataset.axis][+inp.dataset.i] = parseFloat(inp.value) || 0;
      stRenderDividendGoal();
    });
    wrap.addEventListener('click', e => {
      const del = e.target.closest('.st-axis-del'); if (!del) return;
      const ax = del.dataset.axis;
      if (stDgAxes[ax].length <= 1) return;   // 최소 1칸 유지
      stDgAxes[ax].splice(+del.dataset.i, 1);
      stRenderAxisChips(ax);
      stRenderDividendGoal();
    });
  });
  document.querySelectorAll('.st-axis-add').forEach(btn => btn.addEventListener('click', () => {
    const ax = btn.dataset.axis;
    const arr = stDgAxes[ax];
    arr.push(arr.length ? arr[arr.length - 1] + (ax === 'monthly' ? 500000 : 50000000) : 0);
    stRenderAxisChips(ax);
    stRenderDividendGoal();
  }));
  wire('stPanel-dividendgoal', stRenderDividendGoal);

  stSwitchTab('compound');
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', stInit);
  } else {
    stInit();
  }
}
