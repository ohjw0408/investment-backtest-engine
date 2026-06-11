const { JSDOM } = require('jsdom');
const fs = require('fs');
const dom = new JSDOM(`<!DOCTYPE html><body><div id="multiAccountSummary"></div></body>`, { runScripts: 'outside-only' });
global.window = dom.window; global.document = dom.window.document;
window.MMTAX = { mode: 'withdrawal' };
global.fmtKRW = v => '₩' + Math.round(v).toLocaleString();
window.taxAccounts = [];
const src = fs.readFileSync('static/js/multi_account_ui.js', 'utf8');
dom.window.eval(`window.fmtKRW = v => '₩' + Math.round(v).toLocaleString();`);
dom.window.eval(src);
dom.window.eval(`
renderMultiAccountSummary(
  { enabled: true, accounts: [
      { account_id: 0, type: '위탁', distribution: { end_value: { p10: 1e8, p50: 2e8, p90: 3e8 } } },
      { account_id: 1, type: '연금저축', distribution: { end_value: { p10: 1e8, p50: 1.5e8, p90: 2e8 } } },
  ]},
  null,
  { combined: { brokerage_assumed_tax: 33693167, actual_tax: 27389289, tax_saving: 6303878, gain_harvest_saving: 0 },
    accounts: [
      { account_id: 0, type: '위탁', brokerage_assumed_tax: 27389289, actual_tax: 27389289, tax_saving: 0, gain_harvest_saving: 0 },
      { account_id: 1, type: '연금저축', brokerage_assumed_tax: 6303878, actual_tax: 0, tax_saving: 6303878, gain_harvest_saving: 0 },
    ]},
  false
);
`);
const html = dom.window.document.getElementById('multiAccountSummary').innerHTML;
const checks = {
  savingsPanel: html.includes('세금 절감 효과'),
  saving630: html.includes('₩6,303,878'),
  wdNote: html.includes('연금소득세 포함'),
  accountRow: html.includes('연금저축'),
};
console.log(JSON.stringify(checks));
const pass = Object.values(checks).every(Boolean);
console.log(pass ? 'DOM PASS' : 'DOM FAIL');
process.exit(pass ? 0 : 1);
