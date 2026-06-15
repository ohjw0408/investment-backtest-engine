// 증시 캘린더 (/calendar)
(function () {
  const $ = (id) => document.getElementById(id);
  let cur = new Date(); cur.setDate(1);
  let EVENTS = [];           // [{date,type,title,symbol?}]
  let filter = 'all';
  let loggedIn = false;
  const DOW = ['일', '월', '화', '수', '목', '금', '토'];
  const TYPE_CLS = { econ: 'econ', earnings: 'earnings', dividend: 'dividend', policy: 'policy' };

  function ymd(d) { return d.toISOString().slice(0, 10); }

  // 배당 이벤트에 1주당 금액 데이터 부착 (클릭 시 팝오버용)
  function divData(e) {
    if (e.type !== 'dividend') return '';
    const name = (e.title || '').replace(/\s*배당락.*$/, '');
    return ` data-div="1" data-name="${name}" data-date="${e.date}"`
      + ` data-krw="${e.dps_krw == null ? '' : e.dps_krw}"`
      + ` data-usd="${e.dps_usd == null ? '' : e.dps_usd}"`
      + ` data-proj="${e.projected ? 1 : 0}"`;
  }

  function fmtKrw(v) { return '₩' + Math.round(v).toLocaleString('ko-KR'); }
  function fmtUsd(v) { return '$' + Number(v).toFixed(v < 1 ? 4 : 2); }

  function showDivPop(el) {
    const pop = $('calPop');
    if (!pop) return;
    const krw = parseFloat(el.dataset.krw), usd = parseFloat(el.dataset.usd);
    const proj = el.dataset.proj === '1';
    let amt = '—';
    if (!isNaN(krw)) amt = fmtKrw(krw) + (!isNaN(usd) ? ` <span class="cp-usd">(${fmtUsd(usd)})</span>` : '');
    pop.innerHTML = `<div class="cp-name">${el.dataset.name}</div>`
      + `<div class="cp-row"><span>배당락일</span><b>${el.dataset.date}</b></div>`
      + `<div class="cp-row"><span>1주당 배당금</span><b>${amt}</b></div>`
      + `<div class="cp-tag ${proj ? 'proj' : 'conf'}">${proj ? '예상 (yfinance 추정)' : '확정'}</div>`;
    pop.style.display = 'block';
    const r = el.getBoundingClientRect();
    const pw = pop.offsetWidth, ph = pop.offsetHeight;
    let left = r.left, top = r.bottom + 6;
    if (left + pw > window.innerWidth - 8) left = window.innerWidth - pw - 8;
    if (top + ph > window.innerHeight - 8) top = r.top - ph - 6;
    pop.style.left = Math.max(8, left) + 'px';
    pop.style.top = Math.max(8, top) + 'px';
  }
  function hideDivPop() { const p = $('calPop'); if (p) p.style.display = 'none'; }

  function showLoading() {
    const spin = `<div class="cal-loading" style="grid-column:1/-1;">
      <div class="cal-spinner"></div>
      <div class="cal-loading-txt">캘린더 불러오는 중…<br><span>경제지표·실적·배당 일정을 모으고 있어요</span></div>
    </div>`;
    if ($('calGrid')) $('calGrid').innerHTML = spin;
    if ($('calList')) $('calList').innerHTML = spin;
    if ($('calDows')) $('calDows').innerHTML = '';
  }

  async function load() {
    showLoading();
    try {
      const r = await (await fetch('/api/calendar')).json();
      EVENTS = r.events || [];
      loggedIn = !!r.logged_in;
      $('calLoginNote').innerHTML = loggedIn
        ? `내 종목 ${r.symbol_count}개의 실적·배당 포함 (내 자산·포트폴리오·관심목록). · <a href="/settings">⚙ 표시 지표 설정</a>`
        : '로그인하면 내 종목(내 자산·포트폴리오·관심목록)의 <b>실적·배당</b>도 표시되고, <a href="/settings">표시 지표를 설정</a>할 수 있어요.';
    } catch (e) { EVENTS = []; }
    render();
  }

  function eventsByDate() {
    const map = {};
    for (const ev of EVENTS) {
      // 통화정책(policy)은 '지표' 필터에 함께 노출
      if (filter !== 'all' && ev.type !== filter && !(filter === 'econ' && ev.type === 'policy')) continue;
      (map[ev.date] = map[ev.date] || []).push(ev);
    }
    return map;
  }

  function render() {
    const y = cur.getFullYear(), m = cur.getMonth();
    $('calMonth').textContent = `${y}년 ${m + 1}월`;
    // 비로그인 + 실적/배당 필터 = 로그인 유도
    if (!loggedIn && (filter === 'earnings' || filter === 'dividend')) {
      $('calDows').innerHTML = '';
      const msg = `<div style="grid-column:1/-1;text-align:center;padding:48px 20px;color:var(--text-muted);">
        ${filter === 'earnings' ? '기업 실적 발표' : '배당락'} 일정은 <b>내 종목</b> 기준이에요.<br>
        <a href="/auth/google" onclick="return handleGoogleLogin(event)">로그인</a>하면 내 자산·포트폴리오·관심목록 종목의 일정이 표시됩니다.</div>`;
      $('calGrid').innerHTML = msg; $('calList').innerHTML = msg;
      return;
    }
    $('calDows').innerHTML = DOW.map((d, i) => `<div class="cal-dow" style="${i === 0 ? 'color:#C62828' : ''}">${d}</div>`).join('');
    const map = eventsByDate();
    const first = new Date(y, m, 1), startDow = first.getDay();
    const daysIn = new Date(y, m + 1, 0).getDate();
    const todayStr = ymd(new Date());
    let cells = '';
    for (let i = 0; i < startDow; i++) cells += `<div class="cal-cell empty"></div>`;
    for (let day = 1; day <= daysIn; day++) {
      const ds = `${y}-${String(m + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const evs = map[ds] || [];
      const dow = new Date(y, m, day).getDay();
      const evHtml = evs.slice(0, 4).map(e => `<div class="cal-ev ${TYPE_CLS[e.type]}${e.type === 'dividend' ? ' clickable' : ''}" title="${e.title}"${divData(e)}>${e.title}</div>`).join('')
        + (evs.length > 4 ? `<div class="cal-more">+${evs.length - 4}</div>` : '');
      cells += `<div class="cal-cell ${ds === todayStr ? 'today' : ''} ${dow === 0 ? 'sun' : ''}">
        <div class="cal-daynum">${day}</div>${evHtml}</div>`;
    }
    $('calGrid').innerHTML = cells;
    // 모바일 리스트
    let list = '';
    for (let day = 1; day <= daysIn; day++) {
      const ds = `${y}-${String(m + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const evs = map[ds] || [];
      if (!evs.length) continue;
      list += `<div class="cal-list-day"><h4>${m + 1}/${day} (${DOW[new Date(y, m, day).getDay()]})</h4>`
        + evs.map(e => `<div class="cal-list-ev${e.type === 'dividend' ? ' clickable' : ''}"${divData(e)}><span class="cal-dot" style="background:${e.type === 'econ' ? '#1976D2' : e.type === 'policy' ? '#B8860B' : e.type === 'earnings' ? '#6A1B9A' : '#2E7D32'}"></span>${e.title}</div>`).join('')
        + `</div>`;
    }
    $('calList').innerHTML = list || '<div class="cal-loginnote">이 달 이벤트 없음.</div>';
  }

  $('calPrev').addEventListener('click', () => { cur.setMonth(cur.getMonth() - 1); render(); });
  $('calNext').addEventListener('click', () => { cur.setMonth(cur.getMonth() + 1); render(); });
  $('calToday').addEventListener('click', () => { cur = new Date(); cur.setDate(1); render(); });
  $('calFilters').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    $('calFilters').querySelectorAll('button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); filter = b.dataset.f; render();
  }));

  // 배당 이벤트 클릭 → 1주당 배당금 팝오버 (그리드 + 모바일 리스트 위임)
  document.addEventListener('click', (ev) => {
    const t = ev.target.closest('[data-div="1"]');
    if (t) { ev.stopPropagation(); showDivPop(t); }
    else if (!ev.target.closest('#calPop')) { hideDivPop(); }
  });
  window.addEventListener('scroll', hideDivPop, true);

  load();
})();
