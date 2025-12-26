# Обработка асинхронных запросов на перевод видео в текст и обновление токена
# celery -A backend.celery_app worker --beat --loglevel=info --pool=solo

# Для работы Celery локально, нужно не забывать запускать redis-server.exe

from celery import Celery
from celery.schedules import crontab
from shared.config import settings

# Инициализация Celery
celery_app = Celery(
    'cogito_bot',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# Конфигурация Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Moscow',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600 * 3,

    # Настройки приоритизации задач
    task_acks_late=True,  # Подтверждение после выполнения задачи
    worker_prefetch_multiplier=1,  # Берёт по 1 задаче за раз
    task_default_priority=5,  # Приоритет по умолчанию (средний)
    task_queue_max_priority=10  # Максимальный приоритет (0=высший, 10=низший)
)

# Обновление токенов Яндекса каждые 11 часов
celery_app.conf.beat_schedule = {
    'refresh-speechkit-token-every-11-hours': {
        'task': 'backend.s3_storage.refresh_iam_token',
        'schedule': crontab(minute=0, hour='*/11'),
    },
    'refresh-vision-token-every-11-hours': {
        'task': 'backend.s3_storage.refresh_vision_iam_token',
        'schedule': crontab(minute=0, hour='*/11'),
    },
}

# Импорт задач в конце, чтобы избежать циклической зависимости
if __name__ != '__main__':
    from backend import s3_storage