/** B. 포트폴리오 분석(/backtest) — B1~B3 (계획 §5.B) */
'use strict';

module.exports = async function runB(ctx) {
  const { page, dialogs, H } = ctx;
  const { num, fmtMan } = H;

  let b1End = null;

  async function buildBase() {
    await H.gotoPage(page, 'bt');
    await H.addTopTicker(page, 'bt', '458730');
    await page.fill('#btSeed', '10000000');
    await page.fill('#btMonthly', '0');
    await page.fill('#btStartDate', '2015-01-01');
    const endVal = await page.inputValue('#btEndDate');
    if (!endVal) await page.fill('#btEndDate', '2026-06-01'); // 기본값 비어있을 때만
    await H.setTax(page, 'bt', true);
  }

  // ── B1: 멀티 2계좌 + 절세 (ISA 1천만 + 위탁 1천만, 458730) ──
  try {
    await buildBase();
    await H.setAccountType(page, 0, 'ISA');
    await H.addAccount(page);
    await H.setAccountType(page, 1, '위탁');
    await H.setAccountAmount(page, 1, '초기 투자금', 10000000);
    await H.addAccountTicker(page, 1, '458730');

    const res = await H.withRetry(() => H.runSim(page, 'bt', { dialogs }), 'B1');
    if (!res.ok) throw new Error('시뮬 실패: ' + res.error);
    const r = res.result;

    const accounts = r.accounts || [];
    const scalarOk = accounts.length === 2 && accounts.every(a => num(a.end_value) && a.end_value > 0);
    b1End = (r.metrics || {}).end_value;
    const sv = (r.savings || {}).combined || {};
    const savingShown = num(sv.brokerage_assumed_tax);
    const uiVisible = await page.isVisible('#btMultiAccountSummary');
    const uiText = uiVisible ? (await page.textContent('#btMultiAccountSummary')) : '';
    await H.shot(page, 'b1_backtest_multi');

    const pass = !!r.multi_account && scalarOk && num(b1End)
      && uiText.includes('계좌별 종료 자산') && uiText.includes('절세액');
    H.record('B1', '백테스트 멀티 2계좌+절세', pass ? 'PASS' : 'FAIL',
      `multi_account=${!!r.multi_account} accounts=${accounts.length} `
      + `end=[${accounts.map(a => fmtMan(a.end_value)).join(', ')}] combined=${fmtMan(b1End)} `
      + `절세필드=${savingShown} UI(계좌별/절세액)=${uiText.includes('계좌별 종료 자산')}/${uiText.includes('절세액')}`);
  } catch (e) {
    await H.shot(page, 'b1_FAIL');
    H.record('B1', '백테스트 멀티 2계좌+절세', 'FAIL', e.message);
  }

  // ── B2: 세금 ON ≤ OFF (combined 종료자산) ──
  // ⚠ 계획은 "B1 구성 ON/OFF"지만 OFF는 accounts 미부착 → 계좌2의 1천만이 빠져 총투입 불일치(불공정 비교).
  //   단일계좌(위탁 1천만) 대조로 대체 — 계획 의도(세금 부담 방향성)는 유지. 결과에 명시.
  try {
    await buildBase();                              // 계좌1 = 위탁(기본) 단일, 세금ON
    const resOn = await H.withRetry(() => H.runSim(page, 'bt', { dialogs }), 'B2-ON');
    if (!resOn.ok) throw new Error('ON 시뮬 실패: ' + resOn.error);
    const onEnd = ((resOn.result || {}).metrics || {}).end_value;

    await H.setTax(page, 'bt', false);
    const resOff = await H.withRetry(() => H.runSim(page, 'bt', { dialogs }), 'B2-OFF');
    if (!resOff.ok) throw new Error('OFF 시뮬 실패: ' + resOff.error);
    const offEnd = ((resOff.result || {}).metrics || {}).end_value;

    const pass = num(onEnd) && num(offEnd) && onEnd <= offEnd;
    H.record('B2', '백테 세금 ON ≤ OFF (종료자산)', pass ? 'PASS' : 'FAIL',
      `ON=${fmtMan(onEnd)} OFF=${fmtMan(offEnd)} `
      + `(계획의 B1구성 대신 단일계좌 대조 — OFF는 계좌2 미부착이라 총투입 불일치)`);
  } catch (e) {
    H.record('B2', '백테 세금 ON ≤ OFF (종료자산)', 'FAIL', e.message);
  }

  // ── B3: 단일 회귀 (위탁 1계좌 세금ON — 멀티 배선이 단일 안 깨뜨림) ──
  try {
    await buildBase();                              // 계좌1 = 위탁(기본), 1개만
    const res = await H.withRetry(() => H.runSim(page, 'bt', { dialogs }), 'B3');
    if (!res.ok) throw new Error('시뮬 실패: ' + res.error);
    const r = res.result;

    const singleOk = !r.multi_account || (r.accounts || []).length <= 1;
    const contentVisible = await page.isVisible('#btResultContent');
    const metricCount = await page.locator('#btMetrics > *').count();
    const maVisible = await page.isVisible('#btMultiAccountSummary');
    const splitGain = r.kr_foreign_unrealized_gain || 0;
    const splitVisible = await page.isVisible('#btSplitSalePanel');
    await H.shot(page, 'b3_backtest_single');

    const pass = singleOk && contentVisible && metricCount > 0 && !maVisible;
    H.record('B3', '백테 단일계좌 회귀', pass ? 'PASS' : 'FAIL',
      `multi_account=${!!r.multi_account} 결과화면=${contentVisible} 지표=${metricCount}개 멀티패널=${maVisible} `
      + `분할매도패널=${splitVisible}(미실현차익 ${fmtMan(splitGain)} — 2천만 초과시에만 표시, 정보성)`);
  } catch (e) {
    await H.shot(page, 'b3_FAIL');
    H.record('B3', '백테 단일계좌 회귀', 'FAIL', e.message);
  }
};
