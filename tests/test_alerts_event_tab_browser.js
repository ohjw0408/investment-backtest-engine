/**
 * 알림 페이지 종목 알림 서브탭(가격 / 실적·배당) + 캘린더 알림 축소 실브라우저 검증.
 * 실행: node tests/test_alerts_event_tab_browser.js <sessionCookie> [baseUrl]
 */
const { chromium } = require('playwright');
const COOKIE = process.argv[2];
const BASE   = process.argv[3] || 'http://127.0.0.1:5000';
if (!COOKIE) { console.error('usage: node test_alerts_event_tab_browser.js <sessionCookie>'); process.exit(2); }

let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name); }
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  await ctx.addCookies([{ name: 'session', value: COOKIE, domain: new URL(BASE).hostname, path: '/' }]);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  // 시드: 보유 종목(계좌 2종) — 실적·배당 대상이 있는 상태로 본다
  for (const h of [{ code: 'SCHD', quantity: 10, account_type: '일반' },
                   { code: '133690', quantity: 100, account_type: 'ISA' }]) {
    await page.request.post(`${BASE}/api/holdings`, { data: h });
  }

  await page.goto(`${BASE}/alerts`, { waitUntil: 'networkidle' });

  // ── 1. 서브탭 기본 상태 ──
  ok('가격 패널 기본 노출', await page.isVisible('[data-sym-panel="price"] #alTypeChips'));
  ok('실적·배당 패널 기본 숨김', !(await page.isVisible('[data-sym-panel="event"] #evTypeChips')));

  // ── 2. 서브탭 전환 ──
  await page.click('[data-sym-tab="event"]');
  ok('실적·배당 패널 노출', await page.isVisible('#evTypeChips'));
  ok('가격 패널 숨김', !(await page.isVisible('#alTypeChips')));
  ok('배당 칩 기본 선택', await page.getAttribute('[data-etype="dividend"]', 'class').then(c => c.includes('on')));
  ok('금액 옵션 노출(배당)', await page.isVisible('#fEvAmount'));
  ok('종목 셀렉트 숨김(보유 전체 기본)', !(await page.isVisible('#fEvSymbol')));

  // ── 3. 대상 = 특정 종목 → 셀렉트+검색 노출 ──
  await page.selectOption('#evScope', 'symbol');
  ok('종목 셀렉트 노출', await page.isVisible('#fEvSymbol'));
  ok('검색창 노출', await page.isVisible('#fEvSearch'));
  ok('보유 종목이 셀렉트에 채워짐',
     (await page.$$eval('#evCode option', os => os.map(o => o.value))).includes('SCHD'));

  // ── 4. 실적 칩 → 금액 옵션 숨김 ──
  await page.click('[data-etype="earnings"]');
  ok('실적 선택 시 금액 옵션 숨김', !(await page.isVisible('#fEvAmount')));
  await page.click('[data-etype="dividend"]');
  ok('배당 재선택 시 금액 옵션 복귀', await page.isVisible('#fEvAmount'));

  // ── 5. 종목 검색 → 셀렉트 반영 ──
  await page.fill('#evSymSearch', 'QQQM');
  await page.waitForSelector('#evSymResults.open .al-sr-item[data-code]', { timeout: 30000 });
  await page.click('#evSymResults .al-sr-item[data-code]');
  ok('검색 선택이 셀렉트에 반영', (await page.inputValue('#evCode')).length > 0);

  // ── 6. 룰 생성(특정 종목 배당 + 금액) ──
  await page.click('#evCreate');
  await page.waitForSelector('[data-alert-panel="rules"].active', { timeout: 30000 });
  const ruleText = await page.textContent('#alRules');
  ok('내 알림에 배당락일 룰 생성', ruleText.includes('배당락일'));
  ok('룰 설명에 금액 옵션 표기', ruleText.includes('계좌별 예상 배당금 포함'));

  // ── 7. 보유 전체 실적 룰 생성 ──
  await page.click('[data-alert-tab="settings"]');
  await page.click('[data-sym-tab="event"]');
  await page.selectOption('#evScope', 'holdings');
  await page.click('[data-etype="earnings"]');
  await page.selectOption('#evWhen', 'd1');
  await page.click('#evCreate');
  await page.waitForSelector('#alRules .al-item', { timeout: 30000 });
  await page.waitForTimeout(1500);
  const ruleText2 = await page.textContent('#alRules');
  ok('보유 전체 실적 룰 생성', ruleText2.includes('실적 발표') && ruleText2.includes('보유 종목 전체'));
  ok('하루 전 시점 표기', ruleText2.includes('하루 전 아침'));

  // ── 8. 캘린더 알림 = 거시 전용 ──
  await page.click('[data-alert-tab="settings"]');
  ok('캘린더 실적 체크박스 제거', (await page.$('#caEarn')) === null);
  ok('캘린더 배당 체크박스 제거', (await page.$('#caDiv')) === null);
  ok('캘린더 종목 소스 섹션 제거', (await page.$('#caSymbols')) === null);
  await page.check('#caEnabled');
  ok('캘린더 본문 열림', await page.isVisible('#caBody'));
  ok('경제지표 목록 렌더', (await page.$$('#caEconList .ca-econ')).length > 0);
  await page.click('#caSave');
  await page.waitForFunction(() => /저장됐어요|실패/.test(document.getElementById('caStatus').textContent), null, { timeout: 30000 });
  ok('캘린더 저장 성공', (await page.textContent('#caStatus')).includes('저장됐어요'));

  // ── 9. 기존 가격 알림 폼 보존 ──
  await page.click('[data-sym-tab="price"]');
  await page.click('[data-type="target_price"]');
  ok('가격 폼 방향 필드 노출', await page.isVisible('#fDir'));
  ok('가격 폼 임계값 라벨 전환', (await page.textContent('#alThrLabel')) === '목표가');

  // ── 10. 스샷(라이트/다크) ──
  await page.click('[data-sym-tab="event"]');
  await page.screenshot({ path: 'design-shots/alerts-event-tab-light.png', fullPage: true });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.waitForTimeout(300);
  await page.screenshot({ path: 'design-shots/alerts-event-tab-dark.png', fullPage: true });
  ok('스샷 2종 저장', true);

  ok('콘솔 에러 0', errors.length === 0);
  if (errors.length) console.log('  errors:', errors.slice(0, 5));

  await browser.close();
  console.log(`\n${pass} PASS / ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
})();
