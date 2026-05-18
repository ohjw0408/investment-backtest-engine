/**
 * Domino Invest — 투자 계산기 JS
 */

// ── 상태 ──
const tickers = [];
let searchTimer  = null;
const chartInstances = {};  // 모든 차트 인스턴스 관리

// ── 초기화 ──
document.addEventListener('DOMContentLoaded', () => {

  document.getElementById('initialCapital').addEventListener('input', e => {
    document.getElementById('initialHint').textContent = '₩' + Number(e.target.value).toLocaleString();
  });

  document.getElementById('monthlyContrib').addEventListener('input', e => {
    document.getElementById('monthlyHint').textContent = '₩' + Number(e.target.value).toLocaleString();
  });

  document.getElementById('yearsSlider').addEventListener('input', e => {
    document.getElementById('yearsLabel').textContent = e.target.value + '년';
  });

  document.querySelectorAll('input[name="rebal"]').forEach(r => {
    r.addEventListener('change', () => {
      document.getElementById('bandSettings').style.display =
        r.value === 'band' ? 'block' : 'none';
    });
  });

  document.getElementById('bandSlider').addEventListener('input', e => {
    document.getElementById('bandLabel').textContent   = e.target.value + '%';
    document.getElementById('bandNoteVal').textContent = e.target.value + '%';
  });

  // 종목 검색
  const searchInput = document.getElementById('tickerSearchInput');
  const dropdown    = document.getElementById('tickerDropdown');

  searchInput.addEventListener('input', e => {
    const q = e.target.value.trim();
    if (!q) { dropdown.style.display = 'none'; return; }

    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      try {
        const res  = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();

        if (!data.length) {
          dropdown.innerHTML = '<div style="padding:12px;font-size:0.82rem;color:#90A4AE">검색 결과 없음</div>';
        } else {
          dropdown.innerHTML = data.map(item => `
            <div class="ticker-drop-item"
              onclick="addTicker('${item.code}', '${item.name.replace(/'/g, "\\'")}', '${item.badge}')">
              <span class="ticker-drop-badge"
                style="background:${badgeColor(item.badge)}22;color:${badgeColor(item.badge)}">
                ${item.badge}
              </span>
              <div>
                <div class="ticker-drop-code">${item.code}</div>
                <div class="ticker-drop-name">${item.name}</div>
              </div>
            </div>
          `).join('');
        }
        dropdown.style.display = 'block';
      } catch(e) { console.error(e); }
    }, 200);
  });

  document.addEventListener('click', e => {
    if (!searchInput.closest('.ticker-search-box').contains(e.target)) {
      dropdown.style.display = 'none';
    }
  });
});

function badgeColor(badge) {
  if (badge === 'KR ETF' || badge === 'KOSPI' || badge === 'KOSDAQ') return '#1976D2';
  if (badge === 'US ETF' || badge === 'NASDAQ' || badge === 'NYSE')   return '#2E7D32';
  return '#78909C';
}

// ── 균등 비중 재배분 ──
function redistributeWeights() {
  const n = tickers.length;
  if (n === 0) return;
  const base = Math.floor(100 / n);
  tickers.forEach((t, i) => {
    t.weight = (i === n - 1) ? 100 - base * (n - 1) : base;
  });
}

// ── 종목 추가 ──
function addTicker(code, name, badge) {
  if (tickers.find(t => t.code === code)) {
    alert(`${code}는 이미 추가되어 있어요.`);
    return;
  }
  tickers.push({ code, name, badge, weight: 0 });
  redistributeWeights();
  document.getElementById('tickerSearchInput').value = '';
  document.getElementById('tickerDropdown').style.display = 'none';
  renderTickers();
}

// ── 종목 제거 ──
function removeTicker(code) {
  const idx = tickers.findIndex(t => t.code === code);
  if (idx === -1) return;
  tickers.splice(idx, 1);
  if (tickers.length > 0) redistributeWeights();
  renderTickers();
}

// ── 비중 변경 ──
function onWeightChange(code, val) {
  const t = tickers.find(t => t.code === code);
  if (!t) return;
  t.weight = Math.max(0, Math.min(100, Number(val)));
  const item = document.querySelector(`.ticker-item[data-code="${code}"]`);
  if (item) {
    item.querySelector('.weight-input').value       = t.weight;
    item.querySelector('.ticker-item-slider').value = t.weight;
  }
  updateWeightBar();
}

// ── 종목 렌더링 ──
function renderTickers() {
  const list = document.getElementById('tickerList');
  if (tickers.length === 0) {
    list.innerHTML = '<div class="ticker-empty">종목을 검색해서 추가해보세요</div>';
    updateWeightBar();
    return;
  }
  list.innerHTML = tickers.map(t => `
    <div class="ticker-item" data-code="${t.code}">
      <div class="ticker-item-code">${t.code}</div>
      <div class="ticker-item-name">${t.name}</div>
      <div class="ticker-item-weight">
        <input type="number" class="weight-input" value="${t.weight}" min="0" max="100"
          oninput="onWeightChange('${t.code}', this.value)">
        <span class="weight-pct">%</span>
        <input type="range" class="ticker-item-slider" min="0" max="100" value="${t.weight}"
          oninput="onWeightChange('${t.code}', this.value)">
      </div>
      <button class="ticker-remove" onclick="removeTicker('${t.code}')">✕</button>
    </div>
  `).join('');
  updateWeightBar();
}

// ── 비중 합계 바 ──
function updateWeightBar() {
  const total = tickers.reduce((s, t) => s + t.weight, 0);
  const fill  = document.getElementById('weightFill');
  const label = document.getElementById('weightTotal');
  const warn  = document.getElementById('weightWarn');

  label.textContent = total + '%';
  fill.style.width  = Math.min(total, 100) + '%';

  if (total === 100) {
    fill.style.background = 'var(--green-light)';
    label.className = 'weight-total-num ok';
    warn.textContent = '';
  } else if (total > 100) {
    fill.style.background = 'var(--red-light)';
    label.className = 'weight-total-num over';
    warn.textContent = '⚠ 비중 합계가 100%를 초과했어요';
  } else {
    fill.style.background = 'var(--blue)';
    label.className = 'weight-total-num';
    warn.textContent = total > 0 ? `나머지 ${100 - total}%는 현금으로 유지됩니다` : '';
  }
}

// ── 시뮬레이션 실행 ──
async function runCalculator() {
  if (tickers.length === 0) { alert('종목을 최소 1개 이상 추가해주세요.'); return; }
  const totalWeight = tickers.reduce((s, t) => s + t.weight, 0);
  if (totalWeight > 100) { alert('비중 합계가 100%를 초과했어요. 조정해주세요.'); return; }

  const btn = document.getElementById('runBtn');
  btn.disabled = true;

  const rebalMode    = document.querySelector('input[name="rebal"]:checked').value;
  const dividendMode = document.querySelector('input[name="dividend"]:checked').value;
  const bandWidth    = Number(document.getElementById('bandSlider').value) / 100;

  const taxEnabled  = window.taxEnabled || false;
  const taxAccounts = window.taxAccounts || [];
  const isSingle    = taxAccounts.length <= 1;
  const totalInit   = Number(document.getElementById('initialCapital').value);
  const totalMon    = Number(document.getElementById('monthlyContrib').value);

  const accountType   = taxAccounts.length > 0 ? taxAccounts[0].type : '위탁';
  const effectiveInit = taxAccounts.length > 0
    ? taxAccounts.reduce((s,a) => s + (isSingle ? totalInit : Math.round(totalInit * a.pct/100)), 0)
    : totalInit;
  const effectiveMon = taxAccounts.length > 0
    ? taxAccounts.reduce((s,a) => s + (isSingle ? totalMon : Math.round(totalMon * a.pct/100)), 0)
    : totalMon;

  const payload = {
    tickers:              tickers.map(t => ({ code: t.code, weight: t.weight / 100 })),
    initial_capital:      isSingle ? totalInit : effectiveInit,
    monthly_contribution: isSingle ? totalMon  : effectiveMon,
    years:                Number(document.getElementById('yearsSlider').value),
    rebal_mode:           rebalMode,
    band_width:           bandWidth,
    dividend_mode:        dividendMode,
    tax_enabled:          taxEnabled,
    account_type:         accountType,
    isa_renewal:          taxEnabled && (document.getElementById('isaRenewalCheck')?.checked ?? false),
    gain_harvesting:      taxEnabled && (window.taxAccounts||[]).some(a => a.type === '위탁') && (document.getElementById('gainHarvestingCheck')?.checked ?? false),
    user_settings: taxEnabled ? {
      earned_income: Number(document.getElementById('taxEarnedIncome')?.value || 50000000),
      age:           Number(document.getElementById('taxAge')?.value || 40),
      isa_type:      'general',
    } : {},
  };

  showProgressUI();

  try {
    const submitRes = await fetch('/api/calculator/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const { task_id } = await submitRes.json();

    const result = await pollTask(task_id);

    hideProgressUI();
    renderResult(result, payload);
  } catch (err) {
    hideProgressUI();
    alert('오류: ' + err.message);
  } finally {
    btn.disabled = false;
    document.getElementById('runBtnText').style.display    = 'inline';
    document.getElementById('runBtnSpinner').style.display = 'none';
  }
}


async function pollTask(taskId, maxWait = 600000) {
  const start = Date.now();

  while (Date.now() - start < maxWait) {
    await new Promise(r => setTimeout(r, 1500));

    const res  = await fetch(`/api/task/${taskId}`);
    const data = await res.json();

    if (data.status === 'PENDING') {
      updateProgressUI({
        phase:    '대기 중',
        queuePos: data.queue_pos,
        percent:  0,
        eta:      null,
      });

    } else if (data.status === 'PROGRESS') {
      updateProgressUI({
        phase:   '계산 중',
        percent: data.percent,
        current: data.current,
        total:   data.total,
        elapsed: data.elapsed,
        eta:     data.eta,
      });

    } else if (data.status === 'SUCCESS') {
      return data.result;

    } else if (data.status === 'FAILURE') {
      throw new Error(data.error || '시뮬레이션 실패');
    }
  }
  throw new Error('시간 초과 (10분)');
}


// ── 진행 상황 UI ────────────────────────────────────────────
function showProgressUI() {
  document.getElementById('runBtnText').style.display    = 'none';
  document.getElementById('runBtnSpinner').style.display = 'inline';

  const empty = document.getElementById('resultEmpty');
  empty.style.display = 'flex';
  empty.innerHTML = `
    <div style="width:100%;padding:24px;">
      <div id="progressPhase"
           style="font-size:0.9rem;color:var(--text-muted);margin-bottom:8px;">
        준비 중...
      </div>
      <div style="background:var(--border);border-radius:8px;height:8px;overflow:hidden;margin-bottom:8px;">
        <div id="progressBar"
             style="background:var(--blue);height:100%;width:0%;transition:width 0.5s;border-radius:8px;">
        </div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:0.78rem;color:var(--text-muted);">
        <span id="progressDetail">계산 준비 중</span>
        <span id="progressEta"></span>
      </div>
    </div>`;
  document.getElementById('resultContent').style.display = 'none';
}

function updateProgressUI({ phase, queuePos, percent, current, total, elapsed, eta }) {
  const phaseEl  = document.getElementById('progressPhase');
  const barEl    = document.getElementById('progressBar');
  const detailEl = document.getElementById('progressDetail');
  const etaEl    = document.getElementById('progressEta');
  if (!phaseEl) return;

  if (queuePos > 0) {
    phaseEl.textContent  = `⏳ 대기 중 — 내 앞에 ${queuePos}개`;
    barEl.style.width    = '0%';
    detailEl.textContent = '이전 요청 처리 중...';
    etaEl.textContent    = '';
  } else {
    phaseEl.textContent  = `🔄 ${phase || '계산 중'} (${percent || 0}%)`;
    barEl.style.width    = `${percent || 0}%`;
    if (current && total) {
      detailEl.textContent = `${current} / ${total} 케이스`;
    }
    if (eta) {
      const m = Math.floor(eta / 60);
      const s = eta % 60;
      etaEl.textContent = m > 0
        ? `약 ${m}분 ${s}초 남음`
        : `약 ${s}초 남음`;
    }
  }
}

function hideProgressUI() {
  const empty = document.getElementById('resultEmpty');
  if (empty) empty.style.display = 'none';
}

// ── 결과 렌더링 ──
function renderResult(data, payload) {
  document.getElementById('resultEmpty').style.display   = 'none';
  document.getElementById('resultContent').style.display = 'block';

  const dist = data.distribution;

  document.getElementById('resultPeriodLabel').textContent =
    `${payload.years}년 | ${data.cases_count}개 롤링 케이스`;

  // 상단 카드
  document.getElementById('distP10').textContent = fmtKRW(dist.end_value.p10);
  document.getElementById('distP50').textContent = fmtKRW(dist.end_value.p50);
  document.getElementById('distP90').textContent = fmtKRW(dist.end_value.p90);

  // 롤링 케이스 차트
  renderRollingChart(data.cases);

  // 히스토그램들
  const histConfigs = [
    { id: 'histEndValue', key: 'end_value', fmt: fmtKRW,            color: '#1976D2', div: false },
    { id: 'histCagr',     key: 'cagr',      fmt: fmtPct,            color: '#43A047', div: false },
    { id: 'histMdd',      key: 'mdd',       fmt: fmtPct,            color: '#EF5350', div: false },
    { id: 'histSharpe',   key: 'sharpe',    fmt: v => v.toFixed(2), color: '#1976D2', div: false },
    { id: 'histSortino',  key: 'sortino',   fmt: v => v.toFixed(2), color: '#7B1FA2', div: false },
    { id: 'histCalmar',   key: 'calmar',    fmt: v => v.toFixed(2), color: '#F57C00', div: false },
    { id: 'histDiv',             key: 'total_dividend',         fmt: fmtKRW, color: '#00897B', div: true  },
    { id: 'histDivCagr',         key: 'dividend_cagr',          fmt: fmtPct, color: '#00897B', div: true  },
    { id: 'histLastYearDiv',     key: 'last_year_dividend',     fmt: fmtKRW, color: '#00897B', div: true  },
    { id: 'histDivYieldOnCost',  key: 'dividend_yield_on_cost', fmt: fmtPct, color: '#00897B', div: true  },
  ];

  const noDividend = dist.no_dividend === true;
  const divNote = dist.div_data_start
    ? `※ ${dist.div_data_start} 이후 ${dist.div_cases_count}개 케이스 기준`
    : '';

  histConfigs.forEach(cfg => {
    const isDivDisabled = cfg.div && noDividend;
    if (isDivDisabled) {
      // 배당 없는 포트폴리오 → 해당 없음 표시
      const card = document.getElementById(cfg.id).closest('.result-card');
      card.querySelector('.chart-wrap-sm').innerHTML =
        '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#90A4AE;font-size:0.82rem;">배당 데이터 없음</div>';
      const statsEl = document.getElementById(`stats${cfg.id.replace('hist','')}`);
      if (statsEl) statsEl.innerHTML = '';
      return;
    }

    renderHistogram(cfg.id, dist[cfg.key].values, cfg.color, cfg.fmt);
    renderHistStats(`stats${cfg.id.replace('hist', '')}`, dist[cfg.key], cfg.fmt);

    // 배당 히스토그램에 케이스 수 주석 표시
    if (cfg.div && divNote) {
      const card = document.getElementById(cfg.id).closest('.result-card');
      let note = card.querySelector('.div-note');
      if (!note) {
        note = document.createElement('div');
        note.className = 'div-note';
        note.style.cssText = 'font-size:0.7rem;color:#90A4AE;margin-top:4px;text-align:right;';
        card.appendChild(note);
      }
      note.textContent = divNote;
    }

    // 배당 CAGR 최소 기간 안내
    if (cfg.id === 'histDivCagr' && !noDividend) {
      const card = document.getElementById(cfg.id).closest('.result-card');
      let warn = card.querySelector('.div-cagr-warn');
      if (!warn) {
        warn = document.createElement('div');
        warn.className = 'div-cagr-warn';
        warn.style.cssText = 'font-size:0.7rem;color:#F9A825;margin-top:4px;';
        card.appendChild(warn);
      }
      const years = Number(document.getElementById('yearsSlider').value);
      warn.textContent = years < 3 ? '⚠ 배당 CAGR은 최소 3년 이상 시뮬레이션 시 의미 있는 값이 나옵니다' : '';
    }
  });
}

// ── 히스토그램 렌더링 ──
function renderHistogram(canvasId, values, color, fmtFn) {
  if (chartInstances[canvasId]) {
    chartInstances[canvasId].destroy();
  }

  const ctx  = document.getElementById(canvasId).getContext('2d');
  const bins = 15;
  const min  = Math.min(...values);
  const max  = Math.max(...values);
  const step = (max - min) / bins || 1;

  const counts = Array(bins).fill(0);
  values.forEach(v => {
    const idx = Math.min(Math.floor((v - min) / step), bins - 1);
    counts[idx]++;
  });

  const labels = counts.map((_, i) => fmtFn(min + step * (i + 0.5)));

  chartInstances[canvasId] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: counts,
        backgroundColor: color + '55',
        borderColor:     color,
        borderWidth: 1,
        borderRadius: 3,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: items => fmtFn(min + step * items[0].dataIndex),
            label: item  => `${item.raw}개 케이스`,
          }
        }
      },
      scales: {
        x: {
          ticks: { maxTicksLimit: 5, font: { size: 9 }, color: '#90A4AE' },
          grid: { display: false }
        },
        y: {
          ticks: { font: { size: 9 }, color: '#90A4AE', stepSize: 1 },
          grid: { color: 'rgba(0,0,0,0.04)' }
        }
      }
    }
  });
}

// ── 히스토그램 통계 ──
function renderHistStats(elId, distData, fmtFn) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.innerHTML = `
    <div class="hist-stat"><div class="hist-stat-label">하위10%</div><div class="hist-stat-value">${fmtFn(distData.p10)}</div></div>
    <div class="hist-stat"><div class="hist-stat-label">중앙값</div><div class="hist-stat-value">${fmtFn(distData.p50)}</div></div>
    <div class="hist-stat"><div class="hist-stat-label">평균</div><div class="hist-stat-value">${fmtFn(distData.mean)}</div></div>
    <div class="hist-stat"><div class="hist-stat-label">상위10%</div><div class="hist-stat-value">${fmtFn(distData.p90)}</div></div>
  `;
}

// ── 롤링 케이스 차트 ──
function renderRollingChart(cases) {
  if (chartInstances['rollingChart']) chartInstances['rollingChart'].destroy();

  const ctx    = document.getElementById('rollingChart').getContext('2d');
  const labels = cases.map(c => c.start.slice(0, 7));
  const values = cases.map(c => c.end_value);

  chartInstances['rollingChart'] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: values.map(v => v >= 0 ? 'rgba(67,160,71,0.6)' : 'rgba(239,83,80,0.6)'),
        borderColor:     values.map(v => v >= 0 ? '#43A047' : '#EF5350'),
        borderWidth: 1, borderRadius: 3,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => fmtKRW(c.raw) } }
      },
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { size: 10 }, color: '#90A4AE' }, grid: { display: false } },
        y: { ticks: { font: { family: 'DM Mono', size: 10 }, color: '#90A4AE', callback: v => fmtKRW(v) }, grid: { color: 'rgba(0,0,0,0.04)' } }
      }
    }
  });
}

// ── 포맷 헬퍼 ──
function fmtKRW(v) {
  if (Math.abs(v) >= 1e8) return '₩' + (v / 1e8).toFixed(1) + '억';
  if (Math.abs(v) >= 1e4) return '₩' + (v / 1e4).toFixed(0) + '만';
  return '₩' + Math.round(v).toLocaleString();
}

function fmtPct(v) {
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%';
}
// ═══════════════════════════════════════════════════════════
// 세금 토글 + 계좌 설정
// ═══════════════════════════════════════════════════════════

window.taxEnabled  = false;
window.taxAccounts = [];
const ACCOUNT_TYPES = ['위탁', 'ISA', '연금저축', 'IRP'];

function toggleTax() {
  window.taxEnabled = !window.taxEnabled;
  const wrap  = document.getElementById('taxToggleWrap');
  const thumb = document.getElementById('taxToggleThumb');
  const label = document.getElementById('taxToggleLabel');
  const panel = document.getElementById('taxPanel');
  wrap.style.background = window.taxEnabled ? 'var(--blue)' : 'var(--border)';
  thumb.style.left      = window.taxEnabled ? '23px' : '3px';
  label.textContent     = window.taxEnabled ? 'ON'  : 'OFF';
  label.style.color     = window.taxEnabled ? 'var(--blue)' : 'var(--text-muted)';
  panel.style.display   = window.taxEnabled ? 'block' : 'none';
  if (window.taxEnabled && window.taxAccounts.length === 0) addTaxAccount();
}

function addTaxAccount() {
  window.taxAccounts.push({ type: '위탁', pct: 100 });
  rebalancePcts();
  renderTaxAccounts();
}

function removeTaxAccount(idx) {
  window.taxAccounts.splice(idx, 1);
  if (window.taxAccounts.length > 0) rebalancePcts();
  renderTaxAccounts();
}

function updateTaxAccountType(idx, type) {
  window.taxAccounts[idx].type = type;
  renderTaxAccounts();
}

function updateTaxAccountPct(idx, val) {
  window.taxAccounts[idx].pct = Math.max(0, Math.min(100, Number(val) || 0));
  if (idx < window.taxAccounts.length - 1) {
    const used = window.taxAccounts.slice(0, -1).reduce((s, a) => s + a.pct, 0);
    window.taxAccounts[window.taxAccounts.length - 1].pct = Math.max(0, 100 - used);
  }
  renderTaxAccounts();
}

function rebalancePcts() {
  const n = window.taxAccounts.length;
  if (!n) return;
  const base = Math.floor(100 / n);
  const rem  = 100 - base * n;
  window.taxAccounts.forEach((a, i) => { a.pct = base + (i === 0 ? rem : 0); });
}

function fmtTaxKRW(v) {
  if (!v) return '₩0';
  if (Math.abs(v) >= 1e8) return '₩' + (v/1e8).toFixed(1) + '억';
  if (Math.abs(v) >= 1e4) return '₩' + Math.round(v/1e4) + '만';
  return '₩' + Math.round(v).toLocaleString();
}

function renderTaxAccounts() {
  const accs     = window.taxAccounts;
  const isSingle = accs.length <= 1;
  const totalI   = Number(document.getElementById('initialCapital').value) || 0;
  const totalM   = Number(document.getElementById('monthlyContrib').value)  || 0;
  const list     = document.getElementById('taxAccountList');
  if (!list) return;

  const colors = { '위탁':'#1976D2','ISA':'#2E7D32','연금저축':'#7B1FA2','IRP':'#E65100' };

  // 할당 바 (2개 이상)
  let allocBar = '';
  if (!isSingle) {
    const segs = accs.map(a =>
      `<div style="flex:${a.pct};background:${colors[a.type]||'#90A4AE'};height:100%;
        display:flex;align-items:center;justify-content:center;
        font-size:10px;color:white;font-weight:700;overflow:hidden;min-width:0;">
        ${a.pct > 8 ? a.pct+'%' : ''}</div>`).join('');
    const tot   = accs.reduce((s,a) => s+a.pct, 0);
    const color = Math.abs(tot-100)<1 ? '#2E7D32' : '#C62828';
    allocBar = `
      <div style="margin-bottom:10px;">
        <div style="display:flex;justify-content:space-between;font-size:0.75rem;color:var(--text-muted);margin-bottom:4px;">
          <span>초기 ${fmtTaxKRW(totalI)} / 월 ${fmtTaxKRW(totalM)} 배분</span>
          <span style="color:${color};font-weight:700;">합계 ${tot}%</span>
        </div>
        <div style="height:20px;border-radius:8px;overflow:hidden;display:flex;background:var(--border);">${segs}</div>
      </div>`;
  }

  list.innerHTML = allocBar + accs.map((acc, i) => {
    if (isSingle) return `
      <div style="background:var(--bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;display:flex;align-items:center;gap:8px;">
        <select onchange="updateTaxAccountType(${i},this.value)"
          style="flex:1;border:1.5px solid var(--border);border-radius:7px;padding:6px 8px;font-size:0.85rem;background:white;">
          ${ACCOUNT_TYPES.map(t=>`<option value="${t}" ${acc.type===t?'selected':''}>${t}</option>`).join('')}
        </select>
        <span style="font-size:0.75rem;color:var(--text-muted);">상단 설정값 사용</span>
        <button onclick="removeTaxAccount(${i})" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1rem;">✕</button>
      </div>`;

    const initAmt = Math.round(totalI * acc.pct / 100);
    const monAmt  = Math.round(totalM  * acc.pct / 100);
    return `
      <div style="background:var(--bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
          <div style="width:10px;height:10px;border-radius:50%;background:${colors[acc.type]||'#90A4AE'};flex-shrink:0;"></div>
          <select onchange="updateTaxAccountType(${i},this.value)"
            style="flex:1;border:1.5px solid var(--border);border-radius:7px;padding:5px 8px;font-size:0.82rem;background:white;">
            ${ACCOUNT_TYPES.map(t=>`<option value="${t}" ${acc.type===t?'selected':''}>${t}</option>`).join('')}
          </select>
          <input type="number" value="${acc.pct}" min="0" max="100" step="1"
            onchange="updateTaxAccountPct(${i},this.value)"
            style="width:50px;border:1.5px solid var(--border);border-radius:6px;padding:4px;font-size:0.82rem;text-align:center;">
          <span style="font-size:0.78rem;color:var(--text-muted);">%</span>
          <button onclick="removeTaxAccount(${i})" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1rem;">✕</button>
        </div>
        <div style="font-size:0.75rem;color:var(--text-muted);">
          초기 <b style="color:var(--text);">${fmtTaxKRW(initAmt)}</b> &nbsp;
          월 <b style="color:var(--text);">${fmtTaxKRW(monAmt)}</b>
        </div>
      </div>`;
  }).join('');

  // 세액공제 메뉴 표시 조건
  const hasPension = accs.some(a => a.type === '연금저축' || a.type === 'IRP');
  const dedSec     = document.getElementById('taxDeductionSection');
  if (dedSec) dedSec.style.display = hasPension ? 'block' : 'none';

  // ISA 풍차돌리기 섹션
  const hasISA     = accs.some(a => a.type === 'ISA');
  const isaRenSec  = document.getElementById('isaRenewalSection');
  if (isaRenSec) isaRenSec.style.display = hasISA ? 'block' : 'none';

  // 절세 매도 섹션 (위탁 계좌)
  const hasWitaku  = accs.some(a => a.type === '위탁');
  const ghSec      = document.getElementById('gainHarvestingSection');
  if (ghSec) ghSec.style.display = hasWitaku ? 'block' : 'none';

  checkTaxLimits();
}

function checkTaxLimits() {
  const totalM  = Number(document.getElementById('monthlyContrib').value) || 0;
  const accs    = window.taxAccounts;
  const isSingle = accs.length <= 1;
  const warnings = [];

  let pensionAnn = 0, irpAnn = 0;
  accs.forEach(a => {
    const m = isSingle ? totalM : Math.round(totalM * a.pct / 100);
    if (a.type === '연금저축') pensionAnn += m * 12;
    if (a.type === 'IRP')     irpAnn     += m * 12;
  });
  if (pensionAnn + irpAnn > 18_000_000)
    warnings.push(`⚠ 연금저축+IRP 연간 합계 ${fmtTaxKRW(pensionAnn+irpAnn)}이 한도(1,800만)를 초과합니다.`);
  if (Math.min(pensionAnn, 6_000_000) + irpAnn > 9_000_000)
    warnings.push(`⚠ 세액공제 한도(900만) 초과분은 공제 불가합니다.`);

  const warnEl = document.getElementById('taxWarnings');
  if (warnEl) warnEl.innerHTML = warnings.map(w =>
    `<div style="font-size:0.75rem;color:#C62828;background:#FFEBEE;padding:6px 10px;border-radius:6px;margin-bottom:4px;">${w}</div>`
  ).join('');
}