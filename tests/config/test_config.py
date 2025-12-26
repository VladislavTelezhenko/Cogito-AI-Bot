# Тесты конфигурации

import pytest
from shared.config import (
    settings, Messages, Limits, DocumentStatus,
    CONTENT_CONFIG, NOTIFICATION_TEMPLATES
)

pytestmark = pytest.mark.api


def test_settings_has_telegram_token():
    # Settings содержит токен Telegram
    assert hasattr(settings, 'TELEGRAM_TOKEN')


def test_settings_has_api_url():
    # Settings содержит API URL
    assert hasattr(settings, 'API_URL')


def test_settings_has_database_config():
    # Settings содержит настройки БД
    assert hasattr(settings, 'DB_USER')
    assert hasattr(settings, 'DB_PASSWORD')
    assert hasattr(settings, 'DB_HOST')
    assert hasattr(settings, 'DB_PORT')
    assert hasattr(settings, 'DB_NAME')


def test_settings_has_yandex_config():
    # Settings содержит настройки Yandex Cloud
    assert hasattr(settings, 'YC_BUCKET_NAME')
    assert hasattr(settings, 'YANDEX_ACCESS_KEY')
    assert hasattr(settings, 'YANDEX_SECRET_KEY')
    assert hasattr(settings, 'YANDEX_FOLDER_ID')


def test_messages_has_errors():
    # Messages содержит сообщения об ошибках
    assert hasattr(Messages, 'ERROR_CONNECTION')
    assert hasattr(Messages, 'ERROR_DATA')
    assert hasattr(Messages, 'ERROR_UPLOAD')
    assert hasattr(Messages, 'ERROR_PROCESSING')


def test_messages_has_limit_messages():
    # Messages содержит сообщения о лимитах
    assert hasattr(Messages, 'LIMIT_STORAGE_EXCEEDED')
    assert hasattr(Messages, 'LIMIT_DAILY_EXCEEDED')


def test_messages_has_upgrade_prompts():
    # Messages содержит подсказки об апгрейде
    assert hasattr(Messages, 'UPGRADE_PROMPT')
    assert hasattr(Messages, 'DAILY_RESET_INFO')
    assert hasattr(Messages, 'MAX_TIER_INFO')


def test_document_status_constants():
    # DocumentStatus содержит все статусы
    assert DocumentStatus.PENDING == "pending"
    assert DocumentStatus.PROCESSING == "processing"
    assert DocumentStatus.COMPLETED == "completed"
    assert DocumentStatus.FAILED == "failed"


def test_content_config_structure():
    # CONTENT_CONFIG имеет правильную структуру

    required_types = ["text", "video", "photo", "file"]

    for content_type in required_types:
        assert content_type in CONTENT_CONFIG

        config = CONTENT_CONFIG[content_type]

        # Проверяем обязательные поля
        assert "icon" in config
        assert "title" in config
        assert "title_plural" in config
        assert "storage_key" in config
        assert "daily_key" in config
        assert "unit" in config
        assert "callbacks" in config
        assert "api_endpoint" in config


def test_notification_templates_exist():
    # NOTIFICATION_TEMPLATES содержит шаблоны

    assert "video" in NOTIFICATION_TEMPLATES
    assert "photo" in NOTIFICATION_TEMPLATES
    assert "file" in NOTIFICATION_TEMPLATES


def test_notification_templates_use_placeholders():
    # Шаблоны используют правильные плейсхолдеры

    video_template = NOTIFICATION_TEMPLATES["video"]
    assert "{filename}" in video_template

    photo_template = NOTIFICATION_TEMPLATES["photo"]
    assert "{text}" in photo_template

    file_template = NOTIFICATION_TEMPLATES["file"]
    assert "{filename}" in file_template
    assert "{count}" in file_template


def test_limits_are_positive():
    # Все лимиты - положительные числа

    assert Limits.PAGINATION_ITEMS > 0
    assert Limits.BUFFER_MAX_ITEMS > 0
    assert Limits.BUFFER_TIMEOUT_SEC > 0
    assert Limits.MAX_FILE_SIZE_MB > 0
    assert Limits.MESSAGE_MAX_LENGTH > 0