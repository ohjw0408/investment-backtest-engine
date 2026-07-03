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
async function spFetch(page) {
  if (!spQuery) return;
  spPage = page;
  const seq = ++spSeq;
  resultsDiv.innerHTML = '<div class="search-hint">검색 중...</div>';
  try {
    const url = `/api/search?q=${encodeURIComponent(spQuery)}&page=${page}&per=${SP_PER_PAGE}&cats=${encodeURIComponent(spCatsParam())}`;
    const r = await (await fetch(url)).json();
    if (seq !== spSeq || input.value.trim() === '') return;   // stale/빈칸 폐기
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
}

async function refreshSearchPrices() {
  if (!lastCodes.length) return;
  const btn = document.getElementById('searchRefreshBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳'; }
  try {
    const qs  = await (await fetch('/api/watchlist/quotes?codes=' + encodeURIComponent(lastCodes.join(',')))).json();
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
