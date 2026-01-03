"""
Конфигурация приложения.

Содержит настройки, лимиты, сообщения и конфигурацию типов контента.
"""

import os
import logging
import re
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
from pathlib import Path


# Загрузка переменных окружения
env_path = Path(__file__).parent.parent / 'secret' / '.env'
load_dotenv(dotenv_path=env_path)


# ============================================================================
# НАСТРОЙКИ ПРИЛОЖЕНИЯ
# ============================================================================

class Settings(BaseSettings):
    """Настройки приложения из переменных окружения."""

    # Telegram
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN")
    # ID админа для тикет-системы
    ADMIN_TELEGRAM_ID: int = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

    # API
    API_URL: str = os.getenv("API_URL", "http://localhost:8000")
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # Database
    DB_USER: str = os.getenv("DB_USER")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD")
    DB_HOST: str = os.getenv("DB_HOST")
    DB_PORT: str = os.getenv("DB_PORT")
    DB_NAME: str = os.getenv("DB_NAME")

    # Yandex Cloud
    YC_BUCKET_NAME: str = os.getenv("YC_BUCKET_NAME")
    YANDEX_ACCESS_KEY: str = os.getenv("YANDEX_ACCESS_KEY")
    YANDEX_SECRET_KEY: str = os.getenv("YANDEX_SECRET_KEY")
    YANDEX_FOLDER_ID: str = os.getenv("YANDEX_FOLDER_ID")
    YANDEX_IAM_TOKEN: str = os.getenv("YANDEX_IAM_TOKEN")
    YANDEX_VISION_IAM_TOKEN: str = os.getenv("YANDEX_VISION_IAM_TOKEN")
    YANDEX_VISION_FOLDER_ID: str = os.getenv("YANDEX_VISION_FOLDER_ID")

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    model_config = SettingsConfigDict(env_file=str(env_path))


settings = Settings()

# S3 Base URL
S3_BASE_URL = f"https://storage.yandexcloud.net/{settings.YC_BUCKET_NAME}"


# ============================================================================
# ЛИМИТЫ
# ============================================================================

class Limits:
    """Константы лимитов для различных операций."""

    # Файлы
    MAX_FILE_SIZE_MB = 20

    # Буферизация
    BUFFER_MAX_ITEMS = 10
    BUFFER_WAIT_TIME_SEC = 5

    # Видео
    VIDEO_INFO_TIMEOUT_SEC = 15

    # Сообщения
    MESSAGE_MAX_LENGTH = 4000

    # Специальное значение для безлимитных тарифов
    UNLIMITED = 9999


# ============================================================================
# СТАТУСЫ ДОКУМЕНТОВ
# ============================================================================

class DocumentStatus:
    """Статусы обработки документов."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# СООБЩЕНИЯ
# ============================================================================

class Messages:
    """Стандартные сообщения бота."""

    ERROR_CONNECTION = "⚠️ Ошибка подключения к серверу. Попробуйте позже."
    ERROR_DATA = "⚠️ Ошибка получения данных. Попробуйте /start"
    ERROR_UPLOAD = "⚠️ Ошибка загрузки. Попробуйте ещё раз или обратитесь в поддержку."

    UPGRADE_PROMPT = "💎 Купите подписку выше для увеличения лимитов!"
    MAX_TIER_INFO = "Вы на максимальном тарифе! Для увеличения лимитов напишите в поддержку."
    DAILY_RESET_INFO = "Дневные лимиты обновятся завтра в 00:00 UTC."


# ============================================================================
# КОНФИГУРАЦИЯ ТИПОВ КОНТЕНТА
# ============================================================================

CONTENT_CONFIG = {
    "text": {
        "icon": "📝",
        "title": "Текст",
        "title_plural": "Тексты",
        "title_plural_lower": "тексты",
        "title_genitive": "текстов",
        "title_accusative": "текст",
        "storage_key": "texts",
        "daily_key": "texts",
        "unit": "шт",
        "callbacks": {
            "upload": "upload_text",
            "my_list": "my_texts"
        },
        "api_endpoint": "/kb/upload/text"
    },
    "video": {
        "icon": "🎥",
        "title": "Видео",
        "title_plural": "Видео",
        "title_plural_lower": "видео",
        "title_genitive": "видео",
        "title_accusative": "видео",
        "storage_key": "video_hours",
        "daily_key": "video_hours",
        "unit": "ч",
        "callbacks": {
            "upload": "upload_video",
            "my_list": "my_videos"
        },
        "api_endpoint": "/kb/upload/video"
    },
    "photo": {
        "icon": "🖼",
        "title": "Фото",
        "title_plural": "Фото",
        "title_plural_lower": "фото",
        "title_genitive": "фото",
        "title_accusative": "фото",
        "storage_key": "photos",
        "daily_key": "photos",
        "unit": "шт",
        "callbacks": {
            "upload": "upload_photo",
            "my_list": "my_photos"
        },
        "api_endpoint": "/kb/upload/photos"
    },
    "file": {
        "icon": "📄",
        "title": "Файл",
        "title_plural": "Файлы",
        "title_plural_lower": "файлы",
        "title_genitive": "файлов",
        "title_accusative": "файл",
        "storage_key": "files",
        "daily_key": "files",
        "unit": "шт",
        "callbacks": {
            "upload": "upload_file_doc",
            "my_list": "my_files_docs"
        },
        "api_endpoint": "/kb/upload/files"
    }
}


# ============================================================================
# ШАБЛОНЫ УВЕДОМЛЕНИЙ
# ============================================================================

NOTIFICATION_TEMPLATES = {
    "video": (
        "✅ Видео обработано!\n\n"
        "📹 {filename}\n\n"
        "Теперь можете задавать вопросы по этому видео."
    ),

    "photo": (
        "✅ Фото обработано!\n\n"
        "🖼 Распознанный текст:\n\n"
        "{text}"
    ),

    "photo_truncated": (
        "✅ Фото обработано!\n\n"
        "🖼 Распознанный текст (первые 900 символов):\n\n"
        "{text}\n\n"
        "...\n\n"
        "📝 Полный текст доступен в базе знаний."
    ),

    "file": (
        "✅ Файл обработан!\n\n"
        "📄 {filename}\n"
        "📊 Извлечено символов: {count}\n\n"
        "Можете задавать вопросы по этому документу."
    )
}


# ============================================================================
# ЛОГИРОВАНИЕ
# ============================================================================

# Определяем путь к папке logs в корне проекта
BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / 'logs'

# Создание директории для логов
LOGS_DIR.mkdir(exist_ok=True)

# Базовая настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / 'app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


# ============================================================================
# ФИЛЬТР ЧУВСТВИТЕЛЬНЫХ ДАННЫХ (FIX #15)
# ============================================================================

class SensitiveDataFilter(logging.Filter):
    """
    Фильтр для маскирования чувствительных данных в логах.

    Маскирует: токены, ключи доступа, пароли, IAM токены.
    """

    # Паттерны для поиска чувствительных данных
    PATTERNS = [
        (re.compile(r'(bot[0-9]{8,10}:[a-zA-Z0-9_-]{35})'), 'BOT_TOKEN***'),  # Telegram токены
        (re.compile(r'(AQVN[a-zA-Z0-9_-]{100,})'), 'IAM_TOKEN***'),  # Yandex IAM
        (re.compile(r'(YC[a-zA-Z0-9_-]{30,})'), 'ACCESS_KEY***'),  # Yandex Access Keys
        (re.compile(r'(password["\s:=]+)([^"\s,}]+)'), r'\1***'),  # Пароли
        (re.compile(r'(token["\s:=]+)([^"\s,}]+)'), r'\1***'),  # Токены
        (re.compile(r'(secret["\s:=]+)([^"\s,}]+)'), r'\1***'),  # Секреты
        (re.compile(r'(api[_-]?key["\s:=]+)([^"\s,}]+)'), r'\1***'),  # API ключи
    ]

    def filter(self, record):
        """
        Фильтрация логов.

        Args:
            record: Запись лога

        Returns:
            True (всегда пропускаем запись после маскирования)
        """
        # Маскируем сообщение
        if isinstance(record.msg, str):
            for pattern, replacement in self.PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)

        # Маскируем args
        if record.args:
            masked_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    masked_arg = arg
                    for pattern, replacement in self.PATTERNS:
                        masked_arg = pattern.sub(replacement, masked_arg)
                    masked_args.append(masked_arg)
                else:
                    masked_args.append(arg)
            record.args = tuple(masked_args)

        return True


def apply_sensitive_filter_to_all_loggers():
    """Применить фильтр маскирования ко всем существующим логгерам."""
    sensitive_filter = SensitiveDataFilter()

    # Корневой логгер
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(sensitive_filter)

    # Все именованные логгеры
    for logger_name in list(logging.root.manager.loggerDict.keys()):
        logger_obj = logging.getLogger(logger_name)
        for handler in logger_obj.handlers:
            handler.addFilter(sensitive_filter)


# Применяем фильтр при инициализации модуля
apply_sensitive_filter_to_all_loggers()


# ============================================================================
# ВАЛИДАЦИЯ НАСТРОЕК
# ============================================================================

def validate_settings():
    """Проверка наличия обязательных переменных окружения."""
    required_vars = [
        'TELEGRAM_TOKEN',
        'DB_USER',
        'DB_PASSWORD',
        'DB_HOST',
        'DB_NAME',
        'YC_BUCKET_NAME',
        'YANDEX_ACCESS_KEY',
        'YANDEX_SECRET_KEY',
        'YANDEX_FOLDER_ID'
    ]

    missing = []
    for var in required_vars:
        if not getattr(settings, var, None):
            missing.append(var)

    if missing:
        logger.error(f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}")
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    logger.info("✓ Все обязательные переменные окружения настроены")


# Валидируем настройки при импорте
try:
    validate_settings()
except ValueError as e:
    logger.warning(f"Предупреждение при валидации настроек: {e}")