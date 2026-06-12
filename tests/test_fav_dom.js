/**
 * 포트폴리오 즐겨찾기 위젯(B1) jsdom 스모크 — portfolio_favorites.js 단독 주입.
 * fetch/prompt/confirm/alert 전부 스텁. 실행: node tests/test_fav_dom.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const src = fs.readFileSync(
  path.join(__dirname, '..', 'static', 'js', 'portfolio_favorites.js'), 'utf8');

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}

// fetch 스텁 빌더 — 호출 기록 + 라우트별 응답. loggedIn으로 /api/me 자동 응답.
function makeFetch(routes, calls, loggedIn = true) {
  return async (url, opts = {}) => {
    const method = (opts.method || 'GET').toUpperCase();
    calls.push({ url, method, body: opts.body ? JSON.parse(opts.body) : null });
    if (method === 'GET' && url.startsWith('/api/me')) {
      return { ok: true, status: 200, json: async () => ({ logged_in: loggedIn }) };
    }
    for (const r of routes) {
      if (r.method === method && url.startsWith(r.prefix)) {
        return { ok: r.status < 400, status: r.status, json: async () => r.json() };
      }
    }
    throw new Error('unexpected fetch ' + method + ' ' + url);
  };
}

function makeDom() {
  const vc = new VirtualConsole();
  vc.on('jsdomError', () => {});
  const dom = new JSDOM('<body><div id="favBar"></div></body>',
    { runScripts: 'outside-only', virtualConsole: vc });
  return dom.window;
}

async function flush() {
  for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 0));
}

(async () => {

  // ── 1. 비로그인: select 비활성 + 안내 문구 ──
  {
    const w = makeDom();
    const calls = [];
    w.fetch = makeFetch([], calls, false);   // 비로그인 — /api/me만 호출되고 list 미호출
    w.eval(src);
    w.MMFav.init({ mount: 'favBar', getTickers: () => [], setTickers: () => {} });
    await flush();
    ok('비로그인 list 미호출 (401 노이즈 방지)', !calls.some(c => c.url.startsWith('/api/portfolio/list')));
    const sel = w.document.querySelector('.fav-select');
    ok('비로그인 select 비활성', sel.disabled === true);
    ok('비로그인 안내 문구', sel.options[0].textContent.includes('로그인'));

    let alerted = '';
    w.alert = (m) => { alerted = m; };
    w.document.querySelector('.fav-btn').click();
    ok('비로그인 저장 클릭 → 로그인 안내', alerted.includes('로그인'));
  }

  // ── 2. 로그인 + 목록: 옵션 렌더 + 불러오기 → setTickers ──
  {
    const w = makeDom();
    const items = [
      { id: 1, name: '성장형', tickers: [{ code: '069500', name: 'KODEX 200', badge: 'KR ETF', weight: 60 }] },
      { id: 2, name: '<b>주입</b>', tickers: [{ code: 'SPY', name: 'SPY', badge: 'US ETF', weight: 100 }] },
    ];
    const calls = [];
    w.fetch = makeFetch([{ method: 'GET', prefix: '/api/portfolio/list', status: 200, json: () => items }], calls);
    w.eval(src);
    let received = null;
    w.MMFav.init({ mount: 'favBar', getTickers: () => [], setTickers: (l) => { received = l; } });
    await flush();
    const sel = w.document.querySelector('.fav-select');
    ok('로그인 select 활성', sel.disabled === false);
    ok('옵션 = 플레이스홀더 + 2개', sel.options.length === 3);
    ok('이름 XSS 무해 (textContent)', sel.options[2].textContent === '<b>주입</b>'
       && sel.querySelector('b') === null);

    sel.value = '1';
    sel.dispatchEvent(new w.Event('change', { bubbles: true }));
    ok('불러오기 → setTickers 호출', received && received.length === 1 && received[0].code === '069500');
    received[0].weight = 999;
    ok('불러오기 깊은복사 (원본 불변)', items[0].tickers[0].weight === 60);
  }

  // ── 3. 저장: prompt 이름 → POST payload + 목록 갱신 ──
  {
    const w = makeDom();
    let listData = [];
    const calls = [];
    w.fetch = makeFetch([
      { method: 'GET', prefix: '/api/portfolio/list', status: 200, json: () => listData },
      { method: 'POST', prefix: '/api/portfolio/save', status: 200, json: () => ({ ok: true }) },
    ], calls);
    w.eval(src);
    const mine = [{ code: '458730', name: 'TIGER 미국배당', badge: 'KR ETF', weight: 100 }];
    w.MMFav.init({ mount: 'favBar', getTickers: () => mine, setTickers: () => {} });
    await flush();
    w.prompt = () => ' 배당형 ';
    w.alert = () => {};
    listData = [{ id: 7, name: '배당형', tickers: mine }];
    w.document.querySelector('.fav-btn').click();
    await flush(); await flush();
    const post = calls.find(c => c.method === 'POST');
    ok('저장 POST 발생', !!post);
    ok('저장 payload 이름 trim', post.body.name === '배당형');
    ok('저장 payload 신규 id=null', post.body.id === null);
    ok('저장 payload tickers', post.body.tickers[0].code === '458730');
    const sel = w.document.querySelector('.fav-select');
    ok('저장 후 목록 갱신·선택', sel.value === '7' && sel.options.length === 2);
  }

  // ── 4. 동명 덮어쓰기: confirm + 기존 id로 POST ──
  {
    const w = makeDom();
    const existing = [{ id: 3, name: '성장형', tickers: [{ code: 'SPY', name: 'SPY', badge: '', weight: 100 }] }];
    const calls = [];
    w.fetch = makeFetch([
      { method: 'GET', prefix: '/api/portfolio/list', status: 200, json: () => existing },
      { method: 'POST', prefix: '/api/portfolio/save', status: 200, json: () => ({ ok: true }) },
    ], calls);
    w.eval(src);
    w.MMFav.init({ mount: 'favBar',
      getTickers: () => [{ code: 'QQQ', name: 'QQQ', badge: '', weight: 100 }],
      setTickers: () => {} });
    await flush();
    let confirmed = false;
    w.prompt = () => '성장형';
    w.confirm = () => { confirmed = true; return true; };
    w.alert = () => {};
    w.document.querySelector('.fav-btn').click();
    await flush(); await flush();
    const post = calls.find(c => c.method === 'POST');
    ok('동명 저장 → confirm 표시', confirmed);
    ok('동명 저장 → 기존 id로 덮어쓰기', post && post.body.id === 3);
  }

  // ── 5. 삭제: 선택 필수 + confirm + DELETE ──
  {
    const w = makeDom();
    let listData = [{ id: 5, name: '지울것', tickers: [{ code: 'SPY', name: 'SPY', badge: '', weight: 100 }] }];
    const calls = [];
    w.fetch = makeFetch([
      { method: 'GET', prefix: '/api/portfolio/list', status: 200, json: () => listData },
      { method: 'DELETE', prefix: '/api/portfolio/5', status: 200, json: () => ({ ok: true }) },
    ], calls);
    w.eval(src);
    w.MMFav.init({ mount: 'favBar', getTickers: () => [], setTickers: () => {} });
    await flush();
    let alerted = '';
    w.alert = (m) => { alerted = m; };
    w.confirm = () => true;
    const delBtn = w.document.querySelectorAll('.fav-btn')[1];

    delBtn.click();           // 미선택 상태
    ok('미선택 삭제 → 안내', alerted.includes('선택'));

    const sel = w.document.querySelector('.fav-select');
    sel.value = '5';
    listData = [];
    delBtn.click();
    await flush(); await flush();
    ok('삭제 DELETE 발생', calls.some(c => c.method === 'DELETE' && c.url === '/api/portfolio/5'));
    ok('삭제 후 목록 비움', sel.options.length === 1);
  }

  // ── 6. 빈 구성 저장 차단 ──
  {
    const w = makeDom();
    const calls = [];
    w.fetch = makeFetch([
      { method: 'GET', prefix: '/api/portfolio/list', status: 200, json: () => [] },
    ], calls);
    w.eval(src);
    w.MMFav.init({ mount: 'favBar', getTickers: () => [], setTickers: () => {} });
    await flush();
    let alerted = '';
    w.alert = (m) => { alerted = m; };
    w.document.querySelector('.fav-btn').click();
    ok('빈 구성 저장 → 안내 + POST 없음',
       alerted.includes('종목') && !calls.some(c => c.method === 'POST'));
  }

  console.log(`\n${pass} PASS / ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
})();
