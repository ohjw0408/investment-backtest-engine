/** D. 인출기(/retirement wd 모드) — D1~D4 (계획 §5.D) */
'use strict';

module.exports = async function runD(ctx) {
  const { page, dialogs, H } = ctx;
  const { num, fmtMan } = H;

  // D2 구성 빌더 — 위탁(3억, 미실현 g) + 연금저축(2억, 360750), 월인출 200만, 30년, 수령 65세.
  async function buildD2(unrealizedGain) {
    await H.gotoPage(page, 'ret');
    await H.addTopTicker(page, 'ret', '458730');
    await page.click('#tabRetWd');
    await H.setTax(page, 'ret', true);
    await H.addAccount(page);
    await H.setAccountType(page, 1, '연금저축');
    await page.fill('#wdSeed', '300000000');
    await H.setAccountAmount(page, 0, '미실현 차익', unrealizedGain);
    await H.setAccountAmount(page, 1, '시작 목돈', 200000000);
    await H.addAccountTicker(page, 1, '360750');
    await page.fill('#wdWithdraw', '2000000');
    await H.setRange(page, '#wdYearsSlider', 30);
    await page.fill('#wdPensionStartAge', '65');
  }

  function metrics(r) {
    return {
      surv: ((r || {}).combined_summary || {}).survival_rate,
      comb: (((r || {}).combined_summary || {}).combined_end_value || {}).p50,
      pension: (r || {}).median_pension_tax,
    };
  }

  // ── D1: wd 모드 UI 전환 (월적립 숨김·시작목돈·위탁 미실현칸) ──
  try {
    await H.gotoPage(page, 'ret');
    await H.addTopTicker(page, 'ret', '458730');
    await page.click('#tabRetWd');
    await H.setTax(page, 'ret', true);
    await H.addAccount(page);                       // 계좌 2개 (계좌1 위탁 + 계좌2)
    await H.setAccountType(page, 1, '연금저축');

    const card0 = H.accountCard(page, 0);
    const card1 = H.accountCard(page, 1);
    const card0Unreal = await card0.locator('label:has-text("미실현 차익")').count();
    const card1Monthly = await card1.locator('label:has-text("월 적립액")').count();
    const card1Seed = await card1.locator('label:has-text("시작 목돈")').count();
    const card0Text = (await card0.textContent()) || '';
    await H.shot(page, 'd1_wd_mode_ui');

    const pass = card0Unreal === 1 && card1Monthly === 0 && card1Seed === 1
      && card0Text.includes('시작 목돈');
    H.record('D1', '인출기 모드 UI 전환(G5-D 배선)', pass ? 'PASS' : 'FAIL',
      `계좌1 미실현칸=${card0Unreal} 계좌2 월적립칸=${card1Monthly}(0이어야) 시작목돈칸=${card1Seed} `
      + `계좌1 시작목돈 라벨=${card0Text.includes('시작 목돈')}`);
  } catch (e) {
    await H.shot(page, 'd1_FAIL');
    H.record('D1', '인출기 모드 UI 전환(G5-D 배선)', 'FAIL', e.message);
  }

  // ── D2: 멀티 인출 실행 (미실현 1억 + 연금소득세 표시) ──
  try {
    await buildD2(100000000);
    const res = await H.withRetry(() => H.runSim(page, 'ret', { dialogs }), 'D2');
    if (!res.ok) throw new Error('시뮬 실패: ' + res.error);
    const r = res.result;
    const m = metrics(r);
    const ma = r.multi_account || {};
    const accounts = ma.accounts || [];
    const distOk = accounts.length === 2 && accounts.every(a => num((a.distribution || {}).end_value?.p50));

    const uiVisible = await page.isVisible('#multiAccountSummary');
    const pensionVisible = await page.isVisible('#retWdPensionTax');
    const pensionText = pensionVisible ? (await page.textContent('#retWdPensionTax')) : '';
    await H.shot(page, 'd2_wd_multi');

    const pass = ma.enabled === true && distOk && num(m.surv) && m.surv > 0 && m.surv <= 1
      && num(m.pension) && m.pension > 0
      && uiVisible && pensionVisible && pensionText.includes('연금소득세');
    H.record('D2', '인출기 멀티 실행+연금소득세', pass ? 'PASS' : 'FAIL',
      `enabled=${ma.enabled} accounts=${accounts.length} survival=${Math.round((m.surv || 0) * 100)}% `
      + `연금소득세(중앙값)=${fmtMan(m.pension)}/년 combined_p50=${fmtMan(m.comb)} `
      + `UI(멀티/연금세)=${uiVisible}/${pensionVisible}`);
  } catch (e) {
    await H.shot(page, 'd2_FAIL');
    H.record('D2', '인출기 멀티 실행+연금소득세', 'FAIL', e.message);
  }

  // ── D3: 세금 ON vs OFF (생존율 ON ≤ OFF) ──
  // ⚠ 계획은 "D2 구성 ON/OFF"지만 OFF는 accounts 미부착 → 총목돈 3억≠5억 불공정 비교.
  //   단일계좌(위탁 3억, 월인출 200만) 대조로 대체 — 인출세 부담 방향성은 동일하게 검증. 결과에 명시.
  try {
    await H.gotoPage(page, 'ret');
    await H.addTopTicker(page, 'ret', '458730');
    await page.click('#tabRetWd');
    await page.fill('#wdSeed', '300000000');
    await page.fill('#wdWithdraw', '2000000');
    await H.setRange(page, '#wdYearsSlider', 30);
    await H.setTax(page, 'ret', true);              // 계좌1 = 위탁(기본) 단일

    const resOn = await H.withRetry(() => H.runSim(page, 'ret', { dialogs }), 'D3-ON');
    if (!resOn.ok) throw new Error('ON 시뮬 실패: ' + resOn.error);
    const on = metrics(resOn.result);

    await H.setTax(page, 'ret', false);
    const resOff = await H.withRetry(() => H.runSim(page, 'ret', { dialogs }), 'D3-OFF');
    if (!resOff.ok) throw new Error('OFF 시뮬 실패: ' + resOff.error);
    const off = metrics(resOff.result);

    const pass = num(on.surv) && num(off.surv) && on.surv <= off.surv;
    H.record('D3', '인출기 세금 ON ≤ OFF (생존율)', pass ? 'PASS' : 'FAIL',
      `생존율 ON=${Math.round((on.surv || 0) * 100)}% OFF=${Math.round((off.surv || 0) * 100)}% `
      + `combined_p50 ON=${fmtMan(on.comb)} OFF=${fmtMan(off.comb)} `
      + `(계획의 D2구성 대신 단일계좌 대조 — OFF는 계좌2 미부착이라 총목돈 불일치)`);
  } catch (e) {
    H.record('D3', '인출기 세금 ON ≤ OFF (생존율)', 'FAIL', e.message);
  }

  // ── D4: 미실현차익 방향성 (0 vs 2억 → 양도세↑ = 결과 악화) ──
  try {
    await buildD2(0);
    const res0 = await H.withRetry(() => H.runSim(page, 'ret', { dialogs }), 'D4-0');
    if (!res0.ok) throw new Error('미실현 0 시뮬 실패: ' + res0.error);
    const m0 = metrics(res0.result);

    await buildD2(200000000);
    const res2 = await H.withRetry(() => H.runSim(page, 'ret', { dialogs }), 'D4-2억');
    if (!res2.ok) throw new Error('미실현 2억 시뮬 실패: ' + res2.error);
    const m2 = metrics(res2.result);
    await H.shot(page, 'd4_unrealized_2uk');

    // 악화 = combined 종료자산 하락 또는 생존율 하락(계획 PASS 기준 그대로)
    const combWorse = num(m0.comb) && num(m2.comb) && m2.comb < m0.comb;
    const survWorse = num(m0.surv) && num(m2.surv) && m2.surv < m0.surv;
    const pass = combWorse || survWorse;
    H.record('D4', '미실현차익 방향성(0 vs 2억)', pass ? 'PASS' : 'FAIL',
      `combined_p50 0=${fmtMan(m0.comb)} 2억=${fmtMan(m2.comb)} `
      + `생존율 0=${Math.round((m0.surv || 0) * 100)}% 2억=${Math.round((m2.surv || 0) * 100)}% `
      + `→ 종료자산악화=${combWorse} 생존율악화=${survWorse}`);
  } catch (e) {
    await H.shot(page, 'd4_FAIL');
    H.record('D4', '미실현차익 방향성(0 vs 2억)', 'FAIL', e.message);
  }
};
