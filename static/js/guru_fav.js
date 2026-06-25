// 투자대가 포트폴리오 → 즐겨찾기(저장 포트폴리오) 저장. 카드/상세 공용.
// 이름 규약: "<한글이름>의 포트폴리오". 동명 있으면 덮어쓰기.
(function () {
  'use strict';

  async function mmSaveGuru(slug, nameKo, btn) {
    try {
      const me = await fetch('/api/me').then(r => r.json());
      if (!me.logged_in) {
        if (typeof mmToast === 'function') mmToast('로그인하면 이 포트폴리오를 즐겨찾기로 저장할 수 있어요.', 'err');
        setTimeout(() => { location.href = '/auth/google'; }, 1000);
        return;
      }
      if (btn) btn.disabled = true;
      const d = await fetch('/api/gurus/' + slug + '/portfolio').then(r => r.json());
      if (!d.tickers || !d.tickers.length) {
        if (typeof mmToast === 'function') mmToast('저장할 종목이 없어요.', 'err');
        if (btn) btn.disabled = false;
        return;
      }
      const name = nameKo + '의 포트폴리오';
      // weight: 0~1 분수 → % (0~100)
      const tickers = d.tickers.map(t => ({
        code: t.code, name: t.name || t.code, weight: Math.round((t.weight || 0) * 1000) / 10,
      }));
      // 동명 즐겨찾기 있으면 id 넘겨 덮어쓰기(중복 방지)
      let existingId = null;
      try {
        const list = await fetch('/api/portfolio/list').then(r => r.ok ? r.json() : []);
        const e = list.find(p => p.name === name);
        if (e) existingId = e.id;
      } catch (_) {}
      const res = await fetch('/api/portfolio/save', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: existingId, name, tickers }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (typeof mmToast === 'function') mmToast(j.error || '저장에 실패했어요.', 'err');
        if (btn) btn.disabled = false;
        return;
      }
      if (typeof mmToast === 'function') mmToast('⭐ ‘' + name + '’ 저장 완료 · 내 포트폴리오에서 확인하세요.', 'ok');
      if (btn) { btn.disabled = false; btn.classList.add('saved'); }
    } catch (e) {
      if (typeof mmToast === 'function') mmToast('저장에 실패했어요. 잠시 후 다시 시도해주세요.', 'err');
      if (btn) btn.disabled = false;
    }
  }

  window.mmSaveGuru = mmSaveGuru;
})();
