// alerts.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 데이터는 #page-data JSON
const MM_SYMBOLS = JSON.parse(document.getElementById('page-data').textContent).symbols;
const TYPE_LABEL = { daily_pct: '일간 변동률', target_price: '목표가', new_high: '신고가', new_low: '신저가',
  rebalance_band: '리밸런싱', earnings: '실적 발표', dividend: '배당락일' };
const DIR_OPTS = {
  daily_pct:    [['up','상승'],['down','하락'],['both','양방향']],
  target_price: [['above','이상'],['below','이하']],
};
let LAST_ALERT_RULES = [];
let CAL_ALERT_VIEW = null;

function $(id){ return document.getElementById(id); }
function htmlEsc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }
function normalizeAlertTab(raw) {
  const v = String(raw || '').replace(/^#/, '').toLowerCase();
  if (['settings', 'setting', 'config'].includes(v)) return 'settings';
  if (['rules', 'mine', 'my', 'my-alerts'].includes(v)) return 'rules';
  if (['inbox', 'received', 'events'].includes(v)) return 'inbox';
  return 'settings';
}
function setAlertTab(tab, opts) {
  const next = normalizeAlertTab(tab);
  document.querySelectorAll('[data-alert-tab]').forEach(b => {
    const on = b.dataset.alertTab === next;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  document.querySelectorAll('[data-alert-panel]').forEach(p => {
    p.classList.toggle('active', p.dataset.alertPanel === next);
  });
  if (!opts || !opts.silent) {
    const url = new URL(location.href);
    url.hash = next;
    history.replaceState(null, '', url);
  }
  if (next === 'rules') loadRules();
  if (next === 'inbox') loadEvents();
}
document.querySelectorAll('[data-alert-tab]').forEach(b => {
  b.addEventListener('click', () => setAlertTab(b.dataset.alertTab));
});
window.addEventListener('hashchange', () => setAlertTab(location.hash, { silent: true }));
setAlertTab(new URLSearchParams(location.search).get('tab') || location.hash || 'settings', { silent: true });

// 종목 셀렉트 채우기 (보유/관심 종목 빠른선택)
function fillSymbolSelect(selId){
  const sel = $(selId);
  if (!sel) return;
  sel.innerHTML = MM_SYMBOLS.length
    ? MM_SYMBOLS.map(s => `<option value="${mmEsc(s.code)}">${mmEsc(s.name)} (${mmEsc(s.code)})</option>`).join('')
    : '<option value="" disabled selected>보유 종목 없음 — 검색으로 추가</option>';
}
fillSymbolSelect('alCode');
fillSymbolSelect('evCode');

// 종목 검색 → 선택 (검색결과 클릭 시 셀렉트에 옵션 추가+선택)
function wireSymbolSearch({ input, results, select, wrap, onPick }){
  const inp = $(input), box = $(results), sel = $(select);
  if (!inp || !box || !sel) return;
  let timer = null;
  function pick(code, name){
    let opt = Array.from(sel.options).find(o => o.value === code);
    if (!opt) { opt = new Option(`${name} (${code})`, code); sel.add(opt, 0); }
    sel.value = code;
    box.classList.remove('open');
    inp.value = '';
    if (onPick) onPick();
  }
  inp.addEventListener('input', function(){
    const q = this.value.trim();
    clearTimeout(timer);
    if (!q) { box.classList.remove('open'); return; }
    timer = setTimeout(async () => {
      try {
        const res = await (await fetch('/api/search?q=' + encodeURIComponent(q) + '&limit=8')).json();
        const items = Array.isArray(res) ? res : (res.items || []);
        if (!items.length) { box.innerHTML = '<div class="al-sr-item" style="color:var(--ds-muted);cursor:default;">결과 없음</div>'; box.classList.add('open'); return; }
        box.innerHTML = items.map(it =>
          `<div class="al-sr-item" data-code="${it.code}" data-name="${(it.name||'').replace(/"/g,'&quot;')}">
             <span>${it.name||it.code}</span><span class="al-sr-code">${it.code}</span></div>`).join('');
        box.classList.add('open');
        box.querySelectorAll('.al-sr-item[data-code]').forEach(el =>
          el.onclick = () => pick(el.dataset.code, el.dataset.name));
      } catch(e) { box.classList.remove('open'); }
    }, 220);
  });
  document.addEventListener('click', e => {
    if (!e.target.closest('#' + wrap)) box.classList.remove('open');
  });
}
wireSymbolSearch({ input: 'alSymSearch', results: 'alSymResults', select: 'alCode',
  wrap: 'fSymSearch', onPick: () => syncForm() });
wireSymbolSearch({ input: 'evSymSearch', results: 'evSymResults', select: 'evCode',
  wrap: 'fEvSearch' });

// 종목 알림 서브탭 (가격 / 실적·배당)
document.querySelectorAll('[data-sym-tab]').forEach(b => b.addEventListener('click', () => {
  const next = b.dataset.symTab;
  document.querySelectorAll('[data-sym-tab]').forEach(x => {
    const on = x.dataset.symTab === next;
    x.classList.toggle('active', on);
    x.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  document.querySelectorAll('[data-sym-panel]').forEach(p =>
    p.classList.toggle('active', p.dataset.symPanel === next));
}));

// 종목 알림 타입 = 칩 선택
let currentType = 'daily_pct';
const _chipBox = $('alTypeChips');
_chipBox.querySelectorAll('.al-chip').forEach(b => b.addEventListener('click', () => {
  _chipBox.querySelectorAll('.al-chip').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  currentType = b.dataset.type;
  syncForm();
}));

function syncForm(){
  const t = currentType;
  const isExtreme = (t === 'new_high' || t === 'new_low');
  $('fDir').style.display = (t === 'daily_pct' || t === 'target_price') ? '' : 'none';
  $('fWindow').style.display = isExtreme ? '' : 'none';
  $('fThreshold').style.display = isExtreme ? 'none' : '';
  if (t === 'daily_pct') { $('alThrLabel').textContent = '변동률 %'; $('alThr').placeholder = '5'; }
  else if (t === 'target_price') { $('alThrLabel').textContent = '목표가'; $('alThr').placeholder = '150'; }
  // 방향 옵션
  if (DIR_OPTS[t]) $('alDir').innerHTML = DIR_OPTS[t].map(([v,l]) => `<option value="${v}">${l}</option>`).join('');
}
syncForm();

async function createRule(){
  $('alErr').textContent = '';
  const t = currentType;
  const code = $('alCode').value;
  if (!code) { $('alErr').textContent = '종목을 선택하세요.'; return; }
  const body = { rule_type: t, code: code, cooldown_h: 24 };
  if (t === 'new_high' || t === 'new_low') {
    body.window = $('alWindow').value;
  } else {
    body.direction = $('alDir').value;
    body.threshold = parseFloat($('alThr').value);
  }
  const r = await fetch('/api/alerts/rules', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) { $('alErr').textContent = j.error || '추가 실패'; return; }
  await loadRules();
  setAlertTab('rules');
}
$('alCreate').addEventListener('click', createRule);

async function createRebalance(){
  $('alRebErr').textContent = '';
  const body = { rule_type: 'rebalance_band', threshold: parseFloat($('alBand').value), cooldown_h: 24 };
  const r = await fetch('/api/alerts/rules', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) { $('alRebErr').textContent = j.error || '추가 실패'; return; }
  await loadRules();
  setAlertTab('rules');
}
$('alRebCreate').addEventListener('click', createRebalance);

// ── 실적 · 배당 알림 (종목 일정 룰) ──
let currentEventType = 'dividend';
function syncEventForm(){
  const bySymbol = $('evScope').value === 'symbol';
  $('fEvSymbol').style.display = bySymbol ? '' : 'none';
  $('fEvSearch').style.display = bySymbol ? '' : 'none';
  $('fEvAmount').style.display = currentEventType === 'dividend' ? '' : 'none';
}
$('evTypeChips').querySelectorAll('.al-chip').forEach(b => b.addEventListener('click', () => {
  $('evTypeChips').querySelectorAll('.al-chip').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  currentEventType = b.dataset.etype;
  syncEventForm();
}));
$('evScope').addEventListener('change', syncEventForm);
syncEventForm();

async function createEventRule(){
  $('evErr').textContent = '';
  const bySymbol = $('evScope').value === 'symbol';
  const code = bySymbol ? $('evCode').value : '';
  if (bySymbol && !code) { $('evErr').textContent = '종목을 선택하세요.'; return; }
  const body = { rule_type: currentEventType, window: $('evWhen').value, cooldown_h: 24 };
  if (bySymbol) body.code = code;
  if (currentEventType === 'dividend' && $('evAmount').checked) body.with_amount = true;
  const r = await fetch('/api/alerts/rules', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) { $('evErr').textContent = j.error || '추가 실패'; return; }
  await loadRules();
  setAlertTab('rules');
}
$('evCreate').addEventListener('click', createEventRule);

function ruleDesc(r){
  if (r.rule_type === 'daily_pct') return `하루 ${({up:'+',down:'-',both:'±'})[r.direction]||'±'}${r.threshold}% 변동 시`;
  if (r.rule_type === 'target_price') return `가격 ${r.threshold} ${r.direction==='above'?'이상':'이하'} 도달 시`;
  if (r.rule_type === 'new_high') return `${r.window==='all'?'전체기간':'52주'} 신고가 갱신 시`;
  if (r.rule_type === 'new_low') return `${r.window==='all'?'전체기간':'52주'} 신저가 갱신 시`;
  if (r.rule_type === 'rebalance_band') return `목표 비중 ±${r.threshold}%p 이탈 시`;
  if (r.rule_type === 'earnings' || r.rule_type === 'dividend') {
    const when = r.window === 'd1' ? '하루 전 아침' : '당일 아침';
    const what = r.rule_type === 'earnings' ? '실적 발표일' : '배당락일';
    return `${what} ${when}` + (r.direction === 'amount' ? ' · 계좌별 예상 배당금 포함' : '');
  }
  return '';
}

function ruleTargetLabel(r){
  if (r.code) return r.code;
  return r.scope === 'holdings' ? '보유 종목 전체' : '내 자산 그룹';
}

async function loadRules(){
  let j;
  try {
    const r = await fetch('/api/alerts/rules');
    j = await r.json();
  } catch (e) {
    const box = $('alRules');
    if (box) box.innerHTML = '<div class="al-empty">일시적으로 불러오지 못했어요. 잠시 후 새로고침 해주세요.</div>';
    return;
  }
  LAST_ALERT_RULES = j.rules || [];
  renderRules();
}

function renderRules(){
  const rules = LAST_ALERT_RULES || [];
  const showCal = CAL_ALERT_VIEW && (CAL_ALERT_VIEW.configured || CAL_ALERT_VIEW.enabled);
  const total = rules.length + (showCal ? 1 : 0);
  $('alRuleCount').textContent = total ? `(${total}개)` : '';
  const box = $('alRules');
  if (!total) { box.innerHTML = '<div class="al-empty">아직 만든 알림이 없어요.</div>'; return; }
  const calHtml = showCal ? `
    <div class="al-item ${CAL_ALERT_VIEW.enabled ? '' : 'off'}">
      <span class="al-pill">거시경제지표</span>
      <div class="al-item-main">
        <div class="al-item-t">${htmlEsc(CAL_ALERT_VIEW.title)}</div>
        <div class="al-item-d">${htmlEsc(CAL_ALERT_VIEW.detail)}</div>
      </div>
      <button class="al-btn ghost al-cal-edit" data-cal-edit="1">수정</button>
      <button class="al-btn ghost al-toggle" data-cal-toggle="1" data-on="${CAL_ALERT_VIEW.enabled ? '1' : '0'}" style="padding:5px 10px;font-size:0.74rem;">${CAL_ALERT_VIEW.enabled ? '끄기' : '켜기'}</button>
    </div>` : '';
  const ruleHtml = rules.map(r => `
    <div class="al-item ${r.enabled ? '' : 'off'}">
      <span class="al-pill">${htmlEsc(TYPE_LABEL[r.rule_type]||r.rule_type)}</span>
      <div class="al-item-main">
        <div class="al-item-t">${htmlEsc(ruleTargetLabel(r))}</div>
        <div class="al-item-d">${htmlEsc(ruleDesc(r))}</div>
      </div>
      <button class="al-btn ghost al-toggle" data-id="${r.id}" data-on="${r.enabled}" style="padding:5px 10px;font-size:0.74rem;">${r.enabled?'끄기':'켜기'}</button>
      <button class="al-x" data-del="${r.id}" title="삭제">✕</button>
    </div>`).join('');
  box.innerHTML = calHtml + ruleHtml;
  box.querySelectorAll('.al-toggle[data-id]').forEach(b => b.onclick = async () => {
    await fetch(`/api/alerts/rules/${b.dataset.id}`, { method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({enabled: b.dataset.on !== '1'}) });
    loadRules();
  });
  box.querySelectorAll('[data-cal-toggle]').forEach(b => b.onclick = async () => {
    if (window.mmSaveCalendarAlerts) await window.mmSaveCalendarAlerts(b.dataset.on !== '1');
  });
  box.querySelectorAll('[data-cal-edit]').forEach(b => b.onclick = () => {
    if (window.mmFocusCalendarAlerts) window.mmFocusCalendarAlerts();
  });
  box.querySelectorAll('.al-x').forEach(b => b.onclick = async () => {
    await fetch(`/api/alerts/rules/${b.dataset.del}`, { method:'DELETE' });
    loadRules();
  });
}

function timeAgo(iso){
  const d = new Date(iso); const s = (Date.now()-d.getTime())/1000;
  if (s < 60) return '방금'; if (s < 3600) return Math.floor(s/60)+'분 전';
  if (s < 86400) return Math.floor(s/3600)+'시간 전'; return d.toLocaleDateString('ko-KR');
}

function alertTargetUrl(e) {
  const meta = e && e.meta && typeof e.meta === 'object' ? e.meta : {};
  const explicit = String(meta.target_url || meta.targetUrl || '');
  if (explicit.startsWith('/')) return explicit;
  if (e && e.code) return '/symbol/' + encodeURIComponent(e.code);
  if (meta.cal || meta.type === 'calendar') return '/calendar';
  if (meta.portfolio_id) return '/myportfolios/' + encodeURIComponent(meta.portfolio_id);
  if (meta.breaches || meta.rule_type === 'rebalance_band' || meta.type === 'rebalance_band') return '/myassets';
  return '';
}

async function loadEvents(){
  let j;
  try {
    const r = await fetch('/api/alerts/events?limit=50');
    j = await r.json();
  } catch (e) {
    const b = $('alEvents');
    if (b) b.innerHTML = '<div class="al-empty">일시적으로 불러오지 못했어요. 잠시 후 새로고침 해주세요.</div>';
    return;
  }
  const evs = j.events || [];
  const box = $('alEvents');
  if (!evs.length) { box.innerHTML = '<div class="al-empty">아직 받은 알림이 없어요. 캘린더 알림은 저장 직후 생기지 않고, 매일 08:00 KST에 오늘 일정이 있을 때 여기에 쌓입니다.</div>'; return; }
  box.innerHTML = evs.map(e => {
    const target = alertTargetUrl(e);
    return `
    <div class="al-ev ${e.read_at ? 'read' : ''} ${target ? 'al-ev-link' : ''}" data-id="${e.id}" data-target="${htmlEsc(target)}" tabindex="${target ? '0' : '-1'}">
      <div class="al-ev-t">${htmlEsc(e.title)}</div>
      <div class="al-ev-b">${htmlEsc(e.body)}</div>
      <div class="al-ev-time">${timeAgo(e.created_at)}</div>
    </div>`;
  }).join('');
  box.querySelectorAll('.al-ev[data-id]').forEach(el => {
    const openTarget = async () => {
      await fetch(`/api/alerts/events/${el.dataset.id}/read`, { method: 'POST' });
      el.classList.add('read');
      if (window.mmRefreshBell) window.mmRefreshBell();
      if (el.dataset.target) location.href = el.dataset.target;
    };
    el.addEventListener('click', openTarget);
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openTarget(); }
    });
  });
}
$('alReadAll').addEventListener('click', async () => {
  await fetch('/api/alerts/read-all', { method:'POST' });
  loadEvents();
  if (window.mmRefreshBell) window.mmRefreshBell();
});

loadRules();
loadEvents();

// ── 증시 캘린더 알림 ──
(function () {
  const enabled = $('caEnabled'), body = $('caBody');
  const kEcon = $('caEcon'), kPol = $('caPolicy');
  const econWrap = $('caEconWrap'), summary = $('caSummary');
  if (!enabled) return;
  const esc = window.mmEsc;  // E-1 공용화: 전역 mmEsc(base.html) 단일 구현 — 로컬 복붙 제거 (2026-07-03)
  function collectTypes() {
    const types = [];
    if (kEcon.checked) types.push('경제지표 ' + document.querySelectorAll('.ca-econ:checked').length + '개');
    if (kPol.checked) types.push('통화정책');
    return types;
  }
  function currentCalendarView(configured) {
    const types = collectTypes();
    return {
      configured: !!configured,
      enabled: !!enabled.checked,
      title: '거시경제지표',
      detail: enabled.checked
        ? `${types.length ? types.join(' · ') : '선택한 일정 종류 없음'} · 매일 08:00 KST, 오늘 일정이 있을 때`
        : '알림 꺼짐 · 저장된 선택은 유지됩니다.',
    };
  }
  function refreshCalendarRuleView(configured) {
    CAL_ALERT_VIEW = currentCalendarView(configured);
    renderRules();
  }
  function renderSummary(prefix) {
    if (!summary) return;
    if (!enabled.checked) {
      summary.classList.add('off');
      summary.innerHTML = '<b>알림 꺼짐</b> 저장해도 일정 알림은 발송되지 않습니다.';
      return;
    }
    const types = collectTypes();
    summary.classList.remove('off');
    summary.innerHTML = `<b>${prefix || '현재 선택'}</b> ${types.length ? types.join(' · ') : '선택한 일정 종류 없음'}`
      + '<br><span>08:00 KST 실행 때 오늘 일정이 있을 때만 알림함에 생깁니다.</span>';
  }
  function sync() {
    body.style.display = enabled.checked ? 'block' : 'none';
    econWrap.style.display = kEcon.checked ? 'block' : 'none';
    renderSummary();
  }
  [enabled, kEcon, kPol].forEach(el => el.addEventListener('change', sync));

  (async function () {
    let r;
    try { r = await (await fetch('/api/alerts/calendar-prefs', { cache: 'no-store' })).json(); }
    catch (e) { return; }
    if (!r.logged_in) return;
    const p = r.prefs || {};
    enabled.checked = !!p.enabled;
    kEcon.checked = p.show_econ !== false; kPol.checked = p.show_policy !== false;
    const econIds = (p.econ_ids || []).map(String);
    const ids = new Set((p.show_econ !== false && !econIds.length)
      ? (r.available_econ || []).map(e => String(e.id))
      : econIds);
    $('caEconList').innerHTML = (r.available_econ || []).map(e =>
      `<label class="ca-chk"><input type="checkbox" class="ca-econ" value="${e.id}" ${ids.has(String(e.id)) ? 'checked' : ''}> ${esc(e.label)}</label>`).join('');
    document.querySelectorAll('.ca-econ').forEach(c => c.addEventListener('change', () => renderSummary()));
    sync();
    refreshCalendarRuleView(!!p.enabled || !!p.updated_at);
  })();

  async function saveCalendarPrefs() {
    const econ_ids = [...document.querySelectorAll('.ca-econ:checked')].map(c => +c.value);
    const payload = { enabled: enabled.checked, show_econ: kEcon.checked,
      show_policy: kPol.checked, econ_ids };
    const st = $('caStatus'); st.textContent = '저장 중…';
    try {
      const res = await fetch('/api/alerts/calendar-prefs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      st.textContent = res.ok ? '저장됐어요. 알림 내역은 다음 08:00 KST 실행 때 오늘 일정이 있으면 생성됩니다.' : '저장 실패';
      st.style.color = res.ok ? 'var(--ok)' : 'var(--danger)';
      if (res.ok) {
        renderSummary('저장됨');
        refreshCalendarRuleView(true);
      }
      return res.ok;
    } catch (e) {
      st.textContent = '저장 실패';
      return false;
    }
  }
  $('caSave').addEventListener('click', saveCalendarPrefs);
  window.mmSaveCalendarAlerts = async function (nextEnabled) {
    if (typeof nextEnabled === 'boolean') {
      enabled.checked = nextEnabled;
      sync();
    }
    return saveCalendarPrefs();
  };
  window.mmFocusCalendarAlerts = function () {
    setAlertTab('settings');
    requestAnimationFrame(() => {
      document.getElementById('calendarAlertCard')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      enabled.focus({ preventScroll: true });
    });
  };
})();
