// ISA 전환 계산기 — 위탁 유지(A) vs ISA 분할 이전(B)
// 백엔드: POST /api/tax-switch/submit → /api/task/<id> 폴링 (tax_switch_logic.py)

(function () {
  'use strict';

  // ── 상태 ──
  const tickers = [];        // {code, name, badge, weight(%)}
  let running = false;
  let chartInstance = null;

  // ── 포맷 ──
  function fmtKRW(v) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    const sign = v < 0 ? '-' : '';
    const abs = Math.abs(v);
    const uk = Math.floor(abs / 1e8);
    const man = Math.floor((abs % 1e8) / 1e4);
    if (uk > 0 && man > 0) return sign + '₩' + uk.toLocaleString() + '억 ' + man.toLocaleString() + '만';
    if (uk > 0) return sign + '₩' + uk.toLocaleString() + '억';
    if (abs >= 1e4) return sign + '₩' + Math.floor(abs / 1e4).toLocaleString() + '만';
    return sign + '₩' + Math.round(abs).toLocaleString();
  }
  function badgeColor(badge) {
    if (badge === 'KR ETF' || badge === 'KOSPI' || badge === 'KOSDAQ') return '#1976D2';
    if (badge === 'US ETF' || badge === 'NASDAQ' || badge === 'NYSE') return '#2E7D32';
    return '#78909C';
  }
  function cssVar(name, fallback) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  // ── 종목 검색 ──
  const searchInput = document.getElementById('tsSearchInput');
  const dropdown = document.getElementById('tsDropdown');
  let searchTimer = null;

  searchInput.addEventListener('input', (e) => {
    const q = e.target.value.trim();
    clearTimeout(searchTimer);
    if (!q) { dropdown.style.display = 'none'; return; }
    searchTimer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        if (!Array.isArray(data) || data.length === 0) {
          dropdown.innerHTML = '<div class="ts-dd-item">검색 결과 없음</div>';
          dropdown.style.display = 'block';
          return;
        }
        dropdown.innerHTML = data.slice(0, 8).map(item => `
          <div class="ts-dd-item" data-code="${item.code}" data-name="${item.name}" data-badge="${item.badge || ''}">
            <span class="ts-badge" style="background:${badgeColor(item.badge)}">${item.badge || ''}</span>
            <span>${item.name}</span>
            <span style="color:var(--text-muted);font-size:0.72rem;">${item.code}</span>
          </div>`).join('');
        dropdown.style.display = 'block';
        dropdown.querySelectorAll('.ts-dd-item[data-code]').forEach(el => {
          el.addEventListener('click', () => {
            addTicker(el.dataset.code, el.dataset.name, el.dataset.badge);
            searchInput.value = '';
            dropdown.style.display = 'none';
          });
        });
      } catch (err) { /* 네트워크 오류 — 무시 */ }
    }, 250);
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.ts-search-wrap')) dropdown.style.display = 'none';
  });

  function addTicker(code, name, badge) {
    if (tickers.some(t => t.code === code)) return;
    tickers.push({ code, name, badge, weight: 0 });
    rebalanceWeights();
    renderTickers();
  }
  function removeTicker(code) {
    const i = tickers.findIndex(t => t.code === code);
    if (i >= 0) tickers.splice(i, 1);
    rebalanceWeights();
    renderTickers();
  }
  function rebalanceWeights() {
    if (tickers.length === 0) return;
    const w = Math.floor(100 / tickers.length);
    tickers.forEach((t, i) => { t.weight = i === 0 ? 100 - w * (tickers.length - 1) : w; });
  }
  function renderTickers() {
    const list = document.getElementById('tsTickerList');
    if (tickers.length === 0) {
      list.innerHTML = '<div style="font-size:0.78rem;color:var(--text-muted);">종목을 검색해서 추가해보세요 (비중 합 100%)</div>';
      return;
    }
    list.innerHTML = tickers.map(t => `
      <div class="ts-ticker-row" data-code="${t.code}">
        <span class="ts-badge" style="background:${badgeColor(t.badge)}">${t.badge || ''}</span>
        <span class="name">${t.name}</span>
        <input type="number" class="calc-input ts-weight" value="${t.weight}" min="0" max="100" step="1"><span style="font-size:0.75rem;color:var(--text-muted);">%</span>
        <button class="ts-remove-btn" title="제거">✕</button>
      </div>`).join('');
    list.querySelectorAll('.ts-ticker-row').forEach(row => {
      const code = row.dataset.code;
      row.querySelector('.ts-remove-btn').addEventListener('click', () => removeTicker(code));
      row.querySelector('.ts-weight').addEventListener('change', (e) => {
        const t = tickers.find(x => x.code === code);
        if (t) t.weight = Number(e.target.value) || 0;
      });
    });
  }
  renderTickers();

  // 포트폴리오 즐겨찾기 (B1) — weight는 % (0~100) 그대로
  if (window.MMFav) window.MMFav.init({
    mount: 'favBar',
    getTickers: () => tickers.map(t => ({ ...t })),
    setTickers: (list) => {
      tickers.length = 0;
      list.forEach(t => tickers.push({
        code: t.code, name: t.name || t.code, badge: t.badge || '',
        weight: Math.round(Number(t.weight) || 0),
      }));
      renderTickers();
    },
  });

  // ── 세금 프로필 ──
  window.taxProfile = {};
  (async function loadProfile() {
    let settings = {};
    try {
      const me = await fetch('/api/me').then(r => r.json());
      if (me.logged_in) {
        const res = await fetch('/api/settings/tax');
        if (res.ok) settings = await res.json();
      }
    } catch (e) {}
    if (!settings || Object.keys(settings).length === 0) {
      try { settings = JSON.parse(localStorage.getItem('domino_tax_settings') || '{}'); } catch (e) { settings = {}; }
    }
    window.taxProfile = settings || {};
    const info = document.getElementById('tsProfileInfo');
    const p = window.taxProfile;
    if (p.earned_income == null && p.age == null) {
      info.innerHTML = '세금 프로필 없음 — 기본값(나이 40세 · ISA 일반형)으로 계산해요. <a href="/tax-settings" style="color:var(--blue);">세금 설정</a>에서 입력하면 더 정확해요.';
    } else {
      const isaLabel = p.isa_type === 'preferential' ? '서민형(비과세 400만)' : '일반형(비과세 200만)';
      info.innerHTML = `세금 프로필: 나이 ${p.age || 40}세 · ISA ${isaLabel} <a href="/tax-settings" style="color:var(--blue);margin-left:6px;">수정</a>`;
    }
  })();

  // ── 실행 ──
  const runBtn = document.getElementById('tsRunBtn');
  const progress = document.getElementById('tsProgress');
  const progressText = document.getElementById('tsProgressText');
  const progressBar = document.getElementById('tsProgressBar');
  const errBox = document.getElementById('tsError');

  runBtn.addEventListener('click', async () => {
    if (running) return;
    errBox.style.display = 'none';

    if (tickers.length === 0) return showError('보유 종목을 1개 이상 추가해주세요.');
    const wSum = tickers.reduce((s, t) => s + (Number(t.weight) || 0), 0);
    if (Math.abs(wSum - 100) > 0.5) return showError(`비중 합이 100%가 아닙니다 (현재 ${wSum}%).`);

    const currentValue = Number(document.getElementById('tsCurrentValue').value) || 0;
    const costBasis = Number(document.getElementById('tsCostBasis').value) || 0;
    const years = Number(document.getElementById('tsYears').value) || 0;
    if (currentValue <= 0) return showError('현재 평가액을 입력해주세요.');
    if (costBasis <= 0) return showError('취득가를 입력해주세요.');
    if (years < 1) return showError('투자 기간은 1년 이상이어야 합니다.');

    const p = window.taxProfile || {};
    const payload = {
      current_value: currentValue,
      cost_basis: costBasis,
      years: years,
      tickers: tickers.map(t => ({ code: t.code, name: t.name, weight: t.weight / 100 })),
      user_settings: {
        earned_income: Number(p.earned_income || 0),
        age: Number(p.age || 40),
        isa_type: p.isa_type || 'general',
        pension_age: Number(p.pension_age || 65),
      },
    };

    running = true;
    runBtn.disabled = true;
    progress.style.display = 'block';
    progressBar.style.width = '3%';
    progressText.textContent = '대기열 등록 중...';

    try {
      const submitRes = await fetch('/api/tax-switch/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const submitData = await submitRes.json();
      if (!submitRes.ok) throw new Error(submitData.error || '제출 실패');
      const result = await pollTask(submitData.task_id);
      renderResult(result);
    } catch (e) {
      showError(parseErrorMessage(e));
    } finally {
      running = false;
      runBtn.disabled = false;
      progress.style.display = 'none';
    }
  });

  function showError(msg) {
    errBox.innerHTML = msg;
    errBox.style.display = 'block';
  }
  function parseErrorMessage(e) {
    // logic 계층이 JSON 구조화 에러(violations)를 던질 수 있음
    try {
      const data = JSON.parse(e.message);
      if (data.violations) return data.violations.join('<br>');
    } catch (_) {}
    return e.message || '계산 실패';
  }

  async function pollTask(taskId, maxWait = 600000) {
    const start = Date.now();
    while (Date.now() - start < maxWait) {
      await new Promise(r => setTimeout(r, 1500));
      const res = await fetch(`/api/task/${taskId}`);
      const data = await res.json();
      if (data.status === 'PENDING') {
        progressText.textContent = data.queue_rank != null ? `대기 중 (${data.queue_rank}번째)` : '준비 중...';
      } else if (data.status === 'PROGRESS') {
        const pct = Math.max(3, Math.min(99, data.percent || 0));
        progressBar.style.width = pct + '%';
        progressText.textContent = `계산 중... ${pct}%`;
      } else if (data.status === 'SUCCESS') {
        return data.result;
      } else if (data.status === 'FAILURE') {
        throw new Error(data.error || '시뮬레이션 실패');
      } else if (data.status === 'CANCELLED') {
        throw new Error('취소됨');
      }
    }
    throw new Error('시간 초과 (10분)');
  }

  // ── 결과 렌더 ──
  function renderResult(r) {
    document.getElementById('tsResults').style.display = 'block';

    const diff = r.diff.p50;
    const headline = document.getElementById('tsVerdictHeadline');
    const sub = document.getElementById('tsVerdictSub');
    if (r.winner === 'B') {
      headline.textContent = `지금 ISA로 분할 이전하는 게 약 ${fmtKRW(diff)} 이득이에요 (중앙값 기준)`;
      headline.style.color = 'var(--blue)';
    } else if (r.winner === 'A') {
      headline.textContent = `위탁 유지가 약 ${fmtKRW(-diff)} 이득이에요 (중앙값 기준)`;
      headline.style.color = 'var(--green)';
    } else {
      headline.textContent = '두 전략의 차이가 거의 없어요 (중앙값 기준)';
      headline.style.color = 'var(--text-muted)';
    }
    sub.textContent = `${r.years}년 운용 가정 · 과거 데이터 롤링 ${r.cases_count}개 시작 시점 시뮬레이션 · 미실현 차익 ${fmtKRW(r.inputs.unrealized_gain)} 반영`;

    document.getElementById('tsAEnd').textContent = fmtKRW(r.a.p50);
    document.getElementById('tsARange').textContent = `25~75%: ${fmtKRW(r.a.p25)} ~ ${fmtKRW(r.a.p75)}`;
    document.getElementById('tsBEnd').textContent = fmtKRW(r.b.p50);
    document.getElementById('tsBRange').textContent = `25~75%: ${fmtKRW(r.b.p25)} ~ ${fmtKRW(r.b.p75)}`;
    const diffEl = document.getElementById('tsDiff');
    diffEl.textContent = (diff >= 0 ? '+' : '') + fmtKRW(diff);
    diffEl.className = 'ts-sum-value ' + (diff > 0 ? 'blue' : diff < 0 ? 'red' : '');
    document.getElementById('tsSwitchTax').textContent = fmtKRW(r.b.switch_tax.p50);

    const be = r.breakeven || {};
    if (be.year_p50 != null) {
      document.getElementById('tsBreakeven').textContent = `약 ${Math.round(be.year_p50)}년차`;
      document.getElementById('tsBreakevenSub').textContent = `시나리오 ${Math.round((be.found_ratio || 0) * 100)}%에서 역전 발생`;
    } else {
      document.getElementById('tsBreakeven').textContent = '기간 내 없음';
      document.getElementById('tsBreakevenSub').textContent = '이 기간에는 B가 A를 따라잡지 못했어요';
    }

    drawChart(r.trajectory || []);
    drawSchedule(r.representative_schedule || {});

    const notes = (r.notes || []).map(n => '· ' + n).join('<br>');
    document.getElementById('tsNotes').innerHTML =
      notes + '<br>· 과거 데이터 기반 시뮬레이션이며 미래 수익률을 보장하지 않아요. 세법은 2026년 기준 단순화 모델이에요.';

    document.getElementById('tsResults').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function drawChart(trajectory) {
    if (typeof Chart === 'undefined') return;
    const ctx = document.getElementById('tsChart');
    if (chartInstance) chartInstance.destroy();
    const textColor = cssVar('--text-muted', '#888');
    const gridColor = cssVar('--border', '#ddd');
    chartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: trajectory.map(t => t.year + '년차'),
        datasets: [
          {
            label: 'A) 위탁 유지 (세후)',
            data: trajectory.map(t => t.a_p50),
            borderColor: '#2E7D32', backgroundColor: 'transparent', tension: 0.25, pointRadius: 2,
          },
          {
            label: 'B) ISA 분할 이전 (세후)',
            data: trajectory.map(t => t.b_p50),
            borderColor: '#1976D2', backgroundColor: 'transparent', tension: 0.25, pointRadius: 2,
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: textColor, font: { weight: 700 } } },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmtKRW(c.parsed.y)}` } },
        },
        scales: {
          x: { ticks: { color: textColor }, grid: { color: gridColor } },
          y: { ticks: { color: textColor, callback: (v) => fmtKRW(v) }, grid: { color: gridColor } },
        },
      },
    });
  }

  function drawSchedule(rep) {
    const table = document.getElementById('tsScheduleTable');
    const rows = rep.transfers || [];
    if (rows.length === 0) {
      table.innerHTML = '<tr><td style="padding:10px;">이전 내역 없음</td></tr>';
      return;
    }
    table.innerHTML =
      '<tr><th>연차</th><th>매도액</th><th>전환 양도세</th><th>ISA 입금</th></tr>' +
      rows.map((e, i) => `
        <tr>
          <td>${i + 1}년차 (${e.year})</td>
          <td>${fmtKRW(e.gross_sold)}</td>
          <td>${fmtKRW(e.cg_tax)}</td>
          <td>${fmtKRW(e.transferred)}</td>
        </tr>`).join('');
  }
})();
