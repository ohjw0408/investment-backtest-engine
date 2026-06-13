/**
 * D4 fast-follow ① 계좌별 거래수수료 카드 UI jsdom 스모크 — multi_account_ui.js 단독 주입.
 * fee 헬퍼(_mmFeeField/_mmAccountFeePct/update*)만 호출(renderTaxAccounts 전체 의존성 회피).
 * 실행: node tests/test_fee_card_dom.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const src = fs.readFileSync(
  path.join(__dirname, '..', 'static', 'js', 'multi_account_ui.js'), 'utf8');

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}

// feeEnabledChk(opt-in) + feeRateInput(탭레벨 시드) DOM 제공.
function makeDom(feeOn, tabRate) {
  const vc = new VirtualConsole();
  vc.on('jsdomError', () => {});
  const dom = new JSDOM(
    `<body>
       <input type="checkbox" id="feeEnabledChk" ${feeOn ? 'checked' : ''}>
       <input type="number" id="feeRateInput" value="${tabRate}">
     </body>`,
    { runScripts: 'outside-only', virtualConsole: vc });
  const w = dom.window;
  w.eval(src);
  return w;
}

// ── 1. fee OFF → 카드에 필드 미표시(타 탭/미배선 보호) ──
{
  const w = makeDom(false, '0.015');
  w.taxAccounts = [{ type: '위탁' }];
  ok('fee OFF → _mmFeeField 빈 문자열', w._mmFeeField(w.taxAccounts[0], 0) === '');
}

// ── 2. fee ON → 프리셋 select + 수수료율 입력 렌더, 탭레벨 시드 기본값 ──
{
  const w = makeDom(true, '0.02');
  w.taxAccounts = [{ type: '위탁' }];          // 계좌 자체 fee_rate_pct 미지정
  const html = w._mmFeeField(w.taxAccounts[0], 0);
  ok('fee ON → 수수료율 입력 id 포함', html.includes('id="accountFeeRate0"'));
  ok('fee ON → 직접입력 옵션 포함', html.includes('직접입력'));
  ok('미지정 계좌 기본값 = 탭레벨 시드(0.02)', html.includes('value="0.02"'));
  ok('탭 시드 0.02 = 삼성 프리셋 selected', /value="0\.02"\s+selected/.test(html));
}

// ── 3. _mmAccountFeePct: 계좌 지정값 우선, 없으면 탭레벨 ──
{
  const w = makeDom(true, '0.015');
  ok('미지정 → 탭레벨(0.015)', w._mmAccountFeePct({ type: '위탁' }) === 0.015);
  ok('지정값 우선(0)', w._mmAccountFeePct({ fee_rate_pct: 0 }) === 0);
  ok('지정값 우선(0.03)', w._mmAccountFeePct({ fee_rate_pct: 0.03 }) === 0.03);
}

// ── 4. updateAccountFeeRate: 상태 갱신(음수 클램프) + 프리셋 select 동기화 ──
{
  const w = makeDom(true, '0.015');
  w.taxAccounts = [{ type: '위탁' }, { type: 'ISA' }];
  // 프리셋 select DOM(렌더된 카드 모사) — 동기화 확인용
  const sel = w.document.createElement('select');
  sel.id = 'accountFeePreset1';
  ['0.015', '0.02', '0', 'custom'].forEach(v => {
    const o = w.document.createElement('option'); o.value = v; sel.appendChild(o);
  });
  sel.value = '0.015';
  w.document.body.appendChild(sel);

  w.updateAccountFeeRate(1, '0.025');
  ok('직접입력 → 계좌 상태 갱신', w.taxAccounts[1].fee_rate_pct === 0.025);
  ok('비프리셋 율 → 프리셋 select=직접입력', sel.value === 'custom');
  w.updateAccountFeeRate(1, '0.02');
  ok('프리셋 일치 율 → 프리셋 select=해당 증권사', sel.value === '0.02');
  w.updateAccountFeeRate(1, '-5');
  ok('음수 입력 → 0 클램프', w.taxAccounts[1].fee_rate_pct === 0);
  ok('타 계좌 미영향', w.taxAccounts[0].fee_rate_pct === undefined);
}

// ── 5. updateAccountFeePreset: 상태 + 입력칸 DOM 동기화, custom은 무변경 ──
{
  const w = makeDom(true, '0.015');
  w.taxAccounts = [{ type: '위탁' }];
  // 입력칸 DOM 추가(렌더된 카드 모사)
  const inp = w.document.createElement('input');
  inp.id = 'accountFeeRate0';
  inp.value = '0.015';
  w.document.body.appendChild(inp);
  w.updateAccountFeePreset(0, '0');                 // 토스 0%
  ok('프리셋 → 계좌 상태 갱신', w.taxAccounts[0].fee_rate_pct === 0);
  ok('프리셋 → 입력칸 DOM 동기화', inp.value === '0');
  w.updateAccountFeePreset(0, 'custom');            // 직접입력 = 무변경
  ok('custom 프리셋 → 상태 무변경', w.taxAccounts[0].fee_rate_pct === 0);
}

console.log(`\n${pass} PASS / ${fail} FAIL`);
process.exit(fail ? 1 : 0);
