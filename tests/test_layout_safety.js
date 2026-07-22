/**
 * 레이아웃 안전성 전수 검증 — 글자배율 × 화면폭 × 로그인상태.
 *
 * 무엇을 보는가
 *   1) 문서 가로 오버플로우 (가로 스크롤바가 생기는가)
 *   2) 텍스트 가로 잘림 (글자가 자르는 조상 밖으로 나갔는가)
 *   3) 텍스트 세로 잘림 (고정 높이 박스 아래로 잘렸는가)
 *
 * 무엇을 못 보는가 — 검증 한계를 알고 쓸 것
 *   · 실기기가 아니라 시뮬레이션이다. 실제 Android WebView 의 textZoom 과 완전히
 *     같다는 보장은 없다.
 *   · "안 깨짐"만 본다. 안 깨졌지만 찌그러져서 읽기 힘든 상태는 통과한다.
 *     그건 --shots 로 뽑은 스크린샷을 사람이 봐야 한다.
 *   · 폴드 힌지 영역, 접힘 전환, RTL 은 보지 않는다.
 *
 * 전략 — 전체 매트릭스를 다 돌리지 않는다
 *   넘침은 거의 단조적이다(좁을수록·글자 클수록 심함). 그래서 먼저 "모서리"만 돌리고,
 *   거기서 걸린 페이지만 전체 매트릭스로 확대한다. 1,600 조합 → 200 남짓.
 *
 * 실행:
 *   node tests/test_layout_safety.js [BASE_URL] [SESSION_COOKIE] [--full] [--shots]
 *     --full   1단계를 건너뛰고 처음부터 전체 매트릭스
 *     --shots  통과·실패 무관하게 스크린샷 저장(육안 검토용)
 */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const ARGS = process.argv.slice(2);
const BASE = ARGS.find(a => a.startsWith('http')) || 'http://127.0.0.1:5000';
const COOKIE = ARGS.find(a => !a.startsWith('http') && !a.startsWith('--')) || '';
const FULL_ONLY = ARGS.includes('--full');
const SHOTS = ARGS.includes('--shots');
const WORKERS = 6;

const SHOT_DIR = path.join(__dirname, 'shots_layout');
fs.mkdirSync(SHOT_DIR, { recursive: true });

// auth: 'both' | 'auth'(로그인 필요) | 'anon'(비로그인 화면이 따로 있음)
const PAGES = [
  ['home',        '/',                 'both'],
  ['search',      '/search',           'both'],
  ['tools',       '/tools',            'both'],
  ['market',      '/market',           'both'],
  ['calculator',  '/calculator',       'both'],
  ['dividend',    '/dividend-target',  'both'],
  ['retirement',  '/retirement',       'both'],
  ['simple',      '/simple',           'both'],
  ['taxswitch',   '/tax-switch',       'both'],
  ['backtest',    '/backtest',         'both'],
  ['riskreturn',  '/risk-return',      'both'],
  ['macro',       '/macro',            'both'],
  ['calendar',    '/calendar',         'both'],
  ['examples',    '/examples',         'both'],
  ['myportfolios','/myportfolios',     'both'],
  ['myassets',    '/myassets',         'both'],
  ['taxsettings', '/tax-settings',     'auth'],
  ['settings',    '/settings',         'auth'],
  ['alerts',      '/alerts',           'auth'],
  ['terms',       '/terms',            'both'],
  ['privacy',     '/privacy',          'both'],
  ['deletion',    '/account-deletion', 'both'],
];

const VIEWPORTS = [
  ['flip260',   260,  512],  // 갤럭시 플립 커버 디스플레이
  ['fold320',   320,  800],  // 갤럭시 폴드 바깥화면 (가장 좁음)
  ['phone360',  360,  780],  // 보급형 안드로이드 최빈값
  ['phone384',  384,  854],  // S22 Ultra
  ['phone412',  412,  915],  // A 시리즈 다수
  ['fold673',   673,  841],  // 갤럭시 폴드 펼친 화면
  ['tablet800', 800, 1280],  // 갤럭시 탭 세로
  ['tab1280',  1280,  800],  // 갤럭시 탭 가로 / 노트북
];

// 삼성 글자크기 슬라이더 9단 ≒ 0.85 ~ 1.5 배
const SCALES = [1.0, 1.15, 1.3, 1.5];

// 1단계 모서리 — 가장 가혹한 조합만. 여기서 깨끗하면 중간값은 거의 확실히 깨끗하다.
const CORNERS = [['flip260', 1.5], ['fold320', 1.5], ['phone412', 1.5], ['tablet800', 1.5]];

// ── 브라우저 안에서 도는 함수들 ──────────────────────────────────────────────

/**
 * textZoom 시뮬. 2패스 + 스타일시트 주입이어야 실기기와 결과가 같다.
 * (1패스면 상속 사슬 따라 배율이 복리로 곱해지고, 인라인이면 앱이 인라인을 지워
 *  자연 크기를 잴 때 배율까지 사라진다. 둘 다 실측으로 확인된 함정.)
 */
function applyTextZoom(scale) {
  if (scale === 1) return;
  const els = [...document.querySelectorAll('body *')];
  const sizes = els.map(el => parseFloat(getComputedStyle(el).fontSize));
  const rules = [];
  els.forEach((el, i) => {
    if (!(sizes[i] > 0)) return;
    el.setAttribute('data-mmzoom', String(i));
    rules.push(`[data-mmzoom="${i}"]{font-size:${(sizes[i] * scale).toFixed(2)}px}`);
  });
  const style = document.createElement('style');
  style.id = 'mm-zoom-sim';
  style.textContent = rules.join('');
  document.head.appendChild(style);
}

/**
 * 텍스트가 실제로 잘린 곳만 수집(가로 + 세로).
 * scrollWidth 기준은 장식용 가상요소·의도된 말줄임·네이티브 select 까지 잡아
 * 오탐이 압도적이었다(실측 64건). 텍스트 노드의 Range 사각형으로 판정한다.
 */
function findClipped() {
  const SCROLLABLE = new Set(['auto', 'scroll']);
  const seen = new Set();
  const out = [];

  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const raw = node.nodeValue;
    if (!raw || !raw.trim()) continue;

    const host = node.parentElement;
    if (!host) continue;
    const hs = getComputedStyle(host);
    if (!host.offsetParent && hs.position !== 'fixed') continue;

    /* 비상호작용 장식은 잘려도 정보 손실이 없다 — 오히려 잘리라고 만든 것이다.
       예: 내 자산 데모 카드의 "예시" 워터마크(absolute · right:-10px · opacity .05 ·
       pointer-events:none · user-select:none · rotate). 클릭도 선택도 불가능한
       absolute 요소는 사용자가 읽어야 할 내용이 아니다. */
    if (hs.position === 'absolute' &&
        (hs.pointerEvents === 'none' || hs.userSelect === 'none' || hs.webkitUserSelect === 'none')) continue;

    // 가로/세로 각각 "자르는 조상"을 찾는다
    for (const axis of ['x', 'y']) {
      let clip = host, cs = null, skip = false;
      while (clip && clip !== document.documentElement) {
        cs = getComputedStyle(clip);
        const ov = axis === 'x' ? cs.overflowX : cs.overflowY;
        if (SCROLLABLE.has(ov)) { skip = true; break; }             // 스크롤로 볼 수 있음
        if (cs.textOverflow === 'ellipsis') { skip = true; break; }  // 의도된 말줄임
        // -webkit-line-clamp = "N줄까지만 보이고 말줄임" 도 의도된 잘림이다
        if (cs.webkitLineClamp && cs.webkitLineClamp !== 'none') { skip = true; break; }
        if (/^(select|input|textarea|option)$/i.test(clip.tagName)) { skip = true; break; }
        if (ov !== 'visible') break;                                 // 여기가 자른다
        clip = clip.parentElement;
      }
      if (skip || !clip || clip === document.documentElement) continue;

      const cr = clip.getBoundingClientRect();

      /* 접힌 아코디언 제외. `max-height:0; overflow:hidden` 으로 닫아둔 패널은 내용이
         "잘려" 있는 게 정상이다(더보기·수수료 패널 등). 실측 baseline 에서 이 오탐이
         1,100건 넘게 나왔다. 높이가 사실상 0인 클립 박스는 레이아웃 버그가 아니다. */
      if (axis === 'y' && cr.height < 8) continue;

      const range = document.createRange();
      range.selectNodeContents(node);
      const tr = range.getBoundingClientRect();
      if (tr.width === 0 && tr.height === 0) continue;

      let over;
      if (axis === 'x') {
        const l = cr.left + parseFloat(cs.borderLeftWidth || 0);
        const r = cr.right - parseFloat(cs.borderRightWidth || 0);
        over = Math.round(Math.max(tr.right - r, l - tr.left));
      } else {
        const t = cr.top + parseFloat(cs.borderTopWidth || 0);
        const b = cr.bottom - parseFloat(cs.borderBottomWidth || 0);
        over = Math.round(Math.max(tr.bottom - b, t - tr.top));
      }
      // 세로는 line-height/디센더 때문에 1~2px 오차가 흔하다. 3px 이상만 본다.
      if (over <= (axis === 'x' ? 1 : 3)) continue;

      const sel = clip.tagName.toLowerCase() +
        (clip.id ? '#' + clip.id : '') +
        (clip.className && typeof clip.className === 'string'
          ? '.' + clip.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
      const key = axis + '|' + sel + '|' + over;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ axis, sel, over, text: raw.trim().replace(/\s+/g, ' ').slice(0, 32) });
    }
  }
  return out.slice(0, 10);
}

// ── 러너 ────────────────────────────────────────────────────────────────────

const results = [];
let done = 0, total = 0;

async function checkOne(ctx, task) {
  const { pname, url, auth, vpName, w, h, scale } = task;
  const page = await ctx.newPage();
  const tag = `${pname}[${auth}]/${vpName}/x${scale}`;
  const issues = [];
  try {
    await page.setViewportSize({ width: w, height: h });
    try {
      await page.goto(BASE + url, { waitUntil: 'networkidle', timeout: 30000 });
    } catch (e) {
      await page.goto(BASE + url, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
    }
    await page.waitForTimeout(700);
    await page.evaluate(applyTextZoom, scale);
    await page.evaluate(() => window.dispatchEvent(new Event('resize')));
    await page.waitForTimeout(350);

    /* 문서 가로 오버플로우는 "가로 스크롤이 생겼다"까지만 알려준다. 고치려면 범인이
       필요하므로, 뷰포트 오른쪽을 넘은 요소 중 가장 바깥(=원인) 것을 같이 잡는다.
       자식이 부모 때문에 밀려난 경우가 많아 조상이 이미 범인이면 자식은 뺀다. */
    const doc = await page.evaluate(() => {
      const de = document.documentElement;
      const over = de.scrollWidth - de.clientWidth;
      if (over <= 1) return { over, culprits: [] };
      const vw = de.clientWidth;
      const bad = [];
      for (const el of document.querySelectorAll('body *')) {
        const r = el.getBoundingClientRect();
        if (!r.width && !r.height) continue;
        if (r.right <= vw + 1) continue;
        if (getComputedStyle(el).position === 'fixed') continue; // 뷰포트 고정 = 스크롤 유발 안 함
        // 가로 스크롤 컨테이너 안의 넓은 내용(테이블 등)은 문서 스크롤을 만들지 않는다
        let inScroller = false;
        for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
          const ox = getComputedStyle(p).overflowX;
          if (ox === 'auto' || ox === 'scroll') { inScroller = true; break; }
        }
        if (inScroller) continue;
        bad.push(el);
      }
      const outer = bad.filter(el => !bad.some(o => o !== el && o.contains(el)));
      return {
        over,
        culprits: outer.slice(0, 4).map(el => {
          const r = el.getBoundingClientRect();
          return el.tagName.toLowerCase() +
            (el.id ? '#' + el.id : '') +
            (el.className && typeof el.className === 'string'
              ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '') +
            ` (+${Math.round(r.right - vw)}px)`;
        }),
      };
    });
    if (doc.over > 1) {
      issues.push({
        axis: 'doc',
        sel: doc.culprits.length ? doc.culprits.join(' , ') : '<html>',
        over: doc.over,
        text: '문서 가로 오버플로우',
      });
    }

    const clipped = await page.evaluate(findClipped);
    issues.push(...clipped);

    if (SHOTS || issues.length) {
      await page.screenshot({
        path: path.join(SHOT_DIR, `${pname}-${auth}-${vpName}-x${scale}.png`),
        fullPage: false,
      }).catch(() => {});
    }
  } catch (e) {
    issues.push({ axis: 'err', sel: '-', over: 0, text: '검사 실패: ' + String(e).slice(0, 80) });
  } finally {
    await page.close().catch(() => {});
  }
  done++;
  if (done % 25 === 0) process.stdout.write(`  ...${done}/${total}\n`);
  return { tag, pname, issues };
}

async function runPool(tasks, ctxFor) {
  total = tasks.length; done = 0;
  const queue = tasks.slice();
  const out = [];
  await Promise.all(Array.from({ length: WORKERS }, async () => {
    while (queue.length) {
      const t = queue.shift();
      out.push(await checkOne(ctxFor(t), t));
    }
  }));
  return out;
}

function buildTasks(pages, combos) {
  const tasks = [];
  for (const [pname, url, auth] of pages) {
    const modes = auth === 'both' ? ['auth', 'anon'] : [auth === 'auth' ? 'auth' : 'anon'];
    for (const mode of modes) {
      for (const [vpName, scale] of combos) {
        const vp = VIEWPORTS.find(v => v[0] === vpName);
        tasks.push({ pname, url, auth: mode, vpName, w: vp[1], h: vp[2], scale });
      }
    }
  }
  return tasks;
}

(async () => {
  const t0 = Date.now();
  const browser = await chromium.launch();

  // 워커마다 컨텍스트를 따로 두면 쿠키·캐시가 섞이지 않는다
  const authCtxs = [], anonCtxs = [];
  for (let i = 0; i < WORKERS; i++) {
    const a = await browser.newContext();
    if (COOKIE) await a.addCookies([{ name: 'session', value: COOKIE, domain: '127.0.0.1', path: '/' }]);
    authCtxs.push(a);
    anonCtxs.push(await browser.newContext());
  }
  let rr = 0;
  const ctxFor = t => (t.auth === 'auth' ? authCtxs : anonCtxs)[(rr++) % WORKERS];

  const fullCombos = [];
  for (const [vpName] of VIEWPORTS) for (const s of SCALES) fullCombos.push([vpName, s]);

  let all = [];
  if (FULL_ONLY) {
    console.log(`[전체 매트릭스] ${PAGES.length}페이지 × ${fullCombos.length}조합`);
    all = await runPool(buildTasks(PAGES, fullCombos), ctxFor);
  } else {
    console.log(`[1단계 모서리] ${PAGES.length}페이지 × ${CORNERS.length}조합`);
    const stage1 = await runPool(buildTasks(PAGES, CORNERS), ctxFor);
    all = stage1.slice();

    const badPages = [...new Set(stage1.filter(r => r.issues.length).map(r => r.pname))];
    if (badPages.length) {
      const expand = PAGES.filter(p => badPages.includes(p[0]));
      console.log(`\n[2단계 확대] 모서리에서 걸린 ${expand.length}페이지 → 전체 매트릭스`);
      all = all.concat(await runPool(buildTasks(expand, fullCombos), ctxFor));
    } else {
      console.log('\n모서리 전부 통과 — 확대 불필요');
    }
  }

  await browser.close();

  // ── 리포트 ──
  const failed = all.filter(r => r.issues.length);
  const byPage = {};
  for (const r of failed) (byPage[r.pname] = byPage[r.pname] || []).push(r);

  console.log('\n' + '='.repeat(70));
  console.log(`검사 ${all.length}건 · 통과 ${all.length - failed.length} · 실패 ${failed.length} · ${((Date.now() - t0) / 1000).toFixed(0)}초`);
  console.log('='.repeat(70));

  // 원인 셀렉터별 집계 — 고칠 대상 목록
  const bySel = {};
  for (const r of failed) for (const i of r.issues) {
    const k = `${i.axis}|${i.sel}`;
    if (!bySel[k]) bySel[k] = { axis: i.axis, sel: i.sel, n: 0, max: 0, pages: new Set(), sample: i.text };
    bySel[k].n++; bySel[k].max = Math.max(bySel[k].max, i.over); bySel[k].pages.add(r.pname);
  }
  const sels = Object.values(bySel).sort((a, b) => b.n - a.n);
  if (sels.length) {
    console.log('\n■ 고칠 대상 (건수순)\n');
    for (const s of sels) {
      console.log(`  [${s.axis}] ${s.sel}`);
      console.log(`      ${s.n}건 · 최대 +${s.max}px · 페이지: ${[...s.pages].join(', ')}`);
      console.log(`      예: "${s.sample}"`);
    }
  }

  if (Object.keys(byPage).length) {
    console.log('\n■ 페이지별 실패 조합\n');
    for (const [p, rs] of Object.entries(byPage).sort((a, b) => b[1].length - a[1].length)) {
      console.log(`  ${p} (${rs.length}) — ${rs.slice(0, 6).map(r => r.tag.split('/').slice(1).join('/')).join(', ')}${rs.length > 6 ? ' …' : ''}`);
    }
  }

  fs.writeFileSync(path.join(SHOT_DIR, '_report.json'), JSON.stringify(all, null, 2));
  console.log(`\n스크린샷·상세: ${SHOT_DIR}`);
  process.exit(failed.length ? 1 : 0);
})();
