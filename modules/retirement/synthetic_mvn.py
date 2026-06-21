"""
synthetic_mvn.py
────────────────────────────────────────────────────────────────────────────────
조건부 다변량 합성 가격 생성 (BUG-SYNTH-CORR).

상장 짧은 ETF의 상장 전 구간을 종목별 독립 GBM으로 생성하면 종목 간 상관 ≈ 0이라
분산효과·리밸런싱 분석이 깨진다. 이 모듈은 실데이터(실+백필) 겹침구간에서 추정한
상관행렬에 부합하도록, 합성종목을 "같은 날 실데이터가 있는 종목의 실제 등락"에
조건부 다변량 샘플링한다 → synth-real 상관(예 SCHD-SPY 0.89)까지 재현.

오너 결정(2026-06-06):
  9.1=(a) μ_S 캡 backstop  9.2=(b) 쌍별 추정+nearest-PSD  9.3=(a) 다변량-t  9.4=(a) DB 후순위

수익률은 get_price(allow_synthetic=False) 일일 단순수익(KRW/FX 단위)로 추정·생성한다 —
합성 prefix(FX anchor 연결)·실 suffix(get_price KRW)와 동일 단위라 경계 연속성 유지.
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from modules.retirement.synthetic_price_generator import (
    SYNTHETIC_DF, T_SCALE, TRADING_DAYS_PER_MONTH, MAX_SYNTH_MU_MONTHLY,
)
from modules.seed_util import stable_seed

MIN_OBS_DAYS      = 252      # 종목별 최소 일수익 표본
MIN_OVERLAP_DAYS  = 252      # 쌍별 상관 추정 최소 겹침
_RIDGE            = 1e-10    # Cholesky 안정화
MU_DAILY_CAP      = MAX_SYNTH_MU_MONTHLY / TRADING_DAYS_PER_MONTH   # μ_S 일일 상한


def _load_real_returns(code: str, raw_loader) -> pd.Series | None:
    """종목 실데이터 전체 범위 일일 단순수익(KRW). 가상 제외."""
    try:
        row = raw_loader.conn.execute(
            "SELECT MIN(date), MAX(date) FROM price_daily WHERE code=?", (code,)
        ).fetchone()
    except Exception:
        return None
    if not row or not row[0] or not row[1]:
        return None
    start, end = str(row[0])[:10], str(row[1])[:10]
    df = raw_loader.get_price(code, start, end, allow_synthetic=False)
    if df is None or df.empty or "close" not in df.columns:
        return None
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    s = df.set_index("date")["close"].astype(float).sort_index()
    s = s[s > 0]
    ret = s.pct_change().dropna()
    # 극단값 제거(일일 ±25% 초과 = 분할/오류 추정)
    ret = ret[ret.abs() < 0.25]
    return ret if len(ret) >= MIN_OBS_DAYS else None


def _nearest_psd_corr(corr: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """고유값 클리핑으로 최근접 PSD 상관행렬(단위 대각 복원)."""
    corr = (corr + corr.T) / 2.0
    vals, vecs = np.linalg.eigh(corr)
    vals = np.clip(vals, eps, None)
    psd = vecs @ np.diag(vals) @ vecs.T
    d = np.sqrt(np.clip(np.diag(psd), eps, None))
    psd = psd / np.outer(d, d)
    np.fill_diagonal(psd, 1.0)
    return (psd + psd.T) / 2.0


def estimate_joint_stats(tickers, raw_loader) -> dict:
    """쌍별 일일수익 상관 추정 + nearest-PSD (9.2=b).

    반환: {ok, order, mu(daily raw), sigma(daily), corr, cov(daily),
           actual_start{code}, warnings}. ok=False면 호출부가 독립 폴백.
    """
    order = list(dict.fromkeys(tickers))   # 중복 제거·순서 유지
    warnings: list[str] = []

    rets: dict = {}
    for code in order:
        r = _load_real_returns(code, raw_loader)
        if r is None:
            warnings.append(f"{code}: 일일수익 표본 부족(<{MIN_OBS_DAYS}) → joint 불가")
            return {"ok": False, "warnings": warnings}
        rets[code] = r

    k = len(order)
    mu    = np.array([rets[c].mean() for c in order], dtype=float)
    sigma = np.array([rets[c].std(ddof=1) for c in order], dtype=float)
    if not np.all(np.isfinite(mu)) or not np.all(sigma > 0):
        return {"ok": False, "warnings": warnings + ["mu/sigma 비유한 or sigma<=0"]}

    # 쌍별 상관(최대 겹침구간)
    corr = np.eye(k)
    for i in range(k):
        for j in range(i + 1, k):
            a, b = rets[order[i]].align(rets[order[j]], join="inner")
            if len(a) < MIN_OVERLAP_DAYS:
                warnings.append(
                    f"{order[i]}-{order[j]}: 겹침 {len(a)}일(<{MIN_OVERLAP_DAYS}) → 상관 0 가정"
                )
                rho = 0.0
            else:
                sa, sb = a.std(ddof=1), b.std(ddof=1)
                rho = float(((a - a.mean()) * (b - b.mean())).mean() / (sa * sb)) if sa > 0 and sb > 0 else 0.0
                rho = max(-0.999, min(0.999, rho))
            corr[i, j] = corr[j, i] = rho

    corr = _nearest_psd_corr(corr)
    cov  = np.outer(sigma, sigma) * corr

    actual_start = {c: rets[c].index[0].strftime("%Y-%m-%d") for c in order}
    return {
        "ok": True, "order": order, "mu": mu, "sigma": sigma,
        "corr": corr, "cov": cov, "actual_start": actual_start, "warnings": warnings,
    }


def _fx_anchor(code: str, actual_start: str, raw_loader) -> float | None:
    """actual_start의 FX 실가격(실 suffix와 단위 일치). build_window_synth_params와 동일."""
    a_end = (pd.Timestamp(actual_start) + pd.Timedelta(days=14)).strftime("%Y-%m-%d")
    df = raw_loader.get_price(code, actual_start, a_end, allow_synthetic=False)
    if df is None or df.empty or "close" not in df.columns:
        return None
    v = float(df["close"].iloc[0])
    return v if v > 0 else None


def _real_df(code: str, start: str, end: str, raw_loader) -> pd.DataFrame:
    df = raw_loader.get_price(code, start, end, allow_synthetic=False)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    for col in ["open", "high", "low", "close", "volume", "dividend", "split"]:
        if col not in df.columns:
            df[col] = 0.0 if col != "split" else 1.0
    return df


def generate_joint_window(tickers, joint_stats, window_start, window_end, raw_loader):
    """윈도우 1개의 조건부 다변량 합성 prefix + 실 suffix.

    반환: (combined{code: df}, dates) — 기존 _load_*_synthetic 과 동일 포맷.
    joint_stats.ok=False거나 생성 불가 시 ValueError → 호출부가 독립 폴백.
    """
    if not joint_stats or not joint_stats.get("ok"):
        raise ValueError("joint_stats unavailable")

    order        = joint_stats["order"]
    mu_raw       = joint_stats["mu"]                         # 일일, 실수익 centering용
    mu_cap       = np.minimum(mu_raw, MU_DAILY_CAP)          # 9.1=a: 합성 drift 상한
    cov          = joint_stats["cov"]
    actual_start = joint_stats["actual_start"]
    pos          = {c: i for i, c in enumerate(order)}

    ws = pd.Timestamp(window_start)
    we = pd.Timestamp(window_end)
    ws_str, we_str = ws.strftime("%Y-%m-%d"), we.strftime("%Y-%m-%d")

    use_codes = [c for c in tickers if c in pos]
    if not use_codes:
        raise ValueError("no joint-covered tickers in window")

    as_dt = {c: pd.Timestamp(actual_start[c]) for c in use_codes}
    anchor = {}
    for c in use_codes:
        a = _fx_anchor(c, actual_start[c], raw_loader)
        if a is None:
            raise ValueError(f"{c}: anchor 없음")
        anchor[c] = a

    synth_codes = [c for c in use_codes if ws < as_dt[c]]
    real_codes  = [c for c in use_codes if ws >= as_dt[c]]

    combined: dict = {}
    all_dates: set = set()

    # 합성 prefix 불필요(전부 실범위) 종목
    for c in real_codes:
        df = _real_df(c, ws_str, we_str, raw_loader)
        combined[c] = df
        all_dates.update(df.index)

    if synth_codes:
        # ── 마스터 일일수익 정렬(실종목 조건용) ───────────────
        master = pd.bdate_range(start=ws, end=we)
        # pct_change용 prior 가격 확보 위해 10영업일 앞부터 로드
        load_from = (ws - pd.Timedelta(days=20)).strftime("%Y-%m-%d")
        real_ret_aligned: dict = {}
        for c in use_codes:
            df = raw_loader.get_price(c, load_from, we_str, allow_synthetic=False)
            if df is None or df.empty:
                real_ret_aligned[c] = pd.Series(0.0, index=master)
                continue
            df = df.copy(); df["date"] = pd.to_datetime(df["date"])
            s = df.set_index("date")["close"].astype(float).sort_index()
            rr = s.pct_change()
            real_ret_aligned[c] = rr.reindex(master).fillna(0.0)

        # ── 세그먼트 분할(actual_start 경계) ─────────────────
        max_as       = max(as_dt[c] for c in synth_codes)
        synth_end    = min(max_as - pd.Timedelta(days=1), we)
        boundaries   = sorted({as_dt[c] for c in synth_codes if ws < as_dt[c] <= we})
        seg_edges    = [ws] + [b for b in boundaries] + [synth_end + pd.Timedelta(days=1)]
        seg_edges    = sorted(set(seg_edges))

        seed = stable_seed(",".join(use_codes) + "|" + ws_str)
        rng  = np.random.default_rng(seed=seed)

        # 합성종목별 일일수익 저장(index=영업일)
        ret_store: dict = {c: {} for c in synth_codes}

        for si in range(len(seg_edges) - 1):
            s_start = seg_edges[si]
            s_end   = seg_edges[si + 1] - pd.Timedelta(days=1)
            if s_end < s_start or s_start > synth_end:
                continue
            s_end = min(s_end, synth_end)
            seg_days = pd.bdate_range(start=s_start, end=s_end)
            if len(seg_days) == 0:
                continue

            R = [c for c in use_codes  if as_dt[c] <= s_start]      # 실범위
            S = [c for c in synth_codes if as_dt[c] > s_end]        # 합성필요
            if not S:
                continue

            iS = [pos[c] for c in S]
            n  = len(seg_days)
            Sig_SS = cov[np.ix_(iS, iS)]

            if R:
                iR = [pos[c] for c in R]
                Sig_RR = cov[np.ix_(iR, iR)]
                Sig_SR = cov[np.ix_(iS, iR)]
                try:
                    inv_RR = np.linalg.inv(Sig_RR + np.eye(len(iR)) * _RIDGE)
                except np.linalg.LinAlgError:
                    inv_RR = np.linalg.pinv(Sig_RR)
                B       = Sig_SR @ inv_RR                            # |S|×|R|
                Sig_cnd = Sig_SS - B @ Sig_SR.T
                # 실종목 당일수익 행렬 A: n×|R|
                A = np.column_stack([real_ret_aligned[c].reindex(seg_days).fillna(0.0).values for c in R])
                cond_mean = (A - mu_raw[iR]) @ B.T                   # n×|S|
            else:
                Sig_cnd   = Sig_SS
                cond_mean = np.zeros((n, len(iS)))

            Sig_cnd = (Sig_cnd + Sig_cnd.T) / 2.0
            try:
                L = np.linalg.cholesky(Sig_cnd + np.eye(len(iS)) * _RIDGE)
            except np.linalg.LinAlgError:
                Sig_cnd = _psd_floor(Sig_cnd)
                L = np.linalg.cholesky(Sig_cnd + np.eye(len(iS)) * _RIDGE)

            z     = rng.standard_t(df=SYNTHETIC_DF, size=(n, len(iS))) / T_SCALE
            noise = z @ L.T                                          # n×|S|
            r_S   = mu_cap[iS] + cond_mean + noise                  # n×|S|

            for col, c in enumerate(S):
                for di, d in enumerate(seg_days):
                    ret_store[c][d] = float(r_S[di, col])

        # ── 합성종목 가격 역재구성 + 실 suffix stitch ────────
        for c in synth_codes:
            days = sorted(ret_store[c].keys())
            synth_df = None
            if days:
                r = np.array([ret_store[c][d] for d in days])
                nprices = len(r)
                prices = np.empty(nprices)
                # 역재구성: pct_change[d_i] == r_i 가 되도록 전이에 r[i+1]을 쓴다.
                # (r[i]를 쓰면 r_i가 d_i→d_{i+1} 전이가 되어 pct_change가 1일 밀려
                #  실종목 당일수익 조건부 상관이 소멸한다 — BUG-SYNTH-CORR 핵심.)
                prices[-1] = anchor[c] / (1.0 + r[-1])
                for i in range(nprices - 2, -1, -1):
                    prices[i] = prices[i + 1] / (1.0 + r[i + 1])
                    if prices[i] <= 0:
                        prices[i] = prices[i + 1] * 0.99
                synth_df = pd.DataFrame(
                    {"open": prices, "high": prices, "low": prices, "close": prices,
                     "volume": np.zeros(nprices), "dividend": np.zeros(nprices),
                     "split": np.ones(nprices)},
                    index=pd.DatetimeIndex(days),
                )
                synth_df.index.name = "date"

            if we >= as_dt[c]:
                real_df = _real_df(c, actual_start[c], we_str, raw_loader)
                if synth_df is not None and not synth_df.empty:
                    df = pd.concat([synth_df, real_df], axis=0)
                    df = df[~df.index.duplicated(keep="last")].sort_index()
                else:
                    df = real_df
            else:
                df = synth_df if synth_df is not None else pd.DataFrame()

            if df is not None and not df.empty:
                combined[c] = df
                all_dates.update(df.index)

    if not combined:
        raise ValueError("empty combined")

    # ── 공통 인덱스 reindex + ffill ──────────────────────────
    dates      = sorted(all_dates)
    full_index = pd.DatetimeIndex(dates)
    for c in list(combined.keys()):
        df = combined[c].reindex(full_index)
        df[["open", "high", "low", "close", "volume"]] = (
            df[["open", "high", "low", "close", "volume"]].ffill()
        )
        if "dividend" in df.columns:
            df["dividend"] = df["dividend"].fillna(0)
        if "split" in df.columns:
            df["split"] = df["split"].fillna(1)
        combined[c] = df

    return combined, dates


def _psd_floor(M: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    vals, vecs = np.linalg.eigh((M + M.T) / 2.0)
    vals = np.clip(vals, eps, None)
    return vecs @ np.diag(vals) @ vecs.T
