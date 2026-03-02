import pandas as pd
import numpy as np
from typing import List, Dict, Any
from modules.price_loader import PriceLoader


class PortfolioEngine:

    def __init__(self):
        self.loader = PriceLoader()

    def run(
        self,
        tickers: List[str],
        weights: List[float],
        start_date: str,
        end_date: str,
        initial_capital: float = 1_000_000,
        risk_free_rate: float = 0.0,
    ) -> Dict[str, Any]:

        if len(tickers) != len(weights):
            raise ValueError("tickers와 weights 길이가 다릅니다.")

        weights = np.array(weights)

        if not np.isclose(weights.sum(), 1.0):
            raise ValueError("weights 합이 1이 되어야 합니다.")

        returns_list = []

        for t in tickers:
            df = self.loader.get_price(t, start_date, end_date)
            if df.empty:
                raise ValueError(f"{t} 가격 데이터 없음")

            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")

            df["daily_return"] = df["close"].pct_change().fillna(0.0)

            returns_list.append(
                df[["date", "daily_return"]].rename(
                    columns={"daily_return": t}
                )
            )

        merged = returns_list[0]

        for r in returns_list[1:]:
            merged = pd.merge(merged, r, on="date", how="inner")

        merged = merged.dropna().reset_index(drop=True)

        # 포트폴리오 수익률
        merged["portfolio_return"] = merged[tickers] @ weights

        # 개별 기여도
        for i, t in enumerate(tickers):
            merged[f"{t}_contribution"] = merged[t] * weights[i]
            merged[f"{t}_cum_contribution"] = (
                1 + merged[f"{t}_contribution"]
            ).cumprod()

        # 누적 수익률
        merged["cum_return"] = (
            1 + merged["portfolio_return"]
        ).cumprod()

        merged["portfolio_value"] = (
            initial_capital * merged["cum_return"]
        )

        # 성과 지표
        total_return = merged["cum_return"].iloc[-1] - 1

        days = (merged["date"].iloc[-1] - merged["date"].iloc[0]).days
        years = days / 365.25
        cagr = merged["cum_return"].iloc[-1] ** (1 / years) - 1

        merged["cum_max"] = merged["cum_return"].cummax()
        merged["drawdown"] = (
            merged["cum_return"] / merged["cum_max"] - 1
        )

        mdd = merged["drawdown"].min()

        volatility = (
            merged["portfolio_return"].std() * np.sqrt(252)
        )

        excess_return = cagr - risk_free_rate
        sharpe = (
            excess_return / volatility if volatility != 0 else np.nan
        )

        # -------------------------
        # 🔥 MDD 구간 분석
        # -------------------------

        # 최저점 인덱스
        mdd_idx = merged["drawdown"].idxmin()
        mdd_date = merged.loc[mdd_idx, "date"]

        # 시작점 (이전 최고점)
        peak_idx = merged.loc[:mdd_idx, "cum_return"].idxmax()
        peak_date = merged.loc[peak_idx, "date"]

        # 회복 시점
        recovery_idx = None
        for i in range(mdd_idx + 1, len(merged)):
            if merged.loc[i, "cum_return"] >= merged.loc[peak_idx, "cum_return"]:
                recovery_idx = i
                break

        recovery_date = (
            merged.loc[recovery_idx, "date"]
            if recovery_idx is not None
            else None
        )

        recovery_days = (
            (recovery_date - peak_date).days
            if recovery_date is not None
            else None
        )

        # MDD 구간 자산 기여도
        mdd_period = merged.loc[peak_idx:mdd_idx]

        mdd_contributions = {}
        for t in tickers:
            mdd_contributions[t] = float(
                (1 + mdd_period[f"{t}_contribution"]).prod() - 1
            )

        # 최종 자산 기여도
        asset_contributions = {
            t: float(
                merged[f"{t}_cum_contribution"].iloc[-1] - 1
            )
            for t in tickers
        }

        return {
            "tickers": tickers,
            "weights": weights.tolist(),
            "start_date": start_date,
            "end_date": end_date,
            "final_value": float(merged["portfolio_value"].iloc[-1]),
            "total_return": float(total_return),
            "cagr": float(cagr),
            "mdd": float(mdd),
            "volatility": float(volatility),
            "sharpe": float(sharpe),
            "asset_contributions": asset_contributions,
            "mdd_start": peak_date,
            "mdd_bottom": mdd_date,
            "recovery_date": recovery_date,
            "recovery_days": recovery_days,
            "mdd_contributions": mdd_contributions,
            "history": merged,
        }


if __name__ == "__main__":

    engine = PortfolioEngine()

    result = engine.run(
        tickers=["QQQ", "SPY", "TLT"],
        weights=[0.5, 0.3, 0.2],
        start_date="2015-01-01",
        end_date="2020-12-31",
    )

    print("총 수익률:", round(result["total_return"] * 100, 2), "%")
    print("CAGR:", round(result["cagr"] * 100, 2), "%")
    print("MDD:", round(result["mdd"] * 100, 2), "%")

    print("\nMDD 시작:", result["mdd_start"])
    print("MDD 최저점:", result["mdd_bottom"])
    print("회복일:", result["recovery_date"])
    print("회복까지 일수:", result["recovery_days"])

    print("\nMDD 구간 자산 기여도:")
    for k, v in result["mdd_contributions"].items():
        print(k, ":", round(v * 100, 2), "%")
