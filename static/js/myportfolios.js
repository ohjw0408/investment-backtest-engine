// myportfolios.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 내용 무변경 이동
let mpItems = [];                 // 서버 목록
let mpEdit  = { id: null, tickers: [] };   // 모달 편집 상태 (weight = %)
let mpSearchTimer = null;

const esc = window.mmEsc;  // E-1 공용화: 전역 mmEsc(base.html) 단일 구현 — 로컬 복붙 제거 (2026-07-03)
function badgeColor(b) {
  if (b==='KR ETF'||b==='KOSPI'||b==='KOSDAQ') return '#1976D2';
  if (b==='US ETF'||b==='NASDAQ'||b==='NYSE')   return '#2E7D32';
  return '#78909C';
}

// ── 목록 ──
async function mpLoad() {
  try {
    const res = await fetch('/api/portfolio/list');
    if (!res.ok) throw new Error();
    mpItems = await res.json();
  } catch (e) { mpItems = []; }
  mpRenderList();
}

function mpRenderList() {
  const el = document.getElementById('mpList');
  document.getElementById('mpCount').textContent =
    `저장 ${mpItems.length}개 — 각 계산기의 ★ 즐겨찾기에서 바로 불러올 수 있어요.`;
  if (!mpItems.length) {
    el.innerHTML = `<div class="mp-empty">
      <div style="font-size:1.8rem;margin-bottom:10px;">⭐</div>
      <div style="font-weight:700;margin-bottom:6px;">저장된 포트폴리오가 없어요</div>
      <div style="font-size:0.82rem;">[+ 새 포트폴리오]로 만들거나, 각 계산기에서 구성 후 [저장]을 눌러보세요.</div>
    </div>`;
    return;
  }
  el.innerHTML = mpItems.map(p => {
    const total = p.tickers.reduce((s, t) => s + (Number(t.weight) || 0), 0);
    const date = (p.updated_at || '').slice(0, 10);
    return `<div class="mp-card">
      <div class="mp-card-head">
        <div>
          <div class="mp-name" style="cursor:pointer;" title="상세 열기" onclick="location.href='/myportfolios/${p.id}'">${esc(p.name)} <span style="font-size:0.72rem;color:var(--blue);font-weight:600;">상세 ›</span></div>
          <div class="mp-date">수정 ${esc(date)} · 종목 ${p.tickers.length}개</div>
        </div>
        <div class="mp-actions">
          <button class="icon-btn" title="수익 알림 설정" onclick="mmAlert.openPortfolio(${p.id})">🔔</button>
          <button class="icon-btn" title="홈 즐겨찾기에 추가" onclick="mpAddHome(${p.id})">⭐</button>
          <button class="icon-btn" title="상세 열기 (수량·배당·추이)" onclick="location.href='/myportfolios/${p.id}'">📂</button>
          <button class="icon-btn" title="수정" onclick="mpOpenEdit(${p.id})">✏️</button>
          <button class="icon-btn danger" title="삭제" onclick="mpDelete(${p.id})">🗑</button>
        </div>
      </div>
      ${p.tickers.map(t => `
        <div class="mp-ticker-row" style="cursor:pointer;" title="종목 상세 보기" onclick="location.href='/symbol/${esc(t.code)}'">
          <span class="mp-badge" style="background:${badgeColor(t.badge)}">${esc(t.badge || '—')}</span>
          <span class="mp-code">${esc(t.code)}</span>
          <span class="mp-tname">${esc(t.name || '')}</span>
          <div class="mp-weightbar"><div style="width:${Math.min(100, Number(t.weight) || 0)}%"></div></div>
          <span class="mp-weight">${Number(t.weight) || 0}%</span>
        </div>`).join('')}
      <div class="mp-total">
        <span>비중 합계</span>
        <span style="font-weight:700;color:${total === 100 ? 'var(--green, #2E7D32)' : 'var(--text)'}">${total}%${total < 100 ? ' (나머지 현금)' : ''}</span>
      </div>
    </div>`;
  }).join('');
}

// ── 모달 ──
function mpOpenCreate() {
  mpEdit = { id: null, tickers: [] };
  document.getElementById('mpModalTitle').textContent = '새 포트폴리오';
  document.getElementById('mpName').value = '';
  mpRenderEdit();
  document.getElementById('mpModal').classList.add('show');
}

function mpOpenEdit(id) {
  const p = mpItems.find(x => x.id === id);
  if (!p) return;
  mpEdit = { id: p.id, tickers: p.tickers.map(t => ({ ...t, weight: Number(t.weight) || 0 })) };
  document.getElementById('mpModalTitle').textContent = '포트폴리오 수정';
  document.getElementById('mpName').value = p.name;
  mpRenderEdit();
  document.getElementById('mpModal').classList.add('show');
}

function mpCloseModal() {
  document.getElementById('mpModal').classList.remove('show');
  document.getElementById('mpDropdown').style.display = 'none';
  document.getElementById('mpSearch').value = '';
}

function mpRenderEdit() {
  const el = document.getElementById('mpEditList');
  el.innerHTML = mpEdit.tickers.length === 0
    ? '<div style="font-size:0.8rem;color:var(--text-muted);padding:6px 0;">종목을 검색해서 추가해보세요</div>'
    : mpEdit.tickers.map((t, i) => `
      <div class="mp-edit-row">
        <span class="mp-badge" style="background:${badgeColor(t.badge)}">${esc(t.badge || '—')}</span>
        <span class="mp-code">${esc(t.code)}</span>
        <span class="mp-tname">${esc(t.name || '')}</span>
        <input type="number" min="0" max="100" value="${t.weight}" oninput="mpSetWeight(${i}, this.value)"> %
        <button class="mp-remove" onclick="mpRemove(${i})">✕</button>
      </div>`).join('');
  mpRenderSum();
}

function mpRenderSum() {
  const total = mpEdit.tickers.reduce((s, t) => s + (Number(t.weight) || 0), 0);
  const el = document.getElementById('mpSum');
  el.className = 'mp-sum' + (total === 100 ? ' ok' : total > 100 ? ' over' : '');
  el.textContent = `비중 합계 ${total}%` +
    (total > 100 ? ' — 100%를 초과했어요' : total < 100 && total > 0 ? ` — 나머지 ${100 - total}%는 현금` : '');
}

function mpSetWeight(i, v) {
  mpEdit.tickers[i].weight = Math.max(0, Math.min(100, Number(v) || 0));
  mpRenderSum();
}
function mpRemove(i) { mpEdit.tickers.splice(i, 1); mpRenderEdit(); }

function mpAdd(code, name, badge) {
  if (mpEdit.tickers.some(t => t.code === code)) return;
  // 균등 분배 (계산기 패턴)
  const n = mpEdit.tickers.length + 1;
  const w = Math.floor(100 / n);
  mpEdit.tickers.forEach(t => t.weight = w);
  mpEdit.tickers.push({ code, name, badge, weight: 100 - w * (n - 1) });
  mpRenderEdit();
  document.getElementById('mpSearch').value = '';
  document.getElementById('mpDropdown').style.display = 'none';
}

// 종목 검색
document.getElementById('mpSearch').addEventListener('input', e => {
  const q = e.target.value.trim();
  const dd = document.getElementById('mpDropdown');
  clearTimeout(mpSearchTimer);
  if (!q) { dd.style.display = 'none'; return; }
  mpSearchTimer = setTimeout(async () => {
    try {
      const data = await fetch(`/api/search?q=${encodeURIComponent(q)}`).then(r => r.json());
      if (!data.length) { dd.innerHTML = '<div class="mp-dd-item">검색 결과 없음</div>'; dd.style.display = 'block'; return; }
      dd.innerHTML = data.slice(0, 8).map(item => `
        <div class="mp-dd-item" data-code="${esc(item.code)}" data-name="${esc(item.name)}" data-badge="${esc(item.badge || '')}">
          <span class="mp-badge" style="background:${badgeColor(item.badge)}">${esc(item.badge || '—')}</span>
          <span style="font-weight:700;">${esc(item.code)}</span>
          <span style="color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(item.name)}</span>
        </div>`).join('');
      dd.style.display = 'block';
      dd.querySelectorAll('.mp-dd-item[data-code]').forEach(el => {
        el.addEventListener('click', () => mpAdd(el.dataset.code, el.dataset.name, el.dataset.badge));
      });
    } catch (err) {}
  }, 250);
});
document.addEventListener('click', e => {
  if (!e.target.closest('.mp-search-wrap'))
    document.getElementById('mpDropdown').style.display = 'none';
});

// ── 저장 / 삭제 ──
async function mpSave() {
  const name = document.getElementById('mpName').value.trim();
  if (!name) { mmToast('이름을 입력해주세요.'); return; }
  if (!mpEdit.tickers.length) { mmToast('종목을 1개 이상 추가해주세요.'); return; }
  // 동명 충돌 (자기 자신 제외)
  const dup = mpItems.find(p => p.name === name && p.id !== mpEdit.id);
  if (dup && !confirm(`"${name}" 이름이 이미 있어요. 그 포트폴리오를 덮어쓸까요?`)) return;
  try {
    const res = await fetch('/api/portfolio/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: dup ? dup.id : mpEdit.id,
        name,
        tickers: mpEdit.tickers,
      }),
    });
    const data = await res.json();
    if (!res.ok) { mmToast(data.error || '저장에 실패했어요.'); return; }
    mpCloseModal();
    await mpLoad();
  } catch (e) { mmToast('저장에 실패했어요. 네트워크를 확인해주세요.'); }
}

async function mpDelete(id) {
  const p = mpItems.find(x => x.id === id);
  if (!p) return;
  if (!confirm(`"${p.name}" 포트폴리오를 삭제할까요?`)) return;
  try {
    const res = await fetch(`/api/portfolio/${id}`, { method: 'DELETE' });
    if (!res.ok) { mmToast('삭제에 실패했어요.'); return; }
    await mpLoad();
  } catch (e) { mmToast('삭제에 실패했어요. 네트워크를 확인해주세요.'); }
}

async function mpAddHome(id) {
  try {
    const res = await fetch('/api/home-config/add-portfolio', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id }),
    });
    const data = await res.json();
    if (!res.ok) { mmToast(data.error || '추가에 실패했어요.'); return; }
    mmToast(data.already ? '이미 홈 즐겨찾기에 있어요.' : '홈 화면 즐겨찾기에 추가했어요. (수익 추종)');
  } catch (e) { mmToast('추가에 실패했어요. 네트워크를 확인해주세요.'); }
}

mpLoad();
