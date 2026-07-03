// tax_settings.html 인라인 스크립트 외부화 (출시완성도 E-3, 2026-07-03) — 내용 무변경 이동
const STORAGE_KEY = 'domino_tax_settings';
const toggleAccounts = ['pension', 'harvest'];

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

const state = { pension: false, harvest: false };

function toggleAccount(name) {
  state[name] = !state[name];
  const btn  = document.getElementById('toggle-' + name);
  const body = document.getElementById('body-' + name);
  const card = document.getElementById('card-' + name);
  btn.classList.toggle('on', state[name]);
  card.classList.toggle('active', state[name]);
  if (body) body.classList.toggle('show', state[name]);
}

async function saveSettings() {
  const settings = {
    earned_income: parseFloat(document.getElementById('earnedIncome').value) || 0,
    age:           parseInt(document.getElementById('userAge').value) || 40,
    pension_age:   parseInt(document.getElementById('pensionAge').value) || 65,
    isa_type:      document.querySelector('input[name="isaType"]:checked')?.value || 'none',
    accounts:      { ...state },
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  try {
    const me = await fetch('/api/me').then(r => r.json());
    if (me.logged_in) {
      await fetch('/api/settings/tax', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(settings),
      });
    }
  } catch(e) {}
  updateSummary();
  const toast = document.getElementById('saveToast');
  toast.style.display = 'block';
  setTimeout(() => toast.style.display = 'none', 2000);
}

const ISA_LABELS = { none: '미가입', general: '일반형', preferential: '서민형' };

function updateSummary() {
  const age    = parseInt(document.getElementById('userAge').value) || null;
  const income = parseFloat(document.getElementById('earnedIncome').value) || 0;
  const isa    = document.querySelector('input[name="isaType"]:checked')?.value || 'none';
  document.getElementById('sum-age').textContent     = age ? age + '세' : '미입력';
  document.getElementById('sum-income').textContent  = income ? fmtKRW(income) : '미입력';
  document.getElementById('sum-isa').textContent     = ISA_LABELS[isa] || '미가입';
  document.getElementById('sum-pension').textContent = state.pension ? '사용' : '미사용';
  document.getElementById('sum-harvest').textContent = state.harvest ? '사용' : '미사용';
}

function applySettings(s) {
  if (s.earned_income != null) document.getElementById('earnedIncome').value = s.earned_income;
  if (s.age)           document.getElementById('userAge').value = s.age;
  if (s.pension_age)   document.getElementById('pensionAge').value = s.pension_age;
  const isaVal = s.isa_type || 'none';
  const radio = document.querySelector(`input[name="isaType"][value="${isaVal}"]`);
  if (radio) radio.checked = true;
  if (s.accounts) {
    toggleAccounts.forEach(name => {
      if (s.accounts[name] && !state[name]) toggleAccount(name);
    });
  }
  document.getElementById('earnedIncomeHint').textContent = s.earned_income ? fmtKRW(s.earned_income) : '';
  updateSummary();
}

async function loadSettings() {
  try {
    const me = await fetch('/api/me').then(r => r.json());
    if (me.logged_in) {
      const res = await fetch('/api/settings/tax');
      if (res.ok) {
        const dbData = await res.json();
        if (dbData && Object.keys(dbData).length > 0) {
          applySettings(dbData);
          return;
        }
      }
    }
  } catch(e) {}
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) { updateSummary(); return; }
  try { applySettings(JSON.parse(raw)); } catch(e) { updateSummary(); }
}

document.getElementById('earnedIncome').addEventListener('input', function() {
  document.getElementById('earnedIncomeHint').textContent = fmtKRW(parseFloat(this.value)||0);
});

loadSettings();
