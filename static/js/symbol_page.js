// symbol.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 데이터는 #page-data JSON
const CODE = JSON.parse(document.getElementById('page-data').textContent).code;
const DIV_INITIAL_ROWS = 12;

function fmtPrice(v, currency) {
  if (v === null || v === undefined) return '—';
  if (currency === 'PT') {   // 지수 = 포인트(통화 기호 없음)
    if (v >= 1000) return Math.round(v).toLocaleString();
    return v.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }
  if (currency === 'KRW') return '₩' + Math.round(v).toLocaleString();
  return '$' + v.toFixed(2);
}

function fmtDiv(v, currency) {
  if (!v) return '—';
  if (currency === 'KRW') return '₩' + Math.round(v).toLocaleString();
  return '$' + parseFloat(v).toFixed(4);
}

function fmtMcap(v, currency) {
  if (!v) return '—';
  if (currency === 'KRW') {
    if (v >= 1e12) return '₩' + (v / 1e12).toFixed(1) + '조';
    if (v >= 1e8)  return '₩' + Math.round(v / 1e8).toLocaleString() + '억';
    return '₩' + Math.round(v).toLocaleString();
  }
  if (v >= 1e12) return '$' + (v / 1e12).toFixed(2) + 'T';
  if (v >= 1e9)  return '$' + (v / 1e9).toFixed(1) + 'B';
  if (v >= 1e6)  return '$' + (v / 1e6).toFixed(1) + 'M';
  return '$' + Math.round(v).toLocaleString();
}

function fmtWeight(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  return Number(v).toFixed(2) + '%';
}

const escHtml = window.mmEsc;  // E-1 공용화: 전역 mmEsc(base.html) 단일 구현 — 로컬 복붙 제거 (2026-07-03)

function validHoldings(holdings) {
  return (holdings || []).map(h => ({
    ...h,
    weight_pct: Number(h.weight_pct)
  })).filter(h => h.code && Number.isFinite(h.weight_pct) && h.weight_pct > 0);
}

function dividendRowsHtml(dividends, currency, expanded) {
  const list = expanded ? (dividends || []) : (dividends || []).slice(0, DIV_INITIAL_ROWS);
  return list.map(d => `
    <tr${d.est ? ' class="div-est"' : ''}>
      <td>${escHtml(d.date)}${d.est ? ' <span class="div-est-tag" title="상장 이전 구간이라 실제 지급 내역이 아니라 기초지수로 추정한 값입니다">추정</span>' : ''}</td>
      <td>${fmtDiv(d.dividend, currency)}</td>
    </tr>
  `).join('');
}

// ── 배당 그래프 ──────────────────────────────────────────
// 가격 차트와 겹치지 않고 별도로 그린다. 주가(예: 11,000원)와 분기배당(예: 150원)은
// 자릿수가 달라 한 축에 두면 배당이 0에 붙은 직선이 되고, 이중축으로 억지로 맞추면
// 두 선의 관계가 축 스케일이 만든 착시가 된다. 또 라인차트의 기간 선택(1개월~전체)과도
// 안 맞는다 — 배당은 분기 이벤트라 1개월 뷰에선 막대가 0~1개다.
//
// 막대(주당 배당금)와 선(배당수익률)은 같은 축에 둘 근거가 있다: 수익률 = 배당/주가라
// 정의상 관계가 실재한다. "배당은 늘었는데 주가가 더 올라 수익률은 떨어졌다"가 보인다.
let divChart   = null;
let divMode    = 'year';   // 'year' | 'quarter'
let divShowEst = false;    // 상장 전 추정 구간 포함 여부 (기본 끔)

function divBuckets(dividends, prices, mode, includeEst) {
  let divs = (dividends || []).filter(d => d && d.date && Number(d.dividend) > 0);
  // 기본은 실측만. 백필은 상장 전 60년치를 만들어 두기도 해서(458730은 273건 중 237건),
  // 다 그리면 추정 구간이 화면을 지배하고 수익률 선은 오른쪽 끝 몇 점으로 뭉개진다.
  // 가격 차트도 volume=0 행을 빼므로 기본값을 맞춘다 — 보고 싶으면 켤 수 있다.
  if (!includeEst) divs = divs.filter(d => !d.est);
  if (!divs.length) return [];
  // 버킷별 마지막 종가 — 배당수익률 분모. prices는 실데이터만(상장 후)이라
  // 상장 이전 버킷은 자연히 분모가 없어 수익률 선이 끊긴다(정확한 동작).
  const lastClose = {};
  (prices || []).forEach(p => {
    const k = mode === 'year' ? p.date.slice(0, 4) : bucketOf(p.date);
    lastClose[k] = p.close;
  });
  const map = new Map();
  divs.forEach(d => {
    const k = mode === 'year' ? d.date.slice(0, 4) : bucketOf(d.date);
    if (!map.has(k)) map.set(k, { key: k, sum: 0, n: 0, nEst: 0 });
    const b = map.get(k);
    b.sum += Number(d.dividend);
    b.n += 1;
    if (d.est) b.nEst += 1;
  });
  const nowKey = mode === 'year'
    ? String(new Date().getFullYear())
    : bucketOf(new Date().toISOString().slice(0, 10));
  // 상장 연도(또는 분기)도 반쪽이다 — 458730은 2023-06 상장이라 2023 막대가 반년치뿐인데,
  // 실선으로 그리면 "2023년엔 배당이 적었다"로 읽힌다. 진행중과 같은 종류의 착시.
  const realStart = (prices || []).length ? prices[0].date : null;
  const startKey  = realStart
    ? (mode === 'year' ? realStart.slice(0, 4) : bucketOf(realStart))
    : null;
  const startsMidBucket = realStart && (mode === 'year'
    ? realStart.slice(5) !== '01-01'
    : !['01-01', '04-01', '07-01', '10-01'].includes(realStart.slice(5)));
  return [...map.values()]
    .sort((a, b) => (a.key < b.key ? -1 : 1))
    .map(b => ({
      ...b,
      // 미완결 구간 — 아직 배당이 다 안 나와 막대가 낮다. 구분 안 하면 "배당 삭감"으로 읽힌다.
      ongoing: b.key === nowKey,
      partial: !!(startsMidBucket && b.key === startKey),
      // 상장 이전 = 기초지수로 추정한 값. 하나라도 섞이면 표시한다(과소 표기보다 과다 표기).
      est: b.nEst > 0,
      yield: lastClose[b.key] ? (b.sum / lastClose[b.key]) * 100 : null,
    }));
}

function bucketOf(dateStr) {
  const q = Math.floor((Number(dateStr.slice(5, 7)) - 1) / 3) + 1;
  return `${dateStr.slice(0, 4)} Q${q}`;
}

function dividendChartHtml(dividends) {
  const divs = (dividends || []).filter(d => Number(d.dividend) > 0);
  if (divs.length < 2) return '';   // 1건 이하면 추세랄 게 없다
  const hasEst = divs.some(d => d.est);
  return `
    <div class="div-chart-head">
      <div class="div-mode-switch" role="group" aria-label="배당 집계 단위">
        <button type="button" class="div-mode-btn active" data-divmode="year" onclick="setDivMode('year')">연간</button>
        <button type="button" class="div-mode-btn" data-divmode="quarter" onclick="setDivMode('quarter')">분기</button>
      </div>
      ${hasEst ? `
      <label class="div-est-toggle">
        <input type="checkbox" id="divEstToggle" onchange="setDivShowEst(this.checked)">
        <span>상장 전 추정 포함</span>
      </label>` : ''}
    </div>
    <div class="div-chart-wrap"><canvas id="dividendChart"></canvas></div>
    <div class="div-legend">
      <span class="div-lg"><i class="sw-solid"></i>주당 배당금</span>
      <span class="div-lg"><i class="sw-line"></i>배당수익률</span>
      <span class="div-lg"><i class="sw-ongoing"></i>진행중·부분 구간</span>
      <span class="div-lg div-lg-est" hidden><i class="sw-est"></i>상장 전 추정</span>
    </div>
    ${hasEst ? '<div class="div-est-note">이 종목은 상장 전 구간이 기초지수로 <b>추정</b>된 값입니다. 기본 그래프는 실제 지급분만 보여줍니다 — 위 체크박스로 추정 구간까지 볼 수 있고, 백테스트는 추정값도 함께 씁니다.</div>' : ''}
  `;
}

function setDivShowEst(on) {
  divShowEst = !!on;
  const lg = document.querySelector('.div-lg-est');
  if (lg) lg.hidden = !divShowEst;
  renderDividendChart();
}

function setDivMode(mode) {
  if (divMode === mode) return;
  divMode = mode;
  document.querySelectorAll('.div-mode-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.divmode === mode));
  renderDividendChart();
}

function renderDividendChart() {
  const canvas = document.getElementById('dividendChart');
  if (!canvas || !allData) return;
  if (divChart) { divChart.destroy(); divChart = null; }
  const buckets = divBuckets(allData.dividends, allData.prices, divMode, divShowEst);
  if (!buckets.length) return;

  const BAR = '#2E7D32', LINE = '#E65100';
  const soft = b => b.est || b.ongoing || b.partial;   // 반투명 + 점선으로 '그대로 비교하면 안 되는 막대' 표시
  const barColor = b => (soft(b) ? 'rgba(46,125,50,0.32)' : BAR);
  const hasYield = buckets.some(b => b.yield !== null);
  const curr = allData.currency;

  divChart = new Chart(canvas.getContext('2d'), {
    data: {
      labels: buckets.map(b => b.key),
      datasets: [
        {
          type: 'bar', label: '주당 배당금', order: 2,
          data: buckets.map(b => b.sum),
          backgroundColor: buckets.map(barColor),
          // 막대가 많으면(추정 포함 시 60개 넘음) 1.5px 테두리가 4px 막대를 덮어
          // 오히려 실측처럼 진해 보인다 → 그럴 땐 투명도로만 구분한다.
          borderColor: buckets.map(b => (soft(b) && buckets.length <= 30 ? BAR : 'transparent')),
          borderWidth: buckets.map(b => (soft(b) && buckets.length <= 30 ? 1.5 : 0)),
          borderDash: [4, 3], borderSkipped: false, yAxisID: 'y',
        },
        ...(hasYield ? [{
          type: 'line', label: '배당수익률', order: 1,
          data: buckets.map(b => b.yield),
          borderColor: LINE, backgroundColor: LINE, borderWidth: 2,
          pointRadius: 2.5, tension: 0.25, spanGaps: false, yAxisID: 'y1',
        }] : []),
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterTitle: ctx => {
              const b = buckets[ctx[0].dataIndex];
              if (b.ongoing) return '진행중 — 아직 다 지급되지 않았습니다';
              if (b.partial) return '상장 첫 구간 — 일부 기간만 반영됐습니다';
              if (b.est) return b.nEst === b.n ? '상장 전 추정' : `일부 추정 (${b.nEst}/${b.n}건)`;
              return '';
            },
            label: ctx => (ctx.dataset.yAxisID === 'y1'
              ? `배당수익률 ${ctx.parsed.y.toFixed(2)}%`
              : `주당 배당금 ${fmtDiv(ctx.parsed.y, curr)} (${buckets[ctx.dataIndex].n}회)`),
          },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { size: 10 }, color: MM_AXIS }, grid: { display: false } },
        y: {
          position: 'left', beginAtZero: true,
          ticks: { font: { size: 10 }, color: MM_AXIS, callback: v => fmtDiv(v, curr) },
          grid: { color: MM_CHART_GRID },
        },
        ...(hasYield ? {
          y1: {
            position: 'right', beginAtZero: true,
            ticks: { font: { size: 10 }, color: LINE, callback: v => v.toFixed(1) + '%' },
            grid: { display: false },
          },
        } : {}),
      },
    },
  });
}

function dividendTableHtml(dividends, currency) {
  const list = dividends || [];
  if (!list.length) return '<div style="color:var(--text-muted);font-size:0.85rem;padding:8px;">배당 데이터 없음</div>';
  const hiddenCount = Math.max(0, list.length - DIV_INITIAL_ROWS);
  return `
    <table class="div-table">
      <thead><tr><th>배당일</th><th>주당 배당금</th></tr></thead>
      <tbody id="dividendRows">${dividendRowsHtml(list, currency, false)}</tbody>
    </table>
    ${hiddenCount ? `<button class="div-more-btn" id="divMoreBtn" type="button" data-expanded="false" onclick="toggleDividendHistory()">더보기 (${hiddenCount}개)</button>` : ''}
  `;
}

function toggleDividendHistory() {
  const btn = document.getElementById('divMoreBtn');
  const rows = document.getElementById('dividendRows');
  if (!btn || !rows || !allData) return;
  const nextExpanded = btn.dataset.expanded !== 'true';
  rows.innerHTML = dividendRowsHtml(allData.dividends || [], allData.currency, nextExpanded);
  btn.dataset.expanded = nextExpanded ? 'true' : 'false';
  const hiddenCount = Math.max(0, (allData.dividends || []).length - DIV_INITIAL_ROWS);
  btn.textContent = nextExpanded ? '접기' : `더보기 (${hiddenCount}개)`;
}

let chartInst    = null;   // Chart.js (라인)
let holdingsChart = null;  // Chart.js (ETF 구성종목 파이)
let candleChart  = null;   // Lightweight Charts (캔들)
let candleSeries = null;
let allData        = null;
let curType        = 'line';   // 'line' | 'candle'
let lineRange      = '1M';     // 라인 탭 = 표시 기간
let candleInterval = '1D';     // 캔들 탭 = 캔들 1개의 간격 (기간은 항상 전체)

async function loadSymbol() {
  let res, data;
  try {
    res  = await fetch(`/api/symbol/${CODE}`);
    data = await res.json();
  } catch (e) {
    document.getElementById('symbolContent').innerHTML =
      '<div class="symbol-empty">일시적으로 불러오지 못했어요. 잠시 후 새로고침 해주세요.</div>';
    return;
  }
  if (data.error) {
    document.getElementById('symbolContent').innerHTML =
      `<div class="symbol-empty">종목을 찾을 수 없습니다: ${CODE}</div>`;
    return;
  }
  allData = data;
  renderPage(data);
}

function renderPage(data) {
  const cur    = data.current_price;
  const prev   = data.prev_price;
  const chg    = prev ? cur - prev : 0;
  const chgPct = prev ? (chg / prev * 100) : 0;
  const isUp   = chg >= 0;
  const curr   = data.currency;
  const at       = data.asset_type || (data.is_index ? 'INDEX' : (data.country === 'KR' ? 'KR_ETF' : 'US_ETF'));
  const isKR     = data.country === 'KR';
  const isCrypto = at === 'CRYPTO';
  const isIndex  = at === 'INDEX';
  const isStock  = at === 'KR_STOCK' || at === 'US_STOCK';
  const isETF    = at === 'KR_ETF'   || at === 'US_ETF';
  const BADGE = { INDEX:'지수/선물', CRYPTO:'CRYPTO',
                  KR_STOCK:'KR 주식', US_STOCK:'US 주식',
                  KR_ETF:'KR ETF',   US_ETF:'US ETF' };
  const badgeLabel = BADGE[at] || at;
  const badgeClass = isIndex  ? ''
                   : isCrypto ? 'crypto'
                   : isKR     ? 'kr' : '';

  // 지표 그리드 — 자산 타입별 분기 (A4-b)
  const statItems = [
    `<div class="stat-item"><div class="stat-label">52주 최고</div><div class="stat-value">${fmtPrice(data.high_52w, curr)}</div></div>`,
    `<div class="stat-item"><div class="stat-label">52주 최저</div><div class="stat-value">${fmtPrice(data.low_52w, curr)}</div></div>`,
  ];
  if (!isCrypto && !isIndex) {
    statItems.push(`<div class="stat-item"><div class="stat-label">배당수익률</div><div class="stat-value">${data.div_yield ? data.div_yield.toFixed(2) + '%' : '—'}</div></div>`);
  }
  if (isStock) {
    statItems.push(`<div class="stat-item"><div class="stat-label">시가총액</div><div class="stat-value">${fmtMcap(data.market_cap, curr)}</div></div>`);
    statItems.push(`<div class="stat-item"><div class="stat-label">PER</div><div class="stat-value">${data.per ? data.per.toFixed(1) : '—'}</div></div>`);
    statItems.push(`<div class="stat-item"><div class="stat-label">PBR</div><div class="stat-value">${data.pbr ? data.pbr.toFixed(2) : '—'}</div></div>`);
    statItems.push(`<div class="stat-item" style="grid-column:1/-1;"><div class="stat-label">섹터</div><div class="stat-value" style="font-size:0.82rem;">${data.sector || '—'}</div></div>`);
  } else if (isETF) {
    statItems.push(`<div class="stat-item"><div class="stat-label">운용사</div><div class="stat-value" style="font-size:0.82rem;">${data.issuer || '—'}</div></div>`);
    statItems.push(`<div class="stat-item"><div class="stat-label">보수율</div><div class="stat-value">${data.expense_ratio ? (data.expense_ratio * 100).toFixed(2) + '%' : '—'}</div></div>`);
    statItems.push(`<div class="stat-item" style="grid-column:1/-1;"><div class="stat-label">카테고리</div><div class="stat-value" style="font-size:0.82rem;">${data.category || '—'}</div></div>`);
    if (data.aum) statItems.push(`<div class="stat-item" style="grid-column:1/-1;"><div class="stat-label">AUM</div><div class="stat-value">$${(data.aum / 1e9).toFixed(1)}B</div></div>`);
  } else if (isCrypto && data.market_cap) {
    statItems.push(`<div class="stat-item" style="grid-column:1/-1;"><div class="stat-label">시가총액</div><div class="stat-value">${fmtMcap(data.market_cap, curr)}</div></div>`);
  }

  document.getElementById('symbolContent').innerHTML = `
    <!-- 상단 헤더 (full width) -->
    <div class="symbol-header">
      <div class="symbol-header-left">
        <span class="symbol-badge ${badgeClass}">${badgeLabel}</span>
        <div>
          <div class="symbol-name">${escHtml(data.name)}</div>
          <div class="symbol-code">${data.code}</div>
        </div>
        ${window.MM_LOGGED_IN ? `<button class="mm-alert-btn" style="margin-left:6px;" onclick="mmAlert.openSymbol('${data.code}','${(data.name||'').replace(/'/g, "\\'")}')">🔔 알림</button>` : ''}
      </div>
      <div class="symbol-header-right">
        <div class="symbol-price">${fmtPrice(cur, curr)}</div>
        <div class="symbol-change ${isUp ? 'up' : 'down'}">
          ${isUp ? '▲' : '▼'} ${fmtPrice(Math.abs(chg), curr)} (${Math.abs(chgPct).toFixed(2)}%)
        </div>
        <div class="symbol-date">${data.last_date} 기준</div>
      </div>
    </div>

    <!-- 2열 본문 -->
    <div class="symbol-body">
      <!-- 왼쪽: 차트 -->
      <div class="symbol-left-col">
        <div class="symbol-card chart-card" id="chartCard">
          <div class="chart-card-head">
            <div class="symbol-card-title">📈 가격 차트</div>
            <div style="display:flex; gap:8px; align-items:center;">
              <div class="chart-type-toggle" id="chartTypeToggle">
                <button class="ctype-btn active" data-ctype="line">라인</button>
                <button class="ctype-btn" data-ctype="candle">캔들</button>
              </div>
              <button class="fs-btn" id="fsBtn" title="전체화면">⛶</button>
            </div>
          </div>
          <div class="period-tabs" id="periodTabs"></div>
          <div class="chart-hint" id="chartHint"></div>
          <div class="chart-canvas-wrap">
            <canvas id="priceChart"></canvas>
            <div id="candleChart" style="position:absolute; inset:0; display:none;"></div>
          </div>
        </div>

        ${isETF ? `
        <div class="symbol-card holdings-card">
          <div class="symbol-card-title">🧩 구성종목</div>
          ${validHoldings(data.holdings).length ? `
          <div class="holding-pie-wrap">
            <canvas id="holdingsPieChart"></canvas>
          </div>
          <div class="holding-list">
            ${validHoldings(data.holdings).map(h => `
              <div class="holding-row">
                <span class="holding-rank">#${h.rank}</span>
                <span class="holding-code">${escHtml(h.code || '-')}</span>
                <span class="holding-name" title="${escHtml(h.name || '')}">${escHtml(h.name || '')}</span>
                <span class="holding-weight">${fmtWeight(h.weight_pct)}</span>
              </div>
            `).join('')}
          </div>
          <div class="holding-source">${escHtml(data.holdings[0].source || 'Yahoo Finance')} 기준 · 상위 보유종목</div>` :
          '<div style="color:var(--text-muted);font-size:0.85rem;padding:8px;">구성종목 데이터 없음</div>'}
        </div>` : ''}
      </div>

      <!-- 오른쪽: 지표 + 배당 -->
      <div class="symbol-right-col">
        <div class="symbol-card">
          <div class="symbol-card-title">📊 핵심 지표</div>
          <div class="stats-grid">${statItems.join('')}</div>
        </div>

        ${(isStock || isETF) ? `
        <div class="symbol-card">
          <div class="symbol-card-title">💰 배당 내역</div>
          ${dividendChartHtml(data.dividends)}
          ${dividendTableHtml(data.dividends, curr)}
        </div>` : ''}
      </div>
    </div>
  `;

  renderTabs();
  renderHoldingsPie(data);
  renderDividendChart();
  renderActive();
}

// ── 차트 엔진 ────────────────────────────────────────────
// 라인 = 표시 기간(시간봉/일봉). 캔들 = 캔들 1개의 간격, 기간은 항상 전체.
function renderHoldingsPie(data) {
  if (holdingsChart) {
    holdingsChart.destroy();
    holdingsChart = null;
  }
  const canvas = document.getElementById('holdingsPieChart');
  if (!canvas) return;

  const holdings = validHoldings(data.holdings);
  if (!holdings.length) return;

  const slices = holdings.map(h => ({
    code: h.code,
    name: h.name || h.code,
    weight: h.weight_pct
  }));
  const total = slices.reduce((sum, h) => sum + h.weight, 0);
  if (total > 0 && total < 99) {
    slices.push({ code: '기타', name: '기타 보유종목', weight: 100 - total });
  }

  const colors = [
    '#1976D2', '#2E7D32', '#F57C00', '#7B1FA2', '#00838F',
    '#C62828', '#5D6D7E', '#AFB42B', '#6D4C41', '#AD1457',
    '#90A4AE'
  ];
  holdingsChart = new Chart(canvas.getContext('2d'), {
    type: 'pie',
    data: {
      labels: slices.map(h => h.code),
      datasets: [{
        data: slices.map(h => h.weight),
        backgroundColor: slices.map((_, i) => colors[i % colors.length]),
        borderColor: (typeof MM_DARK !== 'undefined' && MM_DARK) ? '#18202B' : '#FFFFFF',
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: { color: MM_AXIS, boxWidth: 12, padding: 12, font: { size: 11 } }
        },
        tooltip: {
          callbacks: {
            label: ctx => {
              const h = slices[ctx.dataIndex];
              return `${h.code} · ${h.name}: ${fmtWeight(h.weight)}`;
            }
          }
        }
      }
    }
  });
}

const MM_AXIS = (typeof MM_DARK !== 'undefined' && MM_DARK) ? '#8FA3B8' : '#90A4AE';
const intradayCache = {};   // {'1d':resp,'1w':resp,'max':resp}

const LINE_TABS   = [['1D','1일'],['1W','1주'],['1M','1개월'],['3M','3개월'],['1Y','1년'],['ALL','전체']];
const CANDLE_TABS = [['1H','1시간'],['1D','1일'],['1W','1주'],['1M','1개월'],['1Y','1년']];

function renderTabs() {
  const tabs   = curType === 'candle' ? CANDLE_TABS : LINE_TABS;
  const active = curType === 'candle' ? candleInterval : lineRange;
  document.getElementById('periodTabs').innerHTML = tabs.map(([v, l]) =>
    `<button class="period-tab${v === active ? ' active' : ''}" data-period="${v}">${l}</button>`
  ).join('');
}

document.addEventListener('click', e => {
  const ptab = e.target.closest('.period-tab');
  if (ptab) {
    if (curType === 'candle') candleInterval = ptab.dataset.period;
    else                      lineRange      = ptab.dataset.period;
    document.querySelectorAll('.period-tab').forEach(b => b.classList.remove('active'));
    ptab.classList.add('active');
    renderActive();
    return;
  }
  const ctype = e.target.closest('.ctype-btn');
  if (ctype && !ctype.classList.contains('disabled')) {
    curType = ctype.dataset.ctype;
    document.querySelectorAll('.ctype-btn').forEach(b => b.classList.remove('active'));
    ctype.classList.add('active');
    renderTabs();      // 모드별 탭 세트 교체
    renderActive();
    return;
  }
  if (e.target.closest('#fsBtn')) {
    const card = document.getElementById('chartCard');
    if (!document.fullscreenElement) card.requestFullscreen && card.requestFullscreen();
    else document.exitFullscreen && document.exitFullscreen();
  }
});

// 시간봉 API fetch + 캐시
async function fetchIntraday(rng) {
  if (!intradayCache[rng]) {
    const r = await fetch(`/api/symbol/${CODE}/intraday?range=${rng}`);
    intradayCache[rng] = await r.json();
  }
  return (intradayCache[rng] || {}).prices || [];
}

// 일봉 → 주/월/년 OHLC 리샘플 (open=첫 open, high=max, low=min, close=끝 close)
function bucketKey(dateStr, unit) {
  if (unit === 'M') return dateStr.slice(0, 7);   // YYYY-MM
  if (unit === 'Y') return dateStr.slice(0, 4);   // YYYY
  // W: 연도 + 주차
  const d = new Date(dateStr);
  const onejan = new Date(d.getFullYear(), 0, 1);
  const week = Math.ceil((((d - onejan) / 86400000) + onejan.getDay() + 1) / 7);
  return d.getFullYear() + '-W' + week;
}
function resampleOHLC(prices, unit) {
  const out = []; let key = null, cur = null;
  for (const p of prices) {
    if (p.open == null) continue;
    const k = bucketKey(p.date, unit);
    if (k !== key) {
      if (cur) out.push(cur);
      key = k;
      cur = { date: p.date, open: p.open, high: p.high, low: p.low, close: p.close, volume: p.volume || 0 };
    } else {
      cur.high = Math.max(cur.high, p.high);
      cur.low  = Math.min(cur.low,  p.low);
      cur.close = p.close;
      cur.volume += (p.volume || 0);
    }
  }
  if (cur) out.push(cur);
  return out;
}

// 간격별 기본 보이는 창(일 단위). 데이터는 전체 로드 — 초기 줌만. 0 = 전체(fitContent).
const CANDLE_DEFAULT_DAYS = { '1H': 2, '1D': 75, '1W': 365, '1M': 2555, '1Y': 0 };

// 라인: 표시 기간만큼 잘라 반환
async function getLineData(range) {
  if (range === '1D' || range === '1W') {
    return { prices: await fetchIntraday(range === '1D' ? '1d' : '1w'), intraday: true };
  }
  const all = allData.prices || [];
  if (!all.length) return { prices: [], intraday: false };
  const cutoff = new Date(all[all.length - 1].date);
  if      (range === '1M') cutoff.setMonth(cutoff.getMonth() - 1);
  else if (range === '3M') cutoff.setMonth(cutoff.getMonth() - 3);
  else if (range === '1Y') cutoff.setFullYear(cutoff.getFullYear() - 1);
  else                      cutoff.setFullYear(1900);
  return { prices: all.filter(p => new Date(p.date) >= cutoff), intraday: false };
}

// 캔들: 항상 전체 기간, 간격만 다름
async function getCandleData(interval) {
  if (interval === '1H') {
    return { prices: await fetchIntraday('max'), intraday: true };
  }
  const all = allData.prices || [];
  if (interval === '1D') return { prices: all, intraday: false };
  const unit = interval === '1W' ? 'W' : interval === '1M' ? 'M' : 'Y';
  return { prices: resampleOHLC(all, unit), intraday: false };
}

function setHint(text) { document.getElementById('chartHint').textContent = text || ''; }

async function renderActive() {
  // 캔들 가용성 = 일봉에 OHLC 있는지(KRX_GOLD 등 close-only는 캔들 불가)
  const dailyHasOHLC = (allData.prices || []).length > 0 && allData.prices[0].open != null;
  const candleBtn = document.querySelector('.ctype-btn[data-ctype="candle"]');
  if (candleBtn) candleBtn.classList.toggle('disabled', !dailyHasOHLC);
  if (curType === 'candle' && !dailyHasOHLC) {   // 강제 라인 복귀
    curType = 'line';
    document.querySelectorAll('.ctype-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.ctype === 'line'));
    renderTabs();
  }

  const canvas = document.getElementById('priceChart');
  const cdiv   = document.getElementById('candleChart');

  if (curType === 'candle') {
    const { prices, intraday } = await getCandleData(candleInterval);
    const labelMap = { '1H':'1시간', '1D':'1일', '1W':'1주', '1M':'1개월', '1Y':'1년' };
    if (candleInterval === '1H') {
      setHint(`⚠ 캔들 1개 = 1시간 · 시간봉은 데이터 제공 한계로 최근 약 730일(2년)까지만 표시됩니다. (스크롤·줌으로 범위 조정)`);
    } else {
      setHint(`캔들 1개 = ${labelMap[candleInterval]} · 전체 기간 데이터 (기본 화면 외 구간은 스크롤·줌으로 확인)`);
    }
    canvas.style.display = 'none'; cdiv.style.display = 'block';
    renderCandle(prices, intraday, candleInterval);
  } else {
    const { prices, intraday } = await getLineData(lineRange);
    setHint(intraday ? (lineRange === '1D' ? '최근 1일(시간봉)' : '최근 1주(시간봉)') : '');
    cdiv.style.display = 'none'; canvas.style.display = 'block';
    if (candleChart) { candleChart.remove(); candleChart = null; candleSeries = null; }
    renderLine(prices, intraday);
  }
}

function renderLine(prices, intraday) {
  if (chartInst) chartInst.destroy();
  if (!prices || !prices.length) return;
  const labels = prices.map(p => p.date);
  const vals   = prices.map(p => p.close);
  const isUp   = vals.length > 1 && vals[vals.length - 1] >= vals[0];
  const color  = isUp ? '#2E7D32' : '#C62828';
  const fill   = isUp ? 'rgba(46,125,50,0.08)' : 'rgba(198,40,40,0.08)';

  const ctx = document.getElementById('priceChart').getContext('2d');
  chartInst = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets: [{
      data: vals, borderColor: color, borderWidth: 2,
      backgroundColor: fill, fill: true, pointRadius: 0, tension: 0.3,
    }]},
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: {
        callbacks: { label: ctx => fmtPrice(ctx.parsed.y, allData.currency) }
      }},
      scales: {
        x: { ticks: { maxTicksLimit: 8, font: { size: 10 }, color: MM_AXIS }, grid: { display: false } },
        y: { ticks: { font: { size: 10 }, color: MM_AXIS }, grid: { color: MM_CHART_GRID } }
      }
    }
  });
}

function renderCandle(prices, intraday, interval) {
  const el = document.getElementById('candleChart');
  if (candleChart) { candleChart.remove(); candleChart = null; candleSeries = null; }
  if (!prices || !prices.length) return;
  candleChart = LightweightCharts.createChart(el, {
    width: el.clientWidth, height: el.clientHeight,
    layout: { background: { color: 'transparent' }, textColor: MM_AXIS },
    grid: { vertLines: { color: MM_CHART_GRID }, horzLines: { color: MM_CHART_GRID } },
    timeScale: { timeVisible: intraday, secondsVisible: false, borderColor: MM_CHART_GRID },
    rightPriceScale: { borderColor: MM_CHART_GRID, scaleMargins: { top: 0.08, bottom: 0.26 } },
    crosshair: { mode: 0 },
  });
  candleSeries = candleChart.addCandlestickSeries({
    upColor: '#2E7D32', downColor: '#C62828', borderVisible: false,
    wickUpColor: '#2E7D32', wickDownColor: '#C62828',
  });
  const toTime = p => intraday
    ? Math.floor(new Date(p.date.replace(' ', 'T')).getTime() / 1000)
    : p.date;
  candleSeries.setData(prices.map(p => ({
    time: toTime(p), open: p.open, high: p.high, low: p.low, close: p.close,
  })));

  // 거래량 히스토그램 — 하단 26% 영역, 봉 색과 동일(상승=초록/하락=빨강)
  const volSeries = candleChart.addHistogramSeries({
    priceScaleId: 'vol', priceFormat: { type: 'volume' },
  });
  candleChart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
  volSeries.setData(prices.map(p => ({
    time: toTime(p), value: p.volume || 0,
    color: (p.close >= p.open) ? 'rgba(46,125,50,0.45)' : 'rgba(198,40,40,0.45)',
  })));

  // 간격별 기본 배율 — 전체 데이터 유지, 초기 보이는 창만 제한
  const days = CANDLE_DEFAULT_DAYS[interval] || 0;
  const ts = candleChart.timeScale();
  if (days > 0 && prices.length > 1) {
    const last  = prices[prices.length - 1];
    const lastT = toTime(last);
    const fromT = intraday
      ? lastT - days * 86400
      : (() => { const d = new Date(last.date); d.setDate(d.getDate() - days);
                 return d.toISOString().slice(0, 10); })();
    try { ts.setVisibleRange({ from: fromT, to: lastT }); }
    catch (e) { ts.fitContent(); }
  } else {
    ts.fitContent();
  }
}

function resizeCharts() {
  if (candleChart) {
    const el = document.getElementById('candleChart');
    candleChart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
    candleChart.timeScale().fitContent();
  }
  if (chartInst) chartInst.resize();
  if (holdingsChart) holdingsChart.resize();
}
window.addEventListener('resize', resizeCharts);
document.addEventListener('fullscreenchange', () => setTimeout(resizeCharts, 120));

loadSymbol();
