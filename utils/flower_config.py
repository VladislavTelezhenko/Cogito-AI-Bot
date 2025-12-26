# Конфигурация Flower для мониторинга Celery

from shared.config import settings

# Настройки Flower
FLOWER_CONFIG = {
    # Основные настройки
    'broker': settings.REDIS_URL,
    'port': 5555,
    'address': '127.0.0.1',

    # Включить базовую аутентификацию (опционально)
    'basic_auth': None,  # Формат: ['user:password']

    # Персистентность (сохранение данных)
    'db': 'flower.db',
    'persistent': True,

    # Настройки отображения
    'max_tasks': 10000,
    'enable_events': True,

    # Автообновление
    'auto_refresh': True,
    'purge_offline_workers': 60,  # Удалять оффлайн воркеры через 60 сек

    # URL префикс (если запускаешь за reverse proxy)
    'url_prefix': '',

    # Логирование
    'logging': 'INFO'
}

# Кастомные колонки для отображения задач
TASK_COLUMNS = [
    'name',  # Название задачи
    'uuid',  # ID задачи
    'state',  # Статус (PENDING, STARTED, SUCCESS, FAILURE)
    'args',  # Аргументы
    'kwargs',  # Именованные аргументы
    'result',  # Результат
    'received',  # Время получения
    'started',  # Время начала
    'runtime',  # Время выполнения
    'worker',  # Какой воркер обрабатывает
    'retries',  # Количество повторов
    'priority',  # Приоритет (важно для нас!)
]

# Цвета для статусов задач (CSS классы)
TASK_STATUS_COLORS = {
    'PENDING': 'warning',  # Жёлтый
    'STARTED': 'info',  # Синий
    'SUCCESS': 'success',  # Зелёный
    'FAILURE': 'danger',  # Красный
    'RETRY': 'warning',  # Жёлтый
    'REVOKED': 'muted',  # Серый
}

# Кастомные фильтры для задач
TASK_FILTERS = {
    'video_tasks': {
        'name': 'Видео',
        'filter': lambda task: 'process_video' in task.name
    },
    'photo_tasks': {
        'name': 'Фото',
        'filter': lambda task: 'process_photo' in task.name
    },
    'file_tasks': {
        'name': 'Файлы',
        'filter': lambda task: 'process_file' in task.name
    },
    'token_tasks': {
        'name': 'Обновление токенов',
        'filter': lambda task: 'refresh_' in task.name
    }
}