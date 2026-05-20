import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import redis
from celery_app import celery

r = redis.Redis(host='localhost', port=6379, db=0)

_DURATION_KEY = 'mm_task_durations'


def get_queue_position(task_id: str) -> int:
    try:
        queue = r.lrange('celery', 0, -1)
        for i, item in enumerate(queue):
            if task_id.encode() in item:
                return i
        return 0
    except Exception:
        return 0


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
    try:
        r.incr('mm_active_tasks')
    except Exception:
        pass

    def progress_callback(current: int, total: int, elapsed: float):
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
            }
        )

    try:
        from calculator_logic import run_calculator_logic
        result = run_calculator_logic(payload, progress_callback=progress_callback)
        record_task_duration(time.time() - start_time)
        return {'status': 'SUCCESS', 'result': result}
    except Exception as e:
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


def _make_progress_callback(task):
    def progress_callback(current: int, total: int, elapsed: float):
        if total <= 0:
            return
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
            }
        )
    return progress_callback


def _task_wrap(fn):
    """incr/decr mm_active_tasks around fn(); return fn()'s result."""
    try:
        r.incr('mm_active_tasks')
    except Exception:
        pass
    try:
        return fn()
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
            import traceback
            return {'status': 'FAILURE', 'error': str(e), 'traceback': traceback.format_exc()}
    return _task_wrap(_run)


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
            import traceback
            return {'status': 'FAILURE', 'error': str(e), 'traceback': traceback.format_exc()}
    return _task_wrap(_run)


@celery.task(bind=True)
def run_dividend_task(self, payload: dict) -> dict:
    cb = _make_progress_callback(self)
    _t = time.time()
    def _run():
        try:
            from dividend_logic import run_dividend_scenario_logic
            result = run_dividend_scenario_logic(payload, progress_callback=cb)
            record_task_duration(time.time() - _t)
            return {'status': 'SUCCESS', 'result': result}
        except Exception as e:
            import traceback
            return {'status': 'FAILURE', 'error': str(e), 'traceback': traceback.format_exc()}
    return _task_wrap(_run)
