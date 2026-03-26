import streamlit as st
from modules.info_engine import InfoEngine

info_engine = InfoEngine()

def render():

    st.title("🔍 종목 검색")

    query = st.text_input("검색")

    if query:
        df = info_engine.search_fuzzy(query)

        if not df.empty:

            options = [
                f"{row['name']} ({row['code']})"
                for _, row in df.iterrows()
            ]

            selected = st.selectbox("결과", options)

            if selected:
                code = selected.split("(")[-1].replace(")", "")

                if st.button("➕ 포트폴리오 추가"):

                    if code not in st.session_state.portfolio:
                        st.session_state.portfolio.append(code)

                        # 기본 weight
                        st.session_state.weights[code] = 1.0

                        st.success(f"{code} 추가됨")