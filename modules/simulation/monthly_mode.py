"""월별 모드 데이터 헬퍼 (divrefactoring 3-1/3-2).

SimulationLoop은 dates 리스트 주도라 루프 수정 없이 "월말 리샘플 데이터 + 월말 날짜"를
주입하면 월별 시뮬이 된다(기존 일별 경로 무변경 = 무위험). 배당계산기 역산 루프의
일별 전환 비용(~20배)을 막는 핵심.

규약 (PriceDataLoader.load의 월별 미러):
- 달력 = 전 종목 합집합의 calendar month-end(ME) 라벨 → 전 종목 positional 정렬 보장
  (SimulationLoop이 price_array[ticker][i]를 dates[i]와 위치로 매칭하므로 필수).
- close = 그 달 마지막 유효 종가, ffill(거래 없던 달은 직전 값). 상장 전 leading NaN 유지.
- dividend = 그 달 합계(fillna 0 — ffill 금지, 중복 지급 방지).
- split = 그 달 곱(기본 1).
- 월 배당은 월말에 일괄 지급·월말 종가로 재투자 — 기존 DividendSimulator(월별 루프,
  월말 가격) 동작과 동일 계열. 일중 타이밍 차이는 plan 차이 6에서 수용됨.
"""
import pandas as pd


def to_monthly_price_data(price_data: dict):
    """일별 price_data dict → (월별 price_data dict, 월말 dates 리스트).

    입력 df는 date 인덱스 + close(필수)/dividend/split 컬럼 가정(PriceDataLoader 출력형).
    """
    monthly = {}
    for ticker, df in price_data.items():
        cols = {"close": df["close"].resample("ME").last()}
        cols["open"] = cols["high"] = cols["low"] = cols["close"]
        cols["volume"] = (
            df["volume"].resample("ME").sum() if "volume" in df.columns else 0.0
        )
        cols["dividend"] = (
            df["dividend"].fillna(0).resample("ME").sum()
            if "dividend" in df.columns else 0.0
        )
        cols["split"] = (
            df["split"].fillna(1).resample("ME").prod()
            if "split" in df.columns else 1.0
        )
        monthly[ticker] = pd.DataFrame(cols)

    all_dates = set()
    for df in monthly.values():
        all_dates.update(df.index)
    full_index = pd.DatetimeIndex(sorted(all_dates))

    for ticker in monthly:
        df = monthly[ticker].reindex(full_index)
        price_cols = ["open", "high", "low", "close", "volume"]
        df[price_cols] = df[price_cols].ffill()
        df["dividend"] = df["dividend"].fillna(0)
        df["split"] = df["split"].fillna(1)
        monthly[ticker] = df

    return monthly, list(full_index)


def last_year_dividend(history_df: pd.DataFrame, window_end) -> float:
    """history_df에서 윈도우 종료 기준 마지막 1년 순배당 합계 (3-2).

    기존 DividendSimulator._simulate_one과 동일 정의:
    last_year_start = (start + years) − 1년, 필터 = div_date >= last_year_start (이상).
    window_end는 실제 마지막 거래일이 아니라 "의도된 종료일(start + years)"을 받아야
    기존 역산 결과와 경계가 일치한다(plan 위험 6).
    """
    if history_df is None or history_df.empty:
        return 0.0
    last_year_start = pd.Timestamp(window_end) - pd.DateOffset(years=1)
    dates = pd.to_datetime(history_df["date"])
    mask = dates >= last_year_start
    return float(history_df.loc[mask, "dividend_income"].sum())
