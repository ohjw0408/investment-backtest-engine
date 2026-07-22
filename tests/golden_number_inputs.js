/**
 * 금액 입력란 콤마 표시 변경의 안전장치 — 골든 마스터.
 *
 * 왜 필요한가
 *   `<input type="number">` 는 콤마를 담을 수 없어서, 화면에 콤마를 보이게 하려면
 *   `type="text"` 로 바꿔야 한다. 그 순간 그 입력란을 읽는 코드가 "1,980,000" 을 받고
 *   `parseFloat` 은 **1** 을 반환한다. 예외도 안 나고 계산도 정상적으로 돌아간다.
 *   결과만 조용히 틀린다 — 읽기 지점을 하나라도 빠뜨리면 그렇게 된다.
 *
 * 무엇을 기록하는가
 *   1) 서버로 나가는 POST 요청 본문 — 입력값이 그대로 반영되므로, 콤마가 숫자를
 *      망가뜨리면 여기서 바로 드러난다. 시세 같은 외부 변동에 오염되지 않는다.
 *   2) 화면에 렌더된 숫자 토큰 — 간편계산기처럼 서버를 안 타는 화면용.
 *
 * 비결정 값 처리
 *   시세·날짜처럼 매번 달라지는 값은 골든이 될 수 없다. 그래서 baseline 을 **2회**
 *   돌려 두 번 다 동일한 항목만 골든으로 채택한다(자동 마스킹).
 *
 * 사용:
 *   node tests/golden_number_inputs.js record   [BASE] [COOKIE]   # 변경 전
 *   node tests/golden_number_inputs.js verify   [BASE] [COOKIE]   # 변경 후
 */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const MODE = process.argv[2] || 'record';
const REST = process.argv.slice(3);
const BASE = REST.find(a => a && a.startsWith('http')) || 'http://127.0.0.1:5000';
const COOKIE = REST.find(a => a && !a.startsWith('http')) || '';
const GOLDEN = path.join(__dirname, 'golden', 'number_inputs.json');
fs.mkdirSync(path.dirname(GOLDEN), { recursive: true });

/* 입력값은 자릿수가 큰 것으로 고정한다. 콤마가 끼면 값이 확 달라져야 탐지가 쉽다
   (1,980,000 을 parseFloat 하면 1 이 되므로 차이가 압도적으로 크게 벌어진다). */
const FILL = {
  money:   '19800000',   // 원
  percent: '7.5',        // %
  years:   '12',         // 년
  age:     '58',         // 세
  qty:     '37',         // 주
};

// 금액(원) 입력란 — 콤마 적용 대상
const MONEY_IDS = [
  'btSeed', 'btMonthly',
  'initialCapital', 'monthlyContrib',
  'dtTargetDiv', 'dtSeedVal', 'dtSeedStep', 'dtMonthlyVal', 'dtMonthlyStep',
  'purchaseAmount', 'holdingAvgPrice', 'manualPriceInput',
  'pdAmount',
  'simSeed', 'simMonthly', 'simWithdraw', 'wdSeed', 'wdWithdraw',
  'earnedIncome',
  'stCpInitial', 'stCpMonthly', 'stDvInitial', 'stDvMonthly',
  'stDgTarget', 'stInfCost', 'stRvAmount',
  'tsCurrentValue', 'tsCostBasis',
];

/* 계산기들은 종목이 0개면 실행 자체가 안 된다(POST 0건). 계산을 안 돌리는 골든
   마스터는 이 변경에 대해 아무것도 보증하지 못하므로, 페이지별 종목 추가 함수를
   직접 호출해 동일한 구성을 심는다. */
const SEED_ASSETS = [
  ['SPY', 'SPDR S&P 500 ETF', 'US ETF'],
  ['TLT', 'iShares 20+ Year Treasury', 'US ETF'],
];

const PAGES = [
  { name: 'calculator', url: '/calculator',      run: '#runBtn',    add: 'addTicker' },
  { name: 'backtest',   url: '/backtest',        run: '#btRunBtn',  add: 'btAddTicker' },
  { name: 'dividend',   url: '/dividend-target', run: '#dtRunBtn',  add: 'dtAddTicker' },
  { name: 'retirement', url: '/retirement',      run: '#retRunBtn', add: 'retAddTicker' },
  { name: 'simple',     url: '/simple',          run: null,         add: null },  // 클라이언트 계산
  /* ISA 전환은 종목 추가 함수가 클로저 안에 있어 직접 호출이 안 된다. 검색 UI 를
     실제로 조작해서 넣는다(uiAdd). 종목이 0개면 '보유 종목을 1개 이상 추가해주세요'
     로 막히고 계산이 아예 돌지 않는다. */
  { name: 'taxswitch',  url: '/tax-switch',      run: '#tsRunBtn',  add: null, wait: 40000,
    uiAdd: { input: '#tsSearchInput', drop: '#tsDropdown .ts-dd-item[data-code]', queries: ['SPY'] } },
];

/** 단위를 문맥에서 추정해 결정론적 값을 넣는다 */
function fillKind(id, step) {
  if (MONEY_IDS.includes(id)) return FILL.money;
  if (step && parseFloat(step) < 1) return FILL.percent;
  if (/age|Age/.test(id)) return FILL.age;
  if (/Qty/.test(id)) return FILL.qty;
  if (/Years|years/.test(id)) return FILL.years;
  return FILL.percent;
}

async function capture(page, p) {
  const posts = [];
  page.on('request', req => {
    if (req.method() !== 'POST') return;
    const body = req.postData();
    if (body) posts.push({ url: req.url().replace(BASE, ''), body });
  });

  try {
    await page.goto(BASE + p.url, { waitUntil: 'networkidle', timeout: 40000 });
  } catch (e) {
    await page.goto(BASE + p.url, { waitUntil: 'domcontentloaded', timeout: 40000 }).catch(() => {});
  }
  await page.waitForTimeout(1200);

  // 종목 시드 — 없으면 계산 버튼이 아무것도 안 한다
  if (p.uiAdd) {
    for (const q of p.uiAdd.queries) {
      await page.fill(p.uiAdd.input, '');
      await page.type(p.uiAdd.input, q, { delay: 40 });
      await page.waitForTimeout(1400);                    // 검색 디바운스 + 응답
      const hit = await page.$(p.uiAdd.drop);   // '검색 결과 없음' 항목에는 data-code 가 없다
      if (hit) { await hit.click().catch(() => {}); await page.waitForTimeout(500); }
    }
  }
  if (p.add) {
    await page.evaluate(([fn, assets]) => {
      if (typeof window[fn] !== 'function') return;
      for (const [c, n, b] of assets) window[fn](c, n, b);
    }, [p.add, SEED_ASSETS]);
    await page.waitForTimeout(400);
    /* 비중은 건드리지 않는다. 첫 종목이 자동으로 100% 가 되므로 그대로 유효하고,
       직접 조작했더니 오히려 상태가 깨져 백테스트가 실행되지 않았다. */
  }

  // 모든 숫자 입력란을 결정론적 값으로 채운다 (type 이 number 든 text 든 동일하게 동작)
  const targets = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('input').forEach(el => {
      const t = (el.type || '').toLowerCase();
      const numericish = t === 'number' || (t === 'text' && el.inputMode &&
        /numeric|decimal/.test(el.inputMode));
      if (!numericish || !el.id) return;
      if (el.offsetParent === null) return;          // 숨겨진 패널은 건너뜀
      out.push({ id: el.id, step: el.getAttribute('step') || '' });
    });
    return out;
  });

  const filled = [];
  for (const t of targets) {
    const val = fillKind(t.id, t.step);
    try {
      await page.fill('#' + t.id, '');
      await page.type('#' + t.id, val, { delay: 0 });   // 실제 타이핑 = 포맷터가 도는 경로
      await page.dispatchEvent('#' + t.id, 'change');
      filled.push({ id: t.id, typed: val });
    } catch (e) { /* 가려졌거나 비활성 */ }
  }
  await page.waitForTimeout(500);

  /* 입력란이 최종적으로 들고 있는 값 — **콤마를 제거한 숫자**로 기록한다.
     원문 그대로 기록하면 콤마 표시를 켠 뒤 "19,800,000" 이 되어 골든과 무조건
     달라지므로 가드가 아니라 잡음이 된다. 여기서 보고 싶은 것은 "자릿수가
     살아있는가"이지 표기 형식이 아니다. */
  const readback = await page.evaluate(ids => {
    const o = {};
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) o[id] = String(el.value).replace(/,/g, '');
    }
    return o;
  }, filled.map(f => f.id));

  if (p.run) {
    try {
      await page.click(p.run, { timeout: 5000 });
      await page.waitForTimeout(p.wait || 8000);   // ISA 전환은 진행바가 있는 장시간 작업
    } catch (e) { /* 버튼 없음 */ }
  } else {
    await page.waitForTimeout(1500);
  }

  // 화면에 렌더된 숫자 토큰
  const rendered = await page.evaluate(() => {
    const txt = document.body.innerText || '';
    return (txt.match(/[₩$]?\s?-?\d[\d,]*(?:\.\d+)?%?/g) || []).slice(0, 400);
  });

  return { filled, readback, posts, rendered };
}

function stableIntersect(a, b) {
  // 두 번의 baseline 에서 동일한 것만 남긴다 (시세·시각 등 비결정 값 제거)
  const out = {};
  for (const k of Object.keys(a)) {
    if (JSON.stringify(a[k]) === JSON.stringify(b[k])) out[k] = a[k];
  }
  return out;
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  if (COOKIE) {
    const host = new URL(BASE).hostname;
    await ctx.addCookies([{ name: 'session', value: COOKIE, domain: host, path: '/' }]);
  }

  async function runAll() {
    const snap = {};
    for (const p of PAGES) {
      const page = await ctx.newPage();
      await page.setViewportSize({ width: 1280, height: 900 });
      const r = await capture(page, p);
      snap[p.name] = {
        readback: r.readback,
        posts: r.posts.map(x => x.url + ' ' + x.body),
        rendered: r.rendered,
      };
      console.log(`  ${p.name}: 입력 ${r.filled.length}칸 · POST ${r.posts.length}건 · 숫자 ${r.rendered.length}개`);
      await page.close();
    }
    return snap;
  }

  if (MODE === 'record') {
    console.log('[1회차]'); const a = await runAll();
    console.log('[2회차 — 비결정 값 걸러내기]'); const b = await runAll();

    const golden = {};
    for (const name of Object.keys(a)) {
      golden[name] = {
        readback: stableIntersect(a[name].readback, b[name].readback),
        posts: JSON.stringify(a[name].posts) === JSON.stringify(b[name].posts) ? a[name].posts : null,
        rendered: a[name].rendered.filter((v, i) => b[name].rendered[i] === v),
      };
    }
    fs.writeFileSync(GOLDEN, JSON.stringify(golden, null, 2));
    const n = Object.entries(golden).map(([k, v]) =>
      `${k}: 값 ${Object.keys(v.readback).length} · POST ${v.posts ? v.posts.length : '불안정(제외)'} · 숫자 ${v.rendered.length}`);
    console.log('\n골든 저장:\n  ' + n.join('\n  '));
  } else {
    const golden = JSON.parse(fs.readFileSync(GOLDEN, 'utf8'));
    console.log('[검증]'); const now = await runAll();
    let fail = 0;
    for (const name of Object.keys(golden)) {
      const g = golden[name], c = now[name];
      for (const [id, v] of Object.entries(g.readback)) {
        if (String(c.readback[id]) !== String(v)) {
          console.log(`  FAIL ${name}.${id}  골든="${v}"  현재="${c.readback[id]}"`); fail++;
        }
      }
      if (g.posts) {
        const cur = c.posts;
        if (JSON.stringify(cur) !== JSON.stringify(g.posts)) {
          console.log(`  FAIL ${name} POST 본문 불일치`);
          for (let i = 0; i < Math.max(g.posts.length, cur.length); i++) {
            if (g.posts[i] !== cur[i]) {
              console.log(`    골든: ${String(g.posts[i]).slice(0, 300)}`);
              console.log(`    현재: ${String(cur[i]).slice(0, 300)}`);
            }
          }
          fail++;
        }
      }
      const gr = g.rendered, cr = c.rendered;
      const diff = gr.filter((v, i) => cr[i] !== v);
      if (diff.length) {
        console.log(`  FAIL ${name} 렌더 숫자 ${diff.length}개 불일치 (예: 골든 ${diff.slice(0, 6).join(' ')} )`);
        fail++;
      }
    }
    console.log(fail ? `\n실패 ${fail}건 — 숫자가 달라졌다. 배포 금지.` : '\n전부 일치 — 계산 결과 보존됨.');
    process.exit(fail ? 1 : 0);
  }

  await ctx.close();
  await browser.close();
})();
