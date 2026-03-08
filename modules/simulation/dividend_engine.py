class DividendEngine:

    def process(
        self,
        portfolio,
        price_data,
        price_dict,
        date,
        dividend_mode
    ):

        daily_dividend = 0

        for ticker, position in portfolio.positions.items():

            if ticker not in price_data:
                continue

            if date not in price_data[ticker].index:
                continue

            dividend = price_data[ticker].loc[date, "dividend"]

            if dividend > 0:

                dividend_cash = dividend * position.quantity
                daily_dividend += dividend_cash

                if dividend_mode == "reinvest":
                    portfolio.cash += dividend_cash

                elif dividend_mode == "cash":
                    portfolio.cash += dividend_cash

                elif dividend_mode == "withdraw":
                    pass

        return daily_dividend