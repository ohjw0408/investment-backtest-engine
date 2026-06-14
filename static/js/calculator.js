/**
 * Domino Invest — 투자 계산기 JS
 */

// ── 상태 ──
const tickers = [];
const chartInstances = {};
let _calcTaskId = null, _calcCancelled = false;

// ── 폼 복원 ──
function calcRestoreForm(payload) {
  if (!payload) return;
  if (payload.tickers?.length) {
    tickers.length = 0;
    payload.tickers.forEach(t => tickers.push({code: t.code, name: t.name || t.code, badge: t.badge || '', weight: Math.round(t.weight * 100)}));
    renderTickers();
    updateWeightBar();
  }
  const set = (id, v) => { const el = document.getElementById(id); if (el && v !== undefined) el.value = v; };
  if (payload.initial_capital !== undefined) { set('initialCapital', payload.initial_capital); document.getElementById('initialHint').textContent = '₩' + (payload.initial_capital||0).toLocaleString(); }
  if (payload.monthly_contribution !== undefined) { set('monthlyContrib', payload.monthly_contribution); document.getElementById('monthlyHint').textContent = '₩' + (payload.monthly_contribution||0).toLocaleString(); }
  if (payload.years !== undefined) { set('yearsSlider', payload.years); document.getElementById('yearsLabel').textContent = payload.years + '년'; }
  if (payload.dividend_mode) { const el = document.querySelector(`input[name="dividend"][value="${payload.dividend_mode}"]`); if (el) el.checked = true; }
  if (payload.rebal_mode) { const el = document.querySelector(`input[name="rebal"][value="${payload.rebal_mode}"]`); if (el) el.checked = true; }
  if (payload.accounts?.length > 1) {
    if (!window.taxEnabled) toggleTax();
    window.taxAccounts = payload.accounts.map((a, i) => ({
      type: a.type || '위탁',
      initial_capital: Number(a.initial_capital || 0),
      monthly_contribution: Number(a.monthly_contribution || 0),
      tickers: i === 0 ? [] : (a.tickers || []).map(t => ({
        code: t.code,
        name: t.name || t.code,
        badge: t.badge || '',
        weight: Math.round(Number(t.weight || 0) * 100),
      })),
    }));
    renderTaxAccounts();
  }
}

// ── 취소 ──
async function cancelCalcTask() {
  _calcCancelled = true;
  const tid = _calcTaskId;
  if (tid) {
    try { await fetch(`/api/task/${tid}/cancel`, {method:'POST'}); } catch(e) {}
  }
}

// ── 초기화 ──
document.addEventListener('DOMContentLoaded', () => {

  // 포트폴리오 즐겨찾기 (B1) — weight는 % (0~100) 그대로
  if (window.MMFav) MMFav.init({
    mount: 'favBar',
    getTickers: () => tickers.map(t => ({ ...t })),
    setTickers: (list) => {
      tickers.length = 0;
      list.forEach(t => tickers.push({
        code: t.code, name: t.name || t.code, badge: t.badge || '',
        weight: Math.round(Number(t.weight) || 0),
      }));
      renderTickers();
      updateWeightBar();
    },
  });

  document.getElementById('initialCapital').addEventListener('input', e => {
    document.getElementById('initialHint').textContent = '₩' + Number(e.target.value).toLocaleString();
    renderTaxAccounts();
  });

  document.getElementById('monthlyContrib').addEventListener('input', e => {
    document.getElementById('monthlyHint').textContent = '₩' + Number(e.target.value).toLocaleString();
    renderTaxAccounts();
  });

  document.getElementById('yearsSlider').addEventListener('input', e => {
    document.getElementById('yearsLabel').textContent = e.target.value + '년';
  });

  document.querySelectorAll('input[name="rebal"]').forEach(r => {
    r.addEventListener('change', () => {
      document.getElementById('bandSettings').style.display =
        r.value === 'band' ? 'block' : 'none';
    });
  });

  document.getElementById('bandSlider').addEventListener('input', e => {
    document.getElementById('bandLabel').textContent   = e.target.value + '%';
    document.getElementById('bandNoteVal').textContent = e.target.value + '%';
  });

  // 종목 검색
  const searchInput = document.getElementById('tickerSearchInput');
  const dropdown    = document.getElementById('tickerDropdown');

  searchInput.addEventListener('input', e => {
    const q = e.target.value.trim();
    if (!q) { dropdown.style.display = 'none'; return; }

    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      try {
        const res  = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();

        if (!data.length) {
          dropdown.innerHTML = '<div style="padding:12px;font-size:0.82rem;color:var(--text-muted)">검색 결과 없음</div>';
        } else {
          dropdown.innerHTML = data.map(item => `
            <div class="ticker-drop-item"
              onclick="addTicker('${item.code}', '${item.name.replace(/'/g, "\\'")}', '${item.badge}')">
              <span class="ticker-drop-badge"
                style="background:${badgeColor(item.badge)}22;color:${badgeColor(item.badge)}">
                ${item.badge}
              </span>
              <div>
                <div class="ticker-drop-code">${item.code}</div>
                <div class="ticker-drop-name">${item.name}</div>
              </div>
            </div>
          `).join('');
        }
        dropdown.style.display = 'block';
      } catch(e) { console.error(e); }
    }, 200);
  });

  document.addEventListener('click', e => {
    if (!searchInput || !searchInput.closest('.ticker-search-box')?.contains(e.target)) {
      if (dropdown) dropdown.style.display = 'none';
    }
  });

  // ── 페이지 복원 ──
  (async () => {
    const taskSaved = localStorage.getItem('mm_task_calculator');
    if (taskSaved) {
      try {
        const state = JSON.parse(taskSaved);
        if (Date.now() - state.timestamp < 3600000) {
          _calcTaskId = state.task_id;
          document.getElementById('runBtn').disabled = true;
          showProgressUI();
          try {
            const result = await pollTask(state.task_id);
            if (result) {
              hideProgressUI();
              renderResult(result, state.payload || {});
              calcRestoreForm(state.payload);
              localStorage.setItem('mm_result_calculator', JSON.stringify({result, payload: state.payload, ts: Date.now()}));
            }
          } catch(e) {
            if (e.message !== 'CANCELLED') hideProgressUI();
          } finally {
            localStorage.removeItem('mm_task_calculator');
            _calcTaskId = null;
            document.getElementById('runBtn').disabled = false;
            document.getElementById('runBtnText').style.display = 'inline';
            document.getElementById('runBtnSpinner').style.display = 'none';
            hideProgressUI();
          }
          return;
        }
      } catch(e) {}
      localStorage.removeItem('mm_task_calculator');
    }

    const resultSaved = localStorage.getItem('mm_result_calculator');
    if (resultSaved) {
      try {
        const {result, payload, ts} = JSON.parse(resultSaved);
        if (Date.now() - ts < 7200000) {
          renderResult(result, payload || {});
          calcRestoreForm(payload);
        } else {
          localStorage.removeItem('mm_result_calculator');
        }
      } catch(e) { localStorage.removeItem('mm_result_calculator'); }
    }
  })();
});

function badgeColor(badge) {
  if (badge === 'KR ETF' || badge === 'KOSPI' || badge === 'KOSDAQ') return '#1976D2';
  if (badge === 'US ETF' || badge === 'NASDAQ' || badge === 'NYSE')   return '#2E7D32';
  return '#78909C';
}

// ── 균등 비중 재배분 ──
function redistributeWeights() {
  const n = tickers.length;
  if (n === 0) return;
  const base = Math.floor(100 / n);
  tickers.forEach((t, i) => {
    t.weight = (i === n - 1) ? 100 - base * (n - 1) : base;
  });
}

// ── 종목 추가 ──
function addTicker(code, name, badge) {
  if (tickers.find(t => t.code === code)) {
    alert(`${code}는 이미 추가되어 있어요.`);
    return;
  }
  tickers.push({ code, name, badge, weight: 0 });
  redistributeWeights();
  document.getElementById('tickerSearchInput').value = '';
  document.getElementById('tickerDropdown').style.display = 'none';
  renderTickers();
}

// ── 종목 제거 ──
function removeTicker(code) {
  const idx = tickers.findIndex(t => t.code === code);
  if (idx === -1) return;
  tickers.splice(idx, 1);
  if (tickers.length > 0) redistributeWeights();
  renderTickers();
}

// ── 비중 변경 ──
function onWeightChange(code, val) {
  const t = tickers.find(t => t.code === code);
  if (!t) return;
  t.weight = Math.max(0, Math.min(100, Number(val)));
  const item = document.querySelector(`.ticker-item[data-code="${code}"]`);
  if (item) {
    item.querySelector('.weight-input').value       = t.weight;
    item.querySelector('.ticker-item-slider').value = t.weight;
  }
  updateWeightBar();
}

// ── 종목 렌더링 ──
function renderTickers() {
  const list = document.getElementById('tickerList');
  if (tickers.length === 0) {
    list.innerHTML = '<div class="ticker-empty">종목을 검색해서 추가해보세요</div>';
    updateWeightBar();
    return;
  }
  list.innerHTML = tickers.map(t => `
    <div class="ticker-item" data-code="${t.code}">
      <div class="ticker-item-code">${t.code}</div>
      <div class="ticker-item-name">${t.name}</div>
      <div class="ticker-item-weight">
        <input type="number" class="weight-input" value="${t.weight}" min="0" max="100"
          oninput="onWeightChange('${t.code}', this.value)">
        <span class="weight-pct">%</span>
        <input type="range" class="ticker-item-slider" min="0" max="100" value="${t.weight}"
          oninput="onWeightChange('${t.code}', this.value)">
      </div>
      <button class="ticker-remove" onclick="removeTicker('${t.code}')">✕</button>
    </div>
  `).join('');
  updateWeightBar();
}

// ── 비중 합계 바 ──
function updateWeightBar() {
  const total = tickers.reduce((s, t) => s + t.weight, 0);
  const fill  = document.getElementById('weightFill');
  const label = document.getElementById('weightTotal');
  const warn  = document.getElementById('weightWarn');

  label.textContent = total + '%';
  fill.style.width  = Math.min(total, 100) + '%';

  if (total === 100) {
    fill.style.background = 'var(--green-light)';
    label.className = 'weight-total-num ok';
    warn.textContent = '';
  } else if (total > 100) {
    fill.style.background = 'var(--red-light)';
    label.className = 'weight-total-num over';
    warn.textContent = '⚠ 비중 합계가 100%를 초과했어요';
  } else {
    fill.style.background = 'var(--blue)';
    label.className = 'weight-total-num';
    warn.textContent = total > 0 ? `나머지 ${100 - total}%는 현금으로 유지됩니다` : '';
  }
}

function buildCalculatorAccountsPayload(rebalMode, bandWidth, dividendMode) {
  const accs = window.taxAccounts || [];
  if (accs.length <= 1) return null;

  const renewalOn = document.getElementById('isaRenewalCheck')?.checked ?? false;
  const feeOn = document.getElementById('feeEnabledChk')?.checked ?? false;

  const primary = {
    type: accs[0]?.type || '위탁',
    initial_capital: Number(document.getElementById('initialCapital').value) || 0,
    monthly_contribution: Number(document.getElementById('monthlyContrib').value) || 0,
    tickers: tickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: t.weight / 100 })),
    rebal_mode: rebalMode,
    band_width: bandWidth,
    dividend_mode: dividendMode,
    isa_renewal: renewalOn && (accs[0]?.type === 'ISA'),
    priority: Number(accs[0]?.priority ?? 1),
    ...(feeOn ? { fee_rate: _mmAccountFeePct(accs[0]) / 100 } : {}),
  };

  const accounts = [primary];
  for (let i = 1; i < accs.length; i++) {
    const accTickers = ensureAccountTickers(i);
    if (accTickers.length === 0) {
      alert(`계좌 ${i + 1}에 종목을 최소 1개 이상 추가해주세요.`);
      return false;
    }
    const totalWeight = accTickers.reduce((s, t) => s + (Number(t.weight) || 0), 0);
    if (totalWeight > 100) {
      alert(`계좌 ${i + 1}의 비중 합계가 100%를 초과했어요.`);
      return false;
    }
    accounts.push({
      type: accs[i].type || '위탁',
      initial_capital: Number(accs[i].initial_capital || 0),
      monthly_contribution: Number(accs[i].monthly_contribution || 0),
      tickers: accTickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: (Number(t.weight) || 0) / 100 })),
      rebal_mode: rebalMode,
      band_width: bandWidth,
      dividend_mode: dividendMode,
      isa_renewal: renewalOn && (accs[i].type === 'ISA'),
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
  if (body) body.style.display = on ? 'block' : 'none';
  // 멀티계좌면 카드별 수수료 입력 노출/숨김 위해 재렌더.
  if (window.taxEnabled && (window.taxAccounts || []).length > 1) renderTaxAccounts();
}
function applyFeePreset(v) {
  if (v === 'custom') return;
  const inp = document.getElementById('feeRateInput');
  if (inp) inp.value = v;
}
// 결과 하단 "총 지불 수수료" 표시 (없으면 제거)
function renderFeeSummary(containerId, totalFees) {
  const el = document.getElementById(containerId);
  if (!el) return;
  let slot = el.querySelector(':scope > #mmFeeSummary');
  if (totalFees == null) { if (slot) slot.remove(); return; }
  if (!slot) { slot = document.createElement('div'); slot.id = 'mmFeeSummary'; el.appendChild(slot); }
  const won = Math.round(Number(totalFees) || 0).toLocaleString();
  slot.innerHTML = `
    <div style="margin-top:12px;padding:10px 14px;background:var(--bg,#f5f5f5);border:1px solid var(--border,#ddd);border-radius:9px;font-size:0.84rem;color:var(--text,#222);">
      💸 총 지불 거래수수료 <b>₩${won}</b> <span style="color:var(--text-muted,#888);font-size:0.78rem;">(중앙값 시나리오, 매수·매도 누적)</span>
    </div>`;
}

// ── 시뮬레이션 실행 ──
async function runCalculator(_limitOverride) {
  if (tickers.length === 0) { alert('종목을 최소 1개 이상 추가해주세요.'); return; }
  const totalWeight = tickers.reduce((s, t) => s + t.weight, 0);
  if (totalWeight > 100) { alert('비중 합계가 100%를 초과했어요. 조정해주세요.'); return; }

  const btn = document.getElementById('runBtn');
  btn.disabled = true;

  const rebalMode    = document.querySelector('input[name="rebal"]:checked').value;
  const dividendMode = document.querySelector('input[name="dividend"]:checked').value;
  const bandWidth    = Number(document.getElementById('bandSlider').value) / 100;

  const taxEnabled  = window.taxEnabled || false;
  const taxAccounts = window.taxAccounts || [];
  if (taxEnabled && (!window.taxProfile || Object.keys(window.taxProfile).length === 0)) {
    await loadTaxProfileForCalculator();
  }
  const taxProfile  = window.taxProfile || {};
  const isSingle    = taxAccounts.length <= 1;
  const totalInit   = Number(document.getElementById('initialCapital').value);
  const totalMon    = Number(document.getElementById('monthlyContrib').value);
  const accountType = taxAccounts.length > 0 ? taxAccounts[0].type : '위탁';
  const accountsPayload = taxEnabled ? buildCalculatorAccountsPayload(rebalMode, bandWidth, dividendMode) : null;
  if (accountsPayload === false) {
    btn.disabled = false;
    return;
  }

  const payload = {
    tickers:              tickers.map(t => ({ code: t.code, name: t.name, badge: t.badge, weight: t.weight / 100 })),
    initial_capital:      totalInit,
    monthly_contribution: totalMon,
    years:                Number(document.getElementById('yearsSlider').value),
    rebal_mode:           rebalMode,
    band_width:           bandWidth,
    dividend_mode:        dividendMode,
    tax_enabled:          taxEnabled,
    account_type:         accountType,
    isa_renewal:          taxEnabled && (document.getElementById('isaRenewalCheck')?.checked ?? false),
    gain_harvesting:      taxEnabled && (window.taxAccounts||[]).some(a => a.type === '위탁') && (document.getElementById('gainHarvestingCheck')?.checked ?? false),
    use_synthetic:        document.getElementById('useSyntheticCheck')?.checked ?? false,
    user_settings: taxEnabled ? {
      earned_income: Number(taxProfile.earned_income || 0),
      age:           Number(taxProfile.age || 40),
      isa_type:      taxProfile.isa_type || 'general',
      pension_age:   Number(taxProfile.pension_age || 65),
    } : {},
  };
  // 납입 한도 soft 경고 — 강행 재시도 또는 "오늘 하루 묻지 않기"면 override 동봉
  if (taxEnabled && (_limitOverride || window.MMLimit?.skipToday())) {
    payload.allow_limit_override = true;
  }
  // D4 거래수수료 — opt-in 시 탭레벨 수수료율(decimal) 동봉
  if (document.getElementById('feeEnabledChk')?.checked) {
    payload.fee_enabled = true;
    payload.fee_rate = (Number(document.getElementById('feeRateInput').value) || 0) / 100;
  }
  if (accountsPayload && accountsPayload.length > 1) {
    payload.accounts = accountsPayload;
    // G2/G3/G4: 우선순위 분배정책 + 금종세 수동연도 + 세액공제 재투자
    payload.distribution_policy = buildDistributionPolicy(accountsPayload);
    payload.reinvest_tax_credit = taxEnabled && (document.getElementById('taxDeductionReinvest')?.checked ?? false);
    // 금종세 대상은 위탁 배당 등 금융소득으로 엔진이 자동 판정(수동 지정 안 함).
    payload.manual_comprehensive_years = [];
  }

  showProgressUI();

  try {
    const submitRes = await fetch('/api/calculator/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const submitData = await submitRes.json();
    if (submitRes.status === 429) throw new Error(submitData.error);
    const { task_id } = submitData;
    _calcTaskId = task_id;
    localStorage.removeItem('mm_result_calculator');
    localStorage.setItem('mm_task_calculator', JSON.stringify({task_id, payload, timestamp: Date.now()}));

    const result = await pollTask(task_id);

    hideProgressUI();
    if (result) {
      renderResult(result, payload);
      window.MMLimit?.attach('resultContent', result.limit_warnings);
      renderFeeSummary('resultContent', result.total_fees);
      localStorage.setItem('mm_result_calculator', JSON.stringify({result, payload, ts: Date.now()}));
    }
  } catch (err) {
    if (err.message !== 'CANCELLED') {
      hideProgressUI();
      let _errData = err._data;
      if (!_errData) { try { _errData = JSON.parse(err.message); } catch(_) {} }
      let _handled = false;
      if (_errData && _errData.error) {
        const _errType = _errData.error;
        if (_errType === 'limit_confirm') {
          _handled = true;
          document.getElementById('resultEmpty').style.display = 'block';
          if (await window.MMLimit.confirm(_errData.violations || [])) {
            return runCalculator(true);
          }
        } else if (_errType === 'account_restrictions' || _errType === 'isa_windmill_disabled') {
          const banner = document.getElementById('accountRestrictBanner');
          const detail = document.getElementById('accountRestrictDetail');
          if (banner && detail) {
            detail.innerHTML = (_errData.violations || []).map(v => `<div>• ${v}</div>`).join('');
            if (_errData.disclaimer) detail.innerHTML += `<div style="margin-top:6px;font-style:italic;">${_errData.disclaimer}</div>`;
            banner.style.display = 'block';
            document.getElementById('resultEmpty').style.display = 'none';
            _handled = true;
          }
        }
      }
      if (!_handled) alert('오류: ' + err.message);
    }
  } finally {
    localStorage.removeItem('mm_task_calculator');
    _calcTaskId = null;
    btn.disabled = false;
    document.getElementById('runBtnText').style.display    = 'inline';
    document.getElementById('runBtnSpinner').style.display = 'none';
    hideProgressUI();
  }
}


async function pollTask(taskId, maxWait = 600000) {
  const start = Date.now();
  let _initialRank = null;

  while (Date.now() - start < maxWait) {
    if (_calcCancelled) { _calcCancelled = false; throw new Error('CANCELLED'); }
    await new Promise(r => setTimeout(r, 1500));
    if (_calcCancelled) { _calcCancelled = false; throw new Error('CANCELLED'); }

    const res  = await fetch(`/api/task/${taskId}`);
    const data = await res.json();

    if (data.status === 'PENDING') {
      const rank = data.queue_rank;
      if (rank !== null && rank !== undefined) {
        if (_initialRank === null) _initialRank = Math.max(rank, 1);
        const rawPct = Math.round((_initialRank - rank) / _initialRank * 100);
        const pct = Math.min(99, Math.max(8, rawPct));
        updateProgressUI({ phase: '대기 중', queueRank: rank, isWaiting: true, avgDuration: data.avg_duration, percent: pct });
      } else {
        updateProgressUI({ phase: '준비 중', percent: 0, isWaiting: false });
      }

    } else if (data.status === 'PROGRESS') {
      updateProgressUI({
        phase:   data.phase === 'preparing' ? '데이터 준비 중' : '계산 중',
        percent: data.percent,
        current: data.current,
        total:   data.total,
        elapsed: data.elapsed,
        eta:     data.eta,
        isWaiting: false,
      });

    } else if (data.status === 'CANCELLED') {
      throw new Error('CANCELLED');

    } else if (data.status === 'SUCCESS') {
      return data.result;

    } else if (data.status === 'FAILURE') {
      const _e = new Error(data.error || '시뮬레이션 실패');
      _e._data = data.error_data || null;  // 서버에서 파싱한 구조화 에러
      throw _e;
    }
  }
  throw new Error('시간 초과 (10분)');
}


// ── 진행 상황 UI ────────────────────────────────────────────
function showProgressUI() {
  document.getElementById('runBtnText').style.display    = 'none';
  document.getElementById('runBtnSpinner').style.display = 'inline';

  const empty = document.getElementById('resultEmpty');
  empty.style.display = 'flex';
  empty.innerHTML = `
    <style>
      @keyframes mm-indeterminate {
        0%   { left: -40%; width: 40%; }
        100% { left: 110%; width: 30%; }
      }
    </style>
    <div style="width:100%;padding:24px;">
      <div id="progressPhase" style="font-size:0.9rem;color:var(--text-muted);margin-bottom:8px;">
        준비 중...
      </div>
      <div style="background:var(--border);border-radius:8px;height:8px;overflow:hidden;margin-bottom:8px;position:relative;">
        <div id="progressBar"
             style="background:var(--blue);height:100%;width:40%;border-radius:8px;position:absolute;top:0;left:0;animation:mm-indeterminate 1.4s ease-in-out infinite;">
        </div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:0.78rem;color:var(--text-muted);">
        <span id="progressDetail">가격 데이터 로딩 중...</span>
        <span id="progressEta"></span>
      </div>
      <div style="text-align:center;margin-top:10px;">
        <button onclick="cancelCalcTask()" style="padding:4px 16px;border:1.5px solid #e53935;border-radius:8px;background:var(--card);color:#e53935;font-size:12px;font-weight:700;cursor:pointer;">✕ 취소</button>
      </div>
    </div>`;
  document.getElementById('resultContent').style.display = 'none';
}

function _setIndeterminate(barEl) {
  if (barEl.dataset.anim === '1') return;
  barEl.style.transition = 'none';
  barEl.style.animation  = 'mm-indeterminate 1.4s ease-in-out infinite';
  barEl.style.width      = '40%';
  barEl.dataset.anim     = '1';
}
function _clearIndeterminate(barEl) {
  barEl.dataset.anim     = '';
  barEl.style.animation  = '';
}

function updateProgressUI({ phase, queueRank, isWaiting, avgDuration, percent, current, total, elapsed, eta }) {
  const phaseEl  = document.getElementById('progressPhase');
  const barEl    = document.getElementById('progressBar');
  const detailEl = document.getElementById('progressDetail');
  const etaEl    = document.getElementById('progressEta');
  if (!phaseEl) return;

  if (isWaiting) {
    barEl.dataset.anim    = '';
    barEl.style.animation = '';
    barEl.style.transition = 'width 0.5s';
    barEl.style.left      = '0%';
    barEl.style.width     = `${percent}%`;
    const _concurrency = 2;  // Celery worker 수
    const _waiting = queueRank >= _concurrency;
    phaseEl.textContent   = _waiting
      ? `⏳ 내 앞에 ${queueRank - _concurrency + 1}개 대기 중 (${percent}%)`
      : `⏳ 곧 시작됩니다...`;
    detailEl.textContent  = _waiting ? '앞 계산 완료 후 자동으로 시작됩니다' : '워커 할당 완료, 바로 시작됩니다';
    const waitSecs = Math.max(0, queueRank - _concurrency + 1) * (avgDuration || 30);
    const wm = Math.floor(waitSecs / 60), ws = waitSecs % 60;
    etaEl.textContent = _waiting
      ? (wm > 0 ? `약 ${wm}분 ${ws}초 후 시작 예상` : `약 ${ws}초 후 시작 예상`)
      : '';
  } else if (percent > 0) {
    _clearIndeterminate(barEl);
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
    _setIndeterminate(barEl);
    detailEl.textContent = '가격 데이터 로딩 중...';
    etaEl.textContent    = '';
  }
}

function hideProgressUI() {
  const empty = document.getElementById('resultEmpty');
  if (empty) empty.style.display = 'none';
}

// ── ISA 중도해지 토글 ──
let _lastCalcResult = null;

function toggleIsaEarlyCancel(checked) {
  if (!_lastCalcResult) return;
  const data = _lastCalcResult;
  const earlyDist = data.distribution_early_cancel;
  if (!earlyDist) return;

  const ev = checked ? earlyDist : data.distribution.end_value;
  document.getElementById('distP10').textContent = fmtKRW(ev.p10);
  document.getElementById('distP50').textContent = fmtKRW(ev.p50);
  document.getElementById('distP90').textContent = fmtKRW(ev.p90);

  // 히스토그램 end_value 재렌더
  const vals = checked
    ? earlyDist.values
    : data.distribution.end_value.values;
  renderHistogram('histEndValue', vals, fmtKRW, '#1976D2');

  // 롤링 차트: end_value 컬럼 교체
  const cases = data.cases.map(c => ({
    ...c,
    end_value: checked && c.end_value_early_cancel != null
      ? c.end_value_early_cancel
      : c.end_value,
  }));
  renderRollingChart(cases);
}


// 종합과세 분할매도 슬라이더 (Phase 2f)
function calcUpdateSplitPlan(years) {
  years = parseInt(years);
  const label = document.getElementById('calcSplitYearsLabel');
  if (label) label.textContent = years + '년';
  const plan = window._calcSplitSaleData;
  if (!plan) return;
  const byYear = plan.plan_by_year || {};
  const afterTaxByYear = plan.after_tax_by_year || {};
  const splitTax = byYear[String(years)] ?? plan.lump_sum_tax;
  const splitAfterTax = afterTaxByYear[String(years)] ?? (plan.gain - splitTax);
  const lumpAfterTax = plan.lump_sum_after_tax ?? (plan.gain - plan.lump_sum_tax);
  const saving = plan.lump_sum_tax - splitTax;
  const el = document.getElementById('calcSplitMetrics');
  if (!el) return;
  el.innerHTML = [
    { label: '일괄 청산 세금',     value: fmtKRW(plan.lump_sum_tax), cls: 'down' },
    { label: years + '년 분할 세금', value: fmtKRW(splitTax),          cls: '' },
    { label: '일괄 세후 이익',     value: fmtKRW(lumpAfterTax),      cls: '' },
    { label: years + '년 세후 이익', value: fmtKRW(splitAfterTax),     cls: 'up' },
    { label: '절감액',             value: fmtKRW(saving),            cls: saving > 0 ? 'up' : '' },
    { label: '최적 연수',          value: plan.optimal_years + '년 (세후 ' + fmtKRW(plan.optimal_after_tax ?? (plan.gain - plan.optimal_tax)) + ')', cls: '' },
  ].map(item => `<div style="background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px 10px;">
      <div style="font-size:0.68rem;color:var(--text-muted);">${item.label}</div>
      <div style="font-size:0.82rem;font-weight:800;" class="${item.cls}">${item.value}</div>
    </div>`).join('');
}

// ── 결과 렌더링 ──
function renderPriceProvenance(provenance) {
  const el = document.getElementById('priceProvenanceNote');
  if (!el) return;
  el.replaceChildren();

  if (!provenance || !Number.isFinite(Number(provenance.total_cases))) {
    el.style.display = 'none';
    return;
  }

  const total = Number(provenance.total_cases || 0);
  const actual = Number(provenance.actual_cases || 0);
  const backfilled = Number(provenance.backfilled_cases || 0);
  const details = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = `가격 데이터: 실측 ${actual.toLocaleString()}개 / 프록시·백필 ${backfilled.toLocaleString()}개`;
  if (total > 0) {
    summary.textContent += ` (총 ${total.toLocaleString()}개 롤링 케이스)`;
  }
  details.appendChild(summary);

  const tickers = Array.isArray(provenance.tickers) ? provenance.tickers : [];
  if (tickers.length) {
    const list = document.createElement('ul');
    tickers.forEach(ticker => {
      const item = document.createElement('li');
      const sources = Array.isArray(ticker.sources) ? ticker.sources : [];
      const source = sources.find(src => src.source_type !== 'actual' && src.source_code);
      const proxy = ticker.proxy || source?.source_code || '프록시';

      if (ticker.is_backfilled) {
        let sourceText = proxy;
        if (source?.date_from && source?.date_to) {
          const rows = Number(source.rows || 0).toLocaleString();
          sourceText = `${source.source_code || proxy} ${source.date_from}~${source.date_to}, ${rows}행`;
        }
        item.textContent = `${ticker.code}: 실측 ${ticker.real_start || '?'}~, 백필 ${sourceText}`;
      } else if (ticker.real_start) {
        item.textContent = `${ticker.code}: 실측 ${ticker.real_start}~`;
      } else {
        item.textContent = `${ticker.code}: 가격 출처 정보 없음`;
      }
      list.appendChild(item);
    });
    details.appendChild(list);
  }

  el.appendChild(details);
  el.style.display = 'block';
}

function renderResult(data, payload) {
  document.getElementById('resultEmpty').style.display   = 'none';
  document.getElementById('resultContent').style.display = 'block';
  _lastCalcResult = data;

  // 에러/경고 배너 초기화
  ['accountRestrictBanner', 'isaLimitErrorBanner', 'isaCapBanner'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });

  // ISA 캡 디버그 (브라우저 콘솔에서 확인 가능)
  if (data.isa_cap_info) console.log('[ISA cap]', data.isa_cap_info);

  // ISA 총 납입 캡 경고
  const capInfo = data.isa_cap_info;
  if (capInfo && capInfo.capped) {
    const capBanner = document.getElementById('isaCapBanner');
    const capDetail = document.getElementById('isaCapDetail');
    if (capBanner && capDetail) {
      if (Array.isArray(capInfo.accounts)) {
        capDetail.innerHTML = capInfo.accounts.map(info => {
          const orig  = Math.round(info.original_total  / 10000).toLocaleString();
          const origM = Math.round(info.original_monthly / 10000).toLocaleString();
          const stopY = info.stop_years ?? 0;
          const stopMr = info.stop_months_remainder ?? 0;
          const stopStr = stopMr > 0 ? `${stopY}년 ${stopMr}개월` : `${stopY}년`;
          return `${info.account_label || 'ISA 계좌'}: 계획 총 납입 <strong>${orig}만원</strong> → <strong>1억원</strong>, 월 <strong>${origM}만원</strong> × <strong>${stopStr}</strong> 후 중단`;
        }).join('<br>');
      } else {
        const orig  = Math.round(capInfo.original_total  / 10000).toLocaleString();
        const origM = Math.round(capInfo.original_monthly / 10000).toLocaleString();
        const stopY = capInfo.stop_years ?? 0;
        const stopMr = capInfo.stop_months_remainder ?? 0;
        const stopStr = stopMr > 0 ? `${stopY}년 ${stopMr}개월` : `${stopY}년`;
        capDetail.innerHTML =
          `ISA 총 납입 한도(1억원)에 도달하여 납입이 자동 중단됩니다.<br>` +
          `계획 총 납입 <strong>${orig}만원</strong> → 실제 적용 <strong>1억원</strong><br>` +
          `월 <strong>${origM}만원</strong> × <strong>${stopStr}</strong> 납입 후 중단, 이후 자산만 복리 운용`;
      }
      capBanner.style.display = 'block';
    }
  }

  // ISA 중도해지 체크박스 초기화
  const isaCheck = document.getElementById('isaEarlyCancelCheck');
  if (isaCheck) isaCheck.checked = false;

  const dist = data.distribution;

  document.getElementById('resultPeriodLabel').textContent =
    `${payload.years}년 | ${data.cases_count}개 롤링 케이스`;
  renderPriceProvenance(data.price_provenance);

  // 가상 데이터 경고 배너
  const synthBanner = document.getElementById('synthWarningBanner');
  const synthDetail = document.getElementById('synthWarningDetail');
  if (synthBanner && synthDetail) {
    const si = data.synthetic_info || {};
    const keys = Object.keys(si);
    if (data.used_synthetic && keys.length > 0) {
      synthDetail.innerHTML = keys.map(code => {
        const info = si[code];
        return `${code}: ${info.date_from || '?'} ~ ${info.date_to || '?'} (${info.rows_added || 0}행 추정)`;
      }).join('<br>');
      synthBanner.style.display = 'block';
    } else {
      synthBanner.style.display = 'none';
    }
  }

  // ISA 중도해지 경고 배너
  const isaPartialBanner = document.getElementById('isaPartialCycleBanner');
  if (isaPartialBanner) {
    if (data.isa_partial_cycle) {
      document.getElementById('isaPartialYearsText').textContent = data.isa_remainder_years || '?';
      isaPartialBanner.style.display = 'block';
    } else {
      isaPartialBanner.style.display = 'none';
    }
  }

  // 금융소득 종합과세 분할매도 패널 (Phase 2f)
  window._calcSplitSaleData = data.split_sale_plan || null;
  const calcSplitPanel = document.getElementById('calcSplitSalePanel');
  if (calcSplitPanel) {
    if (data.split_sale_plan && data.split_sale_plan.gain > 20000000) {
      document.getElementById('calcKrForeignGain').textContent = fmtKRW(data.split_sale_plan.gain);
      calcSplitPanel.style.display = 'block';
      calcUpdateSplitPlan(document.getElementById('calcSplitYearsSlider')?.value || 5);
    } else {
      calcSplitPanel.style.display = 'none';
    }
  }

  // 상단 카드
  document.getElementById('distP10').textContent = fmtKRW(dist.end_value.p10);
  document.getElementById('distP50').textContent = fmtKRW(dist.end_value.p50);
  document.getElementById('distP90').textContent = fmtKRW(dist.end_value.p90);
  renderMultiAccountSummary(data.multi_account, data.g2, data.savings, data.windmill_auto_brokerage);

  // 롤링 케이스 차트
  renderRollingChart(data.cases);

  // 미래 시나리오 부채꼴 (경험적)
  renderFan(data.fan);

  // 히스토그램들
  const histConfigs = [
    { id: 'histEndValue', key: 'end_value', fmt: fmtKRW,            color: '#1976D2', div: false },
    { id: 'histCagr',     key: 'cagr',      fmt: fmtPct,            color: '#43A047', div: false },
    { id: 'histMdd',      key: 'mdd',       fmt: fmtPct,            color: '#EF5350', div: false },
    { id: 'histSharpe',   key: 'sharpe',    fmt: v => v.toFixed(2), color: '#1976D2', div: false },
    { id: 'histSortino',  key: 'sortino',   fmt: v => v.toFixed(2), color: '#7B1FA2', div: false },
    { id: 'histCalmar',   key: 'calmar',    fmt: v => v.toFixed(2), color: '#F57C00', div: false },
    { id: 'histDiv',             key: 'total_dividend',         fmt: fmtKRW, color: '#00897B', div: true  },
    { id: 'histDivCagr',         key: 'dividend_cagr',          fmt: fmtPct, color: '#00897B', div: true  },
    { id: 'histLastYearDiv',     key: 'last_year_dividend',     fmt: fmtKRW, color: '#00897B', div: true  },
    { id: 'histDivYieldOnCost',  key: 'dividend_yield_on_cost', fmt: fmtPct, color: '#00897B', div: true  },
  ];

  const noDividend = dist.no_dividend === true;
  let divNote = '';
  if (dist.div_data_start) {
    if (dist.div_is_backfilled && dist.div_real_start) {
      const realYr = String(dist.div_real_start).slice(0, 4);
      const bfYr   = String(dist.div_data_start).slice(0, 4);
      divNote = `※ 배당: 실측 ${realYr}년~, 그 이전(${bfYr}년~)은 프록시 지수 기반 추정(백필) · ${dist.div_cases_count}개 케이스`;
    } else {
      divNote = `※ ${dist.div_data_start} 이후 ${dist.div_cases_count}개 케이스 기준`;
    }
  }

  histConfigs.forEach(cfg => {
    const el = document.getElementById(cfg.id);
    if (!el) return;                              // 요소 없으면 스킵(null.closest 방지)
    const card = el.closest('.result-card');
    const isDivDisabled = cfg.div && noDividend;
    if (isDivDisabled) {
      // 배당 없는 포트폴리오 → 해당 없음 표시
      const wrap = card && card.querySelector('.chart-wrap-sm');
      if (wrap) {
        wrap.innerHTML =
          '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:0.82rem;">배당 데이터 없음</div>';
      }
      const statsEl = document.getElementById(`stats${cfg.id.replace('hist','')}`);
      if (statsEl) statsEl.innerHTML = '';
      return;
    }

    if (dist[cfg.key]) {
      renderHistogram(cfg.id, dist[cfg.key].values, cfg.color, cfg.fmt);
      renderHistStats(`stats${cfg.id.replace('hist', '')}`, dist[cfg.key], cfg.fmt);
    }

    // 배당 히스토그램에 케이스 수 주석 표시
    if (cfg.div && divNote && card) {
      let note = card.querySelector('.div-note');
      if (!note) {
        note = document.createElement('div');
        note.className = 'div-note';
        note.style.cssText = 'font-size:0.7rem;color:var(--text-muted);margin-top:4px;text-align:right;';
        card.appendChild(note);
      }
      note.textContent = divNote;
    }

    // 배당 CAGR 최소 기간 안내
    if (cfg.id === 'histDivCagr' && !noDividend && card) {
      let warn = card.querySelector('.div-cagr-warn');
      if (!warn) {
        warn = document.createElement('div');
        warn.className = 'div-cagr-warn';
        warn.style.cssText = 'font-size:0.7rem;color:#F9A825;margin-top:4px;';
        card.appendChild(warn);
      }
      const years = Number(document.getElementById('yearsSlider').value);
      warn.textContent = years < 3 ? '⚠ 배당 CAGR은 최소 3년 이상 시뮬레이션 시 의미 있는 값이 나옵니다' : '';
    }
  });

  // 공유 데이터 저장
  try {
    const tickers = payload.accounts?.length > 1
      ? payload.accounts.map((a, i) => `계좌${i+1}:${(a.tickers || []).map(t => `${t.code} ${Math.round(t.weight*100)}%`).join('+')}`).join(' / ')
      : (payload.tickers || []).map(t => `${t.code} ${Math.round(t.weight*100)}%`).join('+');
    window._calcShareData = {
      t: 'calc',
      label: tickers,
      years: payload.years || 0,
      m: {
        p10:  +((dist.end_value?.p10  || 0) / 1e8).toFixed(2),
        p50:  +((dist.end_value?.p50  || 0) / 1e8).toFixed(2),
        p90:  +((dist.end_value?.p90  || 0) / 1e8).toFixed(2),
        cagr: +((dist.cagr?.p50       || 0) * 100).toFixed(2),
      },
    };
  } catch(e) {}
  const shareBtns = document.getElementById('calcShareBtns');
  if (shareBtns) shareBtns.style.display = 'flex';
}

// ── 히스토그램 렌더링 ──
function renderHistogram(canvasId, values, color, fmtFn) {
  if (chartInstances[canvasId]) {
    chartInstances[canvasId].destroy();
  }

  const ctx  = document.getElementById(canvasId).getContext('2d');
  const bins = 15;
  const min  = Math.min(...values);
  const max  = Math.max(...values);
  const step = (max - min) / bins || 1;

  const counts = Array(bins).fill(0);
  values.forEach(v => {
    const idx = Math.min(Math.floor((v - min) / step), bins - 1);
    counts[idx]++;
  });

  const labels = counts.map((_, i) => fmtFn(min + step * (i + 0.5)));

  chartInstances[canvasId] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: counts,
        backgroundColor: color + '55',
        borderColor:     color,
        borderWidth: 1,
        borderRadius: 3,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: items => fmtFn(min + step * items[0].dataIndex),
            label: item  => `${item.raw}개 케이스`,
          }
        }
      },
      scales: {
        x: {
          ticks: { maxTicksLimit: 5, font: { size: 9 }, color: '#90A4AE' },
          grid: { display: false }
        },
        y: {
          ticks: { font: { size: 9 }, color: '#90A4AE', stepSize: 1 },
          grid: { color: MM_CHART_GRID }
        }
      }
    }
  });
}

// ── 히스토그램 통계 ──
function renderHistStats(elId, distData, fmtFn) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.innerHTML = `
    <div class="hist-stat"><div class="hist-stat-label">하위10%</div><div class="hist-stat-value">${fmtFn(distData.p10)}</div></div>
    <div class="hist-stat"><div class="hist-stat-label">중앙값</div><div class="hist-stat-value">${fmtFn(distData.p50)}</div></div>
    <div class="hist-stat"><div class="hist-stat-label">평균</div><div class="hist-stat-value">${fmtFn(distData.mean)}</div></div>
    <div class="hist-stat"><div class="hist-stat-label">상위10%</div><div class="hist-stat-value">${fmtFn(distData.p90)}</div></div>
  `;
}

// ── 롤링 케이스 차트 ──
// 롤링 차트 보기 모드: 'asset'(최종자산·수익률순) | 'cagr'(수익률·수익률순) | 'year'(시작 시점별)
let _rollingCases = [];
let _rollingMode  = 'asset';

const _ROLLING_TITLES = {
  asset: '최종 자산 (수익률 낮은순 →)',
  cagr:  '연복리 수익률 CAGR (낮은순 →)',
  year:  '시작 시점별 종료 자산',
};

function renderRollingChart(cases) {
  _rollingCases = cases || [];
  _renderRolling();
}

function setRollingView(mode) {
  _rollingMode = mode;
  document.querySelectorAll('.rchart-seg-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.mode === mode));
  const title = document.getElementById('rollingTitle');
  if (title) title.textContent = _ROLLING_TITLES[mode] || '';
  _renderRolling();
}

function _renderRolling() {
  if (chartInstances['rollingChart']) chartInstances['rollingChart'].destroy();
  const mode = _rollingMode;

  // 'year'는 시작 시점 순서 유지, 그 외는 수익률(CAGR) 오름차순 정렬
  const cases = (mode === 'year')
    ? _rollingCases.slice()
    : _rollingCases.slice().sort((a, b) => a.cagr - b.cagr);

  const sorted = mode !== 'year';
  // 정렬 보기(asset/cagr): x축은 수익률 분포 순서일 뿐 → 연도 라벨 숨김. 연도별만 시작월 표시
  const labels = sorted ? cases.map(() => '') : cases.map(c => c.start.slice(0, 7));
  const isCagr = mode === 'cagr';
  const values = cases.map(c => isCagr ? c.cagr * 100 : c.end_value);
  const valFmt = isCagr ? (v => (v >= 0 ? '+' : '') + v.toFixed(2) + '%') : fmtKRW;
  // CAGR 보기: 음수면 빨강 / 그 외(최종자산)는 항상 초록
  const pos = isCagr ? values.map(v => v >= 0) : values.map(() => true);

  const ctx = document.getElementById('rollingChart').getContext('2d');
  chartInstances['rollingChart'] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: pos.map(p => p ? 'rgba(67,160,71,0.6)' : 'rgba(239,83,80,0.6)'),
        borderColor:     pos.map(p => p ? '#43A047' : '#EF5350'),
        borderWidth: 1, borderRadius: 3,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          title: items => '시작 ' + (cases[items[0].dataIndex]?.start.slice(0, 7) || ''),
          label: c => {
            const k = cases[c.dataIndex];
            return isCagr
              ? 'CAGR ' + valFmt(c.raw) + ' · ' + fmtKRW(k.end_value)
              : fmtKRW(c.raw) + ' · CAGR ' + (k.cagr >= 0 ? '+' : '') + (k.cagr * 100).toFixed(2) + '%';
          }
        } }
      },
      scales: {
        x: {
          ticks: { display: !sorted, maxTicksLimit: 10, font: { size: 10 }, color: '#90A4AE' },
          grid: { display: false },
          title: sorted ? { display: true, text: '수익률 낮음  ←———→  높음', color: '#90A4AE', font: { size: 11 } } : { display: false },
        },
        y: { ticks: { font: { family: 'DM Mono', size: 10 }, color: '#90A4AE', callback: valFmt }, grid: { color: MM_CHART_GRID } }
      }
    }
  });
}

// ═══════════════════════════════════════════════════════════
// 미래 시나리오 부채꼴 (경험적) — 과거 롤링 윈도우 시점별 퍼센타일 밴드
// ═══════════════════════════════════════════════════════════
let _fanData = null;

function renderFan(fan) {
  const card = document.getElementById('fanCard');
  _fanData = (fan && fan.bands && fan.bands.length === 99) ? fan : null;
  if (!_fanData) { if (card) card.style.display = 'none'; return; }
  card.style.display = '';
  const nEl = document.getElementById('fanN');
  if (nEl) nEl.textContent = `시나리오 ${_fanData.n}개`;
  _drawFan();
}

// 슬라이더 두 개로 밴드 하단/상단 퍼센타일 조정 (하단 < 상단 강제)
function onFanSlider(which) {
  const lo = document.getElementById('fanLo');
  const hi = document.getElementById('fanHi');
  let loV = parseInt(lo.value), hiV = parseInt(hi.value);
  if (loV >= hiV) {
    if (which === 'lo') { hiV = Math.min(99, loV + 1); hi.value = hiV; }
    else               { loV = Math.max(1, hiV - 1);  lo.value = loV; }
  }
  document.getElementById('fanLoVal').textContent = loV;
  document.getElementById('fanHiVal').textContent = hiV;
  // 슬라이더는 차트 재생성 대신 밴드 데이터만 갱신 → 중앙선 고정, 밴드 경계만 부드럽게 이동
  _updateFanBands(loV, hiV);
}

// 슬라이더 조정 시: 기존 차트의 하단·상단 데이터셋만 교체 + update() → x축서 솟는 애니 제거
function _updateFanBands(loV, hiV) {
  const ch = chartInstances['fanChart'];
  if (!ch) { _drawFan(); return; }
  ch.data.datasets[0].data  = _fanData.bands[loV - 1];
  ch.data.datasets[0].label = `하단 p${loV}`;
  ch.data.datasets[1].data  = _fanData.bands[hiV - 1];
  ch.data.datasets[1].label = `상단 p${hiV}`;
  ch.update();   // 변경된 두 라인만 현재 위치→새 위치로 morph (중앙선 불변)
}

function resetFanZoom() {
  const ch = chartInstances['fanChart'];
  if (ch && ch.resetZoom) ch.resetZoom();
}

function _drawFan() {
  if (!_fanData) return;
  if (chartInstances['fanChart']) chartInstances['fanChart'].destroy();

  const loV = parseInt(document.getElementById('fanLo').value);
  const hiV = parseInt(document.getElementById('fanHi').value);
  // percentiles = [1..99] → 인덱스 = p-1
  const rowLo  = _fanData.bands[loV - 1];
  const rowHi  = _fanData.bands[hiV - 1];
  const rowMid = _fanData.bands[49];   // p50
  const labels = _fanData.axis.map(k => k === 0 ? '시작' : `${k}년차`);

  // y축을 전체 분포(p1~p99) 범위로 고정 → 슬라이더로 밴드 바꿔도 프레임 불변(변화 잘 보임)
  const yMin = Math.min(..._fanData.bands[0]);    // p1 (최저)
  const yMax = Math.max(..._fanData.bands[98]);   // p99 (최고)
  const yPad = (yMax - yMin) * 0.05 || 1;

  const ctx = document.getElementById('fanChart').getContext('2d');
  chartInstances['fanChart'] = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: `하단 p${loV}`, data: rowLo, borderColor: 'rgba(25,118,210,0.45)',
          borderWidth: 1, pointRadius: 0, fill: false, tension: 0.2 },
        { label: `상단 p${hiV}`, data: rowHi, borderColor: 'rgba(25,118,210,0.45)',
          borderWidth: 1, pointRadius: 0, fill: '-1',
          backgroundColor: 'rgba(25,118,210,0.18)', tension: 0.2 },
        { label: '중앙값 p50', data: rowMid, borderColor: '#1976D2',
          borderWidth: 2, pointRadius: 0, fill: false, tension: 0.2 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          title: items => items[0].label,
          label: c => `${c.dataset.label}: ${fmtKRW(c.raw)}`,
        } },
        // 줌: Ctrl+휠 확대·축소(일반 스크롤 보존), 핀치(모바일), 드래그 이동
        zoom: {
          zoom: {
            wheel: { enabled: true, modifierKey: 'ctrl' },
            pinch: { enabled: true },
            mode: 'xy',
          },
          pan: { enabled: true, mode: 'xy' },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 12, font: { size: 10 }, color: '#90A4AE' }, grid: { display: false } },
        y: { min: yMin - yPad, max: yMax + yPad,
             ticks: { font: { family: 'DM Mono', size: 10 }, color: '#90A4AE', callback: fmtKRW }, grid: { color: MM_CHART_GRID } }
      }
    }
  });
}

// ── 포맷 헬퍼 ──
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
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%';
}
// ═══════════════════════════════════════════════════════════
// 세금 토글 + 계좌 설정
// ═══════════════════════════════════════════════════════════

window.taxEnabled  = false;
window.taxAccounts = [];
window.taxProfile  = {};

function toggleTax() {
  window.taxEnabled = !window.taxEnabled;
  const wrap  = document.getElementById('taxToggleWrap');
  const thumb = document.getElementById('taxToggleThumb');
  const label = document.getElementById('taxToggleLabel');
  const panel = document.getElementById('taxPanel');
  wrap.style.background = window.taxEnabled ? 'var(--blue)' : 'var(--border)';
  thumb.style.left      = window.taxEnabled ? '23px' : '3px';
  label.textContent     = window.taxEnabled ? 'ON'  : 'OFF';
  label.style.color     = window.taxEnabled ? 'var(--blue)' : 'var(--text-muted)';
  panel.style.display   = window.taxEnabled ? 'block' : 'none';
  if (window.taxEnabled) {
    loadTaxProfileForCalculator();
    if (window.taxAccounts.length === 0) addTaxAccount();
  }
}

async function loadTaxProfileForCalculator() {
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

  window.taxProfile = settings || {};
  const info = document.getElementById('taxProfileInfo');
  if (!info) return;
  const hasProfile = window.taxProfile.earned_income != null || window.taxProfile.age != null;
  if (!hasProfile) {
    info.innerHTML = '저장된 세금 설정이 없습니다. <a href="/tax-settings" style="color:var(--blue);">세금 설정</a>에서 입력하세요.';
    return;
  }
  info.innerHTML = `연소득 ${fmtTaxKRW(window.taxProfile.earned_income || 0)} · 나이 ${window.taxProfile.age || 40}세 <a href="/tax-settings" style="color:var(--blue);margin-left:6px;">수정</a>`;
}

// ── 공유 (C5) ──
async function calcMakeCanvas() {
  const el = document.getElementById('resultContent');
  const body = window._calcShareData || {};
  const label = body.label || '—';
  const years = body.years ? body.years + '년' : '—';
  const m = body.m || {};
  const p50 = m.p50 !== undefined ? Number(m.p50).toLocaleString() + '억' : '—';
  const cagr = m.cagr !== undefined ? Number(m.cagr).toFixed(1) + '%' : '—';
  return html2canvas(el, {
    scale: 2, backgroundColor: (typeof MM_DARK !== 'undefined' && MM_DARK) ? '#0E141C' : '#F0F4F8', useCORS: true, allowTaint: true,
    onclone: function(doc, clonedEl) {
      const hdr = doc.createElement('div');
      hdr.style.cssText = 'background:#1A2332;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;width:100%;box-sizing:border-box;margin-bottom:4px;';
      hdr.innerHTML = '<span style="color:var(--blue-mid);font-size:0.95rem;font-weight:800;">💰 Money Milestone</span>'
                    + '<span style="color:var(--text-muted);font-size:0.78rem;">moneymilestone.duckdns.org · 무료 투자 분석 도구</span>';
      clonedEl.insertBefore(hdr, clonedEl.firstChild);
      const cond = doc.createElement('div');
      cond.style.cssText = 'background:var(--card);border:1.5px solid var(--border);border-radius:10px;padding:10px 16px;margin-bottom:12px;display:flex;gap:20px;flex-wrap:wrap;font-family:inherit;';
      cond.innerHTML = [
        ['종목', label], ['기간', years], ['중간값', p50], ['CAGR', cagr],
      ].map(([l,v]) => '<div><span style="font-size:0.68rem;color:var(--text-muted);display:block;">' + l + '</span><span style="font-size:0.82rem;font-weight:700;color:var(--text);">' + v + '</span></div>').join('');
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
async function calcCopyLink() {
  const btn = event.target; const orig = btn.textContent;
  if (!window._calcShareData) { btn.textContent = '⚠️ 먼저 계산하세요'; setTimeout(() => btn.textContent = orig, 2000); return; }
  btn.textContent = '⏳ 생성 중...'; btn.disabled = true;
  try {
    const canvas = await calcMakeCanvas();
    const b64 = canvas.toDataURL('image/png');
    const res = await fetch('/api/share/upload', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({image: b64}),
    });
    const { id } = await res.json();
    const url = location.origin + '/share/img/' + id;
    const box = document.getElementById('calcShareUrlBox');
    if (box) { box.style.display = 'block'; box.innerHTML = '🔗 공유 링크: <a href="' + url + '" target="_blank">' + url + '</a>'; }
    await mmCopyText(url);
    btn.textContent = '✅ 복사됨!';
    setTimeout(() => btn.textContent = orig, 2000);
  } catch(e) {
    btn.textContent = '⚠️ 오류'; setTimeout(() => btn.textContent = orig, 2000);
  } finally { btn.disabled = false; }
}
function calcDownloadImg() {
  if (typeof html2canvas === 'undefined') { alert('html2canvas 로드 중입니다.'); return; }
  calcMakeCanvas().then(function(canvas) {
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = 'simulation-result.png';
    a.click();
  });
}
