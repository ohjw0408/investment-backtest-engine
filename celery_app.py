from celery import Celery
from celery.schedules import crontab

celery = Celery(
    'domino',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0',
    broker_connection_retry_on_startup=True,
)

celery.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=10,
)
import tasks  # noqa

# Beat 스케줄 — 평일 16:30 KST (= 07:30 UTC)
celery.conf.timezone = 'UTC'
celery.conf.beat_schedule = {
    'refresh-krx-gold-daily': {
        'task': 'tasks.refresh_krx_gold',
        'schedule': crontab(hour=7, minute=30, day_of_week='mon-fri'),
    },
}