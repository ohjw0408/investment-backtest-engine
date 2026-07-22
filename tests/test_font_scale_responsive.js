/**
 * 글자배율 × 뷰포트 매트릭스 검증 — 텍스트 잘림/넘침 탐지.
 *
 * 배경(2026-07-22): 엄마 폰(갤럭시 A, 삼성 "글자 크기" 슬라이더 4단)에서 홈 총자산
 * `₩75,808,745` 마지막 자리가 카드 밖으로 잘림. 해상도 문제가 아니라 Android WebView가
 * 시스템 글자배율을 textZoom으로 CSS 폰트에 곱해서 생긴 넘침.
 *
 * 기존 test_responsive_dark.js가 이걸 못 잡은 이유: 카드가 overflow:hidden 이라
 * documentElement.scrollWidth 는 안 넘친다. 잘림은 요소 안에서 일어난다.
 * → 요소별 scrollWidth > clientWidth (자기 자신이 내용을 자르는 요소) 를 봐야 한다.
 *
 * textZoom 시뮬레이션: 모든 요소의 computed font-size 를 읽어 scale 배로 인라인 고정.
 * Android textZoom 이 하는 일과 동일(단위 무관, 해석된 px에 곱).
 *
 * 실행: node tests/test_font_scale_responsive.js [BASE_URL] [SESSION_COOKIE]
 */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE = process.argv[2] || 'http://127.0.0.1:5000';
const COOKIE = process.argv[3] || '';
const SHOT_DIR = path.join(__dirname, 'shots_fontscale');
fs.mkdirSync(SHOT_DIR, { recursive: true });

// 실기기 폭 — 폴드/플립 커버화면부터 태블릿까지
const VIEWPORTS = [
  ['flip-cover260', 260, 512],   // 갤럭시 플립 커버 디스플레이
  ['fold-outer320', 320, 800],   // 갤럭시 폴드 바깥화면 (가장 좁음)
  ['phone360', 360, 780],        // 보급형 안드로이드 최빈값
  ['phone384', 384, 854],        // S22 Ultra
  ['phone412', 412, 915],        // A 시리즈 다수
  ['fold-inner673', 673, 841],   // 갤럭시 폴드 펼친 화면
  ['tablet800', 800, 1280],      // 갤럭시 탭 세로
  ['tablet1280', 1280, 800],     // 갤럭시 탭 가로 / 노트북
];

// 삼성 글자크기 슬라이더 9단 ≒ 0.85 ~ 1.5 배
const SCALES = [1.0, 1.15, 1.3, 1.5];

const PAGES = [
  ['home', '/'],
  ['myassets', '/myassets'],
  ['search', '/search'],
  ['calculator', '/calculator'],
];

// 전체 매트릭스는 home 만. 나머지는 대표 조합만 (실행시간 억제)
const REDUCED = [['phone360', 1.3], ['phone384', 1.5], ['fold-outer320', 1.15]];

let pass = 0, fail = 0;
const failures = [];
function ok(name, cond, extra) {
  if (cond) { pass++; }
  else { fail++; failures.push(name + (extra ? ' — ' + extra : '')); console.log('FAIL  ' + name + (extra ? '\n      ' + extra : '')); }
}

/**
 * textZoom 시뮬: computed font-size × scale.
 *
 * 함정 두 개를 피해야 실기기와 같은 결과가 나온다.
 *
 * 1) 반드시 2패스. 1패스로 하면 부모에 폰트를 박은 뒤 자식의 computed 를 읽게 돼
 *    상속 사슬을 따라 배율이 복리로 곱해진다(40px → 52 → 67.6 …). 실제 textZoom 은
 *    복리가 아니라 원본 폰트에 한 번만 곱한다. 먼저 전부 읽고, 그 다음 전부 쓴다.
 *
 * 2) 인라인 스타일이 아니라 *스타일시트*로 넣는다. 앱의 mmFitText 는 인라인 font-size 를
 *    지우고 자연 크기를 재측정하는데, 배율을 인라인으로 박아두면 지우는 순간 배율까지
 *    사라져 실제보다 작게 측정된다(→ 축소가 안 걸려 없는 버그가 보고됨). 실제 엔진은
 *    CSS 값에도 배율을 곱하므로, 스타일시트에 넣어야 인라인을 지웠을 때 배율이 남는다.
 *    !important 도 쓰지 않는다 — 앱의 인라인 조정이 이기는 게 실제 우선순위와 같다.
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
 * 실제로 "글자가 잘린" 곳만 수집.
 *
 * scrollWidth 기반 검사는 오탐이 심하다 — 실측으로 확인된 것들:
 *   · .guru-promo-card ::after 장식 글로우가 right:-50px 로 일부러 삐져나가고 카드가
 *     overflow:hidden 으로 자름 → 정확히 +50px 로 잡히지만 글자와 무관
 *   · .ps-name 의 text-overflow:ellipsis → 의도된 말줄임(… 어포던스가 보임)
 *   · <select> 내부 텍스트 truncation → 네이티브 컨트롤 정상 동작
 *
 * 그래서 텍스트 노드의 실제 사각형이 "자르는 조상"의 클라이언트 영역 밖으로
 * 나가는지만 본다. 장식 요소는 텍스트가 없으니 자동 제외된다.
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
    if (!host || !host.offsetParent && getComputedStyle(host).position !== 'fixed') continue;

    // 자르는 조상 찾기
    let clip = host, cs = null, skip = false;
    while (clip && clip !== document.documentElement) {
      cs = getComputedStyle(clip);
      if (SCROLLABLE.has(cs.overflowX)) { skip = true; break; }   // 스크롤로 볼 수 있음
      if (cs.textOverflow === 'ellipsis') { skip = true; break; } // 의도된 말줄임
      if (/^(select|input|textarea|option)$/i.test(clip.tagName)) { skip = true; break; }
      if (cs.overflowX !== 'visible') break;                      // 여기가 자른다
      clip = clip.parentElement;
    }
    if (skip || !clip || clip === document.documentElement) continue;

    const cr = clip.getBoundingClientRect();
    const range = document.createRange();
    range.selectNodeContents(node);
    const tr = range.getBoundingClientRect();
    range.detach && range.detach();
    if (tr.width === 0 && tr.height === 0) continue;

    // 클립 박스의 패딩 영역(테두리 안쪽) 기준
    const padL = cr.left + parseFloat(cs.borderLeftWidth || 0);
    const padR = cr.right - parseFloat(cs.borderRightWidth || 0);
    const overR = tr.right - padR;
    const overL = padL - tr.left;
    const over = Math.round(Math.max(overR, overL));
    if (over <= 1) continue;

    const sel = clip.tagName.toLowerCase() +
      (clip.id ? '#' + clip.id : '') +
      (clip.className && typeof clip.className === 'string'
        ? '.' + clip.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
    const key = sel + '|' + over;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ sel, over, text: raw.trim().replace(/\s+/g, ' ').slice(0, 32) });
  }
  return out.slice(0, 8);
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  if (COOKIE) {
    await ctx.addCookies([{ name: 'session', value: COOKIE, domain: '127.0.0.1', path: '/' }]);
  }

  for (const [pname, url] of PAGES) {
    for (const [vpName, w, h] of VIEWPORTS) {
      for (const scale of SCALES) {
        if (pname !== 'home' && !REDUCED.some(([v, s]) => v === vpName && s === scale)) continue;

        const page = await ctx.newPage();
        await page.setViewportSize({ width: w, height: h });
        try {
          await page.goto(BASE + url, { waitUntil: 'networkidle', timeout: 25000 });
        } catch (e) {
          await page.goto(BASE + url, { waitUntil: 'domcontentloaded', timeout: 25000 }).catch(() => {});
        }
        await page.waitForTimeout(900); // 지연 렌더(차트·시세) 안정화

        await page.evaluate(applyTextZoom, scale);
        // 실기기에서 배율은 로드 전에 이미 적용돼 있다. 여기서는 로드 후에 거는 셈이라
        // 폭 의존 로직(mmFitText 등)이 다시 돌 기회를 준다.
        await page.evaluate(() => window.dispatchEvent(new Event('resize')));
        await page.waitForTimeout(300);

        const tag = `${pname}/${vpName}/x${scale}`;

        const docOver = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        ok(`${tag} 문서 가로 오버플로우 없음`, docOver <= 1, `${docOver}px 초과`);

        const clipped = await page.evaluate(findClipped);
        ok(`${tag} 텍스트 잘림 없음`, clipped.length === 0,
           clipped.map(c => `${c.sel} +${c.over}px "${c.text}"`).join('\n      '));

        if (clipped.length || docOver > 1) {
          await page.screenshot({ path: path.join(SHOT_DIR, `${pname}-${vpName}-x${scale}.png`), fullPage: false });
        }
        await page.close();
      }
    }
  }

  await ctx.close();
  await browser.close();
  console.log(`\n총 ${pass} PASS / ${fail} FAIL`);
  if (failures.length) console.log(`\n실패 목록:\n- ` + failures.join('\n- '));
  process.exit(fail > 0 ? 1 : 0);
})();
