/* alert_widget.js — 어디서나 여는 알림 설정 모달(토스풍 바텀시트).
 * window.mmAlert.openSymbol(code, name)
 * window.mmAlert.openAssets()         — 내 자산(리밸런싱 + 종목별)
 * window.mmAlert.openPortfolio(id)    — 저장 포트폴리오(구성종목별)
 * 로그인 안 됐으면 로그인 유도. */
(function () {
  if (window.mmAlert) return;
  var LOGGED_IN = window.MM_LOGGED_IN === true;

  // ── 스타일 1회 주입 ──
  var css = `
  .mmal-back{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:3000;display:none;
    align-items:flex-end;justify-content:center;}
  .mmal-back.open{display:flex;}
  .mmal-sheet{background:var(--card);color:var(--text);width:100%;max-width:480px;
    border-radius:20px 20px 0 0;box-shadow:0 -8px 32px rgba(0,0,0,.25);
    max-height:88vh;overflow-y:auto;padding:20px 20px 28px;
    animation:mmal-up .22s cubic-bezier(.2,.8,.2,1);}
  @keyframes mmal-up{from{transform:translateY(100%);}to{transform:translateY(0);}}
  @media(min-width:560px){.mmal-back{align-items:center;}
    .mmal-sheet{border-radius:18px;max-height:86vh;}
    @keyframes mmal-up{from{transform:translateY(24px);opacity:.6;}to{transform:translateY(0);opacity:1;}}}
  .mmal-grip{width:38px;height:4px;border-radius:3px;background:var(--border);margin:0 auto 14px;}
  .mmal-hd{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;}
  .mmal-ttl{font-size:1.08rem;font-weight:800;line-height:1.3;}
  .mmal-sub{font-size:.75rem;color:var(--text-muted);margin-top:3px;}
  .mmal-x{background:none;border:none;color:var(--text-muted);font-size:1.3rem;cursor:pointer;line-height:1;padding:2px 4px;}
  .mmal-sec{margin-top:18px;}
  .mmal-sec-t{font-size:.78rem;font-weight:800;color:var(--text-muted);margin-bottom:8px;}
  .mmal-rule{display:flex;align-items:center;gap:10px;border:1.5px solid var(--border);border-radius:12px;
    padding:11px 13px;margin-bottom:8px;background:var(--bg);}
  .mmal-rule.off{opacity:.5;}
  .mmal-rule-m{flex:1;min-width:0;}
  .mmal-rule-t{font-size:.85rem;font-weight:700;}
  .mmal-pill{font-size:.64rem;font-weight:800;padding:2px 8px;border-radius:11px;background:var(--blue);color:#fff;white-space:nowrap;}
  .mmal-mini{background:var(--bg);border:1.5px solid var(--border);color:var(--text-muted);
    border-radius:8px;padding:5px 9px;font-size:.72rem;font-weight:700;cursor:pointer;font-family:inherit;}
  .mmal-x2{background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:1rem;padding:2px 4px;}
  .mmal-add{border:1.5px solid var(--border);border-radius:12px;padding:11px 12px;margin-bottom:9px;}
  .mmal-add-h{font-size:.84rem;font-weight:700;margin-bottom:9px;}
  .mmal-add-row{display:flex;gap:7px;align-items:center;flex-wrap:wrap;}
  .mmal-seg{display:inline-flex;border:1.5px solid var(--border);border-radius:9px;overflow:hidden;}
  .mmal-seg button{border:none;background:var(--bg);color:var(--text-muted);padding:7px 11px;
    font-size:.78rem;font-weight:700;cursor:pointer;font-family:inherit;}
  .mmal-seg button.on{background:var(--blue);color:#fff;}
  .mmal-inp{border:1.5px solid var(--border);background:var(--bg);color:var(--text);border-radius:9px;
    padding:7px 10px;font-size:.84rem;font-family:inherit;width:92px;}
  .mmal-go{background:var(--blue);color:#fff;border:none;border-radius:9px;padding:8px 15px;
    font-size:.8rem;font-weight:800;cursor:pointer;font-family:inherit;margin-left:auto;}
  .mmal-symrow{display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--border);padding:11px 2px;}
  .mmal-symrow:last-child{border-bottom:none;}
  .mmal-symrow-m{flex:1;min-width:0;}
  .mmal-symrow-t{font-size:.86rem;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
  .mmal-symrow-c{font-size:.72rem;color:var(--text-muted);}
  .mmal-symrow .mmal-cnt{font-size:.66rem;font-weight:800;color:var(--blue);}
  .mmal-empty{font-size:.8rem;color:var(--text-muted);padding:6px 2px 2px;}
  .mmal-err{color:#C62828;font-size:.76rem;margin-top:6px;min-height:1em;}
  .mmal-sw{position:relative;width:44px;height:26px;flex-shrink:0;cursor:pointer;}
  .mmal-sw input{opacity:0;width:0;height:0;}
  .mmal-sw .tr{position:absolute;inset:0;background:var(--border);border-radius:14px;transition:.18s;}
  .mmal-sw .tr:before{content:"";position:absolute;width:20px;height:20px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.18s;}
  .mmal-sw input:checked + .tr{background:var(--blue);}
  .mmal-sw input:checked + .tr:before{transform:translateX(18px);}
  `;
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  // ── 모달 골격 ──
  var back = document.createElement('div');
  back.className = 'mmal-back';
  back.innerHTML = '<div class="mmal-sheet" id="mmalSheet"></div>';
  document.body.appendChild(back);
  var sheet = back.querySelector('#mmalSheet');
  back.addEventListener('click', function (e) { if (e.target === back) close(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
  function close() { back.classList.remove('open'); }
  function open() { back.classList.add('open'); }

  function loginGate() {
    sheet.innerHTML =
      '<div class="mmal-grip"></div>' +
      '<div class="mmal-hd"><div class="mmal-ttl">🔔 알림</div>' +
      '<button class="mmal-x" onclick="mmAlert._close()">✕</button></div>' +
      '<div class="mmal-empty" style="padding:24px 2px;text-align:center;">알림은 로그인 후 사용할 수 있어요.</div>' +
      '<a href="/auth/google" style="display:block;text-align:center;background:var(--blue);color:#fff;' +
      'border-radius:10px;padding:11px;font-weight:800;text-decoration:none;margin-top:6px;">Google로 로그인</a>';
    open();
  }

  // ── API ──
  function api(url, opt) { return fetch(url, opt).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); }); }
  function getRules() { return api('/api/alerts/rules').then(function (r) { return r.j.rules || []; }); }

  var TYPE_LABEL = { daily_pct: '변동률', target_price: '목표가', new_high: '신고가', new_low: '신저가', rebalance_band: '리밸런싱' };
  function ruleDesc(r) {
    if (r.rule_type === 'daily_pct') return '하루 ' + ({ up: '+', down: '-', both: '±' }[r.direction] || '±') + r.threshold + '% 변동';
    if (r.rule_type === 'target_price') return '가격 ' + r.threshold + (r.direction === 'above' ? ' 이상' : ' 이하');
    if (r.rule_type === 'new_high') return (r.window === 'all' ? '전체기간' : '52주') + ' 신고가';
    if (r.rule_type === 'new_low') return (r.window === 'all' ? '전체기간' : '52주') + ' 신저가';
    if (r.rule_type === 'rebalance_band') return '목표 비중 ±' + r.threshold + '%p 이탈';
    return '';
  }

  // ── 종목 모달 ──
  function openSymbol(code, name) {
    if (!LOGGED_IN) return loginGate();
    code = String(code).toUpperCase();
    name = name || code;
    open();
    sheet.innerHTML = '<div class="mmal-grip"></div><div class="mmal-empty">불러오는 중…</div>';
    getRules().then(function (rules) { renderSymbol(code, name, rules); });
  }

  function renderSymbol(code, name, allRules) {
    var mine = allRules.filter(function (r) { return r.scope === 'symbol' && (r.code || '').toUpperCase() === code; });
    var h = '<div class="mmal-grip"></div>' +
      '<div class="mmal-hd"><div><div class="mmal-ttl">🔔 ' + esc(name) + '</div>' +
      '<div class="mmal-sub">' + esc(code) + ' · 시세 15분 지연</div></div>' +
      '<button class="mmal-x" onclick="mmAlert._close()">✕</button></div>';

    // 기존 룰
    h += '<div class="mmal-sec"><div class="mmal-sec-t">설정된 알림</div><div id="mmalMine">';
    h += mine.length ? mine.map(ruleRow).join('') : '<div class="mmal-empty">아직 없어요.</div>';
    h += '</div></div>';

    // 새 알림
    h += '<div class="mmal-sec"><div class="mmal-sec-t">새 알림</div>';
    h += '<div class="mmal-add"><div class="mmal-add-h">가격 변동</div><div class="mmal-add-row">' +
      seg('mmalPctDir', [['up', '▲상승'], ['down', '▼하락'], ['both', '↕양방향']], 'up') +
      '<input class="mmal-inp" id="mmalPctVal" type="number" step="any" placeholder="5">%' +
      '<button class="mmal-go" data-add="pct">추가</button></div></div>';
    h += '<div class="mmal-add"><div class="mmal-add-h">목표가 도달</div><div class="mmal-add-row">' +
      seg('mmalTgtDir', [['above', '이상'], ['below', '이하']], 'above') +
      '<input class="mmal-inp" id="mmalTgtVal" type="number" step="any" placeholder="목표가">' +
      '<button class="mmal-go" data-add="tgt">추가</button></div></div>';
    h += '<div class="mmal-add"><div class="mmal-add-h">신고가 / 신저가</div><div class="mmal-add-row">' +
      seg('mmalExtKind', [['new_high', '신고가'], ['new_low', '신저가']], 'new_high') +
      seg('mmalExtWin', [['52w', '52주'], ['all', '전체']], '52w') +
      '<button class="mmal-go" data-add="ext">추가</button></div></div>';
    h += '<div class="mmal-err" id="mmalErr"></div></div>';
    sheet.innerHTML = h;

    bindSeg();
    sheet.querySelectorAll('[data-add]').forEach(function (b) {
      b.onclick = function () { addSymbolRule(code, name, b.getAttribute('data-add')); };
    });
    bindRuleRows(function () { openSymbol(code, name); });
  }

  function addSymbolRule(code, name, kind) {
    var body = { code: code, cooldown_h: 24 };
    if (kind === 'pct') {
      body.rule_type = 'daily_pct';
      body.direction = segVal('mmalPctDir');
      body.threshold = parseFloat(document.getElementById('mmalPctVal').value);
    } else if (kind === 'tgt') {
      body.rule_type = 'target_price';
      body.direction = segVal('mmalTgtDir');
      body.threshold = parseFloat(document.getElementById('mmalTgtVal').value);
    } else {
      body.rule_type = segVal('mmalExtKind');
      body.window = segVal('mmalExtWin');
    }
    api('/api/alerts/rules', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) {
        if (!r.ok) { document.getElementById('mmalErr').textContent = r.j.error || '추가 실패'; return; }
        if (window.mmRefreshBell) window.mmRefreshBell();
        openSymbol(code, name);
      });
  }

  function ruleRow(r) {
    return '<div class="mmal-rule ' + (r.enabled ? '' : 'off') + '">' +
      '<span class="mmal-pill">' + (TYPE_LABEL[r.rule_type] || r.rule_type) + '</span>' +
      '<div class="mmal-rule-m"><div class="mmal-rule-t">' + ruleDesc(r) + '</div></div>' +
      '<button class="mmal-mini" data-toggle="' + r.id + '" data-on="' + r.enabled + '">' + (r.enabled ? '끄기' : '켜기') + '</button>' +
      '<button class="mmal-x2" data-del="' + r.id + '">✕</button></div>';
  }

  function bindRuleRows(reload) {
    sheet.querySelectorAll('[data-toggle]').forEach(function (b) {
      b.onclick = function () {
        api('/api/alerts/rules/' + b.getAttribute('data-toggle'), {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: b.getAttribute('data-on') !== '1' })
        }).then(reload);
      };
    });
    sheet.querySelectorAll('[data-del]').forEach(function (b) {
      b.onclick = function () {
        api('/api/alerts/rules/' + b.getAttribute('data-del'), { method: 'DELETE' }).then(function () {
          if (window.mmRefreshBell) window.mmRefreshBell(); reload();
        });
      };
    });
  }

  // ── 그룹 모달(자산/포트폴리오) ──
  function openAssets() {
    if (!LOGGED_IN) return loginGate();
    open();
    sheet.innerHTML = '<div class="mmal-grip"></div><div class="mmal-empty">불러오는 중…</div>';
    Promise.all([api('/api/alerts/context'), getRules()]).then(function (res) {
      renderGroup('내 자산 알림', res[0].j.holdings || [], res[1], true);
    });
  }
  function openPortfolio(pid) {
    if (!LOGGED_IN) return loginGate();
    open();
    sheet.innerHTML = '<div class="mmal-grip"></div><div class="mmal-empty">불러오는 중…</div>';
    Promise.all([api('/api/alerts/context'), getRules()]).then(function (res) {
      var pf = (res[0].j.portfolios || []).filter(function (p) { return String(p.id) === String(pid); })[0];
      renderPortfolio(pid, pf ? pf.name : '포트폴리오', res[1].j ? res[1].j.rules : res[1]);
    });
  }

  function renderPortfolio(pid, name, allRules) {
    allRules = allRules || [];
    var mine = allRules.filter(function (r) { return r.scope === 'portfolio' && String(r.portfolio_id) === String(pid) && r.rule_type !== 'rebalance_band'; });
    var h = '<div class="mmal-grip"></div>' +
      '<div class="mmal-hd"><div><div class="mmal-ttl">🔔 ' + esc(name) + '</div>' +
      '<div class="mmal-sub">전체 포트폴리오 수익 기준(매일 리밸런싱 가정) · 시세 15분 지연</div></div>' +
      '<button class="mmal-x" onclick="mmAlert._close()">✕</button></div>';
    h += '<div class="mmal-sec"><div class="mmal-sec-t">설정된 알림</div><div id="mmalMine">';
    h += mine.length ? mine.map(ruleRow).join('') : '<div class="mmal-empty">아직 없어요.</div>';
    h += '</div></div>';
    h += '<div class="mmal-sec"><div class="mmal-sec-t">새 알림</div>';
    h += '<div class="mmal-add"><div class="mmal-add-h">일간 수익률</div><div class="mmal-add-row">' +
      seg('mmalPctDir', [['up', '▲상승'], ['down', '▼하락'], ['both', '↕양방향']], 'up') +
      '<input class="mmal-inp" id="mmalPctVal" type="number" step="any" placeholder="3">%' +
      '<button class="mmal-go" data-padd="pct">추가</button></div></div>';
    h += '<div class="mmal-add"><div class="mmal-add-h">수익 신고가 / 신저가</div><div class="mmal-add-row">' +
      seg('mmalExtKind', [['new_high', '신고가'], ['new_low', '신저가']], 'new_high') +
      seg('mmalExtWin', [['52w', '52주'], ['all', '전체']], '52w') +
      '<button class="mmal-go" data-padd="ext">추가</button></div></div>';
    h += '<div class="mmal-err" id="mmalErr"></div></div>';
    sheet.innerHTML = h;
    bindSeg();
    sheet.querySelectorAll('[data-padd]').forEach(function (b) {
      b.onclick = function () { addPortfolioRule(pid, name, b.getAttribute('data-padd')); };
    });
    bindRuleRows(function () { openPortfolio(pid); });
  }

  function addPortfolioRule(pid, name, kind) {
    var body = { portfolio_id: Number(pid), cooldown_h: 24 };
    if (kind === 'pct') {
      body.rule_type = 'daily_pct';
      body.direction = segVal('mmalPctDir');
      body.threshold = parseFloat(document.getElementById('mmalPctVal').value);
    } else {
      body.rule_type = segVal('mmalExtKind');
      body.window = segVal('mmalExtWin');
    }
    api('/api/alerts/rules', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) {
        if (!r.ok) { document.getElementById('mmalErr').textContent = r.j.error || '추가 실패'; return; }
        if (window.mmRefreshBell) window.mmRefreshBell();
        openPortfolio(pid);
      });
  }

  function renderGroup(title, symbols, allRules, withRebalance) {
    var byCode = {};
    allRules.forEach(function (r) {
      if (r.scope === 'symbol' && r.code) { var c = r.code.toUpperCase(); byCode[c] = (byCode[c] || 0) + 1; }
    });
    var reb = allRules.filter(function (r) { return r.rule_type === 'rebalance_band'; })[0];
    var h = '<div class="mmal-grip"></div>' +
      '<div class="mmal-hd"><div><div class="mmal-ttl">🔔 ' + esc(title) + '</div>' +
      '<div class="mmal-sub">종목을 눌러 알림을 설정하세요 · 시세 15분 지연</div></div>' +
      '<button class="mmal-x" onclick="mmAlert._close()">✕</button></div>';

    if (withRebalance) {
      h += '<div class="mmal-sec"><div class="mmal-sec-t">리밸런싱</div>' +
        '<div class="mmal-rule"><div class="mmal-rule-m"><div class="mmal-rule-t">목표 비중 이탈 알림</div>' +
        '<div class="mmal-sub">그룹 목표비중 대비 ±<input class="mmal-inp" id="mmalBand" style="width:58px;" type="number" step="any" value="' +
        (reb ? reb.threshold : 5) + '">%p 벗어나면</div></div>' +
        '<label class="mmal-sw"><input type="checkbox" id="mmalRebSw" ' + (reb ? 'checked' : '') + '><span class="tr"></span></label>' +
        '</div><div class="mmal-err" id="mmalErr"></div></div>';
    }

    h += '<div class="mmal-sec"><div class="mmal-sec-t">종목별 알림</div>';
    if (!symbols.length) {
      h += '<div class="mmal-empty">종목이 없어요.</div>';
    } else {
      h += symbols.map(function (s) {
        var n = byCode[s.code.toUpperCase()] || 0;
        return '<div class="mmal-symrow" data-sym="' + esc(s.code) + '" data-name="' + esc(s.name) + '">' +
          '<div class="mmal-symrow-m"><div class="mmal-symrow-t">' + esc(s.name) + '</div>' +
          '<div class="mmal-symrow-c">' + esc(s.code) + '</div></div>' +
          (n ? '<span class="mmal-cnt">알림 ' + n + '</span>' : '') +
          '<button class="mmal-mini">설정 →</button></div>';
      }).join('');
    }
    h += '</div>';
    sheet.innerHTML = h;

    sheet.querySelectorAll('.mmal-symrow').forEach(function (row) {
      row.onclick = function () { openSymbol(row.getAttribute('data-sym'), row.getAttribute('data-name')); };
    });
    if (withRebalance) {
      var sw = document.getElementById('mmalRebSw');
      sw.onchange = function () {
        if (sw.checked) {
          var band = parseFloat(document.getElementById('mmalBand').value) || 5;
          api('/api/alerts/rules', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rule_type: 'rebalance_band', threshold: band }) })
            .then(function (r) { if (!r.ok) { document.getElementById('mmalErr').textContent = r.j.error || '실패'; sw.checked = false; } else if (window.mmRefreshBell) window.mmRefreshBell(); });
        } else if (reb) {
          api('/api/alerts/rules/' + reb.id, { method: 'DELETE' }).then(function () { reb = null; });
        }
      };
    }
  }

  // ── 헬퍼 ──
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function seg(id, opts, def) {
    return '<span class="mmal-seg" id="' + id + '">' + opts.map(function (o) {
      return '<button data-v="' + o[0] + '" class="' + (o[0] === def ? 'on' : '') + '">' + o[1] + '</button>';
    }).join('') + '</span>';
  }
  function bindSeg() {
    sheet.querySelectorAll('.mmal-seg').forEach(function (g) {
      g.querySelectorAll('button').forEach(function (b) {
        b.onclick = function () { g.querySelectorAll('button').forEach(function (x) { x.classList.remove('on'); }); b.classList.add('on'); };
      });
    });
  }
  function segVal(id) { var on = document.querySelector('#' + id + ' button.on'); return on ? on.getAttribute('data-v') : null; }

  window.mmAlert = { openSymbol: openSymbol, openAssets: openAssets, openPortfolio: openPortfolio, _close: close };
})();
