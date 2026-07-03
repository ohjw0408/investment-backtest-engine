// backtest.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 내용 무변경 이동
// 오늘 날짜 기본값
document.getElementById('btEndDate').value = new Date().toISOString().split('T')[0];

let btTickers = [];
let _btTaskId = null, _btCancelled = false;
let btCharts  = {};
const BT_TASK_KEY = 'mm_task_backtest';
const BT_RESULT_KEY = 'mm_result_backtest';
const btStateStore = window.sessionStorage;
const BT_FEE_PRESETS_URL = JSON.parse(document.getElementById('page-data').textContent).feePresetsUrl;
const BT_FEE_MARKET_LABELS = {
  domestic_stock: '국내주식',
  domestic_etf: '국내 ETF/ETN',
  us_stock: '미국주식',
};
const BT_FEE_FALLBACK_PRESETS = [
  {
    id: 'kiwoom',
    name: '키움증권',
    rates: {
      domestic_stock: { commission_pct: 0.015, display: '0.015%' },
      domestic_etf: { commission_pct: 0.015, display: '0.015%' },
      us_stock: { commission_pct: 0.25, display: '0.25%' },
    },
    notes: '대표 온라인 수수료 기준. 제비용과 세금은 별도.',
  },
  {
    id: 'toss',
    name: '토스증권',
    rates: {
      domestic_stock: { commission_pct: 0.015, display: 'KRX 0.015% / NXT 0.014%' },
      domestic_etf: { commission_pct: 0.015, display: 'KRX 0.015% / NXT 0.014%' },
      us_stock: { commission_pct: 0.1, display: '0.1%' },
    },
    notes: '조건부 이벤트와 제비용은 계좌별로 다를 수 있습니다.',
  },
];
let btBrokerFeePresets = [];

function btClearLegacyPersistentState() {
  try {
    localStorage.removeItem(BT_TASK_KEY);
    localStorage.removeItem(BT_RESULT_KEY);
  } catch(e) {}
}

function fmtKRW(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const sign = v < 0 ? '-' : '';
  const abs = Math.abs(v);
  const uk = Math.floor(abs / 1e8);
  const man = Math.floor((abs % 1e8) / 1e4);
  if (uk > 0 && man > 0) return sign + '₩' + uk.toLocaleString() + '억 ' + man.toLocaleString() + '만';
  if (uk > 0) return sign + '₩' + uk.toLocaleString() + '억';
  if (abs >= 1e4) return sign + '₩' + Math.floor(abs / 1e4).toLocaleString() + '만';
  return sign + '₩' + Math.round(abs).toLocaleString();
}
function fmtPct(v) {
  if (v === null || v === undefined) return '—';
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%';
}
function fmtPctClass(v) { return v >= 0 ? 'up' : 'down'; }

// ── 디자인 토큰 → 차트 색 바인딩 (액센트/다크 따라감) ──
function _btCss(n, fb) { const v = getComputedStyle(document.documentElement).getPropertyValue(n).trim(); return v || fb; }
function _btRgba(hex, a) {
  hex = (hex || '').trim();
  if (hex[0] !== '#' || hex.length < 7) return hex;
  const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${a})`;
}
// 차트 색 — 렌더 직전 토큰값으로 갱신(액센트/다크 반영)
let _btMuted = '#90A4AE', _btBrand = '#0052ff', _btUp = '#05b169', _btDown = '#cf202f';
function _btRefreshChartColors() {
  _btMuted = _btCss('--ds-muted', '#90A4AE');
  _btBrand = _btCss('--brand', '#0052ff');
  _btUp    = _btCss('--up', '#05b169');
  _btDown  = _btCss('--down', '#cf202f');
}

// ── 입력 ↔ 결과 뷰 전환 ──
function btShowResults() {
  document.getElementById('btInputView').style.display = 'none';
  document.getElementById('btResultView').style.display = 'block';
  window.scrollTo({ top: 0, behavior: 'auto' });
}
function btShowInput() {
  document.getElementById('btResultView').style.display = 'none';
  document.getElementById('btInputView').style.display = 'block';
}
function btEditConditions() { btShowInput(); }

// ── 결과 조건 요약 바 ──
function btBuildCondSummary(body) {
  const el = document.getElementById('btCondSummary');
  if (!el || !body) return;
  const tk = (body.tickers || []).map(t => `${t.code} ${Math.round((t.weight||0)*100)}%`).join(' · ');
  const period = (body.start_date || '') + ' ~ ' + (body.end_date || '');
  const seed = fmtKRW(body.initial_capital || 0);
  const mon = (body.monthly_contribution || 0) > 0 ? ' · 월 ' + fmtKRW(body.monthly_contribution) : '';
  const rebalMap = { none:'리밸런싱 안함', monthly:'매월 리밸', quarterly:'분기 리밸', yearly:'매년 리밸', band:'밴드 리밸' };
  const parts = [];
  if (tk) parts.push(`<span class="bt-cond-item"><b>${btE(tk)}</b></span>`);
  parts.push(`<span class="bt-cond-item">${btE(period)}</span>`);
  parts.push(`<span class="bt-cond-item">${btE(seed)}${btE(mon)}</span>`);
  parts.push(`<span class="bt-cond-item">${btE(body.dividend_mode === 'hold' ? '배당 현금보유' : '배당 재투자')} · ${btE(rebalMap[body.rebal_mode] || body.rebal_mode || '')}</span>`);
  if (window.btTaxEnabled) {
    const accs = window.taxAccounts || [];
    const types = accs.length > 1 ? accs.map(a => a.type || '위탁').join('+') : (accs[0]?.type || '위탁');
    parts.push(`<span class="bt-cond-item">세금 ON · ${btE(types)}</span>`);
  }
  if (body.fee_enabled) {
    const marketLabel = BT_FEE_MARKET_LABELS[body.fee_market] || '공통';
    const rate = Number(body.fee_rate || 0) * 100;
    parts.push(`<span class="bt-cond-item">수수료 ${btE(marketLabel)} · ${rate.toFixed(4).replace(/\.?0+$/, '')}%</span>`);
  }
  el.innerHTML = parts.join('<span class="bt-cond-sep"></span>');
  el.style.display = 'flex';
}

// ── 종목 관리 ──
// 비중 합계 바만 갱신(입력칸 재생성 없음 → 슬라이더 드래그 중 DOM 파괴 방지).
function btRefreshWeightBar() {
  const total = btTickers.reduce((s, t) => s + t.weight, 0);
  const pct   = Math.round(total * 100);
  const fill  = document.getElementById('btWeightBar');
  const label = document.getElementById('btWeightTotal');
  const warn  = document.getElementById('btWeightWarn');
  label.textContent = pct + '%';
  fill.style.width  = Math.min(pct, 100) + '%';
  if (pct === 100) {
    fill.style.background = 'var(--up)';
    label.className = 'weight-total-num ok';
    if (warn) warn.textContent = '';
  } else if (pct > 100) {
    fill.style.background = 'var(--down)';
    label.className = 'weight-total-num over';
    if (warn) warn.textContent = '⚠ 비중 합계가 100%를 초과했어요';
  } else {
    fill.style.background = 'var(--brand)';
    label.className = 'weight-total-num';
    if (warn) warn.textContent = pct > 0 ? `나머지 ${100 - pct}%는 현금으로 유지됩니다` : '';
  }
}

// 종목 추가/삭제 시에만 전체 리스트 재생성.
function updateBtWeightUI() {
  btRefreshWeightBar();
  const list = document.getElementById('btTickerList');
  if (!btTickers.length) {
    list.innerHTML = '<div class="ticker-empty" id="btTickerPlaceholder">종목을 검색해서 추가해보세요</div>';
    return;
  }
  list.innerHTML = btTickers.map((t, i) => `
    <div class="ticker-item">
      <span class="ticker-badge">${t.code}</span>
      <span class="ticker-name">${t.name || ''}</span>
      <input type="number" class="ticker-weight-input" value="${Math.round(t.weight*100)}" min="1" max="100"
        oninput="btW(this, ${i})">
      <span class="ticker-weight-pct">%</span>
      <input type="range" class="ticker-weight-slider" value="${Math.round(t.weight*100)}" min="1" max="100"
        oninput="btW(this, ${i})">
      <button class="ticker-remove-btn" onclick="btRemoveTicker(${i})">×</button>
    </div>
  `).join('');
}

// 비중 변경 — 같은 행 number↔slider 동기 + 바만 갱신(재렌더 없음, 커서/드래그 보존).
function btW(el, i) {
  const v = Math.max(1, Math.min(100, parseFloat(el.value) || 0));
  if (!btTickers[i]) return;
  btTickers[i].weight = v / 100;
  const row = el.closest('.ticker-item');
  if (row) row.querySelectorAll('.ticker-weight-input, .ticker-weight-slider').forEach(x => { if (x !== el) x.value = v; });
  btRefreshWeightBar();
}
function btRemoveTicker(i) { btTickers.splice(i, 1); updateBtWeightUI(); }

let btSearchTimer = null;
const btInput    = document.getElementById('btTickerSearch');
const btDropdown = document.getElementById('btTickerDropdown');

function badgeColor(badge) {
  if (badge === 'KR ETF' || badge === 'KOSPI' || badge === 'KOSDAQ') return '#1976D2';
  if (badge === 'US ETF' || badge === 'NASDAQ' || badge === 'NYSE')   return '#2E7D32';
  return '#78909C';
}

btInput.addEventListener('input', e => {
  const q = e.target.value.trim();
  if (!q) { btDropdown.style.display = 'none'; return; }
  clearTimeout(btSearchTimer);
  btDropdown.innerHTML = '<div style="padding:12px;font-size:0.82rem;color:var(--text-muted)">검색 중...</div>';
  btDropdown.style.display = 'block';
  btSearchTimer = setTimeout(async () => {
    const res  = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    if (!data.length) { btDropdown.innerHTML = '<div style="padding:12px;font-size:0.82rem;color:var(--text-muted)">검색 결과 없음</div>'; return; }
    btDropdown.innerHTML = data.map(item => `
      <div class="ticker-drop-item" onclick="btAddTicker('${item.code}','${item.name.replace(/'/g,"\\'")}')">
        <span class="ticker-drop-badge" style="background:${badgeColor(item.badge)}22;color:${badgeColor(item.badge)}">${item.badge}</span>
        <div>
          <div class="ticker-drop-code">${item.code}</div>
          <div class="ticker-drop-name">${item.name}</div>
        </div>
      </div>`).join('');
  }, 250);
});

document.addEventListener('click', e => {
  if (!btInput.closest('.ticker-search-box').contains(e.target))
    btDropdown.style.display = 'none';
});

function btAddTicker(code, name) {
  if (btTickers.find(t => t.code === code)) { btDropdown.style.display='none'; return; }
  const n = btTickers.length + 1;
  const w = Math.round(100 / n) / 100;
  btTickers.forEach(t => t.weight = w);
  btTickers.push({ code, name, weight: parseFloat((1 - w*(n-1)).toFixed(2)) });
  btInput.value = '';
  btDropdown.style.display = 'none';
  updateBtWeightUI();
}

// 포트폴리오 즐겨찾기 (B1) — 내부 weight는 0~1, 위젯 규약은 % (0~100)
if (window.MMFav) MMFav.init({
  mount: 'favBar',
  getTickers: () => btTickers.map(t => ({
    code: t.code, name: t.name || t.code, badge: t.badge || '',
    weight: Math.round(t.weight * 100),
  })),
  setTickers: (list) => {
    btTickers = list.map(t => ({
      code: t.code, name: t.name || t.code,
      weight: (Number(t.weight) || 0) / 100,
    }));
    updateBtWeightUI();
  },
});

// 힌트
document.getElementById('btSeed').addEventListener('input', function() {
  document.getElementById('btSeedHint').textContent = '₩' + (parseFloat(this.value)||0).toLocaleString();
});
document.getElementById('btMonthly').addEventListener('input', function() {
  document.getElementById('btMonthlyHint').textContent = '₩' + (parseFloat(this.value)||0).toLocaleString();
});

// ── 세금 토글 ──
window.btTaxEnabled = false;
window.btTaxProfile = {};
// 멀티계좌 공용모듈(multi_account_ui.js) 결합점 — 백테 포트폴리오·금액 DOM 주입.
window.taxAccounts = [];
window.MMTAX = {
  portfolioTickers: () => btTickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: (t.weight || 0) * 100 })),
  totalInitId: 'btSeed',
  totalMonId:  'btMonthly',
};
function btToggleAdvanced(force) {
  const body = document.getElementById('btMoreoptBody');
  const tog  = document.getElementById('btMoreoptToggle');
  if (!body || !tog) return;
  const open = force === undefined ? !body.classList.contains('open') : !!force;
  body.classList.toggle('open', open);
  tog.classList.toggle('open', open);
}

function toggleBtTax() {
  window.btTaxEnabled = !window.btTaxEnabled;
  window.taxEnabled   = window.btTaxEnabled;  // 모듈이 참조
  const on = window.btTaxEnabled;
  document.getElementById('btTaxWrap').style.background = on ? 'var(--brand)' : 'var(--ds-hairline)';
  document.getElementById('btTaxThumb').style.left      = on ? '23px' : '3px';
  document.getElementById('btTaxLabel').textContent     = on ? 'ON' : 'OFF';
  document.getElementById('btTaxLabel').style.color     = on ? 'var(--brand-text)' : 'var(--ds-muted)';
  document.getElementById('btTaxPanel').style.display   = on ? 'block' : 'none';
  if (on) {
    if (window.taxAccounts.length === 0) addTaxAccount();
    else renderTaxAccounts();
    loadBtTaxProfile();
  }
}

async function loadBtTaxProfile() {
  let settings = {};
  try {
    const me = await fetch('/api/me').then(r => r.json());
    if (me.logged_in) {
      const res = await fetch('/api/settings/tax');
      if (res.ok) settings = await res.json();
    }
  } catch(e) {}
  if (!settings || Object.keys(settings).length === 0) {
    try { settings = JSON.parse(localStorage.getItem('domino_tax_settings') || '{}'); } catch(e) { settings = {}; }
  }
  window.btTaxProfile = settings || {};
  const info = document.getElementById('btTaxProfileInfo');
  if (!info) return;
  const hasProfile = window.btTaxProfile.earned_income != null || window.btTaxProfile.age != null;
  if (!hasProfile) {
    info.innerHTML = '저장된 세금 설정이 없습니다. <a href="/tax-settings" style="color:var(--blue);">세금 설정</a>에서 입력하세요.';
    return;
  }
  info.innerHTML = `연소득 ${fmtKRW(window.btTaxProfile.earned_income || 0)} · 나이 ${window.btTaxProfile.age || 40}세 <a href="/tax-settings" style="color:var(--blue);margin-left:6px;">수정</a>`;
}

// 멀티계좌 페이로드 — 계좌 2개 이상일 때만. 계좌 1은 상단 포트폴리오/금액 사용.
function buildBtAccountsPayload(rebalMode, bandWidth, dividendMode) {
  const accs = window.taxAccounts || [];
  if (accs.length <= 1) return null;
  const renewalOn = document.getElementById('isaRenewalCheck')?.checked ?? false;
  const feeOn = document.getElementById('feeEnabledChk')?.checked ?? false;
  const primary = {
    type: accs[0]?.type || '위탁',
    initial_capital: parseFloat(document.getElementById('btSeed').value) || 0,
    monthly_contribution: parseFloat(document.getElementById('btMonthly').value) || 0,
    tickers: btTickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: t.weight })),
    rebal_mode: rebalMode, band_width: bandWidth, dividend_mode: dividendMode,
    isa_renewal: renewalOn && (accs[0]?.type === 'ISA'),
    priority: Number(accs[0]?.priority ?? 1),
    ...(feeOn ? { fee_rate: _mmAccountFeePct(accs[0]) / 100 } : {}),
  };
  const accounts = [primary];
  for (let i = 1; i < accs.length; i++) {
    const accTickers = ensureAccountTickers(i);
    if (accTickers.length === 0) { mmToast(`계좌 ${i + 1}에 종목을 최소 1개 추가해주세요.`, 'err'); return false; }
    if (accTickers.reduce((s, t) => s + (Number(t.weight) || 0), 0) > 100) {
      mmToast(`계좌 ${i + 1}의 비중 합계가 100%를 초과했어요.`, 'err'); return false;
    }
    accounts.push({
      type: accs[i].type || '위탁',
      initial_capital: Number(accs[i].initial_capital || 0),
      monthly_contribution: Number(accs[i].monthly_contribution || 0),
      tickers: accTickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: (Number(t.weight) || 0) / 100 })),
      rebal_mode: rebalMode, band_width: bandWidth, dividend_mode: dividendMode,
      isa_renewal: renewalOn && (accs[i].type === 'ISA'),
      priority: Number(accs[i].priority ?? (i + 1)),
      ...(feeOn ? { fee_rate: _mmAccountFeePct(accs[i]) / 100 } : {}),
    });
  }
  return accounts;
}

// 백테 멀티계좌 결과 — 단일 역사윈도우라 계좌별 = 스칼라 종료값(분포 아님). + 절세·자금이동.
function btRenderMultiAccount(data) {
  const wrap = document.getElementById('btMultiAccountSummary');
  if (!wrap) return;
  const accts = data.accounts || [];
  if (!data.multi_account || accts.length <= 1) { wrap.style.display = 'none'; wrap.innerHTML = ''; return; }

  const rows = accts.map((a, i) => `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;gap:8px;">
        <div style="font-size:0.82rem;font-weight:800;color:var(--text);">계좌 ${i + 1}</div>
        <div style="font-size:0.72rem;color:var(--text-muted);">${a.type || '위탁'}</div>
      </div>
      <div style="font-size:0.95rem;font-weight:800;color:var(--text);">${fmtKRW(a.end_value)}</div>
      ${a.tax_paid ? `<div style="font-size:0.68rem;color:var(--red);margin-top:2px;">세금 ${fmtKRW(a.tax_paid)}</div>` : ''}
    </div>`).join('');

  // 절세액(세금 ON) — 계산기와 동일 savings 스키마.
  let savingsHtml = '';
  const sv = data.savings;
  if (sv && sv.combined && sv.combined.brokerage_assumed_tax > 0) {
    const c = sv.combined;
    const totalSaving = (c.tax_saving || 0) + (c.gain_harvest_saving || 0);
    savingsHtml = `
      <div style="margin-top:10px;padding:12px;background:var(--green-pale);border:1px solid var(--green-light);border-radius:8px;">
        <div style="font-size:0.8rem;font-weight:800;color:var(--green);margin-bottom:8px;">💰 세금 절감 효과</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
          <div><div style="font-size:0.68rem;color:var(--green);">전체 위탁 가정 세금</div><div style="font-size:0.9rem;font-weight:800;color:var(--green);">${fmtKRW(c.brokerage_assumed_tax)}</div></div>
          <div><div style="font-size:0.68rem;color:var(--green);">실제 세금</div><div style="font-size:0.9rem;font-weight:800;color:var(--green);">${fmtKRW(c.actual_tax)}</div></div>
          <div><div style="font-size:0.68rem;color:var(--green);">절세액</div><div style="font-size:0.98rem;font-weight:900;color:var(--green);">약 ${fmtKRW(totalSaving)}</div></div>
        </div>
      </div>`;
  }

  // 자금이동·세액공제(g2)
  let g2Html = '';
  const g2 = data.g2;
  if (g2) {
    const tl = g2.transfer_log || [];
    const maturity = tl.filter(t => t.type === 'maturity').length;
    const comp = g2.comprehensive_years || [];
    const items = [];
    if (maturity) items.push(`ISA 풍차 만기 ${maturity}회 → 우선순위대로 분배`);
    if (comp.length) items.push(`금융소득종합과세 대상연도: ${comp.join(', ')}`);
    if (g2.annual_deduction_credit > 0) items.push(`연 납입 세액공제 환급: ${fmtKRW(g2.annual_deduction_credit)}`);
    if (g2.pension_transfer_credit_total > 0) items.push(`ISA→연금 이전 세액공제: ${fmtKRW(g2.pension_transfer_credit_total)}`);
    if (items.length) g2Html = `
      <div style="margin-top:10px;padding:10px 12px;background:var(--green-pale);border:1px solid var(--green-light);border-radius:8px;">
        <div style="font-size:0.78rem;font-weight:800;color:var(--green);margin-bottom:6px;">자금 이동 · 세액공제</div>
        ${items.map(t => `<div style="font-size:0.76rem;color:var(--green);margin-top:3px;">• ${t}</div>`).join('')}
      </div>`;
  }

  wrap.innerHTML = `
    <div class="bt-card" style="margin-bottom:0;">
      <div class="bt-card-title">계좌별 종료 자산</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;">${rows}</div>
      ${savingsHtml}
      ${g2Html}
    </div>`;
  wrap.style.display = 'block';
}

// ── 거래수수료 (D4) ──
function btFeeMarket() {
  return document.querySelector('input[name="feeMarket"]:checked')?.value || 'domestic_stock';
}
function btFeePreset() {
  const id = document.getElementById('feePreset')?.value || 'custom';
  return btBrokerFeePresets.find(p => p.id === id) || null;
}
function btFeeRateFor(preset, market) {
  const rate = preset?.rates?.[market]?.commission_pct;
  return Number.isFinite(Number(rate)) ? Number(rate) : null;
}
function btFeeDisplayFor(preset, market) {
  return preset?.rates?.[market]?.display || (btFeeRateFor(preset, market) != null ? btFeeRateFor(preset, market) + '%' : '');
}
function renderBrokerFeePresetOptions() {
  const sel = document.getElementById('feePreset');
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = btBrokerFeePresets.map(p => `<option value="${p.id}">${btE(p.name)}</option>`).join('') +
    '<option value="custom">직접입력</option>';
  sel.value = btBrokerFeePresets.some(p => p.id === prev) ? prev : (btBrokerFeePresets[0]?.id || 'custom');
  applyFeePreset();
}
async function loadBrokerFeePresets() {
  try {
    const res = await fetch(BT_FEE_PRESETS_URL, { cache: 'no-store' });
    const data = res.ok ? await res.json() : {};
    btBrokerFeePresets = Array.isArray(data.presets) && data.presets.length ? data.presets : BT_FEE_FALLBACK_PRESETS;
  } catch(e) {
    btBrokerFeePresets = BT_FEE_FALLBACK_PRESETS;
  }
  window.MM_BROKER_FEE_PRESETS = btBrokerFeePresets;
  renderBrokerFeePresetOptions();
}
function toggleFeePanel() {
  const on = document.getElementById('feeEnabledChk')?.checked;
  const body = document.getElementById('feePanelBody');
  const label = document.getElementById('btFeeLabel');
  if (body) body.classList.toggle('is-open', !!on);
  if (label) {
    label.textContent = on ? 'ON' : 'OFF';
    label.style.color = on ? 'var(--brand-text)' : 'var(--ds-muted)';
  }
  // 멀티계좌면 카드별 수수료 입력 노출/숨김 위해 재렌더.
  if (window.taxEnabled && (window.taxAccounts || []).length > 1) renderTaxAccounts();
}
function applyFeePreset(v) {
  // 옛 onchange="applyFeePreset('0.015')" 호출도 견딘다.
  if (v && v !== 'custom' && !btBrokerFeePresets.some(p => p.id === v)) {
    const legacyRate = Number(v);
    if (Number.isFinite(legacyRate)) {
      const legacyInp = document.getElementById('feeRateInput');
      if (legacyInp) legacyInp.value = legacyRate;
      return;
    }
  }
  if (v) {
    const sel = document.getElementById('feePreset');
    if (sel) sel.value = v;
  }
  const preset = btFeePreset();
  const market = btFeeMarket();
  const inp = document.getElementById('feeRateInput');
  const meta = document.getElementById('feePresetMeta');
  if (!preset) {
    if (meta) meta.innerHTML = '<b>직접입력</b><br>매수·매도 공통 적용. 국내 개별주식 매도 거래세는 별도 반영됩니다.';
    return;
  }
  const rate = btFeeRateFor(preset, market);
  if (inp && rate != null) inp.value = rate;
  if (meta) {
    const marketLabel = BT_FEE_MARKET_LABELS[market] || market;
    const display = btFeeDisplayFor(preset, market);
    meta.innerHTML = `<b>${btE(preset.name)} · ${btE(marketLabel)} ${btE(display)}</b><br>${btE(preset.notes || '이벤트, 협의수수료, 제비용과 세금은 실제 계좌 조건에 따라 달라질 수 있습니다.')}`;
  }
  if (window.taxEnabled && (window.taxAccounts || []).length > 1) renderTaxAccounts();
}
function markFeePresetCustom() {
  const sel = document.getElementById('feePreset');
  if (sel) sel.value = 'custom';
  const meta = document.getElementById('feePresetMeta');
  if (meta) meta.innerHTML = '<b>직접입력</b><br>매수·매도 공통 적용. 국내 개별주식 매도 거래세는 별도 반영됩니다.';
}
function renderFeeSummary(containerId, totalFees) {
  const el = document.getElementById(containerId);
  if (!el) return;
  let slot = el.querySelector(':scope > #mmFeeSummary');
  if (totalFees == null) { if (slot) slot.remove(); return; }
  if (!slot) { slot = document.createElement('div'); slot.id = 'mmFeeSummary'; el.appendChild(slot); }
  const won = Math.round(Number(totalFees) || 0).toLocaleString();
  slot.innerHTML = `
    <div style="margin-top:12px;padding:10px 14px;background:var(--bg,#f5f5f5);border:1px solid var(--border,#ddd);border-radius:9px;font-size:0.84rem;color:var(--text,#222);">
      💸 총 지불 거래수수료 <b>₩${won}</b> <span style="color:var(--text-muted,#888);font-size:0.78rem;">(매수·매도 누적)</span>
    </div>`;
}

// ── 실행 ──
async function runBacktest(_limitOverride) {
  const total = Math.round(btTickers.reduce((s,t) => s+t.weight, 0) * 100);
  if (!btTickers.length) { mmToast('종목을 추가해주세요.', 'err'); return; }
  if (total !== 100)     { mmToast(`비중 합계가 ${total}%입니다. 100%로 맞춰주세요.`, 'err'); return; }

  const startDate = document.getElementById('btStartDate').value;
  const endDate   = document.getElementById('btEndDate').value;
  if (!startDate || !endDate || startDate >= endDate) { mmToast('기간을 올바르게 설정해주세요.', 'err'); return; }

  // 재실행(결과 뷰)에서도 진행바가 보이도록 입력 뷰로 전환 후 진행 표시
  btShowInput();
  document.getElementById('btRunBtn').disabled = true;
  btShowProgressUI();

  try {
    if (window.btTaxEnabled && (!window.btTaxProfile || Object.keys(window.btTaxProfile).length === 0)) {
      await loadBtTaxProfile();
    }
    const taxProfile = window.btTaxProfile || {};
    window._btLastBody = {
      tickers:              btTickers.map(t => ({ code: t.code, name: t.name, weight: t.weight })),
      start_date:           startDate,
      end_date:             endDate,
      initial_capital:      parseFloat(document.getElementById('btSeed').value) || 0,
      monthly_contribution: parseFloat(document.getElementById('btMonthly').value) || 0,
      dividend_mode:        document.querySelector('input[name="btDividend"]:checked').value,
      rebal_mode:           document.querySelector('input[name="btRebal"]:checked').value,
      band_width:           Number(document.getElementById('btBandSlider').value) / 100,
      use_synthetic:        document.getElementById('btUseSyntheticCheck')?.checked ?? false,
    };
    const accs = window.taxAccounts || [];
    const acct0Type = (window.btTaxEnabled && accs.length) ? (accs[0].type || '위탁') : '위탁';
    const accountsPayload = window.btTaxEnabled
      ? buildBtAccountsPayload(window._btLastBody.rebal_mode, window._btLastBody.band_width, window._btLastBody.dividend_mode)
      : null;
    if (accountsPayload === false) { btHideProgressUI(); document.getElementById('btRunBtn').disabled = false; return; }

    const submitBody = {
      ...window._btLastBody,
      tax_enabled:          window.btTaxEnabled || false,
      account_type:         acct0Type,
      gain_harvesting: window.btTaxEnabled && accs.some(a => a.type === '위탁') && (document.getElementById('gainHarvestingCheck')?.checked ?? false),
      isa_renewal:     window.btTaxEnabled && (document.getElementById('isaRenewalCheck')?.checked ?? false),
      user_settings: (window.btTaxEnabled) ? {
        age:           parseInt(taxProfile.age || 40),
        earned_income: parseInt(taxProfile.earned_income || 0),
        isa_type:      taxProfile.isa_type || 'general',
        pension_age:   parseInt(taxProfile.pension_age || 65),
      } : {},
    };
    if (accountsPayload && accountsPayload.length > 1) {
      submitBody.accounts = accountsPayload;
      submitBody.distribution_policy = buildDistributionPolicy(accountsPayload);
      submitBody.reinvest_tax_credit = document.getElementById('taxDeductionReinvest')?.checked ?? false;
      submitBody.manual_comprehensive_years = [];
    }
    // 납입 한도 soft 경고 — 강행 재시도 또는 "오늘 하루 묻지 않기"면 override
    if (submitBody.tax_enabled && (_limitOverride || window.MMLimit?.skipToday())) {
      submitBody.allow_limit_override = true;
    }
    // D4 거래수수료 — opt-in 시 탭레벨 수수료율(decimal) 동봉
    if (document.getElementById('feeEnabledChk')?.checked) {
      submitBody.fee_enabled = true;
      submitBody.fee_rate = (Number(document.getElementById('feeRateInput').value) || 0) / 100;
      submitBody.fee_market = btFeeMarket();
      submitBody.fee_preset = document.getElementById('feePreset')?.value || 'custom';
    }
    const res = await fetch('/api/backtest/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(submitBody),
    });
    const resData = await res.json();
    if (res.status === 429) throw new Error(resData.error);
    const { task_id } = resData;
    _btTaskId = task_id;
    btStateStore.removeItem(BT_RESULT_KEY);
    btStateStore.setItem(BT_TASK_KEY, JSON.stringify({task_id, timestamp: Date.now()}));
    await btPollTask(task_id);
  } catch(e) {
    if (e.message !== 'CANCELLED') {
      mmToast('오류: ' + e.message, 'err');
    }
    btShowInput();
  } finally {
    btStateStore.removeItem(BT_TASK_KEY);
    _btTaskId = null;
    document.getElementById('btRunBtn').disabled = false;
    btHideProgressUI();
  }
}

async function btPollTask(taskId, maxWait = 600000) {
  const deadline = Date.now() + maxWait;
  let _initialRank = null;
  while (Date.now() < deadline) {
    if (_btCancelled) { _btCancelled = false; throw new Error('CANCELLED'); }
    await new Promise(r => setTimeout(r, 1500));
    if (_btCancelled) { _btCancelled = false; throw new Error('CANCELLED'); }
    try {
      const res  = await fetch(`/api/task/${taskId}`);
      const data = await res.json();

      if (data.status === 'PENDING') {
        const rank = data.queue_rank;
        if (rank !== null && rank !== undefined) {
          if (_initialRank === null) _initialRank = Math.max(rank, 1);
          const rawPct = Math.round((_initialRank - rank) / _initialRank * 100);
          const pct = Math.min(99, Math.max(8, rawPct));
          btUpdateProgressUI({ phase: '대기 중', queueRank: rank, isWaiting: true, avgDuration: data.avg_duration, percent: pct, current: 0, total: 0, eta: null });
        } else {
          btUpdateProgressUI({ phase: '준비 중', percent: 0, isWaiting: false, current: 0, total: 0, eta: null });
        }
        continue;
      }
      if (data.status === 'PROGRESS') {
        btUpdateProgressUI({
          phase:    data.phase === 'preparing' ? '데이터 준비 중' : '분석 중...',
          isWaiting: false,
          percent:  data.percent || 0,
          current:  data.current || 0,
          total:    data.total   || 0,
          eta:      data.eta,
        });
        continue;
      }
      if (data.status === 'SUCCESS') {
        btHideProgressUI();
        const btResult = data.result?.result ?? data.result;
        renderBacktest(btResult);
        window.MMLimit?.attach('btResultContent', btResult?.limit_warnings);
        renderFeeSummary('btResultContent', btResult?.total_fees);
        try { btStateStore.setItem(BT_RESULT_KEY, JSON.stringify({result: btResult, body: window._btLastBody, ts: Date.now()})); } catch(e) {}
        return;
      }
      if (data.status === 'CANCELLED') {
        btHideProgressUI();
        btShowInput();
        return;
      }
      if (data.status === 'FAILURE') {
        btHideProgressUI();
        btShowInput();
        const _lc = window.MMLimit?.parseError(data.error);
        if (_lc) {
          if (await window.MMLimit.confirm(_lc.violations)) runBacktest(true);
          return;
        }
        mmToast('오류: ' + (data.error || '알 수 없는 오류'), 'err');
        return;
      }
    } catch(e) {
      if (e.message === 'CANCELLED') { btHideProgressUI(); btShowInput(); return; }
      btHideProgressUI();
      btShowInput();
      mmToast('폴링 오류: ' + e.message, 'err');
      return;
    }
  }
  btHideProgressUI();
  btShowInput();
  mmToast('시간 초과: 분석이 너무 오래 걸립니다.', 'err');
}

function btShowProgressUI() {
  document.getElementById('btLoading').style.display = 'block';
  btUpdateProgressUI({ phase: '준비 중', isWaiting: false, percent: 0, current: 0, total: 0, eta: null });
}

function _btSetAnim(barEl) {
  if (!barEl || barEl.dataset.anim === '1') return;
  barEl.style.transition = 'none';
  barEl.style.animation  = 'mm-indeterminate 1.4s ease-in-out infinite';
  barEl.style.width      = '40%';
  barEl.dataset.anim     = '1';
}
function btUpdateProgressUI({ phase, queueRank, isWaiting, avgDuration, percent, current, total, eta }) {
  const phaseEl  = document.getElementById('btProgressPhase');
  const barEl    = document.getElementById('btProgressBar');
  const detailEl = document.getElementById('btProgressDetail');
  const etaEl    = document.getElementById('btProgressEta');
  if (isWaiting) {
    if (barEl) { barEl.dataset.anim = ''; barEl.style.animation = ''; barEl.style.transition = 'width 0.5s'; barEl.style.left = '0%'; barEl.style.width = percent + '%'; }
    if (phaseEl)  phaseEl.textContent  = queueRank > 0 ? `⏳ 내 앞에 ${queueRank}개 대기 중 (${percent}%)` : `⏳ 곧 시작됩니다...`;
    if (detailEl) detailEl.textContent = '앞 계산 완료 후 자동으로 시작됩니다';
    const w = queueRank * (avgDuration || 30);
    const wm = Math.floor(w / 60), ws = w % 60;
    if (etaEl) etaEl.textContent = queueRank > 0 ? (wm > 0 ? `약 ${wm}분 ${ws}초 후 시작 예상` : `약 ${ws}초 후 시작 예상`) : '';
  } else if (percent > 0) {
    if (barEl) { barEl.dataset.anim = ''; barEl.style.animation = ''; barEl.style.transition = 'width 0.4s ease'; barEl.style.left = '0%'; barEl.style.width = percent + '%'; }
    if (phaseEl)  phaseEl.textContent  = `🔄 ${phase || '계산 중'} (${percent}%)`;
    if (detailEl) detailEl.textContent = total > 0 ? `${current} / ${total} 케이스` : '계산 중...';
    if (eta != null) { const m = Math.floor(eta/60), s = eta%60; if (etaEl) etaEl.textContent = m > 0 ? `약 ${m}분 ${s}초 남음` : `약 ${s}초 남음`; }
  } else {
    if (phaseEl)  phaseEl.textContent  = '🔄 준비 중...';
    _btSetAnim(barEl);
    if (detailEl) detailEl.textContent = '가격 데이터 로딩 중...';
    if (etaEl)    etaEl.textContent    = '';
  }
}

function btHideProgressUI() {
  document.getElementById('btLoading').style.display = 'none';
}

function btRestoreForm(body) {
  if (!body) return;
  if (body.tickers?.length) {
    btTickers.length = 0;
    body.tickers.forEach(t => btTickers.push({code: t.code, name: t.name || t.code, weight: t.weight}));
    updateBtWeightUI();
  }
  const set = (id, v) => { const el = document.getElementById(id); if (el && v !== undefined) el.value = v; };
  set('btStartDate', body.start_date);
  set('btEndDate', body.end_date);
  set('btSeed', body.initial_capital);
  set('btMonthly', body.monthly_contribution);
  if (body.initial_capital !== undefined) document.getElementById('btSeedHint').textContent = '₩' + (body.initial_capital||0).toLocaleString();
  if (body.monthly_contribution !== undefined) document.getElementById('btMonthlyHint').textContent = '₩' + (body.monthly_contribution||0).toLocaleString();
  if (body.dividend_mode) { const el = document.querySelector(`input[name="btDividend"][value="${body.dividend_mode}"]`); if (el) el.checked = true; }
  if (body.rebal_mode) {
    const el = document.querySelector(`input[name="btRebal"][value="${body.rebal_mode}"]`);
    if (el) { el.checked = true; document.getElementById('btBandSettings').style.display = body.rebal_mode === 'band' ? 'block' : 'none'; }
  }
  if (body.band_width) {
    const pct = Math.round(body.band_width * 100);
    document.getElementById('btBandSlider').value = pct;
    document.getElementById('btBandLabel').textContent = pct + '%';
    document.getElementById('btBandNoteVal').textContent = pct + '%';
  }
  if (body.fee_enabled) {
    const chk = document.getElementById('feeEnabledChk');
    if (chk) chk.checked = true;
    if (body.fee_market) {
      const market = document.querySelector(`input[name="feeMarket"][value="${body.fee_market}"]`);
      if (market) market.checked = true;
    }
    const preset = document.getElementById('feePreset');
    if (preset && body.fee_preset) preset.value = body.fee_preset;
    toggleFeePanel();
    applyFeePreset();
    const inp = document.getElementById('feeRateInput');
    if (inp && body.fee_rate != null) inp.value = (Number(body.fee_rate) * 100).toFixed(4).replace(/\.?0+$/, '');
  }
  if (body.use_synthetic) { const s = document.getElementById('btUseSyntheticCheck'); if (s) s.checked = true; }
  // 고급 옵션 중 하나라도 켜져 있으면 펼쳐서 복원 상태가 보이게
  if (body.fee_enabled || body.use_synthetic || body.tax_enabled) btToggleAdvanced(true);
}

async function btCancelTask() {
  _btCancelled = true;
  const tid = _btTaskId;
  if (tid) {
    try { await fetch(`/api/task/${tid}/cancel`, {method:'POST'}); } catch(e) {}
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  btClearLegacyPersistentState();
  await loadBrokerFeePresets();
  toggleFeePanel();

  document.querySelectorAll('input[name="btRebal"]').forEach(r => {
    r.addEventListener('change', () => {
      document.getElementById('btBandSettings').style.display = r.value === 'band' ? 'block' : 'none';
    });
  });
  document.getElementById('btBandSlider').addEventListener('input', e => {
    document.getElementById('btBandLabel').textContent   = e.target.value + '%';
    document.getElementById('btBandNoteVal').textContent = e.target.value + '%';
  });

  // 외부(투자대가·예시 등)에서 넘어온 프리로드 → 폼 채움. autorun이면 자동 실행, 아니면 입력 화면만.
  const preloadRaw = btStateStore.getItem('mm_bt_preload');
  if (preloadRaw) {
    btStateStore.removeItem('mm_bt_preload');
    try {
      const p = JSON.parse(preloadRaw);
      if (p && p.tickers && p.tickers.length) {
        btRestoreForm(p);
        if (p.autorun) { runBacktest(); return; }
        btShowInput(); return;  // 프리로드만: 폼 채우고 입력 화면 표시(자동 실행 X, 직전 결과 캐시 무시)
      }
    } catch(e) {}
  }

  const taskSaved = btStateStore.getItem(BT_TASK_KEY);
  if (taskSaved) {
    let state;
    try { state = JSON.parse(taskSaved); } catch(e) { btStateStore.removeItem(BT_TASK_KEY); }
    if (state && Date.now() - state.timestamp < 3600000) {
      _btTaskId = state.task_id;
      document.getElementById('btRunBtn').disabled = true;
      btShowProgressUI();
      try {
        await btPollTask(state.task_id);
      } catch(e) {
        btShowInput();
      } finally {
        btStateStore.removeItem(BT_TASK_KEY);
        _btTaskId = null;
        document.getElementById('btRunBtn').disabled = false;
        btHideProgressUI();
      }
      return;
    }
    btStateStore.removeItem(BT_TASK_KEY);
  }

  const resultSaved = btStateStore.getItem(BT_RESULT_KEY);
  if (resultSaved) {
    try {
      const {result, body, ts} = JSON.parse(resultSaved);
      if (Date.now() - ts < 7200000) {
        renderBacktest(result);
        btRestoreForm(body);
        window._btLastBody = body;
      } else {
        btStateStore.removeItem(BT_RESULT_KEY);
      }
    } catch(e) { btStateStore.removeItem(BT_RESULT_KEY); }
  }
});

// ── 렌더링 ──
function renderBacktest(data) {
  btShowResults();
  _btRefreshChartColors();
  document.getElementById('btResultContent').style.display = 'block';
  btBuildCondSummary(window._btLastBody);

  // 가상 데이터 경고 배너
  const btSynthBanner = document.getElementById('btSynthWarningBanner');
  const btSynthDetail = document.getElementById('btSynthWarningDetail');
  if (btSynthBanner && btSynthDetail) {
    const si   = data.synthetic_info || {};
    const keys = Object.keys(si);
    if (data.used_synthetic && keys.length > 0) {
      btSynthDetail.innerHTML = keys.map(code => {
        const info = si[code];
        return `${code}: ${info.date_from || '?'} ~ ${info.date_to || '?'} (${info.rows_added || 0}행 추정)`;
      }).join('<br>');
      btSynthBanner.style.display = 'block';
    } else {
      btSynthBanner.style.display = 'none';
    }
  }

  // 종합과세 분할매도 패널 (Phase 2e)
  window._btSplitSaleData = data.split_sale_plan || null;
  const splitPanel = document.getElementById('btSplitSalePanel');
  if (splitPanel) {
    const gain = data.kr_foreign_unrealized_gain || 0;
    if (data.tax_enabled && gain > 20_000_000) {
      document.getElementById('btKrForeignGain').textContent = fmtKRW(gain);
      splitPanel.style.display = 'block';
      btUpdateSplitPlan(document.getElementById('btSplitYearsSlider')?.value || 5);
    } else {
      splitPanel.style.display = 'none';
    }
  }

  const m = data.metrics;

  // 히어로: 최종 자산 + 총수익률·CAGR
  document.getElementById('btHeroValue').textContent = fmtKRW(m.end_value);
  document.getElementById('btHeroSub').innerHTML =
    `<span class="${fmtPctClass(m.total_return)}">총 수익률 ${fmtPct(m.total_return)}</span>` +
    `<span class="${fmtPctClass(m.cagr)}">CAGR ${fmtPct(m.cagr)}</span>`;

  // 보조 지표
  document.getElementById('btMetrics').innerHTML = [
    { label: '총 납입금',  value: fmtKRW(m.total_invested),  cls: '', desc: '초기 투자금 + 월 적립금을 모두 더한 원금.' },
    { label: 'MDD',       value: fmtPct(m.mdd),             cls: 'down', desc: '최대 낙폭 — 고점 대비 가장 크게 떨어진 폭. 0에 가까울수록 방어적.' },
    { label: 'Sharpe',    value: m.sharpe ? m.sharpe.toFixed(2) : '—', cls: '', desc: '위험(변동성) 1단위당 수익. 높을수록 위험 대비 효율적.' },
    { label: '총 배당금', value: fmtKRW(m.total_dividend),  cls: '', desc: '시뮬레이션 기간 동안 받은 배당금 합계.' },
    { label: '분석 기간', value: m.years ? m.years.toFixed(1) + '년' : '—', cls: '', desc: '시뮬레이션이 다룬 총 기간.' },
  ].map(item => `
    <div class="metric-item">
      <div class="metric-label" title="${item.desc}">${item.label} <span style="opacity:0.45;font-weight:400;">ⓘ</span></div>
      <div class="metric-value ${item.cls}">${item.value}</div>
    </div>
  `).join('');

  // 공유 버튼 표시 + 데이터 저장
  try {
    const body = window._btLastBody || {};
    const tickers = (body.tickers || []).map(t => `${t.code} ${t.weight}%`).join('+') || '';
    const startDate = (body.start_date || '').slice(0,7);
    const endDate   = (body.end_date   || '').slice(0,7);
    const rawPV = (data.history || []).map(h => h.portfolio_value);
    window._btShareData = {
      t: 'bt',
      label: tickers,
      period: startDate && endDate ? startDate + ' ~ ' + endDate : '',
      m: {
        cagr:         +((m.cagr         || 0) * 100).toFixed(2),
        mdd:          +((m.mdd          || 0) * 100).toFixed(2),
        sharpe:       +(m.sharpe        || 0).toFixed(3),
        total_return: +((m.total_return || 0) * 100).toFixed(2),
        years:        +(m.years         || 0).toFixed(1),
        end_v: Math.round((m.end_value      || 0) / 10000),
        inv:   Math.round((m.total_invested || 0) / 10000),
        div:   Math.round((m.total_dividend || 0) / 10000),
        sv_mn: rawPV.length ? Math.round(Math.min(...rawPV) / 10000) : 0,
        sv_mx: rawPV.length ? Math.round(Math.max(...rawPV) / 10000) : 0,
      },
      spark:  downsample(rawPV, 80),
      annual: (data.annual_returns || []).map(a => ({y: a.year, r: +(a.return * 100).toFixed(1)})),
      dd:     downsampleDd((data.history || []).map(h => +(h.drawdown * 100).toFixed(1)), 80),
    };
  } catch(e) {}
  document.getElementById('btShareBtns').style.display = 'flex';

  // 멀티계좌 계좌별 종료자산 + 절세·자금이동
  btRenderMultiAccount(data);

  // 가치 추이 차트
  renderValueChart(data.history);

  // 연간 수익률
  renderAnnualChart(data.annual_returns);

  // 낙폭 차트
  renderDrawdownChart(data.history);

  // 연간 배당금 + 배당 성장률 (낙폭 아래)
  renderAnnualDividendChart(data.annual_dividends, m.total_dividend);
  renderDividendGrowthChart(data.annual_dividends, window._btLastBody || {});

  // 심화 분석 (롤링/분포) — P2
  renderRolling(data.rolling);
}

// ════════ 심화 분석 (롤링/분포) — P2 ════════
let _btRoll = null, _btRealOn = false, _btInfl = 0.02;

function btDeflate(cagr) {
  // 실질 CAGR = (1+명목)/(1+물가) - 1. cagr=소수, null 통과.
  if (cagr === null || cagr === undefined) return cagr;
  return _btRealOn ? (1 + cagr) / (1 + _btInfl) - 1 : cagr;
}

// 합성(추정) 구간 강조색 — 흐린 회색 대신 진한 앰버(가독성 + 다른 탭과 결 맞춤)
function _btEstColor() { return _btCss('--gold-deep', '#b8860b'); }

function renderRolling(roll) {
  const sec = document.getElementById('btRollingSection');
  ['btBoxShort', 'btBoxLong', 'btRollCagr'].forEach(k => {
    if (btCharts[k]) { btCharts[k].destroy(); btCharts[k] = null; }
  });
  _btRoll = roll;
  if (!roll || !roll.horizon_table) { sec.style.display = 'none'; return; }
  sec.style.display = 'block';

  // 추정(합성) 의존 경고 — 전체 60% 초과 시
  document.getElementById('btRollSynWarn').style.display = (roll.syn_overall > 0.6) ? 'block' : 'none';

  _btInfl = (parseFloat(document.getElementById('btInflInput').value) || 2) / 100;
  renderHorizonTable();
  renderBoxChart();
  renderRollCagrToggles();
  renderRollCagrChart();
}

function btSetReal(on) {
  _btRealOn = on;
  document.getElementById('btRealNom').classList.toggle('is-on', !on);
  document.getElementById('btRealReal').classList.toggle('is-on', on);
  document.getElementById('btInflWrap').style.display = on ? 'inline-flex' : 'none';
  document.getElementById('btRealBadge').style.display = on ? 'inline' : 'none';
  document.getElementById('btRollCagrRealBadge').style.display = on ? 'inline' : 'none';
  if (!_btRoll) return;
  renderHorizonTable();
  renderBoxChart();
  renderRollCagrChart();   // 체크박스 상태는 유지
}

function btOnInflChange() {
  _btInfl = (parseFloat(document.getElementById('btInflInput').value) || 0) / 100;
  if (_btRealOn && _btRoll) { renderHorizonTable(); renderBoxChart(); renderRollCagrChart(); }
}

function _btSynLevel(sf) { return (sf != null && sf > 0.5); }   // 추정 의존 큼

function renderHorizonTable() {
  const ht = _btRoll.horizon_table, hs = _btRoll.horizons;
  const pctFmt = v => (v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%');
  let html = `<thead><tr><th>보유기간</th><th>손실확률</th><th>중앙 수익률</th><th>최악</th><th>최고</th><th>표본</th></tr></thead><tbody>`;
  hs.forEach(h => {
    const r = ht[String(h)] || {};
    if (!r.n) {
      html += `<tr class="is-dim"><td>${h}년</td><td colspan="5" style="text-align:left;">표본 부족 (가용 기간보다 깁니다)</td></tr>`;
      return;
    }
    // 표본 적을 때(<10)만 회색. 합성 의존은 가독성 유지 + "추정" 배지로 표기.
    const dim = (r.n < 10) ? ' class="is-dim"' : '';
    const lp = r.loss_prob;
    const lpColor = lp == null ? '' : (lp <= 0.001 ? 'color:var(--up);font-weight:800;' : (lp >= 0.3 ? 'color:var(--down);font-weight:700;' : 'font-weight:700;'));
    const pcts = r.pcts || {};
    const worst = btDeflate(pcts['0']), best = btDeflate(pcts['100']);
    const synBadge = _btSynLevel(r.syn_frac) ? ` <span class="bt-est" title="이 기간 윈도우의 ${(r.syn_frac*100).toFixed(0)}%가 추정(합성) 데이터에 의존">추정</span>` : '';
    html += `<tr${dim}>`
      + `<td>${h}년${synBadge}</td>`
      + `<td style="${lpColor}">${lp == null ? '—' : (lp * 100).toFixed(1) + '%'}</td>`
      + `<td>${pctFmt(btDeflate(r.median))}</td>`
      + `<td style="color:var(--down);font-weight:700;">${pctFmt(worst)}</td>`
      + `<td style="color:var(--up);font-weight:700;">${pctFmt(best)}</td>`
      + `<td style="color:var(--ds-muted);">${r.n}</td>`
      + `</tr>`;
  });
  html += `</tbody>`;
  document.getElementById('btHorizonTable').innerHTML = html;
}

// 오차막대(box-whisker) — 박스=[p25,p75], 수염=[p0,p100], 중앙값 가로선. 커스텀 플러그인으로 그림.
const _btBoxPlugin = {
  id: 'btBoxWhisker',
  afterDatasetsDraw(chart) {
    const meta = chart._btBoxMeta;
    if (!meta) return;
    const { ctx, scales: { x, y } } = chart;
    ctx.save();
    meta.forEach((d, i) => {
      if (d == null) return;
      const cx = x.getPixelForValue(i);
      const half = Math.min(x.width / chart.data.labels.length * 0.18, 14);
      const col = d.est ? _btEstColor() : _btBrand;
      ctx.strokeStyle = col; ctx.lineWidth = 1.8;
      // 수염 세로선 p0~p100
      ctx.beginPath(); ctx.moveTo(cx, y.getPixelForValue(d.lo)); ctx.lineTo(cx, y.getPixelForValue(d.hi)); ctx.stroke();
      // 위/아래 캡
      [d.lo, d.hi].forEach(v => { const py = y.getPixelForValue(v); ctx.beginPath(); ctx.moveTo(cx - half, py); ctx.lineTo(cx + half, py); ctx.stroke(); });
      // 중앙값 가로선(굵게)
      const my = y.getPixelForValue(d.med); ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.moveTo(cx - half * 1.25, my); ctx.lineTo(cx + half * 1.25, my); ctx.stroke();
    });
    ctx.restore();
  }
};

function renderBoxChart() {
  // 스케일 충돌 회피 — 단기(≤3년)/장기(≥5년) 2패널 분리, 각자 y축 자동.
  const hs = _btRoll.horizons;
  _btDrawBox('btBoxChartShort', 'btBoxShort', hs.filter(h => h <= 3));
  _btDrawBox('btBoxChartLong', 'btBoxLong', hs.filter(h => h >= 5));
}

function _btDrawBox(canvasId, chartKey, horizons) {
  if (btCharts[chartKey]) { btCharts[chartKey].destroy(); btCharts[chartKey] = null; }
  const ht = _btRoll.horizon_table, est = _btEstColor();
  const labels = [], boxData = [], meta = [];
  let gMin = Infinity, gMax = -Infinity;
  horizons.forEach(h => {
    const r = ht[String(h)] || {};
    if (!r.n) { labels.push(h + '년'); boxData.push(null); meta.push(null); return; }
    const p = r.pcts || {};
    const lo = btDeflate(p['0']) * 100, hi = btDeflate(p['100']) * 100;
    const b25 = btDeflate(p['25']) * 100, b75 = btDeflate(p['75']) * 100;
    labels.push(h + '년');
    boxData.push([b25, b75]);
    meta.push({ lo, hi, med: btDeflate(r.median) * 100, est: _btSynLevel(r.syn_frac) });
    gMin = Math.min(gMin, lo); gMax = Math.max(gMax, hi);
  });
  if (!isFinite(gMin)) { gMin = -10; gMax = 10; }
  const pad = Math.max((gMax - gMin) * 0.08, 2);
  const yMin = Math.min(0, gMin) - pad, yMax = gMax + pad;
  const chart = new Chart(document.getElementById(canvasId).getContext('2d'), {
    type: 'bar',
    data: { labels, datasets: [{
      data: boxData,
      backgroundColor: meta.map(d => d && d.est ? _btRgba(est, 0.55) : _btRgba(_btBrand, 0.6)),
      borderColor: meta.map(d => d && d.est ? est : _btBrand),
      borderWidth: 1.5, borderSkipped: false, barPercentage: 0.5, categoryPercentage: 0.8,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => {
          const d = meta[ctx.dataIndex]; if (!d) return '표본 부족';
          const tag = d.est ? ' (추정 포함)' : '';
          return [`최고 ${d.hi.toFixed(1)}%`, `흔한 범위 ${ctx.raw[0].toFixed(1)}~${ctx.raw[1].toFixed(1)}%`,
                  `중앙값 ${d.med.toFixed(1)}%`, `최악 ${d.lo.toFixed(1)}%${tag}`];
        } } }
      },
      scales: {
        x: { ticks: { font: { size: 11 }, color: _btBody() }, grid: { display: false } },
        y: { suggestedMin: yMin, suggestedMax: yMax,
             ticks: { font: { size: 10 }, color: _btBody(), maxTicksLimit: 8, callback: v => Math.round(v) + '%' },
             grid: { color: ctxLine => ctxLine.tick.value === 0 ? _btRgba(_btMuted, 0.9) : MM_CHART_GRID,
                     lineWidth: ctxLine => ctxLine.tick.value === 0 ? 1.5 : 1 },
             title: { display: true, text: '연 수익률', color: _btBody(), font: { size: 10 } } }
      }
    },
    plugins: [_btBoxPlugin]
  });
  chart._btBoxMeta = meta;
  chart.update();
  btCharts[chartKey] = chart;
}

function _btBody() { return _btCss('--ds-body', '#3a3f47'); }

const _btYearTick = function(val) { const l = this.getLabelForValue(val); return l ? String(l).slice(0, 4) : ''; };

const _btRollPalette = () => ({ '1': _btMuted, '3': _btUp, '5': _btBrand, '10': _btDown });

function renderRollCagrToggles() {
  const wrap = document.getElementById('btRollCagrToggles');
  const rc = _btRoll.rolling_cagr || {};
  const pal = _btRollPalette();
  const defOn = { '1': false, '3': true, '5': true, '10': true };
  wrap.innerHTML = ['1', '3', '5', '10'].filter(h => (rc[h] || []).length).map(h =>
    `<label class="bt-rcb"><input type="checkbox" data-h="${h}" ${defOn[h] ? 'checked' : ''} onchange="btToggleRollCagr()">`
    + `<span class="bt-rcb-dot" style="background:${pal[h]};"></span>직전 ${h}년</label>`
  ).join('');
}

function _btRollVisible() {
  const cbs = document.querySelectorAll('#btRollCagrToggles input[type=checkbox]');
  if (!cbs.length) return { '3': true, '5': true, '10': true };
  const v = {}; cbs.forEach(c => v[c.dataset.h] = c.checked); return v;
}

function renderRollCagrChart() {
  if (btCharts.btRollCagr) { btCharts.btRollCagr.destroy(); btCharts.btRollCagr = null; }
  const rc = _btRoll.rolling_cagr || {};
  const pal = _btRollPalette();
  const vis = _btRollVisible();
  // 시간축 어댑터 없음 → 전 horizon 날짜 합집합을 category 라벨로
  const allDates = new Set();
  ['1', '3', '5', '10'].forEach(h => (rc[h] || []).forEach(p => allDates.add(p[0])));
  const labels = [...allDates].sort();
  const pos = {}; labels.forEach((d, i) => pos[d] = i);
  const datasets = [];
  ['1', '3', '5', '10'].forEach(h => {
    const arr = rc[h] || [];
    if (!arr.length) return;
    const ys = new Array(labels.length).fill(null);
    arr.forEach(p => { ys[pos[p[0]]] = +(btDeflate(p[1]) * 100).toFixed(2); });
    datasets.push({
      label: '직전 ' + h + '년', _h: h, data: ys, borderColor: pal[h], backgroundColor: pal[h],
      borderWidth: 2, pointRadius: 0, tension: 0.1, spanGaps: true, hidden: !vis[h],
    });
  });
  const ctx = document.getElementById('btRollCagrChart').getContext('2d');
  btCharts.btRollCagr = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          title: items => items.length ? String(items[0].label).slice(0, 7) : '',
          label: c => c.parsed.y == null ? null : `${c.dataset.label}: ${c.parsed.y >= 0 ? '+' : ''}${c.parsed.y.toFixed(1)}%`
        } },
        zoom: { zoom: { drag: { enabled: true, backgroundColor: _btRgba(_btBrand, 0.15) }, mode: 'x' } }
      },
      scales: {
        x: { ticks: { font: { size: 10 }, color: _btBody(), maxRotation: 0, autoSkip: true, maxTicksLimit: 8, callback: _btYearTick }, grid: { display: false } },
        y: { ticks: { font: { size: 10 }, color: _btBody(), callback: v => v + '%' }, grid: { color: MM_CHART_GRID } }
      }
    }
  });
}

function btToggleRollCagr() {
  const chart = btCharts.btRollCagr;
  if (!chart) return;
  const vis = _btRollVisible();
  chart.data.datasets.forEach(ds => { ds.hidden = !vis[ds._h]; });
  chart.update();
}

function btRollCagrResetZoom() {
  if (btCharts.btRollCagr && btCharts.btRollCagr.resetZoom) btCharts.btRollCagr.resetZoom();
}

function renderAnnualDividendChart(annualDiv, totalDiv) {
  const card = document.getElementById('btDivCard');
  if (btCharts.annualDiv) { btCharts.annualDiv.destroy(); btCharts.annualDiv = null; }
  const rows = (annualDiv || []).filter(a => a.dividend > 0);
  if (!rows.length) { card.style.display = 'none'; return; }
  card.style.display = 'block';

  const labels = rows.map(a => a.year + '년');
  const values = rows.map(a => a.dividend);
  btCharts.annualDiv = new Chart(document.getElementById('btDivChart').getContext('2d'), {
    type: 'bar',
    data: { labels, datasets: [{ data: values, backgroundColor: _btRgba(_btBrand, 0.85), borderRadius: 4 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: ctx => fmtKRW(ctx.parsed.y) } } },
      scales: {
        x: { ticks: { font: { size: 10 }, color: _btMuted }, grid: { display: false } },
        y: { beginAtZero: true, ticks: { font: { size: 10 }, color: _btMuted, callback: v => fmtKRW(v) }, grid: { color: MM_CHART_GRID } }
      }
    }
  });
  document.getElementById('btDivNote').innerHTML =
    `총 배당금 ${fmtKRW(totalDiv || 0)} · 그 해 보유 수량 기준 실제 수령 배당입니다.`;
}

function btCleanDividendGrowthRows(annualDiv, body) {
  const raw = (annualDiv || [])
    .filter(a => a && a.dividend > 0 && Number.isFinite(Number(a.dividend)))
    .map(a => ({ year: Number(a.year), dividend: Number(a.dividend) }))
    .filter(a => Number.isFinite(a.year))
    .sort((a, b) => a.year - b.year);
  if (!raw.length) return { rows: [], skipped: 0 };

  const start = body?.start_date ? new Date(body.start_date) : null;
  const end = body?.end_date ? new Date(body.end_date) : null;
  let rows = raw.filter(a => {
    if (start && a.year === start.getFullYear() && (start.getMonth() !== 0 || start.getDate() !== 1)) return false;
    if (end && a.year === end.getFullYear() && (end.getMonth() !== 11 || end.getDate() !== 31)) return false;
    return true;
  });
  if (!end && rows.length) rows = rows.slice(0, -1);

  // SCHD처럼 상장 첫해 배당이 1회뿐이면 다음 full-year 대비 +500%대 착시가 생긴다.
  // 중앙값의 30% 미만인 저베이스 선행연도는 성장률 분모에서 제외한다.
  if (rows.length >= 3) {
    const vals = rows.map(a => a.dividend).sort((a, b) => a - b);
    const mid = vals.length % 2 ? vals[(vals.length - 1) / 2] : (vals[vals.length / 2 - 1] + vals[vals.length / 2]) / 2;
    const minBase = mid > 0 ? mid * 0.30 : 0;
    rows = rows.filter(a => a.dividend >= minBase);
  }
  while (rows.length >= 2 && rows[1].year - rows[0].year !== 1) rows.shift();
  return { rows, skipped: raw.length - rows.length };
}

function renderDividendGrowthChart(annualDiv, body = {}) {
  const card = document.getElementById('btDivGrowthCard');
  if (btCharts.divGrowth) { btCharts.divGrowth.destroy(); btCharts.divGrowth = null; }
  const cleaned = btCleanDividendGrowthRows(annualDiv, body);
  const rows = cleaned.rows;
  if (rows.length < 2) { card.style.display = 'none'; return; }   // 성장률 막대 1개 이상 필요
  card.style.display = 'block';

  // 전년 대비 증가율 (첫 해 제외)
  const labels = [], values = [];
  for (let i = 1; i < rows.length; i++) {
    const prev = rows[i-1].dividend, cur = rows[i].dividend;
    if (rows[i].year - rows[i-1].year !== 1) continue;
    labels.push(rows[i].year + '년');
    values.push(prev > 0 ? +((cur / prev - 1) * 100).toFixed(1) : 0);
  }
  if (!labels.length) { card.style.display = 'none'; return; }
  const colors = values.map(v => v >= 0 ? _btRgba(_btUp, 0.85) : _btRgba(_btDown, 0.85));

  btCharts.divGrowth = new Chart(document.getElementById('btDivGrowthChart').getContext('2d'), {
    type: 'bar',
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: 4 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: ctx => (ctx.parsed.y >= 0 ? '+' : '') + ctx.parsed.y.toFixed(1) + '%' } } },
      scales: {
        x: { ticks: { font: { size: 10 }, color: _btMuted }, grid: { display: false } },
        y: { ticks: { font: { size: 10 }, color: _btMuted, callback: v => v + '%' }, grid: { color: MM_CHART_GRID } }
      }
    }
  });

  // 전체 배당 CAGR
  const first = rows[0].dividend, last = rows[rows.length-1].dividend, n = rows.length - 1;
  let cagr = null;
  if (first > 0 && n > 0) cagr = (Math.pow(last / first, 1 / n) - 1) * 100;
  const skipNote = cleaned.skipped > 0 ? ` · 부분연도/저베이스 ${cleaned.skipped}개 제외` : '';
  document.getElementById('btDivGrowthNote').innerHTML = cagr != null
    ? `전체 배당 성장률(CAGR) ${cagr >= 0 ? '+' : ''}${cagr.toFixed(1)}% · ${rows[0].year}년 → ${rows[rows.length-1].year}년 기준${skipNote}`
    : '';
}

let _btAttrLabels = [];
function renderValueChart(history) {
  if (btCharts.value) btCharts.value.destroy();
  const labels = history.map(h => h.date);
  const values = history.map(h => h.portfolio_value);
  const invested = history.map(h => h.total_invested);
  _btAttrLabels = labels;
  // 구간 기여 카드 — 종목 2개 이상일 때만(단일 종목은 기여 분석 무의미). 매 렌더 리셋.
  const attrCard = document.getElementById('btAttrCard');
  if (attrCard) {
    if (labels.length > 1 && btTickers.length >= 2) {
      attrCard.style.display = '';
      const s = document.getElementById('btAttrStart'), e = document.getElementById('btAttrEnd');
      if (s && e) { s.min = e.min = labels[0]; s.max = e.max = labels[labels.length-1]; s.value = labels[0]; e.value = labels[labels.length-1]; }
      document.getElementById('btAttrBody').innerHTML = '<div style="color:var(--ds-muted);font-size:0.85rem;">위 가치 추이 또는 아래 낙폭 그래프를 가로로 드래그하거나, 날짜를 골라 구간을 정하면 종목별 상승 참여율·하락 방어율이 나와요.</div>';
      document.getElementById('btAttrRange').textContent = '';
    } else {
      attrCard.style.display = 'none';
      document.getElementById('btAttrBody').innerHTML = '';
      document.getElementById('btAttrRange').textContent = '';
    }
  }

  btCharts.value = new Chart(document.getElementById('btValueChart').getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '포트폴리오',
          data: values,
          borderColor: _btBrand, borderWidth: 2,
          backgroundColor: _btRgba(_btBrand, 0.08),
          fill: true, pointRadius: 0, tension: 0.2,
        },
        {
          label: '납입금',
          data: invested,
          borderColor: _btMuted, borderWidth: 1.5,
          borderDash: [5, 4],
          fill: false, pointRadius: 0, tension: 0,
        },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, position: 'top', labels: { font: { size: 11 } } },
        tooltip: { callbacks: {
          label: ctx => ctx.dataset.label + ': ' + fmtKRW(ctx.parsed.y)
        }},
        zoom: {
          zoom: {
            drag: { enabled: true, backgroundColor: _btRgba(_btBrand, 0.15) },
            mode: 'x',
            onZoomComplete: ({ chart }) => {
              const x = chart.scales.x;
              const i0 = Math.max(0, Math.round(x.min));
              const i1 = Math.min(_btAttrLabels.length - 1, Math.round(x.max));
              if (i1 - i0 >= 1 && btTickers.length >= 2) btAttrAnalyze(_btAttrLabels[i0], _btAttrLabels[i1]);
            }
          }
        }
      },
      scales: {
        x: { ticks: { maxTicksLimit: 8, font: { size: 10 }, color: _btMuted }, grid: { display: false } },
        y: { ticks: { font: { size: 10 }, color: _btMuted, callback: v => fmtKRW(v) }, grid: { color: MM_CHART_GRID } }
      }
    }
  });
}

async function btAttrAnalyze(start, end) {
  const bodyEl = document.getElementById('btAttrBody');
  if (btTickers.length < 2) return;   // 단일 종목은 기여 분석 무의미
  document.getElementById('btAttrCard').style.display = '';
  document.getElementById('btAttrRange').textContent = `(${start} ~ ${end})`;
  const si = document.getElementById('btAttrStart'), ei = document.getElementById('btAttrEnd');
  if (si) si.value = start; if (ei) ei.value = end;
  bodyEl.innerHTML = '<div style="color:var(--ds-muted);font-size:0.85rem;padding:10px;">계산 중…</div>';
  try {
    const j = await (await fetch('/api/attribution/capture', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickers: btTickers.map(t => ({ code: t.code, weight: t.weight })), start, end })
    })).json();
    if (!j.ok || !j.attribution) { bodyEl.innerHTML = '<div style="color:var(--ds-muted);font-size:0.85rem;padding:10px;">이 구간 데이터가 부족해요.</div>'; return; }
    btAttrRender(j.attribution);
  } catch (e) { bodyEl.innerHTML = '<div style="color:var(--ds-muted);font-size:0.85rem;padding:10px;">오류가 발생했어요.</div>'; }
}

function btAttrRender(a) {
  // 비중 무관 상승 참여율 / 하락 방어율(포착률). 내자산·계산기와 동일 기준.
  const A = a.assets || {}, nm = a.names || {};
  const codes = Object.keys(A);
  if (!codes.length) {
    document.getElementById('btAttrBody').innerHTML =
      '<div style="color:var(--ds-muted);font-size:0.85rem;padding:10px;">이 구간 데이터가 부족해요.</div>';
    return;
  }
  const grn = 'var(--up)', red = 'var(--down)', mut = 'var(--ds-muted)';
  // 하락 방어 잘하는 순(down_capture 작을수록 위)
  codes.sort((x, y) => (A[x].down_capture ?? 9) - (A[y].down_capture ?? 9));

  const upCell = u => {
    if (u.up_capture == null) return '—';
    const c = u.up_capture >= 1 ? grn : mut;
    return `<span style="color:${c};font-weight:700;">${u.up_capture.toFixed(2)}배</span>`
      + `<div style="font-size:0.72rem;color:${mut};">하루 평균 +${u.up_ret.toFixed(2)}%</div>`;
  };
  const dnCell = d => {
    if (d.down_capture == null) return '—';
    let label, col;
    if (d.down_capture < 0) { label = '헤지 ↑'; col = grn; }
    else if (d.down_capture < 1) { label = d.down_capture.toFixed(2) + '배'; col = grn; }
    else { label = d.down_capture.toFixed(2) + '배'; col = red; }
    return `<span style="color:${col};font-weight:700;">${label}</span>`
      + `<div style="font-size:0.72rem;color:${mut};">하루 평균 ${d.down_ret >= 0 ? '+' : ''}${d.down_ret.toFixed(2)}%</div>`;
  };

  let html = `<div style="font-size:0.78rem;color:${mut};margin-bottom:8px;">분석 구간 ${a.period[0]} ~ ${a.period[1]} · 상승 ${a.n_up}일 / 하락 ${a.n_down}일</div>`;
  html += `<table style="width:100%;border-collapse:collapse;font-size:0.84rem;">
    <tr style="color:${mut};font-size:0.76rem;text-align:right;">
      <th style="text-align:left;padding:6px 4px;">종목</th>
      <th style="padding:6px 4px;">📈 상승 참여율</th>
      <th style="padding:6px 4px;">🛡️ 하락 방어율</th></tr>`;
  html += codes.map(c => `<tr style="border-top:1px solid var(--ds-hairline);text-align:right;">
      <td style="text-align:left;padding:7px 4px;font-weight:700;">${btE(nm[c] || c)}<div style="font-size:0.72rem;color:${mut};font-weight:400;">${btE(c)}</div></td>
      <td style="padding:7px 4px;">${upCell(A[c])}</td>
      <td style="padding:7px 4px;">${dnCell(A[c])}</td>
    </tr>`).join('');
  html += `</table><div style="font-size:0.72rem;color:${mut};margin-top:8px;">비중과 무관 · 참여율 = 포트폴리오 1%↑ 때 이 종목 X%↑ · 방어율 = 포트폴리오 1%↓ 때 이 종목 X%↓ (작을수록·음수일수록 방어 ↑)</div>`;
  document.getElementById('btAttrBody').innerHTML = html;
}

function btAttrReset() {
  if (btCharts.value && btCharts.value.resetZoom) btCharts.value.resetZoom();
  if (btCharts.drawdown && btCharts.drawdown.resetZoom) btCharts.drawdown.resetZoom();
  document.getElementById('btAttrRange').textContent = '';
  document.getElementById('btAttrBody').innerHTML = '<div style="color:var(--ds-muted);font-size:0.85rem;">위 가치 추이 또는 아래 낙폭 그래프를 가로로 드래그하거나, 날짜를 골라 구간을 정하면 종목별 상승 참여율·하락 방어율이 나와요.</div>';
}

function btE(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c])); }

function renderAnnualChart(annualReturns) {
  if (btCharts.annual) btCharts.annual.destroy();
  if (!annualReturns || !annualReturns.length) return;
  const labels = annualReturns.map(a => a.year + '년');
  const values = annualReturns.map(a => a.return * 100);
  const colors = values.map(v => v >= 0 ? _btRgba(_btUp, 0.85) : _btRgba(_btDown, 0.85));

  btCharts.annual = new Chart(document.getElementById('btAnnualChart').getContext('2d'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: {
        callbacks: { label: ctx => (ctx.parsed.y >= 0 ? '+' : '') + ctx.parsed.y.toFixed(2) + '%' }
      }},
      scales: {
        x: { ticks: { font: { size: 10 }, color: _btMuted }, grid: { display: false } },
        y: { ticks: { font: { size: 10 }, color: _btMuted, callback: v => v + '%' }, grid: { color: MM_CHART_GRID } }
      }
    }
  });
}

// ── 공유 ──
function downsample(arr, n) {
  if (!arr || arr.length === 0) return [];
  if (arr.length <= n) {
    const mn = Math.min(...arr), mx = Math.max(...arr), rng = mx - mn || 1;
    return arr.map(v => Math.round((v - mn) / rng * 9999));
  }
  const result = [];
  const mn = Math.min(...arr), mx = Math.max(...arr), rng = mx - mn || 1;
  for (let i = 0; i < n; i++) {
    const idx = Math.round(i * (arr.length - 1) / (n - 1));
    result.push(Math.round((arr[idx] - mn) / rng * 9999));
  }
  return result;
}

function downsampleDd(arr, n) {
  if (!arr || arr.length === 0) return [];
  if (arr.length <= n) return arr;
  const result = [];
  for (let i = 0; i < n; i++) {
    const idx = Math.round(i * (arr.length - 1) / (n - 1));
    result.push(arr[idx]);
  }
  return result;
}

function mmEncodeShare(data) {
  return btoa(unescape(encodeURIComponent(JSON.stringify(data))))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function btMakeCanvas() {
  const layout = document.querySelector('.bt-layout');
  const rightPanel = document.querySelector('.bt-right');
  const rightW = rightPanel ? rightPanel.offsetWidth : 0;

  const rawCanvas = await html2canvas(layout, {
    scale: 2, backgroundColor: (typeof MM_DARK !== 'undefined' && MM_DARK) ? '#0E141C' : '#F0F4F8', useCORS: true, allowTaint: true,
    onclone: function(doc, clonedLayout) {
      // Fix flex:1 width so html2canvas renders right panel correctly
      const cr = clonedLayout.querySelector('.bt-right');
      if (cr) { cr.style.width = rightW + 'px'; cr.style.flex = 'none'; cr.style.minWidth = '0'; }
      // Hide elements that don't belong in a static image
      ['#btRunBtn', '#btLoading', '#btShareUrlBox'].forEach(sel => {
        const e = clonedLayout.querySelector(sel); if (e) e.style.display = 'none';
      });
      // Copy canvas pixel data
      const origCanvases = layout.querySelectorAll('canvas');
      const clonedCanvases = clonedLayout.querySelectorAll('canvas');
      origCanvases.forEach(function(orig, i) {
        const cl = clonedCanvases[i];
        if (cl && orig.width > 0) { cl.width = orig.width; cl.height = orig.height; cl.getContext('2d').drawImage(orig, 0, 0); }
      });
    }
  });

  // Add branding header bar via canvas API (avoids DOM restructuring)
  const hdrH = 88; // pixels in @2x canvas (= 44px displayed)
  const out = document.createElement('canvas');
  out.width = rawCanvas.width;
  out.height = rawCanvas.height + hdrH;
  const ctx = out.getContext('2d');
  ctx.fillStyle = '#1A2332';
  ctx.fillRect(0, 0, out.width, hdrH);
  const fontSize = Math.max(24, Math.round(out.width * 0.014));
  ctx.font = 'bold ' + fontSize + 'px sans-serif';
  ctx.fillStyle = '#1976D2';
  ctx.fillText('Money Milestone', 40, hdrH * 0.66);
  ctx.font = Math.max(18, Math.round(out.width * 0.010)) + 'px sans-serif';
  ctx.fillStyle = '#90A4AE';
  const sub = 'moneymilestone.co.kr  ·  무료 투자 분석 도구';
  ctx.fillText(sub, out.width - ctx.measureText(sub).width - 40, hdrH * 0.66);
  ctx.drawImage(rawCanvas, 0, hdrH);
  return out;
}

async function btCopyLink(ev) {
  const btn = ev && ev.currentTarget;
  if (!window._btShareData) { mmToast('먼저 분석을 실행하세요', 'err'); return; }
  if (btn) btn.disabled = true;
  mmToast('공유 이미지 생성 중…');
  try {
    const canvas = await btMakeCanvas();
    const b64 = canvas.toDataURL('image/png');
    const res = await fetch('/api/share/upload', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({image: b64}),
    });
    const { id } = await res.json();
    const url = location.origin + '/share/img/' + id;
    const box = document.getElementById('btShareUrlBox');
    if (box) { box.style.display = 'block'; box.innerHTML = '공유 링크: <a href="' + url + '" target="_blank">' + url + '</a>'; }
    await mmCopyText(url);
    mmToast('링크가 복사됐어요!', 'ok');
  } catch(e) {
    mmToast('오류가 발생했어요', 'err');
  } finally { if (btn) btn.disabled = false; }
}

function btDownloadImg() {
  if (typeof html2canvas === 'undefined') { mmToast('이미지 저장 기능을 불러오는 중입니다.', 'err'); return; }
  btMakeCanvas().then(function(canvas) {
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = 'backtest-result.png';
    a.click();
  });
}

function renderDrawdownChart(history) {
  if (btCharts.drawdown) btCharts.drawdown.destroy();
  const labels = history.map(h => h.date);
  const values = history.map(h => (h.drawdown || 0) * 100);

  btCharts.drawdown = new Chart(document.getElementById('btDrawdownChart').getContext('2d'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: _btDown, borderWidth: 1.5,
        backgroundColor: _btRgba(_btDown, 0.1),
        fill: true, pointRadius: 0, tension: 0.2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: {
        callbacks: { label: ctx => ctx.parsed.y.toFixed(2) + '%' }
      },
      zoom: {
        zoom: {
          drag: { enabled: true, backgroundColor: _btRgba(_btDown, 0.15) },
          mode: 'x',
          onZoomComplete: ({ chart }) => {
            const x = chart.scales.x;
            const i0 = Math.max(0, Math.round(x.min));
            const i1 = Math.min(_btAttrLabels.length - 1, Math.round(x.max));
            if (i1 - i0 >= 1) btAttrAnalyze(_btAttrLabels[i0], _btAttrLabels[i1]);
          }
        }
      }},
      scales: {
        x: { ticks: { maxTicksLimit: 8, font: { size: 10 }, color: _btMuted }, grid: { display: false } },
        y: { ticks: { font: { size: 10 }, color: _btMuted, callback: v => v + '%' }, grid: { color: MM_CHART_GRID } }
      }
    }
  });
}

function btAttrManual() {
  const s = document.getElementById('btAttrStart').value;
  const e = document.getElementById('btAttrEnd').value;
  if (!s || !e || s >= e) { mmToast('시작일이 종료일보다 앞서야 해요.', 'err'); return; }
  btAttrAnalyze(s, e);
}

// ── 분할매도 절세 패널 업데이트 (Phase 2e) ──
function btUpdateSplitPlan(years) {
  years = parseInt(years);
  const label = document.getElementById('btSplitYearsLabel');
  if (label) label.textContent = years + '년';

  const plan = window._btSplitSaleData;
  if (!plan) return;

  const byYear = plan.plan_by_year || {};
  const afterTaxByYear = plan.after_tax_by_year || {};
  const splitTax = byYear[String(years)] ?? plan.lump_sum_tax;
  const splitAfterTax = afterTaxByYear[String(years)] ?? (plan.gain - splitTax);
  const lumpAfterTax = plan.lump_sum_after_tax ?? (plan.gain - plan.lump_sum_tax);
  const saving   = plan.lump_sum_tax - splitTax;
  const optYears = plan.optimal_years;
  const optTax   = plan.optimal_tax;
  const optAfterTax = plan.optimal_after_tax ?? (plan.gain - optTax);

  const el = document.getElementById('btSplitMetrics');
  if (!el) return;
  el.innerHTML = [
    { label: '일괄 청산 세금',     value: fmtKRW(plan.lump_sum_tax), cls: 'down' },
    { label: years + '년 분할 세금', value: fmtKRW(splitTax),          cls: '' },
    { label: '일괄 세후 이익',     value: fmtKRW(lumpAfterTax), cls: '' },
    { label: years + '년 세후 이익', value: fmtKRW(splitAfterTax),       cls: 'up' },
    { label: '절감액',             value: fmtKRW(saving),             cls: saving > 0 ? 'up' : '' },
    { label: '최적 연수',          value: optYears + '년 (' + fmtKRW(optTax) + ' / 세후 ' + fmtKRW(optAfterTax) + ')', cls: '' },
  ].map(item => `
    <div class="metric-item">
      <div class="metric-label">${item.label}</div>
      <div class="metric-value ${item.cls}">${item.value}</div>
    </div>
  `).join('');
}
