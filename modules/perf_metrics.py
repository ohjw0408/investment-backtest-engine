"""납입·인출이 섞인 계좌 시계열에서 "수익률"을 뽑는 공통 함수 (2026-08-05).

계좌 잔고(portfolio_value)를 그대로 쓰면 적립식에서는 납입금 증가가 수익으로,
인출기에는 인출이 손실로 잡힌다. 수익률성 지표는 전부 여기 TWR 지수를 태운다.
"""
import numpy as np


def twr_index(pv, cash_flow=None):
    """시간가중(TWR) 지수 + 일간 TWR 수익률.

    자금 유입은 그날 종가로 집행되어 당일 수익에 기여하지 않으므로
        r_t = (PV_t - CF_t) / PV_(t-1) - 1
    반환: (지수 ndarray[첫날=1.0], 일간수익률 ndarray[len-1])
    """
    v = np.asarray(pv, dtype=float)
    if len(v) < 2:
        return np.ones(len(v)), np.zeros(0)
    c = np.zeros(len(v)) if cash_flow is None else np.asarray(cash_flow, dtype=float)
    prev  = v[:-1]
    ok    = prev > 0
    ratio = np.where(ok, (v[1:] - c[1:]) / np.where(ok, prev, 1.0), 1.0)
    ratio = np.clip(ratio, 0.0, None)   # 잔고 소진 등 비정상 구간 방어
    return np.concatenate(([1.0], np.cumprod(ratio))), ratio - 1.0


def max_drawdown(index_arr):
    """TWR 지수 기준 MDD(음수)."""
    idx = np.asarray(index_arr, dtype=float)
    if len(idx) == 0:
        return 0.0
    return float((idx / np.maximum.accumulate(idx) - 1.0).min())


def monthly_flows(dates, cash_flow):
    """일자별 순현금흐름 → 월별 버킷 배열(index 0 = 첫 달). IRR의 기간 단위를 '월'로 고정한다.

    `cash_flow != 0` 행을 그대로 enumerate하면 "행 하나 = 한 달"을 가정하게 되는데,
    배당 인출처럼 월중에도 흐름이 생기면 그 가정이 깨져 IRR이 엉킨다.
    """
    import pandas as pd
    d = pd.to_datetime(pd.Series(np.asarray(dates)).reset_index(drop=True))
    mpos = ((d.dt.year - d.dt.year.iloc[0]) * 12 + (d.dt.month - d.dt.month.iloc[0])).to_numpy()
    flows = np.zeros(int(mpos[-1]) + 1)
    np.add.at(flows, mpos, np.asarray(cash_flow, dtype=float))
    return flows


def mwr(flows, end_value):
    """금액가중 연수익률 — 월별 순납입(양수=납입) 시계열의 IRR을 연환산. 실패 시 None.

    flows[i]는 i번째 달 초 유입, end_value는 len(flows)번째 달 초(=마지막 달 말) 회수로 본다.
    """
    cfs = [-float(c) for c in flows] + [float(end_value)]
    if len(cfs) < 2 or not any(c < 0 for c in cfs) or not any(c > 0 for c in cfs):
        return None
    rate = 0.01
    for _ in range(200):
        npv  = sum(c / (1 + rate) ** i for i, c in enumerate(cfs))
        dnpv = sum(-i * c / (1 + rate) ** (i + 1) for i, c in enumerate(cfs))
        if abs(dnpv) < 1e-12:
            break
        nr = rate - npv / dnpv
        if abs(nr - rate) < 1e-8:
            rate = nr
            break
        rate = nr
    if not (-0.9 < rate < 10.0):
        return None
    annual = (1 + rate) ** 12 - 1
    return annual if np.isfinite(annual) else None
