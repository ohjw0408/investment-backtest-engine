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
    # 알림 룰 평가 — 15분마다 24/7 (자산군 커버 2026-07-02):
    # KR/US 주식은 task 내부 _open_markets()가 자기 장중만, 크립토(-USD)·환율(=X)·
    # 선물(=F) = ANY 시장은 상시(주말 비트코인 급변도 커버). 장 밖 슬롯은 ANY 룰
    # 없으면 사실상 no-op(수 ms 쿼리 1회).
    'evaluate-alerts': {
        'task': 'tasks.evaluate_alerts',
        'schedule': crontab(minute='*/15'),
    },
    # 장 마감 확정 등락 요약 (알림 교통정리 2026-07-02) — daily_pct 룰 대상, 장중과 별도 레인.
    'close-summary-kr': {
        'task': 'tasks.evaluate_close_alerts',
        'schedule': crontab(hour=6, minute=50, day_of_week='mon-fri'),   # 15:50 KST
        'args': ('KR',),
    },
    'close-summary-us': {
        'task': 'tasks.evaluate_close_alerts',
        # 21:30 UTC = 겨울(EST) 마감 21:00 + 30분 / 여름(EDT) 마감 20:00 + 1.5h — 연중 확정 종가.
        'schedule': crontab(hour=21, minute=30, day_of_week='mon-fri'),
        'args': ('US',),
    },
    # 증시 캘린더 일정 알림 — 매일 08:00 KST(=23:00 UTC). 당일 일정 묶음 1건.
    'evaluate-calendar-alerts': {
        'task': 'tasks.evaluate_calendar_alerts',
        'schedule': crontab(hour=23, minute=0),
    },
    # 가격 오틱(고립 스파이크) 클린업 — 매일 10:00 UTC(US/KR 장 마감 후). 증분 페치가 못 거른
    # 오틱을 DB 전체 이웃 기준으로 제거 → 겹쳐보기 등 raw 읽기경로 self-heal.
    'purge-price-spikes': {
        'task': 'tasks.purge_price_spikes',
        'schedule': crontab(hour=10, minute=0),
    },
    # 대가·예시 포폴 종목 전체기간 워밍업 — 매일 11:00 UTC(스파이크 클린업 후). 플래그면 no-op.
    'warmup-history': {
        'task': 'tasks.warmup_history',
        'schedule': crontab(hour=11, minute=0),
    },
    # 대가 시점별 NAV 곡선 재빌드 — 매일 11:30 UTC(워밍업 후). 비교/겹쳐보기 대가 곡선 소스.
    'refresh-guru-nav': {
        'task': 'tasks.refresh_guru_nav',
        'schedule': crontab(hour=11, minute=30),
    },
    # 데이터 무결성 상시 스캔(B-2②) — 매일 10:30 UTC(스파이크 클린업 후, 워밍업 전).
    # NULL홀 self-heal + 핵심 시계열 신선도 + 합성 손상 스캔. 이상 시 오너 알림+Sentry.
    'data-integrity-scan': {
        'task': 'tasks.data_integrity_scan',
        'schedule': crontab(hour=10, minute=30),
    },
}
