// myassets.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 내용 무변경 이동
let holdings = [];
let groups   = [];
let prices   = {};
let prevClose = {};
let manualCodes = [];
let weightChart = null;
let hideAmounts = true;
let _metricMode = 'today';      // 히어로(전체 자산): 'today' | 'period'
let _rowMetric  = 'total';      // 보유 종목 행: 'today'(오늘±) | 'total'(평단 전체수익률)
let _maPeriodLabel = '1개월';

// JS 렌더용 아이콘 (Jinja 매크로는 JS에서 못 써 별도 정의 — duotone 결 동일)
const _SS = 'class="bic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"';
const MAICON = {
  pencil: `<svg ${_SS}><path d="M4 20h4L18 10l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/></svg>`,
  trash:  `<svg ${_SS}><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13h10l1-13"/></svg>`,
  undo:   `<svg ${_SS}><path d="M9 7 4 12l5 5M4 12h11a5 5 0 0 1 0 10"/></svg>`,
  scale:  `<svg ${_SS}><path d="M12 3v18M7 21h10M5 7h14M5 7 2.5 13a3 3 0 0 0 5 0zM19 7l-2.5 6a3 3 0 0 0 5 0z"/></svg>`,
  layers: `<svg ${_SS}><path d="m12 3 9 5-9 5-9-5zM3 13l9 5 9-5M3 17l9 5 9-5"/></svg>`,
  alert:  `<svg ${_SS}><path d="M12 3 2 20h20zM12 10v4M12 17.5h.01"/></svg>`,
  check:  `<svg ${_SS}><path d="M20 6 9 17l-5-5"/></svg>`,
  chev:   `<svg ${_SS} style="width:16px;height:16px;"><path d="m6 9 6 6 6-6"/></svg>`,
};
function _cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

function fmtKRW(v) {
  if (hideAmounts) return '***,***,***원';
  if (!v && v !== 0) return '—';
  return (v < 0 ? '-' : '') + '₩' + Math.abs(Math.round(v)).toLocaleString();
}
function fmtPrice(v) {
  // 시세(공개 정보)라 금액 숨김 대상 아님
  if (!v && v !== 0) return '—';
  return '₩' + Math.abs(Math.round(v)).toLocaleString();
}
function fmtPct(v) { return (v*100).toFixed(1)+'%'; }
function fmtSignedPct(v) { return (v>=0?'+':'')+(v*100).toFixed(2)+'%'; }
function fmtSignedKRW(v) {
  if (hideAmounts) return '***';
  return (v>=0?'+':'-')+'₩'+Math.abs(Math.round(v)).toLocaleString();
}
function _holdDays(d) {
  if (!d) return null;
  const t = Date.parse(d);
  if (isNaN(t)) return null;
  return Math.max(0, Math.floor((Date.now() - t) / 86400000));
}
function updateAssetHeroTotal(value) {
  const el = document.getElementById('maTotalAssetValue');
  if (el) el.textContent = fmtKRW(value || 0);
}

// 오늘± 총액(현재가 vs 직전 거래일 종가, KRW). 수동가격 종목 제외.
function _todayChange() {
  let cur = 0, prev = 0, ok = false;
  holdings.forEach(h => {
    if (manualCodes.includes(h.code)) return;
    const c = prices[h.code], p = prevClose[h.code];
    if (c == null || p == null) return;
    cur += c * h.quantity; prev += p * h.quantity; ok = true;
  });
  if (!ok || !prev) return null;
  return { diff: cur - prev, pct: (cur - prev) / prev };
}

// 히어로 하단 메트릭 1개만 표시 — 토글(_metricMode)에 따라 오늘 또는 기간.
// values = 현재 선택 기간으로 자른 자산추이 윈도우(기간 모드일 때).
let _lastHistWindow = null;
function updateHeroMetric(values) {
  if (values) _lastHistWindow = values;
  const el = document.getElementById('maHeroChange');
  if (!el) return;
  let lab, diff, pct;
  if (_metricMode === 'today') {
    const t = _todayChange();
    if (!t) { el.innerHTML = ''; el.className = 'ma-asset-change'; return; }
    lab = '오늘'; diff = t.diff; pct = t.pct;
  } else {
    const v = _lastHistWindow;
    if (!v || v.length < 2 || !v[0]) { el.innerHTML = ''; el.className = 'ma-asset-change'; return; }
    lab = _maPeriodLabel; diff = v[v.length - 1] - v[0]; pct = diff / v[0];
  }
  el.innerHTML = `<span class="lab">${lab}</span>${fmtSignedKRW(diff)} (${fmtSignedPct(pct)})`;
  el.className = 'ma-asset-change ' + (pct >= 0 ? 'up' : 'down');
}

// 히어로(전체 자산) 토글 — 자산 메트릭만 (행 미관여)
function setMetricMode(mode, btn) {
  _metricMode = mode;
  document.querySelectorAll('#maAssetHero .mt-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById('maPeriodChips').style.display = (mode === 'period') ? 'flex' : 'none';
  updateHeroMetric();
  renderPerStock();
}

// 보유 종목 토글 — 행 수익 표시만 (오늘± ↔ 평단 전체수익률)
function setRowMetric(mode, btn) {
  _rowMetric = mode;
  document.querySelectorAll('#holdMetricToggle .mt-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderHoldings();
}

// ── 탭 ──
function showTab(name) {
  // 모바일에서는 6탭 컨트롤러로 위임 (데스크톱 4탭 → 모바일 탭 매핑)
  if (_isMobile()) { mShowTab(_DESK2M[name] || 'overview'); return; }
  ['overview','rebalance','purchase','groups'].forEach(t => {
    document.getElementById('tab-'+t).style.display = t===name ? 'block' : 'none';
  });
  document.querySelectorAll('.ma-tab').forEach((b,i) => {
    b.classList.toggle('active', ['overview','rebalance','purchase','groups'][i]===name);
  });
  if (name === 'rebalance') renderRebalance();
  if (name === 'purchase')  calcPurchase();
  if (name === 'groups')    renderGroups();
}

// ── 모바일 전용 6탭 (≤768px). 카드 단위 인라인 display 제어, 데스크톱 DOM·showTab 보존 ──
let _psHasData = false;
let _mReady = false;  // 차트 인스턴스 준비 후 true (숨김탭 차트는 보일 때 resize 필요)
const _DESK2M = { overview:'overview', rebalance:'rebal', purchase:'rebal', groups:'groups' };
function _isMobile() { return window.matchMedia('(max-width: 768px)').matches; }
// 알림 설정: 모바일은 전용 알림 페이지로 이동(바텀시트 부실 → 풀페이지), 데스크톱은 모달
function openAlertSettings() {
  if (_isMobile()) { window.location.href = '/alerts'; return; }
  if (window.mmAlert) mmAlert.openAssets();
}
function _mActive() { const b = document.querySelector('.ma-mtab.active'); return b ? b.dataset.mtab : 'overview'; }
function mShowTab(name) {
  if (!_isMobile()) {
    // 데스크톱: 모바일 인라인 잔재 제거 → 데스크톱 기본(현황 탭)으로 환원
    ['rebalance','purchase','groups'].forEach(t => document.getElementById('tab-'+t).style.display = 'none');
    document.getElementById('tab-overview').style.display = '';
    document.querySelectorAll('#tab-overview [data-mtab]').forEach(el => {
      if (el.id !== 'perStockCard') el.style.display = '';
    });
    document.getElementById('perStockCard').style.display = _psHasData ? '' : 'none';
    document.querySelectorAll('.ma-tab').forEach((b,i) => b.classList.toggle('active', i === 0));
    return;
  }
  document.querySelectorAll('.ma-mtab').forEach(b => b.classList.toggle('active', b.dataset.mtab === name));
  document.querySelectorAll('[data-mtab]:not(.ma-mtab)').forEach(el => {
    const active = el.dataset.mtab === name;
    if (el.id === 'perStockCard') { el.style.display = (active && _psHasData) ? '' : 'none'; return; }
    el.style.display = active ? '' : 'none';
  });
  // 숨김 상태에서 그려진 차트는 캔버스 크기가 0 → 탭이 보일 때 재렌더(재생성)
  if (_mReady) {
    if (name === 'weight')   renderSummary();
    if (name === 'dividend') renderDivYear();
    if (name === 'overview' && _maHistoryChart) _maHistoryChart.resize();
  }
  if (name === 'rebal')  { renderRebalance(); calcPurchase(); }
  if (name === 'groups') renderGroups();
}
mShowTab('overview');  // 초기 분류
window.addEventListener('resize', () => mShowTab(_isMobile() ? _mActive() : 'overview'));

// ── 데이터 로드 ──
async function loadAll() {
  let res, data;
  try {
    res  = await fetch('/api/myassets/data', { cache: 'no-store' });
    // 5xx가 JSON 본문을 갖고 오는 경우가 있다. status를 안 보면 보유내역이
    // 통째로 비어 "자산 0원"으로 렌더된다 (2026-07-21 장애).
    if (!res.ok) throw new Error('HTTP ' + res.status);
    data = await res.json();
    if (data.error) throw new Error(data.error);
  } catch (e) {
    // 네트워크/서버 실패 — 빈 화면 대신 안내 (F-1 3-상태 감사 2026-07-03)
    const wrap = document.getElementById('holdingsTableWrap');
    if (wrap) wrap.innerHTML = '<div style="text-align:center;padding:30px;color:var(--text-muted);">일시적으로 불러오지 못했어요. 잠시 후 새로고침 해주세요.</div>';
    return;
  }
  holdings    = data.holdings || [];
  groups      = data.groups   || [];
  prices      = data.prices   || {};
  prevClose   = data.prev_close || {};
  manualCodes = data.manual_codes || [];
  if (data.rebal_band) syncRebalBand(parseFloat(data.rebal_band));
  hideAmounts = data.hide_amounts !== false;
  const toggle = document.getElementById('hideAmountToggle');
  if (toggle) toggle.checked = hideAmounts;
  _syncHideLabel();
  renderHoldings();
  renderSummary();
  updateHeroMetric();
  renderGroupOptions();
  renderPerStock();
}

// ── 종목별 손익 (히어로 오늘/기간 토글 + 기간칩 연동) ──
function renderPerStock() {
  const card = document.getElementById('perStockCard');
  const body = document.getElementById('psBody');
  if (!card || !body) return;
  const hide = () => { _psHasData = false; card.style.display = 'none'; };

  let rows = [], label;
  if (_metricMode === 'today') {
    label = '오늘';
    // 계좌 넘어 종목별 수량 합산 (renderHoldings와 동일 기준)
    const agg = {};
    holdings.forEach(h => {
      if (!h.quantity || h.quantity <= 0) return;
      const a = agg[h.code] || (agg[h.code] = { name: h.name || h.code, qty: 0, code: h.code });
      a.qty += h.quantity;
    });
    Object.values(agg).forEach(a => {
      const c = prices[a.code], p = prevClose[a.code];
      if (manualCodes.includes(a.code) || c == null || p == null || !p) { rows.push({ name: a.name, nodata: true }); return; }
      rows.push({ name: a.name, pct: (c - p) / p, diff: (c - p) * a.qty });
    });
  } else {
    label = _maPeriodLabel;
    const d = _historyData;
    if (!d || d.empty || !d.series) { hide(); return; }
    Object.entries(d.series).forEach(([code, arr]) => {
      const name = (d.names && d.names[code]) || code;
      const w = (_maHistoryDays > 0 && arr.length > _maHistoryDays) ? arr.slice(-_maHistoryDays) : arr;
      const nn = w.filter(v => v != null && v > 0);
      if (nn.length < 2) { rows.push({ name, nodata: true }); return; }
      const first = nn[0], last = nn[nn.length - 1];
      rows.push({ name, pct: (last - first) / first, diff: last - first });
    });
  }

  if (!rows.some(r => !r.nodata)) { hide(); return; }
  // 기여금액 내림차순, 데이터 없는 종목은 맨 아래
  rows.sort((a, b) => (a.nodata ? 1 : 0) - (b.nodata ? 1 : 0) || (b.diff || 0) - (a.diff || 0));

  body.innerHTML = rows.map(r => {
    if (r.nodata) return `<div class="ps-row"><span class="ps-name">${maEsc(r.name)}</span><span class="ps-pct flat">—</span><span class="ps-amt flat">—</span></div>`;
    const cls = r.diff >= 0 ? 'up' : 'down';
    return `<div class="ps-row"><span class="ps-name">${maEsc(r.name)}</span><span class="ps-pct ${cls}">${fmtSignedPct(r.pct)}</span><span class="ps-amt ${cls}">${fmtSignedKRW(r.diff)}</span></div>`;
  }).join('');
  document.getElementById('psPeriodLbl').textContent = label + ' 기준';
  _psHasData = true;
  // 모바일선 현황 탭일 때만 노출(다른 탭이면 숨김 유지)
  card.style.display = (_isMobile() && _mActive() !== 'overview') ? 'none' : '';
}

const maEsc = window.mmEsc;  // E-1 공용화: 전역 mmEsc(base.html) 단일 구현 — 로컬 복붙 제거 (2026-07-03)

// ── 새로고침 (서버 공유 캐시 20분 floor — 더 자주 눌러도 같은 값) ──
async function refreshHoldings() {
  const btn = document.getElementById('refreshHoldingsBtn');
  if (btn) { btn.disabled = true; btn.classList.add('spinning'); }
  try { await loadAll(); } catch (e) {}
  if (btn) setTimeout(() => { btn.classList.remove('spinning'); btn.disabled = false; }, 700);
}

// ── 수동 가격 override (인라인 모달) ──
function setManual(id, curKRW) {
  document.getElementById('manualHoldingId').value = id;
  const inp = document.getElementById('manualPriceInput');
  inp.value = (curKRW && curKRW > 0) ? Math.round(curKRW) : '';
  document.getElementById('manualErr').style.display = 'none';
  openModal('modalManual');
  setTimeout(() => { inp.focus(); inp.select(); }, 50);
}
async function saveManual() {
  const id  = document.getElementById('manualHoldingId').value;
  const raw = document.getElementById('manualPriceInput').value.trim();
  const err = document.getElementById('manualErr');
  const price = raw === '' ? null : Number(raw.replace(/[,\s₩]/g, ''));
  if (price !== null && (isNaN(price) || price < 0)) {
    err.textContent = '숫자(0 이상)를 입력하세요.'; err.style.display = 'block'; return;
  }
  await fetch('/api/myassets/manual-price', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, price }),
  });
  closeModal('modalManual');
  await loadAll();
}
async function clearManual(id) {
  await fetch('/api/myassets/manual-price', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, price: null }),
  });
  await loadAll();
}

function _syncHideLabel() {
  const lbl = document.getElementById('hideAmountLbl');
  if (lbl) lbl.textContent = hideAmounts ? '가리는 중' : '표시 중';
}

async function savePrivacySetting() {
  const toggle = document.getElementById('hideAmountToggle');
  hideAmounts = !!toggle.checked;
  _syncHideLabel();
  renderHoldings();
  renderSummary();
  updateHeroMetric();
  renderPerStock();
  if (_historyData) renderHistoryChart(_maHistoryDays);
  if (document.getElementById('tab-rebalance').style.display !== 'none') renderRebalance();
  await fetch('/api/myassets/settings', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ hide_amounts: hideAmounts }),
  });
}

// ── 보유 종목 = 종목별 한 줄 카드(계좌 합산) + 탭하면 계좌별 펼침 ──
function renderHoldings() {
  const wrap = document.getElementById('holdingsTableWrap');
  syncHistoryEmptyMode();
  if (!holdings.length) {
    wrap.innerHTML = '<div style="text-align:center;padding:30px;color:var(--text-muted);">'
      + '보유 종목이 없습니다.<br><button class="btn-primary" style="margin-top:14px;" onclick="openAddHolding()">+ 첫 종목 추가</button></div>';
    return;
  }

  // 같은 종목 = 계좌 넘어 보기만 합산 (데이터는 계좌별 유지)
  const agg = {};
  holdings.forEach(h => {
    const a = agg[h.code] || (agg[h.code] = {
      code: h.code, name: h.name, group_name: h.group_name, group_color: h.group_color,
      qty: 0, cost: 0, rows: [],
    });
    a.qty  += h.quantity;
    a.cost += (h.avg_price || 0) * h.quantity;
    a.rows.push(h);
  });
  const items = Object.values(agg);
  const totalValue = items.reduce((s, a) => s + (prices[a.code] || 0) * a.qty, 0);

  wrap.innerHTML = `<div class="hold-list">${items.map((a, i) => {
    const cur = prices[a.code] || 0;
    const val = cur * a.qty;
    const wt  = totalValue > 0 ? val / totalValue : 0;
    const isManual = manualCodes.includes(a.code);
    const avg = a.qty > 0 ? a.cost / a.qty : 0;            // 가중 평단
    const ret = avg > 0 ? (cur - avg) / avg : null;        // 평단 기준 전체수익률
    const _p  = prevClose[a.code];
    const todayPct = (!isManual && cur && _p) ? (cur - _p) / _p : null;
    const gc  = a.group_color || '#90A4AE';

    // 행 수익 = 보유종목 토글(_rowMetric) 따라. today→오늘±, total→평단 전체수익률
    let retHtml;
    if (_rowMetric === 'today') {
      retHtml = (todayPct === null)
        ? `<span class="hc-ret flat">오늘 —</span>`
        : `<span class="hc-ret ${todayPct>=0?'up':'down'}">오늘 ${fmtSignedPct(todayPct)}</span>`;
    } else {
      retHtml = (ret === null)
        ? `<span class="hc-ret flat">—</span>`
        : `<span class="hc-ret ${ret>=0?'up':'down'}">${ret>=0?'+':''}${fmtPct(ret)}</span>`;
    }

    const grpDot  = a.group_name ? `<span class="hc-gdot" style="background:${gc}" title="${maEsc(a.group_name)}"></span>` : '';

    // 펼침 = 계좌별 분해 (각 계좌 수정/삭제)
    const acctRows = a.rows.map(r => {
      const hd = _holdDays(r.buy_date);
      return `<div class="hc-acct">
        <span><b>${r.account_type}</b> · ${r.quantity.toLocaleString()}주 · 평단 ${r.avg_price>0?fmtKRW(r.avg_price):'—'}${hd!==null?` · 보유 ${hd}일`:''}</span>
        <span class="hc-acct-act">
          <button onclick="openEditHolding(${r.id})">수정</button>
          <button class="danger" onclick="deleteHolding(${r.id})">삭제</button>
        </span>
      </div>`;
    }).join('');

    return `<div class="hold-card" id="hold-${i}" onclick="toggleHold(${i})">
      <div class="hc-top">
        <div class="hc-name">${grpDot}${a.name || a.code}</div>
        <div class="hc-val">${fmtKRW(val)}</div>
      </div>
      <div class="hc-meta">
        <span class="hc-wt">${fmtPct(wt)}</span>
        <span style="color:var(--ds-hairline);">·</span>
        ${retHtml}
        ${isManual?'<span class="hc-badge" style="color:var(--blue);">수동가</span>':''}
        <span class="hc-cur">1주 ${cur ? fmtPrice(cur) : '—'}</span>
        <span class="hc-chev">${MAICON.chev}</span>
      </div>
      <div class="hc-exp" id="exp-${i}" hidden onclick="event.stopPropagation();">
        <div class="hc-detail">종목 <b>${a.code}</b> · 현재가 <b>${cur ? fmtPrice(cur) : '—'}</b> · 평단 <b>${avg>0?fmtKRW(avg):'—'}</b> · 합계 <b>${a.qty.toLocaleString()}주</b>${a.rows.length>1?` · <b>${a.rows.length}계좌</b>`:''}</div>
        ${acctRows}
        <div class="hc-actions" style="margin-top:10px;">
          <button onclick="setManual(${a.rows[0].id}, ${cur})">현재가 수동</button>
          ${isManual?`<button onclick="clearManual(${a.rows[0].id})">자동시세</button>`:''}
          <a href="/symbol/${encodeURIComponent(a.code)}">종목 상세 ›</a>
        </div>
      </div>
    </div>`;
  }).join('')}</div>`;
}

function toggleHold(i) {
  const card = document.getElementById('hold-'+i);
  const exp  = document.getElementById('exp-'+i);
  if (!exp || !card) return;
  if (exp.hasAttribute('hidden')) { exp.removeAttribute('hidden'); card.classList.add('open'); }
  else { exp.setAttribute('hidden',''); card.classList.remove('open'); }
}

// ── 요약 + 차트 ──
function renderSummary() {
  const totalValue  = holdings.reduce((s, h) => s + (prices[h.code]||0)*h.quantity, 0);
  const totalCost   = holdings.reduce((s, h) => s + h.avg_price*h.quantity, 0);
  const totalReturn = totalCost > 0 ? (totalValue - totalCost) / totalCost : 0;
  updateAssetHeroTotal(totalValue);

  const uniqCount = new Set(holdings.map(h => h.code)).size;
  document.getElementById('summaryGrid').innerHTML = [
    { label: '총 평가금액', value: fmtKRW(totalValue), cls: '' },
    { label: '총 매입금액', value: fmtKRW(totalCost), cls: '' },
    { label: '총 수익률',   value: (totalReturn>=0?'+':'')+fmtPct(totalReturn), cls: totalReturn>=0?'var(--up)':'var(--down)' },
    { label: '보유 종목 수', value: uniqCount+'개', cls: '' },
  ].map(i=>`<div class="summary-item"><div class="summary-label">${i.label}</div><div class="summary-value" style="color:${i.cls||'var(--text)'}">${i.value}</div></div>`).join('');

  // 그룹 미설정 사용자 안내 — 직접 묶어 관리 가능함을 노출
  const hintEl = document.getElementById('groupHint');
  if (hintEl) {
    const hasGroup = holdings.some(h => h.group_id);
    hintEl.innerHTML = (holdings.length && !hasGroup)
      ? `<div class="grp-hint">${MAICON.layers}<span>종목을 <b>그룹</b>으로 묶으면 (예: 미국주식·금·채권) 자산군별 비중을 한눈에 볼 수 있어요.</span><button onclick="showTab('groups')">그룹 만들기 ›</button></div>`
      : '';
  }

  renderWeightChart(totalValue);
}

function renderWeightChart(totalValue) {
  if (weightChart) weightChart.destroy();
  if (!holdings.length || !totalValue) return;

  // 그룹별 합산 + 미지정 종목은 코드별 합산(복수 계좌 보유 병합) — 범례 중복 방지
  const grouped = {};
  const ungrouped = {};
  holdings.forEach(h => {
    const val = (prices[h.code]||0) * h.quantity;
    if (h.group_name) {
      if (!grouped[h.group_name]) grouped[h.group_name] = { val: 0, color: h.group_color||'#90A4AE' };
      grouped[h.group_name].val += val;
    } else {
      if (!ungrouped[h.code]) ungrouped[h.code] = { name: h.name || h.code, val: 0, n: 0 };
      ungrouped[h.code].val += val;
      ungrouped[h.code].n  += 1;
    }
  });

  // 미지정 종목 고유색(순환 팔레트) — 전부 회색이라 슬라이스 구분 불가하던 문제
  const UNGROUPED_PALETTE = ['#5C6BC0','#26A69A','#EF6C00','#8D6E63','#7E57C2','#EC407A','#66BB6A','#FFA726'];
  const _clip = s => s.length > 14 ? s.slice(0, 13) + '…' : s;
  const items = [
    ...Object.entries(grouped).map(([k,v]) => ({ label: k, val: v.val, color: v.color })),
    ...Object.values(ungrouped).map((u, i) => ({
      label: _clip(u.name) + (u.n > 1 ? ` (${u.n}건)` : ''),
      val: u.val,
      color: UNGROUPED_PALETTE[i % UNGROUPED_PALETTE.length],
    })),
  ].filter(i => i.val > 0);

  weightChart = new Chart(document.getElementById('weightChart').getContext('2d'), {
    type: 'pie',
    data: {
      labels: items.map(i => i.label),
      datasets: [{
        data: items.map(i => parseFloat((i.val/totalValue*100).toFixed(1))),
        backgroundColor: items.map(i => i.color+'cc'),
        borderColor:     items.map(i => i.color),
        borderWidth: 1.5,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: true },   // 파이는 조각 위에서만(전역 index 모드 override)
      plugins: {
        legend: { position: window.innerWidth <= 768 ? 'bottom' : 'right',
                  labels: { boxWidth: 14, font: { size: 11 } } },
        tooltip: { mode: 'nearest', intersect: true, callbacks: { label: ctx => `${ctx.label}: ${ctx.parsed.toFixed(1)}%` } },
      },
    }
  });
}

// ── 리밸런싱 ──
let _rebalBand = 0.05;

function syncRebalBand(val) {
  if (!val || isNaN(val) || val < 0.1) return;
  val = Math.min(20, Math.max(0.5, val));
  _rebalBand = val / 100;
  const slider  = document.getElementById('rebalBandSlider');
  const display = document.getElementById('rebalBandDisplay');
  if (slider)  slider.value = val;
  if (display) display.textContent = (val % 1 === 0) ? val : val.toFixed(1);
  // 프리셋 칩 활성표시 (정확히 일치할 때만)
  document.querySelectorAll('.rb-preset').forEach(b =>
    b.classList.toggle('active', parseFloat(b.dataset.band) === val));
  // 밴드 변경은 금액·차이에 영향 없음 → 전체 재렌더 없이 밴드존만 라이브 갱신
  updateBandVisuals();
}

// 경고 밴드를 계정(설정)에 저장 — 새로고침해도 유지
async function saveRebalBand() {
  try {
    await fetch('/api/myassets/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rebal_band: +(_rebalBand * 100).toFixed(1) }),
    });
  } catch (e) {}
}

function renderRebalance() {
  // 리밸런싱 기준 = 그룹에 속한 종목만(미그룹 제외) + 목표비중은 합으로 정규화 → 매수·매도 net 0
  const groupValues = {};
  let groupedTotal = 0, ungroupedVal = 0;
  holdings.forEach(h => {
    const val = (prices[h.code]||0)*h.quantity;
    if (h.group_id) { groupValues[h.group_id] = (groupValues[h.group_id]||0) + val; groupedTotal += val; }
    else ungroupedVal += val;
  });
  const sumTargets = groups.filter(g => g.target_pct > 0).reduce((s, g) => s + g.target_pct, 0);
  if (!groupedTotal || !sumTargets) {
    document.getElementById('rebalStatus').innerHTML = '';
    document.getElementById('rebalResult').innerHTML =
      `<div class="ma-empty"><div class="em-ic">${MAICON.scale}</div><div class="em-t">아직 계산할 게 없어요</div><div class="em-d">그룹 관리 탭에서 그룹을 만들고 종목을 넣은 뒤<br>목표 비중을 설정하면 리밸런싱이 표시됩니다.</div></div>`;
    return;
  }

  const rows = groups.filter(g => g.target_pct > 0).map(g => {
    const cur      = groupValues[g.id] || 0;
    const curPct   = cur/groupedTotal;
    const tgtPct   = g.target_pct/sumTargets;   // 합으로 정규화
    const diff     = tgtPct - curPct;
    const diffVal  = diff * groupedTotal;
    const absDiff  = Math.abs(diff);
    const outOfBand = absDiff > _rebalBand;
    const action   = absDiff < 0.001 ? 'ok' : diff > 0 ? 'buy' : 'sell';
    return { g, cur, curPct, tgtPct, diff, diffVal, action, outOfBand, absDiff };
  });

  if (!rows.length) {
    document.getElementById('rebalStatus').innerHTML = '';
    document.getElementById('rebalResult').innerHTML =
      '<div style="padding:20px;color:var(--text-muted);font-size:0.85rem;">그룹 탭에서 목표 비중을 설정해주세요</div>';
    return;
  }

  const alertCount = rows.filter(r => r.outOfBand).length;
  const _bandPct = (_rebalBand * 100 % 1 === 0) ? Math.round(_rebalBand*100) : (_rebalBand*100).toFixed(1);

  document.getElementById('rebalStatus').innerHTML = alertCount > 0
    ? `<div class="grp-sum warn">${MAICON.alert} ${alertCount}개 그룹이 ±${_bandPct}%p 밴드를 벗어났어요 — 리밸런싱을 검토하세요</div>`
    : `<div class="grp-sum ok">${MAICON.check} 모든 그룹이 목표 ±${_bandPct}%p 이내예요 — 균형이 잘 잡혀 있어요</div>`;

  const cards = rows.map(r => {
    const fillW = Math.min(100, r.curPct * 100);
    const tgtL  = Math.min(100, r.tgtPct * 100);
    const actCls  = r.action;
    const actText = r.action === 'ok' ? '적정'
      : r.action === 'buy' ? '매수 ' + fmtKRW(r.diffVal)
      : '매도 ' + fmtKRW(Math.abs(r.diffVal));
    const diffCls = r.diff > 0 ? 'under' : r.diff < 0 ? 'over' : '';
    const diffTxt = (r.diff >= 0 ? '+' : '') + (r.diff * 100).toFixed(1) + '%p';
    return `
    <div class="rb-card ${r.outOfBand ? 'warn' : ''}" data-cur="${r.curPct}" data-tgt="${r.tgtPct}">
      <div class="rb-card-head">
        <span class="rb-dot" style="background:${r.g.color}"></span>
        <span class="rb-name">${maEsc(r.g.name)}</span>
        <span class="rb-act ${actCls}">${actText}</span>
      </div>
      <div class="rb-track">
        <div class="rb-band-zone"></div>
        <div class="rb-fill" style="width:${fillW}%;background:${r.g.color}"></div>
        <div class="rb-target" style="left:${tgtL}%"></div>
      </div>
      <div class="rb-nums">
        <span>현재 <b>${(r.curPct*100).toFixed(1)}%</b></span>
        <span class="rb-diff ${diffCls}">차이 ${diffTxt}</span>
        <span>목표 <b>${(r.tgtPct*100).toFixed(1)}%</b></span>
      </div>
    </div>`;
  }).join('');

  const notes = [];
  if (Math.abs(sumTargets - 100) > 0.1)
    notes.push(`목표 비중 합 ${(+sumTargets.toFixed(1))}% → 100% 기준으로 정규화해 계산합니다.`);
  if (ungroupedVal > 0)
    notes.push(`그룹 미지정 종목 ${fmtKRW(ungroupedVal)}은 리밸런싱에서 제외됩니다.`);
  const noteBanner = notes.length
    ? `<div style="font-size:0.74rem;color:var(--ds-muted);margin-top:8px;line-height:1.5;">ℹ ${notes.join(' ')}</div>` : '';

  document.getElementById('rebalResult').innerHTML = cards + noteBanner;
  updateBandVisuals();   // 밴드존 위치 + 이탈 하이라이트
}

// 경고밴드 시각화 갱신 (슬라이더 이동 시 전체 재렌더 없이 라이브 업데이트)
function updateBandVisuals() {
  const cards = document.querySelectorAll('#rebalResult .rb-card');
  if (!cards.length) return;
  let alertCount = 0;
  cards.forEach(card => {
    const tgt = parseFloat(card.dataset.tgt), cur = parseFloat(card.dataset.cur);
    if (isNaN(tgt) || isNaN(cur)) return;
    const lo = Math.max(0, (tgt - _rebalBand) * 100);
    const hi = Math.min(100, (tgt + _rebalBand) * 100);
    const zone = card.querySelector('.rb-band-zone');
    if (zone) { zone.style.left = lo + '%'; zone.style.width = Math.max(0, hi - lo) + '%'; }
    const out = Math.abs(tgt - cur) > _rebalBand;
    card.classList.toggle('warn', out);
    if (out) alertCount++;
  });
  const _bandPct = (_rebalBand * 100 % 1 === 0) ? Math.round(_rebalBand * 100) : (_rebalBand * 100).toFixed(1);
  const st = document.getElementById('rebalStatus');
  if (st) st.innerHTML = alertCount > 0
    ? `<div class="grp-sum warn">${MAICON.alert} ${alertCount}개 그룹이 ±${_bandPct}%p 밴드를 벗어났어요 — 리밸런싱을 검토하세요</div>`
    : `<div class="grp-sum ok">${MAICON.check} 모든 그룹이 목표 ±${_bandPct}%p 이내예요 — 균형이 잘 잡혀 있어요</div>`;
}

// 정수(원) 배분: floats를 합이 정확히 round(total)이 되도록 최대잔여법으로 반올림
function allocExact(weights, total) {
  const floors = weights.map(w => Math.floor(w));
  let rem = Math.round(total) - floors.reduce((a, b) => a + b, 0);
  const order = weights.map((w, i) => ({ i, f: w - Math.floor(w) })).sort((a, b) => b.f - a.f);
  for (let k = 0; k < rem && order.length; k++) floors[order[k % order.length].i]++;
  return floors;
}

// ── 추가매수 ──
function setPurchaseAmount(v) {
  document.getElementById('purchaseAmount').value = v;
  calcPurchase();
}

function calcPurchase() {
  const resEl  = document.getElementById('purchaseResult');
  const amount = parseFloat(document.getElementById('purchaseAmount').value) || 0;

  const tg = groups.filter(g => g.target_pct > 0);
  const sumTargets = tg.reduce((s, g) => s + g.target_pct, 0);
  if (!tg.length || !sumTargets) {
    resEl.innerHTML = `<div class="ma-empty"><div class="em-ic">${MAICON.scale}</div><div class="em-t">목표 비중이 필요해요</div><div class="em-d">그룹 관리 탭에서 그룹 목표 비중을 먼저 설정하면<br>추가매수 배분을 제안해드려요.</div></div>`;
    return;
  }
  if (!amount) {
    resEl.innerHTML = `<div style="color:var(--ds-muted);font-size:0.85rem;padding:10px 0;">투자 금액을 입력하면 그룹별 배분 제안이 표시됩니다.</div>`;
    return;
  }

  const groupValues = {};
  let groupedTotal = 0;
  holdings.forEach(h => {
    if (!h.group_id) return;
    const v = (prices[h.code] || 0) * h.quantity;
    groupValues[h.group_id] = (groupValues[h.group_id] || 0) + v;
    groupedTotal += v;
  });

  const newTotal = groupedTotal + amount;
  // 목표가치 대비 부족분(매수만 가능 → 초과그룹은 0). 부족분 비례로 amount 전액 배분.
  const items = tg.map(g => {
    const w = g.target_pct / sumTargets;
    const posDef = Math.max(0, newTotal * w - (groupValues[g.id] || 0));
    return { g, w, posDef };
  });
  const sumPos = items.reduce((s, r) => s + r.posDef, 0);
  const rawBuys = items.map(r => sumPos > 0 ? amount * r.posDef / sumPos : amount * r.w);
  const buys = allocExact(rawBuys, amount);
  const rows = items.map((r, i) => ({ g: r.g, buy: buys[i] })).filter(r => r.buy > 0);
  if (!rows.length) { resEl.innerHTML = `<div style="color:var(--ds-muted);">배분할 그룹이 없습니다.</div>`; return; }

  const maxBuy = Math.max(...rows.map(r => r.buy));
  const buyTotal = rows.reduce((s, r) => s + r.buy, 0);
  resEl.innerHTML = `
    <div style="font-size:0.82rem;font-weight:700;margin-bottom:4px;">${fmtKRW(amount)} 배분 제안</div>
    ${rows.map(r => `
    <div class="pur-row">
      <span class="rb-dot" style="background:${r.g.color}"></span>
      <span style="min-width:84px;font-weight:600;font-size:0.86rem;">${maEsc(r.g.name)}</span>
      <span class="pur-bar"><i style="width:${(r.buy/maxBuy*100).toFixed(0)}%;background:${r.g.color}"></i></span>
      <span class="pur-buy">+${fmtKRW(r.buy)}</span>
    </div>`).join('')}
    <div style="display:flex;justify-content:space-between;align-items:center;font-weight:700;padding-top:12px;border-top:1.5px solid var(--ds-hairline);margin-top:4px;">
      <span>합계</span><span class="pur-buy" style="color:var(--ds-ink)">+${fmtKRW(buyTotal)}</span>
    </div>
    <div style="margin-top:12px;font-size:0.76rem;color:var(--ds-muted);line-height:1.5;">* 목표 대비 부족한 그룹에 우선 배분(매도 없이 목표에 근접). 그룹 내 종목 선택은 계좌별 세금을 고려해 직접 결정하세요.</div>
  `;
}

// ── 그룹 관리 ──
function renderGroups() {
  const wrap  = document.getElementById('groupsWrap');
  const sumEl = document.getElementById('groupsSum');
  if (!groups.length) {
    if (sumEl) sumEl.innerHTML = '';
    wrap.innerHTML = `<div class="ma-empty"><div class="em-ic">${MAICON.layers}</div><div class="em-t">아직 그룹이 없어요</div><div class="em-d">자산을 국내주식·미국주식·채권·금 등으로 묶고<br>목표 비중을 정해 리밸런싱·추가매수에 활용하세요.</div><button class="btn-primary" style="margin-top:16px;" onclick="openAddGroup()">+ 첫 그룹 만들기</button></div>`;
    return;
  }

  // 그룹별 종목 수·평가액
  const gStat = {};
  holdings.forEach(h => {
    if (!h.group_id) return;
    const v = (prices[h.code] || 0) * h.quantity;
    if (!gStat[h.group_id]) gStat[h.group_id] = { n: 0, val: 0 };
    gStat[h.group_id].n++; gStat[h.group_id].val += v;
  });

  const sumTargets = groups.reduce((s, g) => s + (g.target_pct || 0), 0);
  const sumOk = Math.abs(sumTargets - 100) < 0.1;
  if (sumEl) sumEl.innerHTML =
    `<div class="grp-sum ${sumOk ? 'ok' : 'warn'}">
      <span>${sumOk ? MAICON.check : MAICON.alert} 목표 비중 합계</span>
      <span style="font-family:var(--font-mono)">${(+sumTargets.toFixed(1))}%${sumOk ? '' : ' · 100% 권장'}</span>
    </div>`;

  const maxTgt = Math.max(...groups.map(g => g.target_pct || 0), 1);
  wrap.innerHTML = groups.map(g => {
    const st = gStat[g.id] || { n: 0, val: 0 };
    const initial = (g.name || '?').trim().charAt(0);
    return `
    <div class="grp-card">
      <span class="grp-emblem" style="background:${g.color}">${maEsc(initial)}</span>
      <div class="grp-main">
        <div class="grp-name">${maEsc(g.name)}</div>
        <div class="grp-sub">${st.n}개 종목 · ${fmtKRW(st.val)}</div>
      </div>
      <div class="grp-tgt">
        <div class="grp-tgt-v">${g.target_pct}%</div>
        <div class="grp-tgt-l">목표 비중</div>
        <div class="grp-tgt-bar"><i style="width:${(g.target_pct/maxTgt*100).toFixed(0)}%;background:${g.color}"></i></div>
      </div>
      <div class="grp-actions">
        <button class="icon-btn" onclick="openEditGroup(${g.id})" title="수정">${MAICON.pencil}</button>
        <button class="icon-btn danger" onclick="deleteGroup(${g.id})" title="삭제">${MAICON.trash}</button>
      </div>
    </div>`;
  }).join('');
}

// ── 모달 ──
function openModal(id)  { document.getElementById(id).classList.add('show'); }
function closeModal(id) { document.getElementById(id).classList.remove('show'); }

function renderGroupOptions() {
  const sel = document.getElementById('holdingGroup');
  sel.innerHTML = '<option value="">그룹 없음</option>' +
    groups.map(g=>`<option value="${g.id}">${maEsc(g.name)}</option>`).join('');
}

function openAddHolding() {
  document.getElementById('holdingId').value       = '';
  document.getElementById('holdingCodeInput').value = '';
  document.getElementById('holdingCode').value      = '';
  document.getElementById('holdingCodeSelected').textContent = '';
  document.getElementById('holdingQty').value       = '1';
  document.getElementById('holdingAvgPrice').value  = '0';
  document.getElementById('holdingBuyDate').value   = '';
  document.getElementById('holdingGroup').value     = '';
  document.querySelector('input[name="holdingAccount"][value="일반"]').checked = true;
  document.getElementById('modalHoldingTitle').textContent = '종목 추가';
  openModal('modalHolding');
}

function openEditHolding(id) {
  const h = holdings.find(h=>h.id===id);
  if (!h) return;
  document.getElementById('holdingId').value       = h.id;
  document.getElementById('holdingCodeInput').value = h.code;
  document.getElementById('holdingCode').value      = h.code;
  document.getElementById('holdingCodeSelected').textContent = h.code;
  document.getElementById('holdingQty').value       = h.quantity;
  document.getElementById('holdingAvgPrice').value  = h.avg_price;
  document.getElementById('holdingBuyDate').value   = h.buy_date || '';
  document.getElementById('holdingGroup').value     = h.group_id || '';
  const acc = document.querySelector(`input[name="holdingAccount"][value="${h.account_type}"]`);
  if (acc) acc.checked = true;
  document.getElementById('modalHoldingTitle').textContent = '종목 수정';
  openModal('modalHolding');
}

// 국내 상장 = 6자리 코드 또는 KRX 금현물. 그 외 = 해외 상장(US·크립토 등)
function _isDomesticListed(code) { return /^\d{6}$/.test(code) || code === 'KRX_GOLD'; }
// ISA·연금저축·IRP는 해외 상장 종목 보유 불가(실제 제도) → 경고만, 저장은 허용
const _RESTRICTED_ACCOUNTS = ['ISA', '연금저축', 'IRP'];

async function saveHolding() {
  const code    = document.getElementById('holdingCode').value;
  if (!code) { mmToast('종목을 선택해주세요.'); return; }
  const account = document.querySelector('input[name="holdingAccount"]:checked').value;
  if (_RESTRICTED_ACCOUNTS.includes(account) && !_isDomesticListed(code)) {
    maConfirm(
      `${account} 계좌엔 해외 상장 종목을 담을 수 없어요`,
      `${account}는 국내 상장 종목만 보유 가능해요(해외 상장 ETF·주식 불가). 기록용으로 그대로 저장할까요?`,
      _doSaveHolding,
      { variant: 'warn', yesLabel: '그대로 저장' }
    );
    return;
  }
  await _doSaveHolding();
}

async function _doSaveHolding() {
  await fetch('/api/myassets/holding', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      id:           document.getElementById('holdingId').value || null,
      code:         document.getElementById('holdingCode').value,
      quantity:     parseFloat(document.getElementById('holdingQty').value)||0,
      avg_price:    parseFloat(document.getElementById('holdingAvgPrice').value)||0,
      account_type: document.querySelector('input[name="holdingAccount"]:checked').value,
      group_id:     document.getElementById('holdingGroup').value || null,
      buy_date:     document.getElementById('holdingBuyDate').value || null,
    })
  });
  closeModal('modalHolding');
  await loadAll();
}

// ── 확인 다이얼로그 (confirm() 대체) ──
let _confirmCb = null;
function maConfirm(msg, sub, onYes, opts = {}) {
  const variant = opts.variant || 'danger';   // 'danger'(삭제) | 'warn'(경고)
  const ic = document.getElementById('confirmIc');
  ic.className = 'confirm-ic ' + variant;
  ic.innerHTML = variant === 'danger' ? MAICON.trash : MAICON.alert;
  const yes = document.getElementById('confirmYes');
  yes.textContent = opts.yesLabel || (variant === 'danger' ? '삭제' : '확인');
  yes.className = variant === 'danger' ? 'btn-danger' : 'btn-primary';
  document.getElementById('confirmMsg').textContent = msg;
  document.getElementById('confirmSub').textContent = sub || '';
  _confirmCb = onYes;
  openModal('modalConfirm');
}
document.getElementById('confirmYes').addEventListener('click', async () => {
  closeModal('modalConfirm');
  const cb = _confirmCb; _confirmCb = null;
  if (cb) await cb();
});

function deleteHolding(id) {
  const h = holdings.find(x => x.id === id);
  maConfirm('이 종목을 삭제할까요?',
    h ? `${h.name || h.code} 보유 내역이 삭제됩니다.` : '',
    async () => {
      await fetch('/api/myassets/holding/'+id, { method: 'DELETE' });
      await loadAll();
    });
}

function openAddGroup() {
  document.getElementById('groupId').value         = '';
  document.getElementById('groupName').value       = '';
  document.getElementById('groupColor').value      = '#1976D2';
  document.getElementById('groupTargetPct').value  = '0';
  document.getElementById('modalGroupTitle').textContent = '그룹 추가';
  openModal('modalGroup');
}

function openEditGroup(id) {
  const g = groups.find(g=>g.id===id);
  if (!g) return;
  document.getElementById('groupId').value        = g.id;
  document.getElementById('groupName').value      = g.name;
  document.getElementById('groupColor').value     = g.color;
  document.getElementById('groupTargetPct').value = g.target_pct;
  document.getElementById('modalGroupTitle').textContent = '그룹 수정';
  openModal('modalGroup');
}

async function saveGroup() {
  const name = document.getElementById('groupName').value.trim();
  if (!name) { mmToast('그룹명을 입력해주세요.'); return; }
  await fetch('/api/myassets/group', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      id:         document.getElementById('groupId').value || null,
      name,
      color:      document.getElementById('groupColor').value,
      target_pct: parseFloat(document.getElementById('groupTargetPct').value)||0,
    })
  });
  closeModal('modalGroup');
  await loadAll();
  renderGroups();
}

function deleteGroup(id) {
  const g = groups.find(x => x.id === id);
  maConfirm('이 그룹을 삭제할까요?',
    `${g ? '"' + g.name + '" ' : ''}그룹만 삭제되고 종목은 그대로 유지됩니다.`,
    async () => {
      await fetch('/api/myassets/group/'+id, { method: 'DELETE' });
      await loadAll();
      renderGroups();
    });
}

// ── 종목 검색 (모달) ──
let holdingSearchTimer = null;
document.getElementById('holdingCodeInput').addEventListener('input', e => {
  const q = e.target.value.trim();
  if (!q) { document.getElementById('holdingSearchDrop').style.display='none'; return; }
  clearTimeout(holdingSearchTimer);
  holdingSearchTimer = setTimeout(async () => {
    const res  = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    const drop = document.getElementById('holdingSearchDrop');
    if (!data.length) { drop.style.display='none'; return; }
    drop.innerHTML = data.slice(0,8).map(item=>`
      <div class="nav-search-result" onclick="selectHoldingCode('${item.code}','${item.name.replace(/'/g,"\\'")}')">
        <div class="nav-search-info">
          <div class="nav-search-code">${item.code}</div>
          <div class="nav-search-name">${maEsc(item.name)}</div>
        </div>
      </div>`).join('');
    drop.style.display = 'block';
  }, 250);
});

function selectHoldingCode(code, name) {
  document.getElementById('holdingCode').value          = code;
  document.getElementById('holdingCodeInput').value     = code;
  document.getElementById('holdingCodeSelected').textContent = name;
  document.getElementById('holdingSearchDrop').style.display = 'none';
}

// 외부 클릭으로 닫기 비활성화

loadAll().then(() => { loadPortfolioHistory(30); _mReady = true; });
loadDividends();

// ── 배당금: 연도 선택 + 월별 막대(드릴다운) + 배당 일정 캘린더 ──
let _divChart = null, _divData = null;
let _divTax = 'pretax', _divCur = 'KRW', _divYear = null, _divActiveMonth = null;

async function loadDividends() {
  try {
    const res = await fetch('/api/myassets/dividends', { cache: 'no-store' });
    if (!res.ok) { document.getElementById('divEmpty').style.display = 'block'; return; }
    _divData = await res.json();
  } catch (e) {
    document.getElementById('divEmpty').style.display = 'block';
    return;
  }
  _divYear = _divData.default_year;
  renderYearTabs();
  renderDivYear();
}

function _valOf(e) { return e[(_divCur === 'KRW' ? 'krw' : 'usd') + '_' + (_divTax === 'pretax' ? 'pre' : 'post')]; }
function _fmtDivMoney(v) {
  return _divCur === 'USD'
    ? '$' + v.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : '₩' + Math.round(v).toLocaleString();
}

function _yearLabel(y) {
  if (y === _divData.full_proj_year) return y + ' (예측)';
  if (y === _divData.current_year)   return y + ' (진행)';
  return String(y);
}

function renderYearTabs() {
  document.getElementById('divYearTabs').innerHTML = _divData.years.map(y =>
    `<button class="div-tgl${y === _divYear ? ' active' : ''}" data-div-year="${y}">${_yearLabel(y)}</button>`
  ).join('');
}

function renderDivYear() {
  if (!_divData) return;
  const evs = _divData.events[_divYear] || [];
  const anyData = evs.length > 0;
  document.getElementById('divEmpty').style.display = anyData ? 'none' : 'block';
  document.getElementById('divChart').style.display = anyData ? 'block' : 'none';

  // 월별 실적/예측 분리 합산 — 한 달에 둘이 섞이면(예: 일부 종목만 실데이터 도착)
  // 통째로 예측색이 되던 문제 → 스택 바(파랑=실적, 주황=예측분)로 의미 정확화
  const monthlyReal = Array(12).fill(0);
  const monthlyProj = Array(12).fill(0);
  evs.forEach(e => { (e.projected ? monthlyProj : monthlyReal)[e.month - 1] += _valOf(e); });
  const monthly  = monthlyReal.map((v, i) => v + monthlyProj[i]);
  const monthProj = monthlyProj.map(v => v > 0);
  const _divBrand = _cssVar('--brand') || '#0052ff';

  const labels = ['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월'];
  const ctx = document.getElementById('divChart').getContext('2d');
  if (_divChart) _divChart.destroy();
  _divChart = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [
      { label: '실적', data: monthlyReal, backgroundColor: _divBrand, stack: 'div' },
      { label: '예측', data: monthlyProj, backgroundColor: 'rgba(251,140,0,0.7)', stack: 'div' },
    ]},
    options: {
      responsive: true, maintainAspectRatio: false,
      onClick: (evt, els) => { if (els.length) renderDrill(els[0].index + 1); },
      plugins: { legend: { display: false },
                 tooltip: {
                   filter: c => c.parsed.y > 0,
                   callbacks: {
                     label: c => (c.datasetIndex === 1 ? '예측 ' : '실적 ') + _fmtDivMoney(c.parsed.y) } } },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { font: { size: 10 } } },
        y: { stacked: true, beginAtZero: true, grid: { color: MM_CHART_GRID },
             ticks: { font: { size: 10 }, callback: v =>
               _divCur === 'USD' ? '$' + v : '₩' + (v / 10000).toFixed(0) + '만' } }
      }
    }
  });

  const total = monthly.reduce((a, b) => a + b, 0);
  const hasProj = monthProj.some(Boolean);
  document.getElementById('divDrill').innerHTML =
    `<div class="div-drill-head">${_divYear}년 합계: ${_fmtDivMoney(total)}` +
    (hasProj ? ' <span style="color:#FB8C00;font-size:0.76rem;">(파랑 = 실적 · 주황 = 예측분)</span>' : '') +
    ` <span style="font-weight:400;color:var(--text-muted);font-size:0.78rem;">· 월 막대를 클릭하면 종목별 내역</span></div>`;
  renderMonthGrid(monthly, monthProj);
  renderList(evs);
  renderDivNote();
}

// 월별 네모칸 + 펼침 표
function renderMonthGrid(monthly, monthProj) {
  const grid = document.getElementById('divMonthGrid');
  grid.innerHTML = monthly.map((amt, i) => {
    const has = amt > 0;
    const cls = 'div-month-box' + (has ? '' : ' empty') + ((_divActiveMonth === i + 1) ? ' active' : '');
    const amtTxt = has ? _fmtDivMoney(amt) : '—';
    return `<div class="${cls}" ${has ? `data-month="${i + 1}"` : ''}>
      <div class="m-label">${i + 1}월${monthProj[i] && has ? ' *' : ''}</div>
      <div class="m-amt">${amtTxt}</div>
    </div>`;
  }).join('');
  if (_divActiveMonth) renderMonthDetail(_divActiveMonth);
  else document.getElementById('divMonthDetail').innerHTML = '';
}

function showMonth(month) {
  _divActiveMonth = (_divActiveMonth === month) ? null : month;
  document.querySelectorAll('#divMonthGrid .div-month-box').forEach(b =>
    b.classList.toggle('active', !!(b.dataset.month && parseInt(b.dataset.month) === _divActiveMonth)));
  if (_divActiveMonth) renderMonthDetail(_divActiveMonth);
  else document.getElementById('divMonthDetail').innerHTML = '';
}

function renderMonthDetail(month) {
  const evs = (_divData.events[_divYear] || []).filter(e => e.month === month);
  const byCode = {};
  evs.forEach(e => {
    if (!byCode[e.code]) byCode[e.code] = { name: e.name, val: 0, dates: [], proj: false };
    byCode[e.code].val += _valOf(e);
    byCode[e.code].dates.push(e.date.slice(5));
    if (e.projected) byCode[e.code].proj = true;
  });
  const rows = Object.values(byCode).sort((a, b) => b.val - a.val);
  const total = rows.reduce((s, v) => s + v.val, 0);
  let html = `<div class="div-month-table"><div class="div-drill-head" style="padding:8px 12px;border-bottom:1px solid var(--border);">${month}월 배당: ${_fmtDivMoney(total)}</div>`;
  if (!rows.length) {
    html += '<div style="color:var(--text-muted);font-size:0.82rem;padding:10px 12px;">이 달은 배당이 없습니다.</div>';
  } else {
    rows.forEach(v => {
      html += `<div class="div-list-item"><span class="div-list-date" style="min-width:64px;">${v.dates.join(', ')}</span>` +
        `<span class="div-list-name">${maEsc(v.name)}${v.proj ? '<span class="div-proj-badge">예측</span>' : ''}</span>` +
        `<span class="div-list-amt">${_fmtDivMoney(v.val)}</span></div>`;
    });
  }
  html += '</div>';
  document.getElementById('divMonthDetail').innerHTML = html;
}

function renderDrill(month) {
  const evs = (_divData.events[_divYear] || []).filter(e => e.month === month);
  const byCode = {};
  evs.forEach(e => {
    if (!byCode[e.code]) byCode[e.code] = { name: e.name, val: 0, dates: [] };
    byCode[e.code].val += _valOf(e);
    byCode[e.code].dates.push(e.date.slice(5));
  });
  const rows = Object.entries(byCode).sort((a, b) => b[1].val - a[1].val);
  const total = rows.reduce((s, [, v]) => s + v.val, 0);
  let html = `<div class="div-drill-head">${month}월 배당: ${_fmtDivMoney(total)}</div>`;
  if (!rows.length) {
    html += '<div style="color:var(--text-muted);font-size:0.82rem;padding:6px 10px;">이 달은 배당이 없습니다.</div>';
  } else {
    rows.forEach(([code, v]) => {
      html += `<div class="div-drill-item"><span>${maEsc(v.name)} ` +
        `<span style="color:var(--text-muted);font-size:0.72rem;">(${v.dates.join(', ')})</span></span>` +
        `<b>${_fmtDivMoney(v.val)}</b></div>`;
    });
  }
  document.getElementById('divDrill').innerHTML = html;
}

function renderList(evs) {
  const el = document.getElementById('divCal');
  if (!evs.length) {
    el.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem;padding:10px 12px;">배당 일정이 없습니다.</div>';
    return;
  }
  // 같은 종목끼리 1행으로 묶음 — 연 합계 + 지급월 목록
  const byCode = {};
  evs.forEach(e => {
    if (!byCode[e.code]) byCode[e.code] = { name: e.name, val: 0, months: new Set(), anyProj: false };
    const g = byCode[e.code];
    g.val += _valOf(e);
    g.months.add(e.month);
    if (e.projected) g.anyProj = true;
  });
  const rows = Object.values(byCode).sort((a, b) => b.val - a.val);
  el.innerHTML = rows.map(g => {
    // 지급월 5개+ 나열은 모바일 행을 부수므로 압축(월배당/연N회). 전체 목록은 title로.
    const ms = [...g.months].sort((a, b) => a - b);
    const monthsFull = ms.map(m => m + '월').join('·');
    const months = ms.length >= 10 ? '월배당' : (ms.length > 4 ? `연 ${ms.length}회` : monthsFull);
    return `<div class="div-list-item">` +
      `<span class="div-list-date" style="width:auto;min-width:78px;" title="${monthsFull}">${months}</span>` +
      `<span class="div-list-name">${maEsc(g.name)}${g.anyProj ? '<span class="div-proj-badge">예측</span>' : ''}</span>` +
      `<span class="div-list-amt">${_fmtDivMoney(g.val)}</span>` +
    `</div>`;
  }).join('');
}

function renderDivNote() {
  const note = [];
  note.push('※ 과거 배당은 <b>현재 보유 수량</b>을 그대로 보유했다고 가정해 계산합니다.');
  note.push(`※ ${_divData.current_year}년은 실데이터가 있는 달까지는 실적, 이후 달과 ${_divData.full_proj_year}년은 종목별 최근 5년 배당성장률(CAGR) 기반 <b>예측치</b>입니다.`);
  if (_divData.has_foreign) {
    note.push('※ 해외 종목 배당은 ' +
      (_divCur === 'KRW' ? '배당 당시 환율로 원화 환산' : '원화 종목을 배당 당시 환율로 달러 환산') +
      ', 미래 예측은 현재 환율 기준입니다.');
  }
  document.getElementById('divNote').innerHTML = note.join('<br>');
}

document.addEventListener('click', e => {
  const t = e.target.closest('[data-div-tax]');
  if (t) { _divTax = t.dataset.divTax;
    document.querySelectorAll('[data-div-tax]').forEach(b => b.classList.toggle('active', b === t));
    renderDivYear(); return; }
  const c = e.target.closest('[data-div-cur]');
  if (c) { _divCur = c.dataset.divCur;
    document.querySelectorAll('[data-div-cur]').forEach(b => b.classList.toggle('active', b === c));
    renderDivYear(); return; }
  const y = e.target.closest('[data-div-year]');
  if (y) { _divYear = parseInt(y.dataset.divYear); _divActiveMonth = null;
    document.querySelectorAll('[data-div-year]').forEach(b => b.classList.toggle('active', b === y));
    renderDivYear(); return; }
  const mb = e.target.closest('#divMonthGrid .div-month-box[data-month]');
  if (mb) { showMonth(parseInt(mb.dataset.month)); }
});

// ── 자산 추이 차트 ──
let _maHistoryChart = null;
let _historyData    = null;
let _maHistoryDays  = 30;

async function loadPortfolioHistory(days) {
  _maHistoryDays = days;
  try {
    const res  = await fetch('/api/portfolio/history', { cache: 'no-store' });
    _historyData = await res.json();
    renderHistoryChart(days);
  } catch(e) {
    syncHistoryEmptyMode();
    document.getElementById('maHistoryEmpty').style.display = 'flex';
  } finally {
    document.getElementById('maHistoryLoading').style.display = 'none';
  }
}

function setHistoryPeriod(days, btn) {
  _maHistoryDays = days;
  if (btn) _maPeriodLabel = btn.textContent.trim();
  document.querySelectorAll('.ma-period-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  if (_historyData) renderHistoryChart(days);
}

// 빈 차트 안내 = 보유 종목 유무로 문구 분기 (없으면 "첫 종목 추가" CTA, 있으면 이력 없음 안내)
function syncHistoryEmptyMode() {
  const el = document.getElementById('maHistoryEmpty');
  if (el) el.classList.toggle('has-holdings', holdings.length > 0);
}

function renderHistoryChart(days) {
  const data = _historyData;
  if (!data || data.empty || !data.labels || !data.values || !data.labels.length) {
    syncHistoryEmptyMode();
    document.getElementById('maHistoryEmpty').style.display = 'flex';
    _lastHistWindow = null;
    updateHeroMetric();
    renderPerStock();
    return;
  }
  document.getElementById('maHistoryEmpty').style.display = 'none';

  let labels = data.labels;
  let values = data.values;
  if (days > 0 && labels.length > days) {
    labels = labels.slice(-days);
    values = values.slice(-days);
  }
  updateHeroMetric(values);
  renderPerStock();

  const ctx = document.getElementById('maHistoryChart').getContext('2d');
  const _brand = _cssVar('--brand') || '#0052ff';
  const _grad = ctx.createLinearGradient(0, 0, 0, 160);
  _grad.addColorStop(0, _brand + '2e'); _grad.addColorStop(1, _brand + '00');
  if (_maHistoryChart) _maHistoryChart.destroy();
  _maHistoryChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: _brand,
        backgroundColor: _grad,
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => hideAmounts ? '***원' : Math.round(ctx.parsed.y).toLocaleString() + '원'
          }
        }
      },
      scales: {
        x: { ticks: { maxTicksLimit: 6, font: { size: 11 } }, grid: { display: false } },
        y: {
          ticks: {
            maxTicksLimit: 4,
            font: { size: 11 },
            callback: v => hideAmounts ? '***' : (v >= 1e8 ? (v/1e8).toFixed(1)+'억' : (v/1e4).toFixed(0)+'만')
          }
        }
      }
    }
  });
}
