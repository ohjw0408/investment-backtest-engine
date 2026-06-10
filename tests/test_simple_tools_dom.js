/**
 * 간편 계산기 jsdom 스모크 — Flask 렌더 HTML에 simple_tools.js 주입.
 * 선행: venv python으로 /simple HTML을 tests/_simple_rendered.html에 저장.
 * 실행: node tests/test_simple_tools_dom.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const html = fs.readFileSync(path.join(__dirname, '_simple_rendered.html'), 'utf8');
const src = fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'simple_tools.js'), 'utf8');

const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => errors.push(String(e)));

const dom = new JSDOM(html, { runScripts: 'outside-only', virtualConsole: vc });
const { window } = dom;
const { document } = window;

// 스크립트 주입 (Chart 미정의 → stDrawChart 가드로 차트만 스킵)
// jsdom 생성자 반환 시점 readyState='loading' → DOMContentLoaded 대기 후 단언
window.eval(src);

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}
function setVal(id, v) {
  const el = document.getElementById(id);
  el.value = String(v);
  el.dispatchEvent(new window.Event('input', { bubbles: true }));
}
function txt(id) { return document.getElementById(id).textContent; }

function runTests() {
// 1. 구조: 패널 4개 + 탭버튼 4개
ok('패널 4개 존재', document.querySelectorAll('.st-panel').length === 4);
ok('탭버튼 4개 존재', document.querySelectorAll('.st-tab-btn').length === 4);

// 2. 초기 렌더: 기본값으로 전 패널 계산 완료 ('—' 없음)
['stCpFinal', 'stCpPrincipal', 'stCpGain', 'stCpReal',
 'stDvFinal', 'stDvCum', 'stDvLastYear', 'stDvMonthlyAvg', 'stDvReal',
 'stInfFuture', 'stInfTotal', 'stRvReal', 'stRvLoss', 'stRvRequired'].forEach(id => {
  ok('초기렌더 ' + id + ' 채워짐', txt(id) !== '—' && txt(id) !== '');
});

// 3. 초기 탭 = compound만 표시
ok('초기탭 compound 표시', document.getElementById('stPanel-compound').style.display !== 'none');
ok('초기탭 dividend 숨김', document.getElementById('stPanel-dividend').style.display === 'none');

// 4. 탭 전환
document.querySelector('.st-tab-btn[data-tab="dividend"]').click();
ok('탭전환 dividend 표시', document.getElementById('stPanel-dividend').style.display !== 'none');
ok('탭전환 compound 숨김', document.getElementById('stPanel-compound').style.display === 'none');
ok('탭전환 active 클래스', document.querySelector('.st-tab-btn[data-tab="dividend"]').classList.contains('active'));

// 5. 복리: 거치식 손계산 일치 — 초기 1,000만·월0·7%·10년 → 19,671,513 → "₩1,967만"
setVal('stCpMonthly', 0);
setVal('stCpReturn', 7);
setVal('stCpYears', 10);
setVal('stCpInitial', 10000000);
ok('복리 거치식 표시값 = ₩1,967만', txt('stCpFinal') === '₩1,967만');
ok('복리 거치식 원금 = ₩1,000만', txt('stCpPrincipal') === '₩1,000만');

// 6. 복리 과세 토글 → 값 감소 (세후 17,777,133 → ₩1,777만)
const cpTaxed = document.getElementById('stCpTaxed');
cpTaxed.checked = true;
cpTaxed.dispatchEvent(new window.Event('change', { bubbles: true }));
ok('복리 과세 ON = ₩1,777만', txt('stCpFinal') === '₩1,777만');
cpTaxed.checked = false;
cpTaxed.dispatchEvent(new window.Event('change', { bubbles: true }));
ok('복리 과세 OFF 복귀 = ₩1,967만', txt('stCpFinal') === '₩1,967만');

// 7. 복리 표: 10년 → 헤더 + 10행
ok('복리 표 10행', document.querySelectorAll('#stCpTable tr').length === 11);

// 8. 배당: 거치식 1년·분기·비과세·yield4%·성장0% → 10,406,040 → "₩1,040만"
setVal('stDvMonthly', 0);
setVal('stDvInitial', 10000000);
setVal('stDvYield', 4);
setVal('stDvGrowth', 0);
setVal('stDvYears', 1);
setVal('stDvIncrease', 0);
const dvTaxed = document.getElementById('stDvTaxed');
dvTaxed.checked = false;
dvTaxed.dispatchEvent(new window.Event('change', { bubbles: true }));
ok('배당 분기복리 1년 = ₩1,040만', txt('stDvFinal') === '₩1,040만');
ok('배당 누적배당 = ₩40만', txt('stDvCum') === '₩40만');

// 9. 배당 주기 라디오: 월배당 전환 → 재계산 (1억: 분기 1억406만 vs 월 1억407만)
setVal('stDvInitial', 100000000);
const quarterlyTxt = txt('stDvFinal');
const monthlyRadio = document.querySelector('input[name="stDvFreq"][value="monthly"]');
monthlyRadio.checked = true;
monthlyRadio.dispatchEvent(new window.Event('change', { bubbles: true }));
ok('배당 월배당 전환시 재계산', txt('stDvFinal') !== quarterlyTxt && txt('stDvFinal') === '₩1억 407만');

// 10. 인플레 생활비: 300만·2.5%·20년 → 4,915,849 → "₩491만"
setVal('stInfCost', 3000000);
setVal('stInfRate', 2.5);
setVal('stInfYears', 20);
ok('인플레 미래생활비 = ₩491만', txt('stInfFuture') === '₩491만');
ok('인플레 표 20행', document.querySelectorAll('#stInfTable tr').length === 21);

// 11. 실질 구매력: 1억·2.5%·20년 → 61,027,094 → "₩6,102만", 하락 39.0%
setVal('stRvAmount', 100000000);
setVal('stRvRate', 2.5);
setVal('stRvYears', 20);
ok('실질가치 = ₩6,102만', txt('stRvReal') === '₩6,102만');
ok('하락률 = 39.0%', txt('stRvLoss') === '39.0%');
ok('필요명목 = ₩1억 6,386만', txt('stRvRequired') === '₩1억 6,386만');

// 12. 런타임 에러 0
ok('jsdom 런타임 에러 0', errors.length === 0);
if (errors.length) console.log(errors.join('\n'));

console.log(`\n${pass} PASS / ${fail} FAIL`);
process.exit(fail ? 1 : 0);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => setTimeout(runTests, 0));
} else {
  setTimeout(runTests, 0);
}
