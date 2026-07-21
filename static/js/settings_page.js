// settings.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 내용 무변경 이동
// ── 회원 탈퇴 ──
function openDeleteModal()  { document.getElementById('deleteModal').style.display = 'flex'; }
function closeDeleteModal() { document.getElementById('deleteModal').style.display = 'none'; }
async function confirmDelete() {
  const btn = document.getElementById('deleteConfirmBtn');
  btn.disabled = true; btn.textContent = '삭제 중…';
  try {
    const r = await fetch('/account/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    const j = await r.json();
    if (j.ok) { location.href = '/'; }
    else { btn.disabled = false; btn.textContent = '탈퇴하기'; }
  } catch (e) { btn.disabled = false; btn.textContent = '탈퇴하기'; }
}

// ── 푸시 알림 권한 토글(선택 동의 철회 가능) ──
(function initPushToggle() {
  const t = document.getElementById('pushToggle');
  if (!t) return;   // 비로그인 = 토글 없음
  const hint = document.getElementById('pushHint');
  const isApp = !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
  const baseHint = isApp
    ? '기본값은 꺼짐입니다. 동의해야만 알림을 받을 수 있고, 언제든 다시 끌 수 있어요.'
    : '푸시 알림은 앱에서 켤 수 있어요. (웹은 화면이 열려 있을 때만 알림이 표시돼요)';
  if (hint) hint.textContent = baseHint;

  // 토글 = 서버 동의 AND 기기 알림 권한. 재설치하면 서버 동의는 남아 있어도
  // OS 권한은 초기화된다 — 그때 토글이 켜진 채로 보이면 켤 방법이 없어진다.
  // 권한이 없으면 꺼진 상태로 보여주고, 켜는 순간 OS 권한 요청을 띄운다.
  (async () => {
    let enabled = false;
    try { enabled = !!(await (await fetch('/api/push/status')).json()).enabled; } catch (e) {}
    const perm = await window.mmPushPermission();
    if (isApp && enabled && perm !== 'granted') {
      enabled = false;
      if (hint) hint.textContent = perm === 'denied'
        ? '기기에서 이 앱의 알림이 꺼져 있어요. 휴대폰 설정 › 앱 › Money Milestone › 알림에서 허용해 주세요.'
        : '기기 알림 권한이 아직 없어요. 켜면 권한을 요청할게요.';
    }
    t.checked = enabled;
  })();

  t.addEventListener('change', async () => {
    if (t.checked) {
      if (!isApp) { t.checked = false; mmToast('푸시 알림은 앱에서 켤 수 있어요.'); return; }
      const ok = await window.mmInitPush(true);
      if (ok) {
        if (hint) hint.textContent = baseHint;
        mmToast('알림을 켰어요.', 'ok');
      } else {
        t.checked = false;
        const perm = await window.mmPushPermission();
        if (hint && perm === 'denied') hint.textContent = '기기에서 이 앱의 알림이 꺼져 있어요. 휴대폰 설정 › 앱 › Money Milestone › 알림에서 허용해 주세요.';
        mmToast('알림 권한이 필요해요. 휴대폰 설정 › 앱 › 알림에서 허용해 주세요.', 'err');
      }
    } else {
      try { await fetch('/api/push/disable', { method: 'POST' }); } catch (e) {}
      mmToast('알림을 껐어요.');
    }
  });
})();

// ── 설정 카테고리 패널 전환 ──
function setPanel(name) {
  document.querySelectorAll('.set-nav-btn').forEach(b => b.classList.toggle('active', b.dataset.spanel === name));
  document.querySelectorAll('.set-panel').forEach(p => p.classList.toggle('active', p.dataset.spanel === name));
  if (history.replaceState) history.replaceState(null, '', '#' + name);
}
// 진입 시 URL 해시로 패널 결정 (#tax/#home/#cal/#account) — 각 탭에서 맞는 설정으로 바로 진입
(function () {
  var h = (location.hash || '').replace('#', '');
  if (['tax', 'home', 'cal', 'account'].indexOf(h) >= 0) setPanel(h);
})();

// ── 세금 설정 (설정에 편입 — 구 /tax-settings 이식) ──
const TAX_STORAGE_KEY = 'domino_tax_settings';
function taxFmtKRW(v) {
  if (v == null || isNaN(v)) return '—';
  const abs = Math.abs(v), uk = Math.floor(abs/1e8), man = Math.floor((abs%1e8)/1e4);
  if (uk>0 && man>0) return '₩'+uk.toLocaleString()+'억 '+man.toLocaleString()+'만';
  if (uk>0) return '₩'+uk.toLocaleString()+'억';
  if (abs>=1e4) return '₩'+Math.floor(abs/1e4).toLocaleString()+'만';
  return '₩'+Math.round(abs).toLocaleString();
}
async function saveTaxSettings() {
  const settings = {
    earned_income: parseFloat(document.getElementById('earnedIncome').value) || 0,
    age:           parseInt(document.getElementById('userAge').value) || 40,
    pension_age:   parseInt(document.getElementById('pensionAge').value) || 65,
    isa_type:      document.querySelector('input[name="isaType"]:checked')?.value || 'none',
  };
  localStorage.setItem(TAX_STORAGE_KEY, JSON.stringify(settings));
  const st = document.getElementById('taxStatus');
  try {
    const me = await fetch('/api/me').then(r=>r.json());
    if (me.logged_in) await fetch('/api/settings/tax', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(settings) });
  } catch(e) {}
  if (st) { st.textContent = '저장됐어요.'; st.className = 'we-status ok'; setTimeout(()=>{ st.textContent=''; }, 2500); }
}
function taxApply(s) {
  if (s.earned_income != null) document.getElementById('earnedIncome').value = s.earned_income;
  if (s.age) document.getElementById('userAge').value = s.age;
  if (s.pension_age) document.getElementById('pensionAge').value = s.pension_age;
  const radio = document.querySelector(`input[name="isaType"][value="${s.isa_type||'none'}"]`); if (radio) radio.checked = true;
  document.getElementById('earnedIncomeHint').textContent = s.earned_income ? taxFmtKRW(s.earned_income) : '';
}
(async function loadTaxSettings() {
  if (!document.getElementById('earnedIncome')) return;  // 비로그인=세금 폼 게이트, 스킵
  let s = null;
  try { const me = await fetch('/api/me').then(r=>r.json()); if (me.logged_in) { const r = await fetch('/api/settings/tax'); if (r.ok) { const d = await r.json(); if (d && Object.keys(d).length) s = d; } } } catch(e) {}
  if (!s) { try { s = JSON.parse(localStorage.getItem(TAX_STORAGE_KEY) || 'null'); } catch(e) {} }
  if (s) taxApply(s);
  const ei = document.getElementById('earnedIncome');
  if (ei) ei.addEventListener('input', function(){ document.getElementById('earnedIncomeHint').textContent = taxFmtKRW(parseFloat(this.value)||0); });
})();

let _weWidgets = [];
let _weTarget = -1;
let _weSearchTimer = null;
let _wePortfolios = [];   // 내 저장 포트폴리오 (위젯에 종목처럼 추가용)

const WE_PRESETS = [
  { code: '^GSPC', name: 'S&P 500' },
  { code: '^IXIC', name: 'NASDAQ' },
  { code: '^KS11', name: '코스피' },
  { code: 'GC=F', name: '금 (국제)' },
  { code: 'KRX_GOLD', name: '금 (KRX)' },
  { code: 'KRW=X', name: '환율 (USD/KRW)' },
];

function weEsc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

document.addEventListener('DOMContentLoaded', async () => {
  let cfg;
  try { cfg = await (await fetch('/api/home-config', { cache: 'no-store' })).json(); }
  catch (e) { cfg = { widgets: [], logged_in: false }; }
  _weWidgets = JSON.parse(JSON.stringify(cfg.widgets || []));
  if (!cfg.logged_in) {
    document.getElementById('loginGate').style.display = 'block';
    return;
  }
  document.getElementById('widgetEditor').style.display = 'block';
  try { _wePortfolios = await (await fetch('/api/portfolio/list')).json(); }
  catch (e) { _wePortfolios = []; }
  weRender();

  const si = document.getElementById('weSearch');
  si.addEventListener('input', () => {
    clearTimeout(_weSearchTimer);
    _weSearchTimer = setTimeout(() => weDoSearch(si.value.trim()), 250);
  });
});

function weRender() {
  const list = document.getElementById('weList');
  list.innerHTML = _weWidgets.map((w, i) => `
    <div class="we-widget">
      <div class="we-widget-head">
        <input class="we-name-input" value="${weEsc(w.name)}" maxlength="20"
               oninput="weRename(${i}, this.value)">
        <button class="we-iconbtn" onclick="weMove(${i},-1)" ${i === 0 ? 'disabled' : ''} title="위로">▲</button>
        <button class="we-iconbtn" onclick="weMove(${i},1)" ${i === _weWidgets.length - 1 ? 'disabled' : ''} title="아래로">▼</button>
        <button class="we-iconbtn we-del" onclick="weRemoveWidget(${i})" ${_weWidgets.length <= 1 ? 'disabled' : ''} title="삭제">✕</button>
      </div>
      <div class="we-items">
        ${(w.items || []).length ? (w.items || []).map((it, j) => `
          <div class="we-item-row">
            <span class="we-item-name">${weEsc(it.name)}</span>
            <span class="we-item-code">${weEsc(it.code)}</span>
            <button class="we-item-x" onclick="weRemoveItem(${i},${j})" title="삭제">✕</button>
          </div>`).join('') : '<div class="we-item-empty">아직 종목이 없어요. 아래에서 추가하세요.</div>'}
      </div>
      <button class="we-add-item" onclick="weOpenModal(${i})">+ 종목 추가</button>
    </div>`).join('');
}

function weRename(i, v) { _weWidgets[i].name = v; }
function weMove(i, dir) {
  const j = i + dir;
  if (j < 0 || j >= _weWidgets.length) return;
  [_weWidgets[i], _weWidgets[j]] = [_weWidgets[j], _weWidgets[i]];
  weRender();
}
function weRemoveWidget(i) {
  if (_weWidgets.length <= 1) return;
  _weWidgets.splice(i, 1);
  weRender();
}
function weRemoveItem(wi, ii) {
  _weWidgets[wi].items.splice(ii, 1);
  weRender();
}
function weAddWidget() {
  if (_weWidgets.length >= 10) { weSetStatus('위젯은 최대 10개예요.', false); return; }
  _weWidgets.push({ key: 'w_' + Date.now(), name: '관심목록' + _weWidgets.length, items: [] });
  weRender();
}

function weOpenModal(wi) {
  _weTarget = wi;
  document.getElementById('weModal').classList.add('open');
  const si = document.getElementById('weSearch');
  si.value = '';
  document.getElementById('weResults').innerHTML = '';
  const pfChips = _wePortfolios.length
    ? `<div style="width:100%;font-size:0.72rem;color:var(--text-muted);font-weight:700;margin:4px 0 2px;">📊 내 포트폴리오 (수익 추종)</div>`
      + _wePortfolios.map(p => `<button class="we-preset" onclick="weAddItem('PF:${p.id}','${weEsc(p.name)}')">⭐ ${weEsc(p.name)}</button>`).join('')
      + `<div style="width:100%;height:1px;background:var(--border);margin:8px 0;"></div>`
      + `<div style="width:100%;font-size:0.72rem;color:var(--text-muted);font-weight:700;margin-bottom:2px;">시장 지수</div>`
    : '';
  document.getElementById('wePresets').innerHTML = pfChips +
    WE_PRESETS.map(p => `<button class="we-preset" onclick="weAddItem('${weEsc(p.code)}','${weEsc(p.name)}')">${weEsc(p.name)}</button>`).join('');
  setTimeout(() => si.focus(), 50);
}
function weCloseModal() { document.getElementById('weModal').classList.remove('open'); _weTarget = -1; }

async function weDoSearch(q) {
  const box = document.getElementById('weResults');
  if (!q) { box.innerHTML = ''; return; }
  let results = [];
  try { results = await (await fetch('/api/search?q=' + encodeURIComponent(q))).json(); }
  catch (e) { results = []; }
  box.innerHTML = results.map(r => `
    <div class="we-result" onclick="weAddItem('${weEsc(r.code)}','${weEsc(String(r.name).replace(/'/g, ''))}')">
      <div>
        <div class="we-result-name">${weEsc(r.name)}</div>
        <div class="we-result-code">${weEsc(r.code)}</div>
      </div>
      ${r.badge ? `<span class="we-result-badge">${weEsc(r.badge)}</span>` : ''}
    </div>`).join('') || '<div class="we-result" style="cursor:default;color:var(--text-muted)">결과 없음</div>';
}

function weAddItem(code, name) {
  if (_weTarget < 0) return;
  const items = _weWidgets[_weTarget].items;
  if (items.length >= 30) { weSetStatus('위젯당 종목은 최대 30개예요.', false); return; }
  if (items.some(it => String(it.code).toUpperCase() === String(code).toUpperCase())) return;
  items.push({ code: code, name: name || code });
  weRender();
}

function weSetStatus(msg, ok) {
  const el = document.getElementById('weStatus');
  el.textContent = msg;
  el.className = 'we-status ' + (ok ? 'ok' : 'err');
}

async function weSave() {
  const btn = document.getElementById('weSaveBtn');
  btn.disabled = true;
  weSetStatus('저장 중...', true);
  try {
    const res = await fetch('/api/home-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ widgets: _weWidgets }),
    });
    const j = await res.json();
    if (res.ok) weSetStatus('저장됐어요. 홈 화면에 반영됩니다.', true);
    else weSetStatus(j.error || '저장 실패', false);
  } catch (e) {
    weSetStatus('네트워크 오류', false);
  }
  btn.disabled = false;
}

// 캘린더 설정
function calEsc(s) { return String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }
(async () => {
  let r;
  try { r = await (await fetch('/api/calendar/config', { cache: 'no-store' })).json(); }
  catch (e) { return; }
  if (!r.logged_in) { document.getElementById('calLoginGate').style.display = 'block'; return; }
  document.getElementById('calEditor').style.display = 'block';
  const cfg = r.config || {};
  const enabled = new Set(cfg.econ || []);
  document.getElementById('calEconList').innerHTML = (r.available_econ || []).map(e =>
    `<label class="set-chk"><input type="checkbox" class="cal-econ" value="${e.id}" ${enabled.has(e.id) ? 'checked' : ''}> ${e.label}</label>`).join('');
  document.getElementById('calShowEarn').checked = cfg.show_earnings !== false;
  document.getElementById('calShowDiv').checked = cfg.show_dividend !== false;
  // 소스/개별 종목 — 내 자산·관심목록 + 저장 포트폴리오 각각 별도 그룹
  const src = cfg.sources || {}, excl = new Set(cfg.excluded || []), sym = r.symbols || {};
  const labels = r.group_labels || {}, order = r.group_order || Object.keys(sym);
  let html = '';
  for (const g of order) {
    const items = sym[g] || [];
    if (!items.length) continue;
    const label = labels[g] || g;
    html += `<div class="set-src-card">
      <label class="set-chk" style="font-weight:700;background:transparent;border:none;padding:0;">
        <input type="checkbox" class="cal-src" data-g="${calEsc(g)}" ${src[g] !== false ? 'checked' : ''}> ${calEsc(label)} <span style="color:var(--ds-muted);font-weight:400">(${items.length})</span></label>
      <div class="set-chk-grid" style="grid-template-columns:repeat(auto-fill,minmax(150px,1fr));margin-top:10px;">
        ${items.map(it => `<label class="set-chk"><input type="checkbox" class="cal-sym" value="${calEsc(it.code)}" ${excl.has(it.code) ? '' : 'checked'}> ${calEsc(it.name)}</label>`).join('')}
      </div></div>`;
  }
  document.getElementById('calSymbols').innerHTML = html || '<div class="settings-hint">표시할 종목이 없어요. 내 자산·포트폴리오·관심목록에 종목을 추가하세요.</div>';

  // 상위(소스) 체크 ↔ 하위(종목) 동기
  function calSyncParent(card) {
    const src = card.querySelector('.cal-src');
    const syms = [...card.querySelectorAll('.cal-sym')];
    if (!src || !syms.length) return;
    const checked = syms.filter(s => s.checked).length;
    src.checked = checked > 0;
    src.indeterminate = checked > 0 && checked < syms.length;
  }
  document.querySelectorAll('#calSymbols .set-src-card').forEach(card => {
    const src = card.querySelector('.cal-src');
    if (src) src.addEventListener('change', () => {
      card.querySelectorAll('.cal-sym').forEach(s => s.checked = src.checked);
      src.indeterminate = false;
    });
    card.querySelectorAll('.cal-sym').forEach(s => s.addEventListener('change', () => calSyncParent(card)));
    calSyncParent(card);   // 초기 상태
  });
})();

async function calSave() {
  const econ = [...document.querySelectorAll('.cal-econ:checked')].map(c => +c.value);
  const sources = {};
  document.querySelectorAll('.cal-src').forEach(c => { sources[c.dataset.g] = c.checked; });
  const excluded = [...document.querySelectorAll('.cal-sym:not(:checked)')].map(c => c.value);
  const body = { econ, sources, excluded,
    show_earnings: document.getElementById('calShowEarn').checked,
    show_dividend: document.getElementById('calShowDiv').checked };
  const st = document.getElementById('calStatus');
  st.textContent = '저장 중…';
  try {
    const res = await fetch('/api/calendar/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    st.textContent = res.ok ? '저장됐어요. 캘린더에 반영됩니다.' : '저장 실패';
    st.style.color = res.ok ? 'var(--green, #2E7D32)' : 'var(--red, #C62828)';
  } catch (e) { st.textContent = '저장 실패'; }
}
