// 증시 캘린더 (/calendar)
(function () {
  const $ = (id) => document.getElementById(id);
  let cur = new Date(); cur.setDate(1);
  let EVENTS = [];           // [{date,type,title,symbol?}]
  let filter = 'all';
  let loggedIn = false;
  const DOW = ['일', '월', '화', '수', '목', '금', '토'];
  const TYPE_CLS = { econ: 'econ', earnings: 'earnings', dividend: 'dividend' };

  function ymd(d) { return d.toISOString().slice(0, 10); }

  async function load() {
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
      if (filter !== 'all' && ev.type !== filter) continue;
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
      const evHtml = evs.slice(0, 4).map(e => `<div class="cal-ev ${TYPE_CLS[e.type]}" title="${e.title}">${e.title}</div>`).join('')
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
        + evs.map(e => `<div class="cal-list-ev"><span class="cal-dot" style="background:${e.type === 'econ' ? '#1976D2' : e.type === 'earnings' ? '#6A1B9A' : '#2E7D32'}"></span>${e.title}</div>`).join('')
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

  load();
})();
