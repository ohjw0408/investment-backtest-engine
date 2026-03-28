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
    { id: 'histDiv',      key: 'total_dividend', fmt: fmtKRW,       color: '#00897B', div: true  },
    { id: 'histDivCagr',  key: 'dividend_cagr',  fmt: fmtPct,       color: '#00897B', div: true  },
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
