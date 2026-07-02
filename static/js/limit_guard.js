// 납입 한도 soft 경고 공용 모듈 (2026-06-13 오너 결정)
// 흐름: 백엔드가 limit_confirm 에러(위반 전체 목록) → MMLimit.confirm 모달(예/아니오 +
// "오늘 하루 다시 묻지 않기") → 예: allow_limit_override=true 재요청 → 결과에 limit_warnings
// → MMLimit.banner로 결과 하단 큰 경고. 4탭(계산기·백테·은퇴·배당) 공유.

window.MMLimit = (function () {
  'use strict';

  const SKIP_KEY = 'mm_limit_skip_date';

  function _today() {
    const d = new Date();
    return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
  }

  function skipToday() {
    try { return localStorage.getItem(SKIP_KEY) === _today(); } catch (e) { return false; }
  }

  function _markSkip() {
    try { localStorage.setItem(SKIP_KEY, _today()); } catch (e) {}
  }

  // 백엔드 limit_confirm 에러 파싱 — e는 Error/문자열/객체 무엇이든 받음
  function parseError(e) {
    let raw = e;
    if (e instanceof Error) raw = e.message;
    if (typeof raw === 'string') {
      const i = raw.indexOf('{');
      if (i === -1) return null;
      try { raw = JSON.parse(raw.slice(i)); } catch (err) { return null; }
    }
    if (raw && raw.error === 'limit_confirm' && Array.isArray(raw.violations)) {
      return { violations: raw.violations };
    }
    return null;
  }

  // 진행 확인 모달 — resolve(true)=그래도 진행
  function confirm(violations) {
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.style.cssText =
        'position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:2000;' +
        'display:flex;align-items:center;justify-content:center;padding:16px;';

      const box = document.createElement('div');
      box.style.cssText =
        'background:var(--card,#fff);border-radius:16px;padding:22px;width:480px;' +
        'max-width:94vw;max-height:80vh;overflow-y:auto;box-shadow:0 8px 40px rgba(0,0,0,0.25);';

      const title = document.createElement('div');
      title.style.cssText = 'font-size:1rem;font-weight:800;margin-bottom:10px;color:var(--text,#222);';
      title.textContent = '⚠️ 납입 한도 초과';
      box.appendChild(title);

      const list = document.createElement('div');
      list.style.cssText = 'margin-bottom:12px;';
      violations.forEach(v => {
        const row = document.createElement('div');
        row.style.cssText =
          'font-size:0.82rem;color:#B26A00;background:var(--gold-pale,#FFF8E1);' +
          'border-radius:8px;padding:8px 10px;margin-bottom:6px;line-height:1.5;';
        row.textContent = v;
        list.appendChild(row);
      });
      box.appendChild(list);

      const q = document.createElement('div');
      q.style.cssText = 'font-size:0.85rem;font-weight:700;margin-bottom:10px;color:var(--text,#222);';
      q.textContent = '실제로는 이 금액을 납입할 수 없습니다. 그래도 시뮬레이션을 진행할까요?';
      box.appendChild(q);

      const skipLabel = document.createElement('label');
      skipLabel.style.cssText =
        'display:flex;align-items:center;gap:6px;font-size:0.78rem;' +
        'color:var(--text-muted,#777);margin-bottom:14px;cursor:pointer;';
      const skipChk = document.createElement('input');
      skipChk.type = 'checkbox';
      skipLabel.appendChild(skipChk);
      skipLabel.appendChild(document.createTextNode('오늘 하루 다시 묻지 않기'));
      box.appendChild(skipLabel);

      const btns = document.createElement('div');
      btns.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;';
      const noBtn = document.createElement('button');
      noBtn.textContent = '아니오';
      noBtn.style.cssText =
        'padding:9px 18px;background:var(--bg,#f5f5f5);color:var(--text,#222);' +
        'border:1.5px solid var(--border,#ddd);border-radius:8px;font-size:0.85rem;font-weight:700;cursor:pointer;';
      const yesBtn = document.createElement('button');
      yesBtn.textContent = '예, 진행합니다';
      yesBtn.style.cssText =
        'padding:9px 18px;background:#E65100;color:white;border:none;' +
        'border-radius:8px;font-size:0.85rem;font-weight:700;cursor:pointer;';
      btns.appendChild(noBtn);
      btns.appendChild(yesBtn);
      box.appendChild(btns);

      overlay.appendChild(box);
      document.body.appendChild(overlay);

      function done(ok) {
        if (ok && skipChk.checked) _markSkip();
        overlay.remove();
        resolve(ok);
      }
      noBtn.addEventListener('click', () => done(false));
      yesBtn.addEventListener('click', () => done(true));
    });
  }

  // 결과 하단 경고 배너 HTML — 작지 않게(오너 요구)
  function banner(warnings) {
    if (!warnings || !warnings.length) return '';
    const esc = window.mmEsc;  // E-1 공용화: 전역 mmEsc(base.html) 단일 구현 — 로컬 복붙 제거 (2026-07-03)
    return `
      <div style="margin-top:14px;padding:14px 16px;background:var(--red-pale,#FDECEA);border:1.5px solid var(--red,#C62828);border-radius:10px;">
        <div style="font-size:0.92rem;font-weight:800;color:var(--red,#C62828);margin-bottom:8px;">⚠️ 납입 한도 초과 시뮬레이션</div>
        <div style="font-size:0.84rem;color:var(--red,#C62828);line-height:1.6;margin-bottom:8px;">
          이 결과는 아래 항목이 <b>계좌 납입 한도를 초과</b>하는 조건으로 시뮬레이션되었으며,
          <b>실제 투자 시에는 이 조건으로 납입이 불가능할 수 있습니다.</b>
        </div>
        ${warnings.map(w => `<div style="font-size:0.8rem;color:var(--red,#C62828);margin-top:4px;">• ${esc(w)}</div>`).join('')}
      </div>`;
  }

  // 결과 컨테이너에 경고 배너 부착(없으면 제거) — 각 탭 render 끝에 호출
  function attach(containerId, warnings) {
    const el = document.getElementById(containerId);
    if (!el) return;
    let slot = el.querySelector(':scope > #mmLimitWarn');
    if (!slot) {
      slot = document.createElement('div');
      slot.id = 'mmLimitWarn';
      el.appendChild(slot);
    }
    slot.innerHTML = banner(warnings || []);
  }

  return { skipToday, parseError, confirm, banner, attach };
})();
