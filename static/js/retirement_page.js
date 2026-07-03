// retirement.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 내용 무변경 이동
let retTickers = [];
let _retTaskId = null, _retCancelled = false;
let retCharts  = {};
let retMode    = 'sim';  // 'sim' or 'wd'

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

function fmtKRWHint(v) {
  if (!v || isNaN(v)) return '₩0';
  return '₩' + Math.round(v).toLocaleString();
}

// ── 모드 전환 ──
function switchMode(mode) {
  retMode = mode;
  document.getElementById('modeSimInputs').style.display = mode === 'sim' ? 'grid' : 'none';
  document.getElementById('modeWdInputs').style.display  = mode === 'wd'  ? 'grid' : 'none';
  document.getElementById('tabRetSim').classList.toggle('active', mode === 'sim');
  document.getElementById('tabRetWd').classList.toggle('active',  mode === 'wd');

  // 공용 멀티계좌 패널 MMTAX 스왑 — 인출기(wd)는 시작 목돈(wdSeed)·월적립 숨김.
  const _portfolioTickers = () =>
    retTickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: (t.weight || 0) * 100 }));
  window.MMTAX = (mode === 'wd')
    ? { portfolioTickers: _portfolioTickers, totalInitId: 'wdSeed', mode: 'withdrawal' }
    : { portfolioTickers: _portfolioTickers, totalInitId: 'simSeed', totalMonId: 'simMonthly', mode: 'accumulation' };
  if (window.taxAccounts && window.taxAccounts.length && typeof renderTaxAccounts === 'function') renderTaxAccounts();

  // 결과 초기화
  document.getElementById('retResultEmpty').style.display   = 'block';
  document.getElementById('retResultContent').style.display = 'none';
}

// ── 입력 ↔ 결과 뷰 전환 (계산기/포트폴리오 분석 탭과 동일 아키타입) ──
function retShowResults() {
  document.getElementById('retInputView').style.display  = 'none';
  document.getElementById('retResultView').style.display = 'block';
}
function retShowInput() {
  document.getElementById('retResultView').style.display = 'none';
  document.getElementById('retInputView').style.display  = 'block';
}
function retEditConditions() { retShowInput(); }

// ── 고급 옵션 접기/펼치기 (가상 데이터·세금·수수료) ──
function retToggleAdvanced(force) {
  const body = document.getElementById('retMoreoptBody');
  const tog  = document.getElementById('retMoreoptToggle');
  if (!body || !tog) return;
  const open = force === undefined ? !body.classList.contains('open') : !!force;
  body.classList.toggle('open', open);
  tog.classList.toggle('open', open);
}
function retExpandAdvanced() { retToggleAdvanced(true); }

// ── 목표 생존 확률 슬라이더 ↔ 입력칸 동기 ──
function retSyncProb(src) {
  const sl  = document.getElementById('retTargetProb');
  const inp = document.getElementById('retTargetProbInput');
  if (src === 'input') {
    const v = parseInt(inp.value, 10);
    if (isNaN(v)) return;             // 타이핑 중(빈칸 등)엔 강제하지 않음 — onblur서 정리
    sl.value = Math.max(0, Math.min(100, v));
  } else {
    inp.value = sl.value;
  }
}
function retClampProb() {
  const sl  = document.getElementById('retTargetProb');
  const inp = document.getElementById('retTargetProbInput');
  let v = parseInt(inp.value, 10);
  if (isNaN(v)) v = 50;
  v = Math.max(0, Math.min(100, v));
  inp.value = v;
  sl.value  = v;
}

// ── 연도 슬라이더 ↔ 키보드 입력 동기 (base: simAccYears/simWdYears/wdYears) ──
// 슬라이더(base+'Slider')·입력(base+'Input')·hidden(base) 3자 동기. 비선형 눈금 제거(정직).
function retSyncYears(base, src, min, max) {
  const sl  = document.getElementById(base + 'Slider');
  const inp = document.getElementById(base + 'Input');
  const hid = document.getElementById(base);
  let v;
  if (src === 'input') {
    v = parseInt(inp.value, 10);
    if (isNaN(v)) return;                       // 타이핑 중 — onblur서 정리
    v = Math.max(min, Math.min(max, v));
    if (sl) sl.value = v;
  } else {
    v = parseInt(sl.value, 10);
    if (inp) inp.value = v;
  }
  if (hid) hid.value = v;
  if (typeof updateInflationInfo === 'function') updateInflationInfo();
}
function retClampYears(base, min, max) {
  const sl  = document.getElementById(base + 'Slider');
  const inp = document.getElementById(base + 'Input');
  const hid = document.getElementById(base);
  let v = parseInt(inp.value, 10);
  if (isNaN(v)) v = parseInt((sl && sl.value) || min, 10);
  v = Math.max(min, Math.min(max, v));
  if (inp) inp.value = v;
  if (sl)  sl.value  = v;
  if (hid) hid.value = v;
  if (typeof updateInflationInfo === 'function') updateInflationInfo();
}

// ── 결과 조건 요약 바 (포트폴리오 분석/계산기 결) ──
function retBuildCondSummary(body) {
  const el = document.getElementById('retCondSummary');
  if (!el) return;
  const items = [];
  const port = (retTickers || []).map(t => `${t.code} ${Math.round((t.weight||0)*100)}%`).join(' · ');
  if (port) items.push(['포트폴리오', port]);
  if (retMode === 'sim') {
    items.push(['초기 투자금', fmtKRW(body.initial_capital)]);
    if (body.monthly_contribution) items.push(['월 적립', fmtKRW(body.monthly_contribution)]);
    if (body.accumulation_years)   items.push(['적립 기간', body.accumulation_years + '년']);
  } else {
    items.push(['초기 자산', fmtKRW(body.initial_capital)]);
  }
  items.push(['월 인출', fmtKRW(body.monthly_withdrawal)]);
  if (body.withdrawal_years) items.push(['인출 기간', body.withdrawal_years + '년']);
  if (body.target_percentile != null) items.push(['목표 생존율', Math.round(body.target_percentile*100) + '%']);
  if ((body.inflation || 0) > 0) items.push(['인플레이션', (body.inflation*100).toFixed(1) + '%']);
  if (body.tax_enabled) items.push(['세금', '적용']);
  el.innerHTML = items.map(([l, v], i) =>
    (i > 0 ? '<span class="bt-cond-sep"></span>' : '') +
    `<span class="bt-cond-item">${l} <b>${v}</b></span>`
  ).join('');
  el.style.display = items.length ? 'flex' : 'none';
}

// ── 종목 관리 ──
function updateRetWeightUI() {
  const total = retTickers.reduce((s, t) => s + t.weight, 0);
  const pct   = Math.round(total * 100);
  const totalEl = document.getElementById('retWeightTotal');
  totalEl.textContent = pct + '%';
  totalEl.className = 'weight-total-num' + (pct === 100 ? ' ok' : pct > 100 ? ' over' : '');
  const bar = document.getElementById('retWeightBar');
  bar.style.width = Math.min(pct, 100) + '%';
  bar.style.background = pct === 100 ? 'var(--up)' : pct > 100 ? 'var(--down)' : 'var(--brand)';
  const warn = document.getElementById('retWeightWarn');
  if (warn) warn.textContent = pct > 100 ? '⚠ 비중 합계가 100%를 초과했어요'
    : (pct > 0 && pct < 100 ? `나머지 ${100 - pct}%는 현금으로 유지됩니다` : '');

  const list = document.getElementById('retTickerList');
  if (!retTickers.length) {
    list.innerHTML = '<div class="ticker-empty" id="retTickerPlaceholder">종목을 검색해서 추가해보세요</div>';
    return;
  }
  list.innerHTML = retTickers.map((t, i) => `
    <div class="ticker-item">
      <span class="ticker-item-code">${t.code}</span>
      <span class="ticker-item-name">${t.name ? t.name : ''}</span>
      <div class="ticker-item-weight">
        <input class="weight-input" type="number" value="${Math.round(t.weight*100)}" min="1" max="100" step="1"
          onchange="retUpdateWeight(${i}, this.value)"><span class="weight-pct">%</span>
      </div>
      <input type="range" class="ticker-item-slider" value="${Math.round(t.weight*100)}" min="1" max="100" step="1"
        oninput="retUpdateWeight(${i}, this.value)">
      <button class="ticker-remove" onclick="retRemoveTicker(${i})">✕</button>
    </div>
  `).join('');
}

function retUpdateWeight(i, val) {
  retTickers[i].weight = parseFloat(val) / 100;
  updateRetWeightUI();
}
function retRemoveTicker(i) {
  retTickers.splice(i, 1);
  updateRetWeightUI();
}

// 검색
let retSearchTimer = null;
const retInput    = document.getElementById('retTickerSearch');
const retDropdown = document.getElementById('retTickerDropdown');

function badgeColor(badge) {
  if (badge === 'KR ETF' || badge === 'KOSPI' || badge === 'KOSDAQ') return '#1976D2';
  if (badge === 'US ETF' || badge === 'NASDAQ' || badge === 'NYSE')   return '#2E7D32';
  return '#78909C';
}

retInput.addEventListener('input', (e) => {
  const q = e.target.value.trim();
  if (!q) { retDropdown.style.display = 'none'; return; }
  clearTimeout(retSearchTimer);
  retDropdown.innerHTML = '<div class="ticker-drop-item"><span class="ticker-drop-name">검색 중...</span></div>';
  retDropdown.style.display = 'block';
  retSearchTimer = setTimeout(async () => {
    const res  = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    if (!data.length) { retDropdown.innerHTML = '<div class="ticker-drop-item"><span class="ticker-drop-name">결과 없음</span></div>'; return; }
    retDropdown.innerHTML = data.map(item => `
      <div class="ticker-drop-item" onclick="retAddTicker('${item.code}','${item.name.replace(/'/g,"\\'")}')">
        <span class="ticker-drop-badge" style="background:${badgeColor(item.badge)}22;color:${badgeColor(item.badge)}">${item.badge}</span>
        <div>
          <div class="ticker-drop-code">${item.code}</div>
          <div class="ticker-drop-name">${item.name}</div>
        </div>
      </div>`).join('');
  }, 250);
});

document.addEventListener('click', (e) => {
  if (!retInput.closest('.ticker-search-wrap').contains(e.target))
    retDropdown.style.display = 'none';
});

function retAddTicker(code, name) {
  if (retTickers.find(t => t.code === code)) { retDropdown.style.display='none'; return; }
  const n = retTickers.length + 1;
  const w = Math.round(100 / n) / 100;
  retTickers.forEach(t => t.weight = w);
  retTickers.push({ code, name, weight: parseFloat((1 - w*(n-1)).toFixed(2)) });
  retInput.value = '';
  retDropdown.style.display = 'none';
  updateRetWeightUI();
}

// 포트폴리오 즐겨찾기 (B1) — 내부 weight는 0~1, 위젯 규약은 % (0~100)
if (window.MMFav) MMFav.init({
  mount: 'favBar',
  getTickers: () => retTickers.map(t => ({
    code: t.code, name: t.name || t.code, badge: t.badge || '',
    weight: Math.round(t.weight * 100),
  })),
  setTickers: (list) => {
    retTickers = list.map(t => ({
      code: t.code, name: t.name || t.code,
      weight: (Number(t.weight) || 0) / 100,
    }));
    updateRetWeightUI();
  },
});

// ── 힌트 ──
document.getElementById('simSeed').addEventListener('input', function() { document.getElementById('simSeedHint').textContent = fmtKRWHint(parseFloat(this.value)||0); });
document.getElementById('simMonthly').addEventListener('input', function() { document.getElementById('simMonthlyHint').textContent = fmtKRWHint(parseFloat(this.value)||0); });
document.getElementById('simWithdraw').addEventListener('input', function() { document.getElementById('simWithdrawHint').textContent = fmtKRWHint(parseFloat(this.value)||0); });
document.getElementById('wdSeed').addEventListener('input', function() { document.getElementById('wdSeedHint').textContent = fmtKRWHint(parseFloat(this.value)||0); });
document.getElementById('wdWithdraw').addEventListener('input', function() { document.getElementById('wdWithdrawHint').textContent = fmtKRWHint(parseFloat(this.value)||0); });

// ── 실행 ──
// 멀티계좌 페이로드(적립기) — 계좌 1은 상단 포트폴리오/금액 사용. 2개 이상일 때만.
function buildRetAccountsPayload(rebalMode, bandWidth, dividendMode) {
  const accs = window.taxAccounts || [];
  if (accs.length <= 1) return null;
  const renewalOn = document.getElementById('isaRenewalCheck')?.checked ?? false;
  const feeOn = document.getElementById('feeEnabledChk')?.checked ?? false;
  const primary = {
    type: accs[0]?.type || '위탁',
    initial_capital: parseFloat(document.getElementById('simSeed').value) || 0,
    monthly_contribution: parseFloat(document.getElementById('simMonthly').value) || 0,
    tickers: retTickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: t.weight })),
    rebal_mode: rebalMode, band_width: bandWidth, dividend_mode: dividendMode,
    isa_renewal: renewalOn && (accs[0]?.type === 'ISA'),
    priority: Number(accs[0]?.priority ?? 1),
    ...(feeOn ? { fee_rate: _mmAccountFeePct(accs[0]) / 100 } : {}),
  };
  const accounts = [primary];
  for (let i = 1; i < accs.length; i++) {
    const accTickers = ensureAccountTickers(i);
    if (accTickers.length === 0) { mmToast(`계좌 ${i + 1}에 종목을 최소 1개 추가해주세요.`, 'warn'); return false; }
    if (accTickers.reduce((s, t) => s + (Number(t.weight) || 0), 0) > 100) {
      mmToast(`계좌 ${i + 1}의 비중 합계가 100%를 초과했어요.`, 'warn'); return false;
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

// 인출기 멀티계좌 페이로드 — 계좌별 시작 목돈(value)·미실현차익(위탁). 월적립 없음.
function buildWdAccountsPayload(rebalMode, bandWidth, dividendMode) {
  const accs = window.taxAccounts || [];
  if (accs.length <= 1) return null;
  const feeOn = document.getElementById('feeEnabledChk')?.checked ?? false;
  const primary = {
    type: accs[0]?.type || '위탁',
    initial_capital: parseFloat(document.getElementById('wdSeed').value) || 0,
    unrealized_gain: Number(accs[0]?.unrealized_gain || 0),
    tickers: retTickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: t.weight })),
    rebal_mode: rebalMode, band_width: bandWidth, dividend_mode: dividendMode,
    priority: Number(accs[0]?.priority ?? 1),
    ...(feeOn ? { fee_rate: _mmAccountFeePct(accs[0]) / 100 } : {}),
  };
  const accounts = [primary];
  for (let i = 1; i < accs.length; i++) {
    const accTickers = ensureAccountTickers(i);
    if (accTickers.length === 0) { mmToast(`계좌 ${i + 1}에 종목을 최소 1개 추가해주세요.`, 'warn'); return false; }
    if (accTickers.reduce((s, t) => s + (Number(t.weight) || 0), 0) > 100) {
      mmToast(`계좌 ${i + 1}의 비중 합계가 100%를 초과했어요.`, 'warn'); return false;
    }
    accounts.push({
      type: accs[i].type || '위탁',
      initial_capital: Number(accs[i].initial_capital || 0),
      unrealized_gain: Number(accs[i].unrealized_gain || 0),
      tickers: accTickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: (Number(t.weight) || 0) / 100 })),
      rebal_mode: rebalMode, band_width: bandWidth, dividend_mode: dividendMode,
      priority: Number(accs[i].priority ?? (i + 1)),
      ...(feeOn ? { fee_rate: _mmAccountFeePct(accs[i]) / 100 } : {}),
    });
  }
  return accounts;
}

// ── 거래수수료 (D4) ──
function toggleFeePanel() {
  const on = document.getElementById('feeEnabledChk')?.checked;
  const body = document.getElementById('feePanelBody');
  const label = document.getElementById('feeLabel');
  if (body) body.classList.toggle('is-open', !!on);
  if (label) { label.textContent = on ? 'ON' : 'OFF'; label.style.color = on ? 'var(--brand-text)' : 'var(--ds-muted)'; }
  if (on) retExpandAdvanced();
  // 멀티계좌면 카드별 수수료 입력 노출/숨김 위해 재렌더.
  if (window.retTaxEnabled && (window.taxAccounts || []).length > 1) renderTaxAccounts();
}
// applyFeePreset/markFeePresetCustom/loadBrokerFeePresets = broker_fee.js(공용) 제공.
function renderFeeSummary(containerId, totalFees) {
  const el = document.getElementById(containerId);
  if (!el) return;
  let slot = el.querySelector(':scope > #mmFeeSummary');
  if (totalFees == null) { if (slot) slot.remove(); return; }
  if (!slot) { slot = document.createElement('div'); slot.id = 'mmFeeSummary'; el.appendChild(slot); }
  const won = Math.round(Number(totalFees) || 0).toLocaleString();
  slot.innerHTML = `
    <div style="margin-top:12px;padding:10px 14px;background:var(--bg,#f5f5f5);border:1px solid var(--border,#ddd);border-radius:9px;font-size:0.84rem;color:var(--text,#222);">
      💸 총 지불 거래수수료 <b>₩${won}</b> <span style="color:var(--text-muted,#888);font-size:0.78rem;">(중앙값 시나리오, 적립·인출 누적)</span>
    </div>`;
}

async function runRetirement(_limitOverride) {
  const total = Math.round(retTickers.reduce((s,t) => s+t.weight, 0) * 100);
  if (!retTickers.length) { mmToast('종목을 추가해주세요.', 'warn'); return; }
  if (total !== 100) { mmToast(`비중 합계가 ${total}%입니다. 100%로 맞춰주세요.`, 'warn'); return; }

  retShowResults();
  const _cs = document.getElementById('retCondSummary'); if (_cs) _cs.style.display = 'none';
  document.getElementById('retRunBtn').disabled       = true;
  document.getElementById('retLoading').style.display = 'block';
  document.getElementById('retResultEmpty').style.display   = 'none';
  document.getElementById('retResultContent').style.display = 'none';
  retShowProgressUI();

  const targetProb = parseFloat(document.getElementById('retTargetProb').value) / 100;
  let body;

  if (retMode === 'sim') {
    const retTaxOn  = window.retTaxEnabled || false;
    if (retTaxOn && (!window.retTaxProfile || Object.keys(window.retTaxProfile).length === 0)) {
      await loadRetTaxProfile();
    }
    const taxProfile = window.retTaxProfile || {};
    const retAge    = parseInt(taxProfile.age || 40);
    const retAccYrs = parseInt(document.getElementById('simAccYears').value) || 20;
    body = {
      tickers:              retTickers.map(t => ({ code: t.code, name: t.name, weight: t.weight })),
      initial_capital:      parseFloat(document.getElementById('simSeed').value) || 0,
      monthly_contribution: parseFloat(document.getElementById('simMonthly').value) || 0,
      accumulation_years:   retAccYrs,
      dividend_mode:        document.querySelector('input[name="simDividend"]:checked').value,
      rebal_mode:           document.querySelector('input[name="simRebal"]:checked').value,
      band_width:           Number(document.getElementById('simBandSlider').value) / 100,
      monthly_withdrawal:   parseFloat(document.getElementById('simWithdraw').value) || 0,
      withdrawal_years:     parseInt(document.getElementById('simWdYears').value) || 30,
      inflation:            parseFloat(document.getElementById('simInflation').value) / 100 || 0,
      pension_start_age:    parseInt(document.getElementById('simPensionStartAge')?.value) || 65,
      target_percentile:    targetProb,
      use_synthetic:        document.getElementById('retUseSyntheticCheck')?.checked ?? false,
      tax_enabled:          retTaxOn,
      account_type:         (window.taxAccounts && window.taxAccounts[0]) ? (window.taxAccounts[0].type || '위탁') : '위탁',
      isa_renewal:          retTaxOn && (document.getElementById('isaRenewalCheck')?.checked ?? false),
      gain_harvesting:      retTaxOn && (window.taxAccounts || []).some(a => a.type === '위탁') && (document.getElementById('gainHarvestingCheck')?.checked ?? false),
      user_settings: retTaxOn ? {
        age:           retAge,
        earned_income: parseFloat(taxProfile.earned_income || 0),
        isa_type:      taxProfile.isa_type || 'general',
        pension_age:   parseInt(taxProfile.pension_age || 65),
      } : {},
    };
    // 멀티계좌(적립기) — 계좌 2개 이상이면 accounts/분배정책 부착.
    const _retAp = retTaxOn ? buildRetAccountsPayload(body.rebal_mode, body.band_width, body.dividend_mode) : null;
    if (_retAp === false) {
      document.getElementById('retRunBtn').disabled = false;
      document.getElementById('retLoading').style.display = 'none';
      document.getElementById('retResultEmpty').style.display = 'flex';
      retHideProgressUI && retHideProgressUI();
      return;
    }
    if (_retAp && _retAp.length > 1) {
      body.accounts = _retAp;
      body.distribution_policy = buildDistributionPolicy(_retAp);
      body.reinvest_tax_credit = document.getElementById('taxDeductionReinvest')?.checked ?? false;
      body.manual_comprehensive_years = [];
    }
  } else {
    const retTaxOn = window.retTaxEnabled || false;
    if (retTaxOn && (!window.retTaxProfile || Object.keys(window.retTaxProfile).length === 0)) {
      await loadRetTaxProfile();
    }
    const taxProfile = window.retTaxProfile || {};
    const wdRebal = document.querySelector('input[name="wdRebal"]:checked').value;
    const wdBand  = Number(document.getElementById('wdBandSlider').value) / 100;
    const wdDiv   = document.querySelector('input[name="wdDividend"]:checked').value;
    body = {
      tickers:            retTickers.map(t => ({ code: t.code, name: t.name, weight: t.weight })),
      initial_capital:    parseFloat(document.getElementById('wdSeed').value) || 0,
      monthly_withdrawal: parseFloat(document.getElementById('wdWithdraw').value) || 0,
      withdrawal_years:   parseInt(document.getElementById('wdYears').value) || 30,
      inflation:          parseFloat(document.getElementById('wdInflation').value) / 100 || 0,
      pension_start_age:  parseInt(document.getElementById('wdPensionStartAge')?.value) || 65,
      dividend_mode:      wdDiv,
      rebal_mode:         wdRebal,
      band_width:         wdBand,
      target_percentile:  targetProb,
      tax_enabled:        retTaxOn,
      account_type:       (window.taxAccounts && window.taxAccounts[0]) ? (window.taxAccounts[0].type || '위탁') : '위탁',
      gain_harvesting:    retTaxOn && (window.taxAccounts || []).some(a => a.type === '위탁'),
      user_settings: retTaxOn ? {
        age:           parseInt(taxProfile.age || 40),
        earned_income: parseFloat(taxProfile.earned_income || 0),
        isa_type:      taxProfile.isa_type || 'general',
        pension_age:   parseInt(document.getElementById('wdPensionStartAge')?.value) || 65,
      } : {},
      _withdrawal_only:   true,
    };
    // 멀티계좌(인출기) — 계좌 2개 이상이면 accounts 부착(시작 목돈·미실현차익, 월적립 없음).
    const _wdAp = retTaxOn ? buildWdAccountsPayload(wdRebal, wdBand, wdDiv) : null;
    if (_wdAp === false) {
      document.getElementById('retRunBtn').disabled = false;
      document.getElementById('retLoading').style.display = 'none';
      document.getElementById('retResultEmpty').style.display = 'flex';
      retHideProgressUI && retHideProgressUI();
      return;
    }
    if (_wdAp && _wdAp.length > 1) {
      body.accounts = _wdAp;
      body.distribution_policy = buildDistributionPolicy(_wdAp);
    }
  }

  // D4 거래수수료 — opt-in 시 탭레벨 수수료율(decimal) 동봉(계좌별 율은 accounts에).
  if (document.getElementById('feeEnabledChk')?.checked) {
    body.fee_enabled = true;
    body.fee_rate = (Number(document.getElementById('feeRateInput').value) || 0) / 100;
    body.fee_market = (typeof mmFeeMarket === 'function') ? mmFeeMarket() : 'domestic_stock';
    body.fee_preset = document.getElementById('feePreset')?.value || 'custom';
  }

  // 납입 한도 soft 경고 — 강행 재시도 또는 "오늘 하루 묻지 않기"면 override
  if (body.tax_enabled && (_limitOverride || window.MMLimit?.skipToday())) {
    body.allow_limit_override = true;
  }

  try {
    const submitRes = await fetch('/api/retirement/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const submitData = await submitRes.json();
    if (submitRes.status === 429) throw new Error(submitData.error);
    const { task_id } = submitData;
    _retTaskId = task_id;
    sessionStorage.removeItem('mm_result_retirement');
    sessionStorage.setItem('mm_task_retirement', JSON.stringify({task_id, body, timestamp: Date.now()}));
    const data = await retPollTask(task_id);
    if (data) {
      renderRetirement(data, body);
      window.MMLimit?.attach('retResultContent', data.limit_warnings);
      renderFeeSummary('retResultContent', data.total_fees);
      try { sessionStorage.setItem('mm_result_retirement', JSON.stringify({result: data, body, ts: Date.now()})); } catch(e) {}
    }
  } catch(e) {
    if (e.message !== 'CANCELLED') {
      let _errData = e._data;
      if (!_errData) { try { _errData = JSON.parse(e.message); } catch(_) {} }
      let _handled = false;
      if (_errData && _errData.error) {
        const _errType = _errData.error;
        if (_errType === 'limit_confirm') {
          _handled = true;
          document.getElementById('retResultEmpty').style.display = 'flex';
          if (await window.MMLimit.confirm(_errData.violations || [])) {
            return runRetirement(true);
          }
        } else if (_errType === 'account_restrictions' || _errType === 'isa_windmill_disabled') {
          const banner = document.getElementById('retAccountRestrictBanner');
          const detail = document.getElementById('retAccountRestrictDetail');
          if (banner && detail) {
            detail.innerHTML = (_errData.violations || []).map(v => `<div>• ${v}</div>`).join('');
            if (_errData.disclaimer) detail.innerHTML += `<div style="margin-top:6px;font-style:italic;">${_errData.disclaimer}</div>`;
            banner.style.display = 'block';
            _handled = true;
          }
        }
      }
      if (!_handled) mmToast('오류가 발생했습니다: ' + e.message, 'error');
    }
  } finally {
    sessionStorage.removeItem('mm_task_retirement');
    _retTaskId = null;
    document.getElementById('retRunBtn').disabled       = false;
    document.getElementById('retLoading').style.display = 'none';
  }
}

async function retPollTask(taskId, maxWait = 600000) {
  const start = Date.now();
  let _initialRank = null;
  while (Date.now() - start < maxWait) {
    if (_retCancelled) { _retCancelled = false; throw new Error('CANCELLED'); }
    await new Promise(r => setTimeout(r, 1500));
    if (_retCancelled) { _retCancelled = false; throw new Error('CANCELLED'); }
    const res  = await fetch(`/api/task/${taskId}`);
    const data = await res.json();

    if (data.status === 'PENDING') {
      const rank = data.queue_rank;
      if (rank !== null && rank !== undefined) {
        if (_initialRank === null) _initialRank = Math.max(rank, 1);
        const rawPct = Math.round((_initialRank - rank) / _initialRank * 100);
        const pct = Math.min(99, Math.max(8, rawPct));
        retUpdateProgressUI({ phase: '대기 중', queueRank: rank, isWaiting: true, avgDuration: data.avg_duration, percent: pct });
      } else {
        retUpdateProgressUI({ phase: '준비 중', percent: 0, isWaiting: false });
      }
    } else if (data.status === 'PROGRESS') {
      retUpdateProgressUI({ phase: data.phase === 'preparing' ? '데이터 준비 중' : '계산 중', percent: data.percent, current: data.current, total: data.total, elapsed: data.elapsed, eta: data.eta, isWaiting: false });
    } else if (data.status === 'CANCELLED') {
      throw new Error('CANCELLED');
    } else if (data.status === 'SUCCESS') {
      return data.result;
    } else if (data.status === 'FAILURE') {
      const _e = new Error(data.error || '시뮬레이션 실패');
      _e._data = data.error_data || null;
      throw _e;
    }
  }
  throw new Error('시간 초과 (10분)');
}

function retShowProgressUI() {
  const phaseEl = document.getElementById('retProgressPhase');
  if (phaseEl) phaseEl.textContent = '준비 중...';
  const barEl = document.getElementById('retProgressBar');
  if (barEl) barEl.style.width = '0%';
  const detailEl = document.getElementById('retProgressDetail');
  if (detailEl) detailEl.textContent = '계산 준비 중';
  const etaEl = document.getElementById('retProgressEta');
  if (etaEl) etaEl.textContent = '';
}

function _retSetAnim(barEl) {
  if (barEl.dataset.anim === '1') return;
  barEl.style.transition = 'none';
  barEl.style.animation  = 'mm-indeterminate 1.4s ease-in-out infinite';
  barEl.style.width      = '40%';
  barEl.dataset.anim     = '1';
}
function retUpdateProgressUI({ phase, queueRank, isWaiting, avgDuration, percent, current, total, elapsed, eta }) {
  const phaseEl  = document.getElementById('retProgressPhase');
  const barEl    = document.getElementById('retProgressBar');
  const detailEl = document.getElementById('retProgressDetail');
  const etaEl    = document.getElementById('retProgressEta');
  if (!phaseEl) return;
  if (isWaiting) {
    barEl.dataset.anim    = '';
    barEl.style.animation = '';
    barEl.style.transition = 'width 0.5s';
    barEl.style.left      = '0%';
    barEl.style.width     = `${percent}%`;
    phaseEl.textContent   = queueRank > 0
      ? `⏳ 내 앞에 ${queueRank}개 대기 중 (${percent}%)`
      : `⏳ 곧 시작됩니다...`;
    detailEl.textContent  = '앞 계산 완료 후 자동으로 시작됩니다';
    const w = queueRank * (avgDuration || 30);
    const wm = Math.floor(w / 60), ws = w % 60;
    etaEl.textContent = queueRank > 0
      ? (wm > 0 ? `약 ${wm}분 ${ws}초 후 시작 예상` : `약 ${ws}초 후 시작 예상`)
      : '';
  } else if (percent > 0) {
    barEl.dataset.anim    = '';
    barEl.style.animation = '';
    phaseEl.textContent   = `🔄 ${phase || '계산 중'} (${percent}%)`;
    barEl.style.transition = 'width 0.5s';
    barEl.style.left      = '0%';
    barEl.style.width     = `${percent}%`;
    if (current && total) detailEl.textContent = `${current} / ${total} 케이스`;
    if (eta) {
      const m = Math.floor(eta / 60), s = eta % 60;
      etaEl.textContent = m > 0 ? `약 ${m}분 ${s}초 남음` : `약 ${s}초 남음`;
    }
  } else {
    phaseEl.textContent  = '🔄 준비 중...';
    _retSetAnim(barEl);
    detailEl.textContent = '가격 데이터 로딩 중...';
    etaEl.textContent    = '';
  }
}

function retRestoreForm(body) {
  if (!body) return;
  if (body.tickers?.length) {
    retTickers.length = 0;
    body.tickers.forEach(t => retTickers.push({code: t.code, name: t.name || t.code, weight: t.weight}));
    updateRetWeightUI();
  }
  const set = (id, v) => { const el = document.getElementById(id); if (el && v !== undefined) el.value = v; };
  const setSlider = (id, lblId, v, suffix) => {
    const sl = document.getElementById(id); if (sl && v !== undefined) sl.value = v;
    const lbl = document.getElementById(lblId); if (lbl && v !== undefined) lbl.textContent = v + (suffix || '');
    const inp = document.getElementById(id.replace('Slider', 'Input')); if (inp && v !== undefined) inp.value = v;
  };
  // 인출기 결과는 _withdrawal_only(프론트) — _mode 없음. 둘 다 인식해 sim 필드 오염 방지.
  if (body._mode === 'withdrawal' || body._withdrawal_only) {
    set('wdSeed', body.initial_capital);
    set('wdWithdraw', body.monthly_withdrawal);
    setSlider('wdYearsSlider', 'wdYearsLabel', body.withdrawal_years, '년');
    set('wdYears', body.withdrawal_years);
  } else {
    set('simSeed', body.initial_capital);
    set('simMonthly', body.monthly_contribution);
    set('simWithdraw', body.monthly_withdrawal);
    if (body.accumulation_years !== undefined) { set('simAccYears', body.accumulation_years); setSlider('simAccYearsSlider', 'simAccYearsLabel', body.accumulation_years, '년'); }
    if (body.withdrawal_years !== undefined) { set('simWdYears', body.withdrawal_years); setSlider('simWdYearsSlider', 'simWdYearsLabel', body.withdrawal_years, '년'); }
    if (body.dividend_mode) { const el = document.querySelector(`input[name="simDividend"][value="${body.dividend_mode}"]`); if (el) el.checked = true; }
    if (body.rebal_mode) { const el = document.querySelector(`input[name="simRebal"][value="${body.rebal_mode}"]`); if (el) el.checked = true; }
  }
  if (body.target_percentile !== undefined) {
    const tp = Math.round(body.target_percentile * 100);
    set('retTargetProb', tp); set('retTargetProbInput', tp);
  }
  // 복원 후 모든 금액 힌트 값과 동기 (value만 set돼 힌트가 stale해지는 것 방지)
  ['simSeed','simMonthly','simWithdraw','wdSeed','wdWithdraw'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

async function retCancelTask() {
  _retCancelled = true;
  const tid = _retTaskId;
  if (tid) {
    try { await fetch(`/api/task/${tid}/cancel`, {method:'POST'}); } catch(e) {}
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  // 은퇴시뮬 band
  document.querySelectorAll('input[name="simRebal"]').forEach(r => {
    r.addEventListener('change', () => {
      document.getElementById('simBandSettings').style.display = r.value === 'band' ? 'block' : 'none';
    });
  });
  document.getElementById('simBandSlider').addEventListener('input', e => {
    document.getElementById('simBandLabel').textContent   = e.target.value + '%';
    document.getElementById('simBandNoteVal').textContent = e.target.value + '%';
  });
  // 인출기 band
  document.querySelectorAll('input[name="wdRebal"]').forEach(r => {
    r.addEventListener('change', () => {
      document.getElementById('wdBandSettings').style.display = r.value === 'band' ? 'block' : 'none';
    });
  });
  document.getElementById('wdBandSlider').addEventListener('input', e => {
    document.getElementById('wdBandLabel').textContent   = e.target.value + '%';
    document.getElementById('wdBandNoteVal').textContent = e.target.value + '%';
  });

  // 결과는 sessionStorage(탭 유지·브라우저 종료 시 소멸). 옛 localStorage 잔재 청소.
  try { localStorage.removeItem('mm_task_retirement'); localStorage.removeItem('mm_result_retirement'); } catch(e) {}

  const taskSaved = sessionStorage.getItem('mm_task_retirement');
  if (taskSaved) {
    let state;
    try { state = JSON.parse(taskSaved); } catch(e) { sessionStorage.removeItem('mm_task_retirement'); }
    if (state && Date.now() - state.timestamp < 3600000) {
      _retTaskId = state.task_id;
      retShowResults();
      document.getElementById('retRunBtn').disabled = true;
      document.getElementById('retLoading').style.display = 'block';
      document.getElementById('retResultEmpty').style.display = 'none';
      retShowProgressUI();
      try {
        const data = await retPollTask(state.task_id);
        if (data) {
          renderRetirement(data, state.body || {});
          try { sessionStorage.setItem('mm_result_retirement', JSON.stringify({result: data, body: state.body, ts: Date.now()})); } catch(e) {}
        }
      } catch(e) {
        document.getElementById('retResultEmpty').style.display = 'block';
      } finally {
        sessionStorage.removeItem('mm_task_retirement');
        _retTaskId = null;
        document.getElementById('retRunBtn').disabled = false;
        document.getElementById('retLoading').style.display = 'none';
      }
      return;
    }
    sessionStorage.removeItem('mm_task_retirement');
  }

  const resultSaved = sessionStorage.getItem('mm_result_retirement');
  if (resultSaved) {
    try {
      const {result, body, ts} = JSON.parse(resultSaved);
      if (Date.now() - ts < 7200000) {
        renderRetirement(result, body || {});
        retRestoreForm(body);
      } else {
        sessionStorage.removeItem('mm_result_retirement');
      }
    } catch(e) { sessionStorage.removeItem('mm_result_retirement'); }
  }
});

// ── 세금 토글 ──────────────────────────────────────────
window.retTaxEnabled = false;
window.retTaxProfile = {};
// 멀티계좌 공용모듈(multi_account_ui.js) 결합점 — 은퇴 적립 포트폴리오·금액 DOM 주입.
window.taxAccounts = [];
window.MMTAX = {
  portfolioTickers: () => retTickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: (t.weight || 0) * 100 })),
  totalInitId: 'simSeed',
  totalMonId:  'simMonthly',
};

function toggleRetTax(force) {
  const chk = document.getElementById('retTaxToggleChk');
  const on  = force !== undefined ? !!force : (chk ? chk.checked : !window.retTaxEnabled);
  if (chk) chk.checked = on;
  window.retTaxEnabled = on;
  window.taxEnabled    = on;  // 모듈이 참조
  const label = document.getElementById('retTaxLabel');
  if (label) { label.textContent = on ? 'ON' : 'OFF'; label.style.color = on ? 'var(--brand-text)' : 'var(--ds-muted)'; }
  document.getElementById('retTaxPanel').style.display = on ? 'block' : 'none';
  if (on) {
    retExpandAdvanced();
    if (window.taxAccounts.length === 0) addTaxAccount();
    else renderTaxAccounts();
    loadRetTaxProfile();
  }
}

async function loadRetTaxProfile() {
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

  window.retTaxProfile = settings || {};
  const profileInfo = document.getElementById('retTaxProfileInfo');
  if (profileInfo) {
    const hasProfile = window.retTaxProfile.earned_income != null || window.retTaxProfile.age != null;
    profileInfo.innerHTML = hasProfile
      ? `연소득 ${fmtKRW(window.retTaxProfile.earned_income || 0)} · 나이 ${window.retTaxProfile.age || 40}세 <a href="/tax-settings" style="color:var(--blue);margin-left:6px;">수정</a>`
      : '저장된 세금 설정이 없습니다. <a href="/tax-settings" style="color:var(--blue);">세금 설정</a>에서 입력하세요.';
  }
  updateRetTaxInfo();
}

function updateRetTaxInfo() {
  const taxProfile = window.retTaxProfile || {};
  const age     = parseInt(taxProfile.age || 40);
  const accYrs  = parseInt(document.getElementById('simAccYears')?.value || 20);
  const monthly = parseFloat(document.getElementById('simWithdraw')?.value || 0);
  const account = (window.taxAccounts && window.taxAccounts[0]) ? (window.taxAccounts[0].type || '위탁') : '위탁';

  // 연금 수령 시작 나이: max(55, age+accYrs) 기본값. 사용자 입력 우선.
  const pensionInput = document.getElementById('simPensionStartAge');
  const defaultPensionAge = Math.max(55, age + accYrs);
  if (pensionInput && !pensionInput._manualOverride) pensionInput.value = defaultPensionAge;
  const rawAge = pensionInput ? parseInt(pensionInput.value) : defaultPensionAge;
  const withdrawAge = Math.max(55, rawAge || defaultPensionAge);
  const hint = document.getElementById('simPensionStartAgeHint');
  if (hint) hint.style.display = (rawAge && rawAge < 55) ? 'block' : 'none';
  const annual  = monthly * 12;

  // ISA 풍차/절세매도 섹션 표시는 멀티계좌 모듈(renderTaxAccounts)이 계좌 구성으로 처리.

  let taxInfo = `<b>수령 시작 나이:</b> ${withdrawAge}세`;

  if (account === '연금저축' || account === 'IRP') {
    const rate = withdrawAge >= 80 ? 3.3 : withdrawAge >= 70 ? 4.4 : 5.5;
    const afterTaxMonthly = Math.round(monthly * (1 - rate / 100));
    const THRESHOLD = 15_000_000;

    if (annual > THRESHOLD) {
      taxInfo += `<br><b>연금소득세:</b> ${rate}% + 초과분 최대 16.5%`;
      taxInfo += `<br>⚠ 연 ${(annual/1e4).toFixed(0)}만원 → 1,500만 초과분 별도 과세`;
    } else {
      taxInfo += `<br><b>연금소득세율:</b> ${rate}%`;
    }
    taxInfo += `<br><b>세후 월 실수령 (근사):</b> <span style="color:var(--blue);font-weight:700;">약 ${(afterTaxMonthly/1e4).toFixed(0)}만원</span>`;

    if (withdrawAge < 70)
      taxInfo += `<br><span style="color:var(--text-muted);font-size:0.72rem;">${70 - withdrawAge}년 후(70세) 4.4%로 자동 인하</span>`;
    else if (withdrawAge < 80)
      taxInfo += `<br><span style="color:var(--text-muted);font-size:0.72rem;">${80 - withdrawAge}년 후(80세) 3.3%로 자동 인하</span>`;

  } else if (account === 'ISA') {
    taxInfo += `<br><b>만기 세금:</b> 순이익 200만 공제 후 9.9%`;
  } else {
    taxInfo += `<br><b>배당세:</b> 15.4% 적용 / 최종 청산세 별도`;
  }

  const infoEl = document.getElementById('retTaxInfo');
  if (infoEl) infoEl.innerHTML = taxInfo;
}

// ── 결과 렌더링 ──
function retUpdateSplitPlan(years) {
  years = parseInt(years);
  const label = document.getElementById('retSplitYearsLabel');
  if (label) label.textContent = years + '년';
  const plan = window._retSplitSaleData;
  if (!plan) return;
  const byYear = plan.plan_by_year || {};
  const afterTaxByYear = plan.after_tax_by_year || {};
  const splitTax = byYear[String(years)] ?? plan.lump_sum_tax;
  const splitAfterTax = afterTaxByYear[String(years)] ?? (plan.gain - splitTax);
  const lumpAfterTax = plan.lump_sum_after_tax ?? (plan.gain - plan.lump_sum_tax);
  const saving = plan.lump_sum_tax - splitTax;
  const el = document.getElementById('retSplitMetrics');
  if (!el) return;
  el.innerHTML = [
    { label: '일괄 청산 세금',     value: fmtKRW(plan.lump_sum_tax), cls: '' },
    { label: years + '년 분할 세금', value: fmtKRW(splitTax),          cls: '' },
    { label: '일괄 세후 이익',     value: fmtKRW(lumpAfterTax),      cls: '' },
    { label: years + '년 세후 이익', value: fmtKRW(splitAfterTax),     cls: '' },
    { label: '절감액',             value: fmtKRW(saving),            cls: '' },
    { label: '최적 연수',          value: plan.optimal_years + '년 (세후 ' + fmtKRW(plan.optimal_after_tax ?? (plan.gain - plan.optimal_tax)) + ')', cls: '' },
  ].map(item => `<div style="background:var(--ds-soft);border:1px solid var(--ds-hairline);border-radius:6px;padding:8px 10px;">
      <div style="font-size:0.68rem;color:var(--ds-muted);">${item.label}</div>
      <div style="font-size:0.82rem;font-weight:800;color:var(--ds-ink);">${item.value}</div>
    </div>`).join('');
}

function renderRetirement(data, body) {
  retShowResults();
  document.getElementById('retLoading').style.display       = 'none';
  document.getElementById('retResultEmpty').style.display   = 'none';
  document.getElementById('retResultContent').style.display = 'block';
  retBuildCondSummary(body || {});

  // 금융소득 종합과세 분할매도 패널 (Phase 2f)
  window._retSplitSaleData = data.split_sale_plan || null;
  const retSplitPanel = document.getElementById('retSplitSalePanel');
  if (retSplitPanel) {
    if (data.split_sale_plan && data.split_sale_plan.gain > 20000000) {
      document.getElementById('retKrForeignGain').textContent = fmtKRW(data.split_sale_plan.gain);
      retSplitPanel.style.display = 'block';
      retUpdateSplitPlan(document.getElementById('retSplitYearsSlider')?.value || 5);
    } else {
      retSplitPanel.style.display = 'none';
    }
  }

  const combined  = data.combined_summary || data;
  const survival  = combined.survival_rate;
  const target    = body.target_percentile;

  // 생존율 바
  const pct = Math.round(survival * 100);
  document.getElementById('retSurvivalPct').textContent = pct + '%';
  const bar = document.getElementById('retSurvivalBar');
  bar.style.width = Math.max(pct, 4) + '%';
  bar.textContent = pct + '%';
  bar.className = 'survival-bar-fill ' + (survival >= target ? 'safe' : survival >= target*0.8 ? 'warning' : 'danger');

  // 메시지
  const msgBox  = document.getElementById('retMsgBox');
  const isSafe  = survival >= target;
  msgBox.className = 'ret-msg-box ' + (isSafe ? 'safe' : survival >= target*0.8 ? 'warning' : 'danger');
  const monthly = fmtKRW(body.monthly_withdrawal);
  const wdYears = body.withdrawal_years;
  const tPct    = Math.round(target * 100);
  const inflRate = body.inflation || 0;
  const inflNote = inflRate > 0
    ? ` (인플레이션 ${(inflRate*100).toFixed(1)}% 반영 — 인출액 매년 증가, 명목 수익률 기준 결과)`
    : ' (인플레이션 미반영, 명목 수익률 기준 결과)';
  if (isSafe) {
    msgBox.textContent = `✅ ${tPct}% 신뢰도로 ${wdYears}년간 월 ${monthly} 인출이 가능합니다.${inflNote}`;
  } else {
    const shortfall = Math.round((target - survival) * 100);
    msgBox.textContent = `⚠️ 목표 신뢰도 ${tPct}%에 ${shortfall}%p 부족합니다. 월 인출금을 줄이거나 적립 기간을 늘려보세요.${inflNote}`;
  }

  // 공유 데이터
  try {
    window._retShareData = {
      t: 'ret',
      m: {
        initial:  +((body.initial_asset || 0) / 1e8).toFixed(1),
        monthly:  Math.round((body.monthly_withdrawal || 0) / 10000),
        survival: +(survival * 100).toFixed(1),
        years:    body.withdrawal_years || 0,
      },
    };
  } catch(e) {}
  const retShare = document.getElementById('retShareBtns');
  if (retShare) retShare.style.display = 'flex';

  // 축적기 결과 (시뮬 모드만)
  const showAcc = retMode === 'sim' && data.accumulation_summary;
  document.getElementById('retAccCard').style.display    = showAcc ? 'block' : 'none';
  document.getElementById('retSampleCard').style.display = showAcc ? 'block' : 'none';

  if (showAcc) {
    const acc = data.accumulation_summary;
    document.getElementById('retAccP10').textContent = fmtKRW(acc.end_value.p10);
    document.getElementById('retAccP50').textContent = fmtKRW(acc.end_value.p50);
    document.getElementById('retAccP90').textContent = fmtKRW(acc.end_value.p90);
    document.getElementById('retAccCaseNote').textContent = `※ ${data.acc_cases_count}개 케이스 기준`;
    renderHistogram('retAccChart', data.acc_values, '#42A5F5');

    const tbody = document.getElementById('retSampleBody');
    tbody.innerHTML = (data.sample_results || []).map(s => {
      const sr    = Math.round(s.success_rate * 100);
      const color = sr >= Math.round(target*100) ? '#2E7D32' : sr >= Math.round(target*80) ? '#F57F17' : '#C62828';
      return `<tr>
        <td>p${s.percentile}</td>
        <td>${fmtKRW(s.initial_capital)}</td>
        <td style="font-weight:700;color:${color};">${sr}%</td>
        <td>${fmtKRW(s.end_value_p50)}</td>
      </tr>`;
    }).join('');
  }

  // 멀티계좌 — 적립기=계좌별 적립 분포+절세+자금이동 / 인출기=계좌별 종료자산 분포+절세(공용모듈).
  if (typeof renderMultiAccountSummary === 'function') {
    const maData = (retMode === 'sim') ? (showAcc ? data.multi_account : null)
                                       : (data.multi_account || null);
    renderMultiAccountSummary(
      maData,
      (retMode === 'sim') ? data.g2 : null,
      data.savings || null,   // 절세액 P3: 인출기도 절세 3종 표시(세금 ON 멀티)
      false,
    );
  }

  // 인출기 연금소득세(가구 인출 중앙값) 표시.
  const pensionTaxEl = document.getElementById('retWdPensionTax');
  if (pensionTaxEl) {
    if (retMode === 'wd' && data.median_pension_tax > 0) {
      pensionTaxEl.innerHTML = `🧾 연금 인출 시 예상 연금소득세(중앙값): <b style="color:var(--text);">${fmtKRW(data.median_pension_tax)}</b>/년`;
      pensionTaxEl.style.display = 'block';
    } else {
      pensionTaxEl.style.display = 'none';
    }
  }

  // 인출 투영 가상 윈도우 보충 표시 — 실측 데이터 < 인출기간이면 GBM 합성으로 채움(GAP-RET-KRDATA).
  const synthNoteEl = document.getElementById('retWdSynthNote');
  if (synthNoteEl) {
    const wdReal  = (retMode === 'wd') ? data.n_real
                  : (data.wd_n_real ?? (data.combined_summary || {}).n_windows_real);
    const wdSynth = (retMode === 'wd') ? data.n_synthetic
                  : (data.wd_n_synthetic ?? (data.combined_summary || {}).n_windows_synthetic);
    if (wdSynth > 0) {
      synthNoteEl.innerHTML = `⚠️ 인출 투영: 실측 윈도우 <b>${wdReal || 0}개</b> + 가상 <b>${wdSynth}개</b>`
        + ` — 실제 데이터가 인출 기간보다 짧아 부족분을 통계 기반 가상 시나리오로 보충했습니다. 결과 정확도가 낮을 수 있습니다.`;
      synthNoteEl.style.display = 'block';
    } else {
      synthNoteEl.style.display = 'none';
    }
  }

  // 인출기 종료자산 — p50 축적 시나리오 기준
  const p50Sample = (data.sample_results || []).find(s => s.percentile === 50)
                 || (data.sample_results || [])[Math.floor((data.sample_results||[]).length/2)];
  const p50WdValues = p50Sample ? (p50Sample.wd_end_values || []) : [];

  if (p50WdValues.length) {
    // p10/p50/p90 계산
    const sorted = [...p50WdValues].sort((a,b) => a-b);
    const pIdx = (pct) => sorted[Math.min(Math.floor(sorted.length * pct / 100), sorted.length-1)];
    document.getElementById('retWdP10').textContent = fmtKRW(pIdx(10));
    document.getElementById('retWdP50').textContent = fmtKRW(pIdx(50));
    document.getElementById('retWdP90').textContent = fmtKRW(pIdx(90));
    renderHistogram('retWdChart', p50WdValues, '#66BB6A');
  } else {
    const wdDist = combined.combined_end_value || combined.end_value_dist;
    if (wdDist) {
      document.getElementById('retWdP10').textContent = fmtKRW(wdDist.p10);
      document.getElementById('retWdP50').textContent = fmtKRW(wdDist.p50);
      document.getElementById('retWdP90').textContent = fmtKRW(wdDist.p90);
    }
    // 인출기(wd) 모드 — 전체 종료자산 분포 히스토그램(wd_values)
    if (Array.isArray(data.wd_values) && data.wd_values.length) {
      renderHistogram('retWdChart', data.wd_values, '#66BB6A');
    }
  }

  // 인출 직관 지표 (건전성 + 연차별 잔여자산)
  renderWdInsights(data, body);
}

// ── 인출 건전성 + 연차별 잔여 자산 (백엔드 withdrawal_insights) ──
function renderWdInsights(data, body) {
  const ins        = data.withdrawal_insights;
  const healthCard = document.getElementById('retWdHealthCard');
  const trajCard   = document.getElementById('retWdTrajCard');
  if (!ins || !ins.start_asset) {
    if (healthCard) healthCard.style.display = 'none';
    if (trajCard)   trajCard.style.display = 'none';
    return;
  }

  const startAsset = ins.start_asset;
  const monthly    = body.monthly_withdrawal || 0;
  const infl       = body.inflation || 0;
  const accYears   = body.accumulation_years || 0;
  const wdYears    = body.withdrawal_years || 0;

  // 인플레 반영 은퇴 시점(적립 종료) 월 필요액
  const retireMonthly = monthly * Math.pow(1 + infl, accYears);
  const annualRetWd   = retireMonthly * 12;
  const safe4Monthly  = startAsset * 0.04 / 12;
  const ratio4 = (startAsset * 0.04) > 0 ? annualRetWd / (startAsset * 0.04) : 0;
  const wdRate = startAsset > 0 ? annualRetWd / startAsset : 0;
  const cov    = ins.withdrawal_coverage_p50 || 0;

  const pct = v => (v * 100).toFixed(1) + '%';
  const ratioTag = r => r <= 1 ? '<span style="color:var(--up);">보수적</span>'
                      : r <= 1.2 ? '<span style="color:var(--gold-deep);">적정</span>'
                      : '<span style="color:var(--down);">공격적</span>';

  const depP10 = ins.depletion_p10, depP50 = ins.depletion_p50;
  const depleted10 = depP10 && depP10 < wdYears;
  const depleted50 = depP50 && depP50 < wdYears;
  const depletionTxt   = depleted10 ? `하위10% <span style="white-space:nowrap">${depP10}년차</span>` : depleted50 ? `중앙값 <span style="white-space:nowrap">${depP50}년차</span>` : `${wdYears}년 유지`;
  const depletionColor = depleted10 ? 'var(--down)' : depleted50 ? 'var(--gold-deep)' : 'var(--up)';

  const cards = [
    { l: '은퇴 시작 자산',       v: fmtKRW(startAsset) },
    { l: '은퇴 시점 월 필요액',  v: fmtKRW(Math.round(retireMonthly)) },
    { l: '4% 룰 안전 인출(월)',  v: fmtKRW(Math.round(safe4Monthly)), sub: `내 인출 ${ratio4.toFixed(2)}배 · ${ratioTag(ratio4)}` },
    { l: '인출률 (연)',          v: pct(wdRate) },
    { l: '배당 커버리지',        v: pct(cov), sub: '월 인출 중 배당 충당분' },
    { l: '예상 고갈',            v: `<span style="color:${depletionColor};">${depletionTxt}</span>` },
  ];
  if (ins.mdd_p50) cards.push({ l: '최대 낙폭 (MDD)', v: pct(Math.abs(ins.mdd_p50)) });

  document.getElementById('retWdHealthGrid').innerHTML = cards.map(c => `
    <div class="dist-card">
      <div class="dist-card-label">${c.l}</div>
      <div class="dist-card-value">${c.v}</div>
      ${c.sub ? `<div style="font-size:0.68rem;color:var(--ds-muted);margin-top:4px;">${c.sub}</div>` : ''}
    </div>`).join('');
  healthCard.style.display = 'block';

  // 연차별 잔여 자산
  const traj = ins.trajectory || [];
  if (!traj.length) { trajCard.style.display = 'none'; return; }

  const baseAge   = (body.user_settings && body.user_settings.age)
                 || (window.retTaxProfile && window.retTaxProfile.age) || 40;
  const retireAge = baseAge + accYears;

  document.getElementById('retWdTrajDesc').innerHTML = depleted10
    ? `하위 10% 시나리오에서 약 <b>${depP10}년차</b> 자산 고갈 가능.`
    : `중앙값·하위10% 모두 <b>${wdYears}년</b> 자산 유지.`;

  // 부채꼴 밴드 — 백엔드 연도별 값 배열에서 percentile 계산. 기본 ±25%(=25/75), 슬라이더로 조절.
  window._retTraj = traj;
  const W0 = 25;
  const _bandSlider = document.getElementById('retTrajBand');
  if (_bandSlider) { _bandSlider.value = W0; const _l = document.getElementById('retTrajBandLabel'); if (_l) _l.textContent = W0; }

  if (retCharts['retWdTrajChart']) retCharts['retWdTrajChart'].destroy();
  const brand = (getComputedStyle(document.documentElement).getPropertyValue('--brand') || '#0052ff').trim();
  retCharts['retWdTrajChart'] = new Chart(document.getElementById('retWdTrajChart').getContext('2d'), {
    type: 'line',
    data: {
      labels: traj.map(t => t.year + '년'),
      datasets: [
        { label: `상위 ${50 - W0}%`, data: traj.map(t => retPctile(t.values, 50 + W0)), borderColor: brand + '55', backgroundColor: 'transparent', borderWidth: 1, pointRadius: 0, fill: false },
        { label: `하위 ${50 - W0}%`, data: traj.map(t => retPctile(t.values, 50 - W0)), borderColor: brand + '55', backgroundColor: brand + '1f', borderWidth: 1, pointRadius: 0, fill: '-1' },
        { label: '중앙값',  data: traj.map(t => t.p50), borderColor: brand, backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.2 },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: true, labels: { font: { size: 10 }, boxWidth: 12, color: '#90A4AE' } },
        tooltip: { callbacks: { label: c => c.dataset.label + ': ' + fmtKRW(c.parsed.y) } },
      },
      scales: {
        x: { ticks: { font: { size: 10 }, color: '#90A4AE' }, grid: { display: false } },
        y: { ticks: { font: { size: 10 }, color: '#90A4AE', callback: v => fmtKRW(v) }, grid: { color: 'rgba(0,0,0,0.05)' } },
      },
    },
  });
  trajCard.style.display = 'block';

  // 표 (1·5·10…년차 + 마지막)
  const ymarks = [];
  for (let y = 1; y <= wdYears; y++) { if (y === 1 || y % 5 === 0 || y === wdYears) ymarks.push(y); }
  const rows = ymarks.map(y => {
    const t = traj[y - 1]; if (!t) return '';
    const life = retireMonthly * Math.pow(1 + infl, y - 1);
    return `<tr><td>${y}년차</td><td>${retireAge + y - 1}세</td><td>${fmtKRW(Math.round(life))}</td><td>${fmtKRW(t.p50)}</td></tr>`;
  }).join('');
  document.getElementById('retWdTable').innerHTML =
    `<thead><tr><th>연차</th><th>나이</th><th>월 필요생활비</th><th>잔여자산(중앙)</th></tr></thead><tbody>${rows}</tbody>`;
}

function retToggleWdTable() {
  const wrap = document.getElementById('retWdTableWrap');
  const btn  = document.getElementById('retWdTableToggle');
  const show = wrap.style.display === 'none';
  wrap.style.display = show ? 'block' : 'none';
  if (btn) btn.textContent = show ? '표 닫기' : '표로 보기';
}

function retPctile(arr, p) {
  if (!arr || !arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const idx = Math.min(s.length - 1, Math.max(0, Math.round((p / 100) * (s.length - 1))));
  return s[idx];
}

// 부채꼴 밴드 폭 조절 (±w% → 하위(50-w)~상위(50+w) percentile)
function retUpdateTrajBand(w) {
  w = parseInt(w, 10);
  const lbl = document.getElementById('retTrajBandLabel');
  if (lbl) lbl.textContent = w;
  const ch = retCharts['retWdTrajChart'];
  const traj = window._retTraj;
  if (!ch || !traj) return;
  ch.data.datasets[0].data  = traj.map(t => retPctile(t.values, 50 + w));
  ch.data.datasets[0].label = `상위 ${50 - w}%`;
  ch.data.datasets[1].data  = traj.map(t => retPctile(t.values, 50 - w));
  ch.data.datasets[1].label = `하위 ${50 - w}%`;
  ch.update();
}

function renderHistogram(canvasId, values, color) {
  if (retCharts[canvasId]) retCharts[canvasId].destroy();
  if (!values || !values.length) return;

  // 0원(실패) 케이스 분리
  const zeroCount   = values.filter(v => v <= 0).length;
  const nonZero     = values.filter(v => v > 0);

  const allLabels = [], allData = [], allColors = [];

  // 0원 케이스 별도 표시
  if (zeroCount > 0) {
    allLabels.push('₩0 (고갈)');
    allData.push(zeroCount);
    allColors.push('#EF9A9A');
  }

  // 나머지 구간 히스토그램 — 모바일은 축약 라벨(₩풀표기가 회전·겹침으로 뭉개짐, F-6 R3)
  const isMobileHist = window.matchMedia('(max-width: 768px)').matches;
  const fmtCompact = v => v >= 1e8 ? +(v / 1e8).toFixed(1) + '억'
                        : v >= 1e4 ? Math.round(v / 1e4).toLocaleString() + '만'
                        : '₩' + Math.round(v).toLocaleString();
  if (nonZero.length) {
    const min     = Math.min(...nonZero), max = Math.max(...nonZero);
    const nBins   = Math.min(9, nonZero.length);
    const binSize = (max - min) / nBins || 1;
    const bins    = Array(nBins).fill(0);
    nonZero.forEach(v => { const i = Math.min(Math.floor((v - min) / binSize), nBins - 1); bins[i]++; });
    bins.forEach((cnt, i) => {
      const mid = min + binSize * (i + 0.5);
      allLabels.push(isMobileHist ? fmtCompact(mid) : fmtKRW(mid));
      allData.push(cnt);
      allColors.push(color + '99');
    });
  }

  retCharts[canvasId] = new Chart(document.getElementById(canvasId).getContext('2d'), {
    type: 'bar',
    data: { labels: allLabels, datasets: [{ data: allData, backgroundColor: allColors, borderColor: allColors.map(c => c.replace('99','')), borderWidth: 1.5, borderRadius: 4 }] },
    options: {
      responsive: true, plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { font: { size: 10 }, color: '#90A4AE',
                      autoSkip: true, maxTicksLimit: isMobileHist ? 6 : 12 }, grid: { display: false } },
        y: { ticks: { font: { size: 10 }, color: '#90A4AE' }, grid: { color: 'rgba(0,0,0,0.05)' } }
      }
    }
  });
}

// ── 공유 (C5) ──
async function retMakeCanvas() {
  const el = document.getElementById('retResultContent');
  const body = window._retShareData || {};
  const m = body.m || {};
  const initial = m.initial !== undefined ? Number(m.initial).toLocaleString() + '억' : '—';
  const monthly = m.monthly ? Number(m.monthly).toLocaleString() + '만/월' : '없음';
  const survival = m.survival !== undefined ? m.survival + '%' : '—';
  const years = m.years ? m.years + '년' : '—';
  return html2canvas(el, {
    scale: 2, backgroundColor: (typeof MM_DARK !== 'undefined' && MM_DARK) ? '#0E141C' : '#F0F4F8', useCORS: true, allowTaint: true,
    onclone: function(doc, clonedEl) {
      const hdr = doc.createElement('div');
      hdr.style.cssText = 'background:#1A2332;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;width:100%;box-sizing:border-box;margin-bottom:4px;';
      hdr.innerHTML = '<span style="color:var(--blue-mid);font-size:0.95rem;font-weight:800;">💰 Money Milestone</span>'
                    + '<span style="color:var(--text-muted);font-size:0.78rem;">moneymilestone.co.kr · 무료 투자 분석 도구</span>';
      clonedEl.insertBefore(hdr, clonedEl.firstChild);
      const cond = doc.createElement('div');
      cond.style.cssText = 'background:var(--card);border:1.5px solid var(--border);border-radius:10px;padding:10px 16px;margin-bottom:12px;display:flex;gap:20px;flex-wrap:wrap;font-family:inherit;';
      cond.innerHTML = [
        ['초기자산', initial], ['월적립', monthly], ['목표생존율', survival], ['기간', years],
      ].map(([l,v]) => '<div><span style="font-size:0.68rem;color:var(--text-muted);display:block;">' + l + '</span><span style="font-size:0.82rem;font-weight:700;color:#1A2332;">' + v + '</span></div>').join('');
      hdr.insertAdjacentElement('afterend', cond);
      const origCanvases = el.querySelectorAll('canvas');
      const clonedCanvases = clonedEl.querySelectorAll('canvas');
      origCanvases.forEach(function(orig, i) {
        const cl = clonedCanvases[i];
        if (cl && orig.width > 0) { cl.width = orig.width; cl.height = orig.height; cl.getContext('2d').drawImage(orig, 0, 0); }
      });
    }
  });
}
async function retCopyLink() {
  const btn = event.target; const orig = btn.textContent;
  if (!window._retShareData) { btn.textContent = '⚠️ 먼저 계산하세요'; setTimeout(() => btn.textContent = orig, 2000); return; }
  btn.textContent = '⏳ 생성 중...'; btn.disabled = true;
  try {
    const canvas = await retMakeCanvas();
    const b64 = canvas.toDataURL('image/png');
    const res = await fetch('/api/share/upload', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({image: b64}),
    });
    const { id } = await res.json();
    const url = location.origin + '/share/img/' + id;
    const box = document.getElementById('retShareUrlBox');
    if (box) { box.style.display = 'block'; box.innerHTML = '🔗 공유 링크: <a href="' + url + '" target="_blank">' + url + '</a>'; }
    await mmCopyText(url);
    btn.textContent = '✅ 복사됨!';
    setTimeout(() => btn.textContent = orig, 2000);
  } catch(e) {
    btn.textContent = '⚠️ 오류'; setTimeout(() => btn.textContent = orig, 2000);
  } finally { btn.disabled = false; }
}
function retDownloadImg() {
  if (typeof html2canvas === 'undefined') { mmToast('html2canvas 로드 중입니다.', 'warn'); return; }
  retMakeCanvas().then(function(canvas) {
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = 'retirement-result.png';
    a.click();
  });
}

// ── D5: 인플레이션 생활비 인포박스 ──────────────────────────
function updateInflationInfo() {
  const monthly  = parseFloat(document.getElementById('simWithdraw')?.value) || 3_000_000;
  const accYears = parseFloat(document.getElementById('simAccYears')?.value)  || 20;
  const infl     = parseFloat(document.getElementById('simInflation')?.value) / 100 || 0.02;
  const wdYears  = parseFloat(document.getElementById('simWdYears')?.value)   || 30;

  const fmtW = v => v >= 1e8 ? (v/1e8).toFixed(1)+'억원' : Math.round(v/10000)+'만원';

  // 은퇴 시점 필요 생활비
  const atRetire = monthly * Math.pow(1 + infl, accYears);

  // 인출 기간 중 연도별 생활비 (5년 단위)
  const milestones = [1, 5, 10, 15, 20, 25, 30].filter(y => y <= wdYears);
  const rows = milestones.map(y => {
    const amt = atRetire * Math.pow(1 + infl, y - 1);
    return `<span style="white-space:nowrap;">은퇴 ${y}년차: <strong>${fmtW(Math.round(amt/10000)*10000)}</strong></span>`;
  }).join(' &nbsp;·&nbsp; ');

  // 인출 기간 총 필요 금액 (월 생활비 합산)
  let total = 0;
  for (let m = 0; m < wdYears * 12; m++) {
    total += atRetire * Math.pow(1 + infl, m / 12);  // 월 금액 × 인플레 누적
  }

  // 표시 포맷 — 백만원 단위
  const fmtTotal = v => {
    if (v >= 1e12) return (v/1e12).toFixed(1) + '조원';
    if (v >= 1e8)  return (v/1e8).toFixed(1) + '억원';
    return Math.round(v/1e6) + '백만원';
  };

  const detail = document.getElementById('inflationInfoDetail');
  if (!detail) return;
  if (infl === 0) {
    detail.innerHTML = `인플레이션 0% — 은퇴 후에도 월 <strong>${fmtW(monthly)}</strong> 고정. 인출 ${wdYears}년간 총 <strong>${fmtTotal(monthly * wdYears * 12)}</strong> 필요.`;
    return;
  }
  detail.innerHTML =
    `지금 월 <strong>${fmtW(monthly)}</strong> 기준, <strong>${accYears}년 후</strong> 은퇴 시 월 <strong>${fmtW(Math.round(atRetire))}</strong> 필요<br>` +
    `<span style="font-size:0.78rem;color:var(--text-muted);">${rows}</span><br>` +
    `<span style="font-size:0.78rem;color:var(--text-muted);">인출 ${wdYears}년간 총 필요 금액: 약 <strong>${fmtTotal(total)}</strong> (명목 기준)</span>`;
}

// 페이지 로드 시 초기 계산
document.addEventListener('DOMContentLoaded', () => {
  updateInflationInfo();
  // 월 인출금/투자기간/인출기간 변경 시 자동 갱신
  ['simWithdraw', 'simAccYears', 'simWdYears'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', updateInflationInfo);
  });
  const slider = document.getElementById('simAccYearsSlider');
  if (slider) slider.addEventListener('input', updateInflationInfo);
  const wdSlider = document.getElementById('simWdYearsSlider');
  if (wdSlider) wdSlider.addEventListener('input', updateInflationInfo);
});
