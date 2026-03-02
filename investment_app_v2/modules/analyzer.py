import FinanceDataReader as fdr
import pandas as pd

class Analyzer:
    def __init__(self):
        pass

    def get_price_data(self, code, start_date='2025-01-01'):
        """종목 코드를 받아 실제 시세 데이터를 호출합니다."""
        try:
            # FDR을 통해 실시간/과거 시세 로드
            df = fdr.DataReader(code, start_date)
            if df.empty: return pd.DataFrame()
            return df[['Close']].reset_index()
        except:
            return pd.DataFrame()