// mm_datepicker — 공용 날짜 선택기. 네이티브 <input type="date">를 가벼운 팝업으로 대체.
// 연/월 드롭다운 + 날짜 그리드 → 연도 스크롤·연>월>일 다단계 클릭 없이 빠르게 선택.
// 값은 그대로 YYYY-MM-DD(input.value) 유지 → 기존 코드 변경 0. base.html에서 전역 로드.
(function () {
  'use strict';
  if (window.__mmDatePickerInit) return;
  window.__mmDatePickerInit = true;

  var WD = ['일', '월', '화', '수', '목', '금', '토'];
  var pop = null, activeInput = null, viewY = 0, viewM = 0;

  // ── CSS 주입 ──
  var css = '' +
    '.mm-dp-input{cursor:pointer;}' +
    '.mm-dp-input::-webkit-calendar-picker-indicator{display:none;-webkit-appearance:none;}' +
    '.mm-dp-input::-webkit-inner-spin-button{display:none;}' +
    '.mmdp-pop{position:fixed;z-index:1000;width:278px;padding:12px;border-radius:var(--r-lg,12px);' +
      'background:var(--ds-canvas,#fff);border:1px solid var(--ds-hairline,#e5e7eb);box-shadow:var(--ds-shadow-lg,0 12px 32px rgba(0,0,0,.18));' +
      'font-family:inherit;color:var(--ds-ink,#111);}' +
    '[data-theme="dark"] .mmdp-pop{background:var(--ds-dark-el,#1c1f26);border-color:transparent;}' +
    '.mmdp-head{display:flex;align-items:center;gap:6px;margin-bottom:10px;}' +
    '.mmdp-nav{flex:0 0 auto;width:30px;height:30px;border-radius:8px;border:1px solid var(--ds-hairline,#e5e7eb);' +
      'background:var(--ds-soft,#f5f6f8);color:var(--ds-body,#333);cursor:pointer;font-size:15px;line-height:1;}' +
    '.mmdp-nav:hover{border-color:var(--brand,#1f6feb);color:var(--brand,#1f6feb);}' +
    '.mmdp-sel{flex:1;min-width:0;height:30px;border-radius:8px;border:1px solid var(--ds-hairline,#e5e7eb);' +
      'background:var(--ds-soft,#f5f6f8);color:var(--ds-ink,#111);font-family:inherit;font-size:13px;font-weight:700;' +
      'padding:0 6px;cursor:pointer;outline:none;}' +
    '.mmdp-sel:focus{border-color:var(--brand,#1f6feb);}' +
    '.mmdp-wd,.mmdp-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;}' +
    '.mmdp-wd{margin-bottom:4px;}' +
    '.mmdp-wd span{text-align:center;font-size:11px;font-weight:700;color:var(--ds-muted,#888);padding:4px 0;}' +
    '.mmdp-wd span:first-child{color:#cf202f;}.mmdp-wd span:last-child{color:#1f6feb;}' +
    '.mmdp-day{aspect-ratio:1;display:flex;align-items:center;justify-content:center;border:none;background:none;' +
      'border-radius:8px;cursor:pointer;font-family:var(--font-mono,monospace);font-size:13px;color:var(--ds-ink,#111);}' +
    '.mmdp-day:hover:not(:disabled){background:var(--ds-soft,#eef);}' +
    '.mmdp-day.empty{visibility:hidden;cursor:default;}' +
    '.mmdp-day:disabled{color:var(--ds-muted,#bbb);opacity:.4;cursor:default;}' +
    '.mmdp-day.today{box-shadow:inset 0 0 0 1.5px var(--ds-hairline,#ccc);}' +
    '.mmdp-day.sel{background:var(--brand,#1f6feb);color:var(--on-brand,#fff);font-weight:700;}' +
    '.mmdp-foot{display:flex;justify-content:center;margin-top:8px;}' +
    '.mmdp-today-btn{padding:6px 16px;border-radius:999px;border:1px solid var(--ds-hairline,#e5e7eb);' +
      'background:var(--ds-canvas,#fff);color:var(--ds-body,#333);font-family:inherit;font-size:12px;font-weight:700;cursor:pointer;}' +
    '[data-theme="dark"] .mmdp-today-btn{background:var(--ds-dark-el,#1c1f26);}' +
    '.mmdp-today-btn:hover{border-color:var(--brand,#1f6feb);color:var(--brand,#1f6feb);}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function ymd(y, m, d) { return y + '-' + pad(m + 1) + '-' + pad(d); }
  function parseYMD(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || '');
    return m ? { y: +m[1], m: +m[2] - 1, d: +m[3] } : null;
  }
  function yearOf(s, fb) { var m = /^(\d{4})/.exec(s || ''); return m ? +m[1] : fb; }

  // ── 네이티브 입력 → 팝업형으로 변환 ──
  function convert(inp) {
    if (inp.dataset.mmdp) return;
    inp.dataset.mmdp = '1';
    inp.classList.add('mm-dp-input');
    inp.setAttribute('readonly', 'readonly');   // 네이티브 편집·픽커 차단
    inp.addEventListener('mousedown', function (e) { e.preventDefault(); e.stopPropagation(); inp.blur(); open(inp); });
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(inp); }
    });
  }

  function ensurePop() {
    if (pop) return pop;
    pop = document.createElement('div');
    pop.className = 'mmdp-pop';
    pop.style.display = 'none';
    pop.addEventListener('mousedown', function (e) { e.stopPropagation(); }); // 외부클릭 닫힘 방지
    document.body.appendChild(pop);
    return pop;
  }

  function close() {
    if (pop) pop.style.display = 'none';
    activeInput = null;
  }

  function open(inp) {
    activeInput = inp;
    ensurePop();
    var cur = parseYMD(inp.value) || (function () { var t = new Date(); return { y: t.getFullYear(), m: t.getMonth(), d: t.getDate() }; })();
    viewY = cur.y; viewM = cur.m;
    render();
    pop.style.display = 'block';
    position(inp);
  }

  function position(inp) {
    var r = inp.getBoundingClientRect();
    var ph = pop.offsetHeight, pw = pop.offsetWidth;
    var top = r.bottom + 6, left = r.left;
    if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - 6); // 아래 공간 없으면 위로
    if (left + pw > window.innerWidth - 8) left = Math.max(8, window.innerWidth - pw - 8);
    pop.style.top = top + 'px';
    pop.style.left = left + 'px';
  }

  function bounds() {
    var inp = activeInput;
    var nextY = new Date().getFullYear() + 1;
    var minY = yearOf(inp.getAttribute('min'), 1985);
    var maxY = yearOf(inp.getAttribute('max'), nextY);
    if (maxY < minY) maxY = minY;
    return { minY: minY, maxY: maxY, min: inp.getAttribute('min') || null, max: inp.getAttribute('max') || null };
  }

  function render() {
    var b = bounds();
    if (viewY < b.minY) viewY = b.minY;
    if (viewY > b.maxY) viewY = b.maxY;
    var sel = parseYMD(activeInput.value);
    var today = new Date(); var tY = today.getFullYear(), tM = today.getMonth(), tD = today.getDate();

    var yOpts = '';
    for (var y = b.maxY; y >= b.minY; y--) yOpts += '<option value="' + y + '"' + (y === viewY ? ' selected' : '') + '>' + y + '년</option>';
    var mOpts = '';
    for (var mo = 0; mo < 12; mo++) mOpts += '<option value="' + mo + '"' + (mo === viewM ? ' selected' : '') + '>' + (mo + 1) + '월</option>';

    var first = new Date(viewY, viewM, 1).getDay();
    var dim = new Date(viewY, viewM + 1, 0).getDate();
    var cells = '';
    for (var i = 0; i < first; i++) cells += '<button class="mmdp-day empty" disabled></button>';
    for (var d = 1; d <= dim; d++) {
      var v = ymd(viewY, viewM, d);
      var dis = (b.min && v < b.min) || (b.max && v > b.max);
      var cls = 'mmdp-day';
      if (viewY === tY && viewM === tM && d === tD) cls += ' today';
      if (sel && sel.y === viewY && sel.m === viewM && sel.d === d) cls += ' sel';
      cells += '<button class="' + cls + '"' + (dis ? ' disabled' : '') + ' data-d="' + d + '">' + d + '</button>';
    }

    pop.innerHTML =
      '<div class="mmdp-head">' +
        '<button class="mmdp-nav" data-step="-1" type="button">‹</button>' +
        '<select class="mmdp-sel mmdp-y">' + yOpts + '</select>' +
        '<select class="mmdp-sel mmdp-m">' + mOpts + '</select>' +
        '<button class="mmdp-nav" data-step="1" type="button">›</button>' +
      '</div>' +
      '<div class="mmdp-wd">' + WD.map(function (w) { return '<span>' + w + '</span>'; }).join('') + '</div>' +
      '<div class="mmdp-grid">' + cells + '</div>' +
      '<div class="mmdp-foot"><button class="mmdp-today-btn" type="button">오늘</button></div>';

    pop.querySelector('.mmdp-y').addEventListener('change', function () { viewY = +this.value; render(); });
    pop.querySelector('.mmdp-m').addEventListener('change', function () { viewM = +this.value; render(); });
    pop.querySelectorAll('.mmdp-nav').forEach(function (btn) {
      btn.addEventListener('click', function () {
        viewM += +btn.dataset.step;
        if (viewM < 0) { viewM = 11; viewY--; } else if (viewM > 11) { viewM = 0; viewY++; }
        render();
      });
    });
    pop.querySelector('.mmdp-today-btn').addEventListener('click', function () {
      pick(ymd(tY, tM, tD));
    });
    pop.querySelectorAll('.mmdp-day[data-d]').forEach(function (btn) {
      if (btn.disabled) return;
      btn.addEventListener('click', function () { pick(ymd(viewY, viewM, +btn.dataset.d)); });
    });
  }

  function pick(v) {
    var inp = activeInput;
    inp.value = v;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
    close();
  }

  // ── 전역 바인딩 ──
  function scan(root) {
    (root || document).querySelectorAll('input[type="date"]:not([data-mmdp])').forEach(convert);
  }
  document.addEventListener('mousedown', function () { if (activeInput) close(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && activeInput) close(); });
  window.addEventListener('resize', function () { if (activeInput) position(activeInput); });
  window.addEventListener('scroll', function () { if (activeInput) position(activeInput); }, true);

  function start() {
    scan(document);
    // 동적 삽입(예: 포트폴리오 비교 오버레이) 대응
    new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        for (var j = 0; j < muts[i].addedNodes.length; j++) {
          var n = muts[i].addedNodes[j];
          if (n.nodeType !== 1) continue;
          if (n.matches && n.matches('input[type="date"]')) convert(n);
          if (n.querySelectorAll) scan(n);
        }
      }
    }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();

  window.mmDatePicker = { scan: scan };
})();
