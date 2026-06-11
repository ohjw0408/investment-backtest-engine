/** GAP-RET-KRDATA 조사 — 라이브 C1 구성(sim 멀티) API 직접 호출. 읽기성 시뮬만. */
'use strict';

const BASE = process.argv[2] || 'https://moneymilestone.duckdns.org';

const BODY = {
  tickers: [{ code: '458730', name: 'TIGER 미국배당다우존스', weight: 1.0 }],
  initial_capital: 10000000,
  monthly_contribution: 500000,
  accumulation_years: 20,
  dividend_mode: 'reinvest',
  rebal_mode: 'none',
  band_width: 0.05,
  monthly_withdrawal: 3000000,
  withdrawal_years: 30,
  inflation: 0.02,
  pension_start_age: 65,
  target_percentile: 0.90,
  tax_enabled: true,
  account_type: '위탁',
  isa_renewal: false,
  gain_harvesting: false,
  user_settings: { age: 40, earned_income: 50000000, isa_type: 'general', pension_age: 65 },
  accounts: [
    { type: '위탁', initial_capital: 10000000, monthly_contribution: 500000,
      tickers: [{ code: '458730', name: 'TIGER 미국배당다우존스', weight: 1.0 }],
      rebal_mode: 'none', band_width: 0.05, dividend_mode: 'reinvest', isa_renewal: false, priority: 1 },
    { type: '연금저축', initial_capital: 0, monthly_contribution: 500000,
      tickers: [{ code: '360750', name: 'TIGER 미국S&P500', weight: 1.0 }],
      rebal_mode: 'none', band_width: 0.05, dividend_mode: 'reinvest', isa_renewal: false, priority: 2 },
  ],
  distribution_policy: { destinations: [{ account_id: 0 }, { account_id: 1 }] },
  reinvest_tax_credit: true,
  manual_comprehensive_years: [],
};

const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const sub = await fetch(BASE + '/api/retirement/submit', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(BODY),
  });
  const { task_id, error } = await sub.json();
  if (!task_id) throw new Error('submit 실패: ' + error);
  console.log('task:', task_id);

  const t0 = Date.now();
  while (Date.now() - t0 < 240000) {
    await sleep(2000);
    const r = await fetch(`${BASE}/api/task/${task_id}`).then(x => x.json());
    if (r.status === 'SUCCESS') {
      const d = r.result;
      console.log(JSON.stringify({
        combined_summary: d.combined_summary,
        accumulation_p50: d.accumulation_summary && d.accumulation_summary.end_value,
        acc_cases: d.acc_cases_count,
        data_start: d.data_start,
        withdrawal_pending: d.withdrawal_pending,
        multi_enabled: (d.multi_account || {}).enabled,
      }, null, 2));
      return;
    }
    if (r.status === 'FAILURE') { console.log('FAILURE:', r.error); return; }
  }
  console.log('타임아웃');
})().catch(e => { console.error(e.message); process.exit(1); });
