// 거시경제 지표 탭 (/macro)
(function () {
  let DATA = null;          // overview
  let VIEW = 'US';
  let detailChart = null, cmpChart = null;
  let curDetailCode = null;

  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  // 날짜 'YYYY-MM-DD' → 숫자(연 단위) : Chart.js 시간축 어댑터 없이 선형축 사용
  function dnum(d) {
    const [y, m, day] = d.split('-').map(Number);
    return y + (m - 1) / 12 + (day - 1) / 365;
  }

  function fmtVal(v, unit) {
    if (v == null) return '–';
    if (unit === '%' || unit === '%p') return v.toFixed(2);
    if (Math.abs(v) >= 1000) return Math.round(v).toLocaleString();
    if (Math.abs(v) >= 10) return v.toFixed(1);
    return v.toFixed(2);
  }

  function sparkSVG(arr) {
    if (!arr || arr.length < 2) return '';
    const w = 150, h = 30, pad = 2;
    const mn = Math.min(...arr), mx = Math.max(...arr), rng = (mx - mn) || 1;
    const pts = arr.map((v, i) => {
      const x = pad + (i / (arr.length - 1)) * (w - 2 * pad);
      const y = h - pad - ((v - mn) / rng) * (h - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const up = arr[arr.length - 1] >= arr[0];
    const col = up ? '#2E7D32' : '#C62828';
    return `<svg class="mc-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <polyline points="${pts}" style="stroke:${col}"></polyline></svg>`;
  }

  function cardHTML(s) {
    let chgCls = 'flat', chgTxt = '–';
    if (s.change != null) {
      const up = s.change > 0, dn = s.change < 0;
      chgCls = up ? 'up' : dn ? 'down' : 'flat';
      const arrow = up ? '▲' : dn ? '▼' : '–';
      const cp = (s.change_pct != null) ? ` (${s.change_pct > 0 ? '+' : ''}${s.change_pct.toFixed(2)}%)` : '';
      chgTxt = `${arrow} ${fmtVal(Math.abs(s.change), s.unit)}${cp}`;
    }
    const flag = s.country === 'US' ? '🇺🇸' : '🇰🇷';
    return `<div class="mc-card" data-code="${s.code}">
      <div class="flag">${flag} ${s.freq}</div>
      <div class="nm">${s.name_ko}</div>
      <div class="val">${fmtVal(s.last_val, s.unit)}<span class="unit">${s.unit}</span></div>
      <div class="chg ${chgCls}">${chgTxt}</div>
      ${sparkSVG(s.spark)}
      <div class="mc-date">${s.last_date} 기준</div>
    </div>`;
  }

  function renderCountry(country) {
    const cats = DATA.categories
      .map(c => ({ category: c.category, series: c.series.filter(s => s.country === country) }))
      .filter(c => c.series.length);
    let html = '';
    for (const c of cats) {
      html += `<div class="mc-cat"><div class="mc-cat-head"><span class="dot"></span>${c.category}</div>
        <div class="mc-grid">${c.series.map(cardHTML).join('')}</div></div>`;
    }
    $('mcBody').innerHTML = html || '<div class="mc-loading">데이터 없음</div>';
    $('mcBody').querySelectorAll('.mc-card').forEach(el =>
      el.addEventListener('click', () => openDetail(el.dataset.code)));
  }

  function renderCompare() {
    const pairs = DATA.compare_pairs;
    let html = `<div class="mc-cmp-pairs" id="mcCmpPairs">` +
      pairs.map((p, i) => `<button data-i="${i}" class="${i === 0 ? 'on' : ''}">${p.label}</button>`).join('') +
      `</div><div class="mc-cmp-card"><div class="mc-cmp-mode" id="mcCmpMode"></div>
       <div class="mc-chart-wrap"><canvas id="mcCmpChart"></canvas></div></div>`;
    $('mcBody').innerHTML = html;
    $('mcCmpPairs').querySelectorAll('button').forEach(b =>
      b.addEventListener('click', () => {
        $('mcCmpPairs').querySelectorAll('button').forEach(x => x.classList.remove('on'));
        b.classList.add('on');
        loadCompare(pairs[+b.dataset.i]);
      }));
    if (pairs.length) loadCompare(pairs[0]);
  }

  async function loadCompare(pair) {
    $('mcCmpMode').textContent = '불러오는 중…';
    const r = await fetch(`/api/macro/compare?us=${pair.us}&kr=${pair.kr}`);
    const d = await r.json();
    if (d.error) { $('mcCmpMode').textContent = '데이터 없음'; return; }
    $('mcCmpMode').textContent = d.mode === 'raw'
      ? `같은 단위(${d.unit}) — 원값 직접 비교`
      : `단위가 달라 시작점=100으로 정규화 — 추세 비교`;
    const ds = [
      lineDS(`🇺🇸 ${d.a.name_ko}`, d.a.points, '#1976D2'),
      lineDS(`🇰🇷 ${d.b.name_ko}`, d.b.points, '#E65100'),
    ];
    cmpChart = drawLine('mcCmpChart', cmpChart, ds, d.unit);
  }

  function lineDS(label, points, color) {
    return {
      label, data: points.map(p => ({ x: dnum(p[0]), y: p[1] })),
      borderColor: color, backgroundColor: color, borderWidth: 1.6,
      pointRadius: 0, tension: 0.1,
    };
  }

  function drawLine(canvasId, prev, datasets, unitLabel) {
    if (prev) prev.destroy();
    const ctx = $(canvasId).getContext('2d');
    const grid = css('--border') || '#e0e0e0';
    const txt = css('--text-muted') || '#888';
    return new Chart(ctx, {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: datasets.length > 1, labels: { color: txt, font: { size: 11 } } },
          tooltip: { callbacks: { title: (it) => fracToDate(it[0].parsed.x) } },
        },
        scales: {
          x: { type: 'linear', ticks: { color: txt, callback: (v) => Math.round(v), maxTicksLimit: 8 }, grid: { color: grid } },
          y: { ticks: { color: txt }, grid: { color: grid }, title: { display: !!unitLabel, text: unitLabel, color: txt } },
        },
      },
    });
  }

  function fracToDate(f) {
    const y = Math.floor(f);
    const m = Math.round((f - y) * 12) + 1;
    return `${y}-${String(Math.min(12, m)).padStart(2, '0')}`;
  }

  async function openDetail(code) {
    curDetailCode = code;
    $('mcModal').classList.add('open');
    $('mcModalTitle').textContent = '불러오는 중…';
    $('mcModalSub').textContent = '';
    $('mcModalDesc').style.display = 'none';
    const r = await fetch(`/api/macro/series/${code}`);
    const d = await r.json();
    if (d.error) { $('mcModalTitle').textContent = '데이터 없음'; return; }
    window._mcDetail = d;
    const flag = d.country === 'US' ? '🇺🇸 미국' : '🇰🇷 한국';
    $('mcModalTitle').textContent = d.name_ko;
    $('mcModalSub').textContent = `${flag} · 단위 ${d.unit} · ${d.points.length.toLocaleString()}개 관측 · 최근 ${d.points.at(-1)[0]}`;
    if (d.desc) { $('mcModalDesc').style.display = 'block'; $('mcModalDesc').textContent = d.desc; }
    $('mcPeriod').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.r === '1300'));
    drawDetail(1300);
  }

  function drawDetail(rangeN) {
    const d = window._mcDetail;
    let pts = d.points;
    if (rangeN && rangeN > 0) pts = pts.slice(-rangeN);
    detailChart = drawLine('mcDetailChart', detailChart, [lineDS(d.name_ko, pts, '#1976D2')], d.unit);
  }

  // 이벤트
  $('mcToggle').querySelectorAll('button').forEach(b =>
    b.addEventListener('click', () => {
      $('mcToggle').querySelectorAll('button').forEach(x => x.classList.remove('on'));
      b.classList.add('on');
      VIEW = b.dataset.view;
      if (VIEW === 'CMP') renderCompare(); else renderCountry(VIEW);
    }));
  $('mcModalX').addEventListener('click', () => $('mcModal').classList.remove('open'));
  $('mcModal').addEventListener('click', (e) => { if (e.target === $('mcModal')) $('mcModal').classList.remove('open'); });
  $('mcPeriod').querySelectorAll('button').forEach(b =>
    b.addEventListener('click', () => {
      $('mcPeriod').querySelectorAll('button').forEach(x => x.classList.remove('on'));
      b.classList.add('on');
      drawDetail(+b.dataset.r);
    }));

  // 초기 로드
  fetch('/api/macro/overview').then(r => r.json()).then(d => {
    DATA = d;
    renderCountry('US');
  }).catch(() => { $('mcBody').innerHTML = '<div class="mc-loading">불러오기 실패</div>'; });
})();
