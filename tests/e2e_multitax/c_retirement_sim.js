/** C. 은퇴 시뮬레이션(/retirement sim 모드) — C1~C3 (계획 §5.C) */
'use strict';

module.exports = async function runC(ctx) {
  const { page, dialogs, H } = ctx;
  const { num, fmtMan } = H;

  let c1Result = null;

  // ── C1: 멀티 적립+인출 투영 (위탁 1천만·월50만 + 연금저축 0·월50만) ──
  try {
    await H.gotoPage(page, 'ret');
    await H.addTopTicker(page, 'ret', '458730');
    await page.fill('#simSeed', '10000000');
    await page.fill('#simMonthly', '500000');
    await H.setTax(page, 'ret', true);
    await H.addAccount(page);                       // 계좌2 = 연금저축 월50만 360750
    await H.setAccountType(page, 1, '연금저축');
    await H.setAccountAmount(page, 1, '월 적립액', 500000);
    await H.addAccountTicker(page, 1, '360750');

    const res = await H.withRetry(() => H.runSim(page, 'ret', { dialogs }), 'C1');
    if (!res.ok) throw new Error('시뮬 실패: ' + res.error);
    const r = res.result;
    c1Result = r;

    const ma = r.multi_account || {};
    const surv = ((r.combined_summary || {}).survival_rate);
    const accP50 = (((r.accumulation_summary || {}).end_value) || {}).p50;
    const uiVisible = await page.isVisible('#multiAccountSummary');
    const uiText = uiVisible ? (await page.textContent('#multiAccountSummary')) : '';
    const survPct = ((await page.textContent('#retSurvivalPct').catch(() => '')) || '').trim();
    await H.shot(page, 'c1_retirement_sim_multi');

    const pass = ma.enabled === true && num(surv) && surv > 0 && surv <= 1
      && num(accP50) && uiText.includes('계좌 2') && /%$/.test(survPct);
    H.record('C1', '은퇴sim 멀티 적립+인출 투영', pass ? 'PASS' : 'FAIL',
      `enabled=${ma.enabled} survival=${num(surv) ? Math.round(surv * 100) + '%' : surv} `
      + `적립p50=${fmtMan(accP50)} UI(계좌2/생존율)=${uiText.includes('계좌 2')}/"${survPct}"`);
  } catch (e) {
    await H.shot(page, 'c1_FAIL');
    H.record('C1', '은퇴sim 멀티 적립+인출 투영', 'FAIL', e.message);
  }

  // ── C2: 세금 ON ≤ OFF (적립 종료자산 p50) ──
  // ⚠ 계획은 "C1 구성 ON/OFF"지만 OFF는 accounts 미부착 → 계좌2 월50만이 빠져 총납입 불일치(불공정 비교).
  //   단일계좌(위탁 1천만·월50만) 대조로 대체 — 계획 의도(세금 부담 방향성)는 유지. 결과에 명시.
  try {
    await H.gotoPage(page, 'ret');
    await H.addTopTicker(page, 'ret', '458730');
    await page.fill('#simSeed', '10000000');
    await page.fill('#simMonthly', '500000');
    await H.setTax(page, 'ret', true);              // 계좌1 = 위탁(기본) 단일

    const resOn = await H.withRetry(() => H.runSim(page, 'ret', { dialogs }), 'C2-ON');
    if (!resOn.ok) throw new Error('ON 시뮬 실패: ' + resOn.error);
    const onAcc = (((resOn.result || {}).accumulation_summary || {}).end_value || {}).p50;
    const onSurv = ((resOn.result || {}).combined_summary || {}).survival_rate;

    await H.setTax(page, 'ret', false);
    const resOff = await H.withRetry(() => H.runSim(page, 'ret', { dialogs }), 'C2-OFF');
    if (!resOff.ok) throw new Error('OFF 시뮬 실패: ' + resOff.error);
    const offAcc = (((resOff.result || {}).accumulation_summary || {}).end_value || {}).p50;
    const offSurv = ((resOff.result || {}).combined_summary || {}).survival_rate;

    const pass = num(onAcc) && num(offAcc) && onAcc <= offAcc;
    H.record('C2', '은퇴sim 세금 ON ≤ OFF (적립 p50)', pass ? 'PASS' : 'FAIL',
      `ON=${fmtMan(onAcc)} OFF=${fmtMan(offAcc)} 생존율 ON/OFF=${Math.round((onSurv || 0) * 100)}%/${Math.round((offSurv || 0) * 100)}% `
      + `(계획의 C1구성 대신 단일계좌 대조 — OFF는 계좌2 미부착이라 총납입 불일치)`);
  } catch (e) {
    H.record('C2', '은퇴sim 세금 ON ≤ OFF (적립 p50)', 'FAIL', e.message);
  }

  // ── C3: 무청산 인계 확인 (BUG-TAX-3 회귀) — C1 응답 재사용 ──
  try {
    if (!c1Result) throw new Error('C1 결과 없음(선행 실패)');
    const jsonStr = JSON.stringify(c1Result);
    const liquidationHit = /liquidat|일괄청산/i.test(jsonStr);
    const surv = ((c1Result.combined_summary || {}).survival_rate);
    const pass = !liquidationHit && num(surv) && surv > 0;
    H.record('C3', '은퇴 무청산 인계(BUG-TAX-3 회귀)', pass ? 'PASS' : 'FAIL',
      `청산세 항목=${liquidationHit ? '발견(!)' : '없음'} survival=${Math.round((surv || 0) * 100)}% `
      + `(한계: API에 청산세 액수 직접 미노출 — 구조+생존율 확인으로 대체, 계획 §5.C3 허용)`);
  } catch (e) {
    H.record('C3', '은퇴 무청산 인계(BUG-TAX-3 회귀)', 'SKIP', e.message);
  }
};
