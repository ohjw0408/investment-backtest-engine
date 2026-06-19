// 포트폴리오 즐겨찾기 공용 위젯 (B1)
// 각 페이지가 MMFav.init({mount, getTickers, setTickers})로 결합한다.
//   getTickers(): [{code, name, badge, weight}]  — weight는 % (0~100)
//   setTickers(list): 같은 형식을 받아 페이지 상태에 반영 + 리렌더
// 서버 API: GET /api/portfolio/list · POST /api/portfolio/save · DELETE /api/portfolio/<id>
// 로그인 전용 — 비로그인 시 안내만 표시.

window.MMFav = (function () {
  'use strict';

  function init(opts) {
    const mountEl = typeof opts.mount === 'string'
      ? document.getElementById(opts.mount) : opts.mount;
    if (!mountEl) return;

    const state = { loggedIn: false, items: [] };

    // ── DOM (사용자 입력 이름이 들어가므로 innerHTML 금지) ──
    const bar = document.createElement('div');
    bar.className = 'fav-bar';

    const select = document.createElement('select');
    select.className = 'fav-select';

    const saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'fav-btn';
    saveBtn.textContent = '저장';
    saveBtn.title = '현재 종목 구성을 즐겨찾기로 저장';

    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'fav-btn fav-btn-danger';
    delBtn.textContent = '삭제';
    delBtn.title = '선택한 즐겨찾기 삭제';

    bar.appendChild(select);
    bar.appendChild(saveBtn);
    bar.appendChild(delBtn);
    mountEl.appendChild(bar);

    function renderOptions() {
      select.textContent = '';
      const ph = document.createElement('option');
      ph.value = '';
      ph.textContent = state.loggedIn
        ? (state.items.length ? '★ 즐겨찾기 불러오기' : '★ 저장된 포트폴리오 없음')
        : '★ 즐겨찾기 (로그인 필요)';
      select.appendChild(ph);
      state.items.forEach(p => {
        const o = document.createElement('option');
        o.value = String(p.id);
        o.textContent = p.name;
        select.appendChild(o);
      });
      select.disabled = !state.loggedIn;
    }

    async function refresh() {
      try {
        // /api/me 선확인 — 비로그인 시 list 401 콘솔 노이즈 방지 (loadProfile 패턴)
        const me = await fetch('/api/me').then(r => r.json());
        if (!me.logged_in) { state.loggedIn = false; state.items = []; }
        else {
          const res = await fetch('/api/portfolio/list');
          if (res.ok) { state.loggedIn = true; state.items = await res.json(); }
        }
      } catch (e) { /* 네트워크 오류 — 표시만 유지 */ }
      renderOptions();
    }

    function requireLogin() {
      if (state.loggedIn) return true;
      mmToast('즐겨찾기는 로그인 후 사용할 수 있어요.', 'err');
      return false;
    }

    select.addEventListener('change', () => {
      const id = Number(select.value);
      if (!id) return;
      const item = state.items.find(p => p.id === id);
      if (item) opts.setTickers(item.tickers.map(t => ({ ...t })));
    });

    saveBtn.addEventListener('click', async () => {
      if (!requireLogin()) return;
      const tickers = opts.getTickers();
      if (!tickers || !tickers.length) {
        mmToast('저장할 종목이 없어요. 먼저 종목을 추가해주세요.', 'err');
        return;
      }
      const selected = state.items.find(p => p.id === Number(select.value));
      const name = ((await mmPrompt('포트폴리오 이름', { value: selected ? selected.name : '', placeholder: '예: 안정형 60/40', ok: '저장' })) || '').trim();
      if (!name) return;
      const existing = state.items.find(p => p.name === name);
      if (existing && !(await mmConfirm(`"${name}" 즐겨찾기를 덮어쓸까요?`, { ok: '덮어쓰기' }))) return;
      try {
        const res = await fetch('/api/portfolio/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: existing ? existing.id : null, name, tickers }),
        });
        const data = await res.json();
        if (!res.ok) { mmToast(data.error || '저장에 실패했어요.', 'err'); return; }
        await refresh();
        const saved = state.items.find(p => p.name === name);
        if (saved) select.value = String(saved.id);
        mmToast('즐겨찾기에 저장됐어요.', 'ok');
      } catch (e) { mmToast('저장에 실패했어요. 네트워크를 확인해주세요.', 'err'); }
    });

    delBtn.addEventListener('click', async () => {
      if (!requireLogin()) return;
      const id = Number(select.value);
      const item = state.items.find(p => p.id === id);
      if (!item) { mmToast('삭제할 즐겨찾기를 먼저 선택해주세요.', 'err'); return; }
      if (!(await mmConfirm(`"${item.name}" 즐겨찾기를 삭제할까요?`, { ok: '삭제', danger: true }))) return;
      try {
        const res = await fetch(`/api/portfolio/${id}`, { method: 'DELETE' });
        if (!res.ok) { mmToast('삭제에 실패했어요.', 'err'); return; }
        await refresh();
        mmToast('삭제됐어요.', 'ok');
      } catch (e) { mmToast('삭제에 실패했어요. 네트워크를 확인해주세요.', 'err'); }
    });

    renderOptions();
    refresh();
  }

  return { init };
})();
