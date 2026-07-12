const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'store-assets', 'play-store-graphics-20260704');
const RAW = path.join(OUT, 'raw');
const BASE = process.env.MM_BASE_URL || 'http://127.0.0.1:5000';
const SESSION_COOKIE = process.env.MM_SESSION_COOKIE || '';

fs.mkdirSync(RAW, { recursive: true });

function dates(count) {
  const out = [];
  const d = new Date('2026-07-04T00:00:00+09:00');
  for (let i = count - 1; i >= 0; i -= 1) {
    const x = new Date(d);
    x.setDate(d.getDate() - i);
    out.push(x.toISOString().slice(0, 10));
  }
  return out;
}

function smoothHistory(count, start, end) {
  const vals = [];
  for (let i = 0; i < count; i += 1) {
    const t = i / (count - 1);
    const trend = start + (end - start) * t;
    const wiggle = Math.sin(i / 9) * 90000 + Math.sin(i / 23) * 120000;
    vals.push(Math.round(trend + wiggle));
  }
  const tail = Math.min(34, count);
  for (let j = 0; j < tail; j += 1) {
    const t = j / (tail - 1);
    const ease = 1 - Math.pow(1 - t, 1.35);
    vals[count - tail + j] = Math.round(39280000 + (40000000 - 39280000) * ease + Math.sin(j / 4) * 18000);
  }
  vals[count - 3] = 39870000;
  vals[count - 2] = 39920000;
  vals[count - 1] = 40000000;
  return vals;
}

const groups = [
  { id: 1, user_id: 1, name: '성장 자산', color: '#2563EB', target_pct: 60 },
  { id: 2, user_id: 1, name: '배당 자산', color: '#059669', target_pct: 25 },
  { id: 3, user_id: 1, name: '채권', color: '#7C3AED', target_pct: 10 },
  { id: 4, user_id: 1, name: '금', color: '#D97706', target_pct: 5 },
];

const positionSeed = [
  ['SPY', 'SPDR S&P 500 ETF', 10000000, 910000, 850000, 1],
  ['QQQ', 'Invesco QQQ', 6000000, 780000, 725000, 1],
  ['005930', '삼성전자', 4000000, 83500, 78800, 1],
  ['000660', 'SK하이닉스', 4000000, 285000, 252000, 1],
  ['SCHD', 'Schwab US Dividend Equity ETF', 6000000, 37500, 35600, 2],
  ['JEPQ', 'JPMorgan Nasdaq Equity Premium Income ETF', 4000000, 79000, 76200, 2],
  ['TLT', 'iShares 20+ Year Treasury Bond ETF', 4000000, 124000, 127000, 3],
  ['KRX_GOLD', 'KRX 금현물', 2000000, 184000, 168000, 4],
];

const prices = {};
const prevClose = {};
const holdings = positionSeed.map(([code, name, value, price, avg, groupId], i) => {
  prices[code] = price;
  prevClose[code] = Math.round(price / 1.002);
  const g = groups.find(x => x.id === groupId);
  return {
    id: i + 1,
    user_id: 1,
    code,
    name,
    quantity: value / price,
    avg_price: avg,
    manual_price: null,
    buy_date: '2024-01-15',
    account_type: '일반',
    group_id: groupId,
    group_name: g.name,
    group_color: g.color,
    group_target: g.target_pct,
    created_at: '2026-07-04T00:00:00',
    updated_at: '2026-07-04T00:00:00',
  };
});

const portfolioHistory = {
  empty: false,
  labels: dates(270),
  values: smoothHistory(270, 35600000, 40000000),
  current: 40000000,
  change: 12.36,
  hide_amounts: false,
};

const myassetsData = {
  holdings,
  groups,
  prices,
  prev_close: prevClose,
  manual_codes: [],
  as_of: '2026-07-04T00:00:00',
  hide_amounts: false,
  rebal_band: 5,
};

const dividendData = {
  current_year: 2026,
  events: {
    2026: [
      { date: '2026-07-15', month: 7, code: 'SCHD', name: 'SCHD', krw_post: 46000 },
      { date: '2026-07-28', month: 7, code: 'JEPQ', name: 'JEPQ', krw_post: 73000 },
      { date: '2026-09-20', month: 9, code: 'SPY', name: 'SPY', krw_post: 38000 },
      { date: '2026-10-05', month: 10, code: 'TLT', name: 'TLT', krw_post: 21000 },
    ],
  },
};

const widgetConfig = {
  logged_in: true,
  widgets: [
    {
      id: 'market',
      name: '주요 시장',
      items: [
        { code: '^GSPC', name: 'S&P 500' },
        { code: '^IXIC', name: '나스닥' },
        { code: '^KS11', name: '코스피' },
        { code: 'KRX_GOLD', name: 'KRX 금현물' },
      ],
    },
    {
      id: 'portfolio',
      name: '자산배분 ETF',
      items: [
        { code: 'SPY', name: 'SPY' },
        { code: 'QQQ', name: 'QQQ' },
        { code: 'SCHD', name: 'SCHD' },
        { code: 'TLT', name: 'TLT' },
      ],
    },
  ],
};

const quoteMap = {
  '^GSPC': ['6,820.44', '+0.42%', true, [96, 97, 98, 99, 98.5, 100, 101]],
  '^IXIC': ['22,410.18', '+0.57%', true, [91, 92, 94, 95, 96, 97, 99]],
  '^KS11': ['3,210.55', '-0.18%', false, [101, 100, 99.6, 100.2, 99, 98.8, 98.6]],
  KRX_GOLD: ['184,000원', '+0.31%', true, [90, 91, 92, 93, 94, 95, 96]],
  SPY: ['$664.20', '+0.46%', true, [92, 93, 94, 95, 96, 97, 99]],
  QQQ: ['$568.10', '+0.62%', true, [88, 89, 91, 93, 94, 95, 98]],
  SCHD: ['$27.35', '+0.12%', true, [96, 96.4, 96.1, 96.8, 97, 97.2, 97.3]],
  TLT: ['$90.42', '-0.21%', false, [101, 100.5, 100.1, 99.8, 99.2, 99, 98.8]],
};

const macroOverview = {
  categories: [
    {
      category: '금리',
      series: [
        { code: 'US_FEDFUNDS', country: 'US', freq: '월', name_ko: '미국 기준금리', unit: '%', last_val: 4.75, change: 0, change_pct: 0, spark: [5.25, 5.1, 5.0, 4.9, 4.75], last_date: '2026-06', desc: '연방기금금리' },
        { code: 'US_DGS10', country: 'US', freq: '일', name_ko: '미국 국채 10년', unit: '%', last_val: 4.21, change: -0.03, change_pct: -0.71, spark: [4.35, 4.31, 4.28, 4.24, 4.21], last_date: '2026-07-02', desc: '10년물 국채금리' },
        { code: 'KR_BASE_RATE', country: 'KR', freq: '월', name_ko: '한국 기준금리', unit: '%', last_val: 2.75, change: 0, change_pct: 0, spark: [3.0, 3.0, 2.9, 2.8, 2.75], last_date: '2026-06', desc: '한국은행 기준금리' },
      ],
    },
    {
      category: '물가·고용',
      series: [
        { code: 'US_CPI', country: 'US', freq: '월', name_ko: '미국 CPI', unit: '%', last_val: 2.8, change: -0.1, change_pct: -3.45, spark: [3.2, 3.1, 3.0, 2.9, 2.8], last_date: '2026-06', desc: '소비자물가 상승률' },
        { code: 'KR_CPI', country: 'KR', freq: '월', name_ko: '한국 CPI', unit: '%', last_val: 2.1, change: 0.1, change_pct: 5, spark: [1.9, 2.0, 2.0, 2.1, 2.1], last_date: '2026-06', desc: '소비자물가 상승률' },
      ],
    },
  ],
  compare_pairs: [
    { label: '기준금리', us: 'US_FEDFUNDS', kr: 'KR_BASE_RATE' },
    { label: '물가', us: 'US_CPI', kr: 'KR_CPI' },
  ],
};

function backtestDemo() {
  const labels = dates(84);
  let peak = 25000000;
  const history = labels.map((date, i) => {
    const t = i / (labels.length - 1);
    const value = Math.round(25000000 + 14500000 * t + Math.sin(i / 5) * 230000 + Math.sin(i / 17) * 360000);
    peak = Math.max(peak, value);
    return { date, portfolio_value: value, drawdown: (value - peak) / peak };
  });
  history[history.length - 1].portfolio_value = 39580000;
  const body = {
    start_date: '2021-01-01',
    end_date: '2026-07-04',
    initial_capital: 25000000,
    monthly_contribution: 300000,
    dividend_mode: 'reinvest',
    rebal_mode: 'yearly',
    tickers: [
      { code: 'SPY', name: 'SPY', weight: 0.25 },
      { code: 'QQQ', name: 'QQQ', weight: 0.15 },
      { code: 'SCHD', name: 'SCHD', weight: 0.15 },
      { code: 'JEPQ', name: 'JEPQ', weight: 0.10 },
      { code: '005930', name: '삼성전자', weight: 0.10 },
      { code: '000660', name: 'SK하이닉스', weight: 0.10 },
      { code: 'TLT', name: 'TLT', weight: 0.10 },
      { code: 'KRX_GOLD', name: 'KRX 금현물', weight: 0.05 },
    ],
  };
  const result = {
    used_synthetic: false,
    synthetic_info: {},
    metrics: {
      end_value: 39580000,
      total_return: 0.168,
      cagr: 0.073,
      total_invested: 32500000,
      mdd: -0.118,
      sharpe: 0.86,
      total_dividend: 1480000,
      years: 5.5,
    },
    history,
    annual_returns: [
      { year: 2021, return: 0.091 },
      { year: 2022, return: -0.082 },
      { year: 2023, return: 0.147 },
      { year: 2024, return: 0.102 },
      { year: 2025, return: 0.084 },
      { year: 2026, return: 0.041 },
    ],
    annual_dividends: [
      { year: 2021, dividend: 180000 },
      { year: 2022, dividend: 230000 },
      { year: 2023, dividend: 270000 },
      { year: 2024, dividend: 310000 },
      { year: 2025, dividend: 345000 },
      { year: 2026, dividend: 145000 },
    ],
    rolling: null,
  };
  return { body, result };
}

function json(route, data) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(data),
  });
}

async function installDemoRoutes(page) {
  await page.route('**/api/portfolio/history', route => json(route, portfolioHistory));
  await page.route('**/api/myassets/data', route => json(route, myassetsData));
  await page.route('**/api/myassets/attribution', route => json(route, {
    ok: true,
    attribution: {
      up_driver: { name: 'SK하이닉스', contrib: 2.1 },
      down_defender: { name: 'TLT', down_capture: 0.6 },
    },
  }));
  await page.route('**/api/myassets/dividends', route => json(route, dividendData));
  await page.route('**/api/home-config', route => json(route, widgetConfig));
  await page.route('**/api/watchlist/quotes**', route => {
    const url = new URL(route.request().url());
    const codes = (url.searchParams.get('codes') || '').split(',').map(x => x.trim()).filter(Boolean);
    json(route, codes.map(code => {
      const q = quoteMap[code] || ['—', '+0.00%', true, [1, 2, 3]];
      return { code, value: q[0], change: q[1], up: q[2], spark: q[3] };
    }));
  });
  await page.route('**/api/macro/overview', route => json(route, macroOverview));
}

async function stable(page) {
  await page.waitForLoadState('domcontentloaded');
  try { await page.evaluate(() => document.fonts && document.fonts.ready); } catch (_) {}
  await page.waitForTimeout(900);
}

async function screenshot(page, name) {
  await stable(page);
  await page.screenshot({ path: path.join(RAW, name), fullPage: false });
}

async function captureSet(browser, label, viewport) {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 2,
    isMobile: viewport.width <= 820,
    hasTouch: viewport.width <= 820,
    locale: 'ko-KR',
  });
  if (SESSION_COOKIE) {
    await context.addCookies([{ name: 'session', value: SESSION_COOKIE, url: BASE, sameSite: 'Lax' }]);
  }
  await context.addInitScript(() => {
    localStorage.setItem('mm-theme', 'light');
    localStorage.setItem('mm-accent', 'orange');
  });
  const page = await context.newPage();
  await installDemoRoutes(page);

  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#portfolioCard', { timeout: 10000 });
  await page.waitForFunction(() => (document.querySelector('#portfolioValue')?.textContent || '').includes('₩'));
  await screenshot(page, `${label}-01-home.png`);

  await page.goto(`${BASE}/myassets`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#maTotalAssetValue', { timeout: 10000 });
  await page.waitForFunction(() => (document.querySelector('#maTotalAssetValue')?.textContent || '').includes('₩'));
  await screenshot(page, `${label}-02-assets.png`);

  if (viewport.width <= 820) {
    await page.click('.ma-mtab[data-mtab="holdings"]');
  } else {
    await page.evaluate(() => document.querySelector('[data-mtab="holdings"]')?.scrollIntoView({ block: 'center' }));
  }
  await page.waitForSelector('.hold-card', { timeout: 10000 });
  await screenshot(page, `${label}-03-holdings.png`);

  if (viewport.width <= 820) {
    await page.click('.ma-mtab[data-mtab="rebal"]');
  } else {
    await page.click('.ma-tab:nth-child(2)');
  }
  await page.waitForSelector('#rebalResult .rb-card', { timeout: 10000 });
  await screenshot(page, `${label}-04-rebalance.png`);

  await page.goto(`${BASE}/backtest`, { waitUntil: 'domcontentloaded' });
  const bt = backtestDemo();
  await page.waitForFunction(() => typeof window.renderBacktest === 'function');
  await page.evaluate(({ body, result }) => {
    window._btLastBody = body;
    window.renderBacktest(result);
  }, bt);
  await page.waitForSelector('#btResultContent', { timeout: 10000 });
  await screenshot(page, `${label}-05-backtest.png`);

  await page.goto(`${BASE}/macro`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.mc-card', { timeout: 10000 });
  await screenshot(page, `${label}-06-macro.png`);

  await context.close();
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    await captureSet(browser, 'phone', { width: 390, height: 844 });
    await captureSet(browser, 'tablet7', { width: 768, height: 1024 });
    await captureSet(browser, 'tablet10', { width: 1200, height: 1600 });
  } finally {
    await browser.close();
  }
})();
