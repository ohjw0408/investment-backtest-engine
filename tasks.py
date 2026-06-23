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


def _any_market_open(now_utc=None):
    """US 정규장(13:30~20:00 UTC) 또는 KR 정규장(00:00~06:30 UTC), 월~금."""
    from datetime import datetime as _dt
    now = now_utc or _dt.utcnow()
    if now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    us = 13 * 60 + 30 <= m <= 20 * 60
    kr = 0 <= m <= 6 * 60 + 30
    return us or kr


@celery.task
def evaluate_alerts():
    """장중 15분마다 Celery Beat 실행 — 사용자 알림 룰 평가, 발화 시 수신함 적재."""
    if not _any_market_open():
        return {"status": "market_closed"}
    try:
        from modules.alerts.alert_runner import run_alert_evaluation
        from modules.price_loader import PriceLoader
        from modules import auth_manager
        auth_manager.init_db()  # 워커 프로세스에서 users.db 연결 보장
        from modules.alerts import alert_store
        alert_store.init_alerts_db()
        fired = run_alert_evaluation(PriceLoader())
        print(f"[evaluate_alerts] {fired} alerts fired")
        return {"status": "ok", "fired": fired}
    except Exception as e:
        print(f"[evaluate_alerts] 오류: {e}")
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
