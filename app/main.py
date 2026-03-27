import streamlit as st
import numpy as np
import pandas as pd

def render():

    st.set_page_config(layout="wide")

    # 🔥 전체 배경을 밝게 강제
    st.markdown("""
    <style>
    body {
        background-color: #f5f6fa;
    }

    .main {
        background-color: #f5f6fa;
    }

    /* 헤더 */
    .header {
        background: #2f5fb3;
        padding: 20px;
        border-radius: 15px;
        color: white;
        font-weight: bold;
    }

    /* 카드 */
    .card {
        background: white;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }

    .metric {
        font-size: 32px;
        font-weight: bold;
    }

    .green {
        color: #00c853;
    }

    /* 사이드 카드 */
    .menu-card {
        background: white;
        padding: 12px;
        border-radius: 10px;
        margin-bottom: 10px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
    }

    </style>
    """, unsafe_allow_html=True)

    # ---------------- HEADER ----------------
    st.markdown("""
    <div class="header">
        🎲 Domino Invest
    </div>
    """, unsafe_allow_html=True)

    st.write("")

    # ---------------- LAYOUT ----------------
    left, center, right = st.columns([1, 3, 1.2])

    # ---------------- LEFT ----------------
    with left:
        st.markdown("### 📂 메뉴")

        st.markdown('<div class="menu-card">📊 포트폴리오</div>', unsafe_allow_html=True)
        st.markdown('<div class="menu-card">🏦 은퇴 시뮬레이션</div>', unsafe_allow_html=True)
        st.markdown('<div class="menu-card">💰 목돈 모으기</div>', unsafe_allow_html=True)
        st.markdown('<div class="menu-card">⚖️ 자산 배분</div>', unsafe_allow_html=True)

    # ---------------- CENTER ----------------
    with center:

        st.markdown('<div class="card">', unsafe_allow_html=True)

        st.markdown("### 💼 내 포트폴리오")

        st.markdown(
            '<div class="metric">₩15,870,200 <span class="green">(+1.8%)</span></div>',
            unsafe_allow_html=True
        )

        # 차트
        data = np.cumsum(np.random.randn(200)) + 100
        st.line_chart(pd.DataFrame({"value": data}))

        st.markdown('</div>', unsafe_allow_html=True)

        st.write("")

        # 시장 지수 카드
        st.markdown('<div class="card">', unsafe_allow_html=True)

        st.markdown("### ⭐ 시장 지수")

        c1, c2, c3 = st.columns(3)

        c1.metric("S&P 500", "5,420", "+10.8%")
        c2.metric("NASDAQ", "17,500", "+17.5%")
        c3.metric("KOSPI", "2,750", "+12.5%")

        st.markdown('</div>', unsafe_allow_html=True)

    # ---------------- RIGHT ----------------
    with right:

        st.markdown('<div class="card">', unsafe_allow_html=True)

        st.markdown("### 📊 자산군 비교")

        st.metric("주식", "+7%")
        st.metric("채권", "+2.5%")
        st.metric("금", "+1.5%")
        st.metric("원자재", "-0.5%")

        st.markdown('</div>', unsafe_allow_html=True)