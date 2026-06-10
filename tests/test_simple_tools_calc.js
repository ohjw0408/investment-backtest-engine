/**
 * 간편 계산기 순수함수 손계산 검증 (DOM 불필요).
 * 실행: node tests/test_simple_tools_calc.js
 */
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'simple_tools.js'), 'utf8');
eval(src); // document undefined → stInit 가드로 스킵, 순수함수만 정의됨

let pass = 0, fail = 0;
function check(name, actual, expected, tol) {
  tol = tol === undefined ? 1e-6 : tol;
  const ok = Math.abs(actual - expected) <= tol * Math.max(1, Math.abs(expected));
  if (ok) { pass++; console.log(`PASS  ${name}: ${actual}`); }
  else { fail++; console.log(`FAIL  ${name}: actual=${actual} expected=${expected}`); }
}

// ── 복리 1: 거치식 폐형식 — P0×(1+r)^N (월율=기하환산이라 정확히 일치해야 함)
{
  const r = stCompound({ initial: 10000000, monthly: 0, annualReturn: 0.07, years: 10, annualIncrease: 0, taxed: false, inflation: 0 });
  check('compound 거치식 10M×1.07^10', r.final, 10000000 * Math.pow(1.07, 10));
  check('compound 거치식 원금', r.principal, 10000000);
}

// ── 복리 2: 수익률 0% — 평가액 = 원금
{
  const r = stCompound({ initial: 1000000, monthly: 100000, annualReturn: 0, years: 3, annualIncrease: 0, taxed: false, inflation: 0 });
  check('compound r=0 평가액=원금', r.final, 1000000 + 100000 * 36);
  check('compound r=0 수익=0', r.gain, 0, 1e-9);
}

// ── 복리 3: 과세 = 세후 수익률 r×(1−0.154)로 거치식 일치
{
  const rNet = 0.07 * (1 - 0.154);
  const r = stCompound({ initial: 10000000, monthly: 0, annualReturn: 0.07, years: 10, annualIncrease: 0, taxed: true, inflation: 0 });
  check('compound 과세 거치식', r.final, 10000000 * Math.pow(1 + rNet, 10));
}

// ── 복리 4: 인플레 조정 — 실질 = 명목/(1+i)^N
{
  const r = stCompound({ initial: 10000000, monthly: 0, annualReturn: 0.07, years: 10, annualIncrease: 0, taxed: false, inflation: 0.025 });
  check('compound 실질가치', r.realFinal, 10000000 * Math.pow(1.07, 10) / Math.pow(1.025, 10));
}

// ── 복리 5: 연증액 — r=0, 월10만, 증액 10%, 2년 → 원금 = 12×10만 + 12×11만
{
  const r = stCompound({ initial: 0, monthly: 100000, annualReturn: 0, years: 2, annualIncrease: 0.10, taxed: false, inflation: 0 });
  check('compound 연증액 원금', r.principal, 100000 * 12 + 110000 * 12);
}

// ── 복리 6: 월초 적립 검증 — 1년, 월적립만: FV = M×Σ(1+rm)^k, k=1..12
{
  const rm = Math.pow(1.07, 1 / 12) - 1;
  let fv = 0;
  for (let k = 1; k <= 12; k++) fv += 100000 * Math.pow(1 + rm, k);
  const r = stCompound({ initial: 0, monthly: 100000, annualReturn: 0.07, years: 1, annualIncrease: 0, taxed: false, inflation: 0 });
  check('compound 월초적립 FV 공식', r.final, fv);
}

// ── 인플레 생활비: 300만, 2.5%, 20년 → 300만×1.025^20
{
  const r = stInflationCost({ monthlyCost: 3000000, inflation: 0.025, years: 20 });
  check('inflation 미래 월생활비', r.futureMonthly, 3000000 * Math.pow(1.025, 20));
  // 누적 = Σ_{y=1..20} 12×300만×1.025^y
  let cum = 0;
  for (let y = 1; y <= 20; y++) cum += 12 * 3000000 * Math.pow(1.025, y);
  check('inflation 누적', r.totalCumulative, cum);
  check('inflation 표 길이', r.yearly.length, 20, 0);
}

// ── 실질 구매력: 1억, 2.5%, 20년
{
  const r = stRealValue({ amount: 100000000, inflation: 0.025, years: 20 });
  check('realvalue 실질', r.real, 100000000 / Math.pow(1.025, 20));
  check('realvalue 하락률', r.lossPct, 1 - 1 / Math.pow(1.025, 20));
  check('realvalue 필요명목', r.requiredNominal, 100000000 * Math.pow(1.025, 20));
}

// ── 배당 1: 배당0%·성장0% → 평가액=원금 (무수익)
{
  const r = stDividendReinvest({ initial: 1000000, monthly: 100000, annualIncrease: 0, divYield: 0, divGrowth: 0, frequency: 'quarterly', taxed: true, inflation: 0, years: 2 });
  check('dividend 무수익 평가액=원금', r.final, 1000000 + 100000 * 24);
  check('dividend 무수익 누적배당=0', r.cumDividends, 0, 1e-9);
}

// ── 배당 2: 거치식 1년 분기배당 비과세 — 손계산 재현
//   가격성장 0%, yield 4%, 분기 → 분기마다 value×1% 재투자 → 1년 후 = P0×1.01^4
{
  const r = stDividendReinvest({ initial: 10000000, monthly: 0, annualIncrease: 0, divYield: 0.04, divGrowth: 0, frequency: 'quarterly', taxed: false, inflation: 0, years: 1 });
  check('dividend 분기복리 1.01^4', r.final, 10000000 * Math.pow(1.01, 4));
  check('dividend 누적배당', r.cumDividends, 10000000 * (Math.pow(1.01, 4) - 1));
}

// ── 배당 3: 과세 — 분기 net = gross×(1−0.154) → 1년 후 = P0×(1+0.01×0.846)^4
{
  const r = stDividendReinvest({ initial: 10000000, monthly: 0, annualIncrease: 0, divYield: 0.04, divGrowth: 0, frequency: 'quarterly', taxed: true, inflation: 0, years: 1 });
  check('dividend 과세 분기복리', r.final, 10000000 * Math.pow(1 + 0.01 * (1 - 0.154), 4));
}

// ── 배당 4: 월배당 — 1년 = P0×(1+y/12)^12 ×(가격성장 월복리), 성장 6%
//   월: value×(1+gm) 후 배당 → factor = ((1+gm)(1+y/12))^12
{
  const gm = Math.pow(1.06, 1 / 12) - 1;
  const factor = Math.pow((1 + gm) * (1 + 0.03 / 12), 12);
  const r = stDividendReinvest({ initial: 10000000, monthly: 0, annualIncrease: 0, divYield: 0.03, divGrowth: 0.06, frequency: 'monthly', taxed: false, inflation: 0, years: 1 });
  check('dividend 월배당+성장 결합', r.final, 10000000 * factor);
}

// ── 배당 5: 마지막 해 연배당/월평균 정합
{
  const r = stDividendReinvest({ initial: 10000000, monthly: 500000, annualIncrease: 0.05, divYield: 0.035, divGrowth: 0.08, frequency: 'quarterly', taxed: true, inflation: 0.025, years: 20 });
  const last = r.yearly[r.yearly.length - 1];
  check('dividend lastYear == 표 마지막 연배당', r.lastYearDividends, last.annualDiv);
  check('dividend 월평균 = 연배당/12', r.lastYearMonthlyAvg, last.annualDiv / 12);
  check('dividend 누적 = 표 마지막 누적', r.cumDividends, last.cumDiv);
  check('dividend 실질 = 명목/(1+i)^20', r.realFinal, last.value / Math.pow(1.025, 20));
  // 단조 증가 (성장+적립 양수)
  let mono = true;
  for (let i = 1; i < r.yearly.length; i++) if (r.yearly[i].value <= r.yearly[i - 1].value) mono = false;
  check('dividend 평가액 단조증가', mono ? 1 : 0, 1, 0);
}

console.log(`\n${pass} PASS / ${fail} FAIL`);
process.exit(fail ? 1 : 0);
