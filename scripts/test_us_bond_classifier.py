# -*- coding: utf-8 -*-
"""
US 채권 ETF 키워드 분류기 + 통화 가드 검증.

1) 단위 케이스(만기/유형별 기대값) assert
2) 통화 가드(엔화/유로 등) assert
3) 실제 us_etf_list 'US Fixed Income' 561종 전수 적용 → 커버리지·분포·샘플
4) 한국 us_etf의 엔화노출 류 스캔(가드 대상 존재 확인)

실행: python scripts/test_us_bond_classifier.py
"""
import sys
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from modules.bond_model import classify_us_bond_etf, unsupported_currency

# ── 1) 단위 케이스: (이름, 기대 rate, 기대 duration) / None=스킵 ──
CASES = [
    ("iShares 20+ Year Treasury Bond ETF",          "DGS30", 17.0),
    ("Vanguard Long-Term Treasury ETF",             "DGS30", 17.0),
    ("iShares 7-10 Year Treasury Bond ETF",         "DGS10", 7.5),
    ("Vanguard Intermediate-Term Treasury ETF",     "DGS10", 7.5),
    ("iShares 3-7 Year Treasury Bond ETF",          "DGS10", 4.5),
    ("iShares 10-20 Year Treasury Bond ETF",        "DGS10", 9.0),
    ("iShares 1-3 Year Treasury Bond ETF",          "DGS3MO", 1.0),
    ("iShares 0-3 Month Treasury Bond ETF",         "DGS3MO", 1.0),
    ("Vanguard Short-Term Treasury ETF",            "DGS3MO", 1.0),
    ("SPDR Bloomberg 1-3 Month T-Bill ETF",         "DGS3MO", 1.0),
    ("iShares U.S. Treasury Bond ETF",              "DGS10", 6.0),   # generic
    ("iShares iBoxx $ Investment Grade Corporate Bond ETF", "DBAA", 8.0),
    ("Vanguard Short-Term Corporate Bond ETF",      "DBAA", 2.7),
    ("Vanguard Intermediate-Term Corporate Bond ETF","DBAA", 6.0),
    ("Vanguard Long-Term Corporate Bond ETF",       "DBAA", 13.0),
    ("Vanguard Total Bond Market ETF",              "DGS10", 6.0),
    ("iShares Core U.S. Aggregate Bond ETF",        "DGS10", 6.0),
]
SKIP_CASES = [  # None 기대(안전스킵)
    "iShares iBoxx $ High Yield Corporate Bond ETF",
    "SPDR Bloomberg High Yield Bond ETF",
    "iShares TIPS Bond ETF",
    "iShares National Muni Bond ETF",
    "Vanguard Tax-Exempt Bond ETF",
    "iShares MBS ETF",
    "Vanguard Total International Bond ETF",
    "iShares J.P. Morgan USD Emerging Markets Bond ETF",
    "iShares Convertible Bond ETF",
    "iShares Preferred and Income Securities ETF",
]
# ── 2) 통화 가드 케이스 ──
CCY_BLOCK = [  # True 기대(거부)
    "ACE 미국30년국채엔화노출액티브",
    "KODEX 엔화 미국채30년",
    "Some Euro Government Bond ETF",
    "위안화 중국국채 ETF",
]
CCY_OK = [  # False 기대(통과)
    "iShares 20+ Year Treasury Bond ETF",
    "ACE 미국30년국채액티브(H)",
    "KODEX 국고채10년",
]


def run_units():
    fails = []
    for name, er, ed in CASES:
        c = classify_us_bond_etf(name)
        if c is None or c["rate"] != er or abs(c["duration"] - ed) > 1e-6:
            fails.append(f"  ✗ {name!r} → {c} (기대 {er}/{ed})")
    for name in SKIP_CASES:
        c = classify_us_bond_etf(name)
        if c is not None:
            fails.append(f"  ✗ SKIP기대인데 분류됨: {name!r} → {c}")
    for name in CCY_BLOCK:
        if not unsupported_currency(name):
            fails.append(f"  ✗ 통화거부 기대인데 통과: {name!r}")
    for name in CCY_OK:
        if unsupported_currency(name):
            fails.append(f"  ✗ 통과 기대인데 거부: {name!r}")
    n_total = len(CASES) + len(SKIP_CASES) + len(CCY_BLOCK) + len(CCY_OK)
    print(f"[단위] {n_total - len(fails)}/{n_total} PASS")
    for f in fails:
        print(f)
    return not fails


def run_coverage():
    us = pd.read_csv(BASE / "data" / "meta" / "us_etf_list.csv", dtype=str)
    fi = us[us["category"] == "US Fixed Income"]
    rows = []
    for _, r in fi.iterrows():
        nm = r["name"]
        c = classify_us_bond_etf(nm)
        rows.append((nm, c["rate"] if c else "SKIP", c["duration"] if c else None,
                     unsupported_currency(nm)))
    df = pd.DataFrame(rows, columns=["name", "rate", "dur", "ccy_block"])
    classified = df[df["rate"] != "SKIP"]
    print(f"\n[커버리지] US Fixed Income {len(df)}종 → 분류 {len(classified)} / 스킵 {len(df) - len(classified)}")
    print(df.groupby(["rate", "dur"]).size().to_string())
    print(f"통화가드 차단: {int(df['ccy_block'].sum())}종")
    print("\n--- 분류 샘플(rate별 2종) ---")
    for rate in classified["rate"].unique():
        for nm in classified[classified["rate"] == rate]["name"].head(2):
            print(f"  [{rate}] {nm}")
    print("\n--- 스킵 샘플 10종(모델불가 유형 확인) ---")
    for nm in df[df["rate"] == "SKIP"]["name"].head(10):
        print(f"  [SKIP] {nm}")


if __name__ == "__main__":
    ok = run_units()
    run_coverage()
    sys.exit(0 if ok else 1)
