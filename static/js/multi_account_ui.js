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
// 'accumulation'(투자계산기·은퇴 적립) | 'withdrawal'(은퇴 인출기 — 월적립 없음, 시작 목돈+미실현차익).
function _mmMode() {
  return (window.MMTAX && window.MMTAX.mode) || 'accumulation';
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

// ── D4 계좌별 거래수수료 ─────────────────────────────────
// 증권사가 계좌마다 다르므로 카드별 수수료율 지정. feeEnabledChk(계산기·백테만 존재)
// 켜진 경우에만 카드에 노출 → 미배선 탭(은퇴·배당)은 _mmFeeField가 ''로 자동 미표시.
// 상태 = acc.fee_rate_pct(%). 미지정이면 탭레벨 입력(feeRateInput)을 기본 시드로 사용.
const _MM_FEE_PRESET_FALLBACK = [
  { v: '0.015', label: '키움 0.015%' },
  { v: '0.0140527', label: '한국투자 0.0140527%' },
  { v: '0.1', label: '토스 미국 0.1%' },
];

function _mmBrokerFeeMarket() {
  return document.querySelector('input[name="feeMarket"]:checked')?.value || 'domestic_stock';
}

function _mmFeePresets() {
  const market = _mmBrokerFeeMarket();
  const brokerPresets = Array.isArray(window.MM_BROKER_FEE_PRESETS) ? window.MM_BROKER_FEE_PRESETS : [];
  const mapped = brokerPresets.map(p => {
    const rate = Number(p?.rates?.[market]?.commission_pct);
    if (!Number.isFinite(rate)) return null;
    const display = p?.rates?.[market]?.display || (rate + '%');
    return { v: String(rate), label: `${p.name} ${display}` };
  }).filter(Boolean);
  return mapped.length ? mapped : _MM_FEE_PRESET_FALLBACK;
}

function _mmFeeOn() {
  return document.getElementById('feeEnabledChk')?.checked ?? false;
}

function _mmTabFeePct() {
  return Number(document.getElementById('feeRateInput')?.value) || 0;
}

// 계좌 유효 수수료율(%) — 계좌 지정값 우선, 없으면 탭레벨 시드.
function _mmAccountFeePct(acc) {
  return acc && acc.fee_rate_pct != null ? Number(acc.fee_rate_pct) : _mmTabFeePct();
}

function _mmFeeField(acc, i) {
  if (!_mmFeeOn()) return '';
  const pct = _mmAccountFeePct(acc);
  const feePresets = _mmFeePresets();
  const isPreset = feePresets.some(p => Number(p.v) === pct);
  const opts = feePresets.map(p =>
      `<option value="${p.v}" ${Number(p.v) === pct ? 'selected' : ''}>${p.label}</option>`).join('')
    + `<option value="custom" ${isPreset ? '' : 'selected'}>직접입력</option>`;
  return `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-top:10px;align-items:end;">
      <label style="min-width:0;font-size:0.7rem;font-weight:600;color:var(--ds-muted,var(--text-muted));">증권사 프리셋
        <select id="accountFeePreset${i}" onchange="updateAccountFeePreset(${i}, this.value)"
          style="width:100%;min-width:0;box-sizing:border-box;margin-top:4px;border:1.5px solid var(--ds-hairline,var(--border));border-radius:var(--r-sm,7px);padding:7px 9px;font-size:0.78rem;background:var(--ds-canvas,var(--input-bg));color:var(--ds-ink,var(--text));">
          ${opts}
        </select>
      </label>
      <label style="min-width:0;font-size:0.7rem;font-weight:600;color:var(--ds-muted,var(--text-muted));">수수료율 (%)
        <input type="number" id="accountFeeRate${i}" value="${pct}" min="0" step="0.001"
          oninput="updateAccountFeeRate(${i}, this.value)"
          style="width:100%;min-width:0;box-sizing:border-box;margin-top:4px;border:1.5px solid var(--ds-hairline,var(--border));border-radius:var(--r-sm,7px);padding:7px 9px;font-size:0.78rem;background:var(--ds-canvas,var(--input-bg));color:var(--ds-ink,var(--text));">
      </label>
    </div>`;
}

// 프리셋 선택 — 상태 + 수수료율 입력칸 DOM 동기화(재렌더 없이, 커서 무관 select).
function updateAccountFeePreset(idx, v) {
  if (v === 'custom') return;
  if (window.taxAccounts[idx]) window.taxAccounts[idx].fee_rate_pct = Number(v) || 0;
  const inp = document.getElementById(`accountFeeRate${idx}`);
  if (inp) inp.value = v;
}

// 직접입력 — 재렌더 없이 상태만(입력 커서 유지, updateTaxAccountAmount와 동일 정책).
// 프리셋 select 라벨도 동기화(매칭 율이면 그 증권사, 아니면 '직접입력').
function updateAccountFeeRate(idx, v) {
  const pct = Math.max(0, Number(v) || 0);
  if (window.taxAccounts[idx]) window.taxAccounts[idx].fee_rate_pct = pct;
  const sel = document.getElementById(`accountFeePreset${idx}`);
  if (sel) sel.value = _mmFeePresets().some(p => Number(p.v) === pct) ? String(pct) : 'custom';
}

function ensureAccountTickers(idx) {
  const acc = window.taxAccounts[idx];
  if (!acc) return [];
  if (!Array.isArray(acc.tickers)) acc.tickers = [];
  return acc.tickers;
}

// ── 계좌별 포트폴리오 즐겨찾기 (B1 연동) ─────────────────────────
// 계좌 2+ 카드의 종목 입력에 저장된 포트폴리오 불러오기 select 제공.
let _mmFavList = null;        // null=미로드, []=비로그인/없음
let _mmFavStarted = false;

function _mmEsc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
}

async function _mmFavFetch() {
  try {
    // /api/me 선확인 — 비로그인 401 콘솔 노이즈 방지(MMFav 위젯과 동일 패턴)
    const me = await fetch('/api/me').then(r => r.json());
    if (!me.logged_in) { _mmFavList = []; return; }
    const res = await fetch('/api/portfolio/list');
    _mmFavList = res.ok ? await res.json() : [];
  } catch (e) { _mmFavList = []; }
}

function _mmFavOptionsHtml() {
  const items = _mmFavList || [];
  const ph = items.length ? '★ 즐겨찾기 불러오기' : '★ 저장된 포트폴리오 없음';
  return `<option value="">${_mmFavList === null ? '★ 즐겨찾기 불러오기' : ph}</option>` +
    items.map(p => `<option value="${p.id}">${_mmEsc(p.name)}</option>`).join('');
}

// 포커스 시 재조회 — 같은 페이지에서 방금 저장한 즐겨찾기도 바로 보이게.
async function refreshAccountFavSelect(sel) {
  await _mmFavFetch();
  const v = sel.value;
  sel.innerHTML = _mmFavOptionsHtml();
  sel.value = v;
}

function applyFavToAccount(idx, favId) {
  const id = Number(favId);
  if (!id) return;
  const fav = (_mmFavList || []).find(p => p.id === id);
  if (!fav || !window.taxAccounts[idx]) return;
  window.taxAccounts[idx].tickers = fav.tickers.map(t => ({
    code: t.code, name: t.name || t.code, badge: t.badge || '',
    weight: Math.round(Number(t.weight) || 0),
  }));
  renderTaxAccounts();
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
      dropdown.innerHTML = '<div style="padding:10px;font-size:0.78rem;color:var(--text-muted)">검색 결과 없음</div>';
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
  if (total > 100) return '<span style="font-size:0.72rem;color:var(--red);">비중 합계가 100%를 초과했습니다.</span>';
  if (total < 100) return `<span style="font-size:0.72rem;color:var(--text-muted);">나머지 ${100-total}%는 현금으로 유지됩니다.</span>`;
  return '';
}

// 계좌 비중 변경 — 같은 행의 number↔slider 동기(재렌더 없이 커서 보존, BUG-G1-2).
function _mmAcctW(el, idx, code) {
  const v = Math.max(0, Math.min(100, Number(el.value) || 0));
  const row = el.closest('.ticker-item');
  if (row) row.querySelectorAll('.ticker-weight-input, .ticker-weight-slider').forEach(x => { if (x !== el) x.value = v; });
  onAccountTickerWeightChange(idx, code, v);
}

// 계좌 종목 리스트 — 메인 입력창과 동일 .ticker-item 컴포넌트로 대칭.
function renderAccountTickerList(idx) {
  const accTickers = ensureAccountTickers(idx);
  if (accTickers.length === 0) {
    return '<div style="font-size:var(--fs-cap,13px);color:var(--ds-muted);padding:8px 0;">종목을 추가하세요</div>';
  }
  const warn = `<div id="acctWeightWarn${idx}" style="margin-top:6px;">${accountWeightWarnHtml(idx)}</div>`;
  return '<div style="display:flex;flex-direction:column;gap:8px;margin-top:8px;">' + accTickers.map(t => `
    <div class="ticker-item">
      <span class="ticker-badge">${t.code}</span>
      <span class="ticker-name">${_mmEsc((t.name || t.code).substring(0, 12))}</span>
      <input type="number" class="ticker-weight-input" value="${t.weight}" min="0" max="100" step="1"
        oninput="_mmAcctW(this, ${idx}, '${t.code}')"> %
      <input type="range" class="ticker-weight-slider" value="${t.weight}" min="0" max="100"
        oninput="_mmAcctW(this, ${idx}, '${t.code}')">
      <button class="ticker-remove-btn" onclick="removeAccountTicker(${idx}, '${t.code}')">×</button>
    </div>
  `).join('') + '</div>' + warn;
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

// 계좌 카드 금액 입력칸 — 메인 입력창과 동일 컴포넌트(.calc-input/.input-group/.unit)로 대칭.
// 모드별: 적립=초기+월적립 / 인출=시작목돈(+위탁 미실현차익).
const _MM_LBL = 'display:block;font-size:var(--fs-cap,13px);font-weight:600;color:var(--ds-body);margin-bottom:7px;';
function _mmMoneyField(label, field, val, step, i, title) {
  return `
        <div style="margin-bottom:0;">
          <label style="${_MM_LBL}"${title ? ` title="${title}"` : ''}>${label}</label>
          <div class="input-group">
            <input type="number" class="calc-input" value="${Number(val || 0)}" min="0" step="${step}"
              oninput="updateTaxAccountAmount(${i}, '${field}', this.value)">
            <span class="unit">원</span>
          </div>
        </div>`;
}
function _mmAmountFields(acc, i) {
  if (_mmMode() !== 'withdrawal') {
    return `<div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;margin-bottom:10px;">
          ${_mmMoneyField('초기 투자금', 'initial_capital', acc.initial_capital, 1000000, i)}
          ${_mmMoneyField('월 적립액', 'monthly_contribution', acc.monthly_contribution, 100000, i)}
        </div>`;
  }
  // 인출 모드: 위탁만 미실현차익(양도세 취득가 = 시작목돈 − 미실현차익).
  if (acc.type === '위탁') {
    return `<div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;margin-bottom:10px;">
          ${_mmMoneyField('시작 목돈', 'initial_capital', acc.initial_capital, 1000000, i)}
          ${_mmMoneyField('미실현 차익', 'unrealized_gain', acc.unrealized_gain, 1000000, i, '현재 평가액 중 매수가 대비 이익(양도세 취득가 산정용)')}
        </div>`;
  }
  return `<div style="margin-bottom:10px;">${_mmMoneyField('시작 목돈', 'initial_capital', acc.initial_capital, 1000000, i)}</div>`;
}

function renderTaxAccounts() {
  const accs     = window.taxAccounts;
  const isSingle = accs.length <= 1;
  const totalI   = _mmTotalAmount('init');
  const totalM   = _mmTotalAmount('mon');
  const list     = document.getElementById('taxAccountList');
  if (!list) return;

  const colors = { '위탁':'#1976D2','ISA':'#2E7D32','연금저축':'#7B1FA2','IRP':'#E65100' };

  // 멀티계좌 첫 렌더 시 즐겨찾기 목록 1회 로드 → 도착하면 select 옵션 채워 재렌더.
  if (!_mmFavStarted && accs.length > 1) {
    _mmFavStarted = true;
    _mmFavFetch().then(() => renderTaxAccounts());
  }

  list.innerHTML = accs.map((acc, i) => {
    if (isSingle) return `
      <div style="background:var(--bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;display:flex;align-items:center;gap:8px;">
        <select onchange="updateTaxAccountType(${i},this.value)"
          style="flex:1;border:1.5px solid var(--border);border-radius:7px;padding:6px 8px;font-size:0.85rem;background:var(--input-bg);">
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
              style="flex:1;border:1.5px solid var(--border);border-radius:7px;padding:6px 8px;font-size:0.85rem;background:var(--input-bg);">
              ${ACCOUNT_TYPES.map(t=>`<option value="${t}" ${acc.type===t?'selected':''}>${t}</option>`).join('')}
            </select>
            <label title="자금이동 우선순위(낮을수록 먼저 채움)" style="font-size:0.7rem;color:var(--text-muted);display:flex;align-items:center;gap:3px;">순위
              <input type="number" min="1" value="${Number(acc.priority ?? (i+1))}"
                onchange="updateTaxAccountPriority(${i}, this.value)"
                style="width:42px;border:1.5px solid var(--border);border-radius:6px;padding:4px 5px;font-size:0.8rem;background:var(--input-bg);"></label>
            <button onclick="removeTaxAccount(${i})" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1rem;">✕</button>
          </div>
          <div style="font-size:0.75rem;color:var(--text-muted);margin-top:6px;">
            ${_mmMode() === 'withdrawal'
              ? `계좌 1은 상단 포트폴리오와 시작 목돈을 사용합니다. 시작 목돈 <b style="color:var(--text);">${fmtTaxKRW(totalI)}</b>`
              : `계좌 1은 상단 포트폴리오와 금액을 사용합니다. 초기 <b style="color:var(--text);">${fmtTaxKRW(totalI)}</b> · 월 <b style="color:var(--text);">${fmtTaxKRW(totalM)}</b>`}
          </div>
          ${_mmMode() === 'withdrawal' && acc.type === '위탁' ? `
          <label style="display:block;font-size:0.72rem;color:var(--text-muted);margin-top:8px;" title="현재 평가액 중 매수가 대비 이익(양도세 취득가 산정용)">미실현 차익
            <input type="number" value="${Number(acc.unrealized_gain || 0)}" min="0" step="1000000"
              oninput="updateTaxAccountAmount(${i}, 'unrealized_gain', this.value)"
              style="width:100%;margin-top:3px;border:1.5px solid var(--border);border-radius:7px;padding:6px 8px;font-size:0.82rem;background:var(--input-bg);">
          </label>` : ''}
          ${_mmFeeField(acc, i)}
        </div>`;
    }

    return `
      <div style="background:var(--bg);border-radius:10px;padding:10px 12px;margin-bottom:8px;border:1px solid var(--border);">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">
          <div style="width:10px;height:10px;border-radius:50%;background:${colors[acc.type]||'#90A4AE'};flex-shrink:0;"></div>
          <select onchange="updateTaxAccountType(${i},this.value)"
            style="flex:1;border:1.5px solid var(--border);border-radius:7px;padding:5px 8px;font-size:0.82rem;background:var(--input-bg);">
            ${ACCOUNT_TYPES.map(t=>`<option value="${t}" ${acc.type===t?'selected':''}>${t}</option>`).join('')}
          </select>
          <label title="자금이동 우선순위(낮을수록 먼저 채움)" style="font-size:0.7rem;color:var(--text-muted);display:flex;align-items:center;gap:3px;">순위
            <input type="number" min="1" value="${Number(acc.priority ?? (i+1))}"
              onchange="updateTaxAccountPriority(${i}, this.value)"
              style="width:42px;border:1.5px solid var(--border);border-radius:6px;padding:4px 5px;font-size:0.8rem;background:var(--input-bg);"></label>
          <button onclick="removeTaxAccount(${i})" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1rem;">✕</button>
        </div>
        ${_mmAmountFields(acc, i)}
        <select class="acct-fav-select" id="accountFavSelect${i}"
          onfocus="refreshAccountFavSelect(this)" onchange="applyFavToAccount(${i}, this.value)"
          style="width:100%;margin-top:6px;border:1.5px solid var(--border);border-radius:7px;padding:6px 8px;font-size:0.78rem;background:var(--input-bg);color:var(--text);">
          ${_mmFavOptionsHtml()}
        </select>
        <div style="position:relative;margin-top:6px;">
          <input type="text" id="accountTickerSearch${i}" placeholder="이 계좌 종목 검색"
            oninput="onAccountTickerSearch(${i}, this.value)"
            style="width:100%;box-sizing:border-box;border:1.5px solid var(--ds-hairline);border-radius:var(--r-md,12px);padding:11px 14px;font-size:var(--fs-sm,14px);background:var(--ds-soft);color:var(--ds-ink);outline:none;">
          <div class="ticker-dropdown" id="accountTickerDropdown${i}" style="left:0;right:0;"></div>
        </div>
        ${renderAccountTickerList(i)}
        ${_mmFeeField(acc, i)}
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
      `<div style="font-size:0.75rem;color:var(--red);background:var(--red-pale);padding:6px 10px;border-radius:6px;margin-bottom:4px;">${w}</div>`
    ).join('');
    // 멀티계좌면 초과분이 분배 우선순위대로 다른 계좌로 이전됨을 안내(단일계좌는 이전 대상 없음).
    if (warnings.length && !isSingle) {
      html += `<div style="font-size:0.73rem;color:var(--green);background:var(--green-pale);padding:6px 10px;border-radius:6px;margin-bottom:4px;">➜ 납입한도 초과분은 분배 우선순위에 따라 다른 계좌로 이전됩니다.</div>`;
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
    `<div style="font-size:0.76rem;color:var(--red);background:var(--red-pale);border-radius:6px;padding:6px 8px;margin-top:6px;">${w}</div>`
  ).join('');
  // 멀티계좌 결과 — 한도 초과분은 분배 우선순위대로 이전됨을 안내.
  if ((multiAccount.contribution_warnings || []).length) {
    warnings += `<div style="font-size:0.74rem;color:var(--green);background:var(--green-pale);border-radius:6px;padding:6px 8px;margin-top:6px;">➜ 납입한도 초과분은 분배 우선순위에 따라 다른 계좌로 이전됩니다.</div>`;
  }
  const rows = multiAccount.accounts.map((acc, i) => {
    const d = acc.distribution?.end_value || {};
    return `
      <div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
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
        <div style="margin-top:10px;padding:10px 12px;background:var(--green-pale);border:1px solid var(--green-light);border-radius:8px;">
          <div style="font-size:0.78rem;font-weight:800;color:var(--green);margin-bottom:6px;">자금 이동 · 세액공제 (대표 시나리오)</div>
          ${items.map(t => `<div style="font-size:0.76rem;color:var(--green);margin-top:3px;">• ${t}</div>`).join('')}
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
        <div style="display:flex;justify-content:space-between;font-size:0.73rem;color:var(--green);margin-top:3px;">
          <span>${a.type || '계좌'}</span>
          <span>위탁가정 ${fmtKRW(a.brokerage_assumed_tax)} · 실제 ${fmtKRW(a.actual_tax)} · 절세 <b>${fmtKRW((a.tax_saving || 0) + (a.gain_harvest_saving || 0))}</b></span>
        </div>`).join('');
    const ghNote = (c.gain_harvest_saving > 0)
      ? `<div style="font-size:0.68rem;color:var(--green);margin-top:4px;">↳ 절세매도(연 250만 공제) 효과 ${fmtKRW(c.gain_harvest_saving)} 포함</div>`
      : '';
    savingsHtml = `
      <div style="margin-top:10px;padding:12px;background:var(--green-pale);border:1px solid var(--green-light);border-radius:8px;">
        <div style="font-size:0.8rem;font-weight:800;color:var(--green);margin-bottom:8px;">💰 세금 절감 효과 (중앙값 기준)</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">
          <div><div style="font-size:0.68rem;color:var(--green);">전체 위탁 가정 세금</div><div style="font-size:0.9rem;font-weight:800;color:var(--green);">${fmtKRW(c.brokerage_assumed_tax)}</div></div>
          <div><div style="font-size:0.68rem;color:var(--green);">실제 세금</div><div style="font-size:0.9rem;font-weight:800;color:var(--green);">${fmtKRW(c.actual_tax)}</div></div>
          <div><div style="font-size:0.68rem;color:var(--green);">절세액</div><div style="font-size:0.98rem;font-weight:900;color:var(--green);">약 ${fmtKRW(totalSaving)}</div></div>
        </div>
        ${ghNote}
        ${accRows}
        <div style="font-size:0.67rem;color:#7CB342;margin-top:8px;">${
          _mmMode() === 'withdrawal'
            ? '※ 근사치 — 금융소득종합과세 가산 미반영. 실제 세금에 연금소득세 포함. ISA는 세후 재투자 가정.'
            : '※ 근사치 — 금융소득종합과세 가산·연금 인출세 미반영(연금 인출세는 은퇴 탭에서). ISA는 세후 재투자 가정.'
        }</div>
      </div>`;
  }

  // 단일 풍차 ISA → 위탁계좌 자동 생성 안내(연 2천만 한도 초과분 위탁 운용).
  const autoWindmillHtml = autoWindmill ? `
    <div style="margin-top:10px;padding:9px 12px;background:var(--blue-pale);border:1px solid var(--blue-soft);border-radius:8px;font-size:0.75rem;color:var(--blue);">
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
