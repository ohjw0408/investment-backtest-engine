import pandas as pd
import numpy as np
from typing import Dict, Any


class PortfolioAnalyzer:
    """
    포트폴리오 성과 분석 모듈

    입력:
        PortfolioEngine history DataFrame

    출력:
        CAGR
        Total Return
        MDD
        Volatility
        Sharpe Ratio
        Drawdown period
        Recovery days
    """

    def analyze(
        self,
        history: pd.DataFrame,
        risk_free_rate: float = 0.0
    ) -> Dict[str, Any]:

        if history.empty:
            raise ValueError("history 데이터가 없습니다.")

        df = history.copy()

        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        # -----------------------------
        # Daily return
        # -----------------------------
        df["daily_return"] = df["portfolio_value"].pct_change().fillna(0.0)

        # -----------------------------
        # Cumulative return
        # -----------------------------
        df["cum_return"] = (1 + df["daily_return"]).cumprod()

        # -----------------------------
        # Total Return
        # -----------------------------
        total_return = df["cum_return"].iloc[-1] - 1

        # -----------------------------
        # CAGR
        # -----------------------------
        days = (df["date"].iloc[-1] - df["date"].iloc[0]).days
        years = days / 365.25

        cagr = df["cum_return"].iloc[-1] ** (1 / years) - 1

        # -----------------------------
        # MDD
        # -----------------------------
        df["cum_max"] = df["cum_return"].cummax()

        df["drawdown"] = df["cum_return"] / df["cum_max"] - 1

        mdd = df["drawdown"].min()

        # -----------------------------
        # Volatility
        # -----------------------------
        volatility = df["daily_return"].std() * np.sqrt(252)

        # -----------------------------
        # Sharpe Ratio
        # -----------------------------
        excess_return = cagr - risk_free_rate

        sharpe = (
            excess_return / volatility
            if volatility != 0
            else np.nan
        )

        # -----------------------------
        # MDD 기간 분석
        # -----------------------------
        mdd_idx = df["drawdown"].idxmin()

        mdd_date = df.loc[mdd_idx, "date"]

        peak_idx = df.loc[:mdd_idx, "cum_return"].idxmax()

        peak_date = df.loc[peak_idx, "date"]

        recovery_idx = None

        for i in range(mdd_idx + 1, len(df)):

            if df.loc[i, "cum_return"] >= df.loc[peak_idx, "cum_return"]:

                recovery_idx = i
                break

        recovery_date = (
            df.loc[recovery_idx, "date"]
            if recovery_idx is not None
            else None
        )

        recovery_days = (
            (recovery_date - peak_date).days
            if recovery_date is not None
            else None
        )

        return {
            "total_return": float(total_return),
            "cagr": float(cagr),
            "mdd": float(mdd),
            "volatility": float(volatility),
            "sharpe": float(sharpe),
            "mdd_start": peak_date,
            "mdd_bottom": mdd_date,
            "recovery_date": recovery_date,
            "recovery_days": recovery_days,
            "history": df
        }
