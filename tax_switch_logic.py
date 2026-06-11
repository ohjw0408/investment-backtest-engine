"""
tax_switch_logic.py — 세금 전환 계산기 (위탁 유지 vs ISA 분할 이전).

"지금 보유한 위탁 자산을 팔아서(양도세 내고) ISA로 옮길까, 그냥 위탁에서 굴릴까?"
- A) 위탁 유지: 현 평가액(취득가 주입 = 초기 미실현차익 재현)을 위탁에서 N년 운용.
- B) 분할 이전: 매년 ISA 한도(연 2천만/총 1억)만큼 위탁 매도(양도세) → ISA 납입 → N년 후 ISA 만기세.

오너 결정(2026-06-12): (a) 분할 이전 모델, 독립 페이지. 상세 = 세금계산기_plan.md.
엔진 = MultiAccountAnalyzer(switch_policy + yearly_after_tax_snapshot + carried_cost_basis).
v1 제약: 월 추가납입 없음(기보유 자산 전환 결정만), use_synthetic 미지원(A/B 윈도우 페어링 보장).
"""
import datetime
import json as _json

import numpy as np

from calculator_logic import (
    _get_portfolio_engine,
    _get_price_start,
    _get_dividend_start,
)


def _percentiles(values: list[float]) -> dict:
    if not values:
        return {"p25": 0.0, "p50": 0.0, "p75": 0.0}
    arr = np.asarray(values, dtype=float)
    return {
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
    }


def _breakeven_offset(a_by_year: dict, b_by_year: dict, start_year: int) -> int | None:
    """B 세후가치가 A를 따라잡는 첫 해(1-base 경과년). 없으면 None.

    1년차(전환 직후)는 전환세로 B<A가 정상 — 전 구간 비교해 첫 역전 지점을 찾는다.
    """
    common = sorted(set(a_by_year) & set(b_by_year))
    for y in common:
        if b_by_year[y] >= a_by_year[y]:
            return int(y) - start_year + 1
    return None


def run_tax_switch_logic(body: dict, progress_callback=None) -> dict:
    from modules.retirement.multi_account_analyzer import MultiAccountAnalyzer
    from modules.tax.base_tax import TaxEngine
    from modules.tax.account_tax import validate_account_portfolio

    # ── 입력 ─────────────────────────────────────────────────────────
    current_value = float(body["current_value"])     # 현재 위탁 평가액
    cost_basis    = float(body["cost_basis"])         # 취득가 합계 (지금 팔 때 차익 계산용)
    tickers_input = body["tickers"]                    # [{code, weight}]
    years         = int(body["years"])
    user_settings = body.get("user_settings", {}) or {}
    rebal_mode    = body.get("rebal_mode", "monthly")
    band_width    = float(body.get("band_width", 0.05))
    dividend_mode = body.get("dividend_mode", "reinvest")

    if current_value <= 0:
        raise ValueError("현재 평가액은 0보다 커야 합니다.")
    if cost_basis <= 0:
        raise ValueError("취득가는 0보다 커야 합니다.")
    if years < 1:
        raise ValueError("투자 기간은 1년 이상이어야 합니다.")

    ticker_codes   = [t["code"] for t in tickers_input]
    target_weights = {t["code"]: float(t["weight"]) for t in tickers_input}

    # B 전략의 ISA 계좌가 같은 종목을 보유 — ISA 편입 가능 종목인지 선검증.
    tax_engine = TaxEngine(user_settings)
    _check = validate_account_portfolio("ISA", ticker_codes, target_weights, tax_engine)
    if not _check["valid"]:
        raise ValueError(_json.dumps({
            "error": "account_restrictions",
            "violations": _check["violations"],
            "disclaimer": _check.get("disclaimer"),
        }, ensure_ascii=False))

    # ── 가격 데이터 준비 (calculator 멀티 경로와 동일) ────────────────
    portfolio_engine = _get_portfolio_engine()
    usdkrw_start = portfolio_engine.loader.USD_KRW_START
    today = datetime.date.today().strftime("%Y-%m-%d")
    for ticker in ticker_codes:
        try:
            portfolio_engine.loader.get_price(ticker, usdkrw_start, today)
        except Exception as e:
            print(f"[tax_switch] {ticker} 데이터 로드 오류: {e}")

    price_starts = [_get_price_start(portfolio_engine, t) for t in ticker_codes]
    price_starts = [d for d in price_starts if d]
    data_start = max([usdkrw_start] + price_starts) if price_starts else usdkrw_start
    data_end   = today

    start_dt  = datetime.datetime.strptime(data_start, "%Y-%m-%d").date()
    max_years = (datetime.date.today() - start_dt).days // 365
    if years > max_years:
        raise ValueError(
            f"데이터 부족: {ticker_codes}의 데이터는 {data_start}부터 있어서 "
            f"최대 {max_years}년 시뮬레이션이 가능합니다."
        )

    div_starts = [_get_dividend_start(portfolio_engine, t) for t in ticker_codes]
    div_starts = [d for d in div_starts if d]
    div_start  = max(div_starts) if div_starts else None

    # ── 전략 A: 위탁 유지 ────────────────────────────────────────────
    base_account = {
        "type": "위탁",
        "initial_capital": current_value,
        "monthly_contribution": 0.0,
        "tickers": tickers_input,
        "rebal_mode": rebal_mode,
        "band_width": band_width,
        "dividend_mode": dividend_mode,
        "carried_cost_basis": cost_basis,
    }

    def _progress(phase_offset):
        if progress_callback is None:
            return None

        def cb(current, total, elapsed):
            progress_callback(
                current=phase_offset + current, total=total * 2, elapsed=elapsed
            )
        return cb

    result_a = MultiAccountAnalyzer(
        portfolio_engine=portfolio_engine,
        accounts=[dict(base_account)],
        data_start=data_start,
        data_end=data_end,
        accumulation_years=years,
        dividend_mode=dividend_mode,
        tax_enabled=True,
        user_settings=user_settings,
        progress_callback=_progress(0),
        div_start=div_start,
        yearly_after_tax_snapshot=True,
    ).run()

    # ── 전략 B: 분할 이전 (위탁 → ISA, 연 1회 한도만큼) ───────────────
    isa_account = {
        "type": "ISA",
        "initial_capital": 0.0,
        "monthly_contribution": 0.0,
        "tickers": tickers_input,
        "rebal_mode": rebal_mode,
        "band_width": band_width,
        "dividend_mode": dividend_mode,
        "isa_years_held": years,
    }
    result_b = MultiAccountAnalyzer(
        portfolio_engine=portfolio_engine,
        accounts=[dict(base_account), isa_account],
        data_start=data_start,
        data_end=data_end,
        accumulation_years=years,
        dividend_mode=dividend_mode,
        tax_enabled=True,
        user_settings=user_settings,
        progress_callback=_progress(0),
        div_start=div_start,
        switch_policy={"source_id": 0, "dest_id": 1},
        yearly_after_tax_snapshot=True,
    ).run()

    # ── 케이스 페어링 (동일 데이터·기간·step → 윈도우 start 일치) ─────
    cases_a = {c["start"]: c for c in result_a["cases"]}
    cases_b = {c["start"]: c for c in result_b["cases"]}
    common_starts = sorted(set(cases_a) & set(cases_b))
    if not common_starts:
        raise ValueError("비교 가능한 롤링 윈도우가 없습니다. 기간·종목을 확인해주세요.")

    a_ends, b_ends, diffs, switch_taxes = [], [], [], []
    breakevens = []
    traj_a: dict[int, list[float]] = {}
    traj_b: dict[int, list[float]] = {}
    for s in common_starts:
        ca, cb_ = cases_a[s], cases_b[s]
        a_end = float(ca["end_value"])
        b_end = float(cb_["end_value"])
        a_ends.append(a_end)
        b_ends.append(b_end)
        diffs.append(b_end - a_end)
        switch_taxes.append(float(cb_.get("switch_cg_tax_total", 0.0)))

        start_year = int(s[:4])
        a_by_year = {int(y): v for y, v in (ca.get("after_tax_by_year") or {}).items()}
        b_by_year = {int(y): v for y, v in (cb_.get("after_tax_by_year") or {}).items()}
        be = _breakeven_offset(a_by_year, b_by_year, start_year)
        if be is not None:
            breakevens.append(be)
        for y, v in a_by_year.items():
            traj_a.setdefault(y - start_year + 1, []).append(float(v))
        for y, v in b_by_year.items():
            traj_b.setdefault(y - start_year + 1, []).append(float(v))

    diff_pct = _percentiles(diffs)
    winner = "B" if diff_pct["p50"] > 0 else ("A" if diff_pct["p50"] < 0 else "tie")

    trajectory = []
    for offset in sorted(set(traj_a) | set(traj_b)):
        if offset > years:
            continue
        trajectory.append({
            "year": offset,
            "a_p50": float(np.median(traj_a[offset])) if traj_a.get(offset) else None,
            "b_p50": float(np.median(traj_b[offset])) if traj_b.get(offset) else None,
        })

    # 대표 케이스(B 종료값 중앙값에 가장 가까운 윈도우)의 이전 스케줄 — UI 표시용
    b_p50 = _percentiles(b_ends)["p50"]
    rep_start = min(common_starts, key=lambda s: abs(float(cases_b[s]["end_value"]) - b_p50))
    rep_schedule = list(cases_b[rep_start].get("switch_log") or [])

    return {
        "ok": True,
        "years": years,
        "cases_count": len(common_starts),
        "inputs": {
            "current_value": current_value,
            "cost_basis": cost_basis,
            "unrealized_gain": current_value - cost_basis,
            "tickers": tickers_input,
        },
        "a": _percentiles(a_ends),
        "b": {**_percentiles(b_ends), "switch_tax": _percentiles(switch_taxes)},
        "diff": diff_pct,
        "winner": winner,
        "breakeven": {
            "year_p50": float(np.median(breakevens)) if breakevens else None,
            "found_ratio": len(breakevens) / len(common_starts),
        },
        "trajectory": trajectory,
        "representative_schedule": {
            "window_start": rep_start,
            "transfers": rep_schedule,
        },
        "data_start": data_start,
        "notes": [
            "B 전략: 매년 ISA 한도(연 2,000만/총 1억)만큼 위탁을 매도(양도세 납부 후)해 ISA로 이전합니다.",
            "이전 입금액은 매도대금에서 양도세를 뺀 금액이라 연 한도를 약간 밑돌 수 있습니다.",
            "ISA 만기세는 손익통산 후 비과세 한도(일반 200만/서민형 400만) 초과분에 9.9%를 적용합니다.",
            "평가액이 1억(ISA 총한도)을 넘으면 초과분은 위탁에 남아 계속 운용됩니다.",
        ],
    }
