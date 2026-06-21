from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
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
    get_holdings, upsert_holding, delete_holding, set_manual_price,
    init_holdings_db, get_settings, save_settings,
    init_portfolios_db, get_portfolios, get_portfolio, upsert_portfolio, delete_portfolio,
    get_home_widgets, save_home_widgets,
    get_calendar_config, save_calendar_config,
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
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')
import datetime as _dt_mod
app.config['PERMANENT_SESSION_LIFETIME'] = _dt_mod.timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'


@app.after_request
def _no_cache_html(resp):
    """동적 HTML은 브라우저가 매번 재검증하도록 한다.

    캐시 헤더가 없으면 브라우저가 휴리스틱 캐싱으로 옛 HTML을 재사용해
    배포 후에도 변경이 안 보이는 문제가 생긴다(시크릿 창에서만 최신으로 보임).
    static 자산은 `?v=` 버전 쿼리로 캐시 버스팅하므로 건드리지 않는다.
    응답이 이미 Cache-Control을 지정했으면(공유 이미지 등) 존중한다.
    """
    ctype = resp.headers.get('Content-Type', '')
    if ctype.startswith('text/html') and 'Cache-Control' not in resp.headers:
        resp.headers['Cache-Control'] = 'no-cache, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    return resp

INDEX_DB_PATH  = Path(__file__).parent / "data" / "meta" / "index_master.db"
PRICE_DB_PATH  = Path(__file__).parent / "data" / "price_cache" / "price_daily.db"
SHARE_IMG_DIR  = Path(__file__).parent / "share_images"
SHARE_IMG_DIR.mkdir(exist_ok=True)

from modules.alerts import alert_store
init_holdings_db()
init_portfolios_db()
alert_store.init_alerts_db()
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
    ua = request.headers.get('User-Agent', '')
    import re
    if re.search(r'KAKAOTALK|Instagram|FBAN|FBAV|FB_IAB|Line/|everytimeapp|DaumApps|TwitterAndroid|Pinterest|Snapchat|Threads|TikTok', ua, re.I):
        return '''<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>외부 브라우저에서 열어주세요</title>
<style>body{font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#F0F4F8;padding:24px;text-align:center}
.card{background:white;border-radius:16px;padding:32px 24px;max-width:360px;box-shadow:0 4px 24px rgba(0,0,0,0.08)}
h2{font-size:1.1rem;margin-bottom:12px;color:#1A2332}
p{font-size:0.88rem;color:#546E7A;line-height:1.6;margin-bottom:20px}
.btn{display:inline-block;background:#1976D2;color:white;padding:10px 24px;border-radius:10px;font-size:0.9rem;font-weight:700;text-decoration:none;cursor:pointer;border:none;font-family:inherit}
</style></head><body>
<div class="card">
  <h2>⚠️ 카카오톡 내부 브라우저</h2>
  <p>Google 로그인은 카카오톡 내부 브라우저에서 차단됩니다.<br><br>
  아래 버튼을 눌러 <strong>외부 브라우저(크롬/사파리)</strong>로 열어주세요.</p>
  <button class="btn" onclick="location.href='kakaotalk://web/openExternal?url='+encodeURIComponent('https://moneymilestone.duckdns.org')">외부 브라우저로 열기</button>
</div>
</body></html>''', 200
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route('/auth/google/callback')
def google_callback():
    try:
        token = google.authorize_access_token()
    except Exception:
        # state mismatch (브라우저 전환/뒤로가기 등) → 재시도
        return redirect(url_for('google_login'))
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


def _hide_amounts_for_user(user_id):
    return bool(get_settings(user_id).get("hide_amounts", True))


def _get_current_asset_prices(codes):
    """Return latest asset prices in KRW for holdings/home views."""
    from pathlib import Path as _P
    import sqlite3 as _sq
    import yfinance as _yf
    from modules.krx.krx_client import KRXClient as _KRXC

    codes = list({c for c in codes if c})
    prices = {}
    if not codes:
        return prices

    try:
        idx_db = _P(__file__).parent / 'data' / 'meta' / 'index_master.db'
        ic = _sq.connect(str(idx_db))
        row = ic.execute("SELECT close FROM index_daily WHERE code='USD/KRW' ORDER BY date DESC LIMIT 1").fetchone()
        ic.close()
        usdkrw = float(row[0]) if row else 1300.0
    except Exception:
        usdkrw = 1300.0

    kr_codes = [c for c in codes if c != 'KRX_GOLD' and portfolio_engine.loader.is_kr_etf(c)]
    us_codes = [c for c in codes if c != 'KRX_GOLD' and not portfolio_engine.loader.is_kr_etf(c)]

    if kr_codes:
        try:
            krx = _KRXC(debug=False)
            prices.update(krx.get_current_prices_kr(kr_codes))
        except Exception:
            pass
        for code in kr_codes:
            if prices.get(code, 0) == 0:
                try:
                    hist = _yf.Ticker(f"{code}.KS").history(period="2d")
                    if not hist.empty:
                        prices[code] = float(hist["Close"].iloc[-1])
                except Exception:
                    prices[code] = 0

    for code in us_codes:
        try:
            hist = _yf.Ticker(code).history(period="2d")
            prices[code] = float(hist["Close"].iloc[-1]) * usdkrw if not hist.empty else 0
        except Exception:
            prices[code] = 0

    if 'KRX_GOLD' in codes:
        try:
            idx_db = _P(__file__).parent / 'data' / 'meta' / 'index_master.db'
            ic = _sq.connect(str(idx_db))
            row = ic.execute("SELECT close FROM index_daily WHERE code='KRX_GOLD' ORDER BY date DESC LIMIT 1").fetchone()
            ic.close()
            prices['KRX_GOLD'] = round(float(row[0])) if row else 0
        except Exception:
            prices['KRX_GOLD'] = 0

    return prices


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

@app.route('/simple')
def simple_tools():
    return render_template('simple.html')

@app.route('/tax-switch')
def tax_switch():
    return render_template('tax_switch.html')

@app.route('/backtest')
def backtest():
    return render_template('backtest.html')

@app.route('/risk-return')
def risk_return_page():
    return render_template('risk_return.html')

@app.route('/macro')
def macro_page():
    return render_template('macro.html')

@app.route('/calendar')
def calendar_page():
    return render_template('calendar.html')

@app.route('/myportfolios')
def myportfolios():
    return render_template('myportfolios.html')

@app.route('/myportfolios/<int:pid>')
def myportfolio_detail(pid):
    return render_template('portfolio_detail.html', pid=pid)

@app.route('/myassets')
def myassets():
    return render_template('myassets.html')

@app.route('/tax-settings')
def settings():
    # 세금 설정은 /settings 에 편입됨 — 옛 링크·북마크 호환 리다이렉트.
    return redirect('/settings')

@app.route('/settings')
def settings_page():
    return render_template('settings.html')

@app.route('/alerts')
def alerts_page():
    uid = session.get('user_id')
    symbols = []
    if uid:
        groups, names = _calendar_grouped(uid)
        seen = set()
        for g in ('holdings', 'portfolios', 'watchlist'):
            for c in groups.get(g, []):
                if c not in seen:
                    seen.add(c)
                    symbols.append({'code': c, 'name': names.get(c, c)})
    return render_template('alerts.html', symbols=symbols)

# -----------------------------------------------
# API - 검색
# -----------------------------------------------

def _search_badge_cat(badge):
    if badge == 'KR ETF': return 'kr_etf'
    if badge in ('KOSPI', 'KOSDAQ', 'KRX'): return 'kr_stock'
    if badge == 'US ETF': return 'us_etf'
    if badge in ('NASDAQ', 'NYSE'): return 'us_stock'
    if badge == 'CRYPTO': return 'crypto'
    return ''


def _search_attach_prices(items):
    """주어진 종목 리스트에 최근 종가·등락률 부착(price_daily 배치)."""
    if not items:
        return
    try:
        import sqlite3 as _sq
        if not PRICE_DB_PATH.exists():
            return
        pconn = _sq.connect(str(PRICE_DB_PATH))
        codes = [r['code'] for r in items]
        ph = ','.join('?' * len(codes))
        cur_rows = pconn.execute(f"""
            SELECT p.code, p.close FROM price_daily p
            INNER JOIN (SELECT code, MAX(date) as mx FROM price_daily
                WHERE code IN ({ph}) AND close IS NOT NULL GROUP BY code) m
            ON p.code=m.code AND p.date=m.mx
        """, codes).fetchall()
        prev_rows = pconn.execute(f"""
            SELECT p.code, p.close FROM price_daily p
            INNER JOIN (SELECT p2.code, MAX(p2.date) as mx2 FROM price_daily p2
                INNER JOIN (SELECT code, MAX(date) as mx FROM price_daily
                    WHERE code IN ({ph}) AND close IS NOT NULL GROUP BY code) m
                ON p2.code=m.code AND p2.date < m.mx AND p2.close IS NOT NULL
                GROUP BY p2.code) prev ON p.code=prev.code AND p.date=prev.mx2
        """, codes).fetchall()
        pconn.close()
        price_map = {r[0]: r[1] for r in cur_rows}
        prev_map  = {r[0]: r[1] for r in prev_rows}
        for res in items:
            cur = price_map.get(res['code']); prv = prev_map.get(res['code'])
            res['price'] = round(cur, 2) if cur else None
            res['change_pct'] = round((cur - prv) / prv * 100, 2) if cur and prv else None
            res['currency'] = 'KRW' if res.get('country') == 'KR' else 'USD'
    except Exception as e:
        print(f"[search price] {e}")


@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    paged = request.args.get('page') is not None
    if not q:
        return jsonify({'items': [], 'total': 0, 'page': 1, 'per': 18}) if paged else jsonify([])
    try:
        try:
            _limit = max(1, min(int(request.args.get('limit', 20)), 500))
        except (TypeError, ValueError):
            _limit = 20
        cats = [c for c in request.args.get('cats', '').split(',') if c]
        results = []

        # KRX 금현물 특별 처리
        if any(k in q.upper() for k in ['금', 'GOLD', 'KRX', '현물']):
            results.append({
                'code': 'KRX_GOLD', 'name': '금 현물 (KRX, 1g)',
                'badge': 'KRX', 'subtitle': 'KRX 금시장 현물',
                'country': 'KR', 'is_etf': False,
            })

        # paged면 전체 매칭(제한 없음 — 서버서 페이지 슬라이스라 페이로드 무관), 아니면 _limit.
        uni = 10_000_000 if paged else _limit
        df = info_engine.search_fuzzy(q, limit=uni)
        if not df.empty:
            for _, row in df.iterrows():
                if row.get('is_etf'):
                    badge = 'KR ETF' if row.get('country') == 'KR' else 'US ETF'
                else:
                    badge = row.get('market') or row.get('country') or ''
                subtitle = (row.get('index_name') or row.get('category') or row.get('issuer') or '')
                results.append({
                    'code':     row['code'],
                    'name':     row['name'],
                    'badge':    badge,
                    'subtitle': '' if str(subtitle) == 'nan' else str(subtitle),
                    'country':  row.get('country', ''),
                    'is_etf':   bool(row.get('is_etf', 0)),
                })

        # 카테고리 다중필터(서버) — 페이지네이션과 일관
        if cats:
            results = [r for r in results if _search_badge_cat(r['badge']) in cats]

        if paged:
            try:
                per = max(1, min(int(request.args.get('per', 18)), 50))
                page = max(1, int(request.args.get('page', 1)))
            except (TypeError, ValueError):
                per, page = 18, 1
            total = len(results)
            page_items = results[(page - 1) * per: page * per]
            _search_attach_prices(page_items)   # 보이는 페이지만 가격 조회
            return jsonify({'items': page_items, 'total': total, 'page': page, 'per': per})

        _search_attach_prices(results)
        return jsonify(results[:_limit])
    except Exception as e:
        print(f"[search] 오류: {e}")
        return jsonify({'items': [], 'total': 0, 'page': 1, 'per': 18}) if request.args.get('page') is not None else jsonify([])

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
        from calculator_logic import run_calculator_logic
        result = run_calculator_logic(body)
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


@app.route('/api/tax-switch/run', methods=['POST'])
def tax_switch_run():
    """세금 전환 계산기 동기 실행 (로컬 검증용 — 프론트는 submit 사용)."""
    try:
        from tax_switch_logic import run_tax_switch_logic
        return jsonify(run_tax_switch_logic(request.get_json()))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/tax-switch/submit', methods=['POST'])
def tax_switch_submit():
    from tasks import run_tax_switch_task, add_to_queue
    payload = request.get_json()
    task    = run_tax_switch_task.delay(payload)
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
            import json as _j
            err_str = result.get('error', '알 수 없는 오류')
            err_data = None
            try:
                err_data = _j.loads(err_str)
            except Exception:
                pass
            return jsonify({'status': 'FAILURE', 'error': err_str, 'error_data': err_data})
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
# API - 포트폴리오 히스토리 (실제 역산)
# -----------------------------------------------

def _compute_portfolio_history(valid):
    """valid = [(code, qty)] (qty>0). 평가금액 추이 dict 반환 (hide_amounts 미포함)."""
    import sqlite3 as _sq
    from pathlib import Path as _P
    from datetime import datetime, timedelta
    import re

    if not valid:
        return {"empty": True, "labels": [], "values": []}

    # USD/KRW 환율
    try:
        idx_db = _P(__file__).parent / 'data' / 'meta' / 'index_master.db'
        ic = _sq.connect(str(idx_db))
        row = ic.execute("SELECT close FROM index_daily WHERE code='USD/KRW' ORDER BY date DESC LIMIT 1").fetchone()
        ic.close()
        usdkrw = float(row[0]) if row else 1300.0
    except Exception:
        usdkrw = 1300.0

    kr_pattern = re.compile(r'^\d{6}$')
    def is_kr(code):
        return bool(kr_pattern.match(code)) or code == 'KRX_GOLD'

    price_db = _P(__file__).parent / 'data' / 'price_cache' / 'price_daily.db'
    idx_db   = _P(__file__).parent / 'data' / 'meta' / 'index_master.db'
    cutoff   = (datetime.now() - timedelta(days=3*365)).strftime('%Y-%m-%d')

    # 종목별 날짜→종가 맵
    price_map = {}
    codes = list({code for code, _ in valid})

    pc = _sq.connect(str(price_db))
    for code in codes:
        if code == 'KRX_GOLD':
            # index_master.db에서 조회
            try:
                ic = _sq.connect(str(idx_db))
                rows = ic.execute(
                    "SELECT date, close FROM index_daily WHERE code='KRX_GOLD' AND date>=? ORDER BY date",
                    (cutoff,)
                ).fetchall()
                ic.close()
                if rows:
                    price_map[code] = {r[0]: r[1] for r in rows}
            except Exception:
                pass
            continue

        rows = pc.execute(
            "SELECT date, close FROM price_daily WHERE code=? AND date>=? ORDER BY date",
            (code, cutoff)
        ).fetchall()
        if rows:
            price_map[code] = {r[0]: r[1] for r in rows}
        elif is_kr(code):
            # price_daily.db에 없는 KR 종목 → yfinance .KS로 fetch 후 저장
            try:
                import yfinance as _yf
                ticker = _yf.Ticker(f"{code}.KS")
                hist = ticker.history(period="3y", interval="1d", auto_adjust=False, actions=True)
                if not hist.empty:
                    hist.index = hist.index.tz_localize(None) if hist.index.tz else hist.index
                    rows_to_insert = [
                        (code, d.strftime('%Y-%m-%d'), row['Open'], row['High'], row['Low'], row['Close'], row['Volume'])
                        for d, row in hist.iterrows()
                    ]
                    pc.executemany(
                        "INSERT OR REPLACE INTO price_daily (code,date,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
                        rows_to_insert
                    )
                    # 배당 데이터도 함께 저장
                    if 'Dividends' in hist.columns:
                        div_rows = [
                            (code, d.strftime('%Y-%m-%d'), float(row['Dividends']), 1.0)
                            for d, row in hist.iterrows() if row['Dividends'] > 0
                        ]
                        if div_rows:
                            pc.executemany(
                                "INSERT OR REPLACE INTO corporate_actions (code,date,dividend,split) VALUES (?,?,?,?)",
                                div_rows
                            )
                    pc.commit()
                    price_map[code] = {r[1]: r[5] for r in rows_to_insert if r[1] >= cutoff}
            except Exception:
                pass
    pc.close()

    if not price_map:
        return {"empty": True, "labels": [], "values": []}

    # 전체 날짜 합집합 정렬
    all_dates = sorted(set().union(*[set(v.keys()) for v in price_map.values()]))

    labels, values = [], []
    last_prices = {}
    for date in all_dates:
        total = 0.0
        ok = False
        for code, qty in valid:
            if code not in price_map:
                continue
            px = price_map[code].get(date) or last_prices.get(code)
            if px is None:
                continue
            last_prices[code] = px
            total += qty * (px if is_kr(code) else px * usdkrw)
            ok = True
        if ok and total > 0:
            labels.append(date)
            values.append(round(total))

    if not values:
        return {"empty": True, "labels": [], "values": []}

    current_prices = _get_current_asset_prices(codes)
    current_total = sum(qty * current_prices.get(code, 0) for code, qty in valid)
    if current_total > 0:
        today = datetime.now().strftime('%Y-%m-%d')
        if labels and labels[-1] == today:
            values[-1] = round(current_total)
        else:
            labels.append(today)
            values.append(round(current_total))

    current = values[-1]
    change = round((values[-1] / values[0] - 1) * 100, 2) if values[0] else 0
    return {
        "labels": labels,
        "values": values,
        "current": current,
        "change": change,
    }


@app.route('/api/portfolio/history')
def portfolio_history():
    uid = session.get('user_id')
    if not uid:
        return jsonify({"empty": True, "labels": [], "values": [], "hide_amounts": True})
    holdings = get_holdings(uid)
    valid = [(h['code'], float(h['quantity'])) for h in holdings if h.get('quantity') and h['quantity'] > 0]
    result = _compute_portfolio_history(valid)
    result["hide_amounts"] = _hide_amounts_for_user(uid)
    return jsonify(result)


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
# API - 홈 화면 위젯(관심목록) 설정 + 시세
# -----------------------------------------------

# 비로그인/미설정 기본값 — 현재 시장지수 6종
DEFAULT_HOME_WIDGETS = [
    {"key": "w_market", "name": "시장 지수", "items": [
        {"code": "^GSPC",    "name": "S&P 500"},
        {"code": "^IXIC",    "name": "NASDAQ"},
        {"code": "^KS11",    "name": "코스피"},
        {"code": "GC=F",     "name": "금 (국제)"},
        {"code": "KRX_GOLD", "name": "금 (KRX)"},
        {"code": "KRW=X",    "name": "환율 (USD/KRW)"},
    ]},
]


def _wl_recent_closes(code):
    """위젯용 경량 종가 시계열(오래된→최신) + 통화. 전체 history 미로드.

    - 지수/선물/FX/금현물: index_master(index_ohlc 우선, 없으면 index_daily) 최근 25행 — 로컬 즉시.
    - 주식/ETF/크립토: get_price 최근 45일창 — price_daily 로컬 우선, 갭만 API.
    """
    from datetime import datetime as _dt2, timedelta as _td2
    code   = str(code).upper()
    loader = portfolio_engine.loader
    _FUT   = {'GC=F', 'SI=F', 'CL=F', 'NG=F', 'HG=F', 'KRW=X'}
    is_index = code.startswith('^') or code in _FUT or code == 'KRX_GOLD'

    if is_index:
        conn = loader.index_conn
        if conn is None:
            return [], "USD"
        try:  # index_ohlc 미존재(배포 직후 등) → index_daily 폴백
            rows = conn.execute(
                "SELECT close FROM index_ohlc WHERE code=? ORDER BY date DESC LIMIT 25", (code,)
            ).fetchall()
        except Exception:
            rows = []
        if not rows:
            db_code = 'USD/KRW' if code == 'KRW=X' else code
            rows = conn.execute(
                "SELECT close FROM index_daily WHERE code=? ORDER BY date DESC LIMIT 25", (db_code,)
            ).fetchall()
        currency = "KRW" if code in ('^KS11', 'KRW=X', 'KRX_GOLD') else "USD"
        if rows:
            return [float(r[0]) for r in rows][::-1], currency
        # 로컬 미보유 지수(예: ^KS11은 index_daily에 KS200만 있어 없음) → yfinance 경량 fetch
        if code != 'KRX_GOLD':
            try:
                import yfinance as _yf
                from datetime import datetime as _d3, timedelta as _t3
                _s = (_d3.today() - _t3(days=45)).strftime("%Y-%m-%d")
                df = _yf.download(code, start=_s, progress=False, auto_adjust=False, threads=False)
                if not df.empty:
                    cl = df["Close"]
                    if hasattr(cl, "columns"):
                        cl = cl.iloc[:, 0]
                    return [float(x) for x in cl.dropna().tolist()], currency
            except Exception:
                pass
        return [], currency

    today = _dt2.today().strftime("%Y-%m-%d")
    start = (_dt2.today() - _td2(days=45)).strftime("%Y-%m-%d")
    df = loader.get_price(code, start, today, apply_fx=False)
    if df is None or df.empty:
        return [], "USD"
    closes   = [float(x) for x in df["close"].tolist()]
    currency = "KRW" if loader.is_kr_etf(code) else "USD"
    return closes, currency


def _watchlist_quote(code):
    """단일 종목 경량 시세 — 최근창 종가 기반 + Redis 캐시. 실패 시 None."""
    code = str(code).upper()
    svc = market_quote_service
    key = f"mq:wl:{code}"
    if getattr(svc, '_redis_ok', False):
        cached = svc._get(key)
        if cached:
            return cached
    try:
        closes, currency = _wl_recent_closes(code)
    except Exception:
        return None
    if not closes:
        return None
    cur  = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else None
    change = round((cur - prev) / prev * 100, 2) if prev else 0.0
    is_krw = currency == "KRW"
    prefix = "₩" if is_krw else "$"
    val    = f"{prefix}{cur:,.0f}" if (is_krw or cur >= 1000) else f"{prefix}{cur:,.2f}"
    quote = {
        "code":   code,
        "name":   code,
        "value":  val,
        "change": f"{'+' if change >= 0 else ''}{change}%",
        "up":     change >= 0,
        "spark":  [round(c, 2) for c in closes[-20:]],
        "currency": currency,
    }
    if getattr(svc, '_redis_ok', False):
        svc._set(key, quote, 15 * 60)  # 15분 고정 = 새로고침 floor
    return quote


def _clean_home_widgets(widgets):
    """저장용 위젯 검증·정제. (cleaned, error) 반환."""
    if not isinstance(widgets, list) or not (1 <= len(widgets) <= 10):
        return None, '위젯은 1~10개여야 합니다.'
    cleaned = []
    for w in widgets:
        if not isinstance(w, dict):
            return None, '잘못된 위젯 형식입니다.'
        name = str(w.get('name', '')).strip()
        if not name or len(name) > 20:
            return None, '위젯 이름은 1~20자로 입력해주세요.'
        items = w.get('items')
        if not isinstance(items, list) or not (1 <= len(items) <= 30):
            return None, f'"{name}"의 종목은 1~30개여야 합니다.'
        clean_items = []
        for it in items:
            if not isinstance(it, dict) or not it.get('code'):
                return None, '잘못된 종목 형식입니다.'
            clean_items.append({
                'code': str(it['code']).upper(),
                'name': str(it.get('name', it['code']))[:40],
            })
        cleaned.append({
            'key':   str(w.get('key', ''))[:40] or f'w_{len(cleaned)}',
            'name':  name,
            'items': clean_items,
        })
    return cleaned, None


@app.route('/api/home-config')
def home_config_get():
    if session.get('user_id'):
        w = get_home_widgets(session['user_id'])
        if w:
            return jsonify({"widgets": w, "logged_in": True})
    return jsonify({"widgets": DEFAULT_HOME_WIDGETS,
                    "logged_in": bool(session.get('user_id'))})


@app.route('/api/home-config', methods=['POST'])
def home_config_save():
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    body = request.get_json(silent=True) or {}
    cleaned, err = _clean_home_widgets(body.get('widgets'))
    if err:
        return jsonify({'error': err}), 400
    save_home_widgets(session['user_id'], cleaned)
    return jsonify({'ok': True})


def _portfolio_quote(uid, pid):
    """저장 포트폴리오 → 일일 리밸 정규화 지수 기반 위젯 시세. 실패 시 None."""
    try:
        pf = get_portfolio(uid, int(pid))
    except (TypeError, ValueError):
        return None
    if not pf:
        return None
    from modules.alerts import alert_runner
    closes = alert_runner.compute_portfolio_index(portfolio_engine.loader, pf.get('tickers') or [])
    if len(closes) < 2:
        return None
    cur, prev = closes[-1], closes[-2]
    change = round((cur - prev) / prev * 100, 2) if prev else 0.0
    return {
        "code": f"PF:{pid}", "name": pf.get('name', '포트폴리오'),
        "value": f"{cur:,.1f}",
        "change": f"{'+' if change >= 0 else ''}{change}%",
        "up": change >= 0,
        "spark": [round(c, 2) for c in closes[-20:]],
        "currency": "IDX", "is_portfolio": True,
    }


@app.route('/api/attribution/window', methods=['POST'])
def attribution_window():
    """백테 사용자 지정 구간 — 종목별 기여 + 지분(다이버징). 비로그인 허용(가격 계산)."""
    body = request.get_json(silent=True) or {}
    tk = body.get('tickers') or []
    codes, weights = [], {}
    for t in tk:
        c = str(t.get('code', '')).upper()
        if c:
            codes.append(c)
            weights[c] = float(t.get('weight') or 0)
    start, end = body.get('start'), body.get('end')
    if len(codes) < 2 or not start or not end:
        return jsonify({'ok': False, 'reason': 'need 2+ tickers + range'})
    from modules import attribution
    res = attribution.analyze_window(portfolio_engine.loader, codes, weights, start, end)
    if not res:
        return jsonify({'ok': False, 'reason': 'no_data'})
    names = _resolve_names(codes)
    for r in res['rows']:
        r['name'] = names.get(r['code'], r['code'])
    return jsonify({'ok': True, 'attribution': res})


@app.route('/api/attribution/capture', methods=['POST'])
def attribution_capture():
    """투자계산기 — 비중 무관 상승/하락 포착률(방어력). 비로그인 허용."""
    body = request.get_json(silent=True) or {}
    tk = body.get('tickers') or []
    codes, weights = [], {}
    for t in tk:
        c = str(t.get('code', '')).upper()
        if c:
            codes.append(c)
            weights[c] = float(t.get('weight') or 0)
    if len(codes) < 2:
        return jsonify({'ok': False, 'reason': 'need 2+ tickers'})
    start, end = body.get('start'), body.get('end')
    from modules import attribution
    res = attribution.analyze_capture(portfolio_engine.loader, codes, weights,
                                      start=start, end=end)
    if not res:
        return jsonify({'ok': False, 'reason': 'no_data'})
    names = _resolve_names(codes)
    res['names'] = {c: names.get(c, c) for c in codes}
    return jsonify({'ok': True, 'attribution': res})


@app.route('/api/myassets/attribution')
def myassets_attribution():
    """내 자산 — 상승 견인/하락 방어 종목 요약(보유 비중 기준, 최근 6년)."""
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': '로그인 필요'}), 401
    from datetime import datetime as _dt, timedelta as _td
    holdings = get_holdings(uid)
    today = _dt.today().strftime('%Y-%m-%d')
    start = (_dt.today() - _td(days=20)).strftime('%Y-%m-%d')
    weights, total = {}, 0.0
    for h in holdings:
        qty = h.get('quantity') or 0
        if qty <= 0:
            continue
        code = str(h.get('code', '')).upper()
        mp = h.get('manual_price')
        if mp is not None:
            price = mp
        else:
            try:
                df = portfolio_engine.loader.get_price(code, start, today, apply_fx=True)
                price = float(df['close'].iloc[-1]) if df is not None and not df.empty else 0.0
            except Exception:
                price = 0.0
        val = qty * (price or 0)
        if val > 0:
            weights[code] = weights.get(code, 0.0) + val
            total += val
    if total <= 0 or len(weights) < 2:
        return jsonify({'ok': False, 'reason': 'insufficient'})
    from modules import attribution
    cap = attribution.analyze_capture(portfolio_engine.loader, list(weights.keys()), weights, years=6)
    if not cap or not cap.get('assets'):
        return jsonify({'ok': False, 'reason': 'no_data'})
    names = _resolve_names(list(weights.keys()))
    A = cap['assets']
    # 견인 = 상승장 기여(비중×수익) 최대 / 방어 = 하락 포착률 최소(덜 빠짐)
    driver_code = max(A, key=lambda c: A[c]['contrib_up'])
    defender_code = min(A, key=lambda c: (A[c]['down_capture']
                                          if A[c]['down_capture'] is not None else 9e9))
    out = {
        'period': cap['period'], 'n_up': cap['n_up'], 'n_down': cap['n_down'],
        'up_driver': {'code': driver_code, 'name': names.get(driver_code, driver_code),
                      'contrib': A[driver_code]['contrib_up']},
        'down_defender': {'code': defender_code, 'name': names.get(defender_code, defender_code),
                          'down_capture': A[defender_code]['down_capture'],
                          'down_ret': A[defender_code]['down_ret']},
    }
    return jsonify({'ok': True, 'attribution': out})


@app.route('/api/home-config/add-portfolio', methods=['POST'])
def home_add_portfolio():
    """저장 포트폴리오를 홈 위젯(즐겨찾기)에 추종 항목으로 추가."""
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': '로그인 필요'}), 401
    body = request.get_json(silent=True) or {}
    pf = get_portfolio(uid, body.get('id'))
    if not pf:
        return jsonify({'error': '포트폴리오를 찾을 수 없어요.'}), 404
    item = {'code': f"PF:{pf['id']}", 'name': pf['name'], 'type': 'portfolio'}
    import copy
    widgets = get_home_widgets(uid) or copy.deepcopy(DEFAULT_HOME_WIDGETS)
    # "내 포트폴리오" 위젯 찾거나 생성
    target = next((w for w in widgets if w.get('key') == 'w_portfolios'), None)
    if target is None:
        target = {'key': 'w_portfolios', 'name': '내 포트폴리오', 'items': []}
        widgets.append(target)
    if any(str(i.get('code')) == item['code'] for i in target['items']):
        return jsonify({'ok': True, 'already': True})
    if len(target['items']) >= 30:
        return jsonify({'error': '위젯당 최대 30개까지 추가할 수 있어요.'}), 400
    target['items'].append(item)
    cleaned, err = _clean_home_widgets(widgets)
    if err:
        return jsonify({'error': err}), 400
    save_home_widgets(uid, cleaned)
    return jsonify({'ok': True})


@app.route('/api/watchlist/quotes')
def watchlist_quotes():
    codes = [c.strip() for c in request.args.get('codes', '').split(',') if c.strip()][:60]
    if not codes:
        return jsonify([])
    # 저장 포트폴리오 토큰(PF:<id>)은 사용자별 → 공유 캐시 우회, 따로 처리.
    uid = session.get('user_id')
    pf_ids = {}   # code -> quote
    sym_codes = []
    for c in codes:
        if c.upper().startswith('PF:'):
            if uid:
                pf_ids[c] = _portfolio_quote(uid, c.split(':', 1)[1])
        else:
            sym_codes.append(c)
    # P2-2: 코드별 _watchlist_quote가 순차였음(콜드캐시 = N×네트워크 지연).
    # I/O-bound라 ThreadPool 병렬이 1코어에서도 이득. ex.map = 입력 순서 보존, 결과 동일.
    sym_q = {}
    if sym_codes:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(8, len(sym_codes))) as ex:
            for c, q in zip(sym_codes, ex.map(_watchlist_quote, sym_codes)):
                sym_q[c] = q
    # 입력 순서 보존
    out = []
    for c in codes:
        q = pf_ids.get(c) if c.upper().startswith('PF:') else sym_q.get(c)
        if q:
            out.append(q)
    return jsonify(out)


# -----------------------------------------------
# API - 알림 (룰 + 수신함)
# -----------------------------------------------

_ALERT_DIRECTIONS = {
    'daily_pct':    {'up', 'down', 'both'},
    'target_price': {'above', 'below'},
}


def _validate_alert_payload(body):
    """룰 생성/수정 입력 검증. (clean_dict, error) 반환."""
    rt = str(body.get('rule_type', '')).strip()
    if rt not in alert_store.VALID_TYPES:
        return None, '알 수 없는 알림 종류입니다.'

    out = {'rule_type': rt}
    try:
        cooldown = int(body.get('cooldown_h', 24))
    except (TypeError, ValueError):
        return None, '쿨다운 값이 올바르지 않습니다.'
    out['cooldown_h'] = max(1, min(cooldown, 24 * 30))

    if rt == 'rebalance_band':
        out['scope'] = 'portfolio'
        out['code'] = None
        try:
            band = float(body.get('threshold'))
        except (TypeError, ValueError):
            return None, '밴드 % 값을 입력해주세요.'
        if not (0 < band <= 100):
            return None, '밴드 %는 0 초과 100 이하여야 합니다.'
        out['threshold'] = band
        return out, None

    # 저장 포트폴리오 수익 룰 (portfolio_id 지정, 전체 포폴 지수 기반)
    if body.get('portfolio_id') is not None:
        try:
            pid = int(body.get('portfolio_id'))
        except (TypeError, ValueError):
            return None, '포트폴리오가 올바르지 않습니다.'
        if rt not in ('daily_pct', 'new_high', 'new_low'):
            return None, '포트폴리오 알림은 일간 수익률·신고가·신저가만 지원해요.'
        out['scope'] = 'portfolio'
        out['portfolio_id'] = pid
        out['code'] = None
        if rt in ('new_high', 'new_low'):
            win = str(body.get('window', '52w'))
            if win not in ('52w', 'all'):
                return None, '윈도우는 52w 또는 all 이어야 합니다.'
            out['window'] = win
            return out, None
        direction = str(body.get('direction', '')).strip()
        if direction not in _ALERT_DIRECTIONS['daily_pct']:
            return None, '방향 값이 올바르지 않습니다.'
        out['direction'] = direction
        try:
            thr = float(body.get('threshold'))
        except (TypeError, ValueError):
            return None, '변동률 %를 입력해주세요.'
        if not (0 < thr <= 100):
            return None, '변동률 %는 0 초과 100 이하여야 합니다.'
        out['threshold'] = thr
        return out, None

    # symbol 룰 공통
    code = str(body.get('code', '')).strip().upper()
    if not code:
        return None, '종목 코드가 필요합니다.'
    out['scope'] = 'symbol'
    out['code'] = code

    if rt in ('new_high', 'new_low'):
        win = str(body.get('window', '52w'))
        if win not in ('52w', 'all'):
            return None, '윈도우는 52w 또는 all 이어야 합니다.'
        out['window'] = win
        return out, None

    # daily_pct / target_price → direction + threshold
    direction = str(body.get('direction', '')).strip()
    if direction not in _ALERT_DIRECTIONS[rt]:
        return None, '방향 값이 올바르지 않습니다.'
    out['direction'] = direction
    try:
        thr = float(body.get('threshold'))
    except (TypeError, ValueError):
        return None, '임계값을 입력해주세요.'
    if rt == 'daily_pct':
        if not (0 < thr <= 100):
            return None, '변동률 %는 0 초과 100 이하여야 합니다.'
    else:  # target_price
        if thr <= 0:
            return None, '목표가는 0보다 커야 합니다.'
    out['threshold'] = thr
    return out, None


@app.route('/api/alerts/rules')
def alerts_rules_get():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': '로그인 필요'}), 401
    return jsonify({'rules': alert_store.get_rules(uid)})


@app.route('/api/alerts/rules', methods=['POST'])
def alerts_rules_create():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': '로그인 필요'}), 401
    clean, err = _validate_alert_payload(request.get_json(silent=True) or {})
    if err:
        return jsonify({'error': err}), 400
    # 포트폴리오 룰은 본인 소유 포폴만 (남의 id로 죽은 룰 생성 방지)
    if clean.get('portfolio_id') is not None and not get_portfolio(uid, clean['portfolio_id']):
        return jsonify({'error': '포트폴리오를 찾을 수 없어요.'}), 404
    try:
        rid = alert_store.create_rule(uid, **clean)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, 'id': rid})


@app.route('/api/alerts/rules/<int:rule_id>', methods=['PATCH'])
def alerts_rules_update(rule_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': '로그인 필요'}), 401
    body = request.get_json(silent=True) or {}
    fields = {}
    if 'enabled' in body:
        fields['enabled'] = 1 if body['enabled'] else 0
    for k in ('threshold', 'cooldown_h', 'direction', 'window'):
        if k in body:
            fields[k] = body[k]
    if not fields:
        return jsonify({'error': '변경할 값이 없습니다.'}), 400
    alert_store.update_rule(uid, rule_id, **fields)
    return jsonify({'ok': True})


@app.route('/api/alerts/rules/<int:rule_id>', methods=['DELETE'])
def alerts_rules_delete(rule_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': '로그인 필요'}), 401
    alert_store.delete_rule(uid, rule_id)
    return jsonify({'ok': True})


@app.route('/api/alerts/context')
def alerts_context():
    """알림 설정 진입점용 — 내 종목(보유/포폴/관심) 목록. 그룹 모달에서 사용."""
    uid = session.get('user_id')
    if not uid:
        return jsonify({'logged_in': False, 'holdings': [], 'portfolios': [], 'watchlist': []})
    groups, names = _calendar_grouped(uid)
    def _syms(codes):
        return [{'code': c, 'name': names.get(c, c)} for c in codes]
    portfolios = []
    try:
        for pf in get_portfolios(uid):
            syms = [{'code': str(t['code']).upper(), 'name': t.get('name', t['code'])}
                    for t in pf.get('tickers', []) if isinstance(t, dict) and t.get('code')]
            portfolios.append({'id': pf['id'], 'name': pf['name'], 'symbols': syms})
    except Exception:
        pass
    return jsonify({
        'logged_in': True,
        'holdings': _syms(groups.get('holdings', [])),
        'portfolios': portfolios,
        'watchlist': _syms(groups.get('watchlist', [])),
    })


@app.route('/api/alerts/events')
def alerts_events_get():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': '로그인 필요'}), 401
    unread = request.args.get('unread') == '1'
    try:
        limit = max(1, min(int(request.args.get('limit', 50)), 200))
    except ValueError:
        limit = 50
    return jsonify({'events': alert_store.get_events(uid, unread_only=unread, limit=limit)})


@app.route('/api/alerts/unread-count')
def alerts_unread_count():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'count': 0})
    return jsonify({'count': alert_store.unread_count(uid)})


@app.route('/api/alerts/events/<int:event_id>/read', methods=['POST'])
def alerts_event_read(event_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': '로그인 필요'}), 401
    alert_store.mark_read(uid, event_id)
    return jsonify({'ok': True})


@app.route('/api/alerts/read-all', methods=['POST'])
def alerts_read_all():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': '로그인 필요'}), 401
    alert_store.mark_all_read(uid)
    return jsonify({'ok': True})


# -----------------------------------------------
# API - 배당 목표 시나리오
# -----------------------------------------------

@app.route('/api/dividend-target/scenario', methods=['POST'])
def dividend_target_scenario():
    # celery 경로(run_dividend_task)와 동일 로직 공유 — 세금·계좌검증·절세액(P4) 포함.
    # (과거엔 여기 인라인 복제가 있었음 — 세금 미배선 stale, 2026-06-13 통일)
    try:
        from dividend_logic import run_dividend_scenario_logic
        return jsonify(run_dividend_scenario_logic(request.get_json()))
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
            apply_final_liquidation = False,  # 은퇴: 절대 일괄청산 금지 → 무청산 인계(인출단계서 과세).
        )
        acc_result = acc_analyzer.run()

        # 2. 은퇴 플래너 (축적 → 인출)
        # 인출 과세 배선 (G5-C C1): 적립 무청산 인계 → 인출하면서 과세. cost_basis=적립 총납입.
        from modules.retirement.retirement_planner import RetirementPlanner
        _cost_basis = initial_capital + monthly_contribution * accumulation_years * 12
        planner = RetirementPlanner(
            acc_result         = acc_result,
            wd_config          = {
                "portfolio_engine":   portfolio_engine,
                "tickers":            ticker_codes,
                "strategy_factory":   strategy_factory,
                "data_start":         data_start,
                "data_end":           data_end,
                "withdrawal_years":   withdrawal_years,
                "dividend_mode":      dividend_mode,
                "step_months":        6,
                "tax_engine":         ret_tax_engine,
                "account_type":       account_type if tax_enabled else "위탁",
                "user_settings":      user_settings if tax_enabled else {},
                "current_age":        int(user_settings.get("age", 40)) if tax_enabled else 40,
                "accumulation_years": accumulation_years,
                "gain_harvesting":    gain_harvesting if tax_enabled else False,
            },
            monthly_withdrawal = monthly_withdrawal,
            withdrawal_years   = withdrawal_years,
            inflation          = inflation,
            verbose            = False,
            cost_basis         = _cost_basis if tax_enabled else None,
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

    import json as _json
    import sqlite3 as _sq
    import yfinance as _yf
    from pathlib import Path as _P
    from datetime import datetime as _dt
    from modules.krx.krx_client import KRXClient as _KRXC

    codes  = list({h['code'] for h in holdings})
    prices = {}

    # ── TTL 15분 고정 = 새로고침 floor (yfinance 15분 지연과 동일, 더 자주 호출해도 같은 값) ──
    def _asset_ttl():
        return 15 * 60

    # ── Redis 캐시 helpers (market_quote_service의 Redis 재사용) ──
    _r = getattr(market_quote_service, '_redis', None)

    def _cache_get(code):
        if not _r:
            return None
        try:
            raw = _r.get(f'asset_px:{code}')
            return float(_json.loads(raw)['p']) if raw else None
        except Exception:
            return None

    def _cache_set(code, price_krw):
        if not _r:
            return
        try:
            _r.setex(f'asset_px:{code}', _asset_ttl(), _json.dumps({'p': price_krw}))
        except Exception:
            pass

    # ── USD/KRW 환율 ──────────────────────────────────────────────
    idx_db = _P(__file__).parent / 'data' / 'meta' / 'index_master.db'
    usdkrw = _cache_get('USD/KRW')
    if usdkrw is None:
        try:
            ic  = _sq.connect(str(idx_db))
            row = ic.execute("SELECT close FROM index_daily WHERE code='USD/KRW' ORDER BY date DESC LIMIT 1").fetchone()
            ic.close()
            usdkrw = float(row[0]) if row else 1300.0
        except Exception:
            usdkrw = 1300.0
        _cache_set('USD/KRW', usdkrw)

    # ── KRX_GOLD ────────────────────────────────────────────────
    if 'KRX_GOLD' in codes:
        cached = _cache_get('KRX_GOLD')
        if cached is not None:
            prices['KRX_GOLD'] = cached
        else:
            try:
                ic  = _sq.connect(str(idx_db))
                row = ic.execute("SELECT close FROM index_daily WHERE code='KRX_GOLD' ORDER BY date DESC LIMIT 1").fetchone()
                ic.close()
                prices['KRX_GOLD'] = round(float(row[0])) if row else 0
            except Exception:
                prices['KRX_GOLD'] = 0
            _cache_set('KRX_GOLD', prices['KRX_GOLD'])

    # ── KR / US 종목 분리 ────────────────────────────────────────
    kr_codes = [c for c in codes if c != 'KRX_GOLD' and portfolio_engine.loader.is_kr_etf(c)]
    us_codes = [c for c in codes if c != 'KRX_GOLD' and not portfolio_engine.loader.is_kr_etf(c)]

    # KR 종목 — 캐시 히트 우선, 미스는 KRX 배치 + yfinance 폴백
    kr_miss = []
    for code in kr_codes:
        cached = _cache_get(code)
        if cached is not None:
            prices[code] = cached
        else:
            kr_miss.append(code)

    if kr_miss:
        try:
            krx   = _KRXC(debug=False)
            kr_px = krx.get_current_prices_kr(kr_miss)
            for code, px in kr_px.items():
                if px:
                    prices[code] = px
                    _cache_set(code, px)
        except Exception:
            pass
        for code in kr_miss:
            if prices.get(code, 0) == 0:
                try:
                    hist = _yf.Ticker(f"{code}.KS").history(period="2d")
                    if not hist.empty:
                        px = float(hist["Close"].iloc[-1])
                        prices[code] = px
                        _cache_set(code, px)
                except Exception:
                    pass

    # US 종목 — 캐시 히트 우선, 미스는 yf.download 배치
    us_miss = []
    for code in us_codes:
        cached = _cache_get(code)
        if cached is not None:
            prices[code] = cached
        else:
            us_miss.append(code)

    if us_miss:
        try:
            df = _yf.download(us_miss, period="2d", progress=False, auto_adjust=True)
            close = df["Close"] if len(us_miss) > 1 else df[["Close"]].rename(columns={"Close": us_miss[0]})
            for code in us_miss:
                try:
                    px = float(close[code].dropna().iloc[-1]) * usdkrw
                    prices[code] = px
                    _cache_set(code, px)
                except Exception:
                    prices[code] = 0
        except Exception:
            for code in us_miss:
                try:
                    hist = _yf.Ticker(code).history(period="2d")
                    if not hist.empty:
                        px = float(hist["Close"].iloc[-1]) * usdkrw
                        prices[code] = px
                        _cache_set(code, px)
                except Exception:
                    prices[code] = 0

    # ── 수동 가격 override: 설정된 보유종목은 fetch 무시하고 그 값 사용(KRW) ──
    _nm = _resolve_names([h['code'] for h in holdings])
    for h in holdings:
        h['name'] = _nm.get(h['code']) or h.get('name') or h['code']
    manual_codes = []
    for h in holdings:
        mp = h.get('manual_price')
        if mp is not None:
            prices[h['code']] = float(mp)
            manual_codes.append(h['code'])

    # NaN/inf 방어: 가격 하나라도 비유한수면 JSON에 NaN 리터럴이 박혀
    # 프론트 res.json() 파싱이 통째 실패 → 보유종목/자산추이 전멸. None으로 정규화.
    import math as _math
    prices = {k: (v if (isinstance(v, (int, float)) and _math.isfinite(v)) else None)
              for k, v in prices.items()}

    return jsonify({
        'holdings': holdings,
        'groups': groups,
        'prices': prices,
        'manual_codes': manual_codes,
        'as_of': _dt.utcnow().isoformat(),
        'hide_amounts': _hide_amounts_for_user(uid),
    })


@app.route('/api/myassets/dividends')
def myassets_dividends():
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    from modules.dividend_history import build_dividend_chart
    try:
        holdings = get_holdings(session['user_id'])
        data = build_dividend_chart(portfolio_engine.loader, holdings)
        return jsonify(data)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/myassets/settings', methods=['POST'])
def myassets_save_settings():
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    uid = session['user_id']
    body = request.get_json(silent=True) or {}
    settings = get_settings(uid)
    settings['hide_amounts'] = bool(body.get('hide_amounts', True))
    save_settings(uid, settings)
    return jsonify({'ok': True, 'hide_amounts': settings['hide_amounts']})


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


@app.route('/api/myassets/manual-price', methods=['POST'])
def myassets_manual_price():
    """수동 가격 override 설정/해제. price 없으면(null) 해제 → 자동 시세 복귀."""
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    body = request.get_json(silent=True) or {}
    hid  = body.get('id')
    if not hid:
        return jsonify({'error': 'id 필요'}), 400
    raw = body.get('price', None)
    if raw in (None, ''):
        price = None
    else:
        try:
            price = float(raw)
            if price < 0:
                return jsonify({'error': '가격은 0 이상이어야 합니다.'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': '잘못된 가격'}), 400
    set_manual_price(session['user_id'], int(hid), price)
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
# 포트폴리오 즐겨찾기 API (B1)
# -----------------------------------------------

@app.route('/api/portfolio/list', methods=['GET'])
def portfolio_list():
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    items = get_portfolios(session['user_id'])
    allc = [t['code'] for p in items for t in p['tickers'] if isinstance(t, dict) and t.get('code')]
    nm = _resolve_names(allc)
    for p in items:
        for t in p['tickers']:
            if isinstance(t, dict) and t.get('code') and not t.get('name'):
                t['name'] = nm.get(t['code']) or t['code']
    return jsonify([
        {'id': p['id'], 'name': p['name'], 'tickers': p['tickers'],
         'updated_at': p['updated_at']}
        for p in items
    ])


@app.route('/api/portfolio/save', methods=['POST'])
def portfolio_save():
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    body = request.get_json(silent=True) or {}
    name    = str(body.get('name', '')).strip()
    tickers = body.get('tickers')
    if not name or len(name) > 50:
        return jsonify({'error': '이름은 1~50자로 입력해주세요.'}), 400
    if not isinstance(tickers, list) or not tickers or len(tickers) > 30:
        return jsonify({'error': '종목은 1~30개여야 합니다.'}), 400
    cleaned = []
    for t in tickers:
        if not isinstance(t, dict) or not t.get('code'):
            return jsonify({'error': '잘못된 종목 형식입니다.'}), 400
        try:
            weight = float(t.get('weight', 0))
        except (TypeError, ValueError):
            return jsonify({'error': '비중은 숫자여야 합니다.'}), 400
        try:
            quantity = float(t.get('quantity', 0) or 0)
        except (TypeError, ValueError):
            quantity = 0.0
        cleaned.append({
            'code':   str(t['code']),
            'name':   str(t.get('name', t['code'])),
            'badge':  str(t.get('badge', '')),
            'weight': weight,
            'quantity': quantity,
        })
    try:
        upsert_portfolio(
            session['user_id'], name, cleaned,
            portfolio_id=body.get('id') or None,
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})


@app.route('/api/portfolio/<int:portfolio_id>', methods=['DELETE'])
def portfolio_delete(portfolio_id):
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    delete_portfolio(session['user_id'], portfolio_id)
    return jsonify({'ok': True})


# -----------------------------------------------
# 저장 포트폴리오 상세 (수량 입력 → 비중·추이·배당)
# -----------------------------------------------

@app.route('/api/portfolio/item/<int:portfolio_id>', methods=['GET'])
def portfolio_item(portfolio_id):
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    p = get_portfolio(session['user_id'], portfolio_id)
    if not p:
        return jsonify({'error': '없는 포트폴리오'}), 404
    nm = _resolve_names([t['code'] for t in p['tickers'] if isinstance(t, dict) and t.get('code')])
    for t in p['tickers']:
        if isinstance(t, dict) and t.get('code') and not t.get('name'):
            t['name'] = nm.get(t['code']) or t['code']
    return jsonify({'id': p['id'], 'name': p['name'], 'tickers': p['tickers'],
                    'updated_at': p['updated_at']})


def _amount_to_holdings(amount, tickers):
    """총 투자금액(KRW) + tickers[{code, weight, account_type?}] → (holdings, prices).

    수량 = 총액 × (비중/100) ÷ 현재가(KRW). 비중은 포트폴리오에 이미 저장된 값을 그대로 사용.
    """
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0.0
    rows = []
    for t in (tickers or []):
        if not isinstance(t, dict):
            continue
        code = str(t.get('code', '')).strip()
        try:
            w = float(t.get('weight') or 0)
        except (TypeError, ValueError):
            w = 0.0
        if code and w > 0:
            rows.append((code, w, t.get('account_type', '일반')))
    codes  = list({c for c, _, _ in rows})
    prices = _get_current_asset_prices(codes) if codes else {}
    holdings = []
    for code, w, acct in rows:
        px  = prices.get(code, 0) or 0
        qty = (amount * (w / 100.0) / px) if (amount > 0 and px > 0) else 0.0
        holdings.append({'code': code, 'weight': w, 'quantity': qty, 'account_type': acct})
    return holdings, prices


@app.route('/api/portfolio/compute', methods=['POST'])
def portfolio_compute():
    """amount + tickers:[{code, weight}] → 현재가 + 종목별 수량 + 평가금액 추이."""
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    body = request.get_json(silent=True) or {}
    holdings, prices = _amount_to_holdings(body.get('amount'), body.get('tickers'))
    valid   = [(h['code'], h['quantity']) for h in holdings if h['quantity'] > 0]
    history = _compute_portfolio_history(valid)
    return jsonify({
        'prices':   prices,
        'holdings': holdings,
        'history':  history,
        'hide_amounts': _hide_amounts_for_user(session['user_id']),
    })


@app.route('/api/portfolio/dividends-preview', methods=['POST'])
def portfolio_dividends_preview():
    """amount + tickers:[{code, weight}] → 배당 차트 데이터 (내자산과 동일 엔진)."""
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    from modules.dividend_history import build_dividend_chart
    body = request.get_json(silent=True) or {}
    holdings, _ = _amount_to_holdings(body.get('amount'), body.get('tickers'))
    holdings = [h for h in holdings if h['quantity'] > 0]
    try:
        data = build_dividend_chart(portfolio_engine.loader, holdings)
        return jsonify(data)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/macro/overview')
def api_macro_overview():
    """거시경제 지표 카테고리별 카드 데이터 (공개)."""
    from modules import macro_loader
    return jsonify(macro_loader.get_overview())

@app.route('/api/macro/series/<code>')
def api_macro_series(code):
    """단일 지표 전체 시계열 (상세 차트용)."""
    from modules import macro_loader
    data = macro_loader.get_series(code)
    if not data:
        return jsonify({'error': 'not found'}), 404
    return jsonify(data)

@app.route('/api/macro/compare')
def api_macro_compare():
    """한·미 지표 비교 (단위 같으면 원값, 다르면 시작=100 정규화)."""
    from modules import macro_loader
    data = macro_loader.get_compare(request.args.get('us', ''), request.args.get('kr', ''))
    if not data:
        return jsonify({'error': 'not found'}), 404
    return jsonify(data)

@app.route('/api/macro/ohlc/<code>')
def api_macro_ohlc(code):
    """지수 OHLC (캔들용). yfinance 직접 — 일부 지수에서 /api/symbol 실패 회피."""
    from modules import macro_loader
    spec = macro_loader.SERIES_BY_CODE.get(code)
    if not spec or spec.get('src') != 'yf':
        return jsonify({'error': 'no ohlc'}), 404
    return jsonify({'rows': macro_loader.get_ohlc_cached(spec['yf'])})

@app.route('/api/macro/intraday/<code>')
def api_macro_intraday(code):
    """지수 1시간봉(캔들 1H용). yfinance 직접."""
    from modules import macro_loader
    spec = macro_loader.SERIES_BY_CODE.get(code)
    if not spec or spec.get('src') != 'yf':
        return jsonify({'error': 'no intraday'}), 404
    rng = request.args.get('range', 'max')
    return jsonify({'rows': macro_loader.get_intraday_cached(spec['yf'], rng)})

def _resolve_names(codes):
    """코드→종목명 (symbol_master). 반환 키 = 원본 코드."""
    out = {}
    try:
        from modules.dividend_history import _load_names
        loaded = _load_names(list(codes))   # {CODE_UPPER: name}
        for c in codes:
            nm = loaded.get(str(c).upper())
            if nm:
                out[c] = nm
    except Exception:
        pass
    return out

def _calendar_grouped(uid):
    """사용자 종목을 소스별로 그룹화 + 이름맵. {holdings,portfolios,watchlist}."""
    groups = {'holdings': [], 'portfolios': [], 'watchlist': []}
    names = {}
    try:
        for h in get_holdings(uid):
            if h.get('code'):
                groups['holdings'].append(str(h['code']))
    except Exception:
        pass
    try:
        for pf in get_portfolios(uid):
            for t in pf.get('tickers', []):
                if isinstance(t, dict) and t.get('code'):
                    c = str(t['code']); groups['portfolios'].append(c)
                    if t.get('name'):
                        names.setdefault(c, t['name'])
    except Exception:
        pass
    try:
        for w in (get_home_widgets(uid) or []):
            for it in (w.get('items') or []):
                if isinstance(it, dict) and it.get('code'):
                    c = str(it['code']); groups['watchlist'].append(c)
                    if it.get('name'):
                        names.setdefault(c, it['name'])
    except Exception:
        pass
    for k in groups:
        groups[k] = list(dict.fromkeys(groups[k]))
    return groups, names

def _calendar_user_codes(uid, cfg):
    """설정(소스 on/off + 개별 제외) 적용해 종목 코드 수집."""
    groups, _ = _calendar_grouped(uid)
    src = cfg.get('sources') or {}
    excl = set(cfg.get('excluded') or [])
    codes = []
    for g in ('holdings', 'portfolios', 'watchlist'):
        if src.get(g, True):
            codes += groups[g]
    return [c for c in dict.fromkeys(codes) if c not in excl][:60]

def _default_calendar_config():
    from modules import market_calendar
    return {'econ': list(market_calendar.CAL_RELEASES.keys()),
            'show_earnings': True, 'show_dividend': True,
            'sources': {'holdings': True, 'portfolios': True, 'watchlist': True},
            'excluded': []}

@app.route('/api/calendar')
def api_calendar():
    """증시 캘린더: 경제지표(공개) + 내 종목 실적·배당(로그인). 로그인 시 사용자 설정 적용."""
    from modules import market_calendar
    uid = session.get('user_id')
    if not uid:
        return jsonify({'events': market_calendar.events_for([], portfolio_engine.loader,
                                                             econ_ids=None, show_earnings=False, show_dividend=False),
                        'logged_in': False, 'symbol_count': 0})
    cfg = get_calendar_config(uid) or _default_calendar_config()
    codes = _calendar_user_codes(uid, cfg)
    _, names = _calendar_grouped(uid)
    ev = market_calendar.events_for(codes, portfolio_engine.loader,
                                    econ_ids=set(cfg.get('econ', [])),
                                    show_earnings=cfg.get('show_earnings', True),
                                    show_dividend=cfg.get('show_dividend', True),
                                    names=names)
    return jsonify({'events': ev, 'logged_in': True, 'symbol_count': len(codes)})

@app.route('/api/calendar/config')
def api_calendar_config_get():
    from modules import market_calendar
    uid = session.get('user_id')
    cfg = (get_calendar_config(uid) if uid else None) or _default_calendar_config()
    out = {'config': cfg, 'logged_in': bool(uid),
           'available_econ': [{'id': rid, 'label': lbl} for rid, lbl in market_calendar.CAL_RELEASES.items()]}
    if uid:
        groups, names = _calendar_grouped(uid)
        try:
            from modules.dividend_history import _load_names
            allc = [c for g in groups for c in groups[g]]
            loaded = _load_names(allc)
            for c in allc:
                if not names.get(c):
                    nm = loaded.get(c.upper())
                    if nm:
                        names[c] = nm
        except Exception:
            pass
        out['symbols'] = {g: [{'code': c, 'name': names.get(c, c)} for c in groups[g]]
                          for g in groups}
    return jsonify(out)

@app.route('/api/calendar/config', methods=['POST'])
def api_calendar_config_save():
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    from modules import market_calendar
    body = request.get_json(silent=True) or {}
    valid_ids = set(market_calendar.CAL_RELEASES.keys())
    src = body.get('sources') or {}
    cfg = {
        'econ': [i for i in (body.get('econ') or []) if i in valid_ids],
        'show_earnings': bool(body.get('show_earnings', True)),
        'show_dividend': bool(body.get('show_dividend', True)),
        'sources': {g: bool(src.get(g, True)) for g in ('holdings', 'portfolios', 'watchlist')},
        'excluded': [str(c) for c in (body.get('excluded') or [])][:200],
    }
    save_calendar_config(session['user_id'], cfg)
    return jsonify({'ok': True, 'config': cfg})

@app.route('/api/macro/curves')
def api_macro_curves():
    from modules import macro_loader
    return jsonify({'curves': macro_loader.get_curves_list()})

@app.route('/api/macro/curve/<curve_id>')
def api_macro_curve(curve_id):
    from modules import macro_loader
    data = macro_loader.get_curve(curve_id)
    if not data:
        return jsonify({'error': 'not found'}), 404
    return jsonify(data)

def _portfolio_index_series(tickers, years=6):
    """저장 포트폴리오 → 비중 고정 정규화 지수(시작=100) 일별 시계열. 오버레이 추세 비교용.
       비중 합으로 정규화, 종목별 종가를 시작일=100으로 환산해 가중합 → 통화 무관."""
    from datetime import datetime, timedelta
    from concurrent.futures import ThreadPoolExecutor
    cutoff = (datetime.now() - timedelta(days=int(years * 365))).strftime('%Y-%m-%d')
    wsum = sum(float(t.get('weight') or 0) for t in tickers) or 1.0

    valid = []
    for t in tickers:
        code = str(t.get('code') or '').upper()
        w = float(t.get('weight') or 0) / wsum
        if w > 0 and code:
            valid.append((code, w))
    if not valid:
        return []

    # P2-1: 보유종목마다 get_symbol_data(~2s, I/O 지배)를 순차 호출하던 것(10종목=~20s) →
    # ThreadPool 병렬(I/O-bound라 1코어도 이득). 데이터 출처·종가 동일 → 가중합 지수곡선 불변.
    def _fetch(cw):
        code, w = cw
        try:
            d = portfolio_engine.loader.get_symbol_data(code)
            m = {p['date']: p['close'] for p in d.get('prices', [])
                 if p.get('close') and p['date'] >= cutoff}
            return (code, w, m) if m else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=min(8, len(valid))) as ex:
        fetched = list(ex.map(_fetch, valid))
    series = {}
    for r in fetched:
        if r:
            code, w, m = r
            series[code] = (w, m)
    if not series:
        return []
    common = None
    for _, m in series.values():
        ks = set(m.keys())
        common = ks if common is None else (common & ks)
    dates = sorted(common or [])
    if len(dates) < 2:
        return []
    t0 = dates[0]
    out = []
    for dt in dates:
        val = 0.0
        for _, (w, m) in series.items():
            base = m.get(t0)
            if base:
                val += w * (m[dt] / base) * 100.0
        out.append([dt, round(val, 4)])
    return out


@app.route('/api/macro/multi')
def api_macro_multi():
    """임의 시리즈 N개 겹쳐보기. 토큰 = 거시지표 코드 / 'SYM:<종목>' / 'PF:<저장포폴id>'.
       단위가 제각각이라 프런트에서 시작=100 정규화(또는 개별 축). 원값 반환."""
    from modules import macro_loader
    keys = [k for k in request.args.get('keys', '').split(',') if k][:6]
    uid = session.get('user_id')
    out = []
    for k in keys:
        if k.startswith('SYM:'):
            code = k[4:].upper()
            try:
                d = portfolio_engine.loader.get_symbol_data(code)
                pts = [[p['date'], p['close']] for p in d.get('prices', [])
                       if p.get('close') is not None]
                if pts:
                    out.append({'key': k, 'label': d.get('name') or code,
                                'unit': d.get('currency') or '', 'points': pts})
            except Exception:
                pass
        elif k.startswith('PF:'):
            if not uid:
                continue
            try:
                pf = get_portfolio(uid, int(k[3:]))
            except Exception:
                pf = None
            if pf:
                pts = _portfolio_index_series(pf.get('tickers') or [])
                if pts:
                    out.append({'key': k, 'label': pf['name'],
                                'unit': '지수(시작=100)', 'points': pts})
        else:
            s = macro_loader.get_series(k)
            if s:
                out.append({'key': k, 'label': s['name_ko'], 'unit': s['unit'],
                            'points': s['points']})
    return jsonify({'series': out})

@app.route('/api/risk-return', methods=['POST'])
def risk_return():
    """저장 포트폴리오 + 벤치마크 위험-수익 산점도 데이터 (P3 리스크리턴도표)."""
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    from risk_return_logic import compute_risk_return, DEFAULT_BENCHMARKS
    body = request.get_json(silent=True) or {}
    extra = []
    for b in (body.get('benchmarks') or [])[:10]:
        if isinstance(b, dict) and b.get('code'):
            extra.append({'code': str(b['code']), 'name': str(b.get('name') or b['code'])})
    portfolios = get_portfolios(session['user_id'])
    try:
        result = compute_risk_return(
            portfolios, DEFAULT_BENCHMARKS + extra, portfolio_engine.loader,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'산출 실패: {e}'}), 500


@app.route('/api/portfolio/compare', methods=['POST'])
def portfolio_compare():
    """포트폴리오 비교 탭 — 선택 포폴 + 벤치마크의 11지표.

    body: {portfolio_ids:[int], benchmarks:[{code,name}]}
    portfolio_ids 비면 전체 저장 포폴. benchmarks 없으면 기본셋.
    """
    if not session.get('user_id'):
        return jsonify({'error': '로그인 필요'}), 401
    from risk_return_logic import compute_comparison, DEFAULT_BENCHMARKS
    body = request.get_json(silent=True) or {}

    all_p = get_portfolios(session['user_id'])
    ids = body.get('portfolio_ids')
    if ids is None:
        selected = all_p           # 키 부재 = 전체
    else:
        idset = {int(i) for i in ids}
        selected = [p for p in all_p if p['id'] in idset]   # 빈 배열 = 선택 0

    benchmarks = []
    for b in (body.get('benchmarks') or [])[:15]:
        if isinstance(b, dict) and b.get('code'):
            benchmarks.append({'code': str(b['code']), 'name': str(b.get('name') or b['code'])})
    if not benchmarks:
        benchmarks = DEFAULT_BENCHMARKS

    try:
        result = compute_comparison(selected, benchmarks, portfolio_engine.loader)
        return jsonify(result)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': f'산출 실패: {e}'}), 500

# -----------------------------------------------
# 백테스트 API
# -----------------------------------------------

@app.route('/api/backtest/run', methods=['POST'])
def backtest_run():
    from backtest_logic import run_backtest_logic
    body = request.json
    try:
        result = run_backtest_logic(body)
        return jsonify(result)
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


@app.route('/api/symbol/<code>/intraday')
def symbol_intraday_api(code):
    range_key = request.args.get('range', '1d')
    if range_key not in ('1d', '1w', 'max'):
        range_key = '1d'
    try:
        data = portfolio_engine.loader.get_intraday_data(code.upper(), range_key)
        return jsonify(data)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/assets')
def assets():
    if not session.get('user_id'):
        return jsonify([])
    uid = session['user_id']
    groups = get_groups(uid)
    if not groups:
        return jsonify([])
    holdings = get_holdings(uid)
    prices = _get_current_asset_prices([h['code'] for h in holdings])
    group_values = {}
    for h in holdings:
        gid = h.get('group_id')
        if not gid:
            continue
        group_values[gid] = group_values.get(gid, 0) + prices.get(h['code'], 0) * float(h.get('quantity') or 0)

    total_value = sum(group_values.values())
    if total_value > 0:
        return jsonify([
            {
                "name":  g['name'],
                "color": g['color'],
                "pct":   group_values.get(g['id'], 0) / total_value,
            }
            for g in groups if group_values.get(g['id'], 0) > 0
        ])

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
# C5: 결과 공유

@app.route('/share')
def share():
    import base64, json as _json
    d = request.args.get('d', '')
    data = {}
    if d:
        try:
            data = _json.loads(base64.urlsafe_b64decode(d + '=='))
        except Exception:
            pass
    base_url = request.host_url.rstrip('/')
    return render_template('share.html', data=data, d=d, base_url=base_url)


def _cleanup_old_share_images(max_age_days=7):
    import time
    cutoff = time.time() - max_age_days * 86400
    for f in SHARE_IMG_DIR.glob('*.png'):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except Exception:
            pass


@app.route('/api/share/upload', methods=['POST'])
def share_upload():
    import base64 as _b64, uuid as _uuid
    body = request.get_json(silent=True) or {}
    img_b64 = body.get('image', '')
    if not img_b64:
        return jsonify({'error': 'no image'}), 400
    if ',' in img_b64:
        img_b64 = img_b64.split(',', 1)[1]
    try:
        img_bytes = _b64.b64decode(img_b64)
    except Exception:
        return jsonify({'error': 'invalid base64'}), 400
    if len(img_bytes) > 8 * 1024 * 1024:
        return jsonify({'error': 'too large'}), 400
    _cleanup_old_share_images()
    img_id = _uuid.uuid4().hex[:12]
    (SHARE_IMG_DIR / f"{img_id}.png").write_bytes(img_bytes)
    return jsonify({'id': img_id})


@app.route('/share/img/<img_id>')
def share_img_page(img_id):
    img_path = SHARE_IMG_DIR / f"{img_id}.png"
    if not img_path.exists():
        return '''<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>링크 만료 — Money Milestone</title>
<style>body{font-family:sans-serif;background:#F0F4F8;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;gap:16px;padding:24px}
.card{background:white;border-radius:16px;padding:32px 24px;max-width:360px;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,0.08)}
h2{font-size:1.1rem;color:#1A2332;margin-bottom:8px}p{font-size:0.88rem;color:#546E7A;line-height:1.6}
a{display:inline-block;margin-top:16px;background:#1976D2;color:white;padding:10px 24px;border-radius:10px;font-size:0.9rem;font-weight:700;text-decoration:none}</style></head>
<body><div class="card"><div style="font-size:2.5rem">⏳</div><h2>링크가 만료되었습니다</h2>
<p>공유 링크는 7일간만 유효합니다.<br>결과를 다시 보려면 직접 분석을 실행해주세요.</p>
<a href="/backtest">📊 직접 분석해보기</a></div></body></html>''', 404
    base_url = request.host_url.rstrip('/')
    return render_template('share_img.html',
        img_id=img_id,
        raw_url=f"{base_url}/share/img/{img_id}/raw")


@app.route('/share/img/<img_id>/raw')
def share_img_raw(img_id):
    from flask import send_file as _send_file
    img_path = SHARE_IMG_DIR / f"{img_id}.png"
    if not img_path.exists():
        return "", 404
    resp = _send_file(img_path, mimetype='image/png')
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


@app.route('/share/og-thumb')
def share_og_thumb():
    import base64, json as _json, io
    d = request.args.get('d', '')
    data = {}
    if d:
        try:
            data = _json.loads(base64.urlsafe_b64decode(d + '=='))
        except Exception:
            pass

    from PIL import Image, ImageDraw, ImageFont
    from flask import send_file

    W, H = 1200, 630
    BG   = (15, 23, 42)
    CARD = (30, 41, 59)
    BLUE = (25, 118, 210)
    GREEN = (46, 125, 50)
    RED  = (198, 40, 40)
    WHITE = (255, 255, 255)
    MUTED = (148, 163, 184)

    img  = Image.new('RGB', (W, H), BG)
    draw = ImageDraw.Draw(img)

    try:
        font_lg = ImageFont.load_default(size=56)
        font_md = ImageFont.load_default(size=36)
        font_sm = ImageFont.load_default(size=26)
        font_xs = ImageFont.load_default(size=20)
    except Exception:
        font_lg = font_md = font_sm = font_xs = ImageFont.load_default()

    t = data.get('t', '')
    m = data.get('m', {})
    label = data.get('label', '')

    TYPE_NAMES = {
        'bt':   'Portfolio Backtest',
        'calc': 'Rolling Simulation',
        'div':  'Dividend Calculator',
        'ret':  'Retirement Planner',
    }
    type_name = TYPE_NAMES.get(t, 'Analysis Result')

    # 헤더 영역
    draw.rectangle([0, 0, W, 110], fill=CARD)
    draw.text((48, 28), 'Money Milestone', font=font_md, fill=BLUE)
    draw.text((48, 68), type_name, font=font_sm, fill=MUTED)
    if label:
        draw.text((W - 48, 28), label, font=font_sm, fill=WHITE, anchor='ra')

    # 핵심 지표 그리드
    def draw_metric(x, y, label_text, value_text, color=WHITE):
        draw.text((x, y), label_text, font=font_xs, fill=MUTED)
        draw.text((x, y + 30), value_text, font=font_lg, fill=color)

    if t == 'bt':
        period = data.get('period', '')
        if period:
            draw.text((48, 130), period, font=font_sm, fill=MUTED)
        items = [
            ('CAGR',         f"{m.get('cagr', 0):+.1f}%",  GREEN if m.get('cagr', 0) >= 0 else RED),
            ('MDD',          f"{m.get('mdd', 0):.1f}%",    RED),
            ('Sharpe',       f"{m.get('sharpe', 0):.2f}",  WHITE),
            ('Total Return', f"{m.get('total_return', 0):+.1f}%", GREEN if m.get('total_return', 0) >= 0 else RED),
        ]
        for i, (lbl, val, col) in enumerate(items):
            draw_metric(48 + i * 290, 180, lbl, val, col)

        # 스파크라인
        spark = data.get('spark', [])
        if len(spark) >= 2:
            sx, sy, sw, sh = 48, 370, W - 96, 180
            mn, mx = min(spark), max(spark)
            rng = mx - mn or 1
            pts = [(sx + int(sw * i / (len(spark) - 1)),
                    sy + sh - int(sh * (v - mn) / rng))
                   for i, v in enumerate(spark)]
            for i in range(len(pts) - 1):
                draw.line([pts[i], pts[i+1]], fill=BLUE, width=3)

    elif t == 'calc':
        years = data.get('years', 0)
        if years:
            draw.text((48, 130), f'{years}-year rolling simulation', font=font_sm, fill=MUTED)
        items = [
            ('Pessimistic (P10)', f"{m.get('p10', 0):.1f} 억", MUTED),
            ('Median (P50)',      f"{m.get('p50', 0):.1f} 억", WHITE),
            ('Optimistic (P90)', f"{m.get('p90', 0):.1f} 억", GREEN),
            ('Median CAGR',      f"{m.get('cagr', 0):.1f}%",       BLUE),
        ]
        for i, (lbl, val, col) in enumerate(items):
            draw_metric(48 + i * 290, 200, lbl, val, col)

    elif t == 'div':
        items = [
            ('Target Monthly', f"{m.get('target_monthly', 0):,}만", WHITE),
            ('Required Monthly', f"{m.get('solved_monthly', 0):,}만", GREEN),
            ('Period', f"{m.get('period', 0)}yr", MUTED),
        ]
        for i, (lbl, val, col) in enumerate(items):
            draw_metric(48 + i * 380, 200, lbl, val, col)

    elif t == 'ret':
        survival = m.get('survival', 0)
        s_color = GREEN if survival >= 80 else (WHITE if survival >= 60 else RED)
        items = [
            ('Initial Asset', f"{m.get('initial', 0):.1f} 억", WHITE),
            ('Monthly', f"{m.get('monthly', 0):,}만", WHITE),
            ('Survival Rate', f"{survival:.1f}%", s_color),
            ('Period', f"{m.get('years', 0)}yr", MUTED),
        ]
        for i, (lbl, val, col) in enumerate(items):
            draw_metric(48 + i * 290, 200, lbl, val, col)

    # 하단 워터마크
    draw.rectangle([0, H - 60, W, H], fill=CARD)
    draw.text((48, H - 40), 'moneymilestone.duckdns.org', font=font_xs, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)

    from flask import make_response
    resp = make_response(send_file(buf, mimetype='image/png'))
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


# -----------------------------------------------

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()   # Windows 필수
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
