// base.html 공용 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 내용 무변경 이동.
// 테마 FOUC 방지·앱 감지·MM_LOGGED_IN/mmEsc는 실행 시점 제약으로 base.html 인라인 유지.
// ── 다크모드 토글 ──
(function () {
  const btn = document.getElementById('themeToggle');
  if (!btn) return;
  const cur = document.documentElement.getAttribute('data-theme');
  btn.textContent = cur === 'dark' ? '☀️' : '🌙';
  btn.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('mm-theme', next); } catch (e) {}
    // 차트가 테마 색을 생성 시점에 읽으므로 리로드로 일괄 적용
    location.reload();
  });
})();

// ── 모바일 사이드바 드로어 ──
(function () {
  const burger  = document.getElementById('navHamburger');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (!burger || !sidebar || !overlay) return;

  function closeDrawer() {
    sidebar.classList.remove('open');
    overlay.classList.remove('show');
  }
  burger.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    overlay.classList.toggle('show');
  });
  overlay.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDrawer();
  });
})();

// ── 네비 검색창 ──
const navInput    = document.getElementById('navSearchInput');
const navDropdown = document.getElementById('navSearchDropdown');

let searchTimer = null;

function badgeColor(badge) {
  if (badge === 'KR ETF' || badge === 'KOSPI' || badge === 'KOSDAQ') return '#1976D2';
  if (badge === 'US ETF' || badge === 'NASDAQ' || badge === 'NYSE')   return '#2E7D32';
  return '#78909C';
}

if (navInput) {
  navInput.addEventListener('input', (e) => {
    const q = e.target.value.trim();
    if (!q) { navDropdown.style.display = 'none'; return; }

    clearTimeout(searchTimer);
    navDropdown.innerHTML = '<div class="nav-search-hint">검색 중...</div>';
    navDropdown.style.display = 'block';

    searchTimer = setTimeout(async () => {
      try {
        const res  = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();

        if (!data.length) {
          navDropdown.innerHTML = '<div class="nav-search-hint">검색 결과 없음</div>';
          return;
        }

        navDropdown.innerHTML = data.map(item => `
          <div class="nav-search-result" onclick="selectSymbol(${mmJs(item.code)}, ${mmJs(item.name)})">
            <span class="nav-search-badge" style="background:${badgeColor(item.badge)}22; color:${badgeColor(item.badge)}">${mmEsc(item.badge)}</span>
            <div class="nav-search-info">
              <div class="nav-search-code">${mmEsc(item.name)}</div>
              <div class="nav-search-name">${mmEsc(item.code)}</div>
              ${item.subtitle ? `<div class="nav-search-sub">${mmEsc(item.subtitle)}</div>` : ''}
            </div>
            ${window.MM_LOGGED_IN ? `<button class="nav-search-bell" title="알림 설정" onclick="event.stopPropagation();mmAlert.openSymbol(${mmJs(item.code)},${mmJs(item.name)})">🔔</button>` : ''}
          </div>
        `).join('');

      } catch (err) {
        navDropdown.innerHTML = '<div class="nav-search-hint">오류가 발생했어요</div>';
      }
    }, 250);
  });

  document.addEventListener('click', (e) => {
    if (!navInput.closest('.nav-search-box').contains(e.target)) {
      navDropdown.style.display = 'none';
    }
  });

  navInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      navDropdown.style.display = 'none';
      navInput.blur();
    }
  });
}

function selectSymbol(code, name) {
  navInput.value = '';
  navDropdown.style.display = 'none';
  window.location.href = '/symbol/' + code;
}

function isInAppBrowser() {
  const ua = navigator.userAgent || '';
  return /KAKAOTALK|Instagram|FBAN|FBAV|FB_IAB|Line\/|naver|DaumApps|everytimeapp|TwitterAndroid|Twitter for iPhone|Pinterest|Snapchat|Threads|TikTok|Musical\.ly/i.test(ua);
}

function handleGoogleLogin(e) {
  // Capacitor 네이티브 앱: 시스템 브라우저로 OAuth → 딥링크 토큰 핸드오프(WebView 세션 차단 회피)
  try {
    if (window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()) {
      e.preventDefault();
      window.Capacitor.Plugins.Browser.open({ url: location.origin + '/auth/google?app=1' });
      return false;
    }
  } catch (err) {}
  if (!isInAppBrowser()) return true;
  e.preventDefault();
  const url = encodeURIComponent(location.href);
  const ua = navigator.userAgent || '';
  if (/KAKAOTALK/i.test(ua)) {
    location.href = 'kakaotalk://web/openExternal?url=' + url;
  } else {
    mmToast('현재 앱 내 브라우저에서는 Google 로그인이 차단됩니다.\n\n크롬 또는 사파리에서 직접 열어주세요:\nhttps://moneymilestone.co.kr');
  }
  return false;
}

// ── Capacitor 앱: OAuth 딥링크 콜백 → WebView 세션 교환 ──
(function () {
  try {
    if (!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform())) return;
    const App = window.Capacitor.Plugins.App, Browser = window.Capacitor.Plugins.Browser;
    if (!App) return;
    App.addListener('appUrlOpen', function (data) {
      const u = (data && data.url) || '';
      if (u.indexOf('moneymilestone://auth') === 0 || u.indexOf('intent://auth') === 0) {
        try { if (Browser) Browser.close(); } catch (e) {}
        const m = u.match(/[?&]token=([^&]+)/);
        if (m) location.href = '/auth/exchange?token=' + encodeURIComponent(m[1]);
      }
    });
  } catch (e) {}
})();

function mmAlertTargetUrl(data) {
  data = data || {};
  const meta = data.meta && typeof data.meta === 'object' ? data.meta : data;
  const explicit = String(data.target_url || data.targetUrl || meta.target_url || meta.targetUrl || '');
  if (explicit.startsWith('/')) return explicit;
  const code = data.code || meta.code;
  if (code) return '/symbol/' + encodeURIComponent(code);
  if (meta.cal || meta.type === 'calendar') return '/calendar';
  if (meta.portfolio_id) return '/myportfolios/' + encodeURIComponent(meta.portfolio_id);
  if (meta.breaches || meta.rule_type === 'rebalance_band' || meta.type === 'rebalance_band') return '/myassets';
  return '/alerts#inbox';
}
window.mmAlertTargetUrl = mmAlertTargetUrl;

// ── Capacitor 앱: 푸시 알림(FCM) 등록 — 로그인 후 권한 동의 시 토큰 서버 등록 ──
// force=true(설정서 직접 켤 때): asked/opt-out 무시하고 강제 권한요청·등록. 반환=성공 여부.
async function mmInitPush(force) {
  try {
    const Cap = window.Capacitor;
    if (!(Cap && Cap.isNativePlatform && Cap.isNativePlatform())) return false;  // 앱에서만
    if (!window.MM_LOGGED_IN) return false;                                       // 로그인 후만
    const Push = Cap.Plugins && Cap.Plugins.PushNotifications;
    if (!Push) return false;
    if (!force) {
      let st = null;
      try { st = await fetch('/api/push/status').then(r => r.ok ? r.json() : null); } catch (e) {}
      if (!(st && st.consented)) return false;                                    // 기본값 OFF
    } else {
      const cr = await fetch('/api/push/consent', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true })
      });
      if (!cr.ok) return false;
    }

    async function ensurePluginPermission(plugin, key) {
      if (!plugin || !plugin.checkPermissions || !plugin.requestPermissions) return true;
      let p = await plugin.checkPermissions();
      let v = p && p[key];
      if (v === 'prompt' || v === 'prompt-with-rationale') {
        p = await plugin.requestPermissions();
        v = p && p[key];
      }
      return v === 'granted';
    }

    const pushGranted = await ensurePluginPermission(Push, 'receive');
    if (!pushGranted) {
      if (force) {
        try {
          await fetch('/api/push/consent', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: false })
          });
        } catch (e) {}
      }
      return false;
    }
    // Foreground push is mirrored via LocalNotifications, which also needs notification permission.
    const LN = Cap.Plugins && Cap.Plugins.LocalNotifications;
    await ensurePluginPermission(LN, 'display');

    // 리스너 먼저 등록(토큰 이벤트 누락 방지) -> register
    let settled = false;
    let finishRegistration = function () {};
    const waitForRegistration = new Promise(function (resolve) {
      finishRegistration = function (ok) {
        if (settled) return;
        settled = true;
        resolve(!!ok);
      };
    });
    await Push.addListener('registration', async function (t) {
      try {
        const r = await fetch('/api/push/register', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: t.value, platform: 'android' })
        });
        finishRegistration(r.ok);
      } catch (e) { finishRegistration(false); }
    });
    await Push.addListener('registrationError', function (e) { console.warn('[push] reg error', e); finishRegistration(false); });
    setTimeout(function () { finishRegistration(false); }, 10000);

    if (!window.MM_PUSH_EVENT_LISTENERS_BOUND) {
      window.MM_PUSH_EVENT_LISTENERS_BOUND = true;
      // 앱 포그라운드서 푸시 수신 -> 시스템 알림 재현(로컬 알림) + 인앱 토스트 + 종 갱신
      await Push.addListener('pushNotificationReceived', function (n) {
        try {
          const t = (n && n.title) || (n && n.notification && n.notification.title) || '알림';
          const bd = (n && n.body) || (n && n.notification && n.notification.body) || '';
          if (typeof mmToast === 'function') mmToast('🔔 ' + t + (bd ? ' · ' + bd : ''), 'ok');
          if (window.mmRefreshBell) window.mmRefreshBell();
          const LN = Cap.Plugins && Cap.Plugins.LocalNotifications;
          if (LN) LN.schedule({ notifications: [{
            id: Math.floor(Math.random() * 2000000000) + 1,
            title: t,
            body: bd,
            channelId: 'money_alerts_high_v1'
          }] });
        } catch (e) {}
      });
      // 알림 탭 -> 관련 화면 이동(종목 알림=종목 페이지, 그 외=수신함)
      await Push.addListener('pushNotificationActionPerformed', function (a) {
        const d = (a && a.notification && a.notification.data) || {};
        location.href = mmAlertTargetUrl(d);
      });
    }
    await Push.register();
    return await waitForRegistration;
  } catch (e) { return false; }   // 푸시 실패해도 앱 정상
}
window.mmInitPush = mmInitPush;
(function () {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { mmInitPush(); });
  else mmInitPush();
})();

function mmCopyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none;';
  document.body.appendChild(ta);
  ta.focus(); ta.select();
  try { document.execCommand('copy'); } catch(e) {}
  document.body.removeChild(ta);
  return Promise.resolve();
}

// ── 브랜드 다이얼로그 헬퍼 (전역) — native alert/confirm/prompt 대체 ──
// 단일 진실원천: DOM 동적생성 + ds 컴포넌트 클래스. 페이지별 마크업 불요.
function _mmEscH(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}

// 상단 중앙 슬라이드다운 토스트. type: ''(정보) | 'ok' | 'err'
function mmToast(msg, type) {
  let wrap = document.getElementById('mmToastWrap');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'mmToastWrap';
    wrap.className = 'ds-toast-wrap top';
    document.body.appendChild(wrap);
  }
  const t = document.createElement('div');
  t.className = 'ds-toast top' + (type === 'ok' ? ' ds-toast-ok' : type === 'err' ? ' ds-toast-err' : '');
  t.textContent = msg;
  wrap.appendChild(t);
  setTimeout(() => {
    t.style.transition = 'opacity .25s, transform .25s';
    t.style.opacity = '0';
    t.style.transform = 'translateY(-10px)';
    setTimeout(() => t.remove(), 260);
  }, type === 'err' ? 3400 : 2400);
}

// 확인 다이얼로그 → Promise<boolean>. opts: {sub, ok, cancel, danger}
function mmConfirm(msg, opts) {
  opts = opts || {};
  return new Promise(resolve => {
    const ov = document.createElement('div');
    ov.className = 'ds-overlay';
    ov.innerHTML = `
      <div class="ds-modal" role="dialog" aria-modal="true" style="max-width:400px;">
        <div class="ds-modal-head"><div class="ds-modal-title">${_mmEscH(msg)}</div></div>
        ${opts.sub ? `<div class="ds-modal-body">${_mmEscH(opts.sub)}</div>` : '<div style="height:6px;"></div>'}
        <div class="ds-modal-foot">
          <button class="ds-btn ds-btn-secondary" data-act="no">${_mmEscH(opts.cancel || '취소')}</button>
          <button class="ds-btn ${opts.danger ? 'ds-btn-danger' : 'ds-btn-primary'}" data-act="yes">${_mmEscH(opts.ok || '확인')}</button>
        </div>
      </div>`;
    document.body.appendChild(ov);
    requestAnimationFrame(() => ov.classList.add('open'));
    const close = (val) => { ov.classList.remove('open'); setTimeout(() => ov.remove(), 200); resolve(val); };
    ov.addEventListener('click', e => {
      if (e.target === ov) return close(false);
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (act === 'yes') close(true); else if (act === 'no') close(false);
    });
  });
}

// 입력 다이얼로그 → Promise<string|null>. opts: {value, placeholder, ok}
function mmPrompt(title, opts) {
  opts = opts || {};
  return new Promise(resolve => {
    const ov = document.createElement('div');
    ov.className = 'ds-overlay';
    ov.innerHTML = `
      <div class="ds-modal" role="dialog" aria-modal="true" style="max-width:400px;">
        <div class="ds-modal-head"><div class="ds-modal-title">${_mmEscH(title)}</div></div>
        <div class="ds-modal-body">
          <input type="text" class="mm-prompt-input" value="${_mmEscH(opts.value || '')}" placeholder="${_mmEscH(opts.placeholder || '')}"
            style="width:100%;box-sizing:border-box;padding:11px 14px;border:1.5px solid var(--ds-hairline);border-radius:var(--r-md);font-size:var(--fs-sm);background:var(--ds-soft);color:var(--ds-ink);outline:none;">
        </div>
        <div class="ds-modal-foot">
          <button class="ds-btn ds-btn-secondary" data-act="no">취소</button>
          <button class="ds-btn ds-btn-primary" data-act="yes">${_mmEscH(opts.ok || '확인')}</button>
        </div>
      </div>`;
    document.body.appendChild(ov);
    const input = ov.querySelector('.mm-prompt-input');
    requestAnimationFrame(() => { ov.classList.add('open'); input.focus(); input.select(); });
    const close = (val) => { ov.classList.remove('open'); setTimeout(() => ov.remove(), 200); resolve(val); };
    input.addEventListener('keydown', e => { if (e.key === 'Enter') close(input.value); else if (e.key === 'Escape') close(null); });
    ov.addEventListener('click', e => {
      if (e.target === ov) return close(null);
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (act === 'yes') close(input.value); else if (act === 'no') close(null);
    });
  });
}

// ── 알림 종(로그인 시) ──
(function () {
  const wrap = document.getElementById('mmBellWrap');
  if (!wrap) return;
  const btn = document.getElementById('mmBell');
  const dd = document.getElementById('mmBellDd');
  const badge = document.getElementById('mmBellBadge');
  const list = document.getElementById('mmBellList');

  function fmtAgo(iso) {
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return '방금'; if (s < 3600) return Math.floor(s / 60) + '분 전';
    if (s < 86400) return Math.floor(s / 3600) + '시간 전';
    return new Date(iso).toLocaleDateString('ko-KR');
  }

  let _alPrevCount = null;   // 직전 미읽음 수(증가 감지용). null=최초 로드(토스트 억제)
  async function refreshCount() {
    try {
      const j = await (await fetch('/api/alerts/unread-count')).json();
      const n = j.count || 0;
      badge.style.display = n ? 'block' : 'none';
      badge.textContent = n > 99 ? '99+' : n;
      // 탭 켜진 중 새 알림 도착 → 토스트(웹 인앱 알림). 최초 로드/감소 시엔 안 띄움.
      if (_alPrevCount !== null && n > _alPrevCount && typeof mmToast === 'function') {
        try {
          const e = (await (await fetch('/api/alerts/events?limit=1')).json()).events || [];
          if (e.length) {
            const more = (n - _alPrevCount) > 1 ? ` 외 ${n - _alPrevCount - 1}건` : '';
            mmToast('🔔 ' + e[0].title + (e[0].body ? ' · ' + e[0].body : '') + more, 'ok');
          }
        } catch (_) {}
      }
      _alPrevCount = n;
    } catch (e) {}
  }
  window.mmRefreshBell = refreshCount;

  async function loadList() {
    list.innerHTML = '<div class="mm-bell-empty">불러오는 중…</div>';
    try {
      const j = await (await fetch('/api/alerts/events?limit=12')).json();
      const evs = j.events || [];
      if (!evs.length) { list.innerHTML = '<div class="mm-bell-empty">받은 알림이 없어요.</div>'; return; }
      list.innerHTML = evs.map(e => {
        const target = mmAlertTargetUrl(e);
        return `
        <div class="mm-bell-it ${e.read_at ? '' : 'unread'}" data-id="${e.id}" data-target="${_mmEscH(target)}">
          <div class="mm-bell-it-t">${_mmEscH(e.title)}</div>
          <div class="mm-bell-it-b">${_mmEscH(e.body)}</div>
          <div class="mm-bell-it-time">${fmtAgo(e.created_at)}</div>
        </div>`;
      }).join('');
      list.querySelectorAll('.mm-bell-it').forEach(el => el.onclick = async () => {
        await fetch(`/api/alerts/events/${el.dataset.id}/read`, { method: 'POST' });
        el.classList.remove('unread');
        refreshCount();
        location.href = el.dataset.target || '/alerts#inbox';
      });
    } catch (e) { list.innerHTML = '<div class="mm-bell-empty">오류가 발생했어요.</div>'; }
  }

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = dd.classList.toggle('open');
    if (open) loadList();
  });
  document.addEventListener('click', (e) => {
    if (!wrap.contains(e.target)) dd.classList.remove('open');
  });

  refreshCount();
  setInterval(refreshCount, 60000);
})();

// ── 상단 nav 드롭다운 hover-intent (트리거→메뉴 갭 이동 시 닫힘 방지) ──
(function () {
  document.querySelectorAll('.mmnav-grp').forEach(grp => {
    let t = null;
    const open  = () => { clearTimeout(t); grp.classList.add('mmnav-open'); };
    const close = () => { clearTimeout(t); t = setTimeout(() => grp.classList.remove('mmnav-open'), 220); };
    grp.addEventListener('mouseenter', open);
    grp.addEventListener('mouseleave', close);
    // 메뉴 항목 클릭 시 즉시 닫기(네비게이션)
    grp.querySelectorAll('.mmnav-menu a').forEach(a => a.addEventListener('click', () => grp.classList.remove('mmnav-open')));
  });
})();
