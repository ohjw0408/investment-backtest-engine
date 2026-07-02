// 포트폴리오 예시 — 지역 탭 전환 + 카드 클릭 상세 모달 + 액션 3종(분석/비교/저장) 핸드오프.
// 분석 → /backtest(mm_bt_preload), 비교 → /risk-return(mm_rr_preload 누적), 저장 → /api/portfolio/save.
(function () {
  'use strict';

  var RR_KEY = 'mm_rr_preload';
  var MAX_CMP = 5;
  var SEG = ['#1f6feb', '#2ea043', '#e3873c', '#8957e5', '#c9433f', '#1f9b9b', '#d4a017', '#6e7681'];

  function toast(msg, kind) { if (typeof mmToast === 'function') mmToast(msg, kind); }
  function readJSON(s) { try { return JSON.parse(s) || []; } catch (e) { return []; } }
  function readTickers(card) { return readJSON(card.dataset.tickers); }
  function readCmp() { return readJSON(sessionStorage.getItem(RR_KEY)); }
  function writeCmp(list) { sessionStorage.setItem(RR_KEY, JSON.stringify(list)); }
  var esc = window.mmEsc;  // E-1 공용화: 전역 mmEsc(base.html) 단일 구현 — 로컬 복붙 제거 (2026-07-03)

  // ── 지역 탭 ──
  function selectTab(region) {
    var tabs = document.getElementById('exTabs');
    if (!tabs) return;
    var hit = tabs.querySelector('.ex-tab[data-region="' + region + '"]');
    if (!hit) return;
    tabs.querySelectorAll('.ex-tab').forEach(function (t) { t.classList.toggle('on', t === hit); });
    document.querySelectorAll('.ex-panel').forEach(function (p) {
      p.classList.toggle('on', p.dataset.panel === region);
    });
  }
  function bindTabs() {
    var tabs = document.getElementById('exTabs');
    if (!tabs) return;
    tabs.addEventListener('click', function (e) {
      var b = e.target.closest('.ex-tab');
      if (b) selectTab(b.dataset.region);
    });
    // 딥링크: /examples?tab=guru (옛 /gurus 리다이렉트) → 투자대가 탭 자동 선택
    var tab = new URLSearchParams(location.search).get('tab') || (location.hash || '').replace('#', '');
    if (tab) selectTab(tab);
  }

  // ── ① 분석하기 → 백테스트 프리로드(비중 0~1) ──
  function analyze(card) {
    var tickers = readTickers(card).map(function (t) {
      return { code: t.code, name: t.name || t.code, weight: (+t.weight || 0) / 100 };
    });
    if (!tickers.length) { toast('분석할 종목이 없어요.', 'err'); return; }
    var end = new Date();
    var start = new Date(); start.setFullYear(start.getFullYear() - 5);
    var fmt = function (x) { return x.toISOString().split('T')[0]; };
    sessionStorage.setItem('mm_bt_preload', JSON.stringify({
      tickers: tickers,
      start_date: fmt(start),
      end_date: fmt(end),
      rebal_mode: 'yearly',
      autorun: false,  // 폼만 채우고 분석 화면 표시(자동 실행 X) — 오너 지시
      source: 'example:' + card.dataset.slug,
    }));
    location.href = '/backtest';
  }

  // ── ② 비교에 추가 → 누적(비중 0~100 그대로) ──
  function compareAdd(card, btn) {
    var list = readCmp();
    if (list.some(function (p) { return p.slug === card.dataset.slug; })) {
      toast('이미 비교 목록에 담겨 있어요.', 'err'); return;
    }
    if (list.length >= MAX_CMP) { toast('비교는 최대 ' + MAX_CMP + '개까지예요.', 'err'); return; }
    list.push({ slug: card.dataset.slug, name: card.dataset.name, tickers: readTickers(card) });
    writeCmp(list);
    if (btn) { btn.classList.add('added'); btn.textContent = '✓ 담음'; }
    toast("'" + card.dataset.name + "' 비교 목록에 담았어요 (" + list.length + '개).', 'ok');
    renderCmpBar();
  }

  // ── ③ 즐겨찾기 저장 → 내 포트폴리오(비중 0~100) ──
  async function save(card, btn) {
    try {
      var me = await fetch('/api/me').then(function (r) { return r.json(); });
      if (!me.logged_in) {
        toast('로그인하면 이 포트폴리오를 즐겨찾기로 저장할 수 있어요.', 'err');
        setTimeout(function () { location.href = '/auth/google'; }, 1000);
        return;
      }
      if (btn) btn.disabled = true;
      var name = card.dataset.name;
      var tickers = readTickers(card).map(function (t) {
        return { code: t.code, name: t.name || t.code, weight: +t.weight || 0 };
      });
      // 동명 즐겨찾기 있으면 덮어쓰기
      var existingId = null;
      try {
        var l = await fetch('/api/portfolio/list').then(function (r) { return r.ok ? r.json() : []; });
        var e = l.find(function (p) { return p.name === name; });
        if (e) existingId = e.id;
      } catch (_) {}
      var res = await fetch('/api/portfolio/save', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: existingId, name: name, tickers: tickers }),
      });
      var j = await res.json().catch(function () { return {}; });
      if (!res.ok) { toast(j.error || '저장에 실패했어요.', 'err'); if (btn) btn.disabled = false; return; }
      toast("⭐ '" + name + "' 저장 완료 · 내 포트폴리오에서 확인하세요.", 'ok');
      if (btn) { btn.disabled = false; btn.classList.add('added'); }
    } catch (e) {
      toast('저장에 실패했어요. 잠시 후 다시 시도해주세요.', 'err');
      if (btn) btn.disabled = false;
    }
  }

  // ── 상세 모달 ──
  var activeCard = null;

  function renderHead(d) {
    if (d.type === 'guru') {
      return '<span class="exm-mono" style="background:' + esc(d.stancecolor) + '">' + esc(d.monogram) + '</span>' +
        '<div style="min-width:0;">' +
          '<div class="exm-name" id="exmTitle">' + esc(d.nameko) + ' <span class="exm-name-en">' + esc(d.nameen) + '</span></div>' +
          '<div class="exm-sub">' + esc(d.fund) + '</div>' +
        '</div>' +
        '<span class="exm-badge"><span style="width:8px;height:8px;border-radius:50%;background:' + esc(d.stancecolor) + '"></span>' + esc(d.stancelabel) + '</span>';
    }
    return '<div style="min-width:0;">' +
        '<div class="exm-name" id="exmTitle">' + esc(d.name) + '</div>' +
        '<div class="exm-sub">' + esc(d.source) + '</div>' +
      '</div>' +
      '<span class="exm-badge"><span style="width:8px;height:8px;border-radius:50%;background:' + esc(d.riskcolor) + '"></span>' + esc(d.risklabel) + '</span>';
  }

  function renderExampleBody(card) {
    var ts = readTickers(card);
    var bar = ts.map(function (t, i) {
      return '<span class="ex-bar-seg" style="width:' + (+t.weight) + '%;background:' + SEG[i % 8] + '"></span>';
    }).join('');
    var legend = ts.map(function (t, i) {
      return '<div class="ex-leg-row">' +
        '<span class="ex-leg-dot" style="background:' + SEG[i % 8] + '"></span>' +
        '<span class="ex-leg-name">' + esc(t.name) + ' <span style="color:var(--ds-muted);font-size:10.5px;">' + esc(t.code) + '</span></span>' +
        '<span class="ex-leg-w">' + (+t.weight) + '%</span>' +
      '</div>';
    }).join('');
    return '<div class="exm-sec">구성</div>' +
      '<div class="ex-bar">' + bar + '</div>' +
      '<div class="ex-legend" style="margin-top:11px;">' + legend + '</div>' +
      '<div class="exm-desc">' + esc(card.dataset.desc) + '</div>';
  }

  function renderGuruBody(card) {
    var d = card.dataset;
    var holds = readJSON(d.holdings);
    var mx = holds.reduce(function (m, h) { return Math.max(m, h.weight_norm || 0); }, 0) || 1;
    var rows = holds.map(function (h) {
      var w = Math.floor((h.weight_norm / mx) * 100);
      return '<tr>' +
        '<td class="num exm-co">' + h.rank + '</td>' +
        '<td><span class="exm-tic">' + esc(h.ticker) + '</span> <span class="exm-co">' + esc(h.name) + '</span></td>' +
        '<td class="num exm-w">' + h.weight + '%</td>' +
        '<td class="num"><span class="exm-wbar-wrap"><span class="exm-wbar"><span style="width:' + w + '%"></span></span>' +
          '<span class="exm-w">' + h.weight_norm + '%</span></span></td>' +
      '</tr>';
    }).join('');
    var filed = d.filed ? ' (제출 ' + esc(d.filed) + ')' : '';
    return '<div class="exm-note"><span>⚠️</span><span><b>' + esc(d.period) + ' 공시 기준' + filed + '.</b> ' +
        'SEC 13F는 미국 상장 롱(매수) 주식만 분기 공시(최대 45일 지연)하며, 공매도·옵션·채권·해외자산은 포함되지 않습니다. 실제 현재 보유와 다를 수 있고, 투자자문이 아닙니다.</span></div>' +
      '<div class="exm-meta"><span>공시 종목 <b>' + esc(d.ntotal) + '</b>개</span>' +
        '<span>국내 시세 커버 <b>' + esc(d.ncovered) + '</b>개</span>' +
        '<span>커버 비중 <b>' + esc(d.covweight) + '%</b></span></div>' +
      '<div class="exm-sec">보유 종목 (' + holds.length + ')</div>' +
      '<table class="exm-table"><thead><tr><th style="width:30px">#</th><th>종목</th>' +
        '<th class="num">비중(13F)</th><th class="num" style="width:130px">포트폴리오 내</th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table>' +
      '<div class="exm-note" style="background:transparent;border:none;padding:8px 0 0;font-size:11px;">' +
        '‘비중(13F)’ = 전체 공시 대비. ‘포트폴리오 내’ = 국내 시세 커버 종목만 100%로 재정규화(백테스트 기준).</div>';
  }

  function openModal(card) {
    var modal = document.getElementById('exModal');
    if (!modal) return;
    activeCard = card;
    var type = card.dataset.type;
    document.getElementById('exmHead').innerHTML = renderHead(card.dataset);
    document.getElementById('exmBody').innerHTML = (type === 'guru') ? renderGuruBody(card) : renderExampleBody(card);
    // 액션 버튼 상태 초기화(이전 카드의 '담음' 잔상 제거)
    document.querySelectorAll('#exmActs .ex-btn').forEach(function (b) {
      b.classList.remove('added'); b.disabled = false;
    });
    document.querySelector('#exmActs [data-act="compare"]').textContent = '⚖ 비교';
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
  }
  function closeModal() {
    var modal = document.getElementById('exModal');
    if (modal) modal.hidden = true;
    document.body.style.overflow = '';
    activeCard = null;
  }

  // ── 비교 플로팅 바 ──
  function renderCmpBar() {
    var bar = document.getElementById('exCmpBar');
    var n = readCmp().length;
    if (!bar) return;
    document.getElementById('exCmpN').textContent = n;
    bar.classList.toggle('on', n > 0);
  }

  function runAct(act, card, btn) {
    if (act === 'analyze') analyze(card);
    else if (act === 'compare') compareAdd(card, btn);
    else if (act === 'save') save(card, btn);
  }

  function bindCards() {
    document.addEventListener('click', function (e) {
      // 모달 액션 버튼 → 활성 카드 대상
      var mAct = e.target.closest('#exmActs .ex-btn[data-act]');
      if (mAct) { if (activeCard) runAct(mAct.dataset.act, activeCard, mAct); return; }
      // 모달 닫기
      if (e.target.closest('[data-exm-close]')) { closeModal(); return; }
      // 카드 내 인라인 액션 버튼
      var btn = e.target.closest('.ex-card .ex-btn[data-act]');
      if (btn) {
        var c = btn.closest('[data-ex-card]');
        if (c) runAct(btn.dataset.act, c, btn);
        return;
      }
      // 카드 본문 클릭 → 상세 모달
      var card = e.target.closest('[data-ex-card]');
      if (card) openModal(card);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        var m = document.getElementById('exModal');
        if (m && !m.hidden) closeModal();
      }
    });
    var go = document.getElementById('exCmpGo');
    var clr = document.getElementById('exCmpClear');
    if (go) go.addEventListener('click', function () { location.href = '/risk-return'; });
    if (clr) clr.addEventListener('click', function () { sessionStorage.removeItem(RR_KEY); renderCmpBar(); });
  }

  bindTabs();
  bindCards();
  renderCmpBar();
})();
