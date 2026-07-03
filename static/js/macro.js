// 거시경제 지표 탭 (/macro)
(function () {
  let DATA = null;
  let VIEW = 'US';
  let detailChart = null, cmpChart = null, custChart = null;
  const PALETTE = ['#1976D2', '#E65100', '#2E7D32', '#7B1FA2', '#C2185B', '#00838F'];
  let custom = [];          // [{key,label,color}]
  let custStart = null, custEnd = null, custViewMode = 'raw';  // 구간·표시모드 (기본=최근10년·원값 개별축)
  let custOwner = 'custom';  // 'cmp'|'custom' — 공용 custom 상태 소유 뷰(전환 시 누수 방지)
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

  function mcFlag(c) { return c === 'US' ? '🇺🇸' : c === 'KR' ? '🇰🇷' : c === 'COMM' ? '🛢' : '🌏'; }
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
      const cp = (s.change_pct != null) ? ` <span class="chg-pct">(${s.change_pct > 0 ? '+' : ''}${s.change_pct.toFixed(2)}%)</span>` : '';
      // 절대 변화값은 span 분리 — 모바일 리스트 행에선 %만 노출(B5-1, 이름 폭 확보)
      chgTxt = `${up ? '▲' : dn ? '▼' : '–'} <span class="chg-abs">${fmtVal(Math.abs(s.change), s.unit)}</span>${cp}`;
    }
    const flag = mcFlag(s.country);
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
    // 모바일 sticky 카테고리 점프 칩 (F-6 B5-1) — 지표 151종 1열 스크롤 탐색성
    const chips = cats.length > 1
      ? `<div class="mc-catnav" id="mcCatNav">${cats.map((c, i) =>
          `<button class="mc-catchip" data-target="mc-cat-${i}">${c.category}</button>`).join('')}</div>`
      : '';
    let html = chips + cats.map((c, i) => `<div class="mc-cat" id="mc-cat-${i}"><div class="mc-cat-head"><span class="dot"></span>${c.category}</div>
        <div class="mc-grid">${c.series.map(cardHTML).join('')}</div></div>`).join('');
    if (!cats.length) html = `<div class="mc-nores">검색 결과 없음${f ? ` ("${filter}")` : ''}</div>`;
    $('mcBody').innerHTML = html;
    $('mcBody').querySelectorAll('.mc-card').forEach(el => el.addEventListener('click', () => openDetail(el.dataset.code)));
    $('mcBody').querySelectorAll('.mc-catchip').forEach(b => b.addEventListener('click', () => {
      const t = document.getElementById(b.dataset.target);
      if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }));
  }

  // ── 한·미 비교(고정 쌍) ──
  function renderCompare() {
    const pairs = DATA.compare_pairs;
    // 겹쳐보기 머신 재활용 — 한 쌍 클릭 시 custom=[us,kr]로 로드. 컨트롤(구간·정규화)·차트 공용.
    $('mcBody').innerHTML = `
      <div class="mc-cust-hero">
        <h3>🆚 한·미 지표 비교</h3>
        <p>미국·한국 같은 지표를 한 차트에 겹쳐 봅니다. 금리·실업률처럼 같은 단위는 <b>단일 축</b>, 단위나 스케일이 다르면 개별 축으로 봅니다.</p>
        <div class="mc-presets" id="mcCmpPairs">${pairs.map((p, i) => `<button class="mc-preset ${i === 0 ? 'on' : ''}" data-i="${i}">${p.label}</button>`).join('')}</div>
      </div>
      <div class="mc-cust-ctrl" id="mcCustCtrl"></div>
      <div class="mc-cmp-card"><div class="mc-chart-wrap"><canvas id="mcCustChart"></canvas></div></div>`;
    $('mcCmpPairs').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
      $('mcCmpPairs').querySelectorAll('button').forEach(x => x.classList.remove('on'));
      b.classList.add('on'); loadCmpPair(pairs[+b.dataset.i]);
    }));
    if (pairs.length) loadCmpPair(pairs[0]);
  }
  function _macroName(code) {
    for (const c of DATA.categories) for (const s of c.series) if (s.code === code) return s.name_ko;
    return code;
  }
  function loadCmpPair(pair) {
    custom = [
      { key: pair.us, label: `🇺🇸 ${_macroName(pair.us)}`, color: PALETTE[0] },
      { key: pair.kr, label: `🇰🇷 ${_macroName(pair.kr)}`, color: PALETTE[1] },
    ];
    custStart = custEnd = null; custViewMode = 'raw';   // 기본 = 최근10년·원값
    custOwner = 'cmp';
    loadCustomChart();
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
    // CMP 뷰가 쓰던 custom이 남아있으면 초기화(전환 누수 방지)
    if (custOwner !== 'custom') { custom = []; custOwner = 'custom'; }
    if (!custom.length) loadPreset(activePreset < 0 ? 0 : activePreset);   // 기본 = 예시
    else { renderChips(); loadCustomChart(); }
  }

  function loadPreset(i) {
    activePreset = i;
    custom = PRESETS[i].items.map(([key, label], idx) => ({ key, label, color: PALETTE[idx % PALETTE.length] }));
    custStart = custEnd = null; custViewMode = 'raw';   // 기본 = 최근10년·원값 개별축
    custOwner = 'custom';
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
        <span>${mcFlag(s.country)} ${s.name_ko}</span><span class="b">${s.unit}</span></div>`).join('');
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
    // 현재 구간이 몇 년 프리셋에 해당하는지 — 활성 하이라이트
    let activeY = null;
    if (custStart && custEnd) {
      const yr = (new Date(custEnd) - new Date(custStart)) / (365.25 * 864e5);
      const mins = Object.values(custRaw).map(s => s.points[0]?.[0]).filter(Boolean).sort();
      const common = mins.length ? mins.at(-1) : null;
      if (common && custStart <= common) activeY = 0;
      else activeY = [1, 5, 10].find(y => Math.abs(yr - y) < 0.3) ?? null;
    }
    const qr = (y, t) => `<button class="qr${activeY === y ? ' on' : ''}" data-y="${y}">${t}</button>`;
    ctrl.innerHTML = `
      <span class="grp">📅 구간:
        <input type="date" id="mcStart" value="${custStart || ''}">
        ~ <input type="date" id="mcEnd" value="${custEnd || ''}"></span>
      <span class="grp">
        ${qr(1, '1년')}${qr(5, '5년')}${qr(10, '10년')}${qr(0, '전체')}</span>
      <span class="grp">표시:
        <label><input type="radio" name="cmode" value="norm" ${custViewMode === 'norm' ? 'checked' : ''}> 정규화(시작=100)</label>
        <label><input type="radio" name="cmode" value="raw" ${custViewMode === 'raw' ? 'checked' : ''}> ${custOwner === 'cmp' ? '원값(가능하면 단일 축)' : '원값(개별 축)'}</label></span>`;
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
    // 기본 구간 = 최근 10년 (모바일 좁은 폭에 50년 우겨넣어 짜부되던 문제). 공통시작보다 이르면 공통시작.
    if (!custEnd) {
      const maxs = Object.values(custRaw).map(s => s.points.at(-1)?.[0]).filter(Boolean).sort();
      custEnd = maxs.length ? maxs.at(-1) : null;
    }
    if (!custStart) {
      const mins = Object.values(custRaw).map(s => s.points[0]?.[0]).filter(Boolean).sort();
      const common = mins.length ? mins.at(-1) : null;   // 공통 시작(가장 늦은 시작일)
      if (custEnd) {
        const d10 = new Date(custEnd); d10.setFullYear(d10.getFullYear() - 10);
        const tenYr = d10.toISOString().slice(0, 10);
        custStart = (common && tenYr < common) ? common : tenYr;
      } else custStart = common;
    }
    renderCustCtrl();
    drawCustom();
  }

  function inRange(p) { return (!custStart || p[0] >= custStart) && (!custEnd || p[0] <= custEnd); }
  function cmpSharedRawUnit(series) {
    if (custOwner !== 'cmp' || series.length < 2) return null;
    const rawUnits = new Set(['%', '%p', '배']);
    const units = [...new Set(series.map(s => s.unit).filter(Boolean))];
    return units.length === 1 && rawUnits.has(units[0]) ? units[0] : null;
  }

  function drawCustom() {
    if (!custom.length) { custChart = drawLine('mcCustChart', custChart, [], ''); return; }
    if (custViewMode === 'raw') {
      const datasets = [], axes = {};
      const txt = css('--text-muted') || '#888', grid = css('--border') || '#e0e0e0';
      const seriesForAxis = custom.map(c => custRaw[c.key]).filter(Boolean);
      const sharedUnit = cmpSharedRawUnit(seriesForAxis);
      custom.forEach((c, i) => {
        const s = custRaw[c.key]; if (!s) return;
        const pts = s.points.filter(inRange); if (!pts.length) return;
        if (sharedUnit) {
          datasets.push(lineDS(`${c.label} (${s.unit || '원값'})`, pts, c.color));
          return;
        }
        const ax = 'y' + i;
        axes[ax] = { position: i % 2 ? 'right' : 'left', ticks: { color: c.color, font: { size: 10 } },
          grid: { drawOnChartArea: i === 0, color: grid } };
        datasets.push({ ...lineDS(`${c.label} (${s.unit || '원값'})`, pts, c.color), yAxisID: ax });
      });
      custChart = sharedUnit
        ? drawLine('mcCustChart', custChart, datasets, sharedUnit)
        : drawAxes('mcCustChart', custChart, datasets, axes);
    } else {
      const ds = custom.map(c => { const s = custRaw[c.key]; if (!s) return null;
        const pts = s.points.filter(inRange);
        const base = pts.find(p => p[1])?.[1]; if (!base) return null;
        return lineDS(c.label, pts.map(p => [p[0], p[1] / base * 100]), c.color); }).filter(Boolean);
      custChart = drawLine('mcCustChart', custChart, ds, '정규화(시작=100)');
    }
  }

  // ── 커브 (만기축 단면) ──
  let curveList = null, curCurve = null, curveSnaps = {}, curveMonthIdx = -1, curveFwd = false;

  async function renderCurves() {
    if (!curveList) curveList = (await (await fetch('/api/macro/curves')).json()).curves;
    $('mcBody').innerHTML = `
      <div class="mc-cust-intro">만기(가로축)에 따른 값의 단면 = <b>커브</b>. 최신 + 과거 시점을 겹쳐 형태 변화를 봅니다. (예: 국채 커브 역전, 신용 스프레드 확대)</div>
      <div class="mc-presets" id="mcCurveBtns">${curveList.map((c, i) => `<button class="mc-preset ${i === 0 ? 'on' : ''}" data-id="${c.id}">${c.label}</button>`).join('')}</div>
      <div class="mc-cmp-card">
        <div class="mc-cust-ctrl" id="mcCurveCtrl"></div>
        <div class="mc-chart-wrap"><canvas id="mcCurveChart"></canvas></div>
      </div>`;
    $('mcCurveBtns').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
      $('mcCurveBtns').querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on');
      loadCurve(b.dataset.id);
    }));
    loadCurve(curveList[0].id);
  }

  async function loadCurve(id) {
    curCurve = await (await fetch(`/api/macro/curve/${id}`)).json();
    curveSnaps = { '1y': true, '3y': false, '5y': false };
    curveMonthIdx = -1; curveFwd = false;
    renderCurveCtrl(); drawCurveChart();
  }

  function renderCurveCtrl() {
    const c = curCurve, last = c.months.length - 1;
    let html = `<span class="grp">비교:
      <label><input type="checkbox" data-s="1y" ${curveSnaps['1y'] ? 'checked' : ''}> 1년 전</label>
      <label><input type="checkbox" data-s="3y" ${curveSnaps['3y'] ? 'checked' : ''}> 3년 전</label>
      <label><input type="checkbox" data-s="5y" ${curveSnaps['5y'] ? 'checked' : ''}> 5년 전</label></span>`;
    if (c.forward) html += `<span class="grp"><label><input type="checkbox" id="mcFwd" ${curveFwd ? 'checked' : ''}> implied forward(근사)</label></span>`;
    html += `<span class="grp" style="flex:1;min-width:200px">시점: <input type="range" id="mcCurveSlider" min="0" max="${last}" value="${curveMonthIdx < 0 ? last : curveMonthIdx}" style="flex:1"> <span id="mcCurveMo" style="min-width:64px">${curveMonthIdx < 0 ? '최신' : c.months[curveMonthIdx]}</span></span>`;
    const ctrl = $('mcCurveCtrl'); ctrl.innerHTML = html;
    ctrl.querySelectorAll('input[type=checkbox][data-s]').forEach(cb => cb.addEventListener('change', e => { curveSnaps[e.target.dataset.s] = e.target.checked; drawCurveChart(); }));
    const fwd = $('mcFwd'); if (fwd) fwd.addEventListener('change', e => { curveFwd = e.target.checked; drawCurveChart(); });
    $('mcCurveSlider').addEventListener('input', e => {
      curveMonthIdx = +e.target.value === last ? -1 : +e.target.value;
      $('mcCurveMo').textContent = curveMonthIdx < 0 ? '최신' : c.months[curveMonthIdx];
      drawCurveChart();
    });
  }

  function snapAt(c, monthsBack) {
    const idx = c.months.length - 1 - monthsBack * 12;
    return idx >= 0 ? { label: `${monthsBack}년 전 (${c.months[idx]})`, values: c.matrix[idx] } : null;
  }
  function impliedForward(x, y) {  // 근사: 연속 만기 사이 1구간 선도금리
    const out = [];
    for (let i = 1; i < x.length; i++) {
      if (y[i] == null || y[i - 1] == null) { out.push(null); continue; }
      const f = (y[i] * x[i] - y[i - 1] * x[i - 1]) / (x[i] - x[i - 1]);
      out.push({ x: (x[i] + x[i - 1]) / 2, y: f });
    }
    return out;
  }

  function drawCurveChart() {
    const c = curCurve;
    const pts = (vals) => c.x.map((xx, i) => (vals[i] == null ? null : { x: xx, y: vals[i] })).filter(Boolean);
    const ds = [];
    ds.push({ label: `최신 (${c.latest.date})`, data: pts(c.latest.values), borderColor: '#1976D2', backgroundColor: '#1976D2', borderWidth: 2.4, pointRadius: 3, tension: 0.2 });
    const snapCols = { '1y': '#E65100', '3y': '#7B1FA2', '5y': '#00838F' };
    ['1y', '3y', '5y'].forEach(k => { if (curveSnaps[k]) { const s = snapAt(c, +k[0]); if (s) ds.push({ label: s.label, data: pts(s.values), borderColor: snapCols[k], backgroundColor: snapCols[k], borderWidth: 1.6, pointRadius: 2, tension: 0.2, borderDash: [5, 3] }); } });
    if (curveMonthIdx >= 0) ds.push({ label: `선택 (${c.months[curveMonthIdx]})`, data: pts(c.matrix[curveMonthIdx]), borderColor: '#2E7D32', backgroundColor: '#2E7D32', borderWidth: 2, pointRadius: 3, tension: 0.2 });
    if (c.forward && curveFwd) { const fy = impliedForward(c.x, c.latest.values); ds.push({ label: 'implied fwd(근사)', data: fy.filter(Boolean), borderColor: '#C2185B', backgroundColor: '#C2185B', borderWidth: 1.6, pointRadius: 2, tension: 0.2, borderDash: [2, 2] }); }
    const grid = css('--border') || '#e0e0e0', txt = css('--text-muted') || '#888';
    if (custChart && custChart.canvas && custChart.canvas.id === 'mcCurveChart') custChart.destroy();
    if (window._mcCurveChart) window._mcCurveChart.destroy();
    window._mcCurveChart = new Chart($('mcCurveChart').getContext('2d'), {
      type: 'line', data: { datasets: ds },
      options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: 'nearest', intersect: false },
        plugins: { legend: { labels: { color: txt, font: { size: 11 } } },
          tooltip: { callbacks: { title: it => { const xx = it[0].parsed.x; const i = c.x.indexOf(xx); return i >= 0 ? c.labels[i] : ('만기 ' + xx); } } } },
        scales: {
          x: { type: 'linear', title: { display: true, text: c.x_labels ? '' : '만기(년)', color: txt },
            ticks: { color: txt, callback: v => { const i = c.x.indexOf(v); return i >= 0 ? c.labels[i] : v; } }, grid: { color: grid } },
          y: { ticks: { color: txt }, grid: { color: grid }, title: { display: true, text: c.unit, color: txt } } },
      },
    });
  }

  // ── 공통 차트 ──
  function lineDS(label, points, color) {
    return { label, data: points.map(p => ({ x: dnum(p[0]), y: p[1] })), borderColor: color, backgroundColor: color, borderWidth: 1.6, pointRadius: 0, tension: 0.1 };
  }
  function _mcMobile() { return window.matchMedia('(max-width: 768px)').matches; }
  // datasets의 실제 x(분수연도) 경계 — Chart.js가 2040까지 예쁘게 늘여 오른쪽을 비우던 문제 차단
  function _xBounds(datasets) {
    let mn = Infinity, mx = -Infinity;
    for (const ds of datasets) for (const p of ds.data) {
      if (p.x < mn) mn = p.x; if (p.x > mx) mx = p.x;
    }
    // 정수 연도로 반올림 → Chart가 중간 눈금(1960·1980…)을 예쁘게 생성(성긴 2눈금 방지)
    return isFinite(mn) ? { min: Math.floor(mn), max: Math.ceil(mx) } : {};
  }
  function baseOpts(unitLabel, legend, datasets) {
    const grid = css('--border') || '#e0e0e0', txt = css('--text-muted') || '#888';
    const mobile = _mcMobile();
    const b = datasets ? _xBounds(datasets) : {};
    const spanYears = (b.max != null) ? (b.max - b.min) : 0;
    // 긴 구간(>8년)은 연도만, 짧으면 YYYY-MM — 모바일 라벨 겹침 해소
    const xfmt = (v) => spanYears > 8 ? String(Math.round(v)) : fracToDate(v);
    return {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: legend, labels: { color: txt, font: { size: 11 }, boxWidth: 22, padding: mobile ? 8 : 10 } },
        tooltip: { mode: 'index', intersect: false,
          filter: (item, i, arr) => arr.findIndex(a => a.datasetIndex === item.datasetIndex) === i,
          callbacks: { title: (it) => fracToDate(it[0].parsed.x) } } },
      scales: { x: { type: 'linear', min: b.min, max: b.max,
          ticks: { color: txt, callback: xfmt, maxTicksLimit: mobile ? 5 : 9,
                   maxRotation: 0, minRotation: 0, autoSkip: true, font: { size: mobile ? 10 : 11 } },
          grid: { color: grid } },
        y: { ticks: { color: txt, maxTicksLimit: mobile ? 7 : 11, font: { size: mobile ? 10 : 11 } },
             grid: { color: grid }, title: { display: !!unitLabel, text: unitLabel, color: txt } } },
    };
  }
  function drawLine(id, prev, datasets, unitLabel) {
    if (prev) prev.destroy();
    return new Chart($(id).getContext('2d'), { type: 'line', data: { datasets }, options: baseOpts(unitLabel, datasets.length > 1, datasets) });
  }
  function drawAxes(id, prev, datasets, axes) {
    if (prev) prev.destroy();
    const o = baseOpts('', true, datasets);
    delete o.scales.y;            // 시리즈별 개별 y축으로 교체
    Object.assign(o.scales, axes);
    return new Chart($(id).getContext('2d'), { type: 'line', data: { datasets }, options: o });
  }

  // ── 상세 모달 (라인=기간 / 캔들=간격, 거래량·줌·시간봉 — symbol 페이지 동일) ──
  let detailMonths = 60, detailType = 'line', candleInterval = '1D';
  let candleChart = null, candleCache = null, intradayCache = {};
  const CANDLE_DEFAULT_DAYS = { '1H': 2, '1D': 75, '1W': 365, '1M': 2555, '1Y': 0 };

  function cutoffDate(lastStr, months) {
    if (!months || months <= 0) return null;
    const d = new Date(lastStr); d.setMonth(d.getMonth() - months);
    return d.toISOString().slice(0, 10);
  }
  function bucketKey(dateStr, unit) {
    if (unit === 'M') return dateStr.slice(0, 7);
    if (unit === 'Y') return dateStr.slice(0, 4);
    const d = new Date(dateStr), onejan = new Date(d.getFullYear(), 0, 1);
    const week = Math.ceil((((d - onejan) / 86400000) + onejan.getDay() + 1) / 7);
    return d.getFullYear() + '-W' + week;
  }
  function resampleOHLC(prices, unit) {
    const out = []; let key = null, cur = null;
    for (const p of prices) {
      if (p.open == null) continue;
      const k = bucketKey(p.date, unit);
      if (k !== key) { if (cur) out.push(cur); key = k; cur = { date: p.date, open: p.open, high: p.high, low: p.low, close: p.close, volume: p.volume || 0 }; }
      else { cur.high = Math.max(cur.high, p.high); cur.low = Math.min(cur.low, p.low); cur.close = p.close; cur.volume += (p.volume || 0); }
    }
    if (cur) out.push(cur);
    return out;
  }
  async function fetchMacroIntraday(code, rng) {
    if (!intradayCache[rng]) {
      const r = await (await fetch(`/api/macro/intraday/${code}?range=${rng}`)).json();
      intradayCache[rng] = r.rows || [];
    }
    return intradayCache[rng];
  }
  async function getCandleData(code, interval) {
    if (interval === '1H') return { prices: await fetchMacroIntraday(code, 'max'), intraday: true };
    const all = candleCache || [];
    if (interval === '1D') return { prices: all, intraday: false };
    const unit = interval === '1W' ? 'W' : interval === '1M' ? 'M' : 'Y';
    return { prices: resampleOHLC(all, unit), intraday: false };
  }

  async function openDetail(code) {
    $('mcModal').classList.add('open');
    $('mcModalTitle').textContent = '불러오는 중…'; $('mcModalSub').textContent = ''; $('mcModalDesc').style.display = 'none';
    const d = await (await fetch(`/api/macro/series/${code}`)).json();
    if (d.error) { $('mcModalTitle').textContent = '데이터 없음'; return; }
    window._mcDetail = d; candleCache = null; intradayCache = {}; detailMonths = 60; detailType = 'line'; candleInterval = '1D';
    const flag = d.country === 'US' ? '🇺🇸 미국' : d.country === 'KR' ? '🇰🇷 한국' : d.country === 'COMM' ? '🛢 원자재' : '🌏 글로벌';
    $('mcModalTitle').textContent = d.name_ko;
    $('mcModalSub').textContent = `${flag} · 단위 ${d.unit} · ${d.points.length.toLocaleString()}개 관측 · ${d.points[0][0]}~${d.points.at(-1)[0]}`;
    if (d.desc) { $('mcModalDesc').style.display = 'block'; $('mcModalDesc').textContent = d.desc; }
    $('mcChartType').style.display = d.is_index ? 'inline-flex' : 'none';
    $('mcChartType').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.t === 'line'));
    $('mcPeriod').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.m === '60'));
    $('mcInterval').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.i === '1D'));
    renderDetail();
  }

  async function renderDetail() {
    const d = window._mcDetail;
    const candle = detailType === 'candle' && d.is_index;
    $('mcPeriod').style.display = candle ? 'none' : 'inline-flex';
    $('mcInterval').style.display = candle ? 'inline-flex' : 'none';
    $('mcLineWrap').style.display = candle ? 'none' : 'block';
    $('mcCandleWrap').style.display = candle ? 'block' : 'none';
    if (candle) {
      if (!candleCache) {
        const r = await (await fetch(`/api/macro/ohlc/${d.code}`)).json();
        candleCache = (r.rows || []).filter(p => p.open != null && p.close != null);
      }
      const labelMap = { '1H': '1시간', '1D': '1일', '1W': '1주', '1M': '1개월', '1Y': '1년' };
      $('mcHint').textContent = candleInterval === '1H'
        ? '⚠ 캔들 1개 = 1시간 · 시간봉은 최근 약 730일(2년)까지. (스크롤·줌으로 조정)'
        : `캔들 1개 = ${labelMap[candleInterval]} · 전체 기간 (기본 화면 밖은 스크롤·줌)`;
      const { prices, intraday } = await getCandleData(d.code, candleInterval);
      drawCandle(prices, intraday, candleInterval);
    } else {
      $('mcHint').textContent = '';
      const cut = cutoffDate(d.points.at(-1)[0], detailMonths);
      const pts = cut ? d.points.filter(p => p[0] >= cut) : d.points;
      detailChart = drawLine('mcDetailChart', detailChart, [lineDS(d.name_ko, pts, '#1976D2')], d.unit);
    }
  }

  function drawCandle(prices, intraday, interval) {
    const wrap = $('mcCandleWrap');
    if (candleChart) { try { candleChart.remove(); } catch (e) {} candleChart = null; }
    wrap.innerHTML = '';
    if (!prices || !prices.length) return;
    const txt = css('--text-muted') || '#888', grid = css('--border') || '#e0e0e0';
    candleChart = LightweightCharts.createChart(wrap, {
      width: wrap.clientWidth, height: wrap.clientHeight || 380,
      layout: { background: { color: 'transparent' }, textColor: txt },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      timeScale: { timeVisible: !!intraday, secondsVisible: false, borderColor: grid },
      rightPriceScale: { borderColor: grid, scaleMargins: { top: 0.08, bottom: 0.26 } },
      crosshair: { mode: 0 },
    });
    const toTime = p => intraday ? Math.floor(new Date(p.date.replace(' ', 'T')).getTime() / 1000) : p.date;
    const s = candleChart.addCandlestickSeries({ upColor: '#2E7D32', downColor: '#C62828', borderVisible: false, wickUpColor: '#2E7D32', wickDownColor: '#C62828' });
    s.setData(prices.map(p => ({ time: toTime(p), open: p.open, high: p.high, low: p.low, close: p.close })));
    const vol = candleChart.addHistogramSeries({ priceScaleId: 'vol', priceFormat: { type: 'volume' } });
    candleChart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
    vol.setData(prices.map(p => ({ time: toTime(p), value: p.volume || 0, color: (p.close >= p.open) ? 'rgba(46,125,50,0.45)' : 'rgba(198,40,40,0.45)' })));
    // 간격별 기본 줌
    const days = CANDLE_DEFAULT_DAYS[interval] || 0, ts = candleChart.timeScale();
    if (days > 0 && prices.length > 1) {
      const last = prices[prices.length - 1], lastT = toTime(last);
      const fromT = intraday ? lastT - days * 86400 : (() => { const dd = new Date(last.date); dd.setDate(dd.getDate() - days); return dd.toISOString().slice(0, 10); })();
      try { ts.setVisibleRange({ from: fromT, to: lastT }); } catch (e) { ts.fitContent(); }
    } else ts.fitContent();
  }

  // ── 이벤트 ──
  $('mcToggle').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    $('mcToggle').querySelectorAll('button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); VIEW = b.dataset.view;
    const showSearch = (VIEW === 'US' || VIEW === 'KR' || VIEW === 'GL' || VIEW === 'COMM');
    $('mcSearchBar').style.display = showSearch ? 'block' : 'none';
    if (VIEW === 'CMP') renderCompare();
    else if (VIEW === 'CUSTOM') renderCustom();
    else if (VIEW === 'CURVE') renderCurves();
    else renderCountry(VIEW, $('mcSearch').value);
  }));
  // 검색창 밑 분석도구 바로가기 → 토글 해당 뷰 위임
  document.querySelectorAll('#mcTools .mc-tool').forEach(b => b.addEventListener('click', () => {
    const t = $('mcToggle').querySelector(`button[data-view="${b.dataset.view}"]`);
    if (t) { t.click(); t.scrollIntoView({ inline: 'center', block: 'nearest' }); }
  }));
  $('mcSearch').addEventListener('input', () => { if (VIEW === 'US' || VIEW === 'KR' || VIEW === 'GL' || VIEW === 'COMM') renderCountry(VIEW, $('mcSearch').value); });
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
  $('mcInterval').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    $('mcInterval').querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on');
    candleInterval = b.dataset.i; renderDetail();
  }));
  $('mcChartType').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    $('mcChartType').querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on');
    detailType = b.dataset.t; renderDetail();
  }));

  fetch('/api/macro/overview').then(r => r.json()).then(d => {
    DATA = d;
    // ?view= 딥링크 (분석탭 → 한·미 비교/겹쳐보기 바로 열기)
    const want = (new URLSearchParams(location.search).get('view') || '').toUpperCase();
    const btn = want && want !== 'US' ? $('mcToggle').querySelector(`button[data-view="${want}"]`) : null;
    if (btn) btn.click();
    else renderCountry('US');
  }).catch(() => { $('mcBody').innerHTML = '<div class="mc-loading">불러오기 실패</div>'; });
})();
