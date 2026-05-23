"""TaxSessionState — 시뮬레이션 1회당 세금 누적 상태."""
from dataclasses import dataclass


@dataclass
class TaxSessionState:
    ytd_us_realized_gains: float = 0.0  # US_DIRECT 당해연도 실현 차익 누계
    year: int = 0                        # 현재 추적 연도
