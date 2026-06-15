// 거시경제 지표 탭 (/macro)
(function () {
  let DATA = null;
  let VIEW = 'US';
  let detailChart = null, cmpChart = null, custChart = null;
  const PALETTE = ['#1976D2', '#E65100', '#2E7D32', '#7B1FA2', '#C2185B', '#00838F'];
  let custom = [];          // [{key,label,color}]
  let custStart = null, custEnd = null, custViewMode = 'raw';  // 구간·표시모드 (기본=원값 개별축)
  let custRaw = {};         // 최근 fetch 원본 {key:series}
  let activePreset = 0;
  // 큐레이션 예시: 종목·지수·거시지표를 섞어 "겹쳐보기"가 뭔지 한눈에
  const PRESETS = [
    { title: '🇰🇷 코스피 · 환율 · 기준금리', items: [['SYM:^KS11', '코스피(KOSPI)'], ['KR_USDKRW', '원/달러 환율'], ['KR_BASE_RATE', '한국 기준금리']] },
    { title: '🇺🇸 S&P500 · 기준금리 · VIX', items: [['SYM:^GSPC', 'S&P 500'], ['US_FEDFUNDS', '미 기준금리'], ['US_VIXCLS', 'VIX']] },
    { title: '💻 애플 · 나스닥100 · 미10년물', items: [['SYM:AAPL', '애플'], ['SYM:^NDX', '나스닥100'], ['US_DGS10', '미 국채 10년']] },
    { title: '🥇 금 · 달러지수 · 기대인플레', items: [['SYM:GC=F', '금 선물'], ['US_DTWEXBGS', '달러지수'], ['US_T10YIE', '기대인플레 10Y']] },
  ];

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
    const flag = s.country === 'US' ? '🇺🇸' : s.country === 'KR' ? '🇰🇷' : '🌏';
    const tip = (s.desc || '').replace(/"/g, '&quot;');
    return `<div class="mc-card" data-code="${s.code}" data-name="${s.name_ko}" title="${tip}">
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
      <div class="mc-cust-hero">
        <h3>🔬 무엇이든 겹쳐 비교</h3>
        <p>주식·ETF·지수·거시경제지표를 한 차트에 겹쳐 <b>추세(경향성)</b>를 비교합니다. 단위가 달라도 시작점=100 정규화 또는 개별 축으로 함께 봅니다. 아래 예시를 눌러보거나 직접 추가하세요.</p>
        <div class="mc-presets" id="mcPresets">${PRESETS.map((p, i) => `<button class="mc-preset ${i === activePreset ? 'on' : ''}" data-i="${i}">${p.title}</button>`).join('')}</div>
      </div>
      <div class="mc-cust-search" style="margin-top:14px">
        <input type="text" id="mcCustInput" placeholder="🔍 직접 추가 (예: 삼성전자, 코스피, 국고채, AAPL, CPI)…" autocomplete="off">
        <div class="mc-dd" id="mcCustDD"></div>
      </div>
      <div class="mc-chips" id="mcChips"></div>
      <div class="mc-cust-ctrl" id="mcCustCtrl"></div>
      <div class="mc-cmp-card"><div class="mc-chart-wrap"><canvas id="mcCustChart"></canvas></div></div>`;
    const inp = $('mcCustInput'), dd = $('mcCustDD');
    let t = null;
    inp.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => custSearch(inp.value), 220); });
    inp.addEventListener('focus', () => { if (inp.value.trim()) custSearch(inp.value); });
    document.addEventListener('click', (e) => { if (!dd.contains(e.target) && e.target !== inp) dd.classList.remove('open'); });
    $('mcPresets').querySelectorAll('button').forEach(b => b.addEventListener('click', () => loadPreset(+b.dataset.i)));
    if (!custom.length) loadPreset(activePreset);   // 기본 = 첫 예시
    else { renderChips(); loadCustomChart(); }
  }

  function loadPreset(i) {
    activePreset = i;
    custom = PRESETS[i].items.map(([key, label], idx) => ({ key, label, color: PALETTE[idx % PALETTE.length] }));
    custStart = custEnd = null; custViewMode = 'raw';
    const ps = $('mcPresets');
    if (ps) ps.querySelectorAll('button').forEach(b => b.classList.toggle('on', +b.dataset.i === i));
    renderChips(); loadCustomChart();
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

  function clearPresetHL() { activePreset = -1; const ps = $('mcPresets'); if (ps) ps.querySelectorAll('button').forEach(b => b.classList.remove('on')); }
  function addCustom(key, label) {
    if (custom.find(c => c.key === key) || custom.length >= 6) return;
    custom.push({ key, label, color: PALETTE[custom.length % PALETTE.length] });
    clearPresetHL(); renderChips(); loadCustomChart();
  }
  function removeCustom(key) { custom = custom.filter(c => c.key !== key); custom.forEach((c, i) => c.color = PALETTE[i % PALETTE.length]); clearPresetHL(); renderChips(); loadCustomChart(); }

  function renderChips() {
    $('mcChips').innerHTML = custom.map(c => `<span class="mc-chip2" style="background:${c.color}">${c.label}<button data-k="${c.key}">×</button></span>`).join('')
      || `<span class="mc-nores">위에서 지표·종목을 추가하세요.</span>`;
    $('mcChips').querySelectorAll('button').forEach(b => b.addEventListener('click', () => removeCustom(b.dataset.k)));
  }

  function renderCustCtrl() {
    const ctrl = $('mcCustCtrl');
    if (!ctrl) return;
    if (!custom.length) { ctrl.innerHTML = ''; return; }
    ctrl.innerHTML = `
      <span class="grp">📅 구간:
        <input type="date" id="mcStart" value="${custStart || ''}">
        ~ <input type="date" id="mcEnd" value="${custEnd || ''}"></span>
      <span class="grp">
        <button class="qr" data-y="1">1년</button><button class="qr" data-y="5">5년</button>
        <button class="qr" data-y="10">10년</button><button class="qr" data-y="0">전체</button></span>
      <span class="grp">표시:
        <label><input type="radio" name="cmode" value="norm" ${custViewMode === 'norm' ? 'checked' : ''}> 정규화(시작=100)</label>
        <label><input type="radio" name="cmode" value="raw" ${custViewMode === 'raw' ? 'checked' : ''}> 원값(개별 축)</label></span>`;
    $('mcStart').addEventListener('change', (e) => { custStart = e.target.value; drawCustom(); });
    $('mcEnd').addEventListener('change', (e) => { custEnd = e.target.value; drawCustom(); });
    ctrl.querySelectorAll('input[name=cmode]').forEach(r => r.addEventListener('change', (e) => { custViewMode = e.target.value; drawCustom(); }));
    ctrl.querySelectorAll('.qr').forEach(b => b.addEventListener('click', () => {
      const yrs = +b.dataset.y;
      const ends = Object.values(custRaw).map(s => s.points.at(-1)?.[0]).filter(Boolean).sort();
      custEnd = ends.length ? ends.at(-1) : null;
      if (yrs === 0) {
        const mins = Object.values(custRaw).map(s => s.points[0]?.[0]).filter(Boolean).sort();
        custStart = mins.length ? mins.at(-1) : null;   // 공통 시작(가장 늦은 시작일)
      } else if (custEnd) {
        const d = new Date(custEnd); d.setFullYear(d.getFullYear() - yrs);
        custStart = d.toISOString().slice(0, 10);
      }
      renderCustCtrl(); drawCustom();
    }));
  }

  async function loadCustomChart() {
    if (!custom.length) { custRaw = {}; renderCustCtrl(); custChart = drawLine('mcCustChart', custChart, [], ''); return; }
    const keys = custom.map(c => c.key).join(',');
    const d = await (await fetch(`/api/macro/multi?keys=${encodeURIComponent(keys)}`)).json();
    custRaw = {}; (d.series || []).forEach(s => custRaw[s.key] = s);
    // 기본 구간: 공통 시작(가장 늦은 시작일) ~ 최신
    if (!custStart) {
      const mins = Object.values(custRaw).map(s => s.points[0]?.[0]).filter(Boolean).sort();
      custStart = mins.length ? mins.at(-1) : null;
    }
    if (!custEnd) {
      const maxs = Object.values(custRaw).map(s => s.points.at(-1)?.[0]).filter(Boolean).sort();
      custEnd = maxs.length ? maxs.at(-1) : null;
    }
    renderCustCtrl();
    drawCustom();
  }

  function inRange(p) { return (!custStart || p[0] >= custStart) && (!custEnd || p[0] <= custEnd); }

  function drawCustom() {
    if (!custom.length) { custChart = drawLine('mcCustChart', custChart, [], ''); return; }
    if (custViewMode === 'raw') {
      const datasets = [], axes = {};
      const txt = css('--text-muted') || '#888', grid = css('--border') || '#e0e0e0';
      custom.forEach((c, i) => {
        const s = custRaw[c.key]; if (!s) return;
        const pts = s.points.filter(inRange); if (!pts.length) return;
        const ax = 'y' + i;
        axes[ax] = { position: i % 2 ? 'right' : 'left', ticks: { color: c.color, font: { size: 10 } },
          grid: { drawOnChartArea: i === 0, color: grid } };
        datasets.push({ ...lineDS(`${c.label} (${s.unit || '원값'})`, pts, c.color), yAxisID: ax });
      });
      custChart = drawAxes('mcCustChart', custChart, datasets, axes);
    } else {
      const ds = custom.map(c => { const s = custRaw[c.key]; if (!s) return null;
        const pts = s.points.filter(inRange);
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
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'x', intersect: false },
      plugins: { legend: { display: legend, labels: { color: txt, font: { size: 11 } } }, tooltip: { mode: 'x', intersect: false, callbacks: { title: (it) => fracToDate(it[0].parsed.x) } } },
      scales: { x: { type: 'linear', ticks: { color: txt, callback: (v) => fracToDate(v), maxTicksLimit: 9 }, grid: { color: grid } },
        y: { ticks: { color: txt }, grid: { color: grid }, title: { display: !!unitLabel, text: unitLabel, color: txt } } },
    };
  }
  function drawLine(id, prev, datasets, unitLabel) {
    if (prev) prev.destroy();
    return new Chart($(id).getContext('2d'), { type: 'line', data: { datasets }, options: baseOpts(unitLabel, datasets.length > 1) });
  }
  function drawAxes(id, prev, datasets, axes) {
    if (prev) prev.destroy();
    const o = baseOpts('', true);
    delete o.scales.y;            // 시리즈별 개별 y축으로 교체
    Object.assign(o.scales, axes);
    return new Chart($(id).getContext('2d'), { type: 'line', data: { datasets }, options: o });
  }

  // ── 상세 모달 ──
  let detailMonths = 60, detailType = 'line', candleChart = null, candleCache = null;

  function cutoffDate(lastStr, months) {
    if (!months || months <= 0) return null;
    const d = new Date(lastStr); d.setMonth(d.getMonth() - months);
    return d.toISOString().slice(0, 10);
  }

  async function openDetail(code) {
    $('mcModal').classList.add('open');
    $('mcModalTitle').textContent = '불러오는 중…'; $('mcModalSub').textContent = ''; $('mcModalDesc').style.display = 'none';
    const d = await (await fetch(`/api/macro/series/${code}`)).json();
    if (d.error) { $('mcModalTitle').textContent = '데이터 없음'; return; }
    window._mcDetail = d; candleCache = null; detailMonths = 60; detailType = 'line';
    const flag = d.country === 'US' ? '🇺🇸 미국' : d.country === 'KR' ? '🇰🇷 한국' : '🌏 글로벌';
    $('mcModalTitle').textContent = d.name_ko;
    $('mcModalSub').textContent = `${flag} · 단위 ${d.unit} · ${d.points.length.toLocaleString()}개 관측 · ${d.points[0][0]}~${d.points.at(-1)[0]}`;
    if (d.desc) { $('mcModalDesc').style.display = 'block'; $('mcModalDesc').textContent = d.desc; }
    // 지수만 캔들 토글 노출
    $('mcChartType').style.display = d.is_index ? 'inline-flex' : 'none';
    $('mcChartType').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.t === 'line'));
    $('mcPeriod').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.m === '60'));
    renderDetail();
  }

  async function renderDetail() {
    const d = window._mcDetail;
    const showCandle = detailType === 'candle' && d.is_index;
    $('mcLineWrap').style.display = showCandle ? 'none' : 'block';
    $('mcCandleWrap').style.display = showCandle ? 'block' : 'none';
    const cut = cutoffDate(d.points.at(-1)[0], detailMonths);
    if (showCandle) {
      if (!candleCache) {
        const r = await (await fetch(`/api/macro/ohlc/${d.code}`)).json();
        candleCache = (r.rows || []).filter(p => p.open != null && p.close != null);
      }
      const rows = candleCache.filter(p => !cut || p.date >= cut)
        .map(p => ({ time: p.date, open: p.open, high: p.high, low: p.low, close: p.close }));
      drawCandle(rows);
    } else {
      const pts = cut ? d.points.filter(p => p[0] >= cut) : d.points;
      detailChart = drawLine('mcDetailChart', detailChart, [lineDS(d.name_ko, pts, '#1976D2')], d.unit);
    }
  }

  function drawCandle(rows) {
    const wrap = $('mcCandleWrap');
    wrap.innerHTML = '';
    if (candleChart) { try { candleChart.remove(); } catch (e) {} candleChart = null; }
    const txt = css('--text-muted') || '#888', grid = css('--border') || '#e0e0e0';
    candleChart = LightweightCharts.createChart(wrap, {
      width: wrap.clientWidth, height: wrap.clientHeight || 380,
      layout: { background: { color: 'transparent' }, textColor: txt },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      timeScale: { timeVisible: false },
    });
    const s = candleChart.addCandlestickSeries({ upColor: '#2E7D32', downColor: '#C62828', borderVisible: false, wickUpColor: '#2E7D32', wickDownColor: '#C62828' });
    s.setData(rows);
    candleChart.timeScale().fitContent();
  }

  // ── 이벤트 ──
  $('mcToggle').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    $('mcToggle').querySelectorAll('button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); VIEW = b.dataset.view;
    const showSearch = (VIEW === 'US' || VIEW === 'KR' || VIEW === 'GL');
    $('mcSearchBar').style.display = showSearch ? 'block' : 'none';
    if (VIEW === 'CMP') renderCompare();
    else if (VIEW === 'CUSTOM') renderCustom();
    else renderCountry(VIEW, $('mcSearch').value);
  }));
  $('mcSearch').addEventListener('input', () => { if (VIEW === 'US' || VIEW === 'KR' || VIEW === 'GL') renderCountry(VIEW, $('mcSearch').value); });
  $('mcFsBtn').addEventListener('click', () => {
    const box = document.querySelector('.mc-modal-box');
    if (!document.fullscreenElement) { box.requestFullscreen && box.requestFullscreen(); }
    else { document.exitFullscreen && document.exitFullscreen(); }
  });
  document.addEventListener('fullscreenchange', () => {
    if ($('mcModal').classList.contains('open')) setTimeout(renderDetail, 150);
  });
  $('mcModalX').addEventListener('click', () => { if (document.fullscreenElement) document.exitFullscreen(); $('mcModal').classList.remove('open'); });
  $('mcModal').addEventListener('click', (e) => { if (e.target === $('mcModal')) $('mcModal').classList.remove('open'); });
  $('mcPeriod').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    $('mcPeriod').querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on');
    detailMonths = +b.dataset.m; renderDetail();
  }));
  $('mcChartType').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    $('mcChartType').querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on');
    detailType = b.dataset.t; renderDetail();
  }));

  fetch('/api/macro/overview').then(r => r.json()).then(d => { DATA = d; renderCountry('US'); })
    .catch(() => { $('mcBody').innerHTML = '<div class="mc-loading">불러오기 실패</div>'; });
})();
