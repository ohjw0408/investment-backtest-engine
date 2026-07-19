// search.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 내용 무변경 이동
// 인기 종목(큐레이션 — 추후 증권사 협찬/조회수 기반 동적화). 국내·해외·ETF 대표.
const SP_POPULAR = [
  { code: '005930', name: '삼성전자',        badge: 'KOSPI' },
  { code: 'SPY',    name: 'SPDR S&P 500 ETF', badge: 'US ETF' },
  { code: 'QQQ',    name: 'Invesco QQQ',      badge: 'US ETF' },
  { code: 'NVDA',   name: 'NVIDIA',           badge: 'NASDAQ' },
  { code: 'SCHD',   name: 'Schwab US Dividend Equity', badge: 'US ETF' },
  { code: '069500', name: 'KODEX 200',        badge: 'KR ETF' },
  { code: 'TSLA',   name: 'Tesla',            badge: 'NASDAQ' },
  { code: '000660', name: 'SK하이닉스',       badge: 'KOSPI' },
  { code: 'AAPL',   name: 'Apple',            badge: 'NASDAQ' },
];
const SP_RECENT_KEY = 'mm_recent_searches';

function badgeColor(badge) {
  if (badge === 'KR ETF' || badge === 'KOSPI' || badge === 'KOSDAQ') return '#1976D2';
  if (badge === 'US ETF' || badge === 'NASDAQ' || badge === 'NYSE')   return '#2E7D32';
  if (badge === 'CRYPTO') return '#F57C00';
  return '#78909C';
}
function fmtPrice(price, currency) {
  if (price == null) return '—';
  if (currency === 'PT') {   // 지수 = 포인트(통화 기호 없음)
    if (price >= 1000) return Math.round(price).toLocaleString();
    return price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }
  if (currency === 'RATE') return price.toFixed(2) + '%';   // 금리
  if (currency === 'KRW') {
    if (price >= 10000) return '₩' + (Math.round(price / 100) * 100).toLocaleString();
    return '₩' + Math.round(price).toLocaleString();
  }
  return '$' + price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function fmtChange(pct) {
  if (pct == null) return { text: '—', cls: 'flat' };
  const sign = pct >= 0 ? '+' : '';
  return { text: sign + pct.toFixed(2) + '%', cls: pct > 0 ? 'up' : pct < 0 ? 'down' : 'flat' };
}
function spEsc(s) { return String(s ?? '').replace(/'/g, "\\'"); }

// 필터: badge → 단일 카테고리 키
function spCategory(badge) {
  if (badge === 'KR ETF') return 'kr_etf';
  if (badge === 'KOSPI' || badge === 'KOSDAQ' || badge === 'KRX') return 'kr_stock';
  if (badge === 'US ETF') return 'us_etf';
  if (badge === 'NASDAQ' || badge === 'NYSE') return 'us_stock';
  if (badge === 'CRYPTO') return 'crypto';
  return '';
}

const input      = document.getElementById('searchInput');
const resultsDiv = document.getElementById('searchResults');
const defaultDiv = document.getElementById('spDefault');
let timer = null, lastCodes = [], lastItems = [], spSeq = 0, spPage = 1, spTotal = 0, spQuery = '';
const SP_PER_PAGE = 18;
const spActive = new Set();   // 다중선택 필터

// ── 최근 검색 (localStorage) ──
function spGetRecent() { try { return JSON.parse(localStorage.getItem(SP_RECENT_KEY) || '[]'); } catch(e) { return []; } }
function spPushRecent(item) {
  if (!item || !item.code) return;
  let list = spGetRecent().filter(r => r.code !== item.code);
  list.unshift({ code: item.code, name: item.name || item.code, badge: item.badge || '' });
  list = list.slice(0, 8);
  try { localStorage.setItem(SP_RECENT_KEY, JSON.stringify(list)); } catch(e) {}
}
function spClearRecent() { try { localStorage.removeItem(SP_RECENT_KEY); } catch(e) {} renderRecent(); }
function renderRecent() {
  const list = spGetRecent();
  const sec = document.getElementById('spRecentSection');
  const box = document.getElementById('spRecent');
  if (!list.length) { sec.style.display = 'none'; return; }
  sec.style.display = 'block';
  box.innerHTML = list.map(r => `
    <a class="sp-recent-chip" href="/symbol/${encodeURIComponent(r.code)}" onclick="spPushRecent(${JSON.stringify(r).replace(/"/g,'&quot;')})">
      <b>${r.code}</b> ${r.name && r.name !== r.code ? r.name.slice(0,14) : ''}
    </a>`).join('');
}

// ── 인기 종목 ──
function renderPopular() {
  document.getElementById('spPopular').innerHTML = SP_POPULAR.map((item, i) => {
    const c = badgeColor(item.badge);
    return `<a class="result-card" href="/symbol/${encodeURIComponent(item.code)}"
      onclick="spPushRecent({code:'${spEsc(item.code)}',name:'${spEsc(item.name)}',badge:'${spEsc(item.badge)}'})">
      <div class="card-top">
        <span class="result-badge" style="background:${c}22;color:${c}">${item.badge}</span>
        <span class="sp-rank">#${i+1}</span>
      </div>
      <div class="card-name">${item.name}</div>
      <div class="card-code">${item.code}</div>
    </a>`;
  }).join('');
}

function spClearInput() { input.value = ''; input.dispatchEvent(new Event('input')); input.focus(); }

function spCatsParam() { return [...spActive].join(','); }

// ── ETF 상세검색 모드 ──
let spMode = 'all';
const ETF_GROUPS = ['market', 'asset', 'region', 'bdur', 'btype', 'style', 'size', 'sector'];
const etfFacets = {
  market: new Set(), asset: new Set(), region: new Set(), bdur: new Set(),
  btype: new Set(), style: new Set(), size: new Set(), sector: new Set(),
  lev: '', hedge: '',
};

function spSetMode(m) {
  if (spMode === m) return;
  spMode = m;
  document.getElementById('spModeAll').classList.toggle('active', m === 'all');
  document.getElementById('spModeEtf').classList.toggle('active', m === 'etf');
  document.getElementById('spFacetPanel').style.display = m === 'etf' ? 'block' : 'none';
  document.getElementById('spFilters').style.display = m === 'all' ? 'flex' : 'none';
  input.placeholder = m === 'etf'
    ? 'ETF 이름·자연어 검색 (예: 미국 단기채, 커버드콜)'
    : '종목명, ETF, 티커 입력 (예: SPY, 삼성전자)';
  spQuery = input.value.trim();
  if (m === 'etf') {
    defaultDiv.style.display = 'none';
    spFetch(1);
  } else if (spQuery) {
    spFetch(1);
  } else {
    input.dispatchEvent(new Event('input'));   // 기본화면 복귀
  }
}

function etfClearGroup(g) {
  etfFacets[g].clear();
  document.querySelectorAll(`.sp-chip[data-g="${g}"]`).forEach(c => c.classList.remove('active'));
}

function etfCondRows() {
  const hasBond = etfFacets.asset.has('bond');
  const hasEq   = etfFacets.asset.has('equity');
  document.getElementById('spRowBondDur').style.display  = hasBond ? 'flex' : 'none';
  document.getElementById('spRowBondType').style.display = hasBond ? 'flex' : 'none';
  document.getElementById('spRowEqStyle').style.display  = hasEq ? 'flex' : 'none';
  document.getElementById('spRowSector').style.display   = hasEq ? 'flex' : 'none';
  // 숨긴 그룹의 잔류 선택 해제 — 안 보이는 필터가 결과를 죽이는 것 방지
  if (!hasBond) { etfClearGroup('bdur'); etfClearGroup('btype'); }
  if (!hasEq)   { etfClearGroup('style'); etfClearGroup('size'); etfClearGroup('sector'); }
}

function etfToggle(btn) {
  const set = etfFacets[btn.dataset.g];
  if (set.has(btn.dataset.v)) set.delete(btn.dataset.v); else set.add(btn.dataset.v);
  btn.classList.toggle('active', set.has(btn.dataset.v));
  etfCondRows();
  spFetch(1);
}

function etfToggleSingle(btn) {   // lev·hedge = 그룹 내 단일 선택
  const g = btn.dataset.g;
  etfFacets[g] = etfFacets[g] === btn.dataset.v ? '' : btn.dataset.v;
  document.querySelectorAll(`.sp-chip[data-g="${g}"]`)
    .forEach(c => c.classList.toggle('active', etfFacets[g] === c.dataset.v));
  spFetch(1);
}

function etfResetFacets() {
  ETF_GROUPS.forEach(g => etfFacets[g].clear());
  etfFacets.lev = ''; etfFacets.hedge = '';
  document.querySelectorAll('#spFacetPanel .sp-chip').forEach(c => c.classList.remove('active'));
  etfCondRows();
  spFetch(1);
}

function etfParams() {
  const p = [];
  ETF_GROUPS.forEach(g => {
    if (etfFacets[g].size) p.push(`${g}=${encodeURIComponent([...etfFacets[g]].join(','))}`);
  });
  if (etfFacets.lev) p.push('lev=' + etfFacets.lev);
  if (etfFacets.hedge) p.push('hedge=' + etfFacets.hedge);
  return p.join('&');
}

function spToggle(cat) {
  if (spActive.has(cat)) spActive.delete(cat); else spActive.add(cat);
  document.querySelectorAll('.sp-chip[data-cat]').forEach(c => c.classList.toggle('active', spActive.has(c.dataset.cat)));
  document.getElementById('spReset').style.display = spActive.size ? 'inline-flex' : 'none';
  if (spQuery) spFetch(1);
}
function spResetFilter() {
  spActive.clear();
  document.querySelectorAll('.sp-chip[data-cat]').forEach(c => c.classList.remove('active'));
  document.getElementById('spReset').style.display = 'none';
  if (spQuery) spFetch(1);
}

// 서버사이드 페이지 조회(전체 결과·필터·페이지당 18)
// ETF 모드는 검색어 없이도 브라우즈 가능(etf=1 + 패싯 파라미터)
async function spFetch(page) {
  if (spMode !== 'etf' && !spQuery) return;
  spPage = page;
  const seq = ++spSeq;
  resultsDiv.innerHTML = '<div class="search-hint">검색 중...</div>';
  try {
    let url = `/api/search?q=${encodeURIComponent(spQuery)}&page=${page}&per=${SP_PER_PAGE}`;
    if (spMode === 'etf') {
      url += '&etf=1';
      const fp = etfParams();
      if (fp) url += '&' + fp;
    } else {
      url += `&cats=${encodeURIComponent(spCatsParam())}`;
    }
    const r = await (await fetch(url)).json();
    if (seq !== spSeq) return;                                        // stale 폐기
    if (spMode !== 'etf' && input.value.trim() === '') return;        // 빈칸 폐기(통합만)
    lastItems = r.items || []; spTotal = r.total || 0; spPage = r.page || page;
    renderResults();
  } catch (e) {
    if (seq === spSeq) resultsDiv.innerHTML = '<div class="search-hint">오류가 발생했습니다</div>';
  }
}

// 페이지네이션: 10개 단위 그룹 + 작은화살표(이전/다음 그룹)·큰화살표(처음/끝)
function spGoPage(pg) { spFetch(pg); window.scrollTo({ top: 0, behavior: 'smooth' }); }
function renderPagination(total) {
  const pager = document.getElementById('spPager');
  if (total <= 1) { pager.style.display = 'none'; return; }
  pager.style.display = 'flex';
  const cur = spPage;
  const gStart = Math.floor((cur - 1) / 10) * 10 + 1;
  const gEnd   = Math.min(gStart + 9, total);
  let h = '';
  h += `<button class="sp-pg" ${gStart <= 1 ? 'disabled' : ''} onclick="spGoPage(1)" title="처음">«</button>`;
  h += `<button class="sp-pg" ${gStart <= 1 ? 'disabled' : ''} onclick="spGoPage(${gStart - 1})" title="이전 묶음">‹</button>`;
  for (let p = gStart; p <= gEnd; p++)
    h += `<button class="sp-pg ${p === cur ? 'active' : ''}" onclick="spGoPage(${p})">${p}</button>`;
  h += `<button class="sp-pg" ${gEnd >= total ? 'disabled' : ''} onclick="spGoPage(${gEnd + 1})" title="다음 묶음">›</button>`;
  h += `<button class="sp-pg" ${gEnd >= total ? 'disabled' : ''} onclick="spGoPage(${total})" title="끝(${total})">»</button>`;
  pager.innerHTML = h;
}

function renderResults() {
  const total = spTotal;
  const totalPages = Math.max(1, Math.ceil(total / SP_PER_PAGE));
  const cntEl = document.getElementById('spCount');
  cntEl.style.display = total ? 'block' : 'none';
  cntEl.textContent = total ? `총 ${total}개 · ${spPage}/${totalPages} 페이지` : '';
  document.getElementById('searchControls').style.display = total ? 'flex' : 'none';
  renderPagination(totalPages);
  if (!lastItems.length) {
    resultsDiv.innerHTML = '<div class="search-hint">' + (spActive.size ? '이 필터에 맞는 결과가 없습니다' : '검색 결과가 없습니다') + '</div>';
    return;
  }
  lastCodes = lastItems.map(d => d.code);
  resultsDiv.innerHTML = '<div class="results-grid" style="max-width:900px;margin:0 auto;">' + lastItems.map(item => {
    const chg = fmtChange(item.change_pct);
    const priceStr = fmtPrice(item.price, item.currency);
    const c = badgeColor(item.badge);
    return `
      <a class="result-card" href="/symbol/${encodeURIComponent(item.code)}" data-code="${item.code}"
        onclick="spPushRecent({code:'${spEsc(item.code)}',name:'${spEsc(item.name)}',badge:'${spEsc(item.badge)}'})">
        <div class="card-top">
          <span class="result-badge" style="background:${c}22;color:${c}">${item.badge}</span>
          <span style="display:flex;align-items:center;gap:8px;">
            <span class="card-price">${priceStr}</span>
            ${window.MM_LOGGED_IN ? `<button class="result-bell" title="알림 설정" onclick="event.preventDefault();event.stopPropagation();mmAlert.openSymbol('${spEsc(item.code)}','${spEsc(item.name)}')">🔔</button>` : ''}
          </span>
        </div>
        <div class="card-name">${item.name}</div>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span class="card-code">${item.code}${item.subtitle ? ' · ' + item.subtitle : ''}</span>
          <span class="card-change ${chg.cls}">${chg.text}</span>
        </div>
      </a>`;
  }).join('') + '</div>';
  // 렌더 직후 보이는 페이지(≤18종목)만 라이브 시세 자동 갱신 — price_daily 박제값 방지.
  // 서버 Redis 15분 캐시라 부하 상한 = 15분당 distinct 코드 수(유저 수 무관).
  refreshSearchPrices(true);
}

async function refreshSearchPrices(auto) {
  if (!lastCodes.length) return;
  const codes = lastCodes.slice();   // 응답 도착 전 재검색 대비 스냅샷
  const btn = auto ? null : document.getElementById('searchRefreshBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
  try {
    const qs  = await (await fetch('/api/watchlist/quotes?codes=' + encodeURIComponent(codes.join(',')))).json();
    const map = Object.fromEntries(qs.map(q => [q.code, q]));
    document.querySelectorAll('.result-card[data-code]').forEach(card => {
      const q = map[String(card.dataset.code).toUpperCase()];
      if (!q) return;
      const pe = card.querySelector('.card-price'); if (pe) pe.textContent = q.value;
      const ce = card.querySelector('.card-change'); if (ce) { ce.textContent = q.change; ce.className = 'card-change ' + (q.up ? 'up' : 'down'); }
    });
  } catch (e) {}
  if (btn) { btn.textContent = '✓'; setTimeout(() => { btn.textContent = '🔄'; btn.disabled = false; }, 1200); }
}

input.addEventListener('input', () => {
  const q = input.value.trim();
  document.getElementById('spClear').style.display = q ? 'block' : 'none';
  spQuery = q;
  if (!q) {
    clearTimeout(timer); ++spSeq;   // 대기 타이머 취소 + in-flight 응답 무효화(도배 방지)
    if (spMode === 'etf') {         // ETF 모드: 빈 검색어 = 패싯 브라우즈
      resultsDiv.innerHTML = '';
      timer = setTimeout(() => spFetch(1), 250);
      return;
    }
    resultsDiv.innerHTML = '';
    defaultDiv.style.display = 'block';
    document.getElementById('searchControls').style.display = 'none';
    document.getElementById('spPager').style.display = 'none';
    document.getElementById('spCount').style.display = 'none';
    lastCodes = []; lastItems = []; spTotal = 0;
    renderRecent();
    return;
  }
  defaultDiv.style.display = 'none';
  clearTimeout(timer);
  resultsDiv.innerHTML = '<div class="search-hint">검색 중...</div>';
  timer = setTimeout(() => spFetch(1), 250);
});

// 초기: 최근 + 인기
renderRecent();
renderPopular();
