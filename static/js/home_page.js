// index.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 데이터는 #page-data JSON
  (function () {
    var root = document.getElementById('homeCarousel');
    if (!root) return;
    var track = document.getElementById('hcTrack');
    var dots = [].slice.call(root.querySelectorAll('.hc-dot'));
    var n = track.children.length, i = 0, timer = null, paused = false;
    function go(k) {
      i = (k + n) % n;
      track.style.transform = 'translateX(-' + (i * 100) + '%)';
      dots.forEach(function (d, j) { d.classList.toggle('on', j === i); });
    }
    function start() { stop(); if (!paused) timer = setInterval(function () { go(i + 1); }, 7000); }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    document.getElementById('hcNext').addEventListener('click', function () { go(i + 1); start(); });
    dots.forEach(function (d) { d.addEventListener('click', function () { go(+d.dataset.i); start(); }); });
    var pb = document.getElementById('hcPause');
    pb.addEventListener('click', function () {
      paused = !paused;
      pb.textContent = paused ? '▶' : '⏸';
      pb.setAttribute('aria-label', paused ? '자동 전환 재생' : '자동 전환 일시정지');
      if (paused) stop(); else start();
    });
    root.addEventListener('mouseenter', stop);
    root.addEventListener('mouseleave', function () { if (!paused) start(); });
    start();
  })();
  

document.addEventListener('DOMContentLoaded', () => {
  if (window.MM_LOGGED_IN) { loadPortfolio(); loadActions(); }
  else { drawDemoChart('demoChart'); drawDemoChart('demoSpark'); }
  loadWidgets();
  setInterval(loadWidgets, 5 * 60 * 1000);
  let _wrt;
  window.addEventListener('resize', () => { clearTimeout(_wrt); _wrt = setTimeout(renderWidgets, 200); });
  if (window.MM_LOGGED_IN) setInterval(() => {
    loadPortfolio(_homePortfolioPeriod);
    loadActions();
  }, 60 * 1000);

  document.querySelectorAll('#portfolioCard .period-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#portfolioCard .period-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderPortfolio(btn.dataset.period);
    });
  });
});

// ── 포트폴리오 차트 ──
let portfolioChart = null;
let _portfolioData = null;
let _homeHideAmounts = true;
let _homePeek = false;   // 로컬 금액 보기 (개인 가림설정 임시 해제, 저장 안 함)
let _homePortfolioPeriod = '1m';

function togglePeek() {
  _homePeek = !_homePeek;
  const b = document.getElementById('peekBtn');
  if (b) b.textContent = _homePeek ? '🙈' : '👁';
  renderPortfolio(_homePortfolioPeriod);
  loadActions();
}

// ── SVG 아이콘(사다리·고급 라인) ──
const _S = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"';
const ICON = {
  coins: `<svg class="ic" ${_S}><ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/></svg>`,
  scale: `<svg class="ic" ${_S}><path d="M12 3v18"/><path d="M7 21h10"/><path d="M5 7h14"/><path d="M5 7 2.5 13a3 3 0 0 0 5 0z"/><path d="M19 7l-2.5 6a3 3 0 0 0 5 0z"/></svg>`,
  target: `<svg class="ic" ${_S}><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/></svg>`,
};

// ── 비로그인 데모 그래프 (예시 데이터 하드코딩, SPY60·TLT40 우상향) ──
function drawDemoChart(canvasId = 'demoChart') {
  const el = document.getElementById(canvasId);
  if (!el || typeof Chart === 'undefined') return;
  const vals = [11.92, 11.88, 12.05, 12.21, 12.10, 12.34, 12.52, 12.41, 12.66, 12.83,
                12.74, 12.95, 13.08, 12.97, 13.18, 13.05, 13.27, 13.40, 13.31, 13.21, 13.36, 13.43];
  const labels = vals.map((_, i) => i);
  const ctx = el.getContext('2d');
  const brand = getComputedStyle(document.documentElement).getPropertyValue('--brand').trim() || '#0052ff';
  const grad = ctx.createLinearGradient(0, 0, 0, 200);
  grad.addColorStop(0, brand + '2e'); grad.addColorStop(1, brand + '00');
  new Chart(ctx, {
    type: 'line',
    data: { labels, datasets: [{ data: vals, borderColor: brand, borderWidth: 2.5, fill: true,
      backgroundColor: grad, pointRadius: 0, tension: 0.4 }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } } }
  });
}

function fmtMaskedKRW(v) {
  if (_homeHideAmounts) return '***,***,***원';
  return '₩' + Math.round(v || 0).toLocaleString();
}

function setPortfolioChange(id, label, series) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!series || series.length < 2 || !series[0]) {
    el.textContent = '';
    el.style.display = 'none';
    return;
  }
  const pct = (series[series.length - 1] - series[0]) / series[0] * 100;
  const sign = pct >= 0 ? '+' : '';
  el.innerHTML = `<span class="lab">${label}</span>${sign}${pct.toFixed(2)}%`;
  el.className = 'portfolio-change ' + (pct >= 0 ? 'up' : 'down');
  el.style.display = '';
}

// 선택 기간 최대 기여 종목 한 줄 (내 자산 '종목별 손익' 요약판)
function renderTopMover(n, label, data) {
  const el = document.getElementById('pfTopMover');
  if (!el) return;
  let best = null;
  if (data.series) {
    for (const [code, arr] of Object.entries(data.series)) {
      const nn = arr.slice(-n).filter(v => v != null && v > 0);
      if (nn.length < 2) continue;
      const diff = nn[nn.length - 1] - nn[0];
      if (!best || Math.abs(diff) > Math.abs(best.diff)) best = { code, diff, pct: diff / nn[0] };
    }
  }
  if (!best) { el.style.display = 'none'; return; }
  const name = (data.names && data.names[best.code]) || best.code;
  const cls = best.diff >= 0 ? 'up' : 'down';
  const amt = _homeHideAmounts
    ? (best.pct >= 0 ? '+' : '') + (best.pct * 100).toFixed(1) + '%'
    : (best.diff >= 0 ? '+' : '-') + '₩' + Math.abs(Math.round(best.diff)).toLocaleString();
  const esc = window.mmEsc || (s => s);
  el.innerHTML = `${best.diff >= 0 ? '↑' : '↓'} 최근 ${label} 최대 기여: <b>${esc(name)}</b> <span class="amt ${cls}">${amt}</span>`;
  el.style.display = '';
}

function fmtChartKRW(v) {
  if (!Number.isFinite(v)) return '';
  const sign = v < 0 ? '-' : '';
  const n = Math.abs(v);
  const trim = x => (Math.round(x * 10) / 10).toString();
  if (n >= 1e8) return sign + trim(n / 1e8) + '억';
  return sign + Math.round(n / 1e4) + '만';
}

async function loadPortfolio(period = '1m') {
  try {
    const res = await fetch('/api/portfolio/history', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    _portfolioData = await res.json();
    renderPortfolio(period);
  } catch (e) {
    // 네트워크/서버 실패 — 빈 카드 방치 대신 숨김(아래 온보딩/다른 카드가 안내)
    const card = document.getElementById('portfolioCard');
    if (card) card.style.display = 'none';
  }
}

function renderPortfolio(period = '1m') {
  _homePortfolioPeriod = period;
  const data = _portfolioData;
  if (!data) return;
  _homeHideAmounts = data.hide_amounts !== false;
  if (_homePeek) _homeHideAmounts = false;
  const peekBtn = document.getElementById('peekBtn');
  if (peekBtn) peekBtn.style.display = (data.hide_amounts !== false) ? '' : 'none';

  const card = document.getElementById('portfolioCard');
  if (data.empty) {
    // 포트폴리오 없음 = 카드 숨기고 아래 온보딩이 안내(중복·빈차트 제거)
    if (card) card.style.display = 'none';
    return;
  }
  if (card) card.style.display = '';

  const { labels, values } = data;
  const slices = { '1w': 7, '1m': 22, '1y': 252 };
  const periodLabels = { '1w': '1주', '1m': '1개월', '1y': '1년' };
  const n = slices[period] || 7;
  const slicedLabels = labels.slice(-n);
  const slicedValues = values.slice(-n);

  const valEl = document.getElementById('portfolioValue');
  valEl.classList.remove('mm-skel', 'mm-skel-val');   // 로딩 스켈레톤 해제
  valEl.textContent = fmtMaskedKRW(data.current || values[values.length - 1] || 0);
  setPortfolioChange('portfolioDailyChange', '1일', values.slice(-2));
  setPortfolioChange('portfolioPeriodChange', periodLabels[period] || '1주', slicedValues);
  renderTopMover(n, periodLabels[period] || '1주', data);

  const canvas = document.getElementById('portfolioChart');
  const ctx = canvas.getContext('2d');
  const _brand = getComputedStyle(document.documentElement).getPropertyValue('--brand').trim() || '#0052ff';
  const grad = ctx.createLinearGradient(0, 0, 0, 200);
  grad.addColorStop(0, _brand + '2e');
  grad.addColorStop(1, _brand + '00');

  if (portfolioChart) portfolioChart.destroy();
  portfolioChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: slicedLabels,
      datasets: [{
        data: slicedValues,
        borderColor: _brand,
        borderWidth: 2.5,
        fill: true,
        backgroundColor: grad,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: _brand,
        tension: 0.4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => fmtMaskedKRW(c.raw) } }
      },
      scales: {
        x: {
          display: true,
          ticks: { maxTicksLimit: 6, font: { size: 10 }, color: '#90A4AE' },
          grid: { display: false }
        },
        y: {
          display: true,
          ticks: {
            font: { family: 'JetBrains Mono', size: 10 },
            color: '#90A4AE',
            callback: v => _homeHideAmounts ? '***' : fmtChartKRW(v)
          },
          grid: { color: MM_CHART_GRID }
        }
      }
    }
  });
}

async function refreshPortfolioPrices() {
  const btn = document.getElementById('portfolioRefreshBtn');
  if (btn) { btn.disabled = true; btn.classList.add('spinning'); }
  try {
    await loadPortfolio(_homePortfolioPeriod);
    await loadActions();
  } catch (e) {}
  if (btn) setTimeout(() => { btn.classList.remove('spinning'); btn.disabled = false; }, 700);
}

// ── "다음 할 일" 액션 사다리 ──
function _actionRowHtml(r) {
  return `<a class="action-row" href="${r.href}">
    <div class="action-ic ${r.cls || ''}">${r.ic}</div>
    <div class="action-main"><div class="action-t">${r.t}</div><div class="action-s">${r.s}</div></div>
    <span class="action-arrow">›</span></a>`;
}

function _rebalCard(data) {
  const groups = data.groups || [], holdings = data.holdings || [], prices = data.prices || {};
  if (!groups.length) return null;
  const gv = {}; let total = 0;
  holdings.forEach(h => {
    const gid = h.group_id; if (!gid) return;
    const v = (prices[h.code] || 0) * (+h.quantity || 0);
    gv[gid] = (gv[gid] || 0) + v; total += v;
  });
  if (total <= 0) return null;
  const tt = groups.reduce((s, g) => s + (g.target_pct || 0), 0) || 100;
  let worst = null;
  groups.forEach(g => {
    const cur = (gv[g.id] || 0) / total * 100;
    const tgt = (g.target_pct || 0) / tt * 100;
    const d = cur - tgt;
    if (!worst || Math.abs(d) > Math.abs(worst.d)) worst = { name: g.name, d, cur, tgt };
  });
  if (!worst || Math.abs(worst.d) < 5)
    return { ic: ICON.scale, cls: 'ok', t: '자산 배분 균형 잡힘', s: '목표 비중과 ±5%p 이내', href: '/myassets' };
  const sign = worst.d >= 0 ? '+' : '';
  return { ic: ICON.scale, cls: 'warn', t: `리밸런싱 필요 — ${_esc(worst.name)}`,
    s: `목표보다 ${sign}${worst.d.toFixed(0)}%p · 현재 ${worst.cur.toFixed(0)}% / 목표 ${worst.tgt.toFixed(0)}%`, href: '/myassets' };
}

function _divCard(dv, hide) {
  if (!dv || dv.error || !dv.events) return null;
  const now = new Date(), y = dv.current_year || now.getFullYear(), m = now.getMonth() + 1;
  const todayStr = now.toISOString().slice(0, 10);
  const evs = dv.events[y] || dv.events[String(y)] || [];
  let cur = evs.filter(e => e.month === m && e.date >= todayStr), label = '이번 달';
  if (!cur.length) {
    const future = evs.filter(e => e.date >= todayStr).sort((a, b) => a.date < b.date ? -1 : 1);
    if (!future.length) return null;
    const nm = future[0].month;
    cur = future.filter(e => e.month === nm); label = nm + '월';
  }
  if (!cur.length) return null;
  const sum = cur.reduce((s, e) => s + (e.krw_post || 0), 0);
  const amt = hide ? '' : ` ₩${Math.round(sum).toLocaleString()}`;
  return { ic: ICON.coins, cls: '', t: `${label} 배당${amt} 예정`, s: `${cur.length}건 · 세후 기준`, href: '/myassets' };
}

function _renderOnboard() {
  const head = document.getElementById('actionHead');
  const ladder = document.getElementById('actionLadder');
  head.style.display = 'none';
  ladder.className = '';
  ladder.innerHTML = `
      <div class="onboard">
        <h3>내 포트폴리오, 30년 과거로 검증해보세요</h3>
        <p>종목을 담으면 수익률·배당·은퇴까지 한 번에 시뮬레이션해드려요.</p>
        <div class="onboard-cta">
          <a href="/myassets" class="home-btn home-btn-primary">➕ 자산 추가하고 시작</a>
          <a href="/backtest" class="home-btn home-btn-ghost">데모 백테 둘러보기</a>
        </div>
        <div class="onboard-steps"><span>① 종목 추가</span><span class="sep">→</span><span>② 분석 실행</span><span class="sep">→</span><span>③ 목표 추적</span></div>
      </div>`;
}

async function loadActions() {
  const head = document.getElementById('actionHead');
  const ladder = document.getElementById('actionLadder');
  if (!window.MM_LOGGED_IN) { _renderOnboard(); return; }  // 비로그인 = 온보딩(불필요 401 회피)
  let data;
  try {
    // 5xx를 "보유내역 없음"으로 오해하면 자산이 있는 사용자에게 온보딩이 뜬다.
    const res = await fetch('/api/myassets/data', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    data = await res.json();
  } catch (e) { ladder.innerHTML = ''; return; }

  if (data.error || !(data.holdings || []).length) { _renderOnboard(); return; }

  const hide = data.hide_amounts !== false && !_homePeek;
  // D5(F-6 배치1): 배당 API는 콜드 시 10초+ — 기다리지 않고 빠른 행부터 즉시 렌더,
  // 배당 카드는 도착하면 맨 위에 삽입 ("불러오는 중" 장기 노출 제거).
  const rows = [];
  const r = _rebalCard(data); if (r) rows.push(r);
  rows.push({ ic: ICON.target, cls: '', t: '은퇴까지 얼마나 왔을까?', s: '목표 정하고 시뮬레이션 돌려보기', href: '/retirement' });

  head.style.display = '';
  ladder.className = 'action-ladder';
  ladder.innerHTML = rows.map(_actionRowHtml).join('');

  try {
    const dv = await (await fetch('/api/myassets/dividends', { cache: 'no-store' })).json();
    const c = _divCard(dv, hide);
    if (c) { rows.unshift(c); ladder.innerHTML = rows.map(_actionRowHtml).join(''); }
  } catch (e) { /* 배당 실패 무시 — 이미 렌더된 행 유지 */ }
}

// ── 홈 위젯 (시장지수 / 관심목록) ──
let _widgets = [];
let _quoteMap = {};
let _activeWidget = 0;

const _esc = window.mmEsc;  // E-1 공용화: 전역 mmEsc(base.html) 단일 구현 — 로컬 복붙 제거 (2026-07-03)

async function loadWidgets() {
  try {
    const cfg = await (await fetch('/api/home-config', { cache: 'no-store' })).json();
    const _lh = document.getElementById('widgetLoginHint');
    if (_lh) _lh.style.display = cfg.logged_in ? 'none' : 'block';
    _widgets = cfg.widgets || [];
    const codes = [...new Set(_widgets.flatMap(w => (w.items || []).map(i => String(i.code).toUpperCase())))];
    if (codes.length) {
      const qs = await (await fetch('/api/watchlist/quotes?codes=' + encodeURIComponent(codes.join(',')))).json();
      _quoteMap = Object.fromEntries(qs.map(q => [q.code, q]));
    }
    renderWidgets();
  } catch (e) {
    // 실패 시 "불러오는 중..." 영구 방치 금지 — 에러 문구로 교체
    const body = document.getElementById('widgetBody');
    if (body) body.innerHTML = '<div class="market-loading">일시적으로 불러오지 못했어요. 잠시 후 새로고침 해주세요.</div>';
  }
}

function _itemsWithQuote(w) {
  return (w.items || []).map(it => ({ ...it, q: _quoteMap[String(it.code).toUpperCase()] }));
}

// 현재 시세로 새로고침 (서버 공유 캐시 15분 floor — 더 자주 눌러도 같은 값)
async function refreshWidgets() {
  const btn = document.getElementById('widgetRefreshBtn');
  if (btn) { btn.disabled = true; btn.classList.add('spinning'); }
  try { await loadWidgets(); } catch (e) {}
  if (btn) setTimeout(() => { btn.classList.remove('spinning'); btn.disabled = false; }, 700);
}

function renderWidgets() {
  if (!_widgets.length) return;
  const isMobile = window.matchMedia('(max-width: 768px)').matches;
  const tabs = document.getElementById('widgetTabs');
  const body = document.getElementById('widgetBody');
  const dots = document.getElementById('widgetDots');
  const title = document.getElementById('widgetTitle');
  if (_activeWidget >= _widgets.length) _activeWidget = 0;

  if (isMobile) {
    tabs.style.display = 'none';
    _renderMobile(body, dots, title);
  } else {
    dots.innerHTML = '';
    if (_widgets.length > 1) {
      tabs.style.display = '';
      tabs.innerHTML = _widgets.map((w, i) =>
        `<button class="widget-tab ${i === _activeWidget ? 'active' : ''}" data-i="${i}">${_esc(w.name)}</button>`).join('');
      tabs.querySelectorAll('.widget-tab').forEach(b =>
        b.addEventListener('click', () => { _activeWidget = +b.dataset.i; renderWidgets(); }));
    } else {
      tabs.style.display = 'none';
    }
    if (title) title.textContent = _widgets[_activeWidget].name;
    _renderGrid(_itemsWithQuote(_widgets[_activeWidget]), body);
  }
}

// 위젯 항목 클릭 이동: 포트폴리오(PF:<id>) → 상세, 일반 종목 → 종목 상세
function _widgetGo(code) {
  if (String(code).toUpperCase().startsWith('PF:')) {
    location.href = '/myportfolios/' + encodeURIComponent(String(code).split(':')[1]);
  } else {
    location.href = '/symbol/' + encodeURIComponent(code);
  }
}

// PC: 타일 그리드(3열, gap) — 보더 인덱스 계산 제거(홀수 개수 선 엉킴 종결), 이름 말줄임 (D2 개편 2026-07-03)
function _renderGrid(items, body) {
  body.innerHTML = `<div class="market-grid market-grid--tiles">${items.map((it, i) => `
    <div class="market-item market-tile" data-code="${_esc(it.code)}" title="${_esc(it.name)}">
      <div class="market-name">${_esc(it.name)}</div>
      <div class="market-value">${it.q ? _esc(it.q.value) : '—'}</div>
      <div class="market-change ${it.q && it.q.up ? 'up' : 'down'}">${it.q ? (it.q.up ? '▲' : '▼') + ' ' + _esc(it.q.change) : '—'}</div>
      <canvas id="wtspark-${i}" class="sparkline" width="160" height="46"></canvas>
    </div>`).join('')}</div>`;
  body.querySelectorAll('.market-item[data-code]').forEach(el =>
    el.addEventListener('click', () => _widgetGo(el.dataset.code)));
  items.forEach((it, i) => {
    if (it.q && it.q.spark && it.q.spark.length >= 2)
      requestAnimationFrame(() => drawSparkline(`wtspark-${i}`, it.q.spark, it.q.up));
  });
}

function _renderMobile(body, dots, title) {
  // 모든 위젯을 6개씩 페이지로 평탄화 → 스와이프 시퀀스
  const pages = [];
  _widgets.forEach(w => {
    const items = _itemsWithQuote(w);
    for (let i = 0; i < items.length; i += 6) pages.push({ name: w.name, items: items.slice(i, i + 6) });
  });
  if (!pages.length) { body.innerHTML = ''; dots.innerHTML = ''; return; }

  // 모바일 = 리스트 행 (D2 개편 2026-07-03): 빈 칸·선 엉킴 개념 소멸, 이름이 행 폭 사용.
  body.innerHTML = `<div class="widget-carousel" id="widgetCarousel">${pages.map((pg, pi) => `
    <div class="widget-slide"><div class="market-list">${pg.items.map((it, ii) => `
      <div class="market-row" data-code="${_esc(it.code)}" title="${_esc(it.name)}">
        <div class="mr-l">
          <div class="market-name">${_esc(it.name)}</div>
          <div class="mr-code">${String(it.code).toUpperCase().startsWith('PF:') ? '내 포트폴리오' : _esc(it.code)}</div>
        </div>
        <canvas id="msp-${pi}-${ii}" class="mr-spark" width="64" height="26"></canvas>
        <div class="mr-r">
          <div class="market-value">${it.q ? _esc(it.q.value) : '—'}</div>
          <div class="market-change ${it.q && it.q.up ? 'up' : 'down'}">${it.q ? (it.q.up ? '▲' : '▼') + ' ' + _esc(it.q.change) : '—'}</div>
        </div>
      </div>`).join('')}</div></div>`).join('')}</div>`;

  dots.innerHTML = pages.map((_, i) => `<span class="wdot ${i === 0 ? 'active' : ''}"></span>`).join('');
  if (title) title.textContent = pages[0].name;

  pages.forEach((pg, pi) => pg.items.forEach((it, ii) => {
    if (it.q && it.q.spark && it.q.spark.length >= 2)
      requestAnimationFrame(() => drawSparkline(`msp-${pi}-${ii}`, it.q.spark, it.q.up));
  }));

  const car = document.getElementById('widgetCarousel');
  car.addEventListener('scroll', () => {
    const idx = Math.round(car.scrollLeft / car.clientWidth);
    dots.querySelectorAll('.wdot').forEach((d, i) => d.classList.toggle('active', i === idx));
    if (title && pages[idx]) title.textContent = pages[idx].name;
  }, { passive: true });

  body.querySelectorAll('.market-row[data-code]').forEach(el =>
    el.addEventListener('click', () => _widgetGo(el.dataset.code)));
}
