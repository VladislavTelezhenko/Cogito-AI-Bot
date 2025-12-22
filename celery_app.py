# Обработка асинхронных запросов на перевод видео в текст и обновление токена
# celery -A celery_app worker --beat --loglevel=info --pool=solo

# Для работы Celery локально, нужно не забывать запускать redis-server.exe
from celery import Celery
from celery.schedules import crontab
import os
from dotenv import load_dotenv

load_dotenv()

celery_app = Celery(
    'cogito_bot',
    broker=os.getenv('REDIS_URL'),
    backend=os.getenv('REDIS_URL')
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Moscow',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600*3
)

# Обновление токенов Яндекса каждые 11 часов
celery_app.conf.beat_schedule = {
    'refresh-speechkit-token-every-11-hours': {
        'task': 's3_storage.refresh_iam_token',
        'schedule': crontab(minute=0, hour='*/11'),
    },
    'refresh-vision-token-every-11-hours': {
        'task': 's3_storage.refresh_vision_iam_token',
        'schedule': crontab(minute=0, hour='*/11'),
    },
}

# Импорт задач в конце, чтобы избежать циклической зависимости
# между этим файлом и s3_storage
if __name__ != '__main__':
    import s3_storage