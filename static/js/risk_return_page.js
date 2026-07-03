// risk_return.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 내용 무변경 이동
const RR_AUTH = JSON.parse(document.getElementById('page-data').textContent).auth;
const RR_COLORS = ['#1976D2','#2E7D32','#E65100','#7B1FA2','#C62828','#00838F','#F9A825','#5D4037','#455A64','#AD1457'];
const DEFAULT_BENCH = [
  {code:'SPY', name:'SPY (S&P500)'}, {code:'QQQ', name:'QQQ (나스닥100)'},
  {code:'GLD', name:'GLD (금)'}, {code:'069500', name:'KODEX 200'}, {code:'TLT', name:'TLT (미국 장기채)'},
];

let rrPortfolios = [];          // /api/portfolio/list
let rrSelected = new Set();     // 선택된 포폴 id
let rrSelectedOrder = [];       // compare order for selected portfolio ids
let rrBench = DEFAULT_BENCH.slice();
let rrSearchTimer = null;
let rrItems = [];               // 결과 items
let rrLastData = null;          // 마지막 compare 응답(리사이즈 재렌더용)
let rrTableCols = null;
let rrResizeTimer = null;
let rrVisible = [];             // 스파이더 표시여부(items와 동일 인덱스)
let rrOpacity = 0.18;
let rrScatterChart = null, rrSpiderChart = null;

const esc = window.mmEsc;  // E-1 공용화: 전역 mmEsc(base.html) 단일 구현 — 로컬 복붙 제거 (2026-07-03)
function pct(v, d=1){ return v==null ? '—' : (v*100).toFixed(d)+'%'; }
function colorOf(i){ return RR_COLORS[i % RR_COLORS.length]; }
function hexA(hex, a){ const n=Math.round(a*255).toString(16).padStart(2,'0'); return hex+n; }

// ── 포트폴리오 목록 ──
async function rrLoadPortfolios(){
  try {
    rrPortfolios = await fetch('/api/portfolio/list').then(r => r.json());
  } catch(e){ rrPortfolios = []; }
  rrSelected = new Set(rrPortfolios.map(p => p.id));   // 기본 전체 선택
  rrSelectedOrder = rrPortfolios.map(p => p.id);
  rrRenderPfList();
}
function rrRenderPfList(){
  const el = document.getElementById('rrPfList');
  if (!rrPortfolios.length) {
    el.innerHTML = '<span style="color:var(--text-muted);font-size:0.82rem;">저장된 포트폴리오가 없어요. ⭐ <a href="/myportfolios" style="color:var(--blue);">내 포트폴리오</a>에서 먼저 저장하세요.</span>';
    return;
  }
  const byId = new Map(rrPortfolios.map(p => [p.id, p]));
  const ordered = rrSelectedOrder.map(id => byId.get(id)).filter(Boolean);
  const pfRows = ordered.concat(rrPortfolios.filter(p => !rrSelected.has(p.id)));
  el.innerHTML = pfRows.map(p => {
    const on = rrSelected.has(p.id);
    const orderIdx = rrSelectedOrder.indexOf(p.id);
    const orderBtns = on ? `<span class="rr-pf-order">
        <button type="button" class="${orderIdx<=0?'off':''}" aria-disabled="${orderIdx<=0?'true':'false'}" onclick="event.preventDefault();event.stopPropagation();rrMovePf(${p.id},-1)" title="위로">&uarr;</button>
        <button type="button" class="${orderIdx>=rrSelectedOrder.length-1?'off':''}" aria-disabled="${orderIdx>=rrSelectedOrder.length-1?'true':'false'}" onclick="event.preventDefault();event.stopPropagation();rrMovePf(${p.id},1)" title="아래로">&darr;</button>
      </span>` : '';
    return `<label class="rr-pf-chk${on?' on':''}">
      <input type="checkbox" ${on?'checked':''} onchange="rrTogglePf(${p.id}, this.checked)">
      ${esc(p.name)} <span style="color:var(--text-muted);">(${p.tickers.length})</span>${orderBtns}
    </label>`;
  }).join('');
}
function rrTogglePf(id, on){
  if (on) {
    rrSelected.add(id);
    if (!rrSelectedOrder.includes(id)) rrSelectedOrder.push(id);
  } else {
    rrSelected.delete(id);
    rrSelectedOrder = rrSelectedOrder.filter(x => x !== id);
  }
  rrRenderPfList();
}
function rrMovePf(id, dir){
  const i = rrSelectedOrder.indexOf(id);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= rrSelectedOrder.length) return;
  [rrSelectedOrder[i], rrSelectedOrder[j]] = [rrSelectedOrder[j], rrSelectedOrder[i]];
  rrRenderPfList();
}

// ── 벤치마크 칩 ──
function rrRenderChips(){
  document.getElementById('rrChips').innerHTML = rrBench.length
    ? rrBench.map((b,i) =>
        `<span class="rr-chip">${esc(b.name)}<button onclick="rrRemoveBench(${i})" title="제거">✕</button></span>`).join('')
    : '<span class="rr-chip-empty">아직 없음 — 오른쪽에서 검색해 추가하세요.</span>';
}
function rrRemoveBench(i){ rrBench.splice(i,1); rrRenderChips(); }
function rrAddBench(code, name){
  if (rrBench.some(b => b.code === code) || rrBench.length >= 12) return;
  rrBench.push({code, name});
  rrRenderChips();
  document.getElementById('rrSearch').value = '';
  document.getElementById('rrDropdown').style.display = 'none';
}
document.getElementById('rrSearch').addEventListener('input', e => {
  const q = e.target.value.trim();
  const dd = document.getElementById('rrDropdown');
  clearTimeout(rrSearchTimer);
  if (!q) { dd.style.display = 'none'; return; }
  rrSearchTimer = setTimeout(async () => {
    try {
      const data = await fetch(`/api/search?q=${encodeURIComponent(q)}`).then(r => r.json());
      if (!data.length) { dd.innerHTML = '<div class="rr-dd-item">검색 결과 없음</div>'; dd.style.display = 'block'; return; }
      dd.innerHTML = data.slice(0,8).map(item => `
        <div class="rr-dd-item" data-code="${esc(item.code)}" data-name="${esc(item.name)}">
          <span style="font-weight:700;">${esc(item.code)}</span>
          <span style="color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(item.name)}</span>
        </div>`).join('');
      dd.style.display = 'block';
      dd.querySelectorAll('.rr-dd-item[data-code]').forEach(el =>
        el.addEventListener('click', () => rrAddBench(el.dataset.code, el.dataset.name)));
    } catch(err){}
  }, 250);
});
document.addEventListener('click', e => {
  if (!e.target.closest('.rr-search-wrap')) document.getElementById('rrDropdown').style.display = 'none';
});

function rrSetCompareChartsLoading(on){
  const loading = document.getElementById('rrCompareChartsLoading');
  const charts = document.getElementById('rrCompareCharts');
  if (!loading || !charts) return;
  if (on){
    charts.style.display = 'none';
    loading.style.display = 'block';
    loading.classList.remove('rr-chart-reveal');
    void loading.offsetWidth;
    loading.classList.add('rr-chart-reveal');
  } else {
    loading.style.display = 'none';
  }
}
function rrShowCompareCharts(){
  const loading = document.getElementById('rrCompareChartsLoading');
  const charts = document.getElementById('rrCompareCharts');
  if (loading) loading.style.display = 'none';
  if (!charts) return;
  charts.style.display = 'block';
  charts.classList.remove('rr-chart-reveal');
  void charts.offsetWidth;
  charts.classList.add('rr-chart-reveal');
}

// ── 비교 실행 ──
async function rrCompare(){
  const btn = document.getElementById('rrCompareBtn');
  const status = document.getElementById('rrStatus');
  document.getElementById('rrResults').style.display = 'none';
  rrSetCompareChartsLoading(true);
  const loading = document.getElementById('rrCompareChartsLoading');
  if (loading) loading.scrollIntoView({ behavior: 'smooth', block: 'start' });
  status.style.display = 'none'; status.textContent = '';
  btn.disabled = true;
  try {
    // 즉석 빌더에 포폴이 있으면(비로그인 or 예시 프리로드) portfolios 모드, 아니면 저장 포폴 id 모드
    const adhoc = rrBuildPortfolios();
    const useAdhoc = adhoc.length > 0 || !RR_AUTH;
    const res = await fetch('/api/portfolio/compare', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(useAdhoc
        ? { portfolios: adhoc, benchmarks: rrBench }
        : { portfolio_ids: rrSelectedOrder.filter(id => rrSelected.has(id)), benchmarks: rrBench }),
    });
    const data = await res.json();
    if (!res.ok) { rrSetCompareChartsLoading(false); status.style.display = 'block'; status.textContent = data.error || '산출에 실패했어요.'; return; }
    if (!data.items || !data.items.length) {
      rrSetCompareChartsLoading(false);
      status.style.display = 'block';
      status.innerHTML = '<div class="rr-empty"><div style="font-size:1.8rem;margin-bottom:10px;">📊</div><div style="font-weight:700;">표시할 데이터가 없어요</div><div style="font-size:0.82rem;margin-top:6px;">포트폴리오를 선택하거나 벤치마크를 추가해 보세요.</div></div>';
      return;
    }
    rrItems = data.items;
    rrVisible = rrItems.map(() => true);
    status.style.display = 'none';
    rrShowCompareCharts();
    document.getElementById('rrResults').style.display = 'block';
    rrRenderTable(data);
    rrRenderScatter();
    rrRenderSpiderCtrl();
    rrRenderSpider();
    rrRenderAccordions(data);
    const chartBlock = document.getElementById('rrCompareCharts');
    if (chartBlock) chartBlock.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (rrAutoScroll) rrAutoScroll = false;
  } catch(e){ rrSetCompareChartsLoading(false); status.style.display = 'block'; status.textContent = '산출에 실패했어요. 네트워크를 확인해주세요.'; }
  finally { btn.disabled = false; }
}

// ── 심화 비교 아코디언 (P3) ──
let rrAutoScroll = false;
let rrAccCharts = {};
let rrAccSample = {};
const RR_ACC = [
  { key:'ret',  title:'수익률',        sub:'분포 오차막대 + 기간별 손실확률',
    desc:'연도별 수익률 분포를 오차막대로 요약합니다. <b>박스는 흔한 범위(p25~p75), 수염은 최저~최고, 굵은 선은 중앙값</b>입니다. 오른쪽 표는 과거 데이터상 같은 기간을 보유했을 때 손실로 끝난 사례 비율입니다.',
    get:a=>a.ret, roll:true },
  { key:'vol',  title:'변동성',
    desc:'연도별 변동성 분포입니다. <b>낮고 수염이 짧을수록</b> 출렁임이 작고 예측 가능한 포트입니다.', get:a=>a.vol },
  { key:'mdd',  title:'최대낙폭(MDD)',
    desc:'연도별 최대낙폭 분포입니다. <b>박스와 수염이 0에 가까울수록</b> 큰 손실 구간이 덜했던 포트입니다.', get:a=>a.mdd },
  { key:'div',  title:'배당',
    desc:'연도별 배당수익률 분포입니다. <b>중앙값이 높고 박스가 좁을수록</b> 현금흐름이 꾸준했습니다.', div:'dyield' },
  { key:'divg', title:'배당 성장률',
    desc:'전년 대비 배당 성장률 분포입니다. <b>중앙값이 +이고 하단 수염이 얕을수록</b> 배당 성장의 질이 좋습니다.', divg:true },
];

function rrRenderAccordions(data){
  Object.values(rrAccCharts).forEach(c=>{ try{ c.destroy(); }catch(e){} });
  rrAccCharts = {};
  rrAccSample = {};
  const items = (data.items||[]).filter(it=> (it.annual&&it.annual.length) || (it.annual_div&&it.annual_div.length));
  const host = document.getElementById('rrAccHost');
  const card = document.getElementById('rrAccordions');
  if (!items.length){ card.style.display='none'; return; }
  card.style.display='block';
  window._rrAccItems = items;
  host.innerHTML = RR_ACC.map((m,idx)=>`
    <div class="rr-acc" data-acc="${m.key}">
      <div class="rr-acc-head" onclick="rrAccToggle('${m.key}')">
        <span>${esc(m.title)}</span>${m.sub?`<span class="rr-acc-sub">· ${esc(m.sub)}</span>`:''}
        <span class="rr-acc-cy">▾</span>
      </div>
      <div class="rr-acc-wrap"><div class="rr-acc-body">
        <div class="rr-acc-desc">${m.desc}</div>
        ${rrRenderSampleCtrl(m, items)}
        ${m.roll
          ? `<div class="rr-acc-chart"><canvas id="rrAcc_${m.key}"></canvas></div>`
            + `<div id="rrLP_${m.key}" class="rr-lp-panel"></div>`
          : `<div class="rr-acc-chart"><canvas id="rrAcc_${m.key}"></canvas></div>`}
      </div></div>
    </div>`).join('');
  RR_ACC.forEach(m=>rrAccToggle(m.key));
}

function rrAccToggle(key){
  const el = document.querySelector(`.rr-acc[data-acc="${key}"]`);
  if (!el) return;
  const opening = !el.classList.contains('open');
  el.classList.toggle('open', opening);
  if (opening && !rrAccCharts[key]) rrAccDraw(key);
}

function rrAccDraw(key){
  const m = RR_ACC.find(x=>x.key===key);
  const items = window._rrAccItems || [];
  const cv = document.getElementById('rrAcc_'+key);
  if (!cv) return;
  rrAccCharts[key] = rrBoxChart(cv, items, m);
  if (m.roll) rrRenderLossProb(key, items);
}

// 전체기간 값 분포를 항목별 오차막대 1개로 — 박스=[p25,p75], 수염=[최저,최고], 중앙선.
// 연도별 겹침선 대신 "이 포트가 그 지표에서 보통 어디였나 + 좋을 때~나쁠 때"를 한눈에 비교.
const RR_YTITLE = {ret:'연 수익률', vol:'연 변동성', mdd:'연 낙폭', div:'연 배당수익률', divg:'연 배당성장률'};
const RR_SAMPLE_CHOICES = [
  ['max','최대'], ['auto','자동'], ['5','5년'], ['10','10년'], ['15','15년'],
  ['20','20년'], ['25','25년'], ['30','30년'],
];
function _rrBoxRows(it, m){
  let rows;
  if (m.divg) rows = ((it.divgrowth&&it.divgrowth.yoy)||[]).map(p=>({ year:+p.year, v:p.growth }));
  else if (m.div) rows = (it.annual_div||[]).filter(a=>!a.partial).map(a=>({ year:+a.year, v:a.dyield }));
  else rows = (it.annual||[]).filter(a=>!a.partial && !(a.syn_frac>0)).map(a=>({ year:+a.year, v:m.get(a) }));
  return rows
    .filter(r=>Number.isFinite(r.year) && r.v!=null && isFinite(r.v))
    .sort((a,b)=>a.year-b.year);
}
function rrAccAutoYears(items, m){
  const counts = items.map(it=>_rrBoxRows(it,m).length).filter(n=>n>0);
  return counts.length ? Math.min(...counts) : 0;
}
function rrSampleCaption(mode, items, m){
  if (mode === 'auto') {
    const n = rrAccAutoYears(items, m);
    return n ? `현재: 자동 · 가장 짧은 유효 표본 ${n}년에 맞춰 각 항목의 최근 ${n}개 연도만 비교합니다.`
             : '현재: 자동 · 비교할 유효 표본이 아직 부족합니다.';
  }
  if (mode === 'max') return '현재: 최대 · 각 항목의 모든 실제 가용 연도를 사용합니다.';
  return `현재: 최근 ${mode}년 · 이력이 더 짧은 항목은 가진 실제 연도만 사용합니다.`;
}
function rrRenderSampleCtrl(m, items){
  const mode = rrAccSample[m.key] || 'max';
  const buttons = RR_SAMPLE_CHOICES.map(([key,label]) =>
    `<button class="qr${mode===key?' on':''}" type="button" data-mode="${key}" onclick="rrSetAccSample('${m.key}','${key}')">${label}</button>`).join('');
  return `<div class="rr-sample-ctrl" id="rrSample_${m.key}">
    <span class="lbl">표본 길이</span>${buttons}
    <span class="rr-sample-caption">${esc(rrSampleCaption(mode, items, m))}</span>
  </div>`;
}
function rrSetAccSample(key, mode){
  rrAccSample[key] = mode;
  const m = RR_ACC.find(x=>x.key===key);
  const items = window._rrAccItems || [];
  const ctrl = document.getElementById('rrSample_'+key);
  if (ctrl && m) {
    ctrl.querySelectorAll('.qr').forEach(b=>b.classList.toggle('on', b.dataset.mode === mode));
    const cap = ctrl.querySelector('.rr-sample-caption');
    if (cap) cap.textContent = rrSampleCaption(mode, items, m);
  }
  if (rrAccCharts[key]) { try{ rrAccCharts[key].destroy(); }catch(e){} delete rrAccCharts[key]; }
  rrAccDraw(key);
}
function _rrBoxValues(it, m){
  const mode = rrAccSample[m.key] || 'max';
  const rows = _rrBoxRows(it, m);
  let sliced = rows;
  if (mode === 'auto') {
    const n = rrAccAutoYears(window._rrAccItems || [], m);
    sliced = n ? rows.slice(-n) : [];
  } else if (mode !== 'max') {
    const n = parseInt(mode, 10);
    if (Number.isFinite(n) && n > 0) sliced = rows.slice(-n);
  }
  return sliced.map(r=>r.v*100).sort((a,b)=>a-b);
}
function _rrPctl(sorted, p){
  if (!sorted.length) return null;
  if (sorted.length === 1) return sorted[0];
  const idx=(p/100)*(sorted.length-1), lo=Math.floor(idx), hi=Math.ceil(idx);
  return lo===hi ? sorted[lo] : sorted[lo]+(sorted[hi]-sorted[lo])*(idx-lo);
}
const _rrBoxPlugin = {
  id:'rrBoxWhisker',
  afterDatasetsDraw(chart, _args, opts){
    const meta = opts?.meta || chart._rrBoxMeta; if(!meta) return;
    const { ctx, scales:{x,y} } = chart;
    ctx.save();
    meta.forEach((d,i)=>{
      if (d==null) return;
      const cx = x.getPixelForValue(i);
      const half = Math.min(x.width/Math.max(chart.data.labels.length, 1)*0.18, 16);
      ctx.strokeStyle = d.col; ctx.lineWidth = 1.8;
      // 수염 세로선 최저~최고
      ctx.beginPath(); ctx.moveTo(cx, y.getPixelForValue(d.lo)); ctx.lineTo(cx, y.getPixelForValue(d.hi)); ctx.stroke();
      // 위/아래 캡
      [d.lo,d.hi].forEach(v=>{ const py=y.getPixelForValue(v); ctx.beginPath(); ctx.moveTo(cx-half,py); ctx.lineTo(cx+half,py); ctx.stroke(); });
      // 중앙값 가로선(굵게)
      const my=y.getPixelForValue(d.med); ctx.lineWidth=2.6;
      ctx.beginPath(); ctx.moveTo(cx-half*1.25,my); ctx.lineTo(cx+half*1.25,my); ctx.stroke();
    });
    ctx.restore();
  }
};
function rrBoxChart(cv, items, m){
  const txt = cssVar('--text-muted') || '#888';
  const grid = cssVar('--border') || '#e0e0e0';
  const labels=[], boxData=[], meta=[];
  let gMin=Infinity, gMax=-Infinity;
  items.forEach((it,i)=>{
    const vals = _rrBoxValues(it, m);
    const nm = it.name.length>9 ? it.name.slice(0,9)+'…' : it.name;
    if (!vals.length){ labels.push(nm); boxData.push(null); meta.push(null); return; }
    const lo=vals[0], hi=vals[vals.length-1];
    const b25=_rrPctl(vals,25), b75=_rrPctl(vals,75), med=_rrPctl(vals,50);
    labels.push(nm);
    boxData.push([+b25.toFixed(2), +b75.toFixed(2)]);
    meta.push({ lo, hi, med, col:colorOf(i), name:it.name, n:vals.length });
    gMin=Math.min(gMin,lo); gMax=Math.max(gMax,hi);
  });
  if (!isFinite(gMin)){ gMin=-10; gMax=10; }
  const span=Math.max(gMax-gMin, 1);
  const pad=m.key==='mdd' ? Math.max(span*0.22, Math.abs(gMin)*0.12, 8) : Math.max(span*0.14, 1.5);
  const yMin=Math.min(0,gMin)-pad;
  const yMax=Math.max(0,gMax)+pad;
  const ch = new Chart(cv.getContext('2d'), {
    type:'bar',
    data:{ labels, datasets:[{
      data:boxData,
      backgroundColor: meta.map(d=> d ? hexA(d.col,0.45) : 'rgba(0,0,0,0)'),
      borderColor: meta.map(d=> d ? d.col : 'rgba(0,0,0,0)'),
      borderWidth:1.4, borderSkipped:false, barPercentage:0.55, categoryPercentage:0.8,
    }]},
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{
        legend:{display:false},
        rrBoxWhisker:{ meta },
        tooltip:{ callbacks:{
          title:c=> meta[c[0].dataIndex]?.name || '',
          label:c=>{ const d=meta[c.dataIndex]; if(!d) return '표본 부족';
            return [`최고 ${d.hi.toFixed(1)}%`, `흔한 범위 ${c.raw[0].toFixed(1)}~${c.raw[1].toFixed(1)}%`,
                    `중앙값 ${d.med.toFixed(1)}%`, `최저 ${d.lo.toFixed(1)}% · 표본 ${d.n}년`]; } } }
      },
      scales:{
        x:{ ticks:{font:{size:10}, color:txt}, grid:{display:false} },
        y:{ min:yMin, max:yMax,
            ticks:{font:{size:10}, color:txt, maxTicksLimit:8, callback:v=>Math.round(v)+'%'},
            grid:{ color:c=> c.tick.value===0 ? txt : grid, lineWidth:c=> c.tick.value===0?1.4:1 },
            title:{display:true, text:RR_YTITLE[m.key]||'', color:txt, font:{size:10}} }
      }
    },
    plugins:[_rrBoxPlugin]
  });
  ch._rrBoxMeta = meta;
  return ch;
}

function rrRenderLossProb(key, items){
  const host = document.getElementById('rrLP_'+key);
  if (!host) return;
  const withRoll = items.filter(it=>it.rolling_return && it.rolling_return.horizon_table);
  if (!withRoll.length){ host.innerHTML='<div style="font-size:0.78rem;color:var(--text-muted);">롤링 데이터 없음</div>'; return; }
  const horizons = withRoll[0].rolling_return.horizons || [1,3,5,10,15,20];
  let html = '<div style="font-size:0.78rem;font-weight:700;margin-bottom:6px;">기간별 손실확률 <span style="font-weight:500;color:var(--text-muted);">(과거 표본)</span></div>';
  html += '<div style="overflow-x:auto;"><table class="rr-lp-table"><thead><tr><th>기간</th>'
    + withRoll.map((it,i)=>`<th style="color:${colorOf(items.indexOf(it))}">${esc(it.name.length>6?it.name.slice(0,6)+'…':it.name)}</th>`).join('') + '</tr></thead><tbody>';
  horizons.forEach(h=>{
    html += `<tr><td>${h}년</td>` + withRoll.map(it=>{
      const r = it.rolling_return.horizon_table[String(h)] || {};
      if (r.loss_prob==null) return '<td style="color:var(--text-muted)">—</td>';
      const lp = r.loss_prob;
      const c = lp<=0.001 ? 'var(--green,#2E7D32)' : (lp>=0.3 ? 'var(--red,#C62828)' : 'inherit');
      return `<td style="color:${c};font-weight:600;">${(lp*100).toFixed(1)}%</td>`;
    }).join('') + '</tr>';
  });
  const usesSyn = withRoll.some(it => (it.rolling_return?.syn_overall || 0) > 0.05);
  html += `</tbody></table></div><div style="font-size:0.7rem;color:var(--text-muted);margin-top:6px;line-height:1.45;">전체 가용기간·거치식·배당재투자 기준${usesSyn ? ' · 합성/추정 구간 제외' : ''}. 기간별 손실확률은 미래 손실 가능성을 보장하거나 예측하지 않으며, 과거 표본에서 해당 기간 보유 결과가 손실로 끝난 비율입니다. 0.0%는 과거 표본에 손실 사례가 없었다는 뜻일 뿐 앞으로 손실이 나지 않는다는 의미가 아닙니다. “—”=표본 부족(이력이 그 기간보다 짧음).</div>`;
  host.innerHTML = html;
}

// ── 수치표 ──
function rrRenderTable(data){
  rrLastData = data;
  const cols = [
    ['수익률(CAGR)', it => pct(it.cagr), '연평균 복리 성장률. 높을수록 좋음.'],
    ['변동성', it => pct(it.vol), '수익률이 연 단위로 출렁이는 정도. 낮을수록 안정적.'],
    ['MDD', it => pct(it.mdd), '최대 낙폭 — 고점 대비 가장 크게 떨어진 폭. 0에 가까울수록 방어적.'],
    ['Sharpe', it => it.sharpe?.toFixed(2) ?? '—', '위험(변동성) 1단위당 수익. 높을수록 효율적.'],
    ['Sortino', it => it.sortino?.toFixed(2) ?? '—', '하락 위험 대비 수익. 손실 변동만 위험으로 봄.'],
    ['배당률', it => pct(it.div_yield, 2), '최근 1년 배당금 ÷ 현재가.'],
    ['최고연', it => pct(it.best_year), '연도별 수익률 중 가장 높았던 해.'],
    ['최저연', it => pct(it.worst_year), '연도별 수익률 중 가장 낮았던 해.'],
    ['승률(월)', it => pct(it.win_rate, 0), '월간 수익이 플러스였던 달의 비율.'],
    ['베타', it => it.beta?.toFixed(2) ?? '—', 'S&P500(SPY) 대비 민감도. 1보다 크면 시장보다 더 출렁임.'],
  ];
  rrTableCols = cols;
  const host = document.getElementById('rrTableHost');
  if (window.matchMedia('(max-width:768px)').matches) {
    // 모바일 — 항목별 카드(가로스크롤 제거)
    host.innerHTML = rrItems.map((it,i) => {
      const kind = it.kind === 'portfolio' ? '내 포트폴리오' : '벤치';
      const rows = cols.map(c => `<div class="rr-mrow"><span class="l">${c[0]}</span><span class="v">${c[1](it)}</span></div>`).join('');
      return `<div class="rr-mcard"><div class="rr-mcard-head"><span class="rr-dot" style="background:${colorOf(i)}"></span>${esc(it.name)}<span class="rr-kind">${kind}</span></div><div class="rr-mgrid">${rows}</div></div>`;
    }).join('');
  } else {
    // 데스크탑 — 표
    let html = '<div class="rr-table-wrap"><table class="rr-table"><thead><tr><th>대상</th>'
      + cols.map(c => `<th title="${esc(c[2])}">${c[0]} <span style="opacity:0.5;font-weight:400;">ⓘ</span></th>`).join('') + '</tr></thead><tbody>';
    rrItems.forEach((it,i) => {
      const kind = it.kind === 'portfolio' ? '내 포트폴리오' : '벤치';
      html += `<tr><td><span class="rr-dot" style="background:${colorOf(i)}"></span>${esc(it.name)}<span class="rr-kind">${kind}</span></td>`
        + cols.map(c => `<td>${c[1](it)}</td>`).join('') + '</tr>';
    });
    html += '</tbody></table></div>';
    host.innerHTML = html;
  }

  document.getElementById('rrPeriod').textContent = data.period
    ? `비교 기간: ${data.period.start} ~ ${data.period.end} (${data.period.years}년, 전 종목 공통 겹침 구간)`
      + (data.skipped?.length ? ` · 데이터 없음 제외: ${data.skipped.join(', ')}` : '')
    : '';
  document.getElementById('rrWarn').innerHTML = data.period?.warning ? `<div class="rr-warn">⚠ ${esc(data.period.warning)}</div>` : '';
}

// ── 산점도 ──
function rrRenderScatter(){
  if (rrScatterChart) rrScatterChart.destroy();
  const datasets = rrItems.map((it,i) => ({
    label: it.name,
    data: [{ x: it.vol*100, y: it.cagr*100, name: it.name, sharpe: it.sharpe }],
    backgroundColor: colorOf(i),
    pointRadius: it.kind === 'portfolio' ? 9 : 6,
    pointHoverRadius: 11,
    pointStyle: it.kind === 'portfolio' ? 'circle' : 'rectRot',
  }));
  rrScatterChart = new Chart(document.getElementById('rrScatter').getContext('2d'), {
    type: 'scatter',
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { boxWidth: 10, font: { size: 10 }, usePointStyle: true } },
        tooltip: { callbacks: { label: ctx => {
          const d = ctx.raw;
          return `${d.name} — CAGR ${d.y.toFixed(1)}% · 변동성 ${d.x.toFixed(1)}% · 샤프 ${d.sharpe.toFixed(2)}`;
        } } },
      },
      scales: {
        x: { title: { display: true, text: '연 변동성 (%)' }, ticks: { callback: v => v+'%' }, grid: { color: MM_CHART_GRID } },
        y: { title: { display: true, text: 'CAGR (%)' }, ticks: { callback: v => v+'%' }, grid: { color: MM_CHART_GRID } },
      },
    },
  });
}

// ── 스파이더 ──
const SPIDER_POOL = [
  { key:'cagr',    label:'수익률',  get: it => it.cagr,          invert:false, desc:'연평균 복리 성장률(CAGR). 높을수록 좋음.' },
  { key:'stab',    label:'안정성',  get: it => it.vol,           invert:true,  desc:'가격 출렁임(연 변동성)이 낮을수록 높음.' },
  { key:'def',     label:'방어력',  get: it => Math.abs(it.mdd), invert:true,  desc:'고점 대비 최대 하락(MDD)이 작을수록 높음.' },
  { key:'div',     label:'배당률',  get: it => it.div_yield,     invert:false, desc:'최근 1년 배당금 ÷ 현재가.' },
  { key:'sharpe',  label:'Sharpe',  get: it => it.sharpe,        invert:false, desc:'위험(변동성) 1단위당 수익. 위험 대비 효율.' },
  { key:'sortino', label:'Sortino', get: it => it.sortino,       invert:false, desc:'하락 위험 대비 수익. 손실 변동만 위험으로 봄.' },
  { key:'win',     label:'승률',    get: it => it.win_rate,      invert:false, desc:'월간 수익이 플러스였던 달의 비율.' },
];
let rrAxisKeys = ['cagr','stab','def','div','sharpe','sortino'];   // 기본 6축
function rrAxes(){ return SPIDER_POOL.filter(a => rrAxisKeys.includes(a.key)); }
function rrNormAxis(vals, invert){
  const fin = vals.filter(v => v != null && isFinite(v));
  const mn = Math.min(...fin), mx = Math.max(...fin);
  return vals.map(v => {
    if (v == null || !isFinite(v)) return 0.15;
    let t = mx === mn ? 0.6 : (v - mn) / (mx - mn);
    if (invert) t = 1 - t;
    return 0.15 + 0.85 * t;
  });
}
function rrRenderSpiderCtrl(){
  // 축 선택 + 설명
  const axisBoxes = SPIDER_POOL.map(a => {
    const on = rrAxisKeys.includes(a.key);
    return `<label class="rr-vis" title="${esc(a.desc)}"><input type="checkbox" ${on?'checked':''} onchange="rrToggleAxis('${a.key}', this.checked)">${a.label}</label>`;
  }).join('');
  const descList = rrAxes().map(a => `<div><b>${a.label}</b> — ${esc(a.desc)}</div>`).join('');

  // 항목 표시 토글 + 투명도
  const itemBoxes = rrItems.map((it,i) =>
    `<label class="rr-vis"><input type="checkbox" ${rrVisible[i]?'checked':''} onchange="rrToggleVis(${i}, this.checked)">
      <span class="rr-dot" style="background:${colorOf(i)}"></span>${esc(it.name)}</label>`).join('');

  document.getElementById('rrSpiderCtrl').innerHTML =
    `<div style="flex-basis:100%;font-size:0.76rem;color:var(--text-muted);font-weight:700;">꼭짓점(축) 선택 · 최소 3개</div>
     <div style="flex-basis:100%;display:flex;flex-wrap:wrap;gap:6px 14px;">${axisBoxes}</div>
     <div style="flex-basis:100%;font-size:0.72rem;color:var(--text-muted);line-height:1.55;background:var(--bg);border-radius:8px;padding:8px 12px;">${descList}</div>
     <div style="flex-basis:100%;height:1px;background:var(--border);margin:2px 0;"></div>
     <div style="flex-basis:100%;font-size:0.76rem;color:var(--text-muted);font-weight:700;">표시 항목 · 투명도</div>
     ${itemBoxes}
     <span class="rr-opacity">불투명도 <input type="range" min="0" max="100" value="${Math.round(rrOpacity*100)}" oninput="rrSetOpacity(this.value)"></span>`;
}
function rrToggleAxis(key, on){
  if (on) { if (!rrAxisKeys.includes(key)) rrAxisKeys.push(key); }
  else    { if (rrAxisKeys.length <= 3) { rrRenderSpiderCtrl(); return; }  // 최소 3개 유지
            rrAxisKeys = rrAxisKeys.filter(k => k !== key); }
  // 풀 순서대로 정렬
  rrAxisKeys = SPIDER_POOL.filter(a => rrAxisKeys.includes(a.key)).map(a => a.key);
  rrRenderSpiderCtrl();
  rrRenderSpider();
}
function rrToggleVis(i, on){ rrVisible[i] = on; rrRenderSpider(); }
function rrSetOpacity(v){ rrOpacity = (parseFloat(v)||0)/100; rrRenderSpider(); }
function rrRenderSpider(){
  if (rrSpiderChart) rrSpiderChart.destroy();
  const axes = rrAxes();
  const norms = axes.map(ax => rrNormAxis(rrItems.map(ax.get), ax.invert));
  const datasets = rrItems.map((it,i) => ({
    label: it.name,
    data: axes.map((_, a) => norms[a][i]),
    raw: axes.map(ax => ax.get(it)),
    rkey: axes.map(ax => ax.key),
    borderColor: colorOf(i),
    backgroundColor: hexA(colorOf(i), rrOpacity),
    borderWidth: 2, pointRadius: 2,
    hidden: !rrVisible[i],
  }));
  rrSpiderChart = new Chart(document.getElementById('rrSpider').getContext('2d'), {
    type: 'radar',
    data: { labels: axes.map(a => a.label), datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => {
          const key = ctx.dataset.rkey[ctx.dataIndex];
          const raw = ctx.dataset.raw[ctx.dataIndex];
          const txt = (key === 'sharpe' || key === 'sortino')
            ? (raw==null?'—':raw.toFixed(2))
            : (raw==null?'—':(raw*100).toFixed(1)+'%');
          return `${ctx.dataset.label} · ${axes[ctx.dataIndex].label}: ${txt}`;
        } } },
      },
      scales: { r: { min: 0, max: 1, ticks: { display: false, stepSize: 0.25 }, grid: { color: MM_CHART_GRID },
                     pointLabels: { font: { size: 12, weight: '700' } } } },
    },
  });
}

// ── 공유 (계산기 패턴) ──
function rrMakeCanvas(){
  const el = document.getElementById('rrCapture');
  return html2canvas(el, {
    scale: 2, backgroundColor: (typeof MM_DARK !== 'undefined' && MM_DARK) ? '#0E141C' : '#F0F4F8', useCORS: true, allowTaint: true,
    onclone: function(doc, clonedEl){
      const hdr = doc.createElement('div');
      hdr.style.cssText = 'background:#1A2332;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;width:100%;box-sizing:border-box;margin-bottom:8px;border-radius:10px;';
      hdr.innerHTML = '<span style="color:#4D9FFF;font-size:0.95rem;font-weight:800;">💰 Money Milestone · 포트폴리오 비교</span>'
                    + '<span style="color:#90A4AE;font-size:0.78rem;">moneymilestone.co.kr</span>';
      clonedEl.insertBefore(hdr, clonedEl.firstChild);
      const origCanvases = el.querySelectorAll('canvas');
      const clonedCanvases = clonedEl.querySelectorAll('canvas');
      origCanvases.forEach(function(orig, i){
        const cl = clonedCanvases[i];
        if (cl && orig.width > 0) { cl.width = orig.width; cl.height = orig.height; cl.getContext('2d').drawImage(orig, 0, 0); }
      });
    }
  });
}
async function rrCopyLink(){
  const btn = event.target; const orig = btn.textContent;
  btn.textContent = '⏳ 생성 중...'; btn.disabled = true;
  try {
    const canvas = await rrMakeCanvas();
    const res = await fetch('/api/share/upload', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ image: canvas.toDataURL('image/png') }),
    });
    const { id } = await res.json();
    const url = location.origin + '/share/img/' + id;
    const box = document.getElementById('rrShareUrlBox');
    box.style.display = 'block';
    box.innerHTML = '🔗 공유 링크: <a href="' + url + '" target="_blank">' + url + '</a>';
    try { await navigator.clipboard.writeText(url); } catch(e){}
    btn.textContent = '✅ 복사됨!'; setTimeout(() => btn.textContent = orig, 2000);
  } catch(e){ btn.textContent = '⚠️ 오류'; setTimeout(() => btn.textContent = orig, 2000); }
  finally { btn.disabled = false; }
}
function rrDownloadImg(){
  if (typeof html2canvas === 'undefined') { mmToast('html2canvas 로드 중입니다.'); return; }
  rrMakeCanvas().then(function(canvas){
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = 'portfolio-comparison.png';
    a.click();
  });
}

// 표↔카드 전환 (모바일/데스크탑 경계 넘을 때)
window.addEventListener('resize', () => {
  clearTimeout(rrResizeTimer);
  rrResizeTimer = setTimeout(() => { if (rrItems.length && rrLastData) rrRenderTable(rrLastData); }, 200);
});

// ── 추세 겹쳐보기 오버레이 ──
const rrOv = { items: [], raw: {}, start: null, end: null, mode: 'norm', activeY: 5, activeEvent: null, macros: [], chart: null };
const RR_OV_QUICK = [['SYM:SPY','S&P500'],['SYM:069500','코스피200'],['SYM:GLD','금'],['SYM:TLT','미국 장기채']];
const RR_RANGE_EVENTS = [
  { key:'dotcom', label:'닷컴', start:'2000-01-01', end:'2002-12-31' },
  { key:'gfc', label:'금융위기', start:'2007-06-01', end:'2009-06-30' },
  { key:'covid', label:'코로나', start:'2020-01-01', end:'2020-12-31' },
  { key:'tightening22', label:"'22 긴축", start:'2022-01-01', end:'2022-12-31' },
];
function cssVar(n){ return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function rrOvRecolor(){ rrOv.items.forEach((it,i)=>it.color = colorOf(i)); }

async function rrOvInit(){
  fetch('/api/macro/overview').then(r=>r.json())
    .then(d=>{ rrOv.macros = []; (d.categories||[]).forEach(c=>(c.series||[]).forEach(s=>rrOv.macros.push(s))); })
    .catch(()=>{ rrOv.macros = []; });
  rrOvBindSearch();
  // 포트폴리오 예시 비교 진입 → 포폴별 병렬 요청 + 진행률 바
  if (Array.isArray(window._rrExPreload) && window._rrExPreload.length){
    const pre = window._rrExPreload; window._rrExPreload = null;
    const results = new Array(pre.length);
    let done = 0; rrOvProg(0, pre.length);
    await Promise.all(pre.map(async (p, i) => {
      try {
        const d = await fetch('/api/portfolio/index_series', { method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ portfolios: [p] }) }).then(r=>r.json());
        results[i] = (d.series || [])[0] || null;
      } catch(e){ results[i] = null; }
      done++; rrOvProg(done, pre.length);
    }));
    rrOvProg(-1);
    rrOv.raw = {}; rrOv.items = [];
    results.forEach((s, i) => { if (s){ const key='EX:'+i; rrOv.raw[key] = {...s, key, label: pre[i].name}; rrOv.items.push({key, label: pre[i].name}); } });
    if (rrOv.items.length){
      rrOvRecolor(); rrOv.start = null; rrOvSetDefaultRange();
      rrOvRenderQuick(); rrOvRenderChips(); rrOvRenderCtrl(); rrOvDraw();
      return;
    }
  }
  const n = rrPortfolios.length;
  if (n === 0) rrOv.items = [{key:'SYM:SPY',label:'S&P500'},{key:'SYM:069500',label:'코스피200'},{key:'SYM:GLD',label:'금'}];
  else if (n === 1) rrOv.items = [{key:'PF:'+rrPortfolios[0].id,label:rrPortfolios[0].name},{key:'SYM:SPY',label:'S&P500'}];
  else rrOv.items = [{key:'PF:'+rrPortfolios[0].id,label:rrPortfolios[0].name},{key:'PF:'+rrPortfolios[1].id,label:rrPortfolios[1].name},{key:'SYM:SPY',label:'S&P500'}];
  rrOvRecolor();
  rrOvLoad();
}

function rrOvRenderQuick(){
  const el = document.getElementById('rrOvQuick');
  let html = '<span class="lbl">빠른 추가:</span>';
  rrPortfolios.forEach(p=>{ const key='PF:'+p.id, on=rrOv.items.some(it=>it.key===key);
    html += `<button class="rr-ov-qbtn pf${on?' on':''}" data-key="${key}" data-label="${esc(p.name)}">${esc(p.name)}</button>`; });
  RR_OV_QUICK.forEach(([key,label])=>{ const on=rrOv.items.some(it=>it.key===key);
    html += `<button class="rr-ov-qbtn${on?' on':''}" data-key="${key}" data-label="${esc(label)}">${esc(label)}</button>`; });
  el.innerHTML = html;
  el.querySelectorAll('.rr-ov-qbtn').forEach(b=>b.addEventListener('click',()=>rrOvToggle(b.dataset.key,b.dataset.label)));
}
function rrOvToggle(key,label){ if (rrOv.items.some(it=>it.key===key)) rrOvRemove(key); else rrOvAdd(key,label); }
function rrOvAdd(key,label){
  if (rrOv.items.some(it=>it.key===key) || rrOv.items.length >= 6) return;
  rrOv.items.push({key,label,color:colorOf(rrOv.items.length)}); rrOvRecolor(); rrOvLoad();
}
function rrOvRemove(key){
  rrOv.items = rrOv.items.filter(it=>it.key!==key); rrOvRecolor();
  if (rrOv.items.length) rrOvLoad(); else { rrOvRenderQuick(); rrOvRenderChips(); rrOvRenderCtrl(); rrOvDraw(); }
}
function rrOvRenderChips(){
  const el = document.getElementById('rrOvChips');
  el.innerHTML = rrOv.items.map(it=>`<span class="rr-ov-chip" style="background:${it.color}">${esc(it.label)}<button data-key="${it.key}">✕</button></span>`).join('');
  el.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>rrOvRemove(b.dataset.key)));
}

// 진행률 바 — done<0이면 숨김
function rrOvProg(done, total){
  const sp=document.getElementById('rrOvSpinner'); if(!sp) return;
  if(done<0){ sp.style.display='none'; return; }
  sp.style.display='flex';
  const pct = total? Math.round(done/total*100):0;
  const bar=document.getElementById('rrOvProgBar'), txt=document.getElementById('rrOvProgTxt');
  if(bar) bar.style.width=pct+'%';
  if(txt) txt.textContent=`불러오는 중… ${pct}% (${done}/${total})`;
}

async function rrOvLoad(){
  rrOvRenderQuick(); rrOvRenderChips();
  if (!rrOv.items.length){ rrOvRenderCtrl(); rrOvDraw(); return; }
  // EX:(즉석 예시 포폴) 시계열은 macro/multi에 없음 → 보존하고 나머지만 조회
  const kept = {};
  rrOv.items.forEach(it=>{ if(it.key.startsWith('EX:') && rrOv.raw[it.key]) kept[it.key]=rrOv.raw[it.key]; });
  const fetchKeys = rrOv.items.map(it=>it.key).filter(k=>!k.startsWith('EX:'));
  if (fetchKeys.length){
    // 키별 병렬(동시성 4) 요청 + 진행률 — 도착하는 대로 % 채움
    let done=0; rrOvProg(0, fetchKeys.length);
    const q=[...fetchKeys];
    const worker = async () => { while(q.length){ const k=q.shift();
      try { const d=await fetch(`/api/macro/multi?keys=${encodeURIComponent(k)}`).then(r=>r.json());
        (d.series||[]).forEach(s=>kept[s.key]=s);
      } catch(e){}
      done++; rrOvProg(done, fetchKeys.length);
    }};
    await Promise.all([worker(),worker(),worker(),worker()]);
    rrOvProg(-1);
  }
  rrOv.raw = kept;
  if (!rrOv.start) rrOvSetDefaultRange();   // 최초만 기본 구간(≤5년)
  rrOvRenderCtrl(); rrOvDraw();
}
function rrOvSeriesBounds(){
  let mn=null, mx=null;
  rrOv.items.forEach(it=>{ const s=rrOv.raw[it.key]; if(!s||!s.points.length) return;
    const a=s.points[0][0], b=s.points[s.points.length-1][0];
    if(mn===null||a<mn) mn=a; if(mx===null||b>mx) mx=b; });   // mn=가장 이른 시작(전체 구간) — 늦게 시작하는 포트는 중앙값 규격화로 합류
  return {mn,mx};
}
function rrOvSetDefaultRange(){
  const {mn,mx} = rrOvSeriesBounds();
  rrOv.end = mx;
  rrOv.activeEvent = null;
  if (mx){ const d=new Date(mx); d.setFullYear(d.getFullYear()-rrOv.activeY); const cap=d.toISOString().slice(0,10);
    rrOv.start = (mn && mn>cap) ? mn : cap; } else rrOv.start = mn;
}
function rrOvRangeYears(){ if(!rrOv.start||!rrOv.end) return 0; return (new Date(rrOv.end)-new Date(rrOv.start))/(365*864e5); }

function rrOvApplyRange(start, end, activeY=-1, activeEvent=null){
  rrOv.start = start;
  rrOv.end = end;
  rrOv.activeY = activeY;
  rrOv.activeEvent = activeEvent;
  rrOvRenderCtrl();
  rrOvDraw();
}
function rrOvSetYears(yrs){
  const {mn,mx} = rrOvSeriesBounds();
  let st = mn, en = mx;
  if (yrs !== 0 && mx){
    const d = new Date(mx);
    d.setFullYear(d.getFullYear()-yrs);
    st = d.toISOString().slice(0,10);
  }
  rrOvApplyRange(st, en, yrs, null);
}
function rrOvApplyEvent(key){
  const ev = RR_RANGE_EVENTS.find(x=>x.key===key);
  if (!ev) return;
  const {mn,mx}=rrOvSeriesBounds();
  const st=(mn&&ev.start<mn)?mn:ev.start, en=(mx&&ev.end>mx)?mx:ev.end;
  if (mx&&st>mx || mn&&en<mn || st>=en){ if(typeof mmToast==='function') mmToast('그 시기엔 표시할 데이터가 없어요.','err'); return; }
  rrOvApplyRange(st, en, -1, key);
}

function rrOvRenderCtrl(){
  const el = document.getElementById('rrOvCtrl');
  if (!rrOv.items.length){ el.innerHTML=''; return; }
  const over5 = rrOv.mode==='norm' && rrOvRangeYears() > 5.05;
  const evButtons = RR_RANGE_EVENTS.map(ev =>
    `<button class="qr ev${rrOv.activeEvent===ev.key?' on':''}" data-ev="${ev.key}">${ev.label}</button>`).join('');
  el.innerHTML = `
    <span class="grp">📅 <input type="date" id="rrOvStart" value="${rrOv.start||''}"> ~ <input type="date" id="rrOvEnd" value="${rrOv.end||''}"></span>
    <span class="grp">
      <button class="qr${rrOv.activeY===1?' on':''}" data-y="1">1년</button>
      <button class="qr${rrOv.activeY===3?' on':''}" data-y="3">3년</button>
      <button class="qr${rrOv.activeY===5?' on':''}" data-y="5">5년</button>
      <button class="qr${rrOv.activeY===10?' on':''}" data-y="10">10년</button>
      <button class="qr${rrOv.activeY===0?' on':''}" data-y="0">전체</button></span>
    <span class="grp">🔍 사건확대:
      ${evButtons}
      <button class="qr" id="rrOvZoomReset" title="확대 초기화(기본 5년)">↺ 초기화</button></span>
    <span class="grp">표시:
      <label><input type="radio" name="rrovm" value="norm" ${rrOv.mode==='norm'?'checked':''}>정규화(시작=100)</label>
      <label><input type="radio" name="rrovm" value="raw" ${rrOv.mode==='raw'?'checked':''}>원값(개별축)</label></span>
    <span class="rr-ov-zoomhint" style="font-size:0.72rem;color:var(--text-muted);">💡 그래프를 <b>드래그</b>하면 그 구간만 확대돼요.</span>
    ${over5?'<span class="rr-ov-warn">⚠ 5년 초과 + 정규화는 작은 차이가 과장돼 보여요</span>':''}`;
  document.getElementById('rrOvStart').addEventListener('change',e=>rrOvApplyRange(e.target.value, rrOv.end, -1, null));
  document.getElementById('rrOvEnd').addEventListener('change',e=>rrOvApplyRange(rrOv.start, e.target.value, -1, null));
  el.querySelectorAll('input[name=rrovm]').forEach(r=>r.addEventListener('change',e=>{ rrOv.mode=e.target.value; rrOvRenderCtrl(); rrOvDraw(); }));
  el.querySelectorAll('.qr[data-y]').forEach(b=>b.addEventListener('click',()=>rrOvSetYears(+b.dataset.y)));
  el.querySelectorAll('.ev').forEach(b=>b.addEventListener('click',()=>rrOvApplyEvent(b.dataset.ev)));
  const zr=document.getElementById('rrOvZoomReset');
  if (zr) zr.addEventListener('click',()=>{ if(rrOv.chart&&rrOv.chart.resetZoom) try{rrOv.chart.resetZoom();}catch(_){}
    rrOvSetYears(5); });
}

function rrOvMedian(a){ const b=[...a].sort((x,y)=>x-y); const n=b.length; if(!n) return 0;
  return n%2 ? b[(n-1)/2] : (b[n/2-1]+b[n/2])/2; }

// 같은 x(세로축)에 모든 시리즈 값이 툴팁에 뜨도록, 각 시리즈의 시작~끝 구간 내 빈 라벨
// (다운샘플로 시리즈마다 날짜가 어긋나 생기는 null)을 날짜기준 선형보간으로 채운다.
// 보간점은 직선 세그먼트 위에 놓여 선 모양은 그대로(다운샘플 전 곡선과 동일). 구간 밖은 null 유지.
function rrOvFill(labels, map){
  const n=labels.length, out=new Array(n).fill(null);
  const t=labels.map(d=>+new Date(d));
  let prev=-1;
  for(let i=0;i<n;i++){
    if(map[labels[i]]==null) continue;
    out[i]=map[labels[i]];
    if(prev>=0 && i-prev>1){
      const v0=out[prev], v1=out[i], t0=t[prev], t1=t[i];
      for(let j=prev+1;j<i;j++) out[j]= (t1===t0)? v0 : v0+(v1-v0)*((t[j]-t0)/(t1-t0));
    }
    prev=i;
  }
  return out;
}

function rrOvDraw(){
  const canvas=document.getElementById('rrOvChart'), empty=document.getElementById('rrOvEmpty');
  if (!rrOv.items.length){ if(rrOv.chart){rrOv.chart.destroy();rrOv.chart=null;} canvas.style.display='none'; empty.style.display='block'; rrCorrRender(); return; }
  canvas.style.display=''; empty.style.display='none';
  const inR = d => (!rrOv.start || d>=rrOv.start) && (!rrOv.end || d<=rrOv.end);
  const dset=new Set();
  rrOv.items.forEach(it=>{ const s=rrOv.raw[it.key]; if(s) s.points.forEach(p=>{ if(inR(p[0])) dset.add(p[0]); }); });
  const labels=[...dset].sort();
  const txt=cssVar('--text-muted')||'#888', grid=cssVar('--border')||'#e0e0e0';
  const datasets=[]; const scales={ x:{ type:'category', ticks:{color:txt,maxTicksLimit:8,autoSkip:true}, grid:{color:grid} } };
  // 합성(추정) 구간 점선: 포인트의 3번째 값(syn=1)이면 그 세그먼트를 점선으로.
  const dashSeg = synArr => ({ borderDash: ctx => (synArr[ctx.p0DataIndex] || synArr[ctx.p1DataIndex]) ? [5,4] : undefined });
  if (rrOv.mode==='norm'){
    scales.y={ ticks:{color:txt}, grid:{color:grid}, title:{display:true,text:'정규화 (시작=100)',color:txt} };
    // 각 시리즈 = {원값맵 m, 합성맵 syn, 시작일 fd}. 시작이 늦은(중간 진입) 시리즈는 100이 아니라
    // 진입일에 이미 그려지고 있는 다른 시리즈들의 그 날 정규화값 '중앙값'에 맞춰 시작(자연 합류).
    const ser = rrOv.items.map(it=>{ const s=rrOv.raw[it.key]; if(!s) return null;
      const m={}, syn={}; s.points.forEach(p=>{ if(inR(p[0])){ m[p[0]]=p[1]; syn[p[0]]=p[2]?1:0; } });
      const fd=labels.find(d=>m[d]!=null);
      return fd ? {it,m,syn,fd} : null; }).filter(Boolean);
    const ordered=[...ser].sort((a,b)=> a.fd<b.fd?-1:(a.fd>b.fd?1:0));
    const normMap={};
    ordered.forEach(x=>{
      const baseRaw=x.m[x.fd];
      const peers=[]; ordered.forEach(y=>{ if(y!==x && normMap[y.it.key] && normMap[y.it.key][x.fd]!=null) peers.push(normMap[y.it.key][x.fd]); });
      const anchor = peers.length ? rrOvMedian(peers) : 100;
      const nm={}; labels.forEach(d=>{ if(x.m[d]!=null && baseRaw) nm[d]=+(x.m[d]/baseRaw*anchor).toFixed(2); });
      normMap[x.it.key]=nm;
    });
    rrOv.items.forEach(it=>{ const x=ser.find(z=>z.it.key===it.key); if(!x)return; const nm=normMap[it.key];
      const data=rrOvFill(labels, nm);   // 구간 내 빈 라벨 보간 → 같은 x에 전 시리즈 툴팁값
      const synArr=labels.map(d=> x.syn[d]?1:0);
      datasets.push({label:it.label,data,borderColor:it.color,backgroundColor:it.color,borderWidth:1.8,pointRadius:0,tension:0.1,spanGaps:true,segment:dashSeg(synArr)}); });
  } else {
    rrOv.items.forEach((it,i)=>{ const s=rrOv.raw[it.key]; if(!s)return;
      const m={},syn={}; s.points.forEach(p=>{ if(inR(p[0])){ m[p[0]]=p[1]; syn[p[0]]=p[2]?1:0; } });
      const ax='y'+i;
      scales[ax]={ position:i%2?'right':'left', ticks:{color:it.color,font:{size:10}}, grid:{drawOnChartArea:i===0,color:grid} };
      const data=rrOvFill(labels, m);   // 구간 내 빈 라벨 보간 → 같은 x에 전 시리즈 툴팁값
      const synArr=labels.map(d=> syn[d]?1:0);
      datasets.push({label:it.label+(s.unit?` (${s.unit})`:''),data,borderColor:it.color,backgroundColor:it.color,borderWidth:1.8,pointRadius:0,tension:0.1,spanGaps:true,yAxisID:ax,segment:dashSeg(synArr)}); });
  }
  if (rrOv.chart) rrOv.chart.destroy();
  rrOv.chart=new Chart(canvas.getContext('2d'),{ type:'line', data:{labels,datasets},
    options:{ responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
      plugins:{ legend:{labels:{color:txt,font:{size:11}}},
        tooltip:{ mode:'index', intersect:false, itemSort:(a,b)=>b.parsed.y-a.parsed.y,
          callbacks:{ label:c=> `${c.dataset.label}: ${c.parsed.y!=null ? c.parsed.y.toLocaleString(undefined,{maximumFractionDigits:2}) : '–'}` } },
        zoom:{ zoom:{ drag:{enabled:true, backgroundColor:'rgba(31,111,235,0.15)', borderColor:'rgba(31,111,235,0.45)', borderWidth:1}, mode:'x' } } }, scales } });
  rrCorrRender();
}

// ── 상관계수 계산기: 추세 겹쳐보기 항목의 월간 수익률 기준 ──
function rrCorrPointList(it){
  const pts = (rrOv.raw[it.key]?.points || [])
    .map(p => ({ d: String(p[0]), v: Number(p[1]) }))
    .filter(p => p.d && Number.isFinite(p.v) && p.v > 0)
    .sort((a,b) => a.d.localeCompare(b.d));
  return pts;
}
function rrCorrValidItems(){
  return rrOv.items.filter(it => rrCorrPointList(it).length >= 3);
}
function rrCorrBounds(){
  const starts = [], ends = [];
  rrCorrValidItems().forEach(it => {
    const pts = rrCorrPointList(it);
    starts.push(pts[0].d);
    ends.push(pts[pts.length - 1].d);
  });
  if (starts.length < 2) return null;
  starts.sort(); ends.sort();
  const mn = starts[starts.length - 1], mx = ends[0];
  return (mn && mx && mn < mx) ? { mn, mx } : null;
}
function rrCorrSetYears(yrs){
  rrOvSetYears(yrs);
}
function rrCorrClamp(){
  const b = rrCorrBounds();
  if (!b) return null;
  return b;
}
function rrCorrMonthly(it){
  const pts = rrCorrPointList(it).filter(p => !rrOv.end || p.d <= rrOv.end);
  const byMonth = {};
  pts.forEach(p => { byMonth[p.d.slice(0,7)] = p; });
  const months = Object.keys(byMonth).sort();
  const out = [];
  for (let i=1; i<months.length; i++){
    const prev = byMonth[months[i-1]], cur = byMonth[months[i]];
    if ((rrOv.start && cur.d < rrOv.start) || (rrOv.end && cur.d > rrOv.end)) continue;
    const ret = cur.v / prev.v - 1;
    if (Number.isFinite(ret) && ret > -0.9999 && Math.abs(ret) < 10) out.push({ m: months[i], date: cur.d, ret });
  }
  return out;
}
function rrCorrPair(a, b){
  const bm = new Map(b.map(x => [x.m, x.ret]));
  const xs = [], ys = [];
  a.forEach(x => { if (bm.has(x.m)){ xs.push(x.ret); ys.push(bm.get(x.m)); } });
  const n = xs.length;
  if (n < 3) return null;
  const ax = xs.reduce((s,v)=>s+v,0) / n, ay = ys.reduce((s,v)=>s+v,0) / n;
  let cov = 0, vx = 0, vy = 0;
  for (let i=0; i<n; i++){ const dx = xs[i] - ax, dy = ys[i] - ay; cov += dx * dy; vx += dx * dx; vy += dy * dy; }
  if (vx <= 1e-14 || vy <= 1e-14) return null;
  return { rho: cov / Math.sqrt(vx * vy), n };
}
function rrCorrStats(rows){
  if (!rows.length) return null;
  let eq = 1, peak = 1, mdd = 0;
  rows.forEach(r => { eq *= (1 + r.ret); peak = Math.max(peak, eq); mdd = Math.min(mdd, eq / peak - 1); });
  const mean = rows.reduce((s,r)=>s+r.ret,0) / rows.length;
  const variance = rows.length > 1 ? rows.reduce((s,r)=>s+Math.pow(r.ret - mean, 2),0) / (rows.length - 1) : 0;
  const best = rows.reduce((a,b)=> b.ret > a.ret ? b : a, rows[0]);
  const worst = rows.reduce((a,b)=> b.ret < a.ret ? b : a, rows[0]);
  return { cum: eq - 1, vol: Math.sqrt(variance) * Math.sqrt(12), mdd, best, worst, n: rows.length };
}
function rrCorrCellStyle(v){
  if (v == null) return 'color:var(--text-muted);';
  const a = Math.min(Math.abs(v), 1);
  const alpha = a >= 0.7 ? 0.18 : (a >= 0.4 ? 0.11 : 0.05);
  const bg = v < 0 ? `rgba(198,40,40,${alpha})` : `rgba(25,118,210,${alpha})`;
  const fg = v < -0.25 ? 'var(--red,#C62828)' : 'var(--text)';
  return `background:${bg};color:${fg};`;
}
function rrCorrShort(s, n=8){ s = String(s || ''); return s.length > n ? s.slice(0,n) + '…' : s; }
function rrCorrRender(){
  const card = document.getElementById('rrCorrCard');
  const ctrl = document.getElementById('rrCorrCtrl');
  const host = document.getElementById('rrCorrHost');
  if (!card || !ctrl || !host) return;
  const items = rrCorrValidItems();
  if (rrOv.items.length === 0){ card.style.display = 'none'; return; }
  card.style.display = 'block';
  if (items.length < 2){
    ctrl.innerHTML = '';
    host.innerHTML = '<div class="rr-empty" style="padding:24px 12px;">상관계수는 데이터가 있는 항목 2개 이상부터 계산됩니다.</div>';
    return;
  }
  const b = rrCorrClamp();
  if (!b){
    ctrl.innerHTML = '';
    host.innerHTML = '<div class="rr-empty" style="padding:24px 12px;">공통으로 겹치는 기간이 부족합니다.</div>';
    return;
  }
  const evButtons = RR_RANGE_EVENTS.map(ev =>
    `<button class="qr ev${rrOv.activeEvent===ev.key?' on':''}" data-ev="${ev.key}">${ev.label}</button>`).join('');
  ctrl.innerHTML = `
    <span class="grp">기간 <input type="date" id="rrCorrStart" value="${rrOv.start || ''}"> ~ <input type="date" id="rrCorrEnd" value="${rrOv.end || ''}"></span>
    <span class="grp">
      <button class="qr${rrOv.activeY===1?' on':''}" data-y="1">1년</button>
      <button class="qr${rrOv.activeY===3?' on':''}" data-y="3">3년</button>
      <button class="qr${rrOv.activeY===5?' on':''}" data-y="5">5년</button>
      <button class="qr${rrOv.activeY===10?' on':''}" data-y="10">10년</button>
      <button class="qr${rrOv.activeY===0?' on':''}" data-y="0">전체</button></span>
    <span class="grp">사건구간:
      ${evButtons}</span>`;
  document.getElementById('rrCorrStart').addEventListener('change', e => rrOvApplyRange(e.target.value, rrOv.end, -1, null));
  document.getElementById('rrCorrEnd').addEventListener('change', e => rrOvApplyRange(rrOv.start, e.target.value, -1, null));
  ctrl.querySelectorAll('.qr[data-y]').forEach(btn => btn.addEventListener('click', () => { rrCorrSetYears(+btn.dataset.y); rrCorrRender(); }));
  ctrl.querySelectorAll('.ev').forEach(btn => btn.addEventListener('click', () => rrOvApplyEvent(btn.dataset.ev)));

  const series = items.map(it => ({ it, idx: Math.max(0, rrOv.items.indexOf(it)), rows: rrCorrMonthly(it) })).filter(x => x.rows.length >= 3);
  if (series.length < 2){
    host.innerHTML = '<div class="rr-empty" style="padding:24px 12px;">선택한 기간의 월간 표본이 부족합니다.</div>';
    return;
  }
  const head = '<tr><th>대상</th>' + series.map(s => `<th title="${esc(s.it.label)}">${esc(rrCorrShort(s.it.label, 7))}</th>`).join('') + '</tr>';
  const body = series.map((a,i) => '<tr><td><span class="rr-dot" style="background:'+colorOf(a.idx)+'"></span>'+esc(rrCorrShort(a.it.label, 12))+'</td>'
    + series.map((b,j) => {
      if (i === j) return '<td class="rr-corr-cell" style="background:rgba(25,118,210,0.18);">1.00</td>';
      const p = rrCorrPair(a.rows, b.rows);
      return `<td class="rr-corr-cell" style="${rrCorrCellStyle(p?.rho)}">${p ? p.rho.toFixed(2) : '—'}</td>`;
    }).join('') + '</tr>').join('');
  const matrix = `<div class="rr-table-wrap"><table class="rr-table rr-corr-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;

  const statRows = series.map(s => {
    const st = rrCorrStats(s.rows);
    if (!st) return '';
    return `<tr><td><span class="rr-dot" style="background:${colorOf(s.idx)}"></span>${esc(rrCorrShort(s.it.label, 12))}</td>
      <td>${pct(st.cum, 1)}</td><td>${pct(st.vol, 1)}</td><td>${pct(st.mdd, 1)}</td>
      <td>${esc(st.worst.m)} · ${pct(st.worst.ret, 1)}</td><td>${esc(st.best.m)} · ${pct(st.best.ret, 1)}</td><td>${st.n}</td></tr>`;
  }).join('');
  const stats = `<div style="overflow-x:auto;"><table class="rr-lp-table"><thead><tr><th>대상</th><th>누적수익</th><th>연변동성</th><th>MDD</th><th>최악월</th><th>최고월</th><th>월수</th></tr></thead><tbody>${statRows}</tbody></table></div>`;
  host.innerHTML = `<div class="rr-corr-grid"><div>${matrix}</div><div>${stats}</div></div>
    <div class="rr-corr-note">상관계수는 월말 값으로 계산한 월간 수익률 기준입니다. 1에 가까울수록 같이 움직이고, 0에 가까울수록 관계가 약하며, 음수면 반대로 움직인 표본이 많았다는 뜻입니다.</div>`;
}

function rrOvBindSearch(){
  const inp=document.getElementById('rrOvSearch'), dd=document.getElementById('rrOvDD');
  let t=null;
  inp.addEventListener('input',()=>{ clearTimeout(t); t=setTimeout(()=>rrOvSearch(inp.value),240); });
  document.addEventListener('click',e=>{ if(!e.target.closest('#rrOvCard .rr-search-wrap')) dd.style.display='none'; });
}
async function rrOvSearch(q){
  q=q.trim(); const dd=document.getElementById('rrOvDD');
  if(!q){ dd.style.display='none'; return; }
  const ql=q.toLowerCase(); let html='';
  const ms=(rrOv.macros||[]).filter(s=>(s.name_ko||'').toLowerCase().includes(ql)).slice(0,8);
  if (ms.length) html+='<div style="padding:5px 12px;font-size:0.7rem;color:var(--text-muted);font-weight:700;">거시지표</div>'+
    ms.map(s=>`<div class="rr-dd-item" data-key="${esc(s.code)}" data-label="${esc(s.name_ko)}"><span>${esc(s.name_ko)}</span><span style="color:var(--text-muted);">${esc(s.unit||'')}</span></div>`).join('');
  try{
    const syms=await fetch(`/api/search?q=${encodeURIComponent(q)}`).then(r=>r.json());
    if (syms && syms.length) html+='<div style="padding:5px 12px;font-size:0.7rem;color:var(--text-muted);font-weight:700;">종목·ETF·지수</div>'+
      syms.slice(0,8).map(s=>`<div class="rr-dd-item" data-key="SYM:${esc(s.code)}" data-label="${esc(s.name||s.code)}"><span style="font-weight:700;">${esc(s.code)}</span><span style="color:var(--text-muted);">${esc(s.name||'')}</span></div>`).join('');
  }catch(e){}
  dd.innerHTML=html||'<div class="rr-dd-item">결과 없음</div>'; dd.style.display='block';
  dd.querySelectorAll('.rr-dd-item[data-key]').forEach(el=>el.addEventListener('click',()=>{
    rrOvAdd(el.dataset.key, el.dataset.label); document.getElementById('rrOvSearch').value=''; dd.style.display='none'; }));
}

// ── 비로그인 포트폴리오 빌더 (저장 목록 대신, 결과는 로그인과 동일 렌더 재사용) ──
let abPorts = [{ name: '포트폴리오 1', items: [] }];
function rrBuildPortfolios(){
  return abPorts.filter(p=>p.items.length).map(p=>({ name: p.name||'포트폴리오', tickers: p.items.map(x=>({code:x.code, weight:x.weight})) }));
}
function abEqualize(p){ const n=p.items.length; if(n){ const w=Math.round(100/n); p.items.forEach((it,i)=>it.weight=(i===n-1)?100-w*(n-1):w);} rrRenderBuilder(); }
function abBindSearch(inp, dd, onPick){
  let t=null;
  inp.addEventListener('input', ()=>{ const q=inp.value.trim(); clearTimeout(t);
    if(!q){ dd.style.display='none'; return; }
    t=setTimeout(async()=>{ try{
      const r=await fetch('/api/search?q='+encodeURIComponent(q)+'&limit=8').then(x=>x.json());
      const items=Array.isArray(r)?r:(r.items||[]);
      dd.innerHTML = items.length ? items.map(s=>`<div class="rr-dd-item" data-code="${esc(s.code)}" data-name="${esc(s.name||s.code)}"><span style="font-weight:700;">${esc(s.code)}</span><span style="color:var(--text-muted);">${esc(s.name||'')}</span></div>`).join('') : '<div class="rr-dd-item">결과 없음</div>';
      dd.style.display='block';
      dd.querySelectorAll('.rr-dd-item[data-code]').forEach(el=>el.onclick=()=>{ onPick(el.dataset.code, el.dataset.name); inp.value=''; dd.style.display='none'; });
    }catch(e){ dd.style.display='none'; } }, 240); });
}
function rrRenderBuilder(){
  const host=document.getElementById('rrBuilder');
  if(!host) return;
  host.innerHTML = abPorts.map((p,pi)=>{
    const rows = p.items.length ? p.items.map((it,ii)=>`
      <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);">
        <div style="flex:1;min-width:0;"><span style="font-weight:700;">${esc(it.name||it.code)}</span> <span style="color:var(--text-muted);font-size:0.76rem;">${esc(it.code)}</span></div>
        <input type="number" min="0" max="100" step="1" value="${it.weight}" class="rr-input ab-w" data-p="${pi}" data-i="${ii}" style="width:72px;text-align:right;">
        <span style="color:var(--text-muted);">%</span>
        <button class="ab-tdel" data-p="${pi}" data-i="${ii}" title="삭제" style="background:none;border:none;color:var(--text-muted);cursor:pointer;">✕</button>
      </div>`).join('') : '<div style="color:var(--text-muted);font-size:0.8rem;padding:4px 0;">종목을 검색해 추가하세요.</div>';
    const sum=p.items.reduce((s,x)=>s+(+x.weight||0),0);
    return `<div class="rr-card" style="background:var(--bg);margin-top:10px;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
        <input class="rr-input ab-name" data-p="${pi}" value="${esc(p.name)}" style="font-weight:700;flex:1;">
        ${abPorts.length>1?`<button class="ab-pdel" data-p="${pi}" title="포트폴리오 삭제" style="background:none;border:1px solid var(--border);border-radius:8px;color:var(--red,#C62828);cursor:pointer;font-weight:700;padding:5px 10px;font-size:0.76rem;">✕ 삭제</button>`:''}
      </div>
      <div class="rr-search-wrap"><input class="rr-input ab-psearch" data-p="${pi}" placeholder="🔍 종목·ETF 검색해 추가" autocomplete="off"><div class="rr-dropdown ab-pdd" data-p="${pi}"></div></div>
      <div style="margin-top:8px;">${rows}</div>
      <div style="font-size:0.76rem;color:var(--text-muted);margin-top:6px;">합계 ${sum}%${sum!==100?' · 100% 기준으로 정규화':''}</div>
    </div>`;
  }).join('');
  host.querySelectorAll('.ab-name').forEach(inp=>inp.oninput=()=>{ abPorts[+inp.dataset.p].name=inp.value; });
  host.querySelectorAll('.ab-w').forEach(inp=>inp.onchange=()=>{ abPorts[+inp.dataset.p].items[+inp.dataset.i].weight=Math.max(0,+inp.value||0); rrRenderBuilder(); });
  host.querySelectorAll('.ab-tdel').forEach(b=>b.onclick=()=>{ const p=abPorts[+b.dataset.p]; p.items.splice(+b.dataset.i,1); abEqualize(p); });
  host.querySelectorAll('.ab-pdel').forEach(b=>b.onclick=()=>{ abPorts.splice(+b.dataset.p,1); rrRenderBuilder(); });
  host.querySelectorAll('.ab-psearch').forEach(inp=>{ const dd=host.querySelector(`.ab-pdd[data-p="${inp.dataset.p}"]`);
    abBindSearch(inp, dd, (code,name)=>{ const p=abPorts[+inp.dataset.p]; if(!p.items.find(x=>x.code===code)){ p.items.push({code,name,weight:0}); abEqualize(p); } }); });
}
document.addEventListener('click', e=>{ if(!e.target.closest('#rrBuilder .rr-search-wrap')) document.querySelectorAll('#rrBuilder .rr-dropdown').forEach(d=>d.style.display='none'); });
(function(){ const a=document.getElementById('rrAddPort'); if(a) a.addEventListener('click', ()=>{ abPorts.push({name:`포트폴리오 ${abPorts.length+1}`, items:[]}); rrRenderBuilder(); }); })();

// ── 포트폴리오 예시에서 넘어온 프리로드 → 즉석 빌더에 주입(portfolios 모드로 비교) ──
function rrApplyPreload(){
  let pre=null; try{ pre=JSON.parse(sessionStorage.getItem('mm_rr_preload')||'null'); }catch(e){}
  if(!Array.isArray(pre)||!pre.length) return false;
  sessionStorage.removeItem('mm_rr_preload');
  abPorts = pre.slice(0,5).map((p,i)=>({ name:p.name||`포트폴리오 ${i+1}`,
    items:(p.tickers||[]).filter(t=>t&&t.code).map(t=>({code:t.code,name:t.name||t.code,weight:+t.weight||0})) }));
  // 추세 겹쳐보기도 비교 대상 포폴 N개만 보이게(rrOvInit이 읽어 기본 클리어 후 주입)
  window._rrExPreload = abPorts.filter(p=>p.items.length).map(p=>({ name:p.name, tickers:p.items }));
  rrRenderBuilder();
  const note=document.getElementById('rrPreNote');
  if(note){ note.style.display='block';
    note.innerHTML='<div style="font-size:0.82rem;color:var(--text-muted);margin-bottom:8px;">📥 <b style="color:var(--ds-ink,inherit);">포트폴리오 예시</b>에서 '+abPorts.length+'개를 가져왔어요. 비중·종목을 조정한 뒤 아래 <b>정밀 비교하기</b>를 누르세요.</div>'; }
  if (typeof mmToast==='function') mmToast('포트폴리오 예시 '+abPorts.length+'개를 가져왔어요.', 'ok');
  return true;
}

// init
rrRenderChips();
const _rrPre = rrApplyPreload();
if (RR_AUTH) { rrLoadPortfolios().then(rrOvInit); }
else { if(!_rrPre) rrRenderBuilder(); rrOvInit(); }
// 2모드(결정#9): 예시 유입(preload) = 자동 풀로드 + 결과로 스크롤. 직접 입력 = 수동(버튼).
if (_rrPre) { rrAutoScroll = true; setTimeout(rrCompare, 80); }
