/* broker_fee.js — 증권사 수수료 프리셋 공용 모듈 (retirement·dividend 공유).
   표준 DOM ID: #feePreset(select) · input[name=feeMarket] · #feeRateInput · #feePresetMeta.
   백테스트/계산기는 자체 인라인 구현 유지(이 모듈 미사용). */
(function () {
  const URL = "/static/data/broker_fee_presets.json?v=20260619fees";
  const MARKET_LABELS = { domestic_stock: '국내주식', domestic_etf: '국내 ETF/ETN', us_stock: '미국주식' };
  const FALLBACK = [
    { id: 'kiwoom', name: '키움증권', rates: {
        domestic_stock: { commission_pct: 0.015, display: '0.015%' },
        domestic_etf:   { commission_pct: 0.015, display: '0.015%' },
        us_stock:       { commission_pct: 0.25,  display: '0.25%' } },
      notes: '대표 온라인 수수료 기준. 제비용과 세금은 별도.' },
    { id: 'toss', name: '토스증권', rates: {
        domestic_stock: { commission_pct: 0.015, display: 'KRX 0.015%' },
        domestic_etf:   { commission_pct: 0.015, display: 'KRX 0.015%' },
        us_stock:       { commission_pct: 0.1,   display: '0.1%' } },
      notes: '조건부 이벤트와 제비용은 계좌별로 다를 수 있습니다.' },
  ];
  let presets = [];

  const E = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
  const market = () => document.querySelector('input[name="feeMarket"]:checked')?.value || 'domestic_stock';
  const curPreset = () => {
    const id = document.getElementById('feePreset')?.value || 'custom';
    return presets.find(p => p.id === id) || null;
  };
  const rateFor = (p, m) => { const r = p?.rates?.[m]?.commission_pct; return Number.isFinite(Number(r)) ? Number(r) : null; };
  const dispFor = (p, m) => p?.rates?.[m]?.display || (rateFor(p, m) != null ? rateFor(p, m) + '%' : '');

  const CUSTOM_META = '<b>직접입력</b><br>매수·매도 공통 적용. 국내 개별주식 매도 거래세는 별도 반영됩니다.';

  function applyFeePreset(v) {
    // 옛 인라인 호출 applyFeePreset('0.015') 하위호환
    if (v && v !== 'custom' && !presets.some(p => p.id === v)) {
      const legacy = Number(v);
      if (Number.isFinite(legacy)) { const i = document.getElementById('feeRateInput'); if (i) i.value = legacy; return; }
    }
    if (v) { const sel = document.getElementById('feePreset'); if (sel) sel.value = v; }
    const p = curPreset(), m = market();
    const inp = document.getElementById('feeRateInput'), meta = document.getElementById('feePresetMeta');
    if (!p) { if (meta) meta.innerHTML = CUSTOM_META; return; }
    const r = rateFor(p, m);
    if (inp && r != null) inp.value = r;
    if (meta) meta.innerHTML = `<b>${E(p.name)} · ${E(MARKET_LABELS[m] || m)} ${E(dispFor(p, m))}</b><br>${E(p.notes || '이벤트·협의수수료·제비용·세금은 계좌별로 다를 수 있습니다.')}`;
    // 멀티계좌 카드 수수료 갱신
    if (window.taxEnabled && (window.taxAccounts || []).length > 1 && typeof renderTaxAccounts === 'function') renderTaxAccounts();
  }

  function markFeePresetCustom() {
    const sel = document.getElementById('feePreset'); if (sel) sel.value = 'custom';
    const meta = document.getElementById('feePresetMeta'); if (meta) meta.innerHTML = CUSTOM_META;
  }

  function renderOptions() {
    const sel = document.getElementById('feePreset');
    if (!sel) return;
    const prev = sel.value;
    sel.innerHTML = presets.map(p => `<option value="${p.id}">${E(p.name)}</option>`).join('') + '<option value="custom">직접입력</option>';
    sel.value = presets.some(p => p.id === prev) ? prev : (presets[0]?.id || 'custom');
    applyFeePreset();
  }

  async function loadBrokerFeePresets() {
    try {
      const res = await fetch(URL, { cache: 'no-store' });
      const data = res.ok ? await res.json() : {};
      presets = Array.isArray(data.presets) && data.presets.length ? data.presets : FALLBACK;
    } catch (e) { presets = FALLBACK; }
    window.MM_BROKER_FEE_PRESETS = presets;
    renderOptions();
  }

  // 현재 선택 시장(멀티계좌 카드 프리셋 문구·submit body용)
  function feeMarket() { return market(); }

  // 전역 노출 (인라인 onchange·페이지 init서 호출)
  window.applyFeePreset = applyFeePreset;
  window.markFeePresetCustom = markFeePresetCustom;
  window.loadBrokerFeePresets = loadBrokerFeePresets;
  window.mmFeeMarket = feeMarket;

  document.addEventListener('DOMContentLoaded', loadBrokerFeePresets);
})();
