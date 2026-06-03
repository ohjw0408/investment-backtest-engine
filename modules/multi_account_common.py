"""
modules/multi_account_common.py
────────────────────────────────────────────────────────────────────────────────
Track G 멀티계좌 입력 정규화·검증·결과 헬퍼.

투자계산기 / 백테스트 / 은퇴 logic이 공유한다(중복·드리프트 방지, G5 복제).
전부 순수 함수 — body dict in, 정규화 dict/메시지 list out. 시뮬 엔진·DB 의존 없음.
"""


def normalize_multi_accounts(body: dict) -> list[dict]:
    """body의 accounts 배열을 시뮬용 표준 dict 리스트로 정규화.

    계좌별 종목·비중 검증(종목 1개 이상, 비중 합계 ≤ 100%) + 계좌 레벨 기본값
    (rebal_mode/band_width/dividend_mode는 계좌별 우선, 없으면 body 전역).
    """
    accounts = []
    for idx, raw in enumerate(body.get('accounts') or []):
        tickers = raw.get('tickers') or []
        if not tickers:
            raise ValueError(f"계좌 {idx + 1}에 종목을 최소 1개 이상 추가해주세요.")

        normalized_tickers = []
        total_weight = 0.0
        for ticker in tickers:
            weight = float(ticker.get('weight', 0))
            total_weight += weight
            normalized_tickers.append({
                'code':   ticker['code'],
                'name':   ticker.get('name', ticker['code']),
                'badge':  ticker.get('badge', ''),
                'weight': weight,
            })
        if total_weight > 1.000001:
            raise ValueError(f"계좌 {idx + 1}의 비중 합계가 100%를 초과했습니다.")

        accounts.append({
            'type':                 raw.get('type', '위탁'),
            'initial_capital':      float(raw.get('initial_capital', 0) or 0),
            'monthly_contribution': float(raw.get('monthly_contribution', 0) or 0),
            'tickers':              normalized_tickers,
            'rebal_mode':           raw.get('rebal_mode') or body.get('rebal_mode', 'monthly'),
            'band_width':           float(raw.get('band_width', body.get('band_width', 0.05))),
            'dividend_mode':        raw.get('dividend_mode') or body.get('dividend_mode', 'reinvest'),
            'isa_renewal':          bool(raw.get('isa_renewal', False)),
        })
    return accounts


def validate_initial_capital_limits(accounts: list[dict]) -> list[str]:
    """초기자본 연 납입한도 하드체크 (transfers 무관 — 초기자본은 실제 입금이라 한도 초과 불가).

    - ISA: 각 계좌 초기자본 ≤ 2,000만(연 한도).
    - 연금저축 + IRP: 합산 초기자본 ≤ 1,800만(공유 연 한도).
    위반 메시지 리스트 반환(빈 리스트 = 통과).
    """
    errors: list[str] = []
    for idx, a in enumerate(accounts):
        if a.get('type') == 'ISA' and float(a.get('initial_capital', 0) or 0) > 20_000_000:
            errors.append(
                f"계좌 {idx + 1}: ISA 초기 투자금은 연 납입한도 2,000만원을 초과할 수 없습니다."
            )
    pension_init = sum(
        float(a.get('initial_capital', 0) or 0)
        for a in accounts if a.get('type') in ('연금저축', 'IRP')
    )
    if pension_init > 18_000_000:
        errors.append(
            f"연금저축+IRP 초기 투자금 합계 {pension_init:,.0f}원이 "
            f"연 합산 납입한도 1,800만원을 초과합니다. (연금저축·IRP는 한도 공유)"
        )
    return errors


def build_loop_accounts(accounts: list[dict], start_str: str, end_str: str,
                        default_dividend_mode: str = "reinvest",
                        withdrawal_amount: float = 0) -> list[dict]:
    """정규화 계좌 dict → MultiAccountSimulationLoop이 먹는 config+strategy 포함 dict 리스트.

    롤링(analyzer 윈도우별)·단일윈도우(백테스트)·인출(은퇴, withdrawal_amount>0) 공유.
    start_str/end_str = 해당 윈도우 경계. analyzer._run_rolling의 인라인 빌드와 동일 스펙.
    """
    from modules.config.simulation_config import SimulationConfig
    from modules.rebalance.periodic import PeriodicRebalance

    loop_accounts = []
    for account in accounts:
        tickers = [t["code"] for t in account["tickers"]]
        weights = {t["code"]: float(t["weight"]) for t in account["tickers"]}
        rebal_mode = account.get("rebal_mode", "monthly")
        band_width = float(account.get("band_width", 0.05))
        rebalance_frequency = None if rebal_mode in ("none", "band") else rebal_mode
        drift_threshold = band_width if rebal_mode == "band" else None
        strategy = PeriodicRebalance(
            target_weights=weights,
            rebalance_frequency=rebalance_frequency,
            drift_threshold=drift_threshold,
        )
        config = SimulationConfig(
            start_date=start_str,
            end_date=end_str,
            tickers=tickers,
            target_weights=weights,
            initial_capital=float(account.get("initial_capital", 0.0)),
            monthly_contribution=float(account.get("monthly_contribution", 0.0)),
            contribution_end_months=account.get("contribution_end_months"),
            withdrawal_amount=withdrawal_amount,
            dividend_mode=account.get("dividend_mode", default_dividend_mode),
            rebalance_frequency=rebalance_frequency,
            inflation=0.0,
        )
        loop_accounts.append({
            "type": account.get("type", "위탁"),
            "config": config,
            "strategy": strategy,
            "gain_harvesting": account.get("gain_harvesting", False),
            "isa_years_held": account.get("isa_years_held", 3),
            "isa_renewal": account.get("isa_renewal", False),
        })
    return loop_accounts


def build_savings_summary(savings_raw: dict) -> dict | None:
    """절세액 표시(위탁가정세금·실제세금·절세액 + GH 절세)를 프론트 소비형으로 라운딩.

    analyzer의 `savings`(계좌별 p50 + 합산) → 정수 라운딩. combined 없으면 None.
    """
    if not savings_raw.get('combined'):
        return None
    return {
        'combined': {k: round(v) for k, v in savings_raw['combined'].items()},
        'accounts': [
            {
                'account_id': a['account_id'],
                'type':       a['type'],
                'brokerage_assumed_tax': round(a['brokerage_assumed_tax']),
                'actual_tax':            round(a['actual_tax']),
                'tax_saving':            round(a['tax_saving']),
                'gain_harvest_saving':   round(a.get('gain_harvest_saving', 0)),
            }
            for a in savings_raw.get('accounts', [])
        ],
    }
