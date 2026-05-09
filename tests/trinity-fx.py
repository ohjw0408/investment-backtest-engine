"""
test_fx_effect.py
────────────────────────────────────────────────────────────────────────────────
환율 효과 비교 테스트

[KRW 모드] 현재 시뮬: SPY 원화 가격 기준 (환율 효과 포함)
[USD 모드] SPY 달러 가격 기준 (환율 효과 제거)
           SPY_USD = SPY_KRW / USD_KRW

두 모드의 4% 룰 생존율을 비교해서
환율이 결과에 얼마나 영향을 미치는지 확인.

USD 모드 기대값: Trinity Study 기준 ~95% (인플레 3%)
────────────────────────────────────────────────────────────────────────────────
"""

import sys, sqlite3, datetime, multiprocessing
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
if not (ROOT / "modules").exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

multiprocessing.freeze_support()

PRICE_DB = ROOT / "data" / "price_cache"  / "price_daily.db"
INDEX_DB = ROOT / "data" / "meta" / "index_master.db"
DATA_START = "1964-05-04"


def load_spy_krw() -> pd.Series:
    conn  = sqlite3.connect(str(PRICE_DB))
    rows  = conn.execute(
        "SELECT date, close FROM price_daily WHERE code='SPY' ORDER BY date"
    ).fetchall()
    conn.close()
    s = pd.Series(
        {pd.Timestamp(r[0]): float(r[1]) for r in rows}
    )
    return s[s.index >= DATA_START]


def load_usdkrw() -> pd.Series:
    conn  = sqlite3.connect(str(INDEX_DB))
    rows  = conn.execute(
        "SELECT date, close FROM index_daily WHERE code='USD/KRW' ORDER BY date"
    ).fetchall()
    conn.close()
    s = pd.Series(
        {pd.Timestamp(r[0]): float(r[1]) for r in rows}
    )
    return s[s.index >= DATA_START]


def monthly_returns(prices: pd.Series) -> pd.Series:
    """거래일 기준 월말 가격으로 월수익률 계산."""
    monthly = prices.resample("ME").last().dropna()
    return monthly.pct_change().dropna()


def rolling_survival(
    rets:          pd.Series,
    window_years:  int,
    withdrawal_pct: float,
    inflation:     float,
    step_months:   int = 6,
) -> dict:
    """
    단순 rolling 생존율 계산 (numpy, 배당/리밸런싱 없음).
    rets: 월수익률 시계열
    """
    n_months   = window_years * 12
    n_rets     = len(rets)
    successes  = 0
    total      = 0
    end_ratios = []

    i = 0
    while i + n_months <= n_rets:
        window_rets = rets.iloc[i: i + n_months].values

        # 초기 자산 = 1.0 (정규화)
        portfolio  = 1.0
        monthly_wd = withdrawal_pct / 12   # 연 인출율 → 월
        current_wd = monthly_wd
        depleted   = False

        for m, r in enumerate(window_rets):
            portfolio  = portfolio * (1.0 + r) - current_wd
            # 연간 인플레이션 반영
            if (m + 1) % 12 == 0:
                current_wd *= (1.0 + inflation)
            if portfolio <= 0:
                portfolio = 0.0
                depleted  = True
                break

        successes  += 0 if depleted else 1
        end_ratios.append(max(portfolio, 0.0))
        total      += 1
        i          += step_months

    return {
        "survival_rate": successes / total if total > 0 else 0.0,
        "n_cases":       total,
        "end_ratio_p10": float(np.percentile(end_ratios, 10)) if end_ratios else 0.0,
        "end_ratio_p50": float(np.percentile(end_ratios, 50)) if end_ratios else 0.0,
    }


def main():
    print("=" * 68)
    print("환율 효과 비교: KRW 모드 vs USD 모드")
    print("=" * 68)

    # ── 데이터 로드 ───────────────────────────────────────
    print("\n데이터 로드 중...")
    spy_krw = load_spy_krw()
    usdkrw  = load_usdkrw()

    # price_daily.db의 SPY 가격은 USD 기준 저장
    # KRW 변환: spy_krw = spy_usd * usdkrw
    common  = spy_krw.index.intersection(usdkrw.index)
    spy_usd = spy_krw.loc[common]
    usdkrw  = usdkrw.loc[common]
    spy_krw = spy_usd * usdkrw

    print(f"  SPY USD: {spy_usd.index[0].date()} ~ {spy_usd.index[-1].date()}  ({len(spy_usd):,}일)")
    print(f"  USD/KRW: {usdkrw.iloc[0]:.0f} → {usdkrw.iloc[-1]:.0f}")
    print(f"  SPY USD: ${spy_usd.iloc[0]:.2f} → ${spy_usd.iloc[-1]:.2f}")
    print(f"  SPY KRW: {spy_krw.iloc[0]:,.0f} → {spy_krw.iloc[-1]:,.0f}원")

    # ── 월수익률 계산 ─────────────────────────────────────
    rets_usd = monthly_returns(spy_usd)
    rets_krw = monthly_returns(spy_krw)

    print(f"\n  KRW 월수익률: 평균={rets_krw.mean():.2%}  std={rets_krw.std():.2%}")
    print(f"  USD 월수익률: 평균={rets_usd.mean():.2%}  std={rets_usd.std():.2%}")
    print(f"  연환산 KRW CAGR: {(1+rets_krw.mean())**12-1:.2%}")
    print(f"  연환산 USD CAGR: {(1+rets_usd.mean())**12-1:.2%}")

    # ── 4% 룰, 인플레 케이스별 비교 ──────────────────────
    print(f"\n{'=' * 68}")
    print("4% 룰  30년  인플레별 생존율 비교")
    print(f"  {'인플레':<12s}  {'KRW 생존율':>10s}  {'USD 생존율':>10s}  "
          f"{'KRW p50':>8s}  {'USD p50':>8s}")
    print(f"  {'-'*60}")

    for inf in [0.00, 0.02, 0.03, 0.04]:
        krw = rolling_survival(rets_krw, 30, 0.04, inf)
        usd = rolling_survival(rets_usd, 30, 0.04, inf)
        print(f"  {inf:.0%}{'':<9s}  {krw['survival_rate']:>10.1%}  {usd['survival_rate']:>10.1%}  "
              f"  {krw['end_ratio_p50']:>6.1f}x  {usd['end_ratio_p50']:>6.1f}x")

    # ── 인출율별 비교 (인플레 3%) ─────────────────────────
    print(f"\n{'=' * 68}")
    print("인출율별 생존율 (인플레 3%)")
    print(f"  {'인출율':<10s}  {'KRW 생존율':>10s}  {'USD 생존율':>10s}  Trinity 기준")
    print(f"  {'-'*55}")

    trinity_ref = {0.03: "~100%", 0.04: "~95%", 0.05: "~80%", 0.06: "~65%"}
    for pct in [0.03, 0.04, 0.05, 0.06]:
        krw = rolling_survival(rets_krw, 30, pct, 0.03)
        usd = rolling_survival(rets_usd, 30, pct, 0.03)
        ref = trinity_ref[pct]
        print(f"  {pct:.0%}{'':<7s}  {krw['survival_rate']:>10.1%}  {usd['survival_rate']:>10.1%}  {ref}")

    # ── 연도별 기간 수익률 비교 ───────────────────────────
    print(f"\n{'=' * 68}")
    print("10년 구간별 KRW vs USD CAGR 비교")
    print(f"  {'구간':<15s}  {'KRW CAGR':>10s}  {'USD CAGR':>10s}  {'FX 기여':>8s}")
    print(f"  {'-'*50}")

    decades = [
        ("1964-1974", "1964", "1974"),
        ("1974-1984", "1974", "1984"),
        ("1984-1994", "1984", "1994"),
        ("1994-2004", "1994", "2004"),
        ("2004-2014", "2004", "2014"),
        ("2014-2024", "2014", "2024"),
    ]
    for label, s, e in decades:
        try:
            s_ts, e_ts = pd.Timestamp(s), pd.Timestamp(e)
            k = spy_krw.loc[s_ts:e_ts]
            u = spy_usd.loc[s_ts:e_ts]
            if len(k) < 2: continue
            cagr_k = (k.iloc[-1] / k.iloc[0]) ** (1/10) - 1
            cagr_u = (u.iloc[-1] / u.iloc[0]) ** (1/10) - 1
            fx_contrib = cagr_k - cagr_u
            print(f"  {label:<15s}  {cagr_k:>10.2%}  {cagr_u:>10.2%}  {fx_contrib:>+8.2%}")
        except Exception:
            pass

    print(f"\n{'=' * 68}")
    print("결론: USD 모드 생존율이 Trinity Study와 비슷하면 시뮬 로직 정상.")
    print("      KRW 모드가 높은 건 환율 효과(원화 약세)가 수익을 부스팅한 것.")


if __name__ == "__main__":
    main()