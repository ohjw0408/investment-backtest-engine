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
# 엔진 캐시 (중요)
# -------------------------------------------------
@st.cache_resource
def get_engines():
    info_engine = InfoEngine()
    data_engine = DataEngine()
    return info_engine, data_engine


info_engine, data_engine = get_engines()


# -------------------------------------------------
# 최초 1회 DB 구축 버튼
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
    suggestions = info_engine.search_fuzzy(search_input)

    if suggestions:

        selected = st.selectbox("검색 결과 선택", suggestions)

        if selected:
            code = selected.split("(")[-1].replace(")", "")

            info = info_engine.get_symbol_info(code)

            if not info.empty:
                row = info.iloc[0]

                st.success(f"✅ {row['Name']} 선택됨")

                col1, col2, col3 = st.columns(3)
                col1.metric("시장", row["Market"])
                col2.metric("상장일", row["ListingDate"])
                col3.metric("ETF 여부", "Yes" if row["IsETF"] else "No")

                # -----------------------------------------
                # 가격 차트 (On-Demand 로딩)
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
# 현재 DB 상태 확인
# -------------------------------------------------
st.subheader("📊 현재 저장된 종목 수")

try:
    df_all = pd.read_sql("SELECT * FROM symbols", info_engine.conn)
    st.write(f"총 {len(df_all)}개 종목 저장됨")
    st.dataframe(df_all.head(20), use_container_width=True)
except:
    st.info("아직 DB가 생성되지 않았습니다.")