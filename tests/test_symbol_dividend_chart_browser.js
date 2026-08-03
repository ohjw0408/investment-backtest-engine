/**
 * 종목상세 배당 그래프 실브라우저 검증 (2026-08-03 신규, 로그인 불필요).
 *
 * 검증 대상:
 *  - 연간 집계 막대 + 배당수익률 선(이중축)이 실제로 렌더되는가
 *  - 연간/분기 토글 실클릭 동작 + 복귀
 *  - 상장 이전 = "추정" 이 그래프·표 양쪽에 표시되는가
 *    (백필이 상장 전 구간에 배당을 주입한다 — 458730은 115건 중 79건이 추정값)
 *  - 배당 없는 종목(지수)에서 차트가 안 뜨고 에러도 없는가
 *
 * ⚠️ symbol_page.js는 classic script라 `let` 선언이 window에 안 붙는다 →
 *    page.evaluate 안에서 `window.divChart`가 아니라 **맨이름**으로 접근해야 한다.
 *
 * 실행: node tests/test_symbol_dividend_chart_browser.js [baseUrl]
 */
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://127.0.0.1:5000';
let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('PASS  ' + name); }
  else { fail++; console.log('FAIL  ' + name + (extra ? '  → ' + extra : '')); }
}

async function openSymbol(ctx, code) {
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(`${BASE}/symbol/${code}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof allData !== 'undefined' && allData !== null,
    { timeout: 90000 }).catch(() => {});
  return { page, errors };
}

(async () => {
  const browser = await chromium.launch();

  for (const theme of ['light', 'dark']) {
    const ctx = await browser.newContext({ colorScheme: theme });

    // ── 배당 있는 ETF (실측 + 상장 전 추정 혼재) ──
    {
      const { page, errors } = await openSymbol(ctx, '458730');   // TIGER 미국배당다우존스
      ok(`[${theme}] 배당 차트 캔버스 렌더`, await page.locator('#dividendChart').isVisible());

      const info = await page.evaluate(() => {
        if (typeof divChart === 'undefined' || !divChart) return null;
        const bar = divChart.data.datasets.find(d => d.type === 'bar');
        const line = divChart.data.datasets.find(d => d.type === 'line');
        return {
          barPoints: bar ? bar.data.length : 0,
          hasLine: !!line,
          lineNonNull: line ? line.data.filter(v => v !== null).length : 0,
          axes: Object.keys(divChart.options.scales),
          mode: divMode,
          labels: divChart.data.labels.slice(0, 3),
        };
      });
      ok(`[${theme}] 연간 막대 데이터 존재`, info && info.barPoints >= 2, JSON.stringify(info));
      ok(`[${theme}] 배당수익률 선 존재`, info && info.hasLine && info.lineNonNull > 0, JSON.stringify(info));
      ok(`[${theme}] 이중축(y + y1)`, info && info.axes.includes('y') && info.axes.includes('y1'),
         info && info.axes.join(','));
      ok(`[${theme}] 기본 모드 = 연간`, info && info.mode === 'year', info && info.mode);
      ok(`[${theme}] 연간 라벨 형식(YYYY)`, info && info.labels.every(l => /^\d{4}$/.test(l)),
         info && JSON.stringify(info.labels));

      // ── 분기 토글 실클릭 ──
      await page.click('.div-mode-btn[data-divmode="quarter"]');
      await page.waitForTimeout(400);
      const q = await page.evaluate(() => ({
        mode: divMode,
        labels: divChart.data.labels.slice(0, 3),
        n: divChart.data.labels.length,
        active: document.querySelector('.div-mode-btn.active').dataset.divmode,
      }));
      ok(`[${theme}] 분기 토글 동작`, q.mode === 'quarter' && q.labels.every(l => /^\d{4} Q[1-4]$/.test(l)),
         JSON.stringify(q));
      ok(`[${theme}] 분기 버킷이 연간보다 많음`, q.n > info.barPoints, `${q.n} vs ${info.barPoints}`);
      ok(`[${theme}] 활성 버튼 표시 이동`, q.active === 'quarter', q.active);

      // 한 번 바꾸고 영구 고착되지 않는지
      await page.click('.div-mode-btn[data-divmode="year"]');
      await page.waitForTimeout(400);
      ok(`[${theme}] 연간 복귀`, await page.evaluate(() => divMode === 'year'));

      // ── 기본은 실측만 ──
      // 백필이 상장 전 수십 년치를 만들어 두는 종목이 있어(458730은 273건 중 237건),
      // 다 그리면 추정 구간이 화면을 지배하고 수익률 선이 오른쪽 끝에 뭉개진다.
      const base = await page.evaluate(() => {
        const line = divChart.data.datasets.find(d => d.type === 'line');
        return {
          first: divChart.data.labels[0],
          n: divChart.data.labels.length,
          lineGaps: line ? line.data.filter(v => v === null).length : -1,
          realStart: allData.prices[0].date.slice(0, 4),
          estToggleOff: !document.getElementById('divEstToggle').checked,
        };
      });
      ok(`[${theme}] 기본은 추정 제외(상장연도부터)`, base.first >= base.realStart,
         JSON.stringify(base));
      ok(`[${theme}] 추정 토글 기본 꺼짐`, base.estToggleOff);
      ok(`[${theme}] 수익률 선 끊김 없음(실측 구간엔 주가가 있다)`, base.lineGaps === 0,
         JSON.stringify(base));

      // ── 추정 포함 토글 실클릭 ──
      await page.click('#divEstToggle');
      await page.waitForTimeout(400);
      const withEst = await page.evaluate(() => ({
        first: divChart.data.labels[0],
        n: divChart.data.labels.length,
        legendShown: !document.querySelector('.div-lg-est').hidden,
        faded: divChart.data.datasets.find(d => d.type === 'bar')
          .backgroundColor.filter(x => String(x).startsWith('rgba')).length,
      }));
      ok(`[${theme}] 추정 포함 시 과거로 확장`, withEst.n > base.n && withEst.first < base.first,
         `${base.first}(${base.n}) -> ${withEst.first}(${withEst.n})`);
      ok(`[${theme}] 추정 범례가 그때만 노출`, withEst.legendShown, JSON.stringify(withEst));
      ok(`[${theme}] 추정 막대 반투명 처리`, withEst.faded > 0, JSON.stringify(withEst));

      await page.click('#divEstToggle');   // 되돌리기 — 고착 없는지
      await page.waitForTimeout(400);
      ok(`[${theme}] 추정 토글 복귀`,
         await page.evaluate(() => divChart.data.labels.length) === base.n);

      const est = await page.evaluate(() => ({
        note: !!document.querySelector('.div-est-note'),
        tableTags: document.querySelectorAll('.div-est-tag').length,
        estRows: document.querySelectorAll('tr.div-est').length,
      }));
      ok(`[${theme}] 추정 안내문 노출`, est.note, JSON.stringify(est));

      // 표의 추정 배지는 "더보기"로 과거 행을 펼쳐야 보인다(최근 행은 실측이라)
      const moreBtn = await page.locator('#divMoreBtn').count();
      if (moreBtn) { await page.click('#divMoreBtn'); await page.waitForTimeout(300); }
      const est2 = await page.evaluate(() => ({
        tableTags: document.querySelectorAll('.div-est-tag').length,
        estRows: document.querySelectorAll('tr.div-est').length,
      }));
      ok(`[${theme}] 표에도 추정 배지`, est2.tableTags > 0 && est2.estRows > 0, JSON.stringify(est2));

      // 올해(미완결)는 반투명 — 낮은 막대가 "배당 삭감"으로 읽히면 안 된다
      const styling = await page.evaluate(() => {
        const bar = divChart.data.datasets.find(d => d.type === 'bar');
        return {
          solid: bar.backgroundColor.filter(x => x === '#2E7D32').length,
          faded: bar.backgroundColor.filter(x => String(x).startsWith('rgba')).length,
          lastFaded: String(bar.backgroundColor[bar.backgroundColor.length - 1]).startsWith('rgba'),
        };
      });
      ok(`[${theme}] 진행중(올해) 막대 구분`, styling.lastFaded && styling.solid > 0,
         JSON.stringify(styling));

      // 가격 차트를 건드리지 않았는지 (겹치지 않는 게 설계 의도)
      const priceOk = await page.evaluate(() =>
        typeof chartInst !== 'undefined' && chartInst !== null &&
        chartInst.data.datasets.length === 1);
      ok(`[${theme}] 가격 차트 무변경(데이터셋 1개 유지)`, priceOk);

      await page.screenshot({ path: `design-shots/symbol-dividend-${theme}.png`, fullPage: false });
      ok(`[${theme}] 콘솔 에러 0`, errors.length === 0, errors.slice(0, 3).join(' | '));
      await page.close();
    }

    // ── 배당 없는 종목: 차트 미노출 + 무에러 ──
    {
      const { page, errors } = await openSymbol(ctx, '%5EGSPC');
      const has = await page.locator('#dividendChart').count();
      ok(`[${theme}] 지수엔 배당 차트 없음`, has === 0, `canvas=${has}`);
      ok(`[${theme}] 지수 페이지 콘솔 에러 0`, errors.length === 0, errors.slice(0, 3).join(' | '));
      await page.close();
    }

    await ctx.close();
  }

  await browser.close();
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
