import pandas as pd
import numpy as np
from typing import Dict, Any


class RetirementAnalyzer:
    """
    은퇴 인출 시뮬레이션

    기능
    - 월 단위 인출 시뮬레이션
    - 성공 확률 계산
    - terminal wealth 분포
    - best / median / worst 결과
    """

    def __init__(
        self,
        monthly_withdrawal: float,
        years: int = 30,
        inflation: float = 0.0,
    ):

        self.monthly_withdrawal = monthly_withdrawal
        self.years = years
        self.inflation = inflation

    # -------------------------------------------------
    # Daily → Monthly return 변환
    # -------------------------------------------------
    def _get_monthly_returns(self, history: pd.DataFrame):

        df = history.copy()

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

        monthly = df["portfolio_value"].resample("M").last()

        monthly_returns = monthly.pct_change().dropna()

        return monthly_returns.values

    # -------------------------------------------------
    # 메인 분석
    # -------------------------------------------------
    def analyze(
        self,
        history: pd.DataFrame,
        initial_capital: float,
    ) -> Dict[str, Any]:

        monthly_returns = self._get_monthly_returns(history)

        months = self.years * 12

        terminal_values = []
        success_count = 0

        paths = []

        for start in range(len(monthly_returns) - months):

            capital = initial_capital

            withdrawal = self.monthly_withdrawal

            path = []

            for m in range(months):

                r = monthly_returns[start + m]

                capital *= (1 + r)

                capital -= withdrawal

                path.append(capital)

                if capital <= 0:
                    break

                # inflation adjustment
                withdrawal *= (1 + self.inflation / 12)

            terminal_values.append(capital)

            paths.append(path)

            if capital > 0:
                success_count += 1

        terminal_values = np.array(terminal_values)

        success_rate = success_count / len(terminal_values)

        best = terminal_values.max()
        worst = terminal_values.min()
        median = np.median(terminal_values)

        return {
            "success_rate": success_rate,
            "best_terminal": best,
            "median_terminal": median,
            "worst_terminal": worst,
            "terminal_values": terminal_values,
            "paths": paths,
        }
