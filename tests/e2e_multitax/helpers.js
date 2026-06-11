/**
 * 다계좌 세금 E2E 검증 — 공통 헬퍼 (Playwright Chromium, 라이브 서버 대상)
 * 계획: 다계좌세금_E2E검증_plan.md
 * 실행: node tests/e2e_multitax/run_all.js [BASE_URL]
 */
'use strict';
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.argv[2] || 'https://moneymilestone.duckdns.org';
const RESULTS_DIR = path.join(__dirname, 'results');
const SHOTS_DIR = path.join(RESULTS_DIR, 'shots');
const CASE_TIMEOUT = 180_000;

// 탭별 셀렉터 (2026-06-11 템플릿 실측 — 계획서 표의 #btSearchInput은 실제 #btTickerSearch)
const PAGES = {
  calc: {
    url: '/calculator', search: '#tickerSearchInput',
    item: '#tickerDropdown .ticker-drop-item', codeCls: '.ticker-drop-code',
    toggle: '#taxToggleWrap', label: '#taxToggleLabel', panel: '#taxPanel', run: '#runBtn',
  },
  bt: {
    url: '/backtest', search: '#btTickerSearch',
    item: '#btTickerDropdown .nav-search-result', codeCls: '.nav-search-code',
    toggle: '#btTaxWrap', label: '#btTaxLabel', panel: '#btTaxPanel', run: '#btRunBtn',
  },
  ret: {
    url: '/retirement', search: '#retTickerSearch',
    item: '#retTickerDropdown .nav-search-result', codeCls: '.nav-search-code',
    toggle: '#retTaxWrap', label: '#retTaxLabel', panel: '#retTaxPanel', run: '#retRunBtn',
  },
};

const results = [];
function record(id, name, status, note = '') {
  results.push({ id, name, status, note });
  console.log(`${status.padEnd(4)} ${id}  ${name}${note ? ' — ' + note : ''}`);
}

const num = v => typeof v === 'number' && isFinite(v);
const fmtMan = v => (num(v) ? Math.round(v / 1e4).toLocaleString() + '만' : String(v));
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function newSession() {
  fs.mkdirSync(SHOTS_DIR, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const consoleErrors = [];
  const dialogs = [];
  page.on('pageerror', e => consoleErrors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('dialog', async d => { dialogs.push(d.message()); try { await d.accept(); } catch (e) {} });
  return { browser, page, consoleErrors, dialogs };
}

async function shot(page, name) {
  try { await page.screenshot({ path: path.join(SHOTS_DIR, name + '.png'), fullPage: true }); } catch (e) {}
}

// 세금 프로필: 나이40·연소득5천만·ISA일반형. 비로그인 → localStorage 저장(서버 쓰기 없음 = 라이브 안전).
async function setupTaxProfile(page) {
  await page.goto(BASE + '/tax-settings', { waitUntil: 'networkidle' });
  await page.fill('#userAge', '40');
  await page.fill('#earnedIncome', '50000000');
  // 라디오 input은 CSS로 숨김(커스텀 스타일) → 감싸는 라벨 클릭
  await page.click('label.rebal-option:has(input[name="isaType"][value="general"])');
  await page.click('button.save-btn');
  await sleep(500);
  const saved = await page.evaluate(() => {
    try { return JSON.parse(localStorage.getItem('domino_tax_settings') || 'null'); } catch (e) { return null; }
  });
  if (!saved || Number(saved.age) !== 40 || Number(saved.earned_income) !== 50000000) {
    throw new Error('세금 프로필 저장 실패: ' + JSON.stringify(saved));
  }
  return saved;
}

async function gotoPage(page, kind) {
  await page.goto(BASE + PAGES[kind].url, { waitUntil: 'networkidle' });
}

// 상단 포트폴리오 종목 추가 — 검색 input 실타이핑 → 드롭다운 실클릭.
async function addTopTicker(page, kind, code) {
  const P = PAGES[kind];
  await page.fill(P.search, code);
  await page.locator(`${P.item}:has(${P.codeCls}:text-is("${code}"))`).first().click({ timeout: 15000 });
}

async function setTax(page, kind, on) {
  const P = PAGES[kind];
  const cur = ((await page.textContent(P.label)) || '').trim() === 'ON';
  if (cur !== on) await page.click(P.toggle);
  const now = ((await page.textContent(P.label)) || '').trim() === 'ON';
  if (now !== on) throw new Error(`세금 토글 실패(${kind} → ${on ? 'ON' : 'OFF'})`);
}

function accountCard(page, i) {
  return page.locator('#taxAccountList > div').nth(i);
}

async function addAccount(page) {
  await page.click('button:has-text("+ 계좌 추가")');
}

async function setAccountType(page, i, type) {
  await accountCard(page, i).locator('select').first().selectOption(type);
}

async function setAccountPriority(page, i, p) {
  await accountCard(page, i).locator('label:has-text("순위") input').fill(String(p));
}

// labelText: '초기 투자금' | '월 적립액' | '시작 목돈' | '미실현 차익'
async function setAccountAmount(page, i, labelText, val) {
  await accountCard(page, i).locator(`label:has-text("${labelText}") input`).fill(String(val));
}

async function addAccountTicker(page, i, code) {
  await page.fill(`#accountTickerSearch${i}`, code);
  await page.locator(`#accountTickerDropdown${i} .ticker-drop-item:has(.ticker-drop-code:text-is("${code}"))`)
    .first().click({ timeout: 15000 });
}

// range 슬라이더 — 드래그 자동화 불안정해 값 주입 + input/change 이벤트(페이지 핸들러 동일 경로). 유일한 evaluate 사용처.
async function setRange(page, sel, val) {
  await page.locator(sel).evaluate((el, v) => {
    el.value = String(v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }, val);
}

// 실행 버튼 클릭 → /api/task/{id} 폴링에서 SUCCESS/FAILURE 응답 캡처.
// 검증 alert(비중·종목 누락 등) 시 즉시 실패 처리(타임아웃 방지).
async function runSim(page, kind, { timeout = CASE_TIMEOUT, dialogs = null } = {}) {
  const P = PAGES[kind];
  const dialogBase = dialogs ? dialogs.length : 0;

  const respP = page.waitForResponse(async r => {
    if (!r.url().includes('/api/task/')) return false;
    try {
      const j = await r.json();
      return j.status === 'SUCCESS' || j.status === 'FAILURE';
    } catch (e) { return false; }
  }, { timeout }).then(async r => ({ data: await r.json() })).catch(() => ({ timedOut: true }));

  await page.click(P.run);

  const dialogWatch = (async () => {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      if (dialogs && dialogs.length > dialogBase) return { dialog: dialogs[dialogs.length - 1] };
      await sleep(500);
    }
    return { timedOut: true };
  })();

  const winner = await Promise.race([respP, dialogWatch]);
  if (winner.dialog) throw new Error('실행 중 alert: ' + winner.dialog);
  if (winner.timedOut) throw new Error(`시뮬 응답 타임아웃(${timeout / 1000}s)`);

  const data = winner.data;
  if (data.status === 'SUCCESS') {
    let r = data.result;
    if (kind === 'bt' && r && r.result) r = r.result; // 백테스트는 result.result 이중 래핑
    return { ok: true, result: r };
  }
  return { ok: false, error: data.error || '', errorData: data.error_data || null };
}

// 라이브 큐 지연 대비 1회 재시도(계획 §7).
async function withRetry(fn, label = '') {
  try { return await fn(); }
  catch (e) {
    console.log(`  ↻ 재시도(${label}): ${e.message}`);
    await sleep(8000);
    return await fn();
  }
}

function writeResultsMd(consoleErrors) {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const file = path.join(RESULTS_DIR, `${today}_result.md`);
  const cnt = s => results.filter(r => r.status === s).length;
  const lines = [
    `# 다계좌 세금 E2E 검증 결과 (${new Date().toISOString().slice(0, 16).replace('T', ' ')})`,
    '',
    `대상: ${BASE} · 계획: 다계좌세금_E2E검증_plan.md`,
    '',
    `**${cnt('PASS')} PASS / ${cnt('FAIL')} FAIL / ${cnt('SKIP')} SKIP** (총 ${results.length}건)`,
    '',
    '| # | 케이스 | 판정 | 상세 |',
    '|---|---|---|---|',
    ...results.map(r => `| ${r.id} | ${r.name} | ${r.status} | ${r.note.replace(/\|/g, '\\|')} |`),
    '',
    `브라우저 콘솔/페이지 에러: ${consoleErrors.length}건`,
    ...(consoleErrors.length ? ['```', ...consoleErrors.slice(0, 20), '```'] : []),
    '',
    '스크린샷: `results/shots/`',
    '',
    '_생성: tests/e2e_multitax/run_all.js_',
  ];
  fs.writeFileSync(file, lines.join('\n'), 'utf8');
  return file;
}

module.exports = {
  BASE, CASE_TIMEOUT, PAGES, results,
  record, num, fmtMan, sleep,
  newSession, shot, setupTaxProfile, gotoPage,
  addTopTicker, setTax, accountCard, addAccount,
  setAccountType, setAccountPriority, setAccountAmount, addAccountTicker,
  setRange, runSim, withRetry, writeResultsMd,
};
