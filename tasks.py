import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import redis
from celery_app import celery

r = redis.Redis(host='localhost', port=6379, db=0)

_DURATION_KEY = 'mm_task_durations'
_CANCEL_PREFIX = 'mm_cancel_'


def set_cancel_flag(task_id: str) -> None:
    try:
        r.set(f'{_CANCEL_PREFIX}{task_id}', '1', ex=300)
    except Exception:
        pass


def check_cancel_flag(task_id: str) -> bool:
    try:
        return bool(r.get(f'{_CANCEL_PREFIX}{task_id}'))
    except Exception:
        return False


def clear_cancel_flag(task_id: str) -> None:
    try:
        r.delete(f'{_CANCEL_PREFIX}{task_id}')
    except Exception:
        pass


def add_to_queue(task_id: str) -> None:
    try:
        r.zadd('mm_task_queue', {task_id: time.time()})
        r.expire('mm_task_queue', 3600)
    except Exception:
        pass


def get_queue_rank(task_id: str):
    """내 앞에 아직 시작 안 된 태스크 수. None=이미 픽업됨."""
    try:
        rank = r.zrank('mm_task_queue', task_id)
        return int(rank) if rank is not None else None
    except Exception:
        return None


def _remove_from_queue(task_id: str) -> None:
    try:
        r.zrem('mm_task_queue', task_id)
    except Exception:
        pass


def record_task_duration(seconds: float) -> None:
    try:
        r.rpush(_DURATION_KEY, seconds)
        r.ltrim(_DURATION_KEY, -20, -1)
    except Exception:
        pass


def get_avg_duration() -> int:
    try:
        vals = r.lrange(_DURATION_KEY, 0, -1)
        if not vals:
            return 30
        return round(sum(float(v) for v in vals) / len(vals))
    except Exception:
        return 30


def get_active_tasks() -> int:
    try:
        return max(0, int(r.get('mm_active_tasks') or 0))
    except Exception:
        return 0


@celery.task(bind=True)
def run_simulation_task(self, payload: dict) -> dict:
    start_time = time.time()
    _remove_from_queue(self.request.id)
    try:
        r.incr('mm_active_tasks')
    except Exception:
        pass

    def progress_callback(current: int, total: int, elapsed: float, phase: str = 'computing'):
        if check_cancel_flag(self.request.id):
            raise Exception('__CANCELLED__')
        eta = (elapsed / current * (total - current)) if current > 0 else None
        self.update_state(
            state='PROGRESS',
            meta={
                'current':   current,
                'total':     total,
                'percent':   round(current / total * 100),
                'elapsed':   round(elapsed),
                'eta':       round(eta) if eta is not None else None,
                'queue_pos': 0,
                'phase':     phase,
            }
        )

    try:
        self.update_state(state='PROGRESS', meta={
            'current': 0, 'total': 100, 'percent': 1,
            'elapsed': 0, 'eta': None, 'phase': 'preparing',
        })
        from calculator_logic import run_calculator_logic
        result = run_calculator_logic(payload, progress_callback=progress_callback)
        record_task_duration(time.time() - start_time)
        return {'status': 'SUCCESS', 'result': result}
    except Exception as e:
        if check_cancel_flag(self.request.id):
            clear_cancel_flag(self.request.id)
            return {'status': 'CANCELLED'}
        import traceback
        return {
            'status':    'FAILURE',
            'error':     str(e),
            'traceback': traceback.format_exc(),
        }
    finally:
        try:
            r.decr('mm_active_tasks')
        except Exception:
            pass


def _make_cancel_check(task):
    def cancel_check():
        if check_cancel_flag(task.request.id):
            raise Exception('__CANCELLED__')
    return cancel_check


def _make_progress_callback(task):
    def progress_callback(current: int, total: int, elapsed: float, phase: str = 'computing'):
        if total <= 0:
            return
        if check_cancel_flag(task.request.id):
            raise Exception('__CANCELLED__')
        eta = (elapsed / current * (total - current)) if current > 0 else None
        task.update_state(
            state='PROGRESS',
            meta={
                'current':   current,
                'total':     total,
                'percent':   round(current / total * 100),
                'elapsed':   round(elapsed),
                'eta':       round(eta) if eta is not None else None,
                'queue_pos': 0,
                'phase':     phase,
            }
        )
    return progress_callback


def _mark_preparing(task):
    """태스크 시작 직후 '데이터 준비 중' 신호 — 가격 로드/백필 동안 PENDING으로 남아
    프론트가 단계를 못 보여주던 문제 해소 (출시완성도 G-2)."""
    task.update_state(state='PROGRESS', meta={
        'current': 0, 'total': 100, 'percent': 1,
        'elapsed': 0, 'eta': None, 'queue_pos': 0, 'phase': 'preparing',
    })


def _task_wrap(fn, task_id=None):
    """incr/decr mm_active_tasks around fn(); ZREM from queue on start."""
    if task_id:
        _remove_from_queue(task_id)
    try:
        r.incr('mm_active_tasks')
    except Exception:
        pass
    try:
        result = fn()
        return result
    except Exception:
        if task_id and check_cancel_flag(task_id):
            clear_cancel_flag(task_id)
            return {'status': 'CANCELLED'}
        raise
    finally:
        try:
            r.decr('mm_active_tasks')
        except Exception:
            pass


@celery.task(bind=True)
def run_retirement_task(self, payload: dict) -> dict:
    cb = _make_progress_callback(self)
    _mark_preparing(self)
    _t = time.time()
    def _run():
        try:
            from retirement_logic import run_retirement_logic, run_withdrawal_logic
            if payload.get('_mode') == 'withdrawal':
                result = run_withdrawal_logic(payload, progress_callback=cb)
            else:
                result = run_retirement_logic(payload, progress_callback=cb)
            record_task_duration(time.time() - _t)
            return {'status': 'SUCCESS', 'result': result}
        except Exception as e:
            if check_cancel_flag(self.request.id):
                clear_cancel_flag(self.request.id)
                return {'status': 'CANCELLED'}
            import traceback
            return {'status': 'FAILURE', 'error': str(e), 'traceback': traceback.format_exc()}
    return _task_wrap(_run, self.request.id)


@celery.task(bind=True)
def run_tax_switch_task(self, payload: dict) -> dict:
    cb = _make_progress_callback(self)
    _mark_preparing(self)
    _t = time.time()
    def _run():
        try:
            from tax_switch_logic import run_tax_switch_logic
            result = run_tax_switch_logic(payload, progress_callback=cb)
            record_task_duration(time.time() - _t)
            return {'status': 'SUCCESS', 'result': result}
        except Exception as e:
            if check_cancel_flag(self.request.id):
                clear_cancel_flag(self.request.id)
                return {'status': 'CANCELLED'}
            import traceback
            return {'status': 'FAILURE', 'error': str(e), 'traceback': traceback.format_exc()}
    return _task_wrap(_run, self.request.id)


@celery.task(bind=True)
def run_backtest_task(self, payload: dict) -> dict:
    cb = _make_progress_callback(self)
    _mark_preparing(self)
    _t = time.time()
    def _run():
        try:
            from backtest_logic import run_backtest_logic
            result = run_backtest_logic(payload, progress_callback=cb)
            record_task_duration(time.time() - _t)
            return {'status': 'SUCCESS', 'result': result}
        except Exception as e:
            if check_cancel_flag(self.request.id):
                clear_cancel_flag(self.request.id)
                return {'status': 'CANCELLED'}
            import traceback
            return {'status': 'FAILURE', 'error': str(e), 'traceback': traceback.format_exc()}
    return _task_wrap(_run, self.request.id)


@celery.task(bind=True)
def run_dividend_task(self, payload: dict) -> dict:
    cb = _make_progress_callback(self)
    _mark_preparing(self)
    cc = _make_cancel_check(self)
    _t = time.time()
    def _run():
        try:
            from dividend_logic import run_dividend_scenario_logic
            result = run_dividend_scenario_logic(payload, progress_callback=cb, cancel_check=cc)
            record_task_duration(time.time() - _t)
            return {'status': 'SUCCESS', 'result': result}
        except Exception as e:
            if check_cancel_flag(self.request.id):
                clear_cancel_flag(self.request.id)
                return {'status': 'CANCELLED'}
            import traceback
            return {'status': 'FAILURE', 'error': str(e), 'traceback': traceback.format_exc()}
    return _task_wrap(_run, self.request.id)


@celery.task
def refresh_krx_gold():
    """매 평일 16:30 KST Celery Beat 자동 실행 — KRX 금현물 당일 종가 저장."""
    from datetime import datetime, timedelta
    from modules.krx.fetch_krx_gold import KRXClient, init_db, save

    def invalidate_market_cache():
        try:
            redis.Redis(host='localhost', port=6379, db=1).delete("mq:krx_gold")
        except Exception as e:
            print(f"[refresh_krx_gold] 캐시 무효화 실패: {e}")

    conn = None
    try:
        client = KRXClient()
        conn = init_db()
        today = datetime.today()
        # 오늘부터 최대 15일 전까지 시도 (주말/공휴일/긴 연휴 대비)
        saved = False
        for delta in range(15):
            d = (today - timedelta(days=delta)).strftime("%Y%m%d")
            try:
                df = client.get_gold(d)
                if not df.empty:
                    n = save(conn, df)
                    invalidate_market_cache()
                    print(f"[refresh_krx_gold] {d} → {n}개 저장")
                    saved = True
                    return {"status": "ok", "date": d, "rows": n}
            except Exception as e:
                print(f"[refresh_krx_gold] {d} 조회 실패: {e}")
                continue
        if not saved:
            print("[refresh_krx_gold] 데이터 없음 (공휴일?)")
            return {"status": "no_data"}
    except Exception as e:
        print(f"[refresh_krx_gold] 오류: {e}")
        raise
    finally:
        if conn:
            conn.close()


def _open_markets(now_utc=None):
    """현재 열린 시장 집합: {'KR','US'} 부분집합. 월~금 기준.

    KR 정규장 09:00~15:30 KST = 00:00~06:30 UTC / US 정규장 13:30~21:00 UTC
    (여름 EDT 09:30~16:00 = 13:30~20:00Z, 겨울 EST = 14:30~21:00Z — 둘 다 커버.
    창 밖 이른 슬롯의 오발화는 cur_is_today 가드가 차단).
    알림 교통정리(2026-07-02): 룰별 자기 시장 게이팅용 — "아무 장이나 열림" 전역
    게이트가 코스피 룰을 미국장 시간(22:30 KST)에 평가하던 문제의 근본 수정.
    """
    from datetime import datetime as _dt
    now = now_utc or _dt.utcnow()
    if now.weekday() >= 5:
        return set()
    m = now.hour * 60 + now.minute
    open_ = set()
    if 0 <= m <= 6 * 60 + 30:
        open_.add("KR")
    if 13 * 60 + 30 <= m <= 21 * 60:
        open_.add("US")
    return open_



@celery.task
def evaluate_alerts():
    """15분마다 Celery Beat 실행(24/7) — 사용자 알림 룰 평가, 발화 시 수신함 적재.

    KR/US 룰은 자기 장중만(markets 게이팅), ANY(크립토·환율·선물) 룰은 상시.
    조기리턴 없음 — 주말·장외에도 ANY 룰 커버(2026-07-02 자산군 커버 수정)."""
    try:
        from modules.alerts.alert_runner import run_alert_evaluation
        from modules.price_loader import PriceLoader
        from modules import auth_manager
        auth_manager.init_db()  # 워커 프로세스에서 users.db 연결 보장
        from modules.alerts import alert_store
        alert_store.init_alerts_db()
        fired = run_alert_evaluation(PriceLoader(), markets=_open_markets())
        print(f"[evaluate_alerts] {fired} alerts fired")
        return {"status": "ok", "fired": fired}
    except Exception as e:
        print(f"[evaluate_alerts] 오류: {e}")
        raise


@celery.task
def evaluate_close_alerts(market):
    """장 마감 직후 Celery Beat — 해당 시장 daily_pct 룰의 확정 등락 요약 알림.

    KR: 06:50 UTC(15:50 KST — 마감 15:30 + 지수 당일봉 확정 여유),
    US: 20:30 UTC(마감 20:00 + 여유). 장중 발화와 독립("마감" 타이틀 별도 레인).
    """
    try:
        from modules.alerts.alert_runner import run_close_summary
        from modules.price_loader import PriceLoader
        from modules import auth_manager
        auth_manager.init_db()
        from modules.alerts import alert_store
        alert_store.init_alerts_db()
        fired = run_close_summary(PriceLoader(), str(market).upper())
        print(f"[evaluate_close_alerts] {market} {fired} alerts fired")
        return {"status": "ok", "market": market, "fired": fired}
    except Exception as e:
        print(f"[evaluate_close_alerts] 오류: {e}")
        raise


@celery.task
def evaluate_calendar_alerts():
    """매일 08:00 KST Celery Beat — 증시 캘린더 일정 알림(당일 일정 묶음 1건). 장 무관."""
    try:
        from modules.alerts.calendar_alert_runner import run_calendar_alerts
        from modules.price_loader import PriceLoader
        from modules import auth_manager
        auth_manager.init_db()
        from modules.alerts import alert_store
        alert_store.init_alerts_db()
        fired = run_calendar_alerts(PriceLoader())
        print(f"[evaluate_calendar_alerts] {fired} users notified")
        return {"status": "ok", "fired": fired}
    except Exception as e:
        print(f"[evaluate_calendar_alerts] 오류: {e}")
        raise


@celery.task
def refresh_index_ohlc():
    """장중 주기 실행(Celery Beat) — 시장지수 index_ohlc를 당일까지 갱신.

    이게 없으면 index_ohlc는 첫 방문 지연백필 이후 갱신 안 돼 라인차트/위젯이 어제 종가에
    멈춘다(캔들 1H는 라이브 intraday라 당일 보임 → 불일치). 장 열린 동안 당일 봉을 채운다.
    """
    try:
        from modules.price_loader import PriceLoader
        n = PriceLoader().refresh_index_ohlc()
        print(f"[refresh_index_ohlc] {n} rows upserted")
        return {"status": "ok", "rows": n}
    except Exception as e:
        print(f"[refresh_index_ohlc] 오류: {e}")
        raise


@celery.task
def warmup_history():
    """대가·예시 포폴 구성종목의 전체기간을 미리 백필(플래그) — 첫 사용자 콜드 부담 제거.

    추세 겹쳐보기는 큐레이션된 대가/예시 포폴을 주로 띄우므로, 그 종목들은 미리 풀히스토리
    적재해두면 누가 처음 봐도 즉시. 이미 hist_complete 플래그면 no-op라 반복 실행 안전.
    """
    import json as _json
    import os as _os
    import time as _t
    try:
        from modules.price_loader import PriceLoader
        from modules.gurus import store as guru_store
        pl = PriceLoader()
        codes = set()
        # 예시 포폴
        try:
            p = _os.path.join(_os.path.dirname(__file__), "data", "meta", "portfolio_examples.json")
            for s in _json.load(open(p, encoding="utf-8")).get("strategies", []):
                for t in s.get("tickers", []):
                    if t.get("code"):
                        codes.add(str(t["code"]).upper())
        except Exception as e:
            print(f"[warmup_history] examples 로드 실패: {e}")
        # 대가 보유
        try:
            for g in guru_store.list_gurus():
                d = guru_store.get_guru(g["slug"], limit=30)
                for h in (d or {}).get("holdings", []):
                    if h.get("ticker"):
                        codes.add(str(h["ticker"]).upper())
        except Exception as e:
            print(f"[warmup_history] gurus 로드 실패: {e}")
        done = 0
        for c in sorted(codes):
            try:
                if pl.ensure_full_history(c):
                    done += 1
                    _t.sleep(0.4)   # yfinance rate-limit 회피(이미 플래그면 sleep 안 함)
            except Exception:
                pass
        print(f"[warmup_history] {len(codes)}종목 중 {done}개 신규 백필")
        return {"status": "ok", "total": len(codes), "fetched": done}
    except Exception as e:
        print(f"[warmup_history] 오류: {e}")
        raise


@celery.task
def purge_price_spikes():
    """매일 실행(Celery Beat) — price_daily의 고립 스파이크(yfinance 오틱) 행을 영구 제거.

    쓰기경로가 못 거른 증분 오틱(예: SPY 2026-06-17=346500)을 DB 전체 이웃 기준으로 지워
    겹쳐보기 등 raw 읽기 경로까지 self-heal. 다음 페치가 정상값으로 다시 채운다.
    """
    try:
        from modules.price_loader import PriceLoader
        n = PriceLoader().purge_isolated_spikes()
        print(f"[purge_price_spikes] {n} rows deleted")
        return {"status": "ok", "deleted": n}
    except Exception as e:
        print(f"[purge_price_spikes] 오류: {e}")
        raise


@celery.task
def refresh_macro():
    """거시경제 지표 증분 갱신 (Celery Beat 자동 실행). FRED·ECOS·yfinance 시장지수."""
    try:
        from modules import macro_loader
        n = macro_loader.refresh()
        print(f"[refresh_macro] {n} series updated")
        return {"status": "ok", "updated": n}
    except Exception as e:
        print(f"[refresh_macro] 오류: {e}")
        raise


# ── 데이터 무결성 상시 방어 (출시완성도 B-2②) ─────────────────────────────

def _integrity_notify_owner(issues):
    """무결성 이상을 오너 인앱 수신함 + FCM 푸시로 통지 (기존 알림 인프라 재사용)."""
    import sqlite3
    owner_email = os.environ.get('OWNER_EMAIL', 'ohjw0408@gmail.com')
    try:
        from modules.auth_manager import DB_PATH as _users_db
        conn = sqlite3.connect(str(_users_db))
        row = conn.execute("SELECT id FROM users WHERE email=?", (owner_email,)).fetchone()
        conn.close()
        if not row:
            return
        uid = row[0]
        title = f"⚠️ 데이터 무결성 이상 {len(issues)}건"
        body = " / ".join(issues)[:500]
        from modules.alerts import alert_store
        alert_store.add_event(uid, title, body, meta={'type': 'integrity'})
        try:
            from modules.alerts import push_sender
            push_sender.send_to_user(uid, title, body, data={'type': 'integrity', 'target_url': '/alerts#inbox'})
        except Exception:
            pass
    except Exception as e:
        print(f"[data_integrity_scan] 오너 알림 실패: {e}")


def _sentry_capture(msg):
    """워커에서 Sentry 이벤트 발송 — DSN 미설정/미설치면 조용히 no-op."""
    try:
        import sentry_sdk
        if sentry_sdk.Hub.current.client is None:
            dsn = os.environ.get('SENTRY_DSN', '')
            if not dsn:
                return
            sentry_sdk.init(dsn=dsn, traces_sample_rate=0, send_default_pii=False)
        sentry_sdk.capture_message(msg, level='warning')
    except Exception:
        pass


@celery.task
def data_integrity_scan():
    """매일 실행(Celery Beat) — 데이터 품질 상시 방어. 개별 버그픽스를 체계로 승격.

    ① price_daily 내부 NULL close 행 검출·삭제 (self-heal — pct_change pad 점프의 근원.
       쓰기경로 _validate_price_rows가 신규 유입을 막으므로 잔존 발견 = 우회 쓰기경로 신호)
    ② 핵심 시계열 신선도 — USD/KRW(전 환산의 기반)·KRX_GOLD·price_daily 전체 max(date)
    ③ 합성 백필 손상 스캔 — scripts/scan_backfill_corruption.scan_all 재사용 (B-1 판정 기준)
    이상 발견 시 오너 인앱 알림+푸시, Sentry 이벤트.
    """
    import sqlite3
    from datetime import datetime, timedelta
    base = os.path.dirname(os.path.abspath(__file__))
    price_db = os.path.join(base, 'data', 'price_cache', 'price_daily.db')
    index_db = os.path.join(base, 'data', 'meta', 'index_master.db')
    issues = []
    try:
        pc = sqlite3.connect(price_db)

        # ① 내부 NULL close 행 — 검출 즉시 삭제(순수 오염, 유용한 경우 없음)
        null_rows = pc.execute(
            "SELECT code, COUNT(*) FROM price_daily WHERE close IS NULL GROUP BY code"
        ).fetchall()
        if null_rows:
            pc.execute("DELETE FROM price_daily WHERE close IS NULL")
            pc.commit()
            detail = ", ".join(f"{c}×{n}" for c, n in null_rows[:10])
            issues.append(f"NULL close 행 삭제: {detail} (쓰기경로 우회 유입 의심)")

        # ② 신선도 — 주말+연휴 허용치 반영한 보수적 임계
        today = datetime.now()
        def _staleness(conn, sql, args=()):
            row = conn.execute(sql, args).fetchone()
            if not row or not row[0]:
                return None
            return (today - datetime.strptime(row[0][:10], '%Y-%m-%d')).days
        ic = sqlite3.connect(index_db)
        d = _staleness(ic, "SELECT MAX(date) FROM index_daily WHERE code='USD/KRW'")
        if d is None or d > 6:
            issues.append(f"USD/KRW 환율 신선도 이상 (last {d}일 전)")
        d = _staleness(ic, "SELECT MAX(date) FROM index_daily WHERE code='KRX_GOLD'")
        if d is None or d > 7:
            issues.append(f"KRX_GOLD 신선도 이상 (last {d}일 전)")
        ic.close()
        d = _staleness(pc, "SELECT MAX(date) FROM price_daily")
        if d is None or d > 6:
            issues.append(f"price_daily 전체 갱신 정지 의심 (last {d}일 전)")

        # ③ 합성 백필 손상 스캔 (B-1 스크립트 재사용)
        sys.path.insert(0, os.path.join(base, 'scripts'))
        try:
            from scan_backfill_corruption import scan_all
            corrupt = [r['code'] for r in scan_all(pc) if r['corrupt']]
            if corrupt:
                issues.append(f"합성 백필 손상 검출: {corrupt}")
        except Exception as e:
            issues.append(f"합성 손상 스캔 실행 실패: {e}")
        pc.close()

        if issues:
            print(f"[data_integrity_scan] 이상 {len(issues)}건: {issues}")
            _integrity_notify_owner(issues)
            _sentry_capture(f"data_integrity_scan: {issues}")
        else:
            print("[data_integrity_scan] 이상 없음")
        return {"status": "ok", "issues": issues}
    except Exception as e:
        print(f"[data_integrity_scan] 오류: {e}")
        _sentry_capture(f"data_integrity_scan 자체 실패: {e}")
        raise
