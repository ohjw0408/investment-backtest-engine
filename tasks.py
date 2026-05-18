import time
import redis
from celery_app import celery

r = redis.Redis(host='localhost', port=6379, db=0)


def get_queue_position(task_id: str) -> int:
    try:
        queue = r.lrange('celery', 0, -1)
        for i, item in enumerate(queue):
            if task_id.encode() in item:
                return i
        return 0
    except Exception:
        return 0


@celery.task(bind=True)
def run_simulation_task(self, payload: dict) -> dict:
    start_time = time.time()

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
        return {'status': 'SUCCESS', 'result': result}
    except Exception as e:
        import traceback
        return {
            'status':    'FAILURE',
            'error':     str(e),
            'traceback': traceback.format_exc(),
        }


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


@celery.task(bind=True)
def run_retirement_task(self, payload: dict) -> dict:
    cb = _make_progress_callback(self)
    try:
        from retirement_logic import run_retirement_logic, run_withdrawal_logic
        if payload.get('_mode') == 'withdrawal':
            result = run_withdrawal_logic(payload, progress_callback=cb)
        else:
            result = run_retirement_logic(payload, progress_callback=cb)
        return {'status': 'SUCCESS', 'result': result}
    except Exception as e:
        import traceback
        return {'status': 'FAILURE', 'error': str(e), 'traceback': traceback.format_exc()}


@celery.task(bind=True)
def run_backtest_task(self, payload: dict) -> dict:
    cb = _make_progress_callback(self)
    try:
        from backtest_logic import run_backtest_logic
        result = run_backtest_logic(payload, progress_callback=cb)
        return {'status': 'SUCCESS', 'result': result}
    except Exception as e:
        import traceback
        return {'status': 'FAILURE', 'error': str(e), 'traceback': traceback.format_exc()}


@celery.task(bind=True)
def run_dividend_task(self, payload: dict) -> dict:
    cb = _make_progress_callback(self)
    try:
        from dividend_logic import run_dividend_scenario_logic
        result = run_dividend_scenario_logic(payload, progress_callback=cb)
        return {'status': 'SUCCESS', 'result': result}
    except Exception as e:
        import traceback
        return {'status': 'FAILURE', 'error': str(e), 'traceback': traceback.format_exc()}
