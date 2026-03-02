import FinanceDataReader as fdr
import pandas as pd
import os

class DataEngine:
    def __init__(self, start_date="1950-01-01"):
        self.start_date = start_date
        self.base_path = "data"
        # 자산별 백필링용 벤치마크 (미래에 info_engine과 연동 예정)
        self.bench_map = {
            "SCHD": "DJI",   # 다우존스
            "QQQ": "IXIC",   # 나스닥
            "SPY": "S&P500", # S&P500
            "QQQM": "IXIC"
        }

    def get_symbol_data(self, ticker):
        """로컬 확인 후 없으면 다운로드하여 시세 반환"""
        file_path = os.path.join(self.base_path, f"{ticker.replace(':', '_')}.csv")
        
        if os.path.exists(file_path):
            return pd.read_csv(file_path, index_col=0, parse_dates=True)['Close']
        
        try:
            # FDR은 1970년 이전도 문자열 처리로 안전하게 가져옴
            df = fdr.DataReader(ticker, self.start_date)
            if not df.empty:
                df.to_csv(file_path)
                return df['Close']
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
        return pd.Series()

    def get_backfilled_data(self, ticker):
        """상장 전 데이터를 지수와 매끄럽게 연결 (adj_ratio 적용)"""
        asset = self.get_symbol_data(ticker)
        
        if ticker in self.bench_map:
            bench = self.get_symbol_data(self.bench_map[ticker])
            first_date = asset.first_valid_index()
            
            if first_date and not bench.empty:
                bench_before = bench[bench.index < first_date]
                if not bench_before.empty:
                    # [핵심] 수직 낙하 방지: 연결 지점의 비율 계산
                    ratio = asset.iloc[0] / bench_before.iloc[-1]
                    asset = pd.concat([bench_before * ratio, asset])
        
        return asset.sort_index()

    def get_unified_returns(self, tickers):
        """모든 자산을 원화 환산 수익률로 변환"""
        fx = self.get_symbol_data('USD/KRW').ffill()
        all_rets = []

        for t in tickers:
            price = self.get_backfilled_data(t)
            
            # 미국 자산이면 원화 환산
            if not (".KS" in t or ".KQ" in t):
                combined = pd.concat([price, fx], axis=1).ffill().dropna()
                price = combined.iloc[:, 0] * combined.iloc[:, 1]
            
            # 수익률 계산 (중복 제거 포함)
            price = price[~price.index.duplicated(keep='last')]
            ret = price.pct_change().fillna(0)
            ret.name = t
            all_rets.append(ret)

        return pd.concat(all_rets, axis=1).ffill().fillna(0)