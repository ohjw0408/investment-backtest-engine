class DividendEngine:

    def process(
        self,
        portfolio,
        price_data,
        price_dict,
        date,
        dividend_mode
    ):

        dividend_by_ticker = {}

        for ticker, position in portfolio.positions.items():

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