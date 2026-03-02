import pandas as pd
import numpy as np
from typing import Dict, Any
from modules.price_loader import PriceLoader


class BacktestEngine:
    """
    단일 종목 백테스트 엔진
    포함 지표:
    - Total Return
    - CAGR
    - MDD
    - Volatility (연환산)
    - Sharpe Ratio
    """

    def __init__(self):
        self.loader = PriceLoader()

    def run(
        self,
        code: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 1_000_000,
        risk_free_rate: float = 0.0,  # 무위험수익률 (연)
    ) -> Dict[str, Any]:

        # 1️⃣ 가격 데이터 로드
        df = self.loader.get_price(code, start_date, end_date)
        if df.empty:
            raise ValueError("가격 데이터가 없습니다.")

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        # 2️⃣ 일간 수익률
        df["daily_return"] = df["close"].pct_change().fillna(0.0)

        # 3️⃣ 누적 수익률
        df["cum_return"] = (1.0 + df["daily_return"]).cumprod()

        # 4️⃣ 포트폴리오 가치
        df["portfolio_value"] = initial_capital * df["cum_return"]

        # 5️⃣ 총 수익률
        total_return: float = df["cum_return"].iloc[-1] - 1.0

        # 6️⃣ CAGR
        days: int = (df["date"].iloc[-1] - df["date"].iloc[0]).days
        years: float = days / 365.25
        cagr: float = (df["cum_return"].iloc[-1]) ** (1.0 / years) - 1.0

        # 7️⃣ MDD
        df["cum_max"] = df["cum_return"].cummax()
        df["drawdown"] = df["cum_return"] / df["cum_max"] - 1.0
        mdd: float = df["drawdown"].min()

        # -----------------------------
        # 🔥 8️⃣ 변동성 (Volatility)
        # -----------------------------
        daily_vol: float = df["daily_return"].std()
        volatility: float = daily_vol * np.sqrt(252)

        # -----------------------------
        # 🔥 9️⃣ Sharpe Ratio
        # -----------------------------
        excess_return = cagr - risk_free_rate
        sharpe: float = excess_return / volatility if volatility != 0 else np.nan

        result: Dict[str, Any] = {
            "code": code,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "final_value": float(df["portfolio_value"].iloc[-1]),
            "total_return": float(total_return),
            "cagr": float(cagr),
            "mdd": float(mdd),
            "volatility": float(volatility),
            "sharpe": float(sharpe),
            "history": df,
        }

        return result


# -------------------------------------------------
# 단독 실행 테스트
# -------------------------------------------------
if __name__ == "__main__":
    engine = BacktestEngine()

    result = engine.run(
        code="QQQ",
        start_date="2015-01-01",
        end_date="2020-12-31",
        initial_capital=1_000_000,
        risk_free_rate=0.0,
    )

    print("종목:", result["code"])
    print("총 수익률:", round(result["total_return"] * 100, 2), "%")
    print("CAGR:", round(result["cagr"] * 100, 2), "%")
    print("MDD:", round(result["mdd"] * 100, 2), "%")
    print("변동성:", round(result["volatility"] * 100, 2), "%")
    print("Sharpe Ratio:", round(result["sharpe"], 2))
