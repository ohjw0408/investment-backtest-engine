from flask import Flask, render_template, jsonify, request
import random
import datetime
import sqlite3
from pathlib import Path

from modules.data_engine import DataEngine
from modules.info_engine import InfoEngine
from modules.portfolio_engine import PortfolioEngine
from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
from modules.dividend_simulator import DividendSimulator
from modules.rebalance.periodic import PeriodicRebalance

app = Flask(__name__)
data_engine      = DataEngine()
info_engine      = InfoEngine()
portfolio_engine = PortfolioEngine()

INDEX_DB_PATH = Path(__file__).parent / "data" / "meta" / "index_master.db"

# -----------------------------------------------
# 페이지 라우트
# -----------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculator')
def calculator():
    return render_template('calculator.html')

@app.route('/dividend-target')
def dividend_target():
    return render_template('dividend_target.html')

@app.route('/retirement')
def retirement():
    return render_template('retirement.html')

@app.route('/backtest')
def backtest():
    return render_template('backtest.html')

@app.route('/myassets')
def myassets():
    return render_template('myassets.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')

# -----------------------------------------------
# API - 검색
# -----------------------------------------------

@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    try:
        df = info_engine.search_fuzzy(q, limit=20)
        if df.empty:
            return jsonify([])
        results = []
        for _, row in df.iterrows():
            if row.get('is_etf'):
                badge = 'KR ETF' if row.get('country') == 'KR' else 'US ETF'
            else:
                badge = row.get('market') or row.get('country') or ''
            subtitle = (
                row.get('index_name') or
                row.get('category') or
                row.get('issuer') or ''
            )
            results.append({
                'code':     row['code'],
                'name':     row['name'],
                'badge':    badge,
                'subtitle': '' if str(subtitle) == 'nan' else str(subtitle),
                'country':  row.get('country', ''),
                'is_etf':   bool(row.get('is_etf', 0)),
            })
        return jsonify(results)
    except Exception as e:
        print(f"[search] 오류: {e}")
        return jsonify([])

# -----------------------------------------------
# API - 투자 계산기 헬퍼
# -----------------------------------------------

def get_dividend_start(ticker: str):
    try:
        cur = portfolio_engine.loader.conn.execute(
            "SELECT MIN(date) FROM corporate_actions WHERE code=? AND dividend > 0",
            (ticker,)
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None
    except Exception as e:
        print(f"[get_dividend_start] {ticker} 오류: {e}")
        return None


def get_price_start(ticker: str):
    try:
        cur = portfolio_engine.loader.conn.execute(
            "SELECT MIN(date) FROM price_daily WHERE code=?",
            (ticker,)
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None
    except Exception as e:
        print(f"[get_price_start] {ticker} 오류: {e}")
        return None


def _make_strategy_factory(target_weights, rebal_mode, band_width=0.05):
    if rebal_mode == 'none':
        rebalance_frequency = None
        drift_threshold     = None
    elif rebal_mode == 'band':
        rebalance_frequency = None
        drift_threshold     = band_width
    else:
        rebalance_frequency = rebal_mode
        drift_threshold     = None

    def strategy_factory():
        return PeriodicRebalance(
            target_weights      = target_weights,
            rebalance_frequency = rebalance_frequency,
            drift_threshold     = drift_threshold,
        )
    return strategy_factory


# -----------------------------------------------
# API - 투자 계산기
# -----------------------------------------------

@app.route('/api/calculator/run', methods=['POST'])
def calculator_run():
    try:
        body = request.get_json()

        tickers_input    = body['tickers']
        initial_capital  = float(body['initial_capital'])
        monthly_contrib  = float(body['monthly_contribution'])
        years            = int(body['years'])
        rebal_mode       = body['rebal_mode']
        band_width       = float(body.get('band_width', 0.05))
        dividend_mode    = body['dividend_mode']

        ticker_codes   = [t['code'] for t in tickers_input]
        target_weights = {t['code']: t['weight'] for t in tickers_input}

        strategy_factory = _make_strategy_factory(target_weights, rebal_mode, band_width)

        usdkrw_start = portfolio_engine.loader.USD_KRW_START

        for ticker in ticker_codes:
            try:
                portfolio_engine.loader.get_price(
                    ticker,
                    usdkrw_start,
                    datetime.date.today().strftime('%Y-%m-%d')
                )
            except Exception as e:
                print(f"[calculator] {ticker} 데이터 로드 오류: {e}")

        price_starts = [get_price_start(t) for t in ticker_codes]
        price_starts = [d for d in price_starts if d]

        if price_starts:
            data_start = max([usdkrw_start] + price_starts)
        else:
            data_start = usdkrw_start

        data_end = datetime.date.today().strftime('%Y-%m-%d')

        from dateutil.relativedelta import relativedelta
        start_dt  = datetime.datetime.strptime(data_start, '%Y-%m-%d').date()
        end_dt    = datetime.date.today()
        max_years = (end_dt - start_dt).days // 365

        if years > max_years:
            return jsonify({
                'error': f"데이터 부족: {ticker_codes}의 데이터는 {data_start}부터 있어서 "
                         f"최대 {max_years}년 시뮬레이션이 가능합니다."
            }), 400

        div_starts = [get_dividend_start(t) for t in ticker_codes]
        div_starts = [d for d in div_starts if d]
        div_start  = max(div_starts) if div_starts else None

        analyzer = AccumulationAnalyzer(
            portfolio_engine     = portfolio_engine,
            tickers              = ticker_codes,
            strategy_factory     = strategy_factory,
            data_start           = data_start,
            data_end             = data_end,
            accumulation_years   = years,
            monthly_contribution = monthly_contrib,
            initial_capital      = initial_capital,
            dividend_mode        = dividend_mode,
            step_months          = 3,
            verbose              = False,
            div_start            = div_start,
        )

        result = analyzer.run()

        if div_start:
            result['distribution']['div_data_start']  = div_start
            result['distribution']['div_cases_count'] = len(result['cases'])
        else:
            result['distribution']['no_dividend'] = True

        cases_summary = [
            {
                'run_id':    c['run_id'],
                'start':     c['start'],
                'end':       c['end'],
                'end_value': round(c['end_value']),
                'cagr':      round(c['cagr'], 4),
                'mdd':       round(c['mdd'], 4),
            }
            for c in result['cases']
        ]

        return jsonify({
            'cases':        cases_summary,
            'cases_count':  len(cases_summary),
            'distribution': result['distribution'],
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# -----------------------------------------------
# API - 배당 목표 역산
# -----------------------------------------------

def _make_dividend_analyzer(body):
    tickers_input  = body['tickers']
    ticker_codes   = [t['code'] for t in tickers_input]
    target_weights = {t['code']: t['weight'] for t in tickers_input}

    return DividendSimulator(
        loader      = portfolio_engine.loader,
        tickers     = ticker_codes,
        weights     = target_weights,
        div_mode    = body.get('dividend_mode', 'reinvest'),
        step_months = 3,
    )


@app.route('/api/dividend-target/probability', methods=['POST'])
def dividend_target_probability():
    try:
        body     = request.get_json()
        analyzer = _make_dividend_analyzer(body)
        result   = analyzer.get_probability(
            seed               = float(body['seed']),
            monthly            = float(body['monthly']),
            years              = int(body['years']),
            target_monthly_div = float(body['target_monthly_div']),
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/dividend-target/probability-curve', methods=['POST'])
def dividend_target_probability_curve():
    try:
        body     = request.get_json()
        analyzer = _make_dividend_analyzer(body)
        result   = analyzer.get_probability_curve(
            seed    = float(body['seed']),
            monthly = float(body['monthly']),
            years   = int(body['years']),
            targets = [float(t) for t in body['targets']],
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/dividend-target/solve', methods=['POST'])
def dividend_target_solve():
    try:
        body     = request.get_json()
        analyzer = _make_dividend_analyzer(body)

        seed    = float(body['seed'])    if body.get('seed')    is not None else None
        monthly = float(body['monthly']) if body.get('monthly') is not None else None
        years   = int(body['years'])     if body.get('years')   is not None else None

        result = analyzer.solve(
            target_monthly_div = float(body['target_monthly_div']),
            probability        = float(body.get('probability', 0.90)),
            seed               = seed,
            monthly            = monthly,
            years              = years,
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# -----------------------------------------------
# API - 포트폴리오 히스토리 (임시 더미)
# -----------------------------------------------

@app.route('/api/portfolio/history')
def portfolio_history():
    val = 7870200
    data = []
    for i in range(80):
        val += (random.random() - 0.38) * 300000
        val = max(val, 7000000)
        data.append(round(val))
    data[-1] = 15870200
    labels = [f"{2017 + i//12}년 {i%12+1}월" for i in range(80)]
    return jsonify({"labels": labels, "values": data, "current": 15870200, "change": 1.8})


# -----------------------------------------------
# API - 시장 지수
# -----------------------------------------------

def _get_krx_gold():
    """index_master.db에서 KRX 금현물 최근 2일치 조회"""
    try:
        if not INDEX_DB_PATH.exists():
            return None
        conn = sqlite3.connect(str(INDEX_DB_PATH))
        rows = conn.execute(
            "SELECT date, close FROM index_daily WHERE code='KRX_GOLD' ORDER BY date DESC LIMIT 2"
        ).fetchall()
        conn.close()

        if len(rows) >= 2:
            cur_price  = float(rows[0][1])
            prev_price = float(rows[1][1])
            cur_date   = rows[0][0]
            change     = round((cur_price - prev_price) / prev_price * 100, 2)
            # 스파크라인용 최근 20일
            conn2 = sqlite3.connect(str(INDEX_DB_PATH))
            spark_rows = conn2.execute(
                "SELECT close FROM index_daily WHERE code='KRX_GOLD' ORDER BY date DESC LIMIT 20"
            ).fetchall()
            conn2.close()
            spark = [round(float(r[0]), 0) for r in reversed(spark_rows)]
            return {
                "id":     "krx_gold",
                "name":   "금 (KRX 현물)",
                "tag":    "원/g",
                "value":  f"₩{cur_price:,.0f}",
                "change": f"{'+' if change >= 0 else ''}{change}%",
                "up":     change >= 0,
                "spark":  spark,
                "note":   cur_date,
            }
        elif len(rows) == 1:
            # 1개만 있으면 KRX API로 최신 받아오기
            try:
                from modules.krx.krx_client import KRXClient
                client = KRXClient()
                df = client.get_gold_price()
                if not df.empty and float(df.iloc[0]["close"]) > 0:
                    cur_price  = float(df.iloc[0]["close"])
                    prev_price = float(rows[0][1])
                    change     = round((cur_price - prev_price) / prev_price * 100, 2)
                    return {
                        "id":     "krx_gold",
                        "name":   "금 (KRX 현물)",
                        "tag":    "원/g",
                        "value":  f"₩{cur_price:,.0f}",
                        "change": f"{'+' if change >= 0 else ''}{change}%",
                        "up":     change >= 0,
                        "spark":  [],
                    }
            except Exception as e:
                print(f"[market] KRX 금 최신 조회 실패: {e}")
        else:
            # DB에 없으면 KRX API로 받아오기
            try:
                from modules.krx.krx_client import KRXClient
                client = KRXClient()
                df = client.get_gold_price()
                if not df.empty and float(df.iloc[0]["close"]) > 0:
                    return {
                        "id":     "krx_gold",
                        "name":   "금 (KRX 현물)",
                        "tag":    "원/g",
                        "value":  f"₩{df.iloc[0]['close']:,.0f}",
                        "change": "—",
                        "up":     True,
                        "spark":  [],
                    }
            except Exception as e:
                print(f"[market] KRX 금 조회 실패: {e}")
    except Exception as e:
        print(f"[market] KRX 금현물 오류: {e}")
    return None


@app.route('/api/market')
def market():
    # 순서: sp500, nasdaq, kospi / 국제금, KRX금현물, 환율
    yf_tickers = [
        {"id": "sp500",  "name": "S&P 500",      "tag": "S&P",    "ticker": "^GSPC", "prefix": "",  "fmt": "int"},
        {"id": "nasdaq", "name": "NASDAQ",         "tag": "NASDAQ", "ticker": "^IXIC", "prefix": "",  "fmt": "int"},
        {"id": "kospi",  "name": "코스피 (KOSPI)", "tag": "KOSPI",  "ticker": "^KS11", "prefix": "",  "fmt": "int"},
        {"id": "gold",   "name": "금 (국제)",      "tag": "USD/oz", "ticker": "GC=F",  "prefix": "$", "fmt": "float"},
        {"id": "usdkrw", "name": "환율",           "tag": "USD/KRW","ticker": "KRW=X", "prefix": "₩", "fmt": "float"},
    ]

    yf_result = {}
    for info in yf_tickers:
        try:
            series = data_engine.get_symbol_data(info["ticker"])
            if hasattr(series, 'squeeze'):
                series = series.squeeze()
            if series.empty or len(series) < 2:
                continue
            current = float(series.iloc[-1].iloc[0]) if hasattr(series.iloc[-1], 'iloc') else float(series.iloc[-1])
            prev    = float(series.iloc[-2].iloc[0]) if hasattr(series.iloc[-2], 'iloc') else float(series.iloc[-2])
            change  = round((current - prev) / prev * 100, 2)
            spark   = [round(float(v), 2) for v in series.iloc[-20:].values.flatten().tolist()]
            value_str = f"{info['prefix']}{current:,.0f}" if info["fmt"] == "int" else f"{info['prefix']}{current:,.2f}"
            yf_result[info["id"]] = {
                "id":     info["id"],
                "name":   info["name"],
                "tag":    info["tag"],
                "value":  value_str,
                "change": f"{'+' if change >= 0 else ''}{change}%",
                "up":     change >= 0,
                "spark":  spark,
            }
        except Exception as e:
            print(f"[market] {info['id']} 오류: {e}")

    # 순서 고정: sp500, nasdaq, kospi, gold(국제), krx_gold(한국), usdkrw
    result = []
    for id_ in ["sp500", "nasdaq", "kospi"]:
        if id_ in yf_result:
            result.append(yf_result[id_])

    if "gold" in yf_result:
        result.append(yf_result["gold"])

    krx_gold = _get_krx_gold()
    if krx_gold:
        result.append(krx_gold)

    if "usdkrw" in yf_result:
        result.append(yf_result["usdkrw"])

    return jsonify(result)


# -----------------------------------------------
# API - 자산군별 비교 (임시 더미)
# -----------------------------------------------

@app.route('/api/assets')
def assets():
    return jsonify([
        {"name": "주식",                "icon": "🏢", "color": "#1976D2", "change": "+7%",   "up": True,  "pct": 0.55},
        {"name": "채권",                "icon": "📜", "color": "#43A047", "change": "+2.5%", "up": True,  "pct": 0.25},
        {"name": "금",                  "icon": "🥇", "color": "#F9A825", "change": "+1.5%", "up": True,  "pct": 0.12},
        {"name": "원자재 (Commodities)","icon": "🪨", "color": "#EF5350", "change": "-0.5%", "up": False, "pct": 0.08},
    ])


# -----------------------------------------------

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)