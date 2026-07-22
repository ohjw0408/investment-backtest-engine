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

// ── Capacitor 앱: 안드로이드 뒤로가기 ──
// 기본 동작(webView.canGoBack()이면 goBack, 아니면 종료)만으로는 홈에 도달한 뒤에도
// WebView 히스토리가 남아 있어 아무리 눌러도 앱이 안 닫힌다(오너 보고 2026-07-22).
// 열린 오버레이 닫기 → 이전 페이지 → 홈에서 두 번 누르면 종료, 순으로 직접 처리한다.
(function () {
  try {
    const Cap = window.Capacitor;
    if (!(Cap && Cap.isNativePlatform && Cap.isNativePlatform())) return;
    const App = Cap.Plugins && Cap.Plugins.App;
    if (!App) return;

    let exitArmedUntil = 0;

    function closeOpenOverlay() {
      const sidebar = document.getElementById('sidebar');
      if (sidebar && sidebar.classList.contains('open')) {
        sidebar.classList.remove('open');
        const ov = document.getElementById('sidebarOverlay');
        if (ov) ov.classList.remove('show');
        return true;
      }
      const bell = document.getElementById('mmBellDd');
      if (bell && bell.classList.contains('open')) { bell.classList.remove('open'); return true; }
      const modal = document.querySelector('.modal-overlay.show');
      if (modal) { modal.classList.remove('show'); return true; }
      return false;
    }

    App.addListener('backButton', function () {
      if (closeOpenOverlay()) return;
      if (location.pathname !== '/') {
        if (history.length > 1) history.back(); else location.href = '/';
        return;
      }
      if (Date.now() < exitArmedUntil) { App.exitApp(); return; }
      exitArmedUntil = Date.now() + 2000;
      mmToast('한 번 더 누르면 종료됩니다');
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

// OS(안드로이드) 알림 권한 상태. 서버쪽 동의와 별개 — 서버가 '동의함'이어도
// 재설치·권한 철회로 OS 권한이 없으면 알림은 안 온다.
// 'granted' | 'prompt' | 'denied' | 'unsupported'
async function mmPushPermission() {
  try {
    const Cap = window.Capacitor;
    if (!(Cap && Cap.isNativePlatform && Cap.isNativePlatform())) return 'unsupported';
    const Push = Cap.Plugins && Cap.Plugins.PushNotifications;
    if (!Push || !Push.checkPermissions) return 'unsupported';
    const p = await Push.checkPermissions();
    const v = p && p.receive;
    if (v === 'granted') return 'granted';
    if (v === 'prompt' || v === 'prompt-with-rationale') return 'prompt';
    return 'denied';
  } catch (e) { return 'unsupported'; }
}
window.mmPushPermission = mmPushPermission;
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

/* ── 글자배율 대응: 긴 텍스트를 컨테이너 폭에 맞춤 (mmFitText) ────────────────
 *
 * Android WebView 는 시스템 "글자 크기" 설정을 textZoom 으로 CSS 폰트에 곱한다.
 * 배율을 크게 쓰는 사용자(주로 40~50대)의 폰에서는 CSS 미디어쿼리로는 손댈 수
 * 없는 크기로 글자가 커진다. 줄바꿈이 불가능한 한 덩어리(금액 `₩75,808,745`,
 * 퍼센트 `-24.18%`)는 그대로 카드 밖으로 나가 잘린다.
 *
 * 원칙: 배율과 싸우지 않는다. 사용자가 일부러 키운 것이므로 강제로 되돌리면
 * 오히려 못 읽는다. 다만 "잘려서 안 보이는 것"보다는 "조금 작아도 다 보이는 것"이
 * 낫기 때문에, 넘칠 때만 minPx 를 하한으로 축소한다. 넘치지 않으면 손대지 않는다.
 */
function mmFitText(el, minPx) {
  if (!el) return;
  if (!el.parentElement) return;
  minPx = minPx || 14;

  el.style.fontSize = '';                       // CSS 원래 크기로 되돌린 뒤 재측정
  const base = parseFloat(getComputedStyle(el).fontSize);
  if (!base) return;

  /* 가용 폭 = "잘리기 시작하는 지점까지의 거리".
     바로 위 부모의 clientWidth 를 쓰면 안 된다. 부모 자신이 이미 카드 밖으로 밀려나
     있으면(내 자산 히어로에서 실제로 그랬다) 부모 폭이 카드보다 넓게 나와 "맞는다"고
     오판하고 축소가 걸리지 않는다. 실제로 내용을 자르는 조상을 찾아 거기까지의
     남은 거리를 재야 한다. */
  let clipper = el.parentElement;
  for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
    if (getComputedStyle(p).overflowX !== 'visible') { clipper = p; break; }
  }
  const cRect = clipper.getBoundingClientRect();
  const cStyle = getComputedStyle(clipper);
  const rightEdge = cRect.right
    - parseFloat(cStyle.borderRightWidth || 0)
    - parseFloat(cStyle.paddingRight || 0);
  const avail = rightEdge - el.getBoundingClientRect().left;
  if (!(avail > 0)) return;

  /* 요소의 getBoundingClientRect().width 를 쓰면 안 된다. min-width:0 으로 박스가 이미
     컨테이너 폭에 맞춰 줄어든 상태라 항상 "맞는다"고 나오고, 정작 줄바꿈이 안 되는
     금액 문자열은 박스 밖으로 삐져나가 카드에 잘린다. 글자 자체의 폭을 재야 한다. */
  const textWidth = () => {
    const r = document.createRange();
    r.selectNodeContents(el);
    return r.getBoundingClientRect().width;
  };

  let w = textWidth();
  if (w <= avail) return;                       // 안 넘치면 개입하지 않음

  // 폭은 글자크기에 거의 비례 → 비율로 한 번에 근사(리플로우 최소화)
  let size = Math.max(minPx, Math.floor(base * avail / w));
  el.style.fontSize = size + 'px';

  // 자간·반올림 때문에 남는 오차는 1px씩 보정
  for (let i = 0; i < 6 && size > minPx; i++) {
    if (textWidth() <= avail) break;
    size -= 1;
    el.style.fontSize = size + 'px';
  }
}
window.mmFitText = mmFitText;

/* ── 금액 입력란 콤마 표시 (mmMoneyInput) ────────────────────────────────────
 *
 * 목적: 평단가·초기투자금 같은 금액 칸에서 타이핑하는 동안 화면에 1,980,000 처럼
 * 보이게 한다. 저장·계산에 쓰이는 값은 그대로 1980000 이어야 한다.
 *
 * 왜 이렇게 구현했나
 *   `<input type="number">` 는 콤마를 담지 못한다(명세상 값이 유효한 부동소수점
 *   문자열이어야 하고, 콤마가 들어가면 브라우저가 값을 빈 문자열로 취급한다).
 *   그래서 `type="text"` 로 바꿀 수밖에 없는데, 그 순간 이 칸을 읽는 모든 코드가
 *   "1,980,000" 을 받게 되고 `parseFloat` 은 **1** 을 반환한다. 예외도 안 나고
 *   계산도 정상적으로 돌아간다 — 결과만 조용히 틀린다.
 *
 *   읽는 지점이 앱 전체에 400곳 가까이 흩어져 있어 하나씩 고치면 반드시 빠뜨린다.
 *   그래서 **해당 엘리먼트에만** `value` 접근자를 덮어써서, 화면에는 콤마가 보이되
 *   `el.value` 로 읽으면 언제나 콤마 없는 숫자가 나오도록 했다. 기존 읽기 코드는
 *   한 줄도 바꾸지 않아도 되고, 앞으로 추가될 코드도 자동으로 안전하다.
 *
 * 적용 전제(확인함): 이 앱에는 `valueAsNumber`·네이티브 `<form>` 전송·`stepUp()`·
 * `checkValidity()` 사용처가 없다. 셋 다 type=number 에 묶인 기능이라 전환 시
 * 깨질 수 있는 지점이었다.
 */
function mmMoneyInput(el) {
  if (!el || el.dataset.mmMoney) return;
  el.dataset.mmMoney = '1';

  const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
  const rawOf = s => String(s == null ? '' : s).replace(/,/g, '');

  function fmt(s) {
    const v = rawOf(s);
    if (v === '' || v === '-') return v;
    const m = v.match(/^(-?)(\d*)(\.\d*)?$/);
    if (!m) return v;                       // 숫자 형태가 아니면 건드리지 않는다
    const grouped = m[2].replace(/^0+(?=\d)/, '').replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return m[1] + grouped + (m[3] || '');
  }

  el.type = 'text';                          // number 는 콤마도 캐럿 제어도 불가
  el.setAttribute('inputmode', 'numeric');
  el.setAttribute('autocomplete', 'off');

  Object.defineProperty(el, 'value', {
    configurable: true,
    get() { return rawOf(desc.get.call(this)); },   // 읽기 = 항상 콤마 없는 숫자
    set(v) { desc.set.call(this, fmt(v)); },        // 쓰기 = 자동으로 콤마 표시
  });

  // 타이핑 중 재포맷 — 캐럿은 "앞에 있던 숫자 개수"를 기준으로 되돌린다
  el.addEventListener('input', function () {
    const before = desc.get.call(el);
    const caret = el.selectionStart;
    const digitsLeft = before.slice(0, caret).replace(/\D/g, '').length;
    const after = fmt(before);
    if (after === before) return;
    desc.set.call(el, after);
    let i = 0, seen = 0;
    while (i < after.length && seen < digitsLeft) {
      if (/\d/.test(after[i])) seen++;
      i++;
    }
    try { el.setSelectionRange(i, i); } catch (e) {}
  });

  desc.set.call(el, fmt(desc.get.call(el)));   // 서버가 심어둔 초기값도 포맷
}
window.mmMoneyInput = mmMoneyInput;

/* 콤마를 붙일 금액(원) 칸 목록. 수익률·기간·나이·수량은 대상이 아니다 —
   "7.5%"·"30년"·"만 58세"에 콤마가 낄 일이 없다.
   ⚠️ tsCurrentValue·tsCostBasis(ISA 전환)는 의도적으로 제외했다. 그 페이지는
   계산을 자동으로 돌릴 수 없어 골든 마스터로 결과 보존을 검증할 수 없었다. */
window.MM_MONEY_INPUT_IDS = [
  'btSeed', 'btMonthly',
  'initialCapital', 'monthlyContrib',
  'dtTargetDiv', 'dtSeedVal', 'dtSeedStep', 'dtMonthlyVal', 'dtMonthlyStep',
  'purchaseAmount', 'holdingAvgPrice', 'manualPriceInput',
  'pdAmount',
  'simSeed', 'simMonthly', 'simWithdraw', 'wdSeed', 'wdWithdraw',
  'earnedIncome',
  'stCpInitial', 'stCpMonthly', 'stDvInitial', 'stDvMonthly',
  'stDgTarget', 'stInfCost', 'stRvAmount',
];

(function () {
  function applyMoneyInputs() {
    window.MM_MONEY_INPUT_IDS.forEach(id => mmMoneyInput(document.getElementById(id)));
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyMoneyInputs);
  } else {
    applyMoneyInputs();
  }
  // 모달 안에 나중에 그려지는 칸(내 자산 종목 추가 등)도 잡는다
  window.mmApplyMoneyInputs = applyMoneyInputs;
})();
