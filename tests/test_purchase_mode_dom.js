/**
 * 추가매수 2모드(구매만 / 구매+리밸런싱) jsdom 스모크 — myassets_page.js 단독 주입.
 * calcPurchase()만 호출(페이지 부트 의존성 회피).
 * 실행: node tests/test_purchase_mode_dom.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const src = fs.readFileSync(
  path.join(__dirname, '..', 'static', 'js', 'myassets_page.js'), 'utf8');

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name + (extra ? '  → ' + extra : '')); }
}

// 추가매수 탭에 필요한 DOM만 제공
function makeDom(amount) {
  const vc = new VirtualConsole();
  vc.on('jsdomError', () => {});
  const dom = new JSDOM(
    `<body>
       <div id="tab-overview"></div>
       <div id="perStockCard"></div>
       <button id="confirmYes"></button>
       <div id="tab-rebalance"></div>
       <div id="tab-groups"></div>
       <div id="tab-purchase">
         <span id="purIntroText"></span>
         <button class="pur-mode active" data-mode="buy"></button>
         <button class="pur-mode" data-mode="rebal"></button>
         <input type="number" id="purchaseAmount" value="${amount}">
         <div id="purchaseResult"></div>
       </div>
     </body>`,
    { runScripts: 'outside-only', virtualConsole: vc });
  const w = dom.window;
  // jsdom 미구현 API — 파일 상단 부트 코드가 참조한다(계산 로직과는 무관)
  w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  // base.html 전역(mmEsc) — 스크립트 단독 주입이라 직접 준다
  w.mmEsc = s => String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // 페이지 전체 부트가 참조하는 수십 개 엘리먼트를 다 만들지 않기 위해, 위 body에 없는 id는
  // 분리된 더미 엘리먼트를 돌려준다. 검증 대상 id(purchaseResult 등)는 실제 DOM에 있으므로
  // 잘못된 id로 쓰면 아래 단언이 그대로 실패한다.
  const realGet = w.document.getElementById.bind(w.document);
  w.document.getElementById = id => realGet(id) || w.document.createElement('div');
  // holdings/groups/prices는 파일 최상단 `let` — eval 지역 바인딩이라 밖에서 대입할 수 없다.
  // 같은 eval 안에 세터를 심어 그 바인딩을 잡는다.
  w.eval(src + `
hideAmounts = false;   // 기본 true라 금액이 ***로 마스킹된다
;window.__setState = o => {
  if ('groups'   in o) groups   = o.groups;
  if ('holdings' in o) holdings = o.holdings;
  if ('prices'   in o) prices   = o.prices;
};`);
  return w;
}

const setState = (w, obj) => w.__setState(obj);

// 주식/채권 2그룹, 목표 60:40
function seed(w, stockVal, bondVal) {
  setState(w, {
    groups: [
      { id: 1, name: '주식', color: '#f00', target_pct: 60 },
      { id: 2, name: '채권', color: '#00f', target_pct: 40 },
    ],
    holdings: [
      { code: 'S', quantity: 1, group_id: 1 },
      { code: 'B', quantity: 1, group_id: 2 },
    ],
    prices: { S: stockVal, B: bondVal },
  });
}

// 렌더된 결과에서 그룹별 금액 파싱 (라벨, 부호 포함 문자열)
function amounts(w) {
  return [...w.document.querySelectorAll('#purchaseResult .pur-row')].map(row => ({
    name: row.querySelector('span:nth-child(2)').textContent,
    txt:  row.querySelector('.pur-buy, .pur-sell').textContent,
    sell: !!row.querySelector('.pur-sell'),
  }));
}
const num = s => parseInt(String(s).replace(/[^0-9]/g, ''), 10);

const M = 10000;   // 만원

// ── 1. 구매만 모드 = 기존 동작(매도 없음) ──
{
  const w = makeDom(200 * M);
  seed(w, 700 * M, 300 * M);
  w.calcPurchase();
  const a = amounts(w);
  ok('buy: 두 그룹 모두 매수', a.length === 2 && a.every(r => !r.sell));
  ok('buy: 주식 +20만', num(a[0].txt) === 20 * M, a[0].txt);
  ok('buy: 채권 +180만', num(a[1].txt) === 180 * M, a[1].txt);
  ok('buy: 합계 = 입력액', num(a[0].txt) + num(a[1].txt) === 200 * M);
}

// ── 2. 구매만 모드 — 한쪽이 크게 초과해도 매도 제안 안 함 ──
{
  const w = makeDom(200 * M);
  seed(w, 900 * M, 100 * M);
  w.calcPurchase();
  const a = amounts(w);
  ok('buy(초과): 매도 행 없음', a.every(r => !r.sell));
  ok('buy(초과): 채권에 전액', a.length === 1 && num(a[0].txt) === 200 * M, JSON.stringify(a));
}

// ── 3. 구매+리밸 모드 — 초과 없음이면 매수만, 목표에 정확히 도달 ──
{
  const w = makeDom(200 * M);
  seed(w, 700 * M, 300 * M);
  w.setPurchaseMode('rebal');
  const a = amounts(w);
  ok('rebal: 매도 0건', a.every(r => !r.sell));
  ok('rebal: 주식 매수 20만', num(a[0].txt) === 20 * M, a[0].txt);
  ok('rebal: 채권 매수 180만', num(a[1].txt) === 180 * M, a[1].txt);
}

// ── 4. 구매+리밸 모드 — 초과 그룹 매도 발생 (오너 확정 시나리오) ──
{
  const w = makeDom(200 * M);
  seed(w, 900 * M, 100 * M);
  w.setPurchaseMode('rebal');
  const a = amounts(w);
  ok('rebal(초과): 주식 매도 180만', a[0].sell && num(a[0].txt) === 180 * M, a[0].txt);
  ok('rebal(초과): 채권 매수 380만', !a[1].sell && num(a[1].txt) === 380 * M, a[1].txt);
  const html = w.document.getElementById('purchaseResult').innerHTML;
  const netTxt = html.slice(html.indexOf('순투입'));
  ok('rebal(초과): 순투입 = 입력액', num(netTxt.slice(0, netTxt.indexOf('</div>'))) === 200 * M,
     netTxt.slice(0, 120));
  ok('rebal(초과): 투입 후 목표 60:40 정확', (900 * M - 180 * M) / (1200 * M) === 0.6);
}

// ── 5. 라운딩 — 합계가 입력 금액과 정확히 일치(원 단위 잔돈 없음) ──
{
  const w = makeDom(1000001);
  seed(w, 3333333, 1111111);
  w.setPurchaseMode('rebal');
  const a = amounts(w);
  const net = a.reduce((s, r) => s + (r.sell ? -num(r.txt) : num(r.txt)), 0);
  ok('rebal: 홀수 금액도 Σdelta = 입력액', net === 1000001, 'net=' + net);

  const w2 = makeDom(1000001);
  seed(w2, 3333333, 1111111);
  w2.calcPurchase();
  const b = amounts(w2);
  const sum = b.reduce((s, r) => s + num(r.txt), 0);
  ok('buy: 홀수 금액도 Σbuy = 입력액', sum === 1000001, 'sum=' + sum);
}

// ── 6. 모드 전환이 안내문·활성칩을 바꾼다 ──
{
  const w = makeDom(200 * M);
  seed(w, 700 * M, 300 * M);
  w.setPurchaseMode('rebal');
  ok('전환: rebal 칩 active',
     w.document.querySelector('[data-mode="rebal"]').classList.contains('active') &&
     !w.document.querySelector('[data-mode="buy"]').classList.contains('active'));
  ok('전환: 안내문 리밸 문구', /동시에 리밸런싱/.test(w.document.getElementById('purIntroText').innerHTML));
  w.setPurchaseMode('buy');
  ok('복귀: buy 칩 active', w.document.querySelector('[data-mode="buy"]').classList.contains('active'));
  ok('복귀: 안내문 매도없이 문구', /매도 없이/.test(w.document.getElementById('purIntroText').innerHTML));
}

// ── 7. 목표비중 미설정 / 금액 0 가드는 두 모드 모두 유지 ──
{
  const w = makeDom(200 * M);
  setState(w, { groups: [], holdings: [], prices: {} });
  w.setPurchaseMode('rebal');
  ok('가드: 목표 없으면 빈 상태', /목표 비중이 필요해요/.test(w.document.getElementById('purchaseResult').innerHTML));

  const w2 = makeDom(0);
  seed(w2, 700 * M, 300 * M);
  w2.setPurchaseMode('rebal');
  ok('가드: 금액 0이면 안내', /투자 금액을 입력하면/.test(w2.document.getElementById('purchaseResult').innerHTML));
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
