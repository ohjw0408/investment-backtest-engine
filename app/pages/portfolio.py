import streamlit as st
from modules.portfolio_engine import PortfolioEngine

engine = PortfolioEngine()

def normalize(weights):
    total = sum(weights.values())
    return {k: v/total for k, v in weights.items()}


def render():

    st.title("📊 포트폴리오")

    portfolio = st.session_state.portfolio
    weights   = st.session_state.weights

    if not portfolio:
        st.info("포트폴리오가 비어있습니다.")
        return

    st.subheader("구성")

    # 슬라이더
    for ticker in portfolio:
        weights[ticker] = st.slider(
            ticker,
            0.0, 1.0,
            weights.get(ticker, 0.1)
        )

    weights = normalize(weights)

    st.write("정규화된 비중:", weights)

    # 실행
    if st.button("🚀 시뮬레이션"):

        result = engine.run_simulation(
            tickers=list(weights.keys()),
            start_date="2010-01-01",
            end_date="2020-01-01",
            initial_capital=100000000,
            strategy=None  # 나중에 연결
        )

        st.line_chart(result["history"]["portfolio_value"])
