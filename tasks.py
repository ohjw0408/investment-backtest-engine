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
