// 포트폴리오 예시 — 지역 탭 전환 + 카드 액션 3종(분석/비교/저장) 핸드오프.
// 분석 → /backtest(mm_bt_preload), 비교 → /risk-return(mm_rr_preload 누적), 저장 → /api/portfolio/save.
(function () {
  'use strict';

  var RR_KEY = 'mm_rr_preload';
  var MAX_CMP = 5;

  function toast(msg, kind) { if (typeof mmToast === 'function') mmToast(msg, kind); }
  function readTickers(card) { try { return JSON.parse(card.dataset.tickers) || []; } catch (e) { return []; } }
  function readCmp() { try { return JSON.parse(sessionStorage.getItem(RR_KEY)) || []; } catch (e) { return []; } }
  function writeCmp(list) { sessionStorage.setItem(RR_KEY, JSON.stringify(list)); }

  // ── 지역 탭 ──
  function bindTabs() {
    var tabs = document.getElementById('exTabs');
    if (!tabs) return;
    tabs.addEventListener('click', function (e) {
      var b = e.target.closest('.ex-tab');
      if (!b) return;
      var region = b.dataset.region;
      tabs.querySelectorAll('.ex-tab').forEach(function (t) { t.classList.toggle('on', t === b); });
      document.querySelectorAll('.ex-panel').forEach(function (p) {
        p.classList.toggle('on', p.dataset.panel === region);
      });
    });
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
      autorun: true,
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

  // ── 비교 플로팅 바 ──
  function renderCmpBar() {
    var bar = document.getElementById('exCmpBar');
    var n = readCmp().length;
    if (!bar) return;
    document.getElementById('exCmpN').textContent = n;
    bar.classList.toggle('on', n > 0);
  }

  function bindCards() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.ex-btn[data-act]');
      if (!btn) return;
      var card = btn.closest('[data-ex-card]');
      if (!card) return;
      var act = btn.dataset.act;
      if (act === 'analyze') analyze(card);
      else if (act === 'compare') compareAdd(card, btn);
      else if (act === 'save') save(card, btn);
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
