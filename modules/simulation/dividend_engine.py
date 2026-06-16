class DividendEngine:

    def process(
        self,
        portfolio,
        price_data,
        price_dict,
        date,
        dividend_mode,
        dividend_today=None,
    ):

        dividend_by_ticker = {}

        for ticker, position in portfolio.positions.items():

            if dividend_today is not None:
                # 고속 경로: SimulationLoop이 numpy로 미리 뽑은 당일 배당(정수 인덱스 i).
                # 과거엔 매일·종목마다 `date not in index`(union reindex라 항상 True인 死코드) +
                # `price_data[ticker].loc[date,"dividend"]`(비싼 pandas 스칼라 룩업)을 수행 →
                # 배당 0인 날도 전부. numpy 값으로 대체(=.iloc[i]=.loc[date] 동일, 결과 불변).
                dividend = dividend_today.get(ticker)
                if dividend is None:
                    continue
            else:
                if ticker not in price_data:
                    continue
                if date not in price_data[ticker].index:
                    continue
                dividend = price_data[ticker].loc[date, "dividend"]

            if dividend > 0:

                dividend_cash = dividend * position.quantity

                dividend_by_ticker[ticker] = dividend_cash

                # 모든 모드에서 일단 현금에 입금
                # withdraw 모드의 출금 처리는 simulation_loop에서 담당
                portfolio.cash += dividend_cash

        return dividend_by_ticker