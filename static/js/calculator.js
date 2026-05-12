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
  document.getElementById('runBtnText').style.display    = 'none';
  document.getElementById('runBtnSpinner').style.display = 'inline';

  const rebalMode    = document.querySelector('input[name="rebal"]:checked').value;
  const dividendMode = document.querySelector('input[name="dividend"]:checked').value;
  const bandWidth    = Number(document.getElementById('bandSlider').value) / 100;

  const payload = {
    tickers:              tickers.map(t => ({ code: t.code, weight: t.weight / 100 })),
    initial_capital:      Number(document.getElementById('initialCapital').value),
    monthly_contribution: Number(document.getElementById('monthlyContrib').value),
    years:                Number(document.getElementById('yearsSlider').value),
    rebal_mode:           rebalMode,
    band_width:           bandWidth,
    dividend_mode:        dividendMode,
  };

  try {
    const res  = await fetch('/api/calculator/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.error) { alert('오류: ' + data.error); return; }
    renderResult(data, payload);
  } catch (err) {
    alert('서버 오류: ' + err.message);
  } finally {
    btn.disabled = false;
    document.getElementById('runBtnText').style.display    = 'inline';
    document.getElementById('runBtnSpinner').style.display = 'none';
  }
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
// 세금 엔진
// ═══════════════════════════════════════════════════════════

let taxEnabled     = false;
let taxAccounts    = [];
let taxResultCache = null;
let taxCurrentView = 'before';
const ACCOUNT_TYPES = ['위탁', 'ISA', '연금저축', 'IRP'];

// ── 토글 ──
function toggleTax() {
  taxEnabled = !taxEnabled;
  const wrap  = document.getElementById('taxToggleWrap');
  const thumb = document.getElementById('taxToggleThumb');
  const label = document.getElementById('taxToggleLabel');
  const panel = document.getElementById('taxPanel');
  wrap.style.background = taxEnabled ? 'var(--blue)' : 'var(--border)';
  thumb.style.left      = taxEnabled ? '23px' : '3px';
  label.textContent     = taxEnabled ? 'ON'  : 'OFF';
  label.style.color     = taxEnabled ? 'var(--blue)' : 'var(--text-muted)';
  panel.style.display   = taxEnabled ? 'block' : 'none';
  if (taxEnabled && taxAccounts.length === 0) addTaxAccount();
  taxResultCache = null;
  document.getElementById('taxCompareSection').style.display = 'none';
}

// ── 계좌 추가/삭제 ──
function addTaxAccount() {
  taxAccounts.push({ type: '위탁', pct: 100 });
  rebalancePcts();
  renderTaxAccounts();
}

function removeTaxAccount(idx) {
  taxAccounts.splice(idx, 1);
  if (taxAccounts.length > 0) rebalancePcts();
  renderTaxAccounts();
}

function updateTaxAccountType(idx, type) {
  taxAccounts[idx].type = type;
  renderTaxAccounts();
}

function updateTaxAccountPct(idx, val) {
  // 마지막 계좌는 나머지로 자동 조정
  taxAccounts[idx].pct = Math.max(0, Math.min(100, Number(val) || 0));
  if (idx < taxAccounts.length - 1) {
    const remaining = 100 - taxAccounts.slice(0, -1).reduce((s, a) => s + a.pct, 0);
    taxAccounts[taxAccounts.length - 1].pct = Math.max(0, remaining);
  }
  renderTaxAccounts();
}

function rebalancePcts() {
  const n = taxAccounts.length;
  if (n === 0) return;
  const base = Math.floor(100 / n);
  let   rem  = 100 - base * n;
  taxAccounts.forEach((a, i) => { a.pct = base + (i === 0 ? rem : 0); });
}

function getAccountAmounts(acc) {
  const totalInitial = Number(document.getElementById('initialCapital').value) || 0;
  const totalMonthly = Number(document.getElementById('monthlyContrib').value)  || 0;
  return {
    initial_capital:      Math.round(totalInitial * acc.pct / 100),
    monthly_contribution: Math.round(totalMonthly * acc.pct / 100),
  };
}

function hasPensionAccount() {
  return taxAccounts.some(a => a.type === '연금저축' || a.type === 'IRP');
}

// ── 계좌 UI 렌더링 ──
function renderTaxAccounts() {
  const n           = taxAccounts.length;
  const totalInit   = Number(document.getElementById('initialCapital').value) || 0;
  const totalMonthly= Number(document.getElementById('monthlyContrib').value) || 0;
  const list        = document.getElementById('taxAccountList');
  const isSingle    = n <= 1;

  if (n === 0) {
    list.innerHTML = '<div style="font-size:0.8rem;color:var(--text-muted);text-align:center;padding:8px;">계좌를 추가해주세요</div>';
    return;
  }

  // 할당 시각화 바 (2개 이상일 때)
  let allocBar = '';
  if (!isSingle) {
    const segments = taxAccounts.map(a => {
      const colors = { '위탁':'#1976D2','ISA':'#2E7D32','연금저축':'#7B1FA2','IRP':'#E65100' };
      return `<div style="flex:${a.pct};background:${colors[a.type]||'#90A4AE'};height:100%;
                           display:flex;align-items:center;justify-content:center;
                           font-size:10px;color:white;font-weight:700;min-width:0;overflow:hidden;">
                ${a.pct > 8 ? a.pct+'%' : ''}
              </div>`;
    }).join('');

    const totalPct = taxAccounts.reduce((s,a)=>s+a.pct, 0);
    const pctColor = Math.abs(totalPct-100)<1 ? '#2E7D32' : '#C62828';
    allocBar = `
      <div style="margin-bottom:10px;">
        <div style="display:flex;justify-content:space-between;font-size:0.75rem;color:var(--text-muted);margin-bottom:4px;">
          <span>초기 ${fmtTaxKRW(totalInit)} 배분</span>
          <span style="color:${pctColor};font-weight:700;">합계 ${totalPct}%</span>
        </div>
        <div style="height:20px;border-radius:8px;overflow:hidden;display:flex;background:var(--border);">
          ${segments}
        </div>
        <div style="display:flex;justify-content:space-between;font-size:0.75rem;color:var(--text-muted);margin-top:3px;">
          <span>월 납입 ${fmtTaxKRW(totalMonthly)} 배분</span>
        </div>
      </div>`;
  }

  // 계좌 행 렌더링
  const colors = { '위탁':'#1976D2','ISA':'#2E7D32','연금저축':'#7B1FA2','IRP':'#E65100' };
  const rows = taxAccounts.map((acc, i) => {
    const amounts = getAccountAmounts(acc);
    if (isSingle) {
      // 단일 계좌: 유형만 선택, 금액은 상단 설정 그대로
      return `
        <div style="background:var(--bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;
                    display:flex;align-items:center;gap:8px;">
          <select onchange="updateTaxAccountType(${i},this.value)"
            style="flex:1;border:1.5px solid var(--border);border-radius:7px;padding:6px 8px;font-size:0.85rem;background:white;">
            ${ACCOUNT_TYPES.map(t=>`<option value="${t}" ${acc.type===t?'selected':''}>${t}</option>`).join('')}
          </select>
          <span style="font-size:0.75rem;color:var(--text-muted);">상단 설정값 사용</span>
          <button onclick="removeTaxAccount(${i})"
            style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1rem;padding:0;">✕</button>
        </div>`;
    } else {
      // 복수 계좌: 비율 입력, 금액 자동 계산
      return `
        <div style="background:var(--bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">
            <div style="width:10px;height:10px;border-radius:50%;background:${colors[acc.type]||'#90A4AE'};flex-shrink:0;"></div>
            <select onchange="updateTaxAccountType(${i},this.value)"
              style="flex:1;border:1.5px solid var(--border);border-radius:7px;padding:5px 8px;font-size:0.82rem;background:white;">
              ${ACCOUNT_TYPES.map(t=>`<option value="${t}" ${acc.type===t?'selected':''}>${t}</option>`).join('')}
            </select>
            <div style="display:flex;align-items:center;gap:4px;width:80px;">
              <input type="number" value="${acc.pct}" min="0" max="100" step="1"
                onchange="updateTaxAccountPct(${i},this.value)"
                style="width:50px;border:1.5px solid var(--border);border-radius:6px;padding:4px 6px;font-size:0.82rem;text-align:center;">
              <span style="font-size:0.8rem;color:var(--text-muted);">%</span>
            </div>
            <button onclick="removeTaxAccount(${i})"
              style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1rem;padding:0;">✕</button>
          </div>
          <div style="display:flex;gap:12px;font-size:0.75rem;color:var(--text-muted);">
            <span>초기 <b style="color:var(--text);">${fmtTaxKRW(amounts.initial_capital)}</b></span>
            <span>월 <b style="color:var(--text);">${fmtTaxKRW(amounts.monthly_contribution)}</b></span>
          </div>
        </div>`;
    }
  }).join('');

  list.innerHTML = allocBar + rows;

  // 세액공제 재투자 메뉴 표시/숨김
  const deductWrap = document.getElementById('taxDeductionSection');
  if (deductWrap) deductWrap.style.display = hasPensionAccount() ? 'block' : 'none';

  // 납입한도 경고
  checkTaxLimits();
}

function fmtTaxKRW(v) {
  if (!v) return '₩0';
  if (Math.abs(v) >= 1e8) return '₩'+(v/1e8).toFixed(1)+'억';
  if (Math.abs(v) >= 1e4) return '₩'+(v/1e4).toFixed(0)+'만';
  return '₩'+Math.round(v).toLocaleString();
}

function checkTaxLimits() {
  const warnings = [];
  const totalMonthly = Number(document.getElementById('monthlyContrib').value) || 0;
  let pensionAnnual = 0, irpAnnual = 0;

  taxAccounts.forEach(a => {
    const monthly = Math.round(totalMonthly * a.pct / 100);
    if (a.type === '연금저축') pensionAnnual += monthly * 12;
    if (a.type === 'IRP')     irpAnnual     += monthly * 12;
  });

  const combined = pensionAnnual + irpAnnual;
  if (combined > 18_000_000)
    warnings.push(`⚠ 연금저축+IRP 연간 납입 합계 ${fmtTaxKRW(combined)}이 한도(1,800만)를 초과합니다.`);
  if (Math.min(pensionAnnual, 6_000_000) + irpAnnual > 9_000_000)
    warnings.push(`⚠ 세액공제 한도(900만) 초과분은 공제 불가합니다.`);

  const totalInitial = Number(document.getElementById('initialCapital').value) || 0;
  taxAccounts.forEach(a => {
    if (a.type === 'ISA') {
      const monthly = Math.round(totalMonthly * a.pct / 100);
      if (monthly * 12 > 20_000_000)
        warnings.push(`⚠ ISA 연간 납입 ${fmtTaxKRW(monthly*12)}이 한도(2,000만)를 초과합니다.`);
    }
  });

  const warnEl = document.getElementById('taxWarnings');
  if (warnEl) warnEl.innerHTML = warnings
    .map(w=>`<div style="font-size:0.75rem;color:#C62828;background:#FFEBEE;padding:6px 10px;border-radius:6px;margin-bottom:4px;">${w}</div>`)
    .join('');
}

// ── 실행 ──
const _origRunCalc = window.runCalculator;
window.runCalculator = async function() {
  if (!taxEnabled) return _origRunCalc();

  if (tickers.length === 0) { alert('종목을 최소 1개 이상 추가해주세요.'); return; }
  if (taxAccounts.length === 0) { alert('계좌를 추가해주세요.'); return; }
  const totalWeight = tickers.reduce((s, t) => s + t.weight, 0);
  if (totalWeight > 100) { alert('비중 합계가 100%를 초과했어요.'); return; }

  const btn = document.getElementById('runBtn');
  btn.disabled = true;
  document.getElementById('runBtnText').style.display    = 'none';
  document.getElementById('runBtnSpinner').style.display = 'inline';

  const totalInitial = Number(document.getElementById('initialCapital').value) || 0;
  const totalMonthly = Number(document.getElementById('monthlyContrib').value) || 0;
  const isSingle     = taxAccounts.length === 1;

  const accountsPayload = taxAccounts.map(a => ({
    type:                 a.type,
    initial_capital:      isSingle ? totalInitial : Math.round(totalInitial * a.pct / 100),
    monthly_contribution: isSingle ? totalMonthly : Math.round(totalMonthly * a.pct / 100),
  }));

  const payload = {
    tickers:            tickers.map(t => ({ code: t.code, weight: t.weight / 100 })),
    years:              Number(document.getElementById('yearsSlider').value),
    rebal_mode:         document.querySelector('input[name="rebal"]:checked').value,
    dividend_mode:      document.querySelector('input[name="dividend"]:checked').value,
    accounts:           accountsPayload,
    user_settings: {
      earned_income: Number(document.getElementById('taxEarnedIncome').value) || 0,
      age:           Number(document.getElementById('taxAge').value) || 40,
      isa_type:      'general',
    },
    deduction_reinvest: document.getElementById('taxDeductionReinvest')?.checked ?? true,
    deduction_account:  document.getElementById('taxDeductionAccount')?.value ?? '위탁',
  };

  try {
    const res  = await fetch('/api/tax/run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.error) { alert('오류: ' + data.error); return; }
    taxResultCache  = data;
    taxCurrentView  = 'before';
    // 기존 renderResult로 히스토그램까지 전부 렌더링
    renderResult(data['before'], { years: payload.years });
    renderTaxCompareBanner(data);
  } catch(err) {
    alert('서버 오류: ' + err.message);
  } finally {
    btn.disabled = false;
    document.getElementById('runBtnText').style.display    = 'inline';
    document.getElementById('runBtnSpinner').style.display = 'none';
  }
};

// ── 세전/세후 전환 ──
function switchTaxView(view) {
  taxCurrentView = view;
  document.getElementById('taxViewBefore').classList.toggle('active', view === 'before');
  document.getElementById('taxViewAfter').classList.toggle('active',  view === 'after');
  if (taxResultCache) {
    renderResult(taxResultCache[view], { years: document.getElementById('yearsSlider').value });
    renderTaxCompareBanner(taxResultCache);
  }
}

function renderTaxCompareBanner(data) {
  const tabs = document.getElementById('taxViewTabs');
  if (tabs) tabs.style.display = 'block';

  const before = data['before'];
  const after  = data['after'];
  const bEl    = document.getElementById('taxAccountBreakdown');
  if (!bEl) return;

  const bp50 = before.distribution?.end_value?.p50;
  const ap50 = after.distribution?.end_value?.p50;
  const diff = ap50 && bp50 ? ap50 - bp50 : 0;
  const pct  = bp50 && bp50 > 0 ? (diff / bp50 * 100).toFixed(1) : '0';

  bEl.innerHTML = `
    <div style="background:var(--bg);border-radius:10px;padding:12px;font-size:0.82rem;">
      <div style="font-weight:700;margin-bottom:8px;">세금 영향 요약 (중앙값 기준)</div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;">
        <div><span style="color:var(--text-muted);">세금 미적용</span>
             <span style="font-weight:700;margin-left:6px;">${fmtTaxKRW(bp50)}</span></div>
        <div>→</div>
        <div><span style="color:var(--text-muted);">세금 적용</span>
             <span style="font-weight:700;margin-left:6px;">${fmtTaxKRW(ap50)}</span></div>
        <div><span style="color:${diff>=0?'#2E7D32':'#C62828'};font-weight:700;">
          ${diff>=0?'+':''}${fmtTaxKRW(diff)} (${pct}%)
        </span></div>
      </div>
      ${data.warnings?.length ? data.warnings.map(w=>`<div style="margin-top:6px;font-size:0.75rem;color:#C62828;">${w}</div>`).join('') : ''}
    </div>`;
}

// ── 세금 결과 렌더링 ──
function renderTaxResult(data, view) {
  const result = data[view];
  document.getElementById('resultEmpty').style.display   = 'none';
  document.getElementById('resultContent').style.display = 'block';
  const taxTabs = document.getElementById('taxViewTabs');
  if (taxTabs) taxTabs.style.display = 'block';

  // 계좌별 breakdown
  const breakdown = result.breakdown || [];
  const bdEl = document.getElementById('taxAccountBreakdown');
  if (bdEl && breakdown.length) {
    bdEl.innerHTML = `
      <div style="background:var(--bg);border-radius:10px;padding:12px;">
        <div style="font-size:0.8rem;font-weight:700;margin-bottom:8px;">계좌별 결과 (${view==='after'?'세금 적용':'세금 미적용'})</div>
        ${breakdown.map(b => `
          <div style="display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid var(--border);font-size:0.82rem;">
            <span style="min-width:70px;font-weight:600;">${b.account_type}</span>
            <span style="flex:1;color:var(--text-muted);font-size:0.75rem;">납입 ${fmtTaxKRW(b.total_contrib)}</span>
            <span style="font-weight:700;">${fmtTaxKRW(b.after_tax_end)}</span>
            ${b.total_deduction>0 ? `<span style="color:var(--blue);font-size:0.72rem;">+${fmtTaxKRW(b.total_deduction)} 환급</span>` : ''}
          </div>`).join('')}
        <div style="display:flex;align-items:center;gap:8px;padding:8px 0;font-weight:700;font-size:0.85rem;">
          <span style="min-width:70px;">합계</span>
          <span style="flex:1;"></span>
          <span>${fmtTaxKRW(result.grand_total || result.total_end_value)}</span>
          ${view==='after'&&result.total_deduction>0 ? `<span style="color:var(--blue);font-size:0.72rem;">환급 ${fmtTaxKRW(result.total_deduction)} 포함</span>` : ''}
        </div>
      </div>`;
  }

  // 분포 카드
  const ev = result.total_end_value || 0;
  const iv = result.total_invested  || 0;
  document.getElementById('distP50').textContent = fmtTaxKRW(ev);
  document.getElementById('distP10').textContent = fmtTaxKRW(iv);
  document.getElementById('distP90').textContent = fmtTaxKRW(result.grand_total || ev);

  document.getElementById('resultPeriodLabel').textContent =
    `${breakdown.length}개 계좌 합산 | ${view==='after'?'세금 적용':'세금 미적용'}`;

  // 가치 추이 차트
  if (result.history && result.history.length) {
    renderTaxHistoryChart(result.history);
  }
}

function renderTaxHistoryChart(history) {
  // ── 기존 차트 모두 제거 ──
  Object.keys(chartInstances).forEach(k => {
    if (chartInstances[k]) { chartInstances[k].destroy(); chartInstances[k] = null; }
  });

  const ctx = document.getElementById('rollingChart').getContext('2d');
  chartInstances['rollingChart'] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: history.map(h => h.date),
      datasets: [{
        data: history.map(h => h.portfolio_value),
        borderColor: '#1976D2', borderWidth: 2,
        backgroundColor: 'rgba(25,118,210,0.08)',
        fill: true, pointRadius: 0, tension: 0.3,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend:{display:false}, tooltip:{
        callbacks:{ label: c => fmtTaxKRW(c.parsed.y) }
      }},
      scales: {
        x: { ticks:{maxTicksLimit:8,font:{size:10},color:'#90A4AE'},grid:{display:false}},
        y: { ticks:{font:{size:10},color:'#90A4AE',callback:v=>fmtTaxKRW(v)},grid:{color:'rgba(0,0,0,0.04)'}}
      }
    }
  });
}