// alerts.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 데이터는 #page-data JSON
const MM_SYMBOLS = JSON.parse(document.getElementById('page-data').textContent).symbols;
const TYPE_LABEL = { daily_pct: '일간 변동률', target_price: '목표가', new_high: '신고가', new_low: '신저가', rebalance_band: '리밸런싱' };
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
(function(){
  const sel = $('alCode');
  if (MM_SYMBOLS.length) {
    sel.innerHTML = MM_SYMBOLS.map(s => `<option value="${mmEsc(s.code)}">${mmEsc(s.name)} (${mmEsc(s.code)})</option>`).join('');
  } else {
    sel.innerHTML = '<option value="" disabled selected>보유 종목 없음 — 검색으로 추가</option>';
  }
})();

// 종목 검색 → 선택 (검색결과 클릭 시 셀렉트에 옵션 추가+선택)
let _alSearchTimer = null;
function _alPickSymbol(code, name){
  const sel = $('alCode');
  let opt = Array.from(sel.options).find(o => o.value === code);
  if (!opt) { opt = new Option(`${name} (${code})`, code); sel.add(opt, 0); }
  sel.value = code;
  $('alSymResults').classList.remove('open');
  $('alSymSearch').value = '';
  syncForm();
}
$('alSymSearch').addEventListener('input', function(){
  const q = this.value.trim();
  clearTimeout(_alSearchTimer);
  const box = $('alSymResults');
  if (!q) { box.classList.remove('open'); return; }
  _alSearchTimer = setTimeout(async () => {
    try {
      const res = await (await fetch('/api/search?q=' + encodeURIComponent(q) + '&limit=8')).json();
      const items = Array.isArray(res) ? res : (res.items || []);
      if (!items.length) { box.innerHTML = '<div class="al-sr-item" style="color:var(--ds-muted);cursor:default;">결과 없음</div>'; box.classList.add('open'); return; }
      box.innerHTML = items.map(it =>
        `<div class="al-sr-item" data-code="${it.code}" data-name="${(it.name||'').replace(/"/g,'&quot;')}">
           <span>${it.name||it.code}</span><span class="al-sr-code">${it.code}</span></div>`).join('');
      box.classList.add('open');
      box.querySelectorAll('.al-sr-item[data-code]').forEach(el =>
        el.onclick = () => _alPickSymbol(el.dataset.code, el.dataset.name));
    } catch(e) { box.classList.remove('open'); }
  }, 220);
});
document.addEventListener('click', e => {
  if (!e.target.closest('#fSymSearch')) $('alSymResults').classList.remove('open');
});

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

function ruleDesc(r){
  if (r.rule_type === 'daily_pct') return `하루 ${({up:'+',down:'-',both:'±'})[r.direction]||'±'}${r.threshold}% 변동 시`;
  if (r.rule_type === 'target_price') return `가격 ${r.threshold} ${r.direction==='above'?'이상':'이하'} 도달 시`;
  if (r.rule_type === 'new_high') return `${r.window==='all'?'전체기간':'52주'} 신고가 갱신 시`;
  if (r.rule_type === 'new_low') return `${r.window==='all'?'전체기간':'52주'} 신저가 갱신 시`;
  if (r.rule_type === 'rebalance_band') return `목표 비중 ±${r.threshold}%p 이탈 시`;
  return '';
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
        <div class="al-item-t">${htmlEsc(r.code || '내 자산 그룹')}</div>
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
  const kEcon = $('caEcon'), kPol = $('caPolicy'), kEarn = $('caEarn'), kDiv = $('caDiv');
  const econWrap = $('caEconWrap'), symWrap = $('caSymWrap'), summary = $('caSummary');
  if (!enabled) return;
  const esc = window.mmEsc;  // E-1 공용화: 전역 mmEsc(base.html) 단일 구현 — 로컬 복붙 제거 (2026-07-03)
  function calSymbolEligible(code) {
    const c = String(code || '').toUpperCase();
    return !(c.startsWith('^') || c === 'KRX_GOLD' || c.endsWith('=X') || c.endsWith('=F') || c.includes('-'));
  }
  function collectSelectionParts() {
    const types = [];
    if (kEcon.checked) types.push('경제지표 ' + document.querySelectorAll('.ca-econ:checked').length + '개');
    if (kPol.checked) types.push('통화정책');
    if (kEarn.checked) types.push('실적 발표');
    if (kDiv.checked) types.push('배당락일');
    const sourceParts = [];
    if (kEarn.checked || kDiv.checked) {
      document.querySelectorAll('#caSymbols .ca-src-card').forEach(card => {
        const name = (card.querySelector('.ca-src-name')?.textContent || '').trim();
        const syms = [...card.querySelectorAll('.ca-sym:not(:disabled)')];
        const checked = syms.filter(s => s.checked).length;
        if (checked > 0) sourceParts.push(name + (checked === syms.length ? ' 전체' : ` ${checked}/${syms.length}`));
      });
    }
    return { types, sourceParts };
  }
  function currentCalendarView(configured) {
    const { types, sourceParts } = collectSelectionParts();
    const hasMacro = kEcon.checked || kPol.checked;
    const hasSymbol = kEarn.checked || kDiv.checked;
    let detail = enabled.checked
      ? `${types.length ? types.join(' · ') : '선택한 일정 종류 없음'} · 매일 08:00 KST, 오늘 일정이 있을 때`
      : '알림 꺼짐 · 저장된 선택은 유지됩니다.';
    if (enabled.checked && hasSymbol) {
      detail += sourceParts.length ? ` · 대상 ${sourceParts.join(', ')}` : ' · 종목 일정 대상 없음';
    }
    return {
      configured: !!configured,
      enabled: !!enabled.checked,
      title: hasMacro && hasSymbol ? '거시경제지표·증시 일정' : (hasMacro ? '거시경제지표' : '증시 일정'),
      detail,
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
    const { types, sourceParts } = collectSelectionParts();
    summary.classList.remove('off');
    summary.innerHTML = `<b>${prefix || '현재 선택'}</b> ${types.length ? types.join(' · ') : '선택한 일정 종류 없음'}`
      + `<br><span>${sourceParts.length ? '종목 일정 대상: ' + sourceParts.join(', ') : '종목 일정 대상 없음'} · 08:00 KST 실행 때 오늘 일정이 있을 때만 알림함에 생깁니다.</span>`;
  }
  function sync() {
    body.style.display = enabled.checked ? 'block' : 'none';
    econWrap.style.display = kEcon.checked ? 'block' : 'none';
    symWrap.style.display = (kEarn.checked || kDiv.checked) ? 'block' : 'none';
    renderSummary();
  }
  [enabled, kEcon, kPol, kEarn, kDiv].forEach(el => el.addEventListener('change', sync));

  (async function () {
    let r;
    try { r = await (await fetch('/api/alerts/calendar-prefs', { cache: 'no-store' })).json(); }
    catch (e) { return; }
    if (!r.logged_in) return;
    const p = r.prefs || {};
    enabled.checked = !!p.enabled;
    kEcon.checked = p.show_econ !== false; kPol.checked = p.show_policy !== false;
    kEarn.checked = p.show_earnings !== false; kDiv.checked = p.show_dividend !== false;
    const econIds = (p.econ_ids || []).map(String);
    const ids = new Set((p.show_econ !== false && !econIds.length)
      ? (r.available_econ || []).map(e => String(e.id))
      : econIds);
    $('caEconList').innerHTML = (r.available_econ || []).map(e =>
      `<label class="ca-chk"><input type="checkbox" class="ca-econ" value="${e.id}" ${ids.has(String(e.id)) ? 'checked' : ''}> ${esc(e.label)}</label>`).join('');
    const src = p.sources || {}, excl = new Set(p.excluded || []), sym = r.symbols || {},
          labels = r.group_labels || {}, order = r.group_order || [];
    let html = '';
    for (const g of order) {
      const items = sym[g] || [];
      if (!items.length) continue;
      const eligibleCount = items.filter(it => calSymbolEligible(it.code)).length;
      const countLabel = eligibleCount === items.length ? `(${items.length})` : `(${eligibleCount}/${items.length})`;
      // 포폴별 기본 접힘 — 종목 ~40행이 전부 펼쳐져 페이지를 압도하던 문제 (F-6 B5-2)
      html += `<div class="ca-src-card collapsed">
        <div class="ca-src-head">
        <label class="ca-chk" style="font-weight:700;border:none;background:none;padding:0;">
          <input type="checkbox" class="ca-src" data-g="${esc(g)}" ${src[g] !== false && eligibleCount ? 'checked' : ''} ${eligibleCount ? '' : 'disabled'}> <span class="ca-src-name">${esc(labels[g] || g)}</span> <span class="ca-src-count" style="color:var(--ds-muted);font-weight:400">${countLabel}</span></label>
        <button type="button" class="ca-src-toggle" aria-expanded="false">종목 보기 ▾</button>
        </div>
        <div class="ca-grid" style="margin-top:10px;">
          ${items.map(it => {
            const eligible = calSymbolEligible(it.code);
            const checked = eligible && !excl.has(it.code);
            return `<label class="ca-chk ${eligible ? '' : 'is-disabled'}" ${eligible ? '' : 'title="실적·배당락 일정이 없어 캘린더 알림에서는 자동 제외됩니다."'}><input type="checkbox" class="ca-sym" value="${esc(it.code)}" ${checked ? 'checked' : ''} ${eligible ? '' : 'disabled'}> ${esc(it.name)}${eligible ? '' : '<small class="ca-sym-muted">일정 없음</small>'}</label>`;
          }).join('')}
        </div></div>`;
    }
    $('caSymbols').innerHTML = html || '<div class="al-sub">대상 종목이 없어요. 내 자산·포트폴리오·관심목록에 종목을 추가하세요.</div>';
    document.querySelectorAll('.ca-econ').forEach(c => c.addEventListener('change', () => renderSummary()));
    function syncParent(card) {
      const src = card.querySelector('.ca-src');
      const syms = [...card.querySelectorAll('.ca-sym:not(:disabled)')];
      if (!src) return;
      if (!syms.length) {
        src.checked = false;
        src.indeterminate = false;
        return;
      }
      const checked = syms.filter(s => s.checked).length;
      src.checked = checked > 0;
      src.indeterminate = checked > 0 && checked < syms.length;
      const cnt = card.querySelector('.ca-src-count');
      if (cnt) cnt.textContent = `(${checked}/${syms.length} 선택)`;
    }
    document.querySelectorAll('#caSymbols .ca-src-card').forEach(card => {
      const src = card.querySelector('.ca-src');
      if (src) src.addEventListener('change', () => {
        card.querySelectorAll('.ca-sym:not(:disabled)').forEach(s => s.checked = src.checked);
        src.indeterminate = false;
        renderSummary();
      });
      card.querySelectorAll('.ca-sym:not(:disabled)').forEach(s => s.addEventListener('change', () => {
        syncParent(card);
        renderSummary();
      }));
      const tg = card.querySelector('.ca-src-toggle');
      if (tg) tg.addEventListener('click', () => {
        const open = card.classList.toggle('collapsed') === false;
        tg.textContent = open ? '접기 ▴' : '종목 보기 ▾';
        tg.setAttribute('aria-expanded', String(open));
      });
      syncParent(card);
    });
    sync();
    refreshCalendarRuleView(!!p.enabled || !!p.updated_at);
  })();

  async function saveCalendarPrefs() {
    const sources = {};
    document.querySelectorAll('.ca-src').forEach(s => sources[s.dataset.g] = s.checked);
    const excluded = [...document.querySelectorAll('.ca-sym:not(:checked):not(:disabled)')].map(s => s.value);
    const econ_ids = [...document.querySelectorAll('.ca-econ:checked')].map(c => +c.value);
    const payload = { enabled: enabled.checked, show_econ: kEcon.checked, show_policy: kPol.checked,
      show_earnings: kEarn.checked, show_dividend: kDiv.checked, econ_ids, sources, excluded };
    const st = $('caStatus'); st.textContent = '저장 중…';
    try {
      const res = await fetch('/api/alerts/calendar-prefs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      st.textContent = res.ok ? '저장됐어요. 알림 내역은 다음 08:00 KST 실행 때 오늘 일정이 있으면 생성됩니다.' : '저장 실패';
      st.style.color = res.ok ? 'var(--up)' : 'var(--down)';
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
