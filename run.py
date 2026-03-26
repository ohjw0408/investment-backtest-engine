import streamlit as st
from app.state import init_state

st.set_page_config(layout="wide")

init_state()

st.sidebar.title("📊 QuantMaster")

page = st.sidebar.radio(
    "메뉴",
    ["홈", "종목 검색", "포트폴리오"]
)

if page == "홈":
    from app.main import render
elif page == "종목 검색":
    from app.pages.search import render
elif page == "포트폴리오":
    from app.pages.portfolio import render

render()