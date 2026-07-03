// market.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 내용 무변경 이동
function _mkEsc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// ── 내 지수 (홈 위젯 설정 + 시세 재사용) ──
async function mkLoadIndices() {
  const grid = document.getElementById('mkIndexGrid');
  try {
    const cfg = await (await fetch('/api/home-config', { cache: 'no-store' })).json();
    const hint = document.getElementById('mkLoginHint');
    if (hint) hint.style.display = cfg.logged_in ? 'none' : 'block';
    const items = [];
    (cfg.widgets || []).forEach(w => (w.items || []).forEach(it => {
      const code = String(it.code).toUpperCase();
      if (!code.startsWith('PF:') && !items.some(x => x.code === code)) items.push({ code: code, name: it.name });
    }));
    if (!items.length) { grid.innerHTML = '<div class="mk-empty">표시할 지수가 없어요. 홈에서 시장 지수를 추가해 보세요.</div>'; return; }
    const codes = items.map(i => i.code);
    const qs = await (await fetch('/api/watchlist/quotes?codes=' + encodeURIComponent(codes.join(',')))).json();
    const qmap = Object.fromEntries((qs || []).map(q => [String(q.code).toUpperCase(), q]));
    grid.innerHTML = items.map(it => {
      const q = qmap[it.code];
      const up = q && q.up;
      return `<div class="mk-item" data-code="${_mkEsc(it.code)}">
        <div class="mk-item-name">${_mkEsc(it.name)}</div>
        <div class="mk-item-val">${q ? _mkEsc(q.value) : '—'}</div>
        <div class="mk-item-chg ${q ? (up ? 'up' : 'down') : ''}">${q ? (up ? '▲ ' : '▼ ') + _mkEsc(q.change) : '—'}</div>
      </div>`;
    }).join('');
    grid.querySelectorAll('.mk-item[data-code]').forEach(el =>
      el.addEventListener('click', () => { location.href = '/symbol/' + encodeURIComponent(el.dataset.code); }));
  } catch (e) { grid.innerHTML = '<div class="mk-empty">시세를 불러오지 못했어요.</div>'; }
}

// ── 핵심 거시지표 (카테고리별 헤드라인 1개) ──
function _mkFmtVal(v, unit) {
  if (v == null || isNaN(v)) return '—';
  const n = Math.abs(v) >= 100 ? v.toLocaleString(undefined, { maximumFractionDigits: 1 }) : v.toFixed(2);
  return n + (unit ? ' ' + unit : '');
}
async function mkLoadMacro() {
  const grid = document.getElementById('mkMacroGrid');
  try {
    const ov = await (await fetch('/api/macro/overview')).json();
    const picks = [];
    (ov.categories || []).forEach(c => { if (c.series && c.series.length) picks.push(c.series[0]); });
    if (!picks.length) { grid.innerHTML = '<div class="mk-empty">거시지표를 불러오지 못했어요.</div>'; return; }
    grid.innerHTML = picks.slice(0, 8).map(s => {
      const cp = s.change_pct;
      const up = cp != null && cp >= 0;
      const chg = cp == null ? '' : (up ? '▲ ' : '▼ ') + Math.abs(cp).toFixed(2) + '%';
      return `<div class="mk-item" data-code="${_mkEsc(s.code)}">
        <div class="mk-item-name">${_mkEsc(s.name_ko)}</div>
        <div class="mk-item-val">${_mkEsc(_mkFmtVal(s.last_val, s.unit))}</div>
        <div class="mk-item-chg ${cp == null ? '' : (up ? 'up' : 'down')}">${chg || '&nbsp;'}</div>
      </div>`;
    }).join('');
    grid.querySelectorAll('.mk-item[data-code]').forEach(el =>
      el.addEventListener('click', () => { location.href = '/macro'; }));
  } catch (e) { grid.innerHTML = '<div class="mk-empty">거시지표를 불러오지 못했어요.</div>'; }
}

document.getElementById('mkRefresh').addEventListener('click', async function () {
  this.classList.add('spinning'); this.disabled = true;
  await Promise.all([mkLoadIndices(), mkLoadMacro()]);
  setTimeout(() => { this.classList.remove('spinning'); this.disabled = false; }, 700);
});

mkLoadIndices();
mkLoadMacro();
