// ── 멀티계좌 입력 UI (공용 모듈) ──────────────────────────────────────────
// 투자계산기·백테스트·은퇴 3개 탭이 공유. 단일소스 — 버그수정 1곳(드리프트 방지).
//
// 호스트 페이지 계약(이 모듈이 런타임에 참조하는 전역/DOM, 각 탭이 제공해야 함):
//   - 전역 `tickers`            : 상단 포트폴리오 [{code,name,badge,weight(0~100)}]
//   - 전역 `window.taxAccounts` : 계좌 배열(호스트가 [] 로 초기화)
//   - 전역 함수 `badgeColor(badge)`
//   - DOM id `initialCapital`·`monthlyContrib` : 상단 총 초기/월 금액 입력
//   - DOM id `taxAccountList`·`taxWarnings`
//   - DOM id `taxDeductionSection`·`isaRenewalSection`·`gainHarvestingSection`(선택, 있으면 토글)
// 결과 렌더(renderMultiAccountSummary)와 토글(toggleTax)·프로필 로드는 탭별 glue 로 분리.

const ACCOUNT_TYPES = ['위탁', 'ISA', '연금저축', 'IRP'];

// 탭별 결합점 설정. 각 탭이 자기 포트폴리오 전역·상단 금액 DOM id를 주입.
// 미설정 시 calculator 기본값(전역 `tickers`, id `initialCapital`/`monthlyContrib`).
window.MMTAX = window.MMTAX || {};
function _mmPortfolioTickers() {
  if (typeof window.MMTAX.portfolioTickers === 'function') return window.MMTAX.portfolioTickers();
  return (typeof tickers !== 'undefined') ? tickers : [];
}
function _mmTotalAmount(kind) {
  const id = kind === 'init'
    ? (window.MMTAX.totalInitId || 'initialCapital')
    : (window.MMTAX.totalMonId  || 'monthlyContrib');
  const el = document.getElementById(id);
  return el ? (Number(el.value) || 0) : 0;
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

function addTaxAccount() {
  window.taxAccounts.push({
    type: '위탁',
    initial_capital: 0,
    monthly_contribution: 0,
    tickers: _mmPortfolioTickers().map(t => ({...t})),
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

// 금액 입력(oninput) — 입력칸 재생성하면 커서 유실(BUG-G1-2).
// 상태만 갱신하고 금액 의존 표시(연금/IRP 한도경고)는 입력칸 안 건드리는 checkTaxLimits로만.
function updateTaxAccountAmount(idx, field, val) {
  if (!window.taxAccounts[idx]) return;
  window.taxAccounts[idx][field] = Math.max(0, Number(val) || 0);
  checkTaxLimits();
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

// 비중 입력(oninput) — 입력칸 재생성하면 커서 유실(BUG-G1-2).
// 상태만 갱신하고 비중합계 경고는 입력칸 안 건드리는 전용 div만 갱신.
function onAccountTickerWeightChange(idx, code, val) {
  const accTickers = ensureAccountTickers(idx);
  const ticker = accTickers.find(t => t.code === code);
  if (!ticker) return;
  ticker.weight = Math.max(0, Math.min(100, Number(val) || 0));
  const warnEl = document.getElementById(`acctWeightWarn${idx}`);
  if (warnEl) warnEl.innerHTML = accountWeightWarnHtml(idx);
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

// 비중합계 경고 HTML — oninput 시 입력칸 재생성 없이 전용 div만 갱신하려고 분리(BUG-G1-2).
function accountWeightWarnHtml(idx) {
  const accTickers = ensureAccountTickers(idx);
  const total = accTickers.reduce((s, t) => s + (Number(t.weight) || 0), 0);
  if (total > 100) return '<span style="font-size:0.72rem;color:#C62828;">비중 합계가 100%를 초과했습니다.</span>';
  if (total < 100) return `<span style="font-size:0.72rem;color:#78909C;">나머지 ${100-total}%는 현금으로 유지됩니다.</span>`;
  return '';
}

function renderAccountTickerList(idx) {
  const accTickers = ensureAccountTickers(idx);
  if (accTickers.length === 0) {
    return '<div style="font-size:0.76rem;color:#90A4AE;padding:8px 0;">종목을 추가하세요</div>';
  }
  const warn = `<div id="acctWeightWarn${idx}" style="margin-top:4px;">${accountWeightWarnHtml(idx)}</div>`;
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
  const totalI   = _mmTotalAmount('init');
  const totalM   = _mmTotalAmount('mon');
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
  const totalM  = _mmTotalAmount('mon');
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

// 멀티계좌 결과 요약(분포) — 계산기·은퇴 적립 공유. 계좌별 p10/p50/p90 + 절세 + g2.
// (백테스트는 단일윈도우라 스칼라 종료값 → 자체 렌더 사용)
function renderMultiAccountSummary(multiAccount, g2, savings, autoWindmill) {
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
    // 절세액 = 껍데기 효과(tax_saving) + 절세매도 효과(gain_harvest_saving) 합산.
    const totalSaving = (c.tax_saving || 0) + (c.gain_harvest_saving || 0);
    const accRows = (savings.accounts || [])
      .filter(a => a.brokerage_assumed_tax > 0 || a.tax_saving > 0 || a.gain_harvest_saving > 0)
      .map(a => `
        <div style="display:flex;justify-content:space-between;font-size:0.73rem;color:#33691E;margin-top:3px;">
          <span>${a.type || '계좌'}</span>
          <span>위탁가정 ${fmtKRW(a.brokerage_assumed_tax)} · 실제 ${fmtKRW(a.actual_tax)} · 절세 <b>${fmtKRW((a.tax_saving || 0) + (a.gain_harvest_saving || 0))}</b></span>
        </div>`).join('');
    const ghNote = (c.gain_harvest_saving > 0)
      ? `<div style="font-size:0.68rem;color:#558B2F;margin-top:4px;">↳ 절세매도(연 250만 공제) 효과 ${fmtKRW(c.gain_harvest_saving)} 포함</div>`
      : '';
    savingsHtml = `
      <div style="margin-top:10px;padding:12px;background:#E8F5E9;border:1px solid #A5D6A7;border-radius:8px;">
        <div style="font-size:0.8rem;font-weight:800;color:#1B5E20;margin-bottom:8px;">💰 세금 절감 효과 (중앙값 기준)</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
          <div><div style="font-size:0.68rem;color:#558B2F;">전체 위탁 가정 세금</div><div style="font-size:0.9rem;font-weight:800;color:#33691E;">${fmtKRW(c.brokerage_assumed_tax)}</div></div>
          <div><div style="font-size:0.68rem;color:#558B2F;">실제 세금</div><div style="font-size:0.9rem;font-weight:800;color:#33691E;">${fmtKRW(c.actual_tax)}</div></div>
          <div><div style="font-size:0.68rem;color:#558B2F;">절세액</div><div style="font-size:0.98rem;font-weight:900;color:#2E7D32;">약 ${fmtKRW(totalSaving)}</div></div>
        </div>
        ${ghNote}
        ${accRows}
        <div style="font-size:0.67rem;color:#7CB342;margin-top:8px;">※ 근사치 — 금융소득종합과세 가산·연금 인출세 미반영(연금 인출세는 은퇴 탭에서). ISA는 세후 재투자 가정.</div>
      </div>`;
  }

  // 단일 풍차 ISA → 위탁계좌 자동 생성 안내(연 2천만 한도 초과분 위탁 운용).
  const autoWindmillHtml = autoWindmill ? `
    <div style="margin-top:10px;padding:9px 12px;background:#E3F2FD;border:1px solid #90CAF9;border-radius:8px;font-size:0.75rem;color:#0D47A1;">
      ℹ️ ISA 해지 시 전액 재입금이 불가하여(연 2,000만원 한도) 한도 초과분은 자동 생성된 위탁계좌(같은 종목·비중)에서 운용했습니다.
    </div>` : '';

  wrap.innerHTML = `
    <div class="result-card" style="margin-bottom:0;">
      <div class="result-card-title">계좌별 종료 자산</div>
      ${autoWindmillHtml}
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;">${rows}</div>
      ${savingsHtml}
      ${g2Html}
      ${warnings}
    </div>`;
  wrap.style.display = 'block';
}
