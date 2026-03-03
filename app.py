import streamlit as st
import pandas as pd

from modules.info_engine import InfoEngine
from modules.data_engine import DataEngine
from modules.db_builder import SymbolDBBuilder


# -------------------------------------------------
# 기본 설정
# -------------------------------------------------
st.set_page_config(page_title="QuantMaster", layout="wide")
st.title("🌐 QuantMaster - Institutional Search Engine")


# -------------------------------------------------
# 엔진 캐시
# -------------------------------------------------
@st.cache_resource
def get_engines():
    return InfoEngine(), DataEngine()


info_engine, data_engine = get_engines()


# -------------------------------------------------
# 최초 1회 DB 구축
# -------------------------------------------------
st.subheader("📦 Symbol Master DB")

if st.button("🔧 최초 1회: 종목 DB 구축"):
    with st.spinner("종목 DB 구축 중... (1~3분 소요 가능)"):
        builder = SymbolDBBuilder()
        builder.build_all()
    st.success("✅ DB 구축 완료")

st.divider()


# -------------------------------------------------
# 종목 검색 영역
# -------------------------------------------------
st.subheader("🔍 종목 검색")

search_input = st.text_input("종목명 또는 코드 입력").strip()

if search_input:
    df = info_engine.search_fuzzy(search_input)

    if not df.empty:

        # selectbox용 표시 문자열 생성
        options = [
            f"{row['name']} ({row['code']})"
            for _, row in df.iterrows()
        ]

        selected_option = st.selectbox("검색 결과 선택", options)

        if selected_option:

            # 코드 추출
            code = selected_option.split("(")[-1].replace(")", "")

            # 상세 정보 조회
            info_df = info_engine.get_symbol_by_ticker(code)

            if not info_df.empty:
                row = info_df.iloc[0]

                st.success(f"✅ {row['name']} 선택됨")

                col1, col2, col3 = st.columns(3)
                col1.metric("시장", row["market"])
                col2.metric("국가", row["country"])
                col3.metric("ETF 여부", "Yes" if row["is_etf"] == 1 else "No")

                # -----------------------------------------
                # 가격 차트
                # -----------------------------------------
                st.subheader("📈 가격 차트")

                with st.spinner("가격 데이터 로딩 중..."):
                    price = data_engine.get_symbol_data(code)

                if price is not None and not price.empty:
                    st.line_chart(price)
                else:
                    st.warning("가격 데이터를 불러올 수 없습니다.")

    else:
        st.info("검색 결과가 없습니다.")

st.divider()


# -------------------------------------------------
# 현재 DB 상태
# -------------------------------------------------
st.subheader("📊 현재 저장된 종목 수")

try:
    df_all = info_engine.get_all_symbols()
    st.write(f"총 {len(df_all)}개 종목 저장됨")
    st.dataframe(df_all.head(20), use_container_width=True)
except Exception:
    st.info("아직 DB가 생성되지 않았습니다.")