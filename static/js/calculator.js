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
          dropdown.innerHTML = '<div style="padding:12px;font-size:0.82rem;color:#90A4AE">검색 결과 없음</div>';
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
    if (!searchInput.closest('.ticker-search-box').contains(e.target)) {
      dropdown.style.display = 'none';
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
    });
  }
  return accounts;
}

// 계좌 우선순위 순서로 분배 정책(자금이동 목적지 cascade) 생성.
function buildDistributionPolicy(accountsPayload) {
  if (!accountsPayload || accountsPayload.length <= 1) return null;
  const dests = accountsPayload
    .map((a, idx) => ({ account_id: idx, p: Number(a.priority ?? (idx + 1)) }))
    .sort((x, y) => x.p - y.p)
    .map(d => ({ account_id: d.account_id }));
  return { destinations: dests };
}

// ── 시뮬레이션 실행 ──
async function runCalculator() {
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
        if (_errType === 'account_restrictions' || _errType === 'isa_windmill_disabled') {
          const banner = document.getElementById('accountRestrictBanner');
          const detail = document.getElementById('accountRestrictDetail');
          if (banner && detail) {
            detail.innerHTML = (_errData.violations || []).map(v => `<div>• ${v}</div>`).join('');
            if (_errData.disclaimer) detail.innerHTML += `<div style="margin-top:6px;font-style:italic;">${_errData.disclaimer}</div>`;
            banner.style.display = 'block';
            document.getElementById('resultEmpty').style.display = 'none';
            _handled = true;
          }
        } else if (_errType === 'isa_contribution_limit' || _errType === 'isa_windmill_disabled' || _errType === 'initial_capital_limit' || _errType === 'pension_contribution_limit') {
          const banner = document.getElementById('isaLimitErrorBanner');
          const detail = document.getElementById('isaLimitErrorDetail');
          if (banner && detail) {
            detail.innerHTML = (_errData.violations || []).map(v => `<div>• ${v}</div>`).join('');
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
        <button onclick="cancelCalcTask()" style="padding:4px 16px;border:1.5px solid #e53935;border-radius:8px;background:white;color:#e53935;font-size:12px;font-weight:700;cursor:pointer;">✕ 취소</button>
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

function renderMultiAccountSummary(multiAccount, g2, savings) {
  const wrap = document.getElementById('multiAccountSummary');
  if (!wrap) return;
  if (!multiAccount || !multiAccount.enabled || !multiAccount.accounts?.length) {
    wrap.style.display = 'none';
    wrap.innerHTML = '';
    return;
  }

  let warnings = (multiAccount.contribution_warnings || []).map(w =>
    `<div style="font-size:0.76rem;color:#C62828;background:#FFEBEE;border-radius:6px;padding:6px 8px;margin-top:6px;">${w}</div>`
  ).join('');
  // 멀티계좌 결과 — 한도 초과분은 분배 우선순위대로 이전됨을 안내.
  if ((multiAccount.contribution_warnings || []).length) {
    warnings += `<div style="font-size:0.74rem;color:#1B5E20;background:#E8F5E9;border-radius:6px;padding:6px 8px;margin-top:6px;">➜ 납입한도 초과분은 분배 우선순위에 따라 다른 계좌로 이전됩니다.</div>`;
  }
  const rows = multiAccount.accounts.map((acc, i) => {
    const d = acc.distribution?.end_value || {};
    return `
      <div style="background:white;border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;gap:8px;">
          <div style="font-size:0.82rem;font-weight:800;color:var(--text);">계좌 ${i + 1}</div>
          <div style="font-size:0.72rem;color:var(--text-muted);">${acc.type || '위탁'}</div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
          <div><div style="font-size:0.68rem;color:var(--text-muted);">하위10%</div><div style="font-size:0.82rem;font-weight:800;">${fmtKRW(d.p10)}</div></div>
          <div><div style="font-size:0.68rem;color:var(--text-muted);">중앙값</div><div style="font-size:0.82rem;font-weight:800;">${fmtKRW(d.p50)}</div></div>
          <div><div style="font-size:0.68rem;color:var(--text-muted);">상위10%</div><div style="font-size:0.82rem;font-weight:800;">${fmtKRW(d.p90)}</div></div>
        </div>
      </div>`;
  }).join('');

  // G2/G3/G4: 자금이동·세액공제 요약 (대표 중앙값 케이스 기준)
  let g2Html = '';
  if (g2 && g2.enabled) {
    const tl = g2.transfer_log || [];
    const maturity = tl.filter(t => t.type === 'maturity').length;
    const reinvest = tl.filter(t => t.type === 'credit_reinvest').length;
    const comp = (g2.comprehensive_years || []);
    const items = [];
    if (maturity) items.push(`ISA 풍차 만기 ${maturity}회 → 우선순위대로 분배`);
    if (comp.length) items.push(`금융소득종합과세 대상연도: ${comp.join(', ')} (해당 연도 풍차 중단)`);
    if (g2.annual_deduction_credit > 0) items.push(`연 납입 세액공제 환급: ${fmtKRW(g2.annual_deduction_credit)}`);
    if (g2.pension_transfer_credit > 0) items.push(`ISA→연금 이전 세액공제: ${fmtKRW(g2.pension_transfer_credit)}`);
    if (reinvest) items.push(`세액공제 환급금 재투자 ${reinvest}회`);
    if (items.length) {
      g2Html = `
        <div style="margin-top:10px;padding:10px 12px;background:#F1F8E9;border:1px solid #C5E1A5;border-radius:8px;">
          <div style="font-size:0.78rem;font-weight:800;color:#33691E;margin-bottom:6px;">자금 이동 · 세액공제 (대표 시나리오)</div>
          ${items.map(t => `<div style="font-size:0.76rem;color:#33691E;margin-top:3px;">• ${t}</div>`).join('')}
        </div>`;
    }
  }

  // 절세액 표시(3종: 위탁가정세금·실제세금·절세액) — 중앙값(p50) 기준, 합산 = 계좌별 합.
  let savingsHtml = '';
  if (savings && savings.combined && savings.combined.brokerage_assumed_tax > 0) {
    const c = savings.combined;
    const accRows = (savings.accounts || [])
      .filter(a => a.brokerage_assumed_tax > 0 || a.tax_saving > 0)
      .map(a => `
        <div style="display:flex;justify-content:space-between;font-size:0.73rem;color:#33691E;margin-top:3px;">
          <span>${a.type || '계좌'}</span>
          <span>위탁가정 ${fmtKRW(a.brokerage_assumed_tax)} · 실제 ${fmtKRW(a.actual_tax)} · 절세 <b>${fmtKRW(a.tax_saving)}</b></span>
        </div>`).join('');
    savingsHtml = `
      <div style="margin-top:10px;padding:12px;background:#E8F5E9;border:1px solid #A5D6A7;border-radius:8px;">
        <div style="font-size:0.8rem;font-weight:800;color:#1B5E20;margin-bottom:8px;">💰 세금 절감 효과 (중앙값 기준)</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
          <div><div style="font-size:0.68rem;color:#558B2F;">전체 위탁 가정 세금</div><div style="font-size:0.9rem;font-weight:800;color:#33691E;">${fmtKRW(c.brokerage_assumed_tax)}</div></div>
          <div><div style="font-size:0.68rem;color:#558B2F;">실제 세금</div><div style="font-size:0.9rem;font-weight:800;color:#33691E;">${fmtKRW(c.actual_tax)}</div></div>
          <div><div style="font-size:0.68rem;color:#558B2F;">절세액</div><div style="font-size:0.98rem;font-weight:900;color:#2E7D32;">약 ${fmtKRW(c.tax_saving)}</div></div>
        </div>
        ${(c.gain_harvest_saving > 0) ? `
        <div style="margin-top:8px;display:flex;justify-content:space-between;align-items:center;padding:7px 10px;background:#FFF3E0;border:1px solid #FFCC80;border-radius:6px;">
          <span style="font-size:0.73rem;color:#E65100;font-weight:700;">📉 절세매도(연 250만 공제) 추가 절감</span>
          <span style="font-size:0.92rem;font-weight:900;color:#E65100;">약 ${fmtKRW(c.gain_harvest_saving)}</span>
        </div>` : ''}
        ${accRows}
        <div style="font-size:0.67rem;color:#7CB342;margin-top:8px;">※ 근사치 — 금융소득종합과세 가산·연금 인출세 미반영(연금 인출세는 은퇴 탭에서). ISA는 세후 재투자 가정.</div>
      </div>`;
  }

  wrap.innerHTML = `
    <div class="result-card" style="margin-bottom:0;">
      <div class="result-card-title">계좌별 종료 자산</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;">${rows}</div>
      ${savingsHtml}
      ${g2Html}
      ${warnings}
    </div>`;
  wrap.style.display = 'block';
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
  ].map(item => `<div style="background:#fff;border:1px solid #eee;border-radius:6px;padding:8px 10px;">
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
  renderMultiAccountSummary(data.multi_account, data.g2, data.savings);

  // 롤링 케이스 차트
  renderRollingChart(data.cases);

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
    const isDivDisabled = cfg.div && noDividend;
    if (isDivDisabled) {
      // 배당 없는 포트폴리오 → 해당 없음 표시
      const card = document.getElementById(cfg.id).closest('.result-card');
      card.querySelector('.chart-wrap-sm').innerHTML =
        '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#90A4AE;font-size:0.82rem;">배당 데이터 없음</div>';
      const statsEl = document.getElementById(`stats${cfg.id.replace('hist','')}`);
      if (statsEl) statsEl.innerHTML = '';
      return;
    }

    renderHistogram(cfg.id, dist[cfg.key].values, cfg.color, cfg.fmt);
    renderHistStats(`stats${cfg.id.replace('hist', '')}`, dist[cfg.key], cfg.fmt);

    // 배당 히스토그램에 케이스 수 주석 표시
    if (cfg.div && divNote) {
      const card = document.getElementById(cfg.id).closest('.result-card');
      let note = card.querySelector('.div-note');
      if (!note) {
        note = document.createElement('div');
        note.className = 'div-note';
        note.style.cssText = 'font-size:0.7rem;color:#90A4AE;margin-top:4px;text-align:right;';
        card.appendChild(note);
      }
      note.textContent = divNote;
    }

    // 배당 CAGR 최소 기간 안내
    if (cfg.id === 'histDivCagr' && !noDividend) {
      const card = document.getElementById(cfg.id).closest('.result-card');
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
          grid: { color: 'rgba(0,0,0,0.04)' }
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
function renderRollingChart(cases) {
  if (chartInstances['rollingChart']) chartInstances['rollingChart'].destroy();

  const ctx    = document.getElementById('rollingChart').getContext('2d');
  const labels = cases.map(c => c.start.slice(0, 7));
  const values = cases.map(c => c.end_value);

  chartInstances['rollingChart'] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: values.map(v => v >= 0 ? 'rgba(67,160,71,0.6)' : 'rgba(239,83,80,0.6)'),
        borderColor:     values.map(v => v >= 0 ? '#43A047' : '#EF5350'),
        borderWidth: 1, borderRadius: 3,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => fmtKRW(c.raw) } }
      },
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { size: 10 }, color: '#90A4AE' }, grid: { display: false } },
        y: { ticks: { font: { family: 'DM Mono', size: 10 }, color: '#90A4AE', callback: v => fmtKRW(v) }, grid: { color: 'rgba(0,0,0,0.04)' } }
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
const ACCOUNT_TYPES = ['위탁', 'ISA', '연금저축', 'IRP'];

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

function addTaxAccount() {
  window.taxAccounts.push({
    type: '위탁',
    initial_capital: 0,
    monthly_contribution: 0,
    tickers: tickers.map(t => ({...t})),
    priority: window.taxAccounts.length + 1,
  });
  renderTaxAccounts();
}

function removeTaxAccount(idx) {
  window.taxAccounts.splice(idx, 1);
  if (window.taxAccounts.length === 0 && window.taxEnabled) {
    window.taxAccounts.push({ type: '위탁', initial_capital: 0, monthly_contribution: 0, tickers: [] });
  }
  renderTaxAccounts();
}

function updateTaxAccountType(idx, type) {
  window.taxAccounts[idx].type = type;
  renderTaxAccounts();
}

function updateTaxAccountAmount(idx, field, val) {
  if (!window.taxAccounts[idx]) return;
  window.taxAccounts[idx][field] = Math.max(0, Number(val) || 0);
  renderTaxAccounts();
}

// 분배 우선순위 — 재렌더 없이 상태만 갱신(입력 커서 유지).
function updateTaxAccountPriority(idx, val) {
  if (!window.taxAccounts[idx]) return;
  window.taxAccounts[idx].priority = Math.max(1, Number(val) || 1);
}

function ensureAccountTickers(idx) {
  const acc = window.taxAccounts[idx];
  if (!acc) return [];
  if (!Array.isArray(acc.tickers)) acc.tickers = [];
  return acc.tickers;
}

function redistributeAccountWeights(idx) {
  const accTickers = ensureAccountTickers(idx);
  const n = accTickers.length;
  if (!n) return;
  const base = Math.floor(100 / n);
  accTickers.forEach((t, i) => {
    t.weight = (i === n - 1) ? 100 - base * (n - 1) : base;
  });
}

function addAccountTicker(idx, code, name, badge) {
  const accTickers = ensureAccountTickers(idx);
  if (accTickers.find(t => t.code === code)) return;
  accTickers.push({ code, name, badge, weight: 0 });
  redistributeAccountWeights(idx);
  renderTaxAccounts();
}

function removeAccountTicker(idx, code) {
  const accTickers = ensureAccountTickers(idx);
  const pos = accTickers.findIndex(t => t.code === code);
  if (pos === -1) return;
  accTickers.splice(pos, 1);
  if (accTickers.length > 0) redistributeAccountWeights(idx);
  renderTaxAccounts();
}

function onAccountTickerWeightChange(idx, code, val) {
  const accTickers = ensureAccountTickers(idx);
  const ticker = accTickers.find(t => t.code === code);
  if (!ticker) return;
  ticker.weight = Math.max(0, Math.min(100, Number(val) || 0));
  renderTaxAccounts();
}

async function onAccountTickerSearch(idx, q) {
  const dropdown = document.getElementById(`accountTickerDropdown${idx}`);
  if (!dropdown) return;
  q = (q || '').trim();
  if (!q) { dropdown.style.display = 'none'; return; }

  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    if (!data.length) {
      dropdown.innerHTML = '<div style="padding:10px;font-size:0.78rem;color:#90A4AE">검색 결과 없음</div>';
    } else {
      dropdown.innerHTML = data.map(item => `
        <div class="ticker-drop-item"
          onclick="addAccountTicker(${idx}, '${item.code}', '${item.name.replace(/'/g, "\\'")}', '${item.badge}')">
          <span class="ticker-drop-badge"
            style="background:${badgeColor(item.badge)}22;color:${badgeColor(item.badge)}">${item.badge}</span>
          <div>
            <div class="ticker-drop-code">${item.code}</div>
            <div class="ticker-drop-name">${item.name}</div>
          </div>
        </div>
      `).join('');
    }
    dropdown.style.display = 'block';
  } catch(e) {
    dropdown.style.display = 'none';
  }
}

function renderAccountTickerList(idx) {
  const accTickers = ensureAccountTickers(idx);
  if (accTickers.length === 0) {
    return '<div style="font-size:0.76rem;color:#90A4AE;padding:8px 0;">종목을 추가하세요</div>';
  }
  const total = accTickers.reduce((s, t) => s + (Number(t.weight) || 0), 0);
  const warn = total > 100
    ? '<div style="font-size:0.72rem;color:#C62828;margin-top:4px;">비중 합계가 100%를 초과했습니다.</div>'
    : (total < 100 ? `<div style="font-size:0.72rem;color:#78909C;margin-top:4px;">나머지 ${100-total}%는 현금으로 유지됩니다.</div>` : '');
  return accTickers.map(t => `
    <div style="display:grid;grid-template-columns:70px 1fr 64px 24px;gap:6px;align-items:center;margin-top:6px;">
      <div style="font-weight:800;font-size:0.78rem;color:var(--text);">${t.code}</div>
      <div style="font-size:0.72rem;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${t.name || t.code}</div>
      <input type="number" value="${t.weight}" min="0" max="100" step="1"
        oninput="onAccountTickerWeightChange(${idx}, '${t.code}', this.value)"
        style="width:64px;border:1.5px solid var(--border);border-radius:6px;padding:4px;font-size:0.78rem;text-align:right;">
      <button onclick="removeAccountTicker(${idx}, '${t.code}')"
        style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:0.9rem;">✕</button>
    </div>
  `).join('') + warn;
}

function fmtTaxKRW(v) {
  if (!v) return '₩0';
  const sign = v < 0 ? '-' : '';
  const abs = Math.abs(v);
  const uk = Math.floor(abs / 1e8);
  const man = Math.floor((abs % 1e8) / 1e4);
  if (uk > 0 && man > 0) return sign + '₩' + uk.toLocaleString() + '억 ' + man.toLocaleString() + '만';
  if (uk > 0) return sign + '₩' + uk.toLocaleString() + '억';
  if (abs >= 1e4) return sign + '₩' + Math.floor(abs / 1e4).toLocaleString() + '만';
  return sign + '₩' + Math.round(abs).toLocaleString();
}

function renderTaxAccounts() {
  const accs     = window.taxAccounts;
  const isSingle = accs.length <= 1;
  const totalI   = Number(document.getElementById('initialCapital').value) || 0;
  const totalM   = Number(document.getElementById('monthlyContrib').value)  || 0;
  const list     = document.getElementById('taxAccountList');
  if (!list) return;

  const colors = { '위탁':'#1976D2','ISA':'#2E7D32','연금저축':'#7B1FA2','IRP':'#E65100' };

  list.innerHTML = accs.map((acc, i) => {
    if (isSingle) return `
      <div style="background:var(--bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;display:flex;align-items:center;gap:8px;">
        <select onchange="updateTaxAccountType(${i},this.value)"
          style="flex:1;border:1.5px solid var(--border);border-radius:7px;padding:6px 8px;font-size:0.85rem;background:white;">
          ${ACCOUNT_TYPES.map(t=>`<option value="${t}" ${acc.type===t?'selected':''}>${t}</option>`).join('')}
        </select>
        <span style="font-size:0.75rem;color:var(--text-muted);">상단 설정값 사용</span>
        <button onclick="removeTaxAccount(${i})" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1rem;">✕</button>
      </div>`;

    if (i === 0) {
      return `
        <div style="background:var(--bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;border:1px solid var(--border);">
          <div style="display:flex;align-items:center;gap:8px;">
            <div style="width:10px;height:10px;border-radius:50%;background:${colors[acc.type]||'#90A4AE'};flex-shrink:0;"></div>
            <select onchange="updateTaxAccountType(${i},this.value)"
              style="flex:1;border:1.5px solid var(--border);border-radius:7px;padding:6px 8px;font-size:0.85rem;background:white;">
              ${ACCOUNT_TYPES.map(t=>`<option value="${t}" ${acc.type===t?'selected':''}>${t}</option>`).join('')}
            </select>
            <label title="자금이동 우선순위(낮을수록 먼저 채움)" style="font-size:0.7rem;color:var(--text-muted);display:flex;align-items:center;gap:3px;">순위
              <input type="number" min="1" value="${Number(acc.priority ?? (i+1))}"
                onchange="updateTaxAccountPriority(${i}, this.value)"
                style="width:42px;border:1.5px solid var(--border);border-radius:6px;padding:4px 5px;font-size:0.8rem;background:white;"></label>
            <button onclick="removeTaxAccount(${i})" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1rem;">✕</button>
          </div>
          <div style="font-size:0.75rem;color:var(--text-muted);margin-top:6px;">
            계좌 1은 상단 포트폴리오와 금액을 사용합니다. 초기 <b style="color:var(--text);">${fmtTaxKRW(totalI)}</b> · 월 <b style="color:var(--text);">${fmtTaxKRW(totalM)}</b>
          </div>
        </div>`;
    }

    return `
      <div style="background:var(--bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;border:1px solid var(--border);">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">
          <div style="width:10px;height:10px;border-radius:50%;background:${colors[acc.type]||'#90A4AE'};flex-shrink:0;"></div>
          <select onchange="updateTaxAccountType(${i},this.value)"
            style="flex:1;border:1.5px solid var(--border);border-radius:7px;padding:5px 8px;font-size:0.82rem;background:white;">
            ${ACCOUNT_TYPES.map(t=>`<option value="${t}" ${acc.type===t?'selected':''}>${t}</option>`).join('')}
          </select>
          <label title="자금이동 우선순위(낮을수록 먼저 채움)" style="font-size:0.7rem;color:var(--text-muted);display:flex;align-items:center;gap:3px;">순위
            <input type="number" min="1" value="${Number(acc.priority ?? (i+1))}"
              onchange="updateTaxAccountPriority(${i}, this.value)"
              style="width:42px;border:1.5px solid var(--border);border-radius:6px;padding:4px 5px;font-size:0.8rem;background:white;"></label>
          <button onclick="removeTaxAccount(${i})" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1rem;">✕</button>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
          <label style="font-size:0.72rem;color:var(--text-muted);">초기 투자금
            <input type="number" value="${Number(acc.initial_capital || 0)}" min="0" step="1000000"
              oninput="updateTaxAccountAmount(${i}, 'initial_capital', this.value)"
              style="width:100%;margin-top:3px;border:1.5px solid var(--border);border-radius:7px;padding:6px 8px;font-size:0.82rem;background:white;">
          </label>
          <label style="font-size:0.72rem;color:var(--text-muted);">월 적립액
            <input type="number" value="${Number(acc.monthly_contribution || 0)}" min="0" step="100000"
              oninput="updateTaxAccountAmount(${i}, 'monthly_contribution', this.value)"
              style="width:100%;margin-top:3px;border:1.5px solid var(--border);border-radius:7px;padding:6px 8px;font-size:0.82rem;background:white;">
          </label>
        </div>
        <div style="position:relative;margin-top:6px;">
          <input type="text" id="accountTickerSearch${i}" placeholder="이 계좌 종목 검색"
            oninput="onAccountTickerSearch(${i}, this.value)"
            style="width:100%;border:1.5px solid var(--border);border-radius:7px;padding:7px 9px;font-size:0.8rem;background:white;">
          <div class="ticker-dropdown" id="accountTickerDropdown${i}" style="left:0;right:0;"></div>
        </div>
        ${renderAccountTickerList(i)}
      </div>`;
  }).join('');

  // 세액공제 메뉴 표시 조건
  const hasPension = accs.some(a => a.type === '연금저축' || a.type === 'IRP');
  const dedSec     = document.getElementById('taxDeductionSection');
  if (dedSec) dedSec.style.display = hasPension ? 'block' : 'none';

  // ISA 풍차돌리기 섹션
  const hasISA     = accs.some(a => a.type === 'ISA');
  const isaRenSec  = document.getElementById('isaRenewalSection');
  if (isaRenSec) isaRenSec.style.display = hasISA ? 'block' : 'none';

  // 절세 매도 섹션 (위탁 계좌)
  const hasWitaku  = accs.some(a => a.type === '위탁');
  const ghSec      = document.getElementById('gainHarvestingSection');
  if (ghSec) ghSec.style.display = hasWitaku ? 'block' : 'none';

  checkTaxLimits();
}

function checkTaxLimits() {
  const totalM  = Number(document.getElementById('monthlyContrib').value) || 0;
  const accs    = window.taxAccounts;
  const isSingle = accs.length <= 1;
  const warnings = [];

  let pensionAnn = 0, irpAnn = 0;
  accs.forEach((a, i) => {
    const m = isSingle || i === 0 ? totalM : Number(a.monthly_contribution || 0);
    if (a.type === '연금저축') pensionAnn += m * 12;
    if (a.type === 'IRP')     irpAnn     += m * 12;
  });
  if (pensionAnn + irpAnn > 18_000_000)
    warnings.push(`⚠ 연금저축+IRP 연간 합계 ${fmtTaxKRW(pensionAnn+irpAnn)}이 한도(1,800만)를 초과합니다.`);
  if (Math.min(pensionAnn, 6_000_000) + irpAnn > 9_000_000)
    warnings.push(`⚠ 세액공제 한도(900만) 초과분은 공제 불가합니다.`);

  const warnEl = document.getElementById('taxWarnings');
  if (warnEl) {
    let html = warnings.map(w =>
      `<div style="font-size:0.75rem;color:#C62828;background:#FFEBEE;padding:6px 10px;border-radius:6px;margin-bottom:4px;">${w}</div>`
    ).join('');
    // 멀티계좌면 초과분이 분배 우선순위대로 다른 계좌로 이전됨을 안내(단일계좌는 이전 대상 없음).
    if (warnings.length && !isSingle) {
      html += `<div style="font-size:0.73rem;color:#1B5E20;background:#E8F5E9;padding:6px 10px;border-radius:6px;margin-bottom:4px;">➜ 납입한도 초과분은 분배 우선순위에 따라 다른 계좌로 이전됩니다.</div>`;
    }
    warnEl.innerHTML = html;
  }
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
    scale: 2, backgroundColor: '#F0F4F8', useCORS: true, allowTaint: true,
    onclone: function(doc, clonedEl) {
      const hdr = doc.createElement('div');
      hdr.style.cssText = 'background:#1A2332;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;width:100%;box-sizing:border-box;margin-bottom:4px;';
      hdr.innerHTML = '<span style="color:#1976D2;font-size:0.95rem;font-weight:800;">💰 Money Milestone</span>'
                    + '<span style="color:#90A4AE;font-size:0.78rem;">moneymilestone.duckdns.org · 무료 투자 분석 도구</span>';
      clonedEl.insertBefore(hdr, clonedEl.firstChild);
      const cond = doc.createElement('div');
      cond.style.cssText = 'background:white;border:1.5px solid #E0E7EF;border-radius:10px;padding:10px 16px;margin-bottom:12px;display:flex;gap:20px;flex-wrap:wrap;font-family:inherit;';
      cond.innerHTML = [
        ['종목', label], ['기간', years], ['중간값', p50], ['CAGR', cagr],
      ].map(([l,v]) => '<div><span style="font-size:0.68rem;color:#90A4AE;display:block;">' + l + '</span><span style="font-size:0.82rem;font-weight:700;color:#1A2332;">' + v + '</span></div>').join('');
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
