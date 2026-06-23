/** BUG-WD-MULTI-LIVE 조사 — 라이브 D2 구성 API 직접 호출, n_real/n_synthetic/data_start 캡처. 읽기성 시뮬만. */
'use strict';

const BASE = process.argv[2] || 'https://moneymilestone.co.kr';
const UNREALIZED = process.argv[3] !== undefined ? Number(process.argv[3]) : 100000000;

const BODY = {
  tickers: [{ code: '458730', name: 'TIGER 미국배당다우존스', weight: 1.0 }],
  initial_capital: 300000000,
  monthly_withdrawal: 2000000,
  withdrawal_years: 30,
  inflation: 0.02,
  pension_start_age: 65,
  dividend_mode: 'reinvest',
  rebal_mode: 'none',
  band_width: 0.05,
  target_percentile: 0.90,
  tax_enabled: true,
  account_type: '위탁',
  gain_harvesting: true,
  user_settings: { age: 40, earned_income: 50000000, isa_type: 'general', pension_age: 65 },
  _withdrawal_only: true,
  accounts: [
    { type: '위탁', initial_capital: 300000000, unrealized_gain: UNREALIZED,
      tickers: [{ code: '458730', name: 'TIGER 미국배당다우존스', weight: 1.0 }],
      rebal_mode: 'none', band_width: 0.05, dividend_mode: 'reinvest', priority: 1 },
    { type: '연금저축', initial_capital: 200000000, unrealized_gain: 0,
      tickers: [{ code: '360750', name: 'TIGER 미국S&P500', weight: 1.0 }],
      rebal_mode: 'none', band_width: 0.05, dividend_mode: 'reinvest', priority: 2 },
  ],
  distribution_policy: { destinations: [{ account_id: 0 }, { account_id: 1 }] },
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
        survival_rate: d.survival_rate,
        combined_summary: d.combined_summary,
        median_pension_tax: d.median_pension_tax,
        n_real: d.n_real,
        n_synthetic: d.n_synthetic,
        data_start: d.data_start,
        per_account: (d.multi_account || {}).accounts,
      }, null, 2));
      return;
    }
    if (r.status === 'FAILURE') { console.log('FAILURE:', r.error); return; }
  }
  console.log('타임아웃');
})().catch(e => { console.error(e.message); process.exit(1); });
