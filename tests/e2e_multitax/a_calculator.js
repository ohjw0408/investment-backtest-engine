/** A. 투자계산기(/calculator) — A1~A6 (계획 §5.A) */
'use strict';

module.exports = async function runA(ctx) {
  const { page, dialogs, H } = ctx;
  const { num, fmtMan } = H;

  let a1MaturityCount = null;
  let a1OnP50 = null;

  // 공통 빌더: 상단 458730 · 초기 1천만 · 월 100만 · 12년 · 세금ON · 계좌1=ISA(풍차)
  async function buildBase() {
    await H.gotoPage(page, 'calc');
    await H.addTopTicker(page, 'calc', '458730');
    await page.fill('#initialCapital', '10000000');
    await page.fill('#monthlyContrib', '1000000');
    await H.setRange(page, '#yearsSlider', 12);
    await H.setTax(page, 'calc', true);
    await H.setAccountType(page, 0, 'ISA');
    await page.check('#isaRenewalCheck');
  }

  // ── A1: 멀티 기본 + 절세액 ──────────────────────────────
  try {
    await buildBase();
    await H.addAccount(page);                       // 계좌2 = 위탁(0,0)
    await H.setAccountType(page, 1, '위탁');
    await H.setAccountPriority(page, 0, 1);
    await H.setAccountPriority(page, 1, 2);
    await H.addAccountTicker(page, 1, '360750');    // 페이로드 요건: 계좌2 종목 ≥1

    const res = await H.withRetry(() => H.runSim(page, 'calc', { dialogs }), 'A1');
    if (!res.ok) throw new Error('시뮬 실패: ' + res.error);
    const r = res.result;

    const ma = r.multi_account || {};
    const accounts = ma.accounts || [];
    const distOk = accounts.length === 2 && accounts.every(a => {
      const d = (a.distribution || {}).end_value || {};
      return num(d.p10) && num(d.p50) && num(d.p90);
    });
    const sv = (r.savings || {}).combined || {};
    const saving = (sv.tax_saving || 0) + (sv.gain_harvest_saving || 0);
    const tl = ((r.g2 || {}).transfer_log) || [];
    a1MaturityCount = tl.filter(t => t.type === 'maturity').length;
    a1OnP50 = ((r.distribution || {}).end_value || {}).p50;

    const uiVisible = await page.isVisible('#multiAccountSummary');
    const uiText = uiVisible ? (await page.textContent('#multiAccountSummary')) : '';
    await H.shot(page, 'a1_calculator_multi');

    const pass = ma.enabled === true && distOk && saving >= 0
      && uiText.includes('계좌 2') && uiText.includes('절세액')
      && a1MaturityCount >= 3 && uiText.includes('풍차 만기');
    H.record('A1', '계산기 멀티 기본+절세액', pass ? 'PASS' : 'FAIL',
      `enabled=${ma.enabled} accounts=${accounts.length} `
      + `p50=[${accounts.map(a => fmtMan(a.distribution?.end_value?.p50)).join(', ')}] `
      + `절세=${fmtMan(saving)} 풍차만기=${a1MaturityCount}회 UI(계좌2/절세액/풍차)=${uiText.includes('계좌 2')}/${uiText.includes('절세액')}/${uiText.includes('풍차 만기')}`);
  } catch (e) {
    await H.shot(page, 'a1_FAIL');
    H.record('A1', '계산기 멀티 기본+절세액', 'FAIL', e.message);
  }

  // ── A2: 세금 ON ≤ OFF (combined p50) + A6: OFF시 패널 미표시 ──
  // A1 런 = ON. 같은 구성 토글 OFF 1회 실행 — A6 UI 검증도 이 런으로(라이브 부하 절감).
  try {
    if (a1OnP50 == null) throw new Error('A1 결과 없음(선행 실패)');
    await H.setTax(page, 'calc', false);
    const res = await H.withRetry(() => H.runSim(page, 'calc', { dialogs }), 'A2');
    if (!res.ok) throw new Error('시뮬 실패: ' + res.error);
    const offP50 = ((res.result || {}).distribution || {}).end_value?.p50;
    const pass = num(offP50) && a1OnP50 <= offP50;
    H.record('A2', '세금 ON ≤ OFF (combined p50)', pass ? 'PASS' : 'FAIL',
      `ON=${fmtMan(a1OnP50)} OFF=${fmtMan(offP50)}`);

    const maVisible = await page.isVisible('#multiAccountSummary');
    const distP50Txt = ((await page.textContent('#distP50').catch(() => '')) || '').trim();
    await H.shot(page, 'a6_calculator_tax_off');
    H.record('A6', '세금 OFF 대조(멀티/절세 패널 미표시)',
      (!maVisible && distP50Txt && distP50Txt !== '—') ? 'PASS' : 'FAIL',
      `멀티패널표시=${maVisible} distP50="${distP50Txt}" (A2의 OFF 런 재사용)`);
  } catch (e) {
    H.record('A2', '세금 ON ≤ OFF (combined p50)', 'FAIL', e.message);
    H.record('A6', '세금 OFF 대조(멀티/절세 패널 미표시)', 'SKIP', 'A2 실패로 미검증');
  }

  // ── A3: ISA 초기자본 한도 차단 ──────────────────────────
  try {
    await H.setTax(page, 'calc', true);             // 계좌 2개 유지 상태
    await page.fill('#initialCapital', '21000000'); // ISA 연 납입한도 2,000만 초과
    const res = await H.withRetry(() => H.runSim(page, 'calc', { dialogs }), 'A3');
    const limitBanner = await page.isVisible('#isaLimitErrorBanner');
    const restrictBanner = await page.isVisible('#accountRestrictBanner');
    const bannerText = limitBanner ? (await page.textContent('#isaLimitErrorBanner'))
      : restrictBanner ? (await page.textContent('#accountRestrictBanner')) : '';
    await H.shot(page, 'a3_isa_limit_error');
    const pass = res.ok === false && (limitBanner || restrictBanner) && /한도|2,?000만/.test(bannerText || '');
    H.record('A3', 'ISA 초기자본 한도 차단', pass ? 'PASS' : 'FAIL',
      `task=${res.ok ? 'SUCCESS(차단 안 됨!)' : 'FAILURE'} banner=${limitBanner || restrictBanner} "${(bannerText || '').trim().slice(0, 80)}"`);
  } catch (e) {
    await H.shot(page, 'a3_FAIL');
    H.record('A3', 'ISA 초기자본 한도 차단', 'FAIL', e.message);
  }

  // ── A4: 연금 풀세트 공제 (ISA풍차 + 연금저축 + 위탁) ─────
  try {
    await buildBase();
    await H.addAccount(page);                       // 계좌2 = 연금저축 월50만 360750
    await H.setAccountType(page, 1, '연금저축');
    await H.setAccountAmount(page, 1, '월 적립액', 500000);
    await H.addAccountTicker(page, 1, '360750');
    await H.addAccount(page);                       // 계좌3 = 위탁 458730
    await H.setAccountType(page, 2, '위탁');
    await H.addAccountTicker(page, 2, '458730');
    const reinvestChecked = await page.isChecked('#taxDeductionReinvest');

    const res = await H.withRetry(() => H.runSim(page, 'calc', { dialogs }), 'A4');
    if (!res.ok) throw new Error('시뮬 실패: ' + res.error);
    const r = res.result;
    const g2 = r.g2 || {};
    const ded = g2.annual_deduction_credit || 0;
    const maturity = (g2.transfer_log || []).filter(t => t.type === 'maturity').length;
    const uiText = (await page.isVisible('#multiAccountSummary'))
      ? (await page.textContent('#multiAccountSummary')) : '';
    await H.shot(page, 'a4_pension_fullset');

    const pass = ded > 0 && uiText.includes('연 납입 세액공제 환급')
      && maturity >= 1 && uiText.includes('풍차 만기');
    H.record('A4', '연금 풀세트 공제(ISA+연금저축+위탁)', pass ? 'PASS' : 'FAIL',
      `세액공제환급=${fmtMan(ded)} 풍차만기=${maturity}회 재투자체크=${reinvestChecked} `
      + `UI(공제줄/풍차줄)=${uiText.includes('연 납입 세액공제 환급')}/${uiText.includes('풍차 만기')}`);
  } catch (e) {
    await H.shot(page, 'a4_FAIL');
    H.record('A4', '연금 풀세트 공제(ISA+연금저축+위탁)', 'FAIL', e.message);
  }

  // ── A5: 자동 금종세 풍차중단 (위탁 거액 배당 → 종합과세 연도) ──
  try {
    async function runA5(brokerageInit) {
      await buildBase();
      await H.addAccount(page);                     // 계좌2 = 위탁 거액 458730(배당)
      await H.setAccountType(page, 1, '위탁');
      await H.setAccountAmount(page, 1, '초기 투자금', brokerageInit);
      await H.addAccountTicker(page, 1, '458730');
      const res = await H.withRetry(() => H.runSim(page, 'calc', { dialogs }), 'A5');
      if (!res.ok) throw new Error('시뮬 실패: ' + res.error);
      return res.result;
    }

    let amount = 800_000_000;
    let r = await runA5(amount);
    let comp = ((r.g2 || {}).comprehensive_years) || [];
    if (comp.length === 0) {                        // 임계 미달 → 10억 1회 재시도(계획 §7)
      amount = 1_000_000_000;
      r = await runA5(amount);
      comp = ((r.g2 || {}).comprehensive_years) || [];
    }
    const maturity = ((r.g2 || {}).transfer_log || []).filter(t => t.type === 'maturity').length;
    const uiText = (await page.isVisible('#multiAccountSummary'))
      ? (await page.textContent('#multiAccountSummary')) : '';
    await H.shot(page, 'a5_comprehensive_tax');

    if (comp.length === 0) {
      H.record('A5', '자동 금종세 풍차중단', 'SKIP',
        '8억·10억 모두 금종세 임계 미도달 — 계획 §7에 따라 정상 기록(FAIL 아님)');
    } else {
      const pass = uiText.includes('금융소득종합과세 대상연도')
        && (a1MaturityCount == null || maturity < a1MaturityCount);
      H.record('A5', '자동 금종세 풍차중단', pass ? 'PASS' : 'FAIL',
        `위탁=${fmtMan(amount)} 대상연도=[${comp.join(',')}] 풍차만기=${maturity}회(A1=${a1MaturityCount}회) `
        + `UI표시=${uiText.includes('금융소득종합과세 대상연도')}`);
    }
  } catch (e) {
    await H.shot(page, 'a5_FAIL');
    H.record('A5', '자동 금종세 풍차중단', 'FAIL', e.message);
  }
};
