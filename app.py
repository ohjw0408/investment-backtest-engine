from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import random
import datetime
import sqlite3
import os
from pathlib import Path
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from modules.auth_manager import (
    init_db, get_or_create_user, get_user_by_id,
    get_groups, upsert_group, delete_group,
    get_holdings, upsert_holding, delete_holding,
    init_holdings_db, get_settings, save_settings,
)

load_dotenv()

try:
    import sentry_sdk  # type: ignore[import-untyped]
    from sentry_sdk.integrations.flask import FlaskIntegration as _FlaskIntegration  # type: ignore[import-untyped]
    _sentry_available = True
except ImportError:
    sentry_sdk = None  # type: ignore[assignment]
    _FlaskIntegration = None  # type: ignore[assignment]
    _sentry_available = False

_sentry_dsn = os.environ.get('SENTRY_DSN', '')
if _sentry_dsn and _sentry_available:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[_FlaskIntegration()],
        traces_sample_rate=0,
        send_default_pii=False,
    )

from modules.data_engine import DataEngine
from modules.info_engine import InfoEngine
from modules.portfolio_engine import PortfolioEngine
from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
from modules.retirement.data_preparer import DataPreparer
from modules.dividend_simulator import DividendSimulator
from modules.rebalance.periodic import PeriodicRebalance
from modules.market_quote_service import MarketQuoteService

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')
import datetime as _dt_mod
app.config['PERMANENT_SESSION_LIFETIME'] = _dt_mod.timedelta(days=30)

INDEX_DB_PATH = Path(__file__).parent / "data" / "meta" / "index_master.db"
PRICE_DB_PATH = Path(__file__).parent / "data" / "price_cache" / "price_daily.db"

init_holdings_db()
data_engine          = DataEngine()
info_engine          = InfoEngine()
portfolio_engine     = PortfolioEngine()
market_quote_service = MarketQuoteService(index_db_path=INDEX_DB_PATH)

# Google OAuth
oauth  = OAuth(app)
google = oauth.register(
    name='google',
    client_id     = os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url = 'https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs = {'scope': 'openid email profile'},
)

# DB 초기화
init_db()

# 모든 템플릿에 user 자동 주입
@app.context_processor
def inject_user():
    return {'user': current_user()}

def current_user():
    uid = session.get('user_id')
    return get_user_by_id(uid) if uid else None

# -----------------------------------------------
# Google OAuth 라우트
# -----------------------------------------------

@app.route('/auth/google')
def google_login():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route('/auth/google/callback')
def google_callback():
    token     = google.authorize_access_token()
    userinfo  = token.get('userinfo')
    if not userinfo:
        return redirect('/')
    user = get_or_create_user(
        google_id = userinfo['sub'],
        email     = userinfo.get('email', ''),
        name      = userinfo.get('name', ''),
        picture   = userinfo.get('picture', ''),
    )
    session.permanent = True
    session['user_id'] = user['id']
    return redirect('/')


@app.route('/auth/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/api/me')
def me():
    user = current_user()
    if not user:
        return jsonify({'logged_in': False})
    return jsonify({
        'logged_in': True,
        'name':      user['name'],
        'email':     user['email'],
        'picture':   user['picture'],
    })


@app.route('/api/settings/tax', methods=['GET'])
def get_tax_settings():
    uid = session.get('user_id')
    if not uid:
        return jsonify({})
    return jsonify(get_settings(uid))


@app.route('/api/settings/tax', methods=['POST'])
def save_tax_settings():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': '로그인 필요'}), 401
    save_settings(uid, request.get_json())
    return jsonify({'ok': True})


# -----------------------------------------------
# 페이지 라우트
# -----------------------------------------------

@app.route('/')
def index():
    return render_template('index.html', user=current_user())

@app.route('/search')
def search_page():
    return render_template('search.html')

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
@app.route('/tax-settings')
def settings():
    return render_template('tax_settings.html')

# -----------------------------------------------
# API - 검색
# -----------------------------------------------

@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    try:
        results = []

        # KRX 금현물 특별 처리
        if any(k in q.upper() for k in ['금', 'GOLD', 'KRX', '현물']):
            results.append({
                'code': 'KRX_GOLD', 'name': '금 현물 (KRX, 1g)',
                'badge': 'KRX', 'subtitle': 'KRX 금시장 현물',
                'country': 'KR', 'is_etf': False,
            })

        df = info_engine.search_fuzzy(q, limit=20)
        if not df.empty:
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

        # 가격 배치 조회 (price_daily.db)
        if results:
            try:
                import sqlite3 as _sq
                pdb = PRICE_DB_PATH
                if pdb.exists():
                    pconn = _sq.connect(str(pdb))
                    codes = [r['code'] for r in results]
                    ph = ','.join('?' * len(codes))
                    # 최근 종가
                    cur_rows = pconn.execute(f"""
                        SELECT p.code, p.close FROM price_daily p
                        INNER JOIN (
                            SELECT code, MAX(date) as mx FROM price_daily
                            WHERE code IN ({ph}) AND close IS NOT NULL GROUP BY code
                        ) m ON p.code=m.code AND p.date=m.mx
                    """, codes).fetchall()
                    # 전일 종가
                    prev_rows = pconn.execute(f"""
                        SELECT p.code, p.close FROM price_daily p
                        INNER JOIN (
                            SELECT p2.code, MAX(p2.date) as mx2
                            FROM price_daily p2
                            INNER JOIN (
                                SELECT code, MAX(date) as mx FROM price_daily
                                WHERE code IN ({ph}) AND close IS NOT NULL GROUP BY code
                            ) m ON p2.code=m.code AND p2.date < m.mx AND p2.close IS NOT NULL
                            GROUP BY p2.code
                        ) prev ON p.code=prev.code AND p.date=prev.mx2
                    """, codes).fetchall()
                    pconn.close()
                    price_map = {r[0]: r[1] for r in cur_rows}
                    prev_map  = {r[0]: r[1] for r in prev_rows}
                    for res in results:
                        c = res['code']
                        cur = price_map.get(c)
                        prv = prev_map.get(c)
                        res['price'] = round(cur, 2) if cur else None
                        res['change_pct'] = round((cur - prv) / prv * 100, 2) if cur and prv else None
                        res['currency'] = 'KRW' if res['country'] == 'KR' else 'USD'
            except Exception as e:
                print(f"[search price] {e}")

        return jsonify(results[:20])
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

def _run_calculator_logic(body: dict, progress_callback=None) -> dict:
    """calculator_run 핵심 로직. 동기(직접 호출) / 비동기(Celery) 양쪽에서 사용."""
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

    data_start = max([usdkrw_start] + price_starts) if price_starts else usdkrw_start
    data_end   = datetime.date.today().strftime('%Y-%m-%d')

    from dateutil.relativedelta import relativedelta
    start_dt  = datetime.datetime.strptime(data_start, '%Y-%m-%d').date()
    max_years = (datetime.date.today() - start_dt).days // 365

    if years > max_years:
        raise ValueError(
            f"데이터 부족: {ticker_codes}의 데이터는 {data_start}부터 있어서 "
            f"최대 {max_years}년 시뮬레이션이 가능합니다."
        )

    div_starts = [get_dividend_start(t) for t in ticker_codes]
    div_starts = [d for d in div_starts if d]
    div_start  = max(div_starts) if div_starts else None

    tax_enabled     = body.get('tax_enabled', False)
    account_type    = body.get('account_type', '위탁')
    user_settings   = body.get('user_settings', {})
    isa_renewal     = body.get('isa_renewal', False)
    gain_harvesting = body.get('gain_harvesting', False)
    tax_engine      = None
    if tax_enabled:
        from modules.tax.base_tax import TaxEngine
        tax_engine = TaxEngine(user_settings)

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
        tax_engine           = tax_engine,
        account_type         = account_type,
        isa_renewal          = isa_renewal,
        gain_harvesting      = gain_harvesting,
        progress_callback    = progress_callback,
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

    return {
        'cases':        cases_summary,
        'cases_count':  len(cases_summary),
        'distribution': result['distribution'],
    }


@app.route('/api/calculator/run', methods=['POST'])
def calculator_run():
    try:
        body   = request.get_json()
        result = _run_calculator_logic(body)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/calculator/submit', methods=['POST'])
def calculator_submit():
    from tasks import run_simulation_task, add_to_queue
    payload = request.get_json()
    task    = run_simulation_task.delay(payload)
    add_to_queue(task.id)
    return jsonify({'task_id': task.id, 'status': 'PENDING'})


@app.route('/api/task/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id: str):
    from celery_app import celery as celery_app
    from tasks import _remove_from_queue, set_cancel_flag
    set_cancel_flag(task_id)
    _remove_from_queue(task_id)
    return jsonify({'ok': True})


@app.route('/api/task/<task_id>', methods=['GET'])
def task_status(task_id: str):
    from celery_app import celery as celery_app
    from tasks import get_queue_rank, get_avg_duration

    task = celery_app.AsyncResult(task_id)

    if task.state == 'PENDING':
        return jsonify({
            'status':       'PENDING',
            'queue_rank':   get_queue_rank(task_id),
            'avg_duration': get_avg_duration(),
            'percent':      0,
        })

    elif task.state == 'PROGRESS':
        meta = task.info or {}
        return jsonify({
            'status':  'PROGRESS',
            'percent': meta.get('percent', 0),
            'current': meta.get('current', 0),
            'total':   meta.get('total', 0),
            'elapsed': meta.get('elapsed', 0),
            'eta':     meta.get('eta'),
            'phase':   meta.get('phase', 'computing'),
        })

    elif task.state == 'SUCCESS':
        result = task.result or {}
        if result.get('status') == 'CANCELLED':
            return jsonify({'status': 'CANCELLED'})
        if result.get('status') == 'FAILURE':
            return jsonify({'status': 'FAILURE', 'error': result.get('error', '알 수 없는 오류')})
        return jsonify({
            'status': 'SUCCESS',
            'result': result.get('result'),
        })

    else:
        return jsonify({
            'status': 'FAILURE',
            'error':  str(task.info),
        })


# -----------------------------------------------
# API - 투자 계산기 비동기 제출 (이미 위에 정의됨)
# API - 은퇴 설계 / 백테스트 / 배당 — 비동기 submit
# -----------------------------------------------

@app.route('/api/retirement/submit', methods=['POST'])
def retirement_submit():
    from tasks import run_retirement_task, add_to_queue
    payload = request.get_json()
    payload['_mode'] = 'withdrawal' if payload.get('_withdrawal_only') else 'full'
    task = run_retirement_task.delay(payload)
    add_to_queue(task.id)
    return jsonify({'task_id': task.id, 'status': 'PENDING'})


@app.route('/api/backtest/submit', methods=['POST'])
def backtest_submit():
    from tasks import run_backtest_task, add_to_queue
    task = run_backtest_task.delay(request.get_json())
    add_to_queue(task.id)
    return jsonify({'task_id': task.id, 'status': 'PENDING'})


@app.route('/api/dividend-target/submit', methods=['POST'])
def dividend_target_submit():
    from tasks import run_dividend_task, add_to_queue
    task = run_dividend_task.delay(request.get_json())
    add_to_queue(task.id)
    return jsonify({'task_id': task.id, 'status': 'PENDING'})


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
    return jsonify({"empty": True, "labels": [], "values": []})


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
    return jsonify(market_quote_service.get_all())


# -----------------------------------------------
# API - 배당 목표 시나리오
# -----------------------------------------------

@app.route('/api/dividend-target/scenario', methods=['POST'])
def dividend_target_scenario():
    try:
        body = request.get_json()
        tickers_input  = body['tickers']
        ticker_codes   = [t['code'] for t in tickers_input]
        target_weights = {t['code']: t['weight'] for t in tickers_input}

        from modules.dividend_simulator import DividendSimulator
        sim = DividendSimulator(
            loader      = portfolio_engine.loader,
            tickers     = ticker_codes,
            weights     = target_weights,
            div_mode    = body.get('dividend_mode', 'reinvest'),
            step_months = 3,
        )

        seed_cfg    = body.get('seed',    {"center": 0,      "step": 0, "n": 0, "mode": "fixed"})
        monthly_cfg = body.get('monthly', {"center": 500000, "step": 0, "n": 0, "mode": "fixed"})
        years_cfg   = body.get('years',   {"center": 20,     "step": 0, "n": 0, "mode": "fixed"})

        result = sim.run_scenario(
            target_monthly_div = float(body['target_monthly_div']),
            probability        = float(body.get('probability', 0.90)),
            seed_cfg           = seed_cfg,
            monthly_cfg        = monthly_cfg,
            years_cfg          = years_cfg,
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# -----------------------------------------------
# API - 은퇴 설계
# -----------------------------------------------

@app.route('/api/retirement/run', methods=['POST'])
def retirement_run():
    try:
        body = request.get_json()

        tickers_input  = body['tickers']
        ticker_codes   = [t['code'] for t in tickers_input]
        target_weights = {t['code']: t['weight'] for t in tickers_input}

        initial_capital      = float(body['initial_capital'])
        monthly_contribution = float(body['monthly_contribution'])
        accumulation_years   = int(body['accumulation_years'])
        dividend_mode        = body.get('dividend_mode', 'reinvest')
        rebal_mode           = body.get('rebal_mode', 'none')
        band_width           = float(body.get('band_width', 0.05))
        monthly_withdrawal   = float(body['monthly_withdrawal'])
        withdrawal_years     = int(body['withdrawal_years'])
        inflation            = float(body.get('inflation', 0.02))
        target_percentile    = float(body.get('target_percentile', 0.90))

        strategy_factory = _make_strategy_factory(target_weights, rebal_mode, band_width)

        data_end = datetime.date.today().strftime('%Y-%m-%d')

        # ── 데이터 준비 (백필 + 가상 데이터 생성) ──────────
        preparer = DataPreparer(price_db_path=PRICE_DB_PATH, verbose=False)
        prep     = preparer.prepare(
            tickers     = ticker_codes,
            sim_years   = accumulation_years,
            data_end    = data_end,
            step_months = 3,
        )
        preparer.close()

        data_start     = prep["data_start"]
        synthetic_info = prep["synthetic_info"]
        backfilled     = prep["backfilled"]

        div_starts = [get_dividend_start(t) for t in ticker_codes]
        div_starts = [d for d in div_starts if d]
        div_start  = max(div_starts) if div_starts else None

        # 1. 축적기
        from modules.retirement.accumulation_analyzer import AccumulationAnalyzer
        # 세금 파라미터
        tax_enabled     = body.get('tax_enabled', False)
        account_type    = body.get('account_type', '위탁')
        user_settings   = body.get('user_settings', {})
        isa_renewal     = body.get('isa_renewal', False)
        gain_harvesting = body.get('gain_harvesting', False)
        ret_tax_engine  = None
        if tax_enabled:
            from modules.tax.base_tax import TaxEngine
            ret_tax_engine = TaxEngine(user_settings)

        acc_analyzer = AccumulationAnalyzer(
            portfolio_engine     = portfolio_engine,
            tickers              = ticker_codes,
            strategy_factory     = strategy_factory,
            data_start           = data_start,
            data_end             = data_end,
            accumulation_years   = accumulation_years,
            monthly_contribution = monthly_contribution,
            initial_capital      = initial_capital,
            dividend_mode        = dividend_mode,
            step_months          = 3,
            verbose              = False,
            div_start            = div_start,
            tax_engine           = ret_tax_engine,
            account_type         = account_type,
            isa_renewal          = isa_renewal,
            gain_harvesting      = gain_harvesting,
        )
        acc_result = acc_analyzer.run()

        # 2. 은퇴 플래너 (축적 → 인출)
        from modules.retirement.retirement_planner import RetirementPlanner
        planner = RetirementPlanner(
            acc_result         = acc_result,
            wd_config          = {
                "portfolio_engine": portfolio_engine,
                "tickers":          ticker_codes,
                "strategy_factory": strategy_factory,
                "data_start":       data_start,
                "data_end":         data_end,
                "withdrawal_years": withdrawal_years,
                "dividend_mode":    dividend_mode,
                "step_months":      6,
            },
            monthly_withdrawal = monthly_withdrawal,
            withdrawal_years   = withdrawal_years,
            inflation          = inflation,
            verbose            = False,
        )
        report = planner.run(target_percentile=target_percentile)

        # 3. 응답 구성
        return jsonify({
            "accumulation_summary": report["accumulation_summary"],
            "sample_results": [
                {
                    "percentile":      s["percentile"],
                    "initial_capital": round(s["initial_capital"]),
                    "success_rate":    round(s["success_rate"], 4),
                    "end_value_p50":   round(s["end_value_p50"]),
                    "wd_end_values":   s.get("wd_end_values", []),
                }
                for s in report["sample_results"]
            ],
            "combined_summary":  report["combined_summary"],
            "message":           report["message"],
            "acc_cases_count":   len(acc_result["cases"]),
            "acc_n_real":        acc_result.get("n_real"),
            "acc_n_synthetic":   acc_result.get("n_synthetic"),
            "acc_values":        [round(c["end_value"]) for c in acc_result["cases"]],
            "wd_values":         [
                v
                for s in report["sample_results"]
                for v in s.get("wd_end_values", [])
            ],
            "data_start":        data_start,
            "synthetic_info":    synthetic_info,
            "backfilled":        backfilled,
            "tax_enabled":       tax_enabled,
            "account_type":      account_type if tax_enabled else None,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/retirement/withdrawal', methods=['POST'])
def retirement_withdrawal():
    try:
        body = request.get_json()

        tickers_input  = body['tickers']
        ticker_codes   = [t['code'] for t in tickers_input]
        target_weights = {t['code']: t['weight'] for t in tickers_input}

        initial_capital    = float(body['initial_capital'])
        monthly_withdrawal = float(body['monthly_withdrawal'])
        withdrawal_years   = int(body['withdrawal_years'])
        inflation          = float(body.get('inflation', 0.02))
        dividend_mode      = body.get('dividend_mode', 'reinvest')
        rebal_mode         = body.get('rebal_mode', 'none')
        target_percentile  = float(body.get('target_percentile', 0.90))

        strategy_factory = _make_strategy_factory(target_weights, rebal_mode)

        data_end = datetime.date.today().strftime('%Y-%m-%d')

        # ── 데이터 준비 (백필 + 가상 데이터 생성) ──────────
        preparer = DataPreparer(price_db_path=PRICE_DB_PATH, verbose=False)
        prep     = preparer.prepare(
            tickers     = ticker_codes,
            sim_years   = withdrawal_years,
            data_end    = data_end,
            step_months = 3,
        )
        preparer.close()

        data_start = prep["data_start"]

        # 세금 파라미터
        tax_enabled   = body.get('tax_enabled', False)
        account_type  = body.get('account_type', '위탁')
        user_settings = body.get('user_settings', {})
        acc_years     = int(body.get('accumulation_years', 0))
        ret_tax_engine = None
        if tax_enabled:
            from modules.tax.base_tax import TaxEngine
            ret_tax_engine = TaxEngine(user_settings)

        from modules.retirement.withdrawal_analyzer import WithdrawalAnalyzer
        wd_analyzer = WithdrawalAnalyzer(
            portfolio_engine   = portfolio_engine,
            tickers            = ticker_codes,
            strategy_factory   = strategy_factory,
            data_start         = data_start,
            data_end           = data_end,
            withdrawal_years   = withdrawal_years,
            monthly_withdrawal = monthly_withdrawal,
            initial_capital    = initial_capital,
            inflation          = inflation,
            dividend_mode      = dividend_mode,
            step_months        = 3,
            verbose            = False,
            tax_engine         = ret_tax_engine,
            account_type       = account_type if tax_enabled else "위탁",
            current_age        = user_settings.get("age", 40) if tax_enabled else 40,
            accumulation_years = acc_years,
        )
        result = wd_analyzer.run()

        dist     = result['distribution']
        end_vals = [round(c['end_value']) for c in result['cases']]

        return jsonify({
            "survival_rate": round(result['success_rate'], 4),
            "combined_summary": {
                "survival_rate": round(result['success_rate'], 4),
                "combined_end_value": {
                    "p10":  round(dist['end_value_ratio']['p10'] * initial_capital),
                    "p25":  round(dist['end_value_ratio']['p25'] * initial_capital),
                    "p50":  round(dist['end_value_ratio']['p50'] * initial_capital),
                    "p75":  round(dist['end_value_ratio']['p75'] * initial_capital),
                    "p90":  round(dist['end_value_ratio']['p90'] * initial_capital),
                },
            },
            "wd_values":        end_vals,
            "data_start":       data_start,
            "n_real":           result.get("n_real"),
            "n_synthetic":      result.get("n_synthetic"),
            "pension_tax_info": result.get("pension_tax_info"),
            "tax_enabled":      tax_enabled,
            "account_type":     account_type if tax_enabled else None,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500







# -----------------------------------------------
# 내 자산 API
# -----------------------------------------------

@app.route('/api/myassets/data')
def myassets_data():
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    uid      = session['user_id']
    holdings = get_holdings(uid)
    groups   = get_groups(uid)

    # 현재가 조회
    from pathlib import Path as _P
    import sqlite3 as _sq

    codes  = list({h['code'] for h in holdings})
    prices = {}

    # USD/KRW 최신 환율 한 번만 조회
    try:
        idx_db = _P(__file__).parent / 'data' / 'meta' / 'index_master.db'
        ic  = _sq.connect(str(idx_db))
        row = ic.execute("SELECT close FROM index_daily WHERE code='USD/KRW' ORDER BY date DESC LIMIT 1").fetchone()
        ic.close()
        usdkrw = float(row[0]) if row else 1300.0
    except Exception:
        usdkrw = 1300.0

    price_db = _P(__file__).parent / 'data' / 'price_cache' / 'price_daily.db'
    pc = _sq.connect(str(price_db))

    import yfinance as _yf
    from modules.krx.krx_client import KRXClient as _KRXC

    pc.close()

    # KR / US 종목 분리
    kr_codes = [c for c in codes if c != 'KRX_GOLD' and portfolio_engine.loader.is_kr_etf(c)]
    us_codes = [c for c in codes if c != 'KRX_GOLD' and not portfolio_engine.loader.is_kr_etf(c)]

    # KR 종목 → KRX API (공식 종가, 이미 KRW → 환율 변환 없음)
    if kr_codes:
        try:
            krx   = _KRXC(debug=False)
            kr_px = krx.get_current_prices_kr(kr_codes)
            prices.update(kr_px)
        except Exception:
            pass
        # KRX API 실패한 종목은 yfinance .KS 폴백 (이미 KRW)
        for code in kr_codes:
            if prices.get(code, 0) == 0:
                try:
                    hist = _yf.Ticker(f"{code}.KS").history(period="2d")
                    if not hist.empty:
                        prices[code] = float(hist["Close"].iloc[-1])  # .KS는 이미 KRW
                except Exception:
                    pass

    # US 종목 → yfinance (USD) → KRW 변환
    for code in us_codes:
        try:
            hist = _yf.Ticker(code).history(period="2d")
            if not hist.empty:
                prices[code] = float(hist["Close"].iloc[-1]) * usdkrw  # USD → KRW
        except Exception:
            prices[code] = 0

    # KRX_GOLD 별도 처리
    if 'KRX_GOLD' in codes:
        try:
            ic  = _sq.connect(str(idx_db))
            row = ic.execute("SELECT close FROM index_daily WHERE code='KRX_GOLD' ORDER BY date DESC LIMIT 1").fetchone()
            ic.close()
            prices['KRX_GOLD'] = round(float(row[0])) if row else 0
        except Exception:
            prices['KRX_GOLD'] = 0

    return jsonify({'holdings': holdings, 'groups': groups, 'prices': prices})


@app.route('/api/myassets/holding', methods=['POST'])
def myassets_save_holding():
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    uid  = session['user_id']
    body = request.json
    upsert_holding(
        user_id      = uid,
        code         = body['code'],
        quantity     = float(body['quantity']),
        avg_price    = float(body.get('avg_price', 0)),
        account_type = body.get('account_type', '일반'),
        group_id     = body.get('group_id') or None,
        holding_id   = body.get('id') or None,
    )
    return jsonify({'ok': True})


@app.route('/api/myassets/holding/<int:holding_id>', methods=['DELETE'])
def myassets_delete_holding(holding_id):
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    delete_holding(session['user_id'], holding_id)
    return jsonify({'ok': True})


@app.route('/api/myassets/group', methods=['POST'])
def myassets_save_group():
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    body = request.json
    upsert_group(
        user_id    = session['user_id'],
        name       = body['name'],
        color      = body.get('color', '#1976D2'),
        target_pct = float(body.get('target_pct', 0)),
        group_id   = body.get('id') or None,
    )
    return jsonify({'ok': True})


@app.route('/api/myassets/group/<int:group_id>', methods=['DELETE'])
def myassets_delete_group(group_id):
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    delete_group(session['user_id'], group_id)
    return jsonify({'ok': True})

# -----------------------------------------------
# 백테스트 API
# -----------------------------------------------

@app.route('/api/backtest/run', methods=['POST'])
def backtest_run():
    import numpy as np
    from modules.core.portfolio                 import Portfolio
    from modules.config.simulation_config       import SimulationConfig
    from modules.execution.order_executor       import OrderExecutor
    from modules.execution.cash_allocator       import CashAllocator
    from modules.simulation.dividend_engine     import DividendEngine
    from modules.simulation.contribution_engine import ContributionEngine
    from modules.simulation.withdrawal_engine   import WithdrawalEngine
    from modules.simulation.history_recorder    import HistoryRecorder
    from modules.simulation.simulation_loop     import SimulationLoop
    from modules.rebalance.periodic             import PeriodicRebalance

    body = request.json
    try:
        tickers    = [t['code']   for t in body['tickers']]
        weights    = {t['code']:  t['weight'] for t in body['tickers']}
        start_date = body['start_date']
        end_date   = body['end_date']
        initial    = float(body.get('initial_capital', 10_000_000))
        monthly    = float(body.get('monthly_contribution', 0))
        div_mode   = body.get('dividend_mode', 'reinvest')
        rebal_mode = body.get('rebal_mode', 'none')
        band_width = float(body.get('band_width', 0.05))

        rebal_freq = None if rebal_mode in ('none', 'band') else rebal_mode
        drift      = band_width if rebal_mode == 'band' else None

        strategy = PeriodicRebalance(
            target_weights      = weights,
            rebalance_frequency = rebal_freq,
            drift_threshold     = drift,
        )
        config = SimulationConfig(
            start_date           = start_date,
            end_date             = end_date,
            tickers              = tickers,
            target_weights       = weights,
            initial_capital      = initial,
            monthly_contribution = monthly,
            withdrawal_amount    = 0,
            dividend_mode        = div_mode,
            rebalance_frequency  = rebal_freq,
            inflation            = 0.0,
        )

        price_data, dates = portfolio_engine.price_loader.load(tickers, start_date, end_date)

        # 세금 주입
        tax_enabled     = body.get('tax_enabled', False)
        account_type    = body.get('account_type', '위탁')
        user_settings   = body.get('user_settings', {})
        gain_harvesting = body.get('gain_harvesting', False)

        # 계좌별 투자 제약 검증
        if tax_enabled and account_type != '위탁':
            from modules.tax.base_tax    import TaxEngine as _TaxEngine
            from modules.tax.account_tax import validate_account_portfolio
            _check = validate_account_portfolio(
                account_type, tickers, weights, _TaxEngine(user_settings)
            )
            if not _check['valid']:
                return jsonify({
                    'error':      'account_restrictions',
                    'violations': _check['violations'],
                    'disclaimer': _check.get('disclaimer'),
                }), 400

        bt_tax_engine   = None
        if tax_enabled:
            from modules.tax.base_tax    import TaxEngine
            from modules.tax.account_tax import TaxedDividendEngine
            from modules.execution.order_executor import TaxedOrderExecutor
            from modules.core.portfolio  import TaxTrackedPortfolio
            bt_tax_engine = TaxEngine(user_settings)
            div_engine    = TaxedDividendEngine(DividendEngine(), bt_tax_engine, account_type)
            exec_engine   = TaxedOrderExecutor(bt_tax_engine, account_type,
                                               gain_harvesting=gain_harvesting)
            portfolio     = TaxTrackedPortfolio(initial)
        else:
            div_engine    = DividendEngine()
            exec_engine   = OrderExecutor()
            portfolio     = Portfolio(initial)

        loop = SimulationLoop(
            div_engine, ContributionEngine(), WithdrawalEngine(),
            exec_engine, CashAllocator()
        )
        recorder = HistoryRecorder()
        loop.run(portfolio, strategy, config, price_data, dates, recorder)
        history_df = recorder.to_dataframe()

        if history_df.empty:
            return jsonify({'error': '시뮬레이션 결과가 없습니다. 날짜 범위나 종목을 확인해주세요.'}), 400

        pv     = history_df['portfolio_value']
        years  = (len(history_df) / 252)

        # 총 납입금
        total_invested = initial + monthly * years * 12
        end_value      = float(pv.iloc[-1])

        # 세금 적용: 최종 청산세
        if tax_enabled and bt_tax_engine:
            from modules.tax.base_tax import TaxEngine as _TE
            if account_type == 'ISA':
                end_value = bt_tax_engine.after_tax_withdrawal(
                    end_value, 'ISA', total_invested)
            elif account_type in ('연금저축', 'IRP'):
                end_value = bt_tax_engine.after_tax_withdrawal(
                    end_value, account_type, total_invested,
                    age=user_settings.get('age', 40))
            else:
                # 위탁: 미실현 차익 최종 청산세 (손익통산 적용)
                gain = end_value - total_invested
                if gain > 0:
                    kr_foreign_gains = 0.0
                    us_direct_gains  = 0.0
                    for t, w in weights.items():
                        t_gain = gain * w  # 비중별 미실현 차익 근사
                        asset_type = bt_tax_engine.classify_asset(t)
                        if asset_type == 'KR_FOREIGN':
                            kr_foreign_gains += t_gain
                        elif asset_type == 'US_DIRECT':
                            us_direct_gains += t_gain
                    total_tax = 0.0
                    if kr_foreign_gains > 0:
                        total_tax += kr_foreign_gains * 0.154
                    if us_direct_gains > 0:
                        total_tax += max(0.0, us_direct_gains - 2_500_000) * 0.22
                    end_value -= total_tax
        total_return   = (end_value / total_invested - 1) if total_invested > 0 else 0

        # CAGR
        cagr = (end_value / total_invested) ** (1 / years) - 1 if years > 0 and total_invested > 0 else 0

        # MDD
        cummax = pv.cummax()
        dd     = (pv - cummax) / cummax
        mdd    = float(dd.min())

        # Sharpe
        daily_ret = pv.pct_change().dropna()
        sharpe    = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0

        # 총 배당금
        total_dividend = float(history_df['dividend_income'].sum()) if 'dividend_income' in history_df.columns else 0

        # history 직렬화 (매 거래일 → 주 1회 샘플링으로 경량화)
        h = history_df.copy()
        h['drawdown'] = (pv - cummax) / cummax
        h['total_invested'] = initial + monthly * np.arange(len(h)) / 21  # 월 근사

        step    = max(1, len(h) // 500)
        h_sampled = h.iloc[::step]

        history_out = [
            {
                'date':            str(row['date'])[:10],
                'portfolio_value': round(float(row['portfolio_value'])),
                'total_invested':  round(float(row['total_invested'])),
                'drawdown':        round(float(row['drawdown']), 4),
            }
            for _, row in h_sampled.iterrows()
        ]

        # 연간 수익률
        h2 = history_df.copy()
        import pandas as _pd; h2['year'] = _pd.to_datetime(h2['date']).dt.year
        annual_returns = []
        for yr, grp in h2.groupby('year'):
            s = float(grp['portfolio_value'].iloc[0])
            e = float(grp['portfolio_value'].iloc[-1])
            if s > 0:
                annual_returns.append({'year': int(yr), 'return': round((e / s - 1), 4)})

        return jsonify({
            'tax_enabled':  tax_enabled,
            'account_type': account_type if tax_enabled else None,
            'metrics': {
                'end_value':       round(end_value),
                'total_invested':  round(total_invested),
                'total_return':    round(total_return, 4),
                'cagr':            round(cagr, 4),
                'mdd':             round(mdd, 4),
                'sharpe':          round(sharpe, 2),
                'total_dividend':  round(total_dividend),
                'years':           round(years, 1),
            },
            'history':        history_out,
            'annual_returns': annual_returns,
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# -----------------------------------------------
# 종목 상세 페이지
# -----------------------------------------------

@app.route('/symbol/<code>')
def symbol_page(code):
    return render_template('symbol.html', code=code.upper())


@app.route('/api/symbol/<code>')
def symbol_api(code):
    try:
        data = portfolio_engine.loader.get_symbol_data(code.upper())
        return jsonify(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/assets')
def assets():
    if not session.get('user_id'):
        return jsonify([])
    groups = get_groups(session['user_id'])
    if not groups:
        return jsonify([])
    total_target = sum(g['target_pct'] for g in groups) or 100
    return jsonify([
        {
            "name":  g['name'],
            "color": g['color'],
            "pct":   g['target_pct'] / total_target,
        }
        for g in groups if g['target_pct'] > 0
    ])


# -----------------------------------------------

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()   # Windows 필수
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)