# Централизованная конфигурация проекта

import os
from dotenv import load_dotenv

load_dotenv()


# Настройки приложения из переменных окружения
class Settings:

    # Telegram
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN")

    # API
    API_URL: str = os.getenv("API_URL")
    API_HOST: str = os.getenv("API_HOST")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # Database
    DB_USER: str = os.getenv("DB_USER")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD")
    DB_HOST: str = os.getenv("DB_HOST")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME")

    # Yandex Cloud
    YC_BUCKET_NAME: str = os.getenv("YC_BUCKET_NAME")
    YANDEX_ACCESS_KEY: str = os.getenv("YANDEX_ACCESS_KEY")
    YANDEX_SECRET_KEY: str = os.getenv("YANDEX_SECRET_KEY")
    YANDEX_FOLDER_ID: str = os.getenv("YANDEX_FOLDER_ID")
    YANDEX_IAM_TOKEN: str = os.getenv("YANDEX_IAM_TOKEN")
    YANDEX_VISION_IAM_TOKEN: str = os.getenv("YANDEX_VISION_IAM_TOKEN")

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL")


# Глобальный экземпляр настроек
settings = Settings()


# Константы текстовых сообщений для пользователя
class Messages:

    # Сообщения об ошибках
    ERROR_CONNECTION = "⚠️ Ошибка подключения к серверу."
    ERROR_DATA = "⚠️ Ошибка получения данных."
    ERROR_UPLOAD = "⚠️ Ошибка при загрузке."
    ERROR_PROCESSING = "⚠️ Ошибка при обработке."

    # Сообщения о лимитах (используются с .format())
    LIMIT_STORAGE_EXCEEDED = "⚠️ Хранилище {content_type} заполнено!\n\nИспользовано: {current}/{limit} {unit}"
    LIMIT_DAILY_EXCEEDED = "⚠️ Дневной лимит загрузки {content_type} исчерпан!\n\nИспользовано сегодня: {current}/{limit} {unit}"

    # Подсказки пользователю
    UPGRADE_PROMPT = "💎 Увеличьте лимиты — купите подписку уровнем выше!"
    DAILY_RESET_INFO = "Дневной лимит обновится завтра."
    MAX_TIER_INFO = "Вы на максимальном тарифе. Удалите старые {content_type}, чтобы загрузить новые."


# Константы для лимитов и ограничений приложения
class Limits:

    # Настройки пагинации списков
    PAGINATION_ITEMS = 15  # Количество элементов на странице

    # Настройки буферизации загрузок
    BUFFER_MAX_ITEMS = 10  # Максимум элементов в буфере
    BUFFER_TIMEOUT_SEC = 3  # Таймаут отправки буфера (секунды)

    # Ограничения размера файлов
    MAX_FILE_SIZE_MB = 20  # Максимальный размер файла (МБ)
    MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # То же в байтах

    # Ограничения длины сообщений Telegram
    MAX_URLS_PER_MESSAGE = 10  # Максимум URL в одном сообщении
    CAPTION_MAX_LENGTH = 1024  # Максимальная длина caption
    MESSAGE_MAX_LENGTH = 4000  # Максимальная длина текстового сообщения
    TEXT_PREVIEW_LENGTH = 100  # Длина превью текста в списках

    # Таймауты для внешних запросов
    VIDEO_INFO_TIMEOUT_SEC = 15  # Таймаут получения информации о видео
    API_REQUEST_TIMEOUT_SEC = 30  # Таймаут запросов к API
    FILE_UPLOAD_TIMEOUT_SEC = 120  # Таймаут загрузки файлов

    # Настройки S3
    PRESIGNED_URL_EXPIRATION_SEC = 3600  # Время жизни presigned URL (1 час)


# Статусы обработки документов в базе знаний
class DocumentStatus:

    PENDING = "pending"  # Ожидает обработки
    PROCESSING = "processing"  # Обрабатывается
    COMPLETED = "completed"  # Обработан успешно
    FAILED = "failed"  # Ошибка обработки


# Конфигурация типов контента в базе знаний
CONTENT_CONFIG = {
    "text": {
        "icon": "📝",  # Иконка для отображения
        "title": "Текст",  # Единственное число
        "title_plural": "Тексты",  # Множественное число
        "title_plural_lower": "тексты",  # Для использования в предложениях
        "title_genitive": "текстов",  # Родительный падеж ("Хранилище текстов")
        "storage_key": "texts",  # Ключ в kb_storage из API
        "daily_key": "daily_texts",  # Ключ в kb_daily из API
        "unit": "шт",  # Единица измерения лимита
        "callbacks": {
            "upload": "upload_text",  # callback_data для кнопки загрузки
            "my_list": "my_texts",  # callback_data для кнопки списка
        },
        "api_endpoint": "/kb/upload/text",  # Эндпоинт API для загрузки
        "requires_buffer": False,  # Не требует буферизации
        "has_preview_button": False,  # Нет дополнительной кнопки превью
    },
    "video": {
        "icon": "🎥",
        "title": "Видео",
        "title_plural": "Видео",
        "title_plural_lower": "видео",
        "title_genitive": "видео",
        "storage_key": "video_hours",
        "daily_key": "daily_video_hours",
        "unit": "ч",
        "callbacks": {
            "upload": "upload_video",
            "my_list": "my_videos",
        },
        "api_endpoint": "/kb/upload/video",
        "requires_buffer": False,
        "has_preview_button": False,
        "has_link": True,  # В списке отображается как ссылка
    },
    "photo": {
        "icon": "🖼",
        "title": "Фото",
        "title_plural": "Фото",
        "title_plural_lower": "фото",
        "title_genitive": "фото",
        "storage_key": "photos",
        "daily_key": "daily_photos",
        "unit": "шт",
        "callbacks": {
            "upload": "upload_photo",
            "my_list": "my_photos",
        },
        "api_endpoint": "/kb/upload/photos",
        "requires_buffer": True,  # Требует буферизации (до 10 фото)
        "has_preview_button": True,  # Есть кнопка "Показать фото"
    },
    "file": {
        "icon": "📄",
        "title": "Файл",
        "title_plural": "Файлы",
        "title_plural_lower": "файлы",
        "title_genitive": "файлов",
        "storage_key": "files",
        "daily_key": "daily_files",
        "unit": "шт",
        "callbacks": {
            "upload": "upload_file_doc",
            "my_list": "my_files_docs",
        },
        "api_endpoint": "/kb/upload/files",
        "requires_buffer": True,  # Требует буферизации (до 10 файлов)
        "has_preview_button": False,
    },
}


# Шаблоны уведомлений для Celery задач
# Используются при отправке сообщений пользователю после обработки
NOTIFICATION_TEMPLATES = {
    "video": "✅ Видео обработано!\n\n🎥 {filename}",
    "photo": "✅ Фото обработано!\n\n📝 Распознанный текст:\n\n{text}",
    "photo_truncated": "✅ Фото обработано!\n\n📝 Распознанный текст:\n\n{text}...\n\n(Текст обрезан. Полный текст в базе знаний)",
    "file": "✅ Файл обработан!\n\n📄 {filename}\n\n📝 Распознано символов: {count}",
}