// portfolio_detail.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 데이터는 #page-data JSON
const PID = JSON.parse(document.getElementById('page-data').textContent).pid;
const LS_KEY = 'pf_amount_' + PID;
let pf = null;                 // {id, name, tickers:[{code,name,badge,weight}]}
let pdPrices = {};
let pdAmount = 0;
let hideAmounts = false;
const PALETTE = ['#1976D2','#2E7D32','#F57C00','#7B1FA2','#00838F','#C62828','#5D4037','#455A64','#AD1457','#558B2F'];

const esc = window.mmEsc;  // E-1 공용화: 전역 mmEsc(base.html) 단일 구현 — 로컬 복붙 제거 (2026-07-03)
function badgeColor(b){
  if (b==='KR ETF'||b==='KOSPI'||b==='KOSDAQ') return '#1976D2';
  if (b==='US ETF'||b==='NASDAQ'||b==='NYSE')   return '#2E7D32';
  return '#78909C';
}
function fmtKRW(v){ if (hideAmounts) return '***원'; if (v==null) return '—'; return '₩'+Math.round(v).toLocaleString(); }

// ── 로드 ──
async function loadPortfolio(){
  try {
    const res = await fetch(`/api/portfolio/item/${PID}`);
    if (!res.ok) throw new Error();
    pf = await res.json();
  } catch(e){
    document.getElementById('pdName').textContent = '포트폴리오를 찾을 수 없습니다';
    return;
  }
  document.getElementById('pdName').textContent = '⭐ ' + pf.name;
  renderWeight();                       // 비중 파이는 금액과 무관하게 즉시 표시
  const saved = parseFloat(localStorage.getItem(LS_KEY) || '0') || 0;
  document.getElementById('pdAmount').value = saved > 0 ? saved : 10000000;  // 기본 1천만
  applyAmount();
}

function setAmount(v){ document.getElementById('pdAmount').value = v; applyAmount(); }

// ── 금액 적용 → 추이·배당 ──
async function applyAmount(){
  pdAmount = Math.max(0, parseFloat(document.getElementById('pdAmount').value) || 0);
  localStorage.setItem(LS_KEY, String(pdAmount));
  renderWeight();
  if (pdAmount <= 0) {
    document.getElementById('pdHistHint').style.display = 'block';
    document.getElementById('pdHistWrap').style.display = 'none';
    document.getElementById('divHint').style.display = 'block';
    document.getElementById('divChart').style.display = 'none';
    document.getElementById('divYearTabs').innerHTML = '';
    document.getElementById('divDrill').innerHTML = '';
    document.getElementById('divCalWrap').style.display = 'none';
    document.getElementById('divNote').innerHTML = '';
    return;
  }
  const payload = { amount: pdAmount, tickers: pf.tickers.map(t => ({ code:t.code, weight:t.weight })) };
  try {
    const res = await fetch('/api/portfolio/compute', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload),
    });
    const data = await res.json();
    pdPrices    = data.prices || {};
    hideAmounts = !!data.hide_amounts;
    _histData   = data.history;
    renderWeight();
    renderHist();
  } catch(e){}
  loadDividends();
}

// ── 비중 ──
let _weightChart = null;
function renderWeight(){
  const items = pf.tickers
    .filter(t => Number(t.weight) > 0)
    .map((t,i) => ({ code:t.code, name:t.name, badge:t.badge, weight:Number(t.weight), color: PALETTE[i % PALETTE.length] }));
  const totalW = items.reduce((s,i)=>s+i.weight, 0);

  // 요약
  document.getElementById('pdSummary').innerHTML = [
    { label:'총 투자금액', value: pdAmount>0 ? fmtKRW(pdAmount) : '— (금액 입력)' },
    { label:'종목 수', value: items.length + '개' },
    { label:'비중 합계', value: totalW + '%' + (totalW < 100 ? ` (현금 ${100-totalW}%)` : '') },
  ].map(i => `<div class="summary-item"><div class="summary-label">${i.label}</div><div class="summary-value">${i.value}</div></div>`).join('');

  // 종목 구성 행 (비중 + 배분금액)
  document.getElementById('pdCompose').innerHTML = items.map(t => {
    const val = pdAmount > 0 ? pdAmount * t.weight / 100 : null;
    return `<div class="pd-row" style="cursor:pointer;" title="종목 상세 보기" onclick="location.href='/symbol/${esc(t.code)}'">
      <span class="pd-badge" style="background:${badgeColor(t.badge)}">${esc(t.badge || '—')}</span>
      <span class="pd-code">${esc(t.code)}</span>
      <span class="pd-name">${esc(t.name || '')}</span>
      <span class="pd-weight">${t.weight}%</span>
      <span class="pd-val">${val==null ? '' : fmtKRW(val)}</span>
    </div>`;
  }).join('');

  // 파이
  if (_weightChart) _weightChart.destroy();
  if (!items.length) return;
  _weightChart = new Chart(document.getElementById('pdWeightChart').getContext('2d'), {
    type:'pie',
    data:{ labels: items.map(i=>i.code), datasets:[{
      data: items.map(i => i.weight),
      backgroundColor: items.map(i => i.color+'cc'),
      borderColor: items.map(i => i.color), borderWidth:1.5,
    }]},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{
      legend:{ position: window.innerWidth<=768 ? 'bottom':'right', labels:{ boxWidth:14, font:{size:11} } },
      tooltip:{ callbacks:{ label: ctx => `${ctx.label}: ${ctx.parsed}%` } },
    }}
  });
}

// ── 자산 추이 ──
let _histChart = null, _histData = null;
function renderHist(){
  const d = _histData;
  if (!d || d.empty || !d.labels || !d.labels.length) {
    document.getElementById('pdHistHint').textContent = '이 종목 구성의 과거 가격 데이터가 없습니다.';
    document.getElementById('pdHistHint').style.display = 'block';
    document.getElementById('pdHistWrap').style.display = 'none';
    if (_histChart) { _histChart.destroy(); _histChart = null; }
    return;
  }
  document.getElementById('pdHistHint').style.display = 'none';
  document.getElementById('pdHistWrap').style.display = 'block';
  renderHistChart(30);
}
function setHistPeriod(days, btn){
  document.querySelectorAll('.ma-period-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderHistChart(days);
}
function renderHistChart(days){
  const d = _histData;
  if (!d || !d.labels || !d.labels.length) return;
  let labels = d.labels, values = d.values;
  if (days > 0 && labels.length > days) { labels = labels.slice(-days); values = values.slice(-days); }
  const ctx = document.getElementById('pdHistChart').getContext('2d');
  if (_histChart) _histChart.destroy();
  _histChart = new Chart(ctx, {
    type:'line',
    data:{ labels, datasets:[{ data: values, borderColor:'#1a73e8', backgroundColor:'rgba(26,115,232,0.08)', fill:true, tension:0.3, pointRadius:0, borderWidth:2 }]},
    options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{display:false},
      tooltip:{ callbacks:{ label: ctx => hideAmounts ? '***원' : Math.round(ctx.parsed.y).toLocaleString()+'원' } } },
      scales:{ x:{ ticks:{ maxTicksLimit:6, font:{size:11} }, grid:{display:false} },
               y:{ ticks:{ maxTicksLimit:4, font:{size:11}, callback: v => hideAmounts ? '***' : (v>=1e8 ? (v/1e8).toFixed(1)+'억' : (v/1e4).toFixed(0)+'만') } } } }
  });
}

// ── 배당금 (내자산과 동일 엔진) ──
let _divChart = null, _divData = null;
let _divTax = 'pretax', _divCur = 'KRW', _divYear = null, _divActiveMonth = null;

async function loadDividends(){
  try {
    const res = await fetch('/api/portfolio/dividends-preview', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ amount: pdAmount, tickers: pf.tickers.map(t => ({ code:t.code, weight:t.weight })) }),
    });
    if (!res.ok) throw new Error();
    _divData = await res.json();
  } catch(e){
    document.getElementById('divHint').textContent = '배당 데이터를 불러오지 못했습니다.';
    document.getElementById('divHint').style.display = 'block';
    return;
  }
  const anyEvents = _divData.years && _divData.years.some(y => (_divData.events[y]||[]).length);
  if (!anyEvents) {
    document.getElementById('divHint').textContent = '배당 이력이 있는 종목이 없습니다.';
    document.getElementById('divHint').style.display = 'block';
    document.getElementById('divChart').style.display = 'none';
    document.getElementById('divCalWrap').style.display = 'none';
    return;
  }
  document.getElementById('divHint').style.display = 'none';
  document.getElementById('divChart').style.display = 'block';
  document.getElementById('divCalWrap').style.display = 'block';
  _divYear = _divData.default_year;
  _divActiveMonth = null;
  renderYearTabs();
  renderDivYear();
}

function _valOf(e){ return e[(_divCur==='KRW'?'krw':'usd')+'_'+(_divTax==='pretax'?'pre':'post')]; }
function _fmtDivMoney(v){ return _divCur==='USD' ? '$'+v.toLocaleString(undefined,{maximumFractionDigits:2}) : '₩'+Math.round(v).toLocaleString(); }
function _yearLabel(y){
  if (y === _divData.full_proj_year) return y+' (예측)';
  if (y === _divData.current_year)   return y+' (진행)';
  return String(y);
}
function renderYearTabs(){
  document.getElementById('divYearTabs').innerHTML = _divData.years.map(y =>
    `<button class="div-tgl${y===_divYear?' active':''}" data-div-year="${y}">${_yearLabel(y)}</button>`).join('');
}

function renderDivYear(){
  if (!_divData) return;
  const evs = _divData.events[_divYear] || [];
  const monthly = Array(12).fill(0);
  const monthProj = Array(12).fill(false);
  evs.forEach(e => { monthly[e.month-1] += _valOf(e); if (e.projected) monthProj[e.month-1] = true; });
  const colors = monthProj.map(p => p ? 'rgba(251,140,0,0.7)' : '#1976D2');

  const labels = ['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월'];
  const ctx = document.getElementById('divChart').getContext('2d');
  if (_divChart) _divChart.destroy();
  _divChart = new Chart(ctx, {
    type:'bar',
    data:{ labels, datasets:[{ label:_divYear+' 배당', data:monthly, backgroundColor:colors }]},
    options:{ responsive:true, maintainAspectRatio:false,
      onClick:(evt,els)=>{ if (els.length) showMonth(els[0].index+1); },
      plugins:{ legend:{display:false}, tooltip:{ callbacks:{
        label: c => _fmtDivMoney(c.parsed.y) + (monthProj[c.dataIndex] ? ' (예측)':'') } } },
      scales:{ x:{ grid:{display:false}, ticks:{font:{size:10}} },
               y:{ beginAtZero:true, grid:{color:MM_CHART_GRID}, ticks:{ font:{size:10},
                 callback: v => _divCur==='USD' ? '$'+v : '₩'+(v/10000).toFixed(0)+'만' } } } }
  });

  const total = monthly.reduce((a,b)=>a+b,0);
  const hasProj = monthProj.some(Boolean);
  document.getElementById('divDrill').innerHTML =
    `<div class="div-drill-head">${_divYear}년 합계: ${_fmtDivMoney(total)}` +
    (hasProj ? ' <span style="color:#FB8C00;font-size:0.76rem;">(주황 = 예측)</span>' : '') + `</div>`;

  renderMonthGrid(monthly, monthProj);
  renderList(evs);
  renderDivNote();
}

function renderMonthGrid(monthly, monthProj){
  const grid = document.getElementById('divMonthGrid');
  grid.innerHTML = monthly.map((amt,i) => {
    const has = amt > 0;
    const cls = 'div-month-box' + (has ? '' : ' empty') + ((_divActiveMonth===i+1)?' active':'');
    const amtTxt = has ? _fmtDivMoney(amt) : '—';
    return `<div class="${cls}" ${has?`data-month="${i+1}"`:''}>
      <div class="m-label">${i+1}월${monthProj[i] && has ? ' *' : ''}</div>
      <div class="m-amt">${amtTxt}</div>
    </div>`;
  }).join('');
  if (_divActiveMonth) renderMonthDetail(_divActiveMonth);
  else document.getElementById('divMonthDetail').innerHTML = '';
}

function showMonth(month){
  _divActiveMonth = (_divActiveMonth === month) ? null : month;
  document.querySelectorAll('#divMonthGrid .div-month-box').forEach(b =>
    b.classList.toggle('active', !!(b.dataset.month && parseInt(b.dataset.month) === _divActiveMonth)));
  if (_divActiveMonth) renderMonthDetail(_divActiveMonth);
  else document.getElementById('divMonthDetail').innerHTML = '';
}

function renderMonthDetail(month){
  const evs = (_divData.events[_divYear] || []).filter(e => e.month === month);
  const byCode = {};
  evs.forEach(e => {
    if (!byCode[e.code]) byCode[e.code] = { name:e.name, val:0, dates:[], proj:false };
    byCode[e.code].val += _valOf(e);
    byCode[e.code].dates.push(e.date.slice(5));
    if (e.projected) byCode[e.code].proj = true;
  });
  const rows = Object.values(byCode).sort((a,b)=>b.val-a.val);
  const total = rows.reduce((s,v)=>s+v.val,0);
  let html = `<div class="div-month-table"><div class="div-drill-head" style="padding:8px 12px;border-bottom:1px solid var(--border);">${month}월 배당: ${_fmtDivMoney(total)}</div>`;
  if (!rows.length) {
    html += '<div style="color:var(--text-muted);font-size:0.82rem;padding:10px 12px;">이 달은 배당이 없습니다.</div>';
  } else {
    rows.forEach(v => {
      html += `<div class="div-list-item"><span class="div-list-date" style="min-width:64px;">${v.dates.join(', ')}</span>` +
        `<span class="div-list-name">${esc(v.name)}${v.proj?'<span class="div-proj-badge">예측</span>':''}</span>` +
        `<span class="div-list-amt">${_fmtDivMoney(v.val)}</span></div>`;
    });
  }
  html += '</div>';
  document.getElementById('divMonthDetail').innerHTML = html;
}

function renderList(evs){
  const el = document.getElementById('divCal');
  if (!evs.length) { el.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem;padding:10px 12px;">배당 일정이 없습니다.</div>'; return; }
  const byCode = {};
  evs.forEach(e => {
    if (!byCode[e.code]) byCode[e.code] = { name:e.name, val:0, months:new Set(), anyProj:false };
    const g = byCode[e.code]; g.val += _valOf(e); g.months.add(e.month); if (e.projected) g.anyProj = true;
  });
  const rows = Object.values(byCode).sort((a,b)=>b.val-a.val);
  el.innerHTML = rows.map(g => {
    const months = [...g.months].sort((a,b)=>a-b).map(m=>m+'월').join('·');
    return `<div class="div-list-item"><span class="div-list-date" style="width:auto;min-width:78px;">${months}</span>` +
      `<span class="div-list-name">${esc(g.name)}${g.anyProj?'<span class="div-proj-badge">예측</span>':''}</span>` +
      `<span class="div-list-amt">${_fmtDivMoney(g.val)}</span></div>`;
  }).join('');
}

function renderDivNote(){
  const note = [];
  note.push('※ 입력한 <b>총 투자금액 × 비중</b>으로 현재 매수했다고 가정해 계산합니다.');
  note.push(`※ ${_divData.current_year}년은 실데이터가 있는 달까지는 실적, 이후 달과 ${_divData.full_proj_year}년은 종목별 최근 5년 배당성장률(CAGR) 기반 <b>예측치</b>입니다.`);
  if (_divData.has_foreign) note.push('※ 해외 종목 배당은 배당 당시 환율로 환산, 미래 예측은 현재 환율 기준입니다.');
  note.push('더 정확한 과거 성과·미래 전망은 ' +
    '<a href="/backtest" style="color:var(--blue);font-weight:600;">포트폴리오 백테스트</a> · ' +
    '<a href="/calculator" style="color:var(--blue);font-weight:600;">투자계산기</a> 탭을 이용해 보세요.');
  document.getElementById('divNote').innerHTML = note.join('<br>');
}

// 토글 이벤트
document.addEventListener('click', e => {
  const t = e.target.closest('[data-div-tax]');
  if (t) { _divTax = t.dataset.divTax; document.querySelectorAll('[data-div-tax]').forEach(b=>b.classList.toggle('active', b===t)); if (_divData) renderDivYear(); return; }
  const c = e.target.closest('[data-div-cur]');
  if (c) { _divCur = c.dataset.divCur; document.querySelectorAll('[data-div-cur]').forEach(b=>b.classList.toggle('active', b===c)); if (_divData) renderDivYear(); return; }
  const y = e.target.closest('[data-div-year]');
  if (y) { _divYear = parseInt(y.dataset.divYear); _divActiveMonth = null; document.querySelectorAll('[data-div-year]').forEach(b=>b.classList.toggle('active', b===y)); renderDivYear(); return; }
  const mb = e.target.closest('#divMonthGrid .div-month-box[data-month]');
  if (mb) { showMonth(parseInt(mb.dataset.month)); }
});

document.getElementById('pdAmount').addEventListener('keydown', e => { if (e.key === 'Enter') applyAmount(); });

loadPortfolio();
