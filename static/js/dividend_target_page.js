// dividend_target.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 내용 무변경 이동
let dtTickers = [], dtSearchTimer = null, dtCharts = {};
let _dtTaskId = null, _dtCancelled = false;
const dtInput = document.getElementById('dtSearchInput');
const dtDropdown = document.getElementById('dtSearchDropdown');

function badgeColor(b) {
  if (b==='KR ETF'||b==='KOSPI'||b==='KOSDAQ') return '#1976D2';
  if (b==='US ETF'||b==='NASDAQ'||b==='NYSE')   return '#2E7D32';
  return '#78909C';
}

dtInput.addEventListener('input', e => {
  const q = e.target.value.trim();
  if (!q) { dtDropdown.style.display='none'; return; }
  clearTimeout(dtSearchTimer);
  dtDropdown.innerHTML = '<div class="ticker-drop-item"><span class="ticker-drop-name">검색 중...</span></div>';
  dtDropdown.style.display = 'block';
  dtSearchTimer = setTimeout(async () => {
    const data = await fetch(`/api/search?q=${encodeURIComponent(q)}`).then(r=>r.json());
    if (!data.length) { dtDropdown.innerHTML='<div class="ticker-drop-item"><span class="ticker-drop-name">결과 없음</span></div>'; return; }
    dtDropdown.innerHTML = data.map(item=>`
      <div class="ticker-drop-item" onclick="dtAddTicker('${item.code}','${item.name.replace(/'/g,"\\'")}','${item.badge}')">
        <span class="ticker-drop-badge" style="background:${badgeColor(item.badge)}22;color:${badgeColor(item.badge)}">${item.badge}</span>
        <div><div class="ticker-drop-code">${item.code}</div><div class="ticker-drop-name">${item.name}</div></div>
      </div>`).join('');
  }, 250);
});
document.addEventListener('click', e => {
  if (!dtInput.closest('.ticker-search-box').contains(e.target)) dtDropdown.style.display='none';
});

function dtAddTicker(code, name, badge) {
  if (dtTickers.find(t=>t.code===code)) { dtDropdown.style.display='none'; dtInput.value=''; return; }
  dtTickers.push({code, name, badge, weight: dtTickers.length===0?100:0});
  renderDtTickers(); dtDropdown.style.display='none'; dtInput.value='';
}

// 포트폴리오 즐겨찾기 (B1) — weight는 % (0~100) 그대로
if (window.MMFav) MMFav.init({
  mount: 'favBar',
  getTickers: () => dtTickers.map(t => ({ ...t })),
  setTickers: (list) => {
    dtTickers = list.map(t => ({
      code: t.code, name: t.name || t.code, badge: t.badge || '',
      weight: Math.round(Number(t.weight) || 0),
    }));
    renderDtTickers();
  },
});
function dtRemoveTicker(code) { dtTickers=dtTickers.filter(t=>t.code!==code); renderDtTickers(); }
function dtUpdateWeight(code, val) {
  const t=dtTickers.find(t=>t.code===code);
  if(t) t.weight=Math.max(0,Math.min(100,parseInt(val)||0));
  renderDtTickers();
}
function renderDtTickers() {
  const list=document.getElementById('dtTickerList');
  const fill=document.getElementById('dtWeightFill');
  const total=document.getElementById('dtWeightTotal');
  const warn=document.getElementById('dtWeightWarn');
  const sum=dtTickers.reduce((s,t)=>s+t.weight,0);
  list.innerHTML = dtTickers.length===0
    ? '<div class="ticker-empty">종목을 검색해서 추가해보세요</div>'
    : dtTickers.map(t=>`
      <div class="ticker-item">
        <span class="ticker-item-code">${t.code}</span>
        <span class="ticker-item-name">${t.name}</span>
        <div class="ticker-item-weight">
          <input class="weight-input" type="number" value="${t.weight}" min="0" max="100"
            onchange="dtUpdateWeight('${t.code}',this.value)"><span class="weight-pct">%</span>
        </div>
        <input type="range" min="0" max="100" value="${t.weight}" class="ticker-item-slider"
          oninput="dtUpdateWeight('${t.code}',this.value);this.previousElementSibling.previousElementSibling.querySelector('input').value=this.value">
        <button class="ticker-remove" onclick="dtRemoveTicker('${t.code}')">✕</button>
      </div>`).join('');
  fill.style.width = Math.min(sum,100)+'%';
  fill.style.background = sum===100?'var(--green-light)':sum>100?'var(--red-light)':'var(--blue)';
  total.textContent = sum+'%';
  total.className = 'weight-total-num'+(sum===100?' ok':sum>100?' over':'');
  warn.textContent = sum>100?'⚠ 비중 합계가 100%를 초과했어요':sum>0&&sum<100?`나머지 ${100-sum}%는 현금으로 유지됩니다`:'';
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

document.getElementById('dtTargetDiv').addEventListener('input', function() {
  document.getElementById('dtTargetDivHint').textContent = fmtKRW(parseFloat(this.value)||0);
});
document.getElementById('dtProbSlider').addEventListener('input', function() {
  document.getElementById('dtProbLabel').textContent = this.value+'%';
});

// ── 입력 ↔ 결과 뷰 전환 (계산기/포트폴리오 분석 탭과 동일 아키타입) ──
function dtShowResults() {
  document.getElementById('dtInputView').style.display = 'none';
  document.getElementById('dtResultView').style.display = 'block';
}
function dtShowInput() {
  document.getElementById('dtResultView').style.display = 'none';
  document.getElementById('dtInputView').style.display = 'block';
}
function dtEditConditions() { dtShowInput(); }

// ── 고급 옵션 접기/펼치기 (세금·수수료) ──
function dtToggleAdvanced(force) {
  const body = document.getElementById('dtMoreoptBody');
  const tog  = document.getElementById('dtMoreoptToggle');
  if (!body || !tog) return;
  const open = force === undefined ? !body.classList.contains('open') : !!force;
  body.classList.toggle('open', open);
  tog.classList.toggle('open', open);
}
function dtExpandAdvanced() { dtToggleAdvanced(true); }

// ── 세금 토글 + 멀티계좌(공용 모듈 multi_account_ui.js 결합) ──
let dtTaxOn = false;
window.dtTaxProfile = {};
window.taxEnabled = false;          // 공용 모듈 호환
window.taxAccounts = [];
// 결합점: 상단 포트폴리오 = dtTickers(% 그대로), 총 금액 = 시드/월납 center 입력
window.MMTAX = {
  portfolioTickers: () => dtTickers,
  totalInitId: 'dtSeedVal',
  totalMonId:  'dtMonthlyVal',
};
function toggleTax(force) {
  const chk = document.getElementById('dtTaxToggleChk');
  dtTaxOn = force !== undefined ? !!force : (chk ? chk.checked : !dtTaxOn);
  if (chk) chk.checked = dtTaxOn;
  window.taxEnabled = dtTaxOn;
  const label = document.getElementById('dtTaxToggleLabel');
  const wrap  = document.getElementById('dtTaxAccountWrap');
  if (label) { label.textContent = dtTaxOn ? 'ON' : 'OFF'; label.style.color = dtTaxOn ? 'var(--brand-text)' : 'var(--ds-muted)'; }
  if (wrap) wrap.style.display = dtTaxOn ? 'block' : 'none';
  if (dtTaxOn) {
    dtExpandAdvanced();
    loadTaxProfile();
    if (window.taxAccounts.length === 0) addTaxAccount();
    else renderTaxAccounts();
    dtUpdateMultiNote();
  }
}

// 멀티 + 자동 모드 안내(역산 변수 = 계좌 1)
function dtUpdateMultiNote() {
  const note = document.getElementById('dtMultiAutoNote');
  if (note) note.style.display = (window.taxAccounts.length > 1) ? 'block' : 'none';
}
// 공용 모듈의 renderTaxAccounts 후 호출되도록 래핑
const _dtOrigRender = window.renderTaxAccounts;
window.renderTaxAccounts = function () {
  if (_dtOrigRender) _dtOrigRender();
  dtUpdateMultiNote();
};

// ── 거래수수료 (D4) ──
function toggleFeePanel() {
  const on = document.getElementById('feeEnabledChk')?.checked;
  const body = document.getElementById('feePanelBody');
  const label = document.getElementById('feeLabel');
  if (body) body.classList.toggle('is-open', !!on);
  if (label) { label.textContent = on ? 'ON' : 'OFF'; label.style.color = on ? 'var(--brand-text)' : 'var(--ds-muted)'; }
  if (on) dtExpandAdvanced();
  // 멀티계좌면 카드별 수수료 입력 노출/숨김 위해 재렌더.
  if (window.taxEnabled && (window.taxAccounts || []).length > 1) renderTaxAccounts();
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
      💸 총 지불 거래수수료 <b>₩${won}</b> <span style="color:var(--text-muted,#888);font-size:0.78rem;">(중앙값 시나리오, 리밸·재투자 누적)</span>
    </div>`;
}

// 멀티계좌 payload — 계좌 1 = 상단(dtTickers + 시드/월납 center), 2+ = 카드 (calculator 규약 미러)
function buildDtAccountsPayload() {
  const accs = window.taxAccounts;
  const rebalMode    = document.querySelector('input[name="dtRebal"]:checked').value;
  const dividendMode = document.querySelector('input[name="dtDividend"]:checked').value;
  const bandWidth    = Number(document.getElementById('dtBandSlider').value) / 100;
  const feeOn = document.getElementById('feeEnabledChk')?.checked ?? false;
  const primary = {
    type: accs[0]?.type || '위탁',
    initial_capital: parseFloat(document.getElementById('dtSeedVal').value) || 0,
    monthly_contribution: parseFloat(document.getElementById('dtMonthlyVal').value) || 0,
    tickers: dtTickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: t.weight / 100 })),
    rebal_mode: rebalMode, band_width: bandWidth, dividend_mode: dividendMode,
    priority: Number(accs[0]?.priority ?? 1),
    ...(feeOn ? { fee_rate: _mmAccountFeePct(accs[0]) / 100 } : {}),
  };
  const accounts = [primary];
  for (let i = 1; i < accs.length; i++) {
    const accTickers = ensureAccountTickers(i);
    if (accTickers.length === 0) {
      mmToast(`계좌 ${i + 1}에 종목을 최소 1개 이상 추가해주세요.`);
      return false;
    }
    const totalWeight = accTickers.reduce((s, t) => s + (Number(t.weight) || 0), 0);
    if (totalWeight > 100) {
      mmToast(`계좌 ${i + 1}의 비중 합계가 100%를 초과했어요.`);
      return false;
    }
    accounts.push({
      type: accs[i].type || '위탁',
      initial_capital: Number(accs[i].initial_capital || 0),
      monthly_contribution: Number(accs[i].monthly_contribution || 0),
      tickers: accTickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: (Number(t.weight) || 0) / 100 })),
      rebal_mode: rebalMode, band_width: bandWidth, dividend_mode: dividendMode,
      priority: Number(accs[i].priority ?? (i + 1)),
      ...(feeOn ? { fee_rate: _mmAccountFeePct(accs[i]) / 100 } : {}),
    });
  }
  return accounts;
}

async function loadTaxProfile() {
  let settings = {};
  const info = document.getElementById('dtTaxProfileInfo');
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
  window.dtTaxProfile = settings || {};

  const hasProfile = window.dtTaxProfile.earned_income != null || window.dtTaxProfile.age != null;
  if (!hasProfile) {
    info.innerHTML = '⚠ 세금 프로필이 없습니다. <a href="/tax-settings" style="color:var(--blue);">세금 설정 →</a>';
    return;
  }
  const s = window.dtTaxProfile;
  info.innerHTML = `연소득 ${fmtKRW(s.earned_income||0)} · 나이 ${s.age||40}세`;
}

// (계좌 유형은 공용 멀티계좌 카드에서 선택 — 구 dtAccount 라디오 제거, 2026-06-13 G5-E)

// ── 모드 변경 핸들러 ──
function getMode(name) {
  return document.querySelector(`input[name="${name}Mode"]:checked`)?.value || 'fixed';
}

function onModeChange() {
  ['seed','monthly','years'].forEach(v => {
    const mode = getMode(v);
    const extra = document.getElementById(`${v}RangeExtra`);
    const valInput = document.getElementById(`dt${v.charAt(0).toUpperCase()+v.slice(1)}Val`);

    extra.classList.toggle('show', mode === 'explore');
    valInput.disabled = mode === 'optimize';
    valInput.style.opacity = mode === 'optimize' ? '0.3' : '1';

    updateHint(v);
  });
  validateModes();
}

function updateHint(v) {
  const mode = getMode(v);
  const cap  = v.charAt(0).toUpperCase() + v.slice(1);
  const hint = document.getElementById(`dt${cap}Hint`);
  const unit = v === 'years' ? '년' : '원';

  if (mode === 'optimize') {
    hint.textContent = '→ 목표 달성 최소값 자동 계산';
    hint.style.color = '#2E7D32';
    return;
  }
  hint.style.color = '';

  const center = parseFloat(document.getElementById(`dt${cap}Val`).value)||0;
  if (mode === 'fixed') {
    hint.textContent = '→ ' + (unit==='년' ? center+'년' : fmtKRW(center)) + ' (단일)';
  } else {
    const step = parseFloat(document.getElementById(`dt${cap}Step`).value)||0;
    const n    = parseInt(document.getElementById(`dt${cap}N`).value)||0;
    if (step > 0 && n > 0) {
      const vals = [];
      for (let i=-n; i<=n; i++) {
        const x = center + step*i;
        if ((v==='years'&&x>=1)||(v!=='years'&&x>=0)) vals.push(x);
      }
      hint.textContent = '→ ' + vals.map(x=>unit==='년'?x+'년':fmtKRW(x)).join(', ');
    } else {
      hint.textContent = '→ 간격/스텝 입력 필요';
    }
  }
}

document.querySelectorAll('input[name="seedMode"], input[name="monthlyMode"], input[name="yearsMode"]')
  .forEach(el => el.addEventListener('change', onModeChange));
['dtSeedVal','dtSeedStep','dtSeedN','dtMonthlyVal','dtMonthlyStep','dtMonthlyN','dtYearsVal','dtYearsStep','dtYearsN']
  .forEach(id => document.getElementById(id).addEventListener('input', () => {
    const v = id.includes('Seed')?'seed':id.includes('Monthly')?'monthly':'years';
    updateHint(v);
  }));

function validateModes() {
  const modes = ['seed','monthly','years'].map(getMode);
  const rangeCnt = modes.filter(m=>m==='explore').length;
  const autoCnt  = modes.filter(m=>m==='optimize').length;
  const warn = document.getElementById('dtScenarioWarn');
  if (rangeCnt > 2) { warn.style.display='block'; warn.textContent='⚠ 다중 변수는 최대 2개입니다.'; }
  else if (autoCnt > 1) { warn.style.display='block'; warn.textContent='⚠ 역산 변수는 최대 1개입니다.'; }
  else warn.style.display='none';
}

onModeChange();

// ── 리밸런싱 밴드 핸들러 ──
document.querySelectorAll('input[name="dtRebal"]').forEach(el => {
  el.addEventListener('change', function() {
    const show = this.value === 'band';
    document.getElementById('dtBandSettings').style.display = show ? 'block' : 'none';
  });
});
document.getElementById('dtBandSlider').addEventListener('input', function() {
  document.getElementById('dtBandLabel').textContent = this.value + '%';
  document.getElementById('dtBandNoteVal').textContent = this.value;
});

// ── 실행 ──
async function runDividendTarget(_limitOverride) {
  if (!dtTickers.length) { mmToast('종목을 최소 1개 추가해주세요.'); return; }
  if (dtTickers.reduce((s,t)=>s+t.weight,0) !== 100) { mmToast('비중 합계가 100%여야 해요.'); return; }

  const modes = ['seed','monthly','years'].map(getMode);
  if (modes.filter(m=>m==='explore').length > 2) { mmToast('다중 변수는 최대 2개입니다.'); return; }
  if (modes.filter(m=>m==='optimize').length > 1) { mmToast('역산 변수는 최대 1개입니다.'); return; }

  const btn=document.getElementById('dtRunBtn');
  const btnText=document.getElementById('dtRunBtnText');
  const spinner=document.getElementById('dtRunBtnSpinner');
  btn.disabled=true;
  btnText.textContent = modes.includes('optimize') ? '자동 계산 중...' : '계산 중...';
  spinner.style.display='inline';

  dtShowResults();
  const _cs = document.getElementById('dtCondSummary'); if (_cs) _cs.style.display = 'none';
  document.getElementById('dtResultEmpty').style.display   = 'none';
  document.getElementById('dtResultContent').style.display = 'none';
  dtShowProgressUI();

  const mkCfg = (v) => {
    const cap  = v.charAt(0).toUpperCase()+v.slice(1);
    const mode = getMode(v);
    return {
      center: parseFloat(document.getElementById(`dt${cap}Val`).value)||0,
      step:   parseFloat(document.getElementById(`dt${cap}Step`)?.value)||0,
      n:      parseInt(document.getElementById(`dt${cap}N`)?.value)||0,
      mode,
    };
  };

  if (dtTaxOn && (!window.dtTaxProfile || Object.keys(window.dtTaxProfile).length === 0)) {
    await loadTaxProfile();
  }
  const taxProfile = window.dtTaxProfile || {};
  // 계좌 유형 = 멀티계좌 카드(계좌 1)의 type — 한글 값('위탁' 등)도 백엔드 매핑 지원
  const accountType = dtTaxOn ? (window.taxAccounts[0]?.type || '위탁') : 'none';

  const body = {
    tickers:            dtTickers.map(t=>({code:t.code, name:t.name, badge:t.badge, weight:t.weight/100})),
    target_monthly_div: parseFloat(document.getElementById('dtTargetDiv').value)||0,
    probability:        parseFloat(document.getElementById('dtProbSlider').value)/100,
    dividend_mode:      document.querySelector('input[name="dtDividend"]:checked').value,
    rebal_mode:         document.querySelector('input[name="dtRebal"]:checked').value,
    band_width:         Number(document.getElementById('dtBandSlider').value) / 100,
    account_type:       accountType,
    earned_income:      taxProfile.earned_income || 50000000,
    isa_type:           taxProfile.isa_type || 'general',
    user_settings:      dtTaxOn ? taxProfile : undefined,
    seed:    mkCfg('seed'),
    monthly: mkCfg('monthly'),
    years:   mkCfg('years'),
  };

  // 납입 한도 soft 경고 — 강행 재시도 또는 "오늘 하루 묻지 않기"면 override
  if (dtTaxOn && (_limitOverride || window.MMLimit?.skipToday())) {
    body.allow_limit_override = true;
  }

  // 멀티계좌(G5-E): 계좌 2개 이상이면 accounts + 분배정책 동봉 → 백엔드 멀티 분기
  if (dtTaxOn && window.taxAccounts.length > 1) {
    const accountsPayload = buildDtAccountsPayload();
    if (accountsPayload === false) {
      btn.disabled=false; btnText.textContent='시뮬레이션 실행'; spinner.style.display='none';
      dtHideProgressUI(); document.getElementById('dtResultEmpty').style.display='block';
      return;
    }
    body.accounts = accountsPayload;
    body.tax_enabled = true;
    body.distribution_policy = buildDistributionPolicy(accountsPayload);
  }

  // D4 거래수수료 — opt-in 시 탭레벨 수수료율(decimal) 동봉(계좌별 율은 accounts에).
  if (document.getElementById('feeEnabledChk')?.checked) {
    body.fee_enabled = true;
    body.fee_rate = (Number(document.getElementById('feeRateInput').value) || 0) / 100;
    body.fee_market = (typeof mmFeeMarket === 'function') ? mmFeeMarket() : 'domestic_stock';
    body.fee_preset = document.getElementById('feePreset')?.value || 'custom';
  }

  try {
    const res = await fetch('/api/dividend-target/submit', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
    });
    const resData = await res.json();
    if (res.status === 429) throw new Error(resData.error);
    const { task_id } = resData;
    window._dtLastBody = body;
    _dtTaskId = task_id;
    sessionStorage.setItem('mm_task_dividend', JSON.stringify({task_id, body, timestamp: Date.now()}));
    await dtPollTask(task_id);
  } catch(e) {
    if (e.message !== 'CANCELLED') mmToast('오류: '+e.message);
    dtHideProgressUI();
    document.getElementById('dtResultEmpty').style.display = 'block';
  } finally {
    sessionStorage.removeItem('mm_task_dividend');
    _dtTaskId = null;
    btn.disabled=false; btnText.textContent='시뮬레이션 실행'; spinner.style.display='none';
  }
}

async function dtPollTask(taskId, maxWait = 600000) {
  const deadline = Date.now() + maxWait;
  let _initialRank = null;
  let _pollCount = 0;
  while (Date.now() < deadline) {
    if (_dtCancelled) { _dtCancelled = false; throw new Error('CANCELLED'); }
    await new Promise(r => setTimeout(r, _pollCount < 10 ? 300 : 1500));
    _pollCount++;
    if (_dtCancelled) { _dtCancelled = false; throw new Error('CANCELLED'); }
    try {
      const res  = await fetch(`/api/task/${taskId}`);
      const data = await res.json();

      if (data.status === 'PENDING') {
        const rank = data.queue_rank;
        if (rank !== null && rank !== undefined) {
          if (_initialRank === null) _initialRank = Math.max(rank, 1);
          const rawPct = Math.round((_initialRank - rank) / _initialRank * 100);
          const pct = Math.min(99, Math.max(8, rawPct));
          dtUpdateProgressUI({ phase: '대기 중', queueRank: rank, isWaiting: true, avgDuration: data.avg_duration, percent: pct, current: 0, total: 0, eta: null });
        } else {
          dtUpdateProgressUI({ phase: '준비 중', isWaiting: false, percent: 0, current: 0, total: 0, eta: null });
        }
        continue;
      }
      if (data.status === 'PROGRESS') {
        const isLoading = data.phase === 'loading';
        dtUpdateProgressUI({
          phase:     isLoading ? '데이터 로딩 중' : '시뮬레이션 중...',
          isWaiting: false,
          isLoading,
          percent:   data.percent || 0,
          current:   data.current || 0,
          total:     data.total   || 0,
          eta:       isLoading ? null : data.eta,
        });
        continue;
      }
      if (data.status === 'SUCCESS') {
        dtHideProgressUI();
        const result = data.result;
        if (result.error) { mmToast('오류: '+result.error); document.getElementById('dtResultEmpty').style.display='block'; return; }
        renderResult(result, window._dtLastBody || {});
        window.MMLimit?.attach('dtResultContent', result.limit_warnings);
        renderFeeSummary('dtResultContent', result.total_fees);
        try { sessionStorage.setItem('mm_result_dividend', JSON.stringify({result, body: window._dtLastBody, ts: Date.now()})); } catch(e) {}
        return;
      }
      if (data.status === 'CANCELLED') {
        dtHideProgressUI();
        document.getElementById('dtResultEmpty').style.display = 'block';
        document.getElementById('dtResultContent').style.display = 'none';
        return;
      }
      if (data.status === 'FAILURE') {
        dtHideProgressUI();
        document.getElementById('dtResultEmpty').style.display = 'block';
        const _lc = window.MMLimit?.parseError(data.error);
        if (_lc) {
          if (await window.MMLimit.confirm(_lc.violations)) runDividendTarget(true);
          return;
        }
        mmToast('오류: ' + (data.error || '알 수 없는 오류'));
        return;
      }
    } catch(e) {
      dtHideProgressUI();
      document.getElementById('dtResultEmpty').style.display = 'block';
      mmToast('폴링 오류: ' + e.message);
      return;
    }
  }
  dtHideProgressUI();
  document.getElementById('dtResultEmpty').style.display = 'block';
  mmToast('시간 초과: 시뮬레이션이 너무 오래 걸립니다.');
}

function dtShowProgressUI() {
  document.getElementById('dtLoading').style.display = 'block';
  dtUpdateProgressUI({ phase: '준비 중', isWaiting: false, percent: 0, current: 0, total: 0, eta: null });
}

function _dtSetAnim(barEl) {
  if (!barEl || barEl.dataset.anim === '1') return;
  barEl.style.transition = 'none';
  barEl.style.animation  = 'mm-indeterminate 1.4s ease-in-out infinite';
  barEl.style.width      = '40%';
  barEl.dataset.anim     = '1';
}
function dtUpdateProgressUI({ phase, queueRank, isWaiting, isLoading, avgDuration, percent, current, total, eta }) {
  const phaseEl  = document.getElementById('dtProgressPhase');
  const barEl    = document.getElementById('dtProgressBar');
  const detailEl = document.getElementById('dtProgressDetail');
  const etaEl    = document.getElementById('dtProgressEta');
  if (isWaiting) {
    if (barEl) { barEl.dataset.anim = ''; barEl.style.animation = ''; barEl.style.transition = 'width 0.5s'; barEl.style.left = '0%'; barEl.style.width = percent + '%'; }
    if (phaseEl)  phaseEl.textContent  = queueRank > 0 ? `⏳ 내 앞에 ${queueRank}개 대기 중 (${percent}%)` : `⏳ 곧 시작됩니다...`;
    if (detailEl) detailEl.textContent = '앞 계산 완료 후 자동으로 시작됩니다';
    const w = queueRank * (avgDuration || 30);
    const wm = Math.floor(w / 60), ws = w % 60;
    if (etaEl) etaEl.textContent = queueRank > 0 ? (wm > 0 ? `약 ${wm}분 ${ws}초 후 시작 예상` : `약 ${ws}초 후 시작 예상`) : '';
  } else if (isLoading) {
    if (percent > 0) {
      if (barEl) { barEl.dataset.anim = ''; barEl.style.animation = ''; barEl.style.transition = 'width 0.4s ease'; barEl.style.left = '0%'; barEl.style.width = percent + '%'; }
      if (phaseEl)  phaseEl.textContent  = `⬇ 데이터 로딩 중 (${percent}%)`;
      if (detailEl) detailEl.textContent = total > 0 && current > 0 ? `${current} / ${total} 종목 완료` : '종목 데이터 로딩 중...';
    } else {
      _dtSetAnim(barEl);
      if (phaseEl)  phaseEl.textContent  = '⬇ 데이터 로딩 중...';
      if (detailEl) detailEl.textContent = '종목 데이터 로딩 중...';
    }
    if (etaEl) etaEl.textContent = '';
  } else if (percent > 0) {
    if (barEl) { barEl.dataset.anim = ''; barEl.style.animation = ''; barEl.style.transition = 'width 0.4s ease'; barEl.style.left = '0%'; barEl.style.width = percent + '%'; }
    if (phaseEl)  phaseEl.textContent  = `🔄 ${phase || '계산 중'} (${percent}%)`;
    if (detailEl) detailEl.textContent = total > 0 ? `${current} / ${total} 케이스` : '계산 중...';
    if (eta != null) { const m = Math.floor(eta/60), s = eta%60; if (etaEl) etaEl.textContent = m > 0 ? `약 ${m}분 ${s}초 남음` : `약 ${s}초 남음`; }
  } else {
    if (phaseEl)  phaseEl.textContent  = '🔄 준비 중...';
    _dtSetAnim(barEl);
    if (detailEl) detailEl.textContent = '가격 데이터 로딩 중...';
    if (etaEl)    etaEl.textContent    = '';
  }
}

function dtHideProgressUI() {
  document.getElementById('dtLoading').style.display = 'none';
}

function dtRestoreForm(body) {
  if (!body) return;
  if (body.tickers?.length) {
    dtTickers = body.tickers.map(t => ({code: t.code, name: t.name || t.code, badge: t.badge || '', weight: Math.round(t.weight * 100)}));
    renderDtTickers();
  }
  const set = (id, v) => { const el = document.getElementById(id); if (el && v !== undefined) el.value = v; };
  set('dtTargetDiv', body.target_monthly_div);
  if (body.probability !== undefined) {
    set('dtProbSlider', Math.round(body.probability * 100));
    // 슬라이더 프로그램 세팅은 input 이벤트를 안 발생시킴 → 라벨 수동 동기화 (값/위치/라벨 불일치 방지)
    document.getElementById('dtProbLabel').textContent = document.getElementById('dtProbSlider').value + '%';
  }
  if (body.seed?.center !== undefined) set('dtSeedVal', body.seed.center);
  if (body.monthly?.center !== undefined) set('dtMonthlyVal', body.monthly.center);
  if (body.years?.center !== undefined) set('dtYearsVal', body.years.center);
}

async function dtCancelTask() {
  _dtCancelled = true;
  const tid = _dtTaskId;
  if (tid) {
    try { await fetch(`/api/task/${tid}/cancel`, {method:'POST'}); } catch(e) {}
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  // 결과는 sessionStorage(탭 유지·브라우저 종료 시 소멸). 옛 localStorage 잔재 청소.
  try { localStorage.removeItem('mm_task_dividend'); localStorage.removeItem('mm_result_dividend'); } catch(e) {}

  const taskSaved = sessionStorage.getItem('mm_task_dividend');
  if (taskSaved) {
    let state;
    try { state = JSON.parse(taskSaved); } catch(e) { sessionStorage.removeItem('mm_task_dividend'); }
    if (state && Date.now() - state.timestamp < 3600000) {
      _dtTaskId = state.task_id;
      if (state.body) window._dtLastBody = state.body;
      const btn = document.getElementById('dtRunBtn');
      if (btn) btn.disabled = true;
      dtShowResults();
      document.getElementById('dtLoading').style.display = 'block';
      document.getElementById('dtResultEmpty').style.display = 'none';
      try {
        await dtPollTask(state.task_id);
      } catch(e) {
        document.getElementById('dtResultEmpty').style.display = 'block';
      } finally {
        sessionStorage.removeItem('mm_task_dividend');
        _dtTaskId = null;
        if (btn) { btn.disabled = false; document.getElementById('dtRunBtnText').textContent = '시뮬레이션 실행'; document.getElementById('dtRunBtnSpinner').style.display = 'none'; }
        dtHideProgressUI();
      }
      return;
    }
    sessionStorage.removeItem('mm_task_dividend');
  }

  const resultSaved = sessionStorage.getItem('mm_result_dividend');
  if (resultSaved) {
    try {
      const {result, body, ts} = JSON.parse(resultSaved);
      if (Date.now() - ts < 7200000) {
        window._dtLastBody = body || {};
        renderResult(result, body || {});
        renderFeeSummary('dtResultContent', result.total_fees);
        dtRestoreForm(body);
      } else {
        sessionStorage.removeItem('mm_result_dividend');
      }
    } catch(e) { sessionStorage.removeItem('mm_result_dividend'); }
  }
});

// ── 결과 조건 요약 바 ──
function buildDtCondSummary(body) {
  const el = document.getElementById('dtCondSummary');
  if (!el || !body) return;
  const esc = window.mmEsc;  // E-1 공용화: 전역 mmEsc(base.html) 단일 구현 — 로컬 복붙 제거 (2026-07-03) (기존은 따옴표 미이스케이프 — 강화됨)
  const items = [];
  const tk = (body.tickers || []).map(t => `${t.code} ${Math.round((t.weight || 0) * 100)}%`).join(' · ');
  if (tk) items.push(['종목', tk]);
  if (body.target_monthly_div) items.push(['목표 월배당', fmtKRW(body.target_monthly_div)]);
  if (body.probability != null) items.push(['목표 신뢰도', Math.round(body.probability * 100) + '%']);
  const rebalMap = { none:'리밸 안함', monthly:'매월 리밸', quarterly:'분기 리밸', yearly:'매년 리밸', band:'밴드 리밸' };
  if (body.rebal_mode) items.push(['리밸런싱', rebalMap[body.rebal_mode] || body.rebal_mode]);
  const divMap = { reinvest:'재투자', hold:'현금 보유', withdraw:'인출' };
  if (body.dividend_mode) items.push(['배당', divMap[body.dividend_mode] || body.dividend_mode]);
  el.innerHTML = items.map(([l, v], i) =>
    `${i > 0 ? '<span class="bt-cond-sep"></span>' : ''}<span class="bt-cond-item">${l} <b>${esc(v)}</b></span>`
  ).join('');
  el.style.display = items.length ? 'flex' : 'none';
}

// ── 결과 렌더링 ──
// 차트색 ds 토큰 바인딩
function _dtCss(v, fb) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim() || fb; }
function _dtRgba(v, a, fb) {
  const hex = _dtCss(v, fb).replace('#', '');
  if (hex.length < 6) return fb || 'rgba(0,82,255,' + a + ')';
  return `rgba(${parseInt(hex.slice(0,2),16)},${parseInt(hex.slice(2,4),16)},${parseInt(hex.slice(4,6),16)},${a})`;
}
const palette = [ _dtCss('--brand','#0052ff'), _dtCss('--down','#e5484d'), _dtCss('--up','#30a46c'), _dtCss('--gold-deep','#9a6700'), '#9C27B0', '#00BCD4', '#FF5722', '#607D8B' ];

// 예상 월 배당금 분포 막대 차트 (p10~p90)
function drawDistChart(dist) {
  const card = document.getElementById('dtDistChartCard');
  const canvas = document.getElementById('dtDistChart');
  if (!card || !canvas) return;
  if (!dist || dist.p50 == null || dist.p50 <= 0) { card.style.display = 'none'; return; }
  card.style.display = 'block';
  const brand = _dtCss('--brand', '#0052ff');
  const soft  = _dtRgba('--brand', '0.3', 'rgba(0,82,255,0.3)');
  const labels = ['하위 10%', '25%', '중앙값', '75%', '상위 10%'];
  const vals = [dist.p10, dist.p25, dist.p50, dist.p75, dist.p90].map(v => Math.round((v || 0) / 12));
  if (dtCharts['dist']) dtCharts['dist'].destroy();
  dtCharts['dist'] = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: { labels, datasets: [{ data: vals, backgroundColor: vals.map((_, i) => i === 2 ? brand : soft), borderRadius: 6, borderSkipped: false, maxBarThickness: 64 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => fmtKRW(c.raw) + ' / 월' } } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11, weight: '600' }, color: '#90A4AE' } },
        y: { ticks: { callback: v => fmtKRW(v), font: { size: 10 }, color: '#90A4AE', maxTicksLimit: 6 }, grid: { color: 'rgba(0,0,0,0.06)' } }
      }
    }
  });
}

// 절세액 3종 패널 (P4) — 대표 콤보(역산이면 solved 값) 윈도우 p50. 합성-only면 미표시.
function renderDtSavings(data) {
  const el = document.getElementById('dtSavingsPanel');
  if (!el) return;
  const s = data.savings;
  if (!s || !(s.brokerage_assumed_tax > 0)) { el.style.display = 'none'; el.innerHTML = ''; return; }
  const acct = data.savings_account_type || '';
  // 멀티계좌: 계좌별 분해 줄 (G5-E)
  const accRows = (s.accounts || [])
    .filter(a => a.brokerage_assumed_tax > 0 || a.tax_saving > 0)
    .map(a => `
      <div style="display:flex;justify-content:space-between;font-size:0.73rem;color:var(--green);margin-top:3px;">
        <span>계좌 ${(a.account_id ?? 0) + 1} · ${a.type || ''}</span>
        <span>위탁가정 ${fmtKRW(a.brokerage_assumed_tax)} · 실제 ${fmtKRW(a.actual_tax)} · 절세 <b>${fmtKRW((a.tax_saving || 0) + (a.gain_harvest_saving || 0))}</b></span>
      </div>`).join('');
  el.innerHTML = `
    <div style="margin-top:12px;padding:12px;background:var(--green-pale);border:1px solid var(--green-light);border-radius:8px;">
      <div style="font-size:0.8rem;font-weight:800;color:var(--green);margin-bottom:8px;">💰 세금 절감 효과 (중앙값 기준${acct ? ' · ' + acct : ''})</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
        <div><div style="font-size:0.68rem;color:var(--green);">전체 위탁 가정 세금</div><div style="font-size:0.9rem;font-weight:800;color:var(--green);">${fmtKRW(s.brokerage_assumed_tax)}</div></div>
        <div><div style="font-size:0.68rem;color:var(--green);">실제 세금</div><div style="font-size:0.9rem;font-weight:800;color:var(--green);">${fmtKRW(s.actual_tax)}</div></div>
        <div><div style="font-size:0.68rem;color:var(--green);">절세액</div><div style="font-size:0.98rem;font-weight:900;color:var(--green);">약 ${fmtKRW(s.tax_saving)}</div></div>
      </div>
      ${accRows}
      <div style="font-size:0.67rem;color:#7CB342;margin-top:8px;">※ 근사치 — 전체 투자기간 누적(실측 ${s.n_windows}개 윈도우 중앙값). 무청산 기준(잔여 미실현차익 양쪽 미가산). 금융소득종합과세 가산·연금 인출세 미반영. ISA/연금은 세후 재투자 가정.</div>
    </div>`;
  el.style.display = 'block';
}

// 시나리오 곡선 핵심 요약 (단선)
function buildScenSummary(data, body) {
  const el = document.getElementById('dtScenSummary');
  if (!el) return;
  const xKey = data.x_key;
  const lines = data.lines || [];
  const pts = (lines[0] || {}).points || [];
  if (lines.length !== 1 || pts.length < 2) { el.style.display = 'none'; return; }
  const xLabel = xKey === 'seed' ? '초기 투자금' : xKey === 'monthly' ? '월 적립금' : '투자 기간';
  const fmtX = v => xKey === 'years' ? Math.round(v) + '년' : fmtKRW(Math.round(v / 1e4) * 1e4);
  const lo = pts[0], hi = pts[pts.length - 1];
  const tgtP = body && body.probability != null ? body.probability : 0.5;
  let crossX = null;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i];
    if ((a.probability - tgtP) * (b.probability - tgtP) <= 0 && a.probability !== b.probability) {
      const r = (tgtP - a.probability) / (b.probability - a.probability);
      crossX = a[xKey] + (b[xKey] - a[xKey]) * r;
      break;
    }
  }
  const items = [
    ['범위', `${fmtX(lo[xKey])} ~ ${fmtX(hi[xKey])}`],
    ['달성 확률', `${Math.round((lo.probability || 0) * 100)}% → ${Math.round((hi.probability || 0) * 100)}%`],
  ];
  if (crossX != null) items.push([`확률 ${Math.round(tgtP * 100)}% 도달`, `${xLabel} ${fmtX(crossX)}`]);
  el.className = 'bt-cond';
  el.innerHTML = items.map(([l, v], i) => `${i > 0 ? '<span class="bt-cond-sep"></span>' : ''}<span class="bt-cond-item">${l} <b>${v}</b></span>`).join('');
  el.style.display = 'flex';
}

// 등위선 핵심 요약 (양 끝 맞교환)
function buildIsoSummary(data) {
  const el = document.getElementById('dtIsoSummary');
  if (!el) return;
  const lines = data.lines || [{ points: data.points || [] }];
  const pts = (lines[0] || {}).points || [];
  if (lines.length !== 1 || pts.length < 2) { el.style.display = 'none'; return; }
  const xKey = data.x_key, optKey = data.opt_key;
  const fmtV = (k, v) => k === 'years' ? Math.round(v) + '년' : fmtKRW(v);
  const lo = pts[0], hi = pts[pts.length - 1];
  el.className = 'bt-cond';
  el.innerHTML =
    `<span class="bt-cond-item">${data.x_label} <b>${fmtV(xKey, lo[xKey])}</b> 이면 ${data.opt_label} <b>${fmtV(optKey, lo[optKey])}</b></span>` +
    `<span class="bt-cond-sep"></span>` +
    `<span class="bt-cond-item">${data.x_label} <b>${fmtV(xKey, hi[xKey])}</b> 이면 ${data.opt_label} <b>${fmtV(optKey, hi[optKey])}</b></span>`;
  el.style.display = 'flex';
}

function renderResult(data, body) {
  dtShowResults();
  buildDtCondSummary(body);
  document.getElementById('dtResultEmpty').style.display   = 'none';
  document.getElementById('dtResultContent').style.display = 'block';
  renderDtSavings(data);
  document.getElementById('dtSolveSection').style.display  = 'none';
  document.getElementById('dtProbCurveCard').style.display = 'none';
  document.getElementById('dtIsocurveCard').style.display  = 'none';
  ['divShareBtns','divScenShareBtns','divIsoShareBtns'].forEach(id => {
    const e = document.getElementById(id); if (e) e.style.display = 'none';
  });
  ['divShareUrlBox','divScenShareUrlBox','divIsoShareUrlBox'].forEach(id => {
    const e = document.getElementById(id); if (e) { e.style.display = 'none'; e.innerHTML = ''; }
  });
  window._divShareData = null;
  window._divUrlBoxId = null;
  const oldBtn = document.getElementById('dtSwapBtn');
  if (oldBtn) oldBtn.remove();

  const mode = data.mode;

  // 단일 결과 (확률 또는 역산)
  if (mode === 'probability') {
    document.getElementById('dtSolveSection').style.display = 'block';
    const res  = data.result || {};
    const p    = res.probability ? Math.round(res.probability * 100) : 0;
    const dist = res.distribution || {};
    const hasDist = dist.p50 != null && dist.p50 > 0;

    // 역산 결과 (solved_seed / solved_monthly / solved_years)
    let solvedLabel = '', solvedValue = '';
    if (res.solved_years   !== undefined) { solvedLabel = '필요 투자 기간';   solvedValue = res.solved_years ? res.solved_years + '년' : '—'; }
    if (res.solved_seed    !== undefined) { solvedLabel = '필요 초기 투자금'; solvedValue = res.solved_seed > 0 ? fmtKRW(res.solved_seed) : '투자금 불필요'; }
    if (res.solved_monthly !== undefined) { solvedLabel = '필요 월 적립금';   solvedValue = res.solved_monthly > 0 ? fmtKRW(res.solved_monthly) : '적립금 불필요'; }

    // 히어로
    const tgt = body.target_monthly_div ? fmtKRW(body.target_monthly_div) : '—';
    document.getElementById('dtHeroLabel').textContent = solvedLabel || '목표 달성 확률';
    document.getElementById('dtHeroValue').textContent = solvedLabel ? solvedValue : (p + '%');
    let subHtml = `<span>목표 월 배당 <b>${tgt}</b></span>`;
    if (solvedLabel) {
      subHtml += `<span>달성 확률 기준 <b>${p}%</b></span>`;
    } else if (res.cases_count) {
      const nHit = Math.round((res.probability || 0) * res.cases_count);
      subHtml += `<span class="${p >= 50 ? 'opt' : 'pess'}">${res.cases_count}개 시나리오 중 <b>${nHit}개</b> 달성</span>`;
    }
    document.getElementById('dtHeroSub').innerHTML = subHtml;

    // 예상 배당 분포 카드 그리드 (월 배당 기준)
    const monthly50 = hasDist ? Math.round(dist.p50 / 12) : 0;
    const targetPct = (hasDist && body.target_monthly_div > 0) ? Math.round(monthly50 / body.target_monthly_div * 100) : null;
    document.getElementById('dtSolveCards').innerHTML = hasDist ? `
      <div class="dist-card median">
        <div class="dist-card-label">예상 월 배당금 (중앙값)</div>
        <div class="dist-card-value">${fmtKRW(monthly50)}</div>
      </div>
      <div class="dist-card pessimistic">
        <div class="dist-card-label">보수적 (하위 10%)</div>
        <div class="dist-card-value">${fmtKRW(Math.round(dist.p10 / 12))}</div>
      </div>
      <div class="dist-card optimistic">
        <div class="dist-card-label">낙관적 (상위 10%)</div>
        <div class="dist-card-value">${fmtKRW(Math.round(dist.p90 / 12))}</div>
      </div>
      <div class="dist-card">
        <div class="dist-card-label">중간 50% 구간 (p25~p75)</div>
        <div class="dist-card-value" style="font-size:0.95rem;">${fmtKRW(Math.round(dist.p25 / 12))} ~ ${fmtKRW(Math.round(dist.p75 / 12))}</div>
      </div>
      <div class="dist-card">
        <div class="dist-card-label">연 배당금 (중앙값)</div>
        <div class="dist-card-value">${fmtKRW(dist.p50)}</div>
      </div>
      <div class="dist-card">
        <div class="dist-card-label">목표 대비 (중앙값)</div>
        <div class="dist-card-value">${targetPct != null ? targetPct + '%' : '—'}</div>
      </div>` : '<div class="dist-card"><div class="dist-card-label">분포 데이터 없음</div><div class="dist-card-value">—</div></div>';

    drawDistChart(dist);

    // 공유 데이터
    try {
      const tickers = (body.tickers || []).map(t => `${t.code} ${Math.round(t.weight * 100)}%`).join('+');
      window._divShareData = {
        label: tickers,
        cond_rows: [
          ['종목', tickers],
          ['목표 월배당', fmtKRW(body.target_monthly_div)],
          [solvedLabel || '달성 확률', solvedLabel ? solvedValue : p + '%'],
        ],
      };
      window._divUrlBoxId = 'divShareUrlBox';
    } catch(e) {}
    const divShare = document.getElementById('divShareBtns');
    if (divShare) divShare.style.display = 'flex';
    return;
  }

  // 등위선 (자동 모드)
  if (mode === 'isocurve') {
    document.getElementById('dtIsocurveCard').style.display = 'block';
    renderIsocurve(data);
    buildIsoSummary(data);
    try {
      const tkrs = (body.tickers||[]).map(t=>`${t.code} ${Math.round(t.weight*100)}%`).join('+');
      window._divShareData = {
        label: tkrs,
        cond_rows: [
          ['종목', tkrs],
          ['기간', (body.years||0) + '년'],
          ['초기투자', fmtKRW(body.seed||0)],
          ['월적립', body.monthly > 0 ? fmtKRW(body.monthly) : '없음'],
        ],
      };
      window._divUrlBoxId = 'divIsoShareUrlBox';
      document.getElementById('divIsoShareBtns').style.display = 'flex';
    } catch(e) {}
    return;
  }

  // 시나리오 곡선
  document.getElementById('dtProbCurveCard').style.display = 'block';
  drawScenarioChart(data, false);
  buildScenSummary(data, body);
  try {
    const tkrs2 = (body.tickers||[]).map(t=>`${t.code} ${Math.round(t.weight*100)}%`).join('+');
    window._divShareData = {
      label: tkrs2,
      cond_rows: [
        ['종목', tkrs2],
        ['기간', (body.years||0) + '년'],
        ['초기투자', fmtKRW(body.seed||0)],
        ['월적립', body.monthly > 0 ? fmtKRW(body.monthly) : '없음'],
      ],
    };
    window._divUrlBoxId = 'divScenShareUrlBox';
    document.getElementById('divScenShareBtns').style.display = 'flex';
  } catch(e) {}

  // X↔선 전환 버튼 (2변수)
  if (mode === 'scenario_2var') {
    window._scenarioData = data;
    window._scenarioFlipped = false;
    const btn = document.createElement('button');
    btn.id = 'dtSwapBtn';
    btn.textContent = '⇄ X축 / 선 전환';
    btn.className = 'ds-btn ds-btn-ghost ds-btn-sm';
    btn.style.marginTop = '10px';
    btn.onclick = () => { window._scenarioFlipped=!window._scenarioFlipped; drawScenarioChart(window._scenarioData, window._scenarioFlipped); };
    document.getElementById('dtProbCurveCard').appendChild(btn);
  }
}

function drawScenarioChart(data, flipped) {
  let xKey, lines, xLabel, lineLabel;
  const lineLabelOf = (key,v) => key==='years'?v+'년':fmtKRW(v);

  if (!flipped || data.mode==='scenario_1var') {
    xKey=data.x_key; lines=data.lines;
    xLabel   = xKey==='seed'?'초기 투자금':xKey==='monthly'?'월 적립금':'투자 기간';
    lineLabel= data.line_key?(data.line_key==='seed'?'초기 투자금':data.line_key==='monthly'?'월 적립금':'투자 기간'):'';
  } else {
    xKey=data.line_key;
    xLabel   = xKey==='seed'?'초기 투자금':xKey==='monthly'?'월 적립금':'투자 기간';
    lineLabel= data.x_key==='seed'?'초기 투자금':data.x_key==='monthly'?'월 적립금':'투자 기간';
    const origX = [...new Set(data.lines[0].points.map(p=>p[data.x_key]))].sort((a,b)=>a-b);
    const newLV = [...new Set(data.lines.map(l=>l[data.line_key]))].sort((a,b)=>a-b);
    lines = origX.map(xv=>({
      label:`${lineLabel}=${lineLabelOf(data.x_key,xv)}`,
      [data.x_key]:xv,
      points: newLV.map(lv=>{
        const sl=data.lines.find(l=>l[data.line_key]===lv);
        const pt=sl?.points.find(p=>p[data.x_key]===xv);
        return {[xKey]:lv, probability:pt?pt.probability:null};
      })
    }));
  }

  const allX    = [...new Set(lines.flatMap(l=>l.points.map(p=>p[xKey])))].sort((a,b)=>a-b);
  const labels  = allX.map(v=>xKey==='years'?v+'년':fmtKRW(v));
  const allProbs= lines.flatMap(l=>l.points.map(p=>Math.round((p.probability||0)*100)));
  const minP    = Math.max(0, Math.floor(Math.min(...allProbs)/10)*10-5);
  const maxP    = Math.min(100, Math.ceil(Math.max(...allProbs)/10)*10+15);

  document.getElementById('dtChartTitle').textContent =
    lineLabel ? `${xLabel} × 달성 확률 (${lineLabel}별)` : `${xLabel} × 달성 확률`;

  if (dtCharts['prob']) dtCharts['prob'].destroy();
  dtCharts['prob'] = new Chart(document.getElementById('dtProbCurveChart').getContext('2d'), {
    type:'line',
    data:{ labels, datasets: lines.map((line,i)=>({
      label: line.label||'달성 확률',
      data: allX.map(xv=>{ const pt=line.points.find(p=>p[xKey]===xv); return pt?Math.round((pt.probability||0)*100):null; }),
      borderColor:palette[i%palette.length], backgroundColor:palette[i%palette.length]+'15',
      fill:lines.length===1, cubicInterpolationMode:'monotone', pointRadius:5, pointHoverRadius:7, borderWidth:2.5, spanGaps:true,
    }))},
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{
        legend:{display:lines.length>1, position:'top', labels:{font:{size:11}, padding:12, boxWidth:20}},
        tooltip:{callbacks:{
          title:items=>xLabel+': '+labels[items[0].dataIndex],
          label:c=>`${c.dataset.label}: ${c.raw}%`
        }}
      },
      scales:{
        x:{ticks:{font:{size:11,weight:'600'}, color:'#546E7A', maxRotation:0}, grid:{display:true, color:'rgba(0,0,0,0.06)'}},
        y:{min:minP, max:maxP, ticks:{font:{size:11}, color:'#90A4AE', callback:v=>v+'%', stepSize:10}, grid:{color:'rgba(0,0,0,0.07)'}}
      }
    }
  });
}

function renderIsocurve(data) {
  // 버튼/상태 세팅 후 차트 그리기
  drawIsocurveChart(data);
}

function drawIsocurveChart(data) {
  if (dtCharts['iso']) dtCharts['iso'].destroy();
  const xKey    = data.x_key;
  const optKey  = data.opt_key;
  const xLabel  = data.x_label;
  const optLabel = data.opt_label;
  const lines   = data.lines || [{ label: null, points: data.points || [] }];

  const xFmt   = v => xKey   === 'years' ? (Number.isInteger(v) ? v+'년' : v.toFixed(1)+'년') : fmtKRW(v);
  const optFmt = v => optKey === 'years' ? (Number.isInteger(v) ? v+'년' : v.toFixed(1)+'년') : fmtKRW(v);

  document.getElementById('dtIsocurveTitle').textContent =
    data.line_label
      ? `등위선 — ${xLabel} vs ${optLabel} (${data.line_label}별)`
      : `등위선 — ${xLabel} vs ${optLabel}`;

  // Y축 여백 계산
  const allOptVals = lines.flatMap(l => l.points.map(p => p[optKey])).filter(v => v != null);
  const optMin = allOptVals.length ? Math.min(...allOptVals) : 0;
  const optMax = allOptVals.length ? Math.max(...allOptVals) : 30;
  const optRange = optMax - optMin || 1;
  const optAxisMin = Math.max(0, optMin - optRange * 0.2);
  const optAxisMax = optMax + optRange * 0.2;

  const datasets = lines.map((line, i) => ({
    label: line.label || optLabel,
    data: line.points.map(p => ({ x: p[xKey], y: p[optKey] })),
    borderColor: palette[i % palette.length],
    backgroundColor: palette[i % palette.length] + '15',
    fill: lines.length === 1,
    cubicInterpolationMode: 'monotone',
    pointRadius: 6, pointHoverRadius: 8,
    pointBackgroundColor: palette[i % palette.length],
    borderWidth: 2.5,
  }));

  // X축/선 전환 버튼 (선이 2개 이상일 때)
  const oldIsoBtn = document.getElementById('dtIsoSwapBtn');
  if (oldIsoBtn) oldIsoBtn.remove();
  if (data.line_key && lines.length > 1) {
    window._isoOrigData = data;
    const swapBtn = document.createElement('button');
    swapBtn.id = 'dtIsoSwapBtn';
    swapBtn.textContent = '⇄ X축 / 선 전환';
    swapBtn.className = 'ds-btn ds-btn-ghost ds-btn-sm';
    swapBtn.style.cssText = 'margin-bottom:10px;display:block;';
    swapBtn.onclick = () => {
      const d = window._isoOrigData;
      const isNormal = swapBtn.dataset.flipped !== '1';
      if (isNormal) {
        // X축과 선 swap
        swapBtn.dataset.flipped = '1';
        const origXVals = [...new Set(d.lines.flatMap(l => l.points.map(p => p[d.x_key])))].sort((a,b)=>a-b);
        const origLineVals = [...new Set(d.lines.map(l => l[d.line_key]))].sort((a,b)=>a-b);
        const fmtV = (key, v) => key==='years' ? v+'년' : fmtKRW(v);
        const flippedLines = origXVals.map(xv => ({
          label: `${d.x_label}=${fmtV(d.x_key, xv)}`,
          [d.x_key]: xv,
          points: origLineVals.map(lv => {
            const srcLine = d.lines.find(l => l[d.line_key] === lv);
            const pt = srcLine?.points.find(p => p[d.x_key] === xv);
            return pt ? {[d.line_key]: lv, [d.opt_key]: pt[d.opt_key]} : null;
          }).filter(Boolean)
        }));
        const flippedData = {
          ...d,
          x_key: d.line_key, line_key: d.x_key,
          x_label: d.line_label || d.line_key,
          line_label: d.x_label,
          lines: flippedLines,
        };
                    drawIsocurveChart(flippedData);
      } else {
        swapBtn.dataset.flipped = '0';
        drawIsocurveChart(d);
      }
    };
    document.getElementById('dtIsocurveCard').insertBefore(swapBtn,
      document.getElementById('dtIsocurveChart').parentElement);
  }

  dtCharts['iso'] = new Chart(document.getElementById('dtIsocurveChart').getContext('2d'), {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: lines.length > 1, position: 'top', labels: { font:{size:11}, padding:12, boxWidth:20 } },
        tooltip: { callbacks: {
          title: items => xLabel+': '+xFmt(items[0].parsed.x),
          label: c => `${c.dataset.label}: ${optFmt(c.parsed.y)}`,
        }}
      },
      scales: {
        x: {
          type: 'linear',
          title: { display:true, text:xLabel, font:{size:11}, color:'#90A4AE' },
          ticks: { font:{size:11}, color:'#546E7A', callback: xFmt },
          grid:  { color:'rgba(0,0,0,0.06)' }
        },
        y: {
          min: optAxisMin, max: optAxisMax,
          title: { display:true, text:optLabel, font:{size:11}, color:'#90A4AE' },
          ticks: { font:{size:11}, color:'#90A4AE', callback: optFmt },
          grid:  { color:'rgba(0,0,0,0.07)' }
        }
      }
    }
  });
}

// ── 공유 (C5) ──
async function divMakeCanvas() {
  const el = document.getElementById('dtResultContent');
  const sd = window._divShareData || {};
  const condRows = sd.cond_rows || [];
  return html2canvas(el, {
    scale: 2, backgroundColor: (typeof MM_DARK !== 'undefined' && MM_DARK) ? '#0E141C' : '#F0F4F8', useCORS: true, allowTaint: true,
    onclone: function(doc, clonedEl) {
      ['#divShareBtns','#divScenShareBtns','#divIsoShareBtns'].forEach(sel => {
        const e = clonedEl.querySelector(sel); if (e) e.style.display = 'none';
      });
      const hdr = doc.createElement('div');
      hdr.style.cssText = 'background:#1A2332;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;width:100%;box-sizing:border-box;margin-bottom:4px;';
      hdr.innerHTML = '<span style="color:var(--blue-mid);font-size:0.95rem;font-weight:800;">💰 Money Milestone</span>'
                    + '<span style="color:var(--text-muted);font-size:0.78rem;">moneymilestone.co.kr · 무료 투자 분석 도구</span>';
      clonedEl.insertBefore(hdr, clonedEl.firstChild);
      const cond = doc.createElement('div');
      cond.style.cssText = 'background:var(--card);border:1.5px solid var(--border);border-radius:10px;padding:10px 16px;margin-bottom:12px;display:flex;gap:20px;flex-wrap:wrap;font-family:inherit;';
      cond.innerHTML = condRows.map(([l,v]) => '<div><span style="font-size:0.68rem;color:var(--text-muted);display:block;">' + l + '</span><span style="font-size:0.82rem;font-weight:700;color:#1A2332;">' + v + '</span></div>').join('');
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
async function divCopyLink() {
  const btn = event.target; const orig = btn.textContent;
  if (!window._divShareData) { btn.textContent = '⚠️ 먼저 계산하세요'; setTimeout(() => btn.textContent = orig, 2000); return; }
  btn.textContent = '⏳ 생성 중...'; btn.disabled = true;
  try {
    const canvas = await divMakeCanvas();
    const b64 = canvas.toDataURL('image/png');
    const res = await fetch('/api/share/upload', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({image: b64}),
    });
    const { id } = await res.json();
    const url = location.origin + '/share/img/' + id;
    const box = document.getElementById(window._divUrlBoxId || 'divShareUrlBox');
    if (box) { box.style.display = 'block'; box.innerHTML = '🔗 공유 링크: <a href="' + url + '" target="_blank">' + url + '</a>'; }
    await mmCopyText(url);
    btn.textContent = '✅ 복사됨!';
    setTimeout(() => btn.textContent = orig, 2000);
  } catch(e) {
    btn.textContent = '⚠️ 오류'; setTimeout(() => btn.textContent = orig, 2000);
  } finally { btn.disabled = false; }
}
function divDownloadImg() {
  if (typeof html2canvas === 'undefined') { mmToast('html2canvas 로드 중입니다.'); return; }
  divMakeCanvas().then(function(canvas) {
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = 'dividend-result.png';
    a.click();
  });
}
