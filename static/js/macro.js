// 거시경제 지표 탭 (/macro)
(function () {
  let DATA = null;
  let VIEW = 'US';
  let detailChart = null, cmpChart = null, custChart = null;
  const PALETTE = ['#1976D2', '#E65100', '#2E7D32', '#7B1FA2', '#C2185B', '#00838F'];
  let custom = [];          // [{key,label,color}]

  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  function dnum(d) { const [y, m, day] = d.split('-').map(Number); return y + (m - 1) / 12 + (day - 1) / 365; }
  function fracToDate(f) { const y = Math.floor(f); const m = Math.min(12, Math.round((f - y) * 12) + 1); return `${y}-${String(m).padStart(2, '0')}`; }

  function fmtVal(v, unit) {
    if (v == null) return '–';
    if (unit === '%' || unit === '%p') return v.toFixed(2);
    if (Math.abs(v) >= 1000) return Math.round(v).toLocaleString();
    if (Math.abs(v) >= 10) return v.toFixed(1);
    return v.toFixed(2);
  }

  function sparkSVG(arr) {
    if (!arr || arr.length < 2) return '';
    const w = 150, h = 30, pad = 2, mn = Math.min(...arr), mx = Math.max(...arr), rng = (mx - mn) || 1;
    const pts = arr.map((v, i) => `${(pad + (i / (arr.length - 1)) * (w - 2 * pad)).toFixed(1)},${(h - pad - ((v - mn) / rng) * (h - 2 * pad)).toFixed(1)}`).join(' ');
    const col = arr[arr.length - 1] >= arr[0] ? '#2E7D32' : '#C62828';
    return `<svg class="mc-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${pts}" style="stroke:${col}"></polyline></svg>`;
  }

  function cardHTML(s) {
    let chgCls = 'flat', chgTxt = '–';
    if (s.change != null) {
      const up = s.change > 0, dn = s.change < 0;
      chgCls = up ? 'up' : dn ? 'down' : 'flat';
      const cp = (s.change_pct != null) ? ` (${s.change_pct > 0 ? '+' : ''}${s.change_pct.toFixed(2)}%)` : '';
      chgTxt = `${up ? '▲' : dn ? '▼' : '–'} ${fmtVal(Math.abs(s.change), s.unit)}${cp}`;
    }
    const flag = s.country === 'US' ? '🇺🇸' : '🇰🇷';
    return `<div class="mc-card" data-code="${s.code}" data-name="${s.name_ko}">
      <div class="flag">${flag} ${s.freq}</div>
      <div class="nm">${s.name_ko}</div>
      <div class="val">${fmtVal(s.last_val, s.unit)}<span class="unit">${s.unit}</span></div>
      <div class="chg ${chgCls}">${chgTxt}</div>
      ${sparkSVG(s.spark)}
      <div class="mc-date">${s.last_date} 기준</div></div>`;
  }

  function renderCountry(country, filter) {
    const f = (filter || '').trim().toLowerCase();
    const cats = DATA.categories
      .map(c => ({ category: c.category, series: c.series.filter(s => s.country === country && (!f || s.name_ko.toLowerCase().includes(f))) }))
      .filter(c => c.series.length);
    let html = cats.map(c => `<div class="mc-cat"><div class="mc-cat-head"><span class="dot"></span>${c.category}</div>
        <div class="mc-grid">${c.series.map(cardHTML).join('')}</div></div>`).join('');
    if (!html) html = `<div class="mc-nores">검색 결과 없음${f ? ` ("${filter}")` : ''}</div>`;
    $('mcBody').innerHTML = html;
    $('mcBody').querySelectorAll('.mc-card').forEach(el => el.addEventListener('click', () => openDetail(el.dataset.code)));
  }

  // ── 한·미 비교(고정 쌍) ──
  function renderCompare() {
    const pairs = DATA.compare_pairs;
    $('mcBody').innerHTML = `<div class="mc-cmp-pairs" id="mcCmpPairs">` +
      pairs.map((p, i) => `<button data-i="${i}" class="${i === 0 ? 'on' : ''}">${p.label}</button>`).join('') +
      `</div><div class="mc-cmp-card"><div class="mc-cmp-mode" id="mcCmpMode"></div>
       <div class="mc-chart-wrap"><canvas id="mcCmpChart"></canvas></div></div>`;
    $('mcCmpPairs').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
      $('mcCmpPairs').querySelectorAll('button').forEach(x => x.classList.remove('on'));
      b.classList.add('on'); loadCompare(pairs[+b.dataset.i]);
    }));
    if (pairs.length) loadCompare(pairs[0]);
  }
  async function loadCompare(pair) {
    $('mcCmpMode').textContent = '불러오는 중…';
    const d = await (await fetch(`/api/macro/compare?us=${pair.us}&kr=${pair.kr}`)).json();
    if (d.error) { $('mcCmpMode').textContent = '데이터 없음'; return; }
    $('mcCmpMode').textContent = d.mode === 'raw' ? `같은 단위(${d.unit}) — 원값 직접 비교` : `단위가 달라 시작점=100으로 정규화 — 추세 비교`;
    cmpChart = drawLine('mcCmpChart', cmpChart, [
      lineDS(`🇺🇸 ${d.a.name_ko}`, d.a.points, '#1976D2'),
      lineDS(`🇰🇷 ${d.b.name_ko}`, d.b.points, '#E65100')], d.unit);
  }

  // ── 커스텀 겹쳐보기 ──
  function renderCustom() {
    $('mcBody').innerHTML = `
      <div class="mc-cust-intro">단위가 달라도 여러 지표·종목을 겹쳐 <b>추세(경향성)</b>를 비교합니다. 기본은 공통 시작점=100 정규화. 최대 6개.</div>
      <div class="mc-cust-search">
        <input type="text" id="mcCustInput" placeholder="🔍 지표·종목 추가 (예: M2, 환율, 국고채, AAPL)…" autocomplete="off">
        <div class="mc-dd" id="mcCustDD"></div>
      </div>
      <div class="mc-chips" id="mcChips"></div>
      <div class="mc-cust-opt" id="mcCustOpt"></div>
      <div class="mc-cmp-card"><div class="mc-chart-wrap"><canvas id="mcCustChart"></canvas></div></div>`;
    const inp = $('mcCustInput'), dd = $('mcCustDD');
    let t = null;
    inp.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => custSearch(inp.value), 220); });
    inp.addEventListener('focus', () => { if (inp.value.trim()) custSearch(inp.value); });
    document.addEventListener('click', (e) => { if (!dd.contains(e.target) && e.target !== inp) dd.classList.remove('open'); });
    renderChips();
    if (!custom.length) {  // 기본 예시 2종
      addCustom('KR_M2', '한국 M2(평잔, 계절조정)'); addCustom('KR_USDKRW', '원/달러 매매기준율');
    } else { loadCustomChart(); }
  }

  async function custSearch(q) {
    q = q.trim(); const dd = $('mcCustDD');
    if (!q) { dd.classList.remove('open'); return; }
    const ql = q.toLowerCase();
    const macros = [];
    for (const c of DATA.categories) for (const s of c.series)
      if (s.name_ko.toLowerCase().includes(ql)) macros.push(s);
    let html = '';
    if (macros.length) html += `<div class="mc-dd-grouphdr">거시지표</div>` +
      macros.slice(0, 12).map(s => `<div class="mc-dd-item" data-k="${s.code}" data-l="${s.name_ko}">
        <span>${s.country === 'US' ? '🇺🇸' : '🇰🇷'} ${s.name_ko}</span><span class="b">${s.unit}</span></div>`).join('');
    // 종목 검색
    try {
      const syms = await (await fetch(`/api/search?q=${encodeURIComponent(q)}`)).json();
      if (syms && syms.length) html += `<div class="mc-dd-grouphdr">종목·ETF·지수</div>` +
        syms.slice(0, 10).map(s => `<div class="mc-dd-item" data-k="SYM:${s.code}" data-l="${(s.name || s.code).replace(/"/g, '')}">
          <span>${s.name || s.code}</span><span class="b">${s.badge || s.code}</span></div>`).join('');
    } catch (e) {}
    dd.innerHTML = html || `<div class="mc-dd-item">결과 없음</div>`;
    dd.classList.add('open');
    dd.querySelectorAll('.mc-dd-item[data-k]').forEach(el => el.addEventListener('click', () => {
      addCustom(el.dataset.k, el.dataset.l); dd.classList.remove('open'); $('mcCustInput').value = '';
    }));
  }

  function addCustom(key, label) {
    if (custom.find(c => c.key === key) || custom.length >= 6) return;
    custom.push({ key, label, color: PALETTE[custom.length % PALETTE.length] });
    renderChips(); loadCustomChart();
  }
  function removeCustom(key) { custom = custom.filter(c => c.key !== key); custom.forEach((c, i) => c.color = PALETTE[i % PALETTE.length]); renderChips(); loadCustomChart(); }

  function renderChips() {
    $('mcChips').innerHTML = custom.map(c => `<span class="mc-chip2" style="background:${c.color}">${c.label}<button data-k="${c.key}">×</button></span>`).join('')
      || `<span class="mc-nores">위에서 지표·종목을 추가하세요.</span>`;
    $('mcChips').querySelectorAll('button').forEach(b => b.addEventListener('click', () => removeCustom(b.dataset.k)));
    // 옵션(정확히 2개일 때 원값 2축 토글)
    const opt = $('mcCustOpt');
    if (custom.length === 2) {
      opt.innerHTML = `<label><input type="radio" name="cmode" value="norm" checked> 정규화(시작=100)</label>
        <label><input type="radio" name="cmode" value="dual"> 원값(좌우 2축)</label>`;
      opt.querySelectorAll('input').forEach(r => r.addEventListener('change', loadCustomChart));
    } else opt.innerHTML = custom.length ? `<span>여러 단위 혼합 → 공통 시작점=100 정규화</span>` : '';
  }

  function custMode() { const r = document.querySelector('input[name="cmode"]:checked'); return (custom.length === 2 && r) ? r.value : 'norm'; }

  async function loadCustomChart() {
    if (!custom.length) { custChart = drawLine('mcCustChart', custChart, [], ''); return; }
    const keys = custom.map(c => c.key).join(',');
    const d = await (await fetch(`/api/macro/multi?keys=${encodeURIComponent(keys)}`)).json();
    const map = {}; (d.series || []).forEach(s => map[s.key] = s);
    const mode = custMode();
    if (mode === 'dual') {
      const ds = custom.map((c, i) => { const s = map[c.key]; if (!s) return null;
        return { ...lineDS(`${c.label} (${s.unit || '원값'})`, s.points, c.color), yAxisID: i === 0 ? 'y' : 'y1' }; }).filter(Boolean);
      custChart = drawDual('mcCustChart', custChart, ds, map);
    } else {
      // 공통 시작점 정규화: 모든 시리즈가 데이터 있는 가장 늦은 시작일 기준
      const starts = custom.map(c => map[c.key]).filter(Boolean).map(s => s.points[0] && s.points[0][0]).filter(Boolean);
      const common = starts.length ? starts.sort().slice(-1)[0] : null;
      const ds = custom.map(c => { const s = map[c.key]; if (!s) return null;
        let pts = common ? s.points.filter(p => p[0] >= common) : s.points;
        const base = pts.find(p => p[1])?.[1]; if (!base) return null;
        return lineDS(c.label, pts.map(p => [p[0], p[1] / base * 100]), c.color); }).filter(Boolean);
      custChart = drawLine('mcCustChart', custChart, ds, '정규화(시작=100)');
    }
  }

  // ── 공통 차트 ──
  function lineDS(label, points, color) {
    return { label, data: points.map(p => ({ x: dnum(p[0]), y: p[1] })), borderColor: color, backgroundColor: color, borderWidth: 1.6, pointRadius: 0, tension: 0.1 };
  }
  function baseOpts(unitLabel, legend) {
    const grid = css('--border') || '#e0e0e0', txt = css('--text-muted') || '#888';
    return {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: legend, labels: { color: txt, font: { size: 11 } } }, tooltip: { callbacks: { title: (it) => fracToDate(it[0].parsed.x) } } },
      scales: { x: { type: 'linear', ticks: { color: txt, callback: (v) => Math.round(v), maxTicksLimit: 9 }, grid: { color: grid } },
        y: { ticks: { color: txt }, grid: { color: grid }, title: { display: !!unitLabel, text: unitLabel, color: txt } } },
    };
  }
  function drawLine(id, prev, datasets, unitLabel) {
    if (prev) prev.destroy();
    return new Chart($(id).getContext('2d'), { type: 'line', data: { datasets }, options: baseOpts(unitLabel, datasets.length > 1) });
  }
  function drawDual(id, prev, datasets, map) {
    if (prev) prev.destroy();
    const o = baseOpts('', true);
    const txt = css('--text-muted') || '#888', grid = css('--border') || '#e0e0e0';
    o.scales.y1 = { position: 'right', ticks: { color: txt }, grid: { drawOnChartArea: false } };
    return new Chart($(id).getContext('2d'), { type: 'line', data: { datasets }, options: o });
  }

  // ── 상세 모달 ──
  async function openDetail(code) {
    $('mcModal').classList.add('open');
    $('mcModalTitle').textContent = '불러오는 중…'; $('mcModalSub').textContent = ''; $('mcModalDesc').style.display = 'none';
    const d = await (await fetch(`/api/macro/series/${code}`)).json();
    if (d.error) { $('mcModalTitle').textContent = '데이터 없음'; return; }
    window._mcDetail = d;
    $('mcModalTitle').textContent = d.name_ko;
    $('mcModalSub').textContent = `${d.country === 'US' ? '🇺🇸 미국' : '🇰🇷 한국'} · 단위 ${d.unit} · ${d.points.length.toLocaleString()}개 관측 · ${d.points[0][0]}~${d.points.at(-1)[0]}`;
    if (d.desc) { $('mcModalDesc').style.display = 'block'; $('mcModalDesc').textContent = d.desc; }
    $('mcPeriod').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.r === '1300'));
    drawDetail(1300);
  }
  function drawDetail(n) {
    const d = window._mcDetail; let pts = d.points;
    if (n && n > 0) pts = pts.slice(-n);
    detailChart = drawLine('mcDetailChart', detailChart, [lineDS(d.name_ko, pts, '#1976D2')], d.unit);
  }

  // ── 이벤트 ──
  $('mcToggle').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    $('mcToggle').querySelectorAll('button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); VIEW = b.dataset.view;
    const showSearch = (VIEW === 'US' || VIEW === 'KR');
    $('mcSearchBar').style.display = showSearch ? 'block' : 'none';
    if (VIEW === 'CMP') renderCompare();
    else if (VIEW === 'CUSTOM') renderCustom();
    else renderCountry(VIEW, $('mcSearch').value);
  }));
  $('mcSearch').addEventListener('input', () => { if (VIEW === 'US' || VIEW === 'KR') renderCountry(VIEW, $('mcSearch').value); });
  $('mcModalX').addEventListener('click', () => $('mcModal').classList.remove('open'));
  $('mcModal').addEventListener('click', (e) => { if (e.target === $('mcModal')) $('mcModal').classList.remove('open'); });
  $('mcPeriod').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    $('mcPeriod').querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on'); drawDetail(+b.dataset.r);
  }));

  fetch('/api/macro/overview').then(r => r.json()).then(d => { DATA = d; renderCountry('US'); })
    .catch(() => { $('mcBody').innerHTML = '<div class="mc-loading">불러오기 실패</div>'; });
})();
