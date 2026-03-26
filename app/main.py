# app/main.py

import streamlit as st


def render():

    st.title("🏠 QuantMaster")

    st.markdown("### 📊 내 투자 대시보드")

    # 포트폴리오 상태 가져오기
    portfolio = st.session_state.get("portfolio", [])
    weights   = st.session_state.get("weights", {})

    # -------------------------
    # 포트폴리오 요약
    # -------------------------
    st.subheader("🧺 내 포트폴리오")

    if not portfolio:
        st.info("아직 포트폴리오가 없습니다. 종목 검색에서 추가하세요.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.write("보유 종목 수")
        st.metric("종목 수", len(portfolio))

    with col2:
        total_weight = sum(weights.values()) if weights else 0
        st.write("총 비중")
        st.metric("합계", f"{total_weight:.2f}")

    st.divider()

    # -------------------------
    # 종목 리스트
    # -------------------------
    st.subheader("📋 구성 종목")

    for ticker in portfolio:
        w = weights.get(ticker, 0)
        st.write(f"{ticker} - {w:.2f}")

    st.divider()

    # -------------------------
    # 시장 참고 정보 (간단)
    # -------------------------
    st.subheader("🌎 시장 참고")

    st.write("S&P500, NASDAQ 등은 추후 연결")