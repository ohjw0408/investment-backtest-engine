// 투자대가 제너러티브 추상 아바타 — 이름(slug) 해시로 결정적 그라데이션+블롭 SVG.
// 실제 초상이 아니라 식별 불가능한 추상 → 퍼블리시티권/초상권 리스크 회피.
// 사용: <span class="..." data-gavatar="warren-buffett">WB</span>  (JS가 내부를 SVG로 교체, 실패 시 이니셜 fallback)
(function () {
  'use strict';

  function hash(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function rng(seed) {
    let s = seed >>> 0;
    return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
  }

  function avatarSVG(seed) {
    const h = hash(seed), r = rng(h);
    const base = Math.floor(r() * 360);
    const h2 = (base + 25 + Math.floor(r() * 70)) % 360;
    const h3 = (base + (r() < 0.5 ? -1 : 1) * (50 + Math.floor(r() * 90)) + 360) % 360;
    const h4 = (h2 + 40 + Math.floor(r() * 60)) % 360;
    const ang = Math.floor(r() * 360);
    const id = 'ga' + h.toString(36);
    const blob = (hue) =>
      `<circle cx="${(14 + r() * 52).toFixed(1)}" cy="${(14 + r() * 52).toFixed(1)}" r="${(20 + r() * 24).toFixed(1)}" fill="hsl(${hue} 82% 60%)" opacity="${(0.6 + r() * 0.35).toFixed(2)}"/>`;
    return `<svg viewBox="0 0 80 80" style="display:block;width:100%;height:100%" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="${id}" gradientTransform="rotate(${ang} 0.5 0.5)">
          <stop offset="0" stop-color="hsl(${base} 78% 54%)"/>
          <stop offset="1" stop-color="hsl(${h2} 76% 44%)"/>
        </linearGradient>
      </defs>
      <rect width="80" height="80" fill="url(#${id})"/>
      ${blob(h3)}${blob(h4)}
      <circle cx="${(r() * 80).toFixed(0)}" cy="${(r() * 80).toFixed(0)}" r="${(7 + r() * 11).toFixed(0)}" fill="#fff" opacity="${(0.07 + r() * 0.13).toFixed(2)}"/>
    </svg>`;
  }

  function render(el) {
    const seed = el.getAttribute('data-gavatar');
    if (!seed) return;
    el.style.overflow = 'hidden';
    el.innerHTML = avatarSVG(seed);
  }
  function init() { document.querySelectorAll('[data-gavatar]').forEach(render); }

  window.mmGuruAvatar = { svg: avatarSVG, render, init };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
