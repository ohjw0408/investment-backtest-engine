import streamlit as st

def init_state():

    if "portfolio" not in st.session_state:
        st.session_state.portfolio = []

    if "weights" not in st.session_state:
        st.session_state.weights = {}

    if "selected_asset" not in st.session_state:
        st.session_state.selected_asset = None
