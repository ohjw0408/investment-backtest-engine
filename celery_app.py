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

# Beat 스케줄 — KRX 금현물은 당일 API 반영 시간이 일정하지 않아 여러 번 재시도
celery.conf.timezone = 'UTC'
celery.conf.beat_schedule = {
    'refresh-krx-gold-after-close': {
        'task': 'tasks.refresh_krx_gold',
        'schedule': crontab(hour=7, minute=40, day_of_week='mon-fri'),   # 16:40 KST
    },
    'refresh-krx-gold-evening': {
        'task': 'tasks.refresh_krx_gold',
        'schedule': crontab(hour=9, minute=30, day_of_week='mon-fri'),   # 18:30 KST
    },
    'refresh-krx-gold-night': {
        'task': 'tasks.refresh_krx_gold',
        'schedule': crontab(hour=13, minute=30, day_of_week='mon-fri'),  # 22:30 KST
    },
    'refresh-krx-gold-next-morning': {
        'task': 'tasks.refresh_krx_gold',
        'schedule': crontab(hour=23, minute=30, day_of_week='mon-fri'),  # 08:30 KST next day
    },
    # 거시지표 증분 갱신 — 미국 장 마감 후(21:30 UTC≈06:30 KST 익일) + 한국 장 마감 후(07:00 UTC≈16:00 KST)
    'refresh-macro-us-close': {
        'task': 'tasks.refresh_macro',
        'schedule': crontab(hour=21, minute=30, day_of_week='tue-sat'),
    },
    'refresh-macro-kr-close': {
        'task': 'tasks.refresh_macro',
        'schedule': crontab(hour=7, minute=0, day_of_week='mon-fri'),
    },
    # 시장지수 index_ohlc 갱신 — 장 열린 동안 30분마다 당일 봉을 채워 라인차트/홈위젯이
    # 어제 종가에 멈추지 않게(캔들 1H는 라이브라 당일 보임 → 불일치 해소).
    # KR 정규장 00:00~06:30 UTC, US 정규장 13:30~21:00 UTC(서머타임 여유) 커버.
    'refresh-index-ohlc': {
        'task': 'tasks.refresh_index_ohlc',
        'schedule': crontab(minute='*/20', hour='0-6,13-21', day_of_week='mon-fri'),
    },
    # 알림 룰 평가 — 장중 15분마다(US 13:30~20:00 + KR 00:00~06:30 UTC). task 내부서 장시간 재확인.
    'evaluate-alerts': {
        'task': 'tasks.evaluate_alerts',
        'schedule': crontab(minute='*/15', hour='0-6,13-20', day_of_week='mon-fri'),
    },
    # 증시 캘린더 일정 알림 — 매일 08:00 KST(=23:00 UTC). 당일 일정 묶음 1건.
    'evaluate-calendar-alerts': {
        'task': 'tasks.evaluate_calendar_alerts',
        'schedule': crontab(hour=23, minute=0),
    },
}
