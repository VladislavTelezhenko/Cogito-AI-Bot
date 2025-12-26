# Тесты утилит бота

import pytest
from unittest.mock import AsyncMock, Mock, patch
from bot.bot_utils import check_upload_limits, ButtonFactory
from shared.config import CONTENT_CONFIG

pytestmark = pytest.mark.bot


@pytest.mark.asyncio
async def test_check_upload_limits_free_user_text():
    # Проверка лимитов для free пользователя (текст)

    mock_stats = {
        "subscription_tier": "free",
        "kb_storage": {"texts": "0/5"},
        "kb_daily": {"daily_texts": "0/5"}
    }

    with patch('bot.bot_utils.get_user_stats', return_value=(True, mock_stats, None)):
        can_upload, error, keyboard = await check_upload_limits(12345, "text")

    assert can_upload is True
    assert error == ""


@pytest.mark.asyncio
async def test_check_upload_limits_storage_exceeded():
    # Проверка превышения лимита хранилища

    mock_stats = {
        "subscription_tier": "free",
        "kb_storage": {"texts": "5/5"},  # Хранилище заполнено
        "kb_daily": {"daily_texts": "0/5"}
    }

    with patch('bot.bot_utils.get_user_stats', return_value=(True, mock_stats, None)):
        can_upload, error, keyboard = await check_upload_limits(12345, "text")

    assert can_upload is False
    assert "хранилища" in error.lower()


@pytest.mark.asyncio
async def test_check_upload_limits_daily_exceeded():
    # Проверка превышения дневного лимита

    mock_stats = {
        "subscription_tier": "free",
        "kb_storage": {"texts": "3/5"},
        "kb_daily": {"daily_texts": "5/5"}  # Дневной лимит исчерпан
    }

    with patch('bot.bot_utils.get_user_stats', return_value=(True, mock_stats, None)):
        can_upload, error, keyboard = await check_upload_limits(12345, "text")

    assert can_upload is False
    assert "дневной" in error.lower()


@pytest.mark.asyncio
async def test_check_upload_limits_unlimited_tier():
    # Проверка для безлимитного тарифа

    mock_stats = {
        "subscription_tier": "ultra",
        "kb_storage": {"texts": "100/∞"},
        "kb_daily": {"daily_texts": "50/∞"}
    }

    with patch('bot.bot_utils.get_user_stats', return_value=(True, mock_stats, None)):
        can_upload, error, keyboard = await check_upload_limits(12345, "text")

    assert can_upload is True


@pytest.mark.asyncio
async def test_check_upload_limits_api_error():
    # Проверка при ошибке API

    with patch('bot.bot_utils.get_user_stats', return_value=(False, None, "API Error")):
        can_upload, error, keyboard = await check_upload_limits(12345, "text")

    assert can_upload is False
    assert len(keyboard) > 0


def test_button_factory_back_to_main():
    # ButtonFactory создаёт кнопку "Главное меню"
    button = ButtonFactory.back_to_main()

    assert button.text == "🏠 Главное меню"
    assert button.callback_data == "back_to_main"


def test_button_factory_back_button():
    # ButtonFactory создаёт кнопку "Назад"
    button = ButtonFactory.back_button("test_callback")

    assert button.text == "◀️ Назад"
    assert button.callback_data == "test_callback"


def test_button_factory_upload_more():
    # ButtonFactory создаёт кнопку "Загрузить ещё"
    button = ButtonFactory.upload_more("text")

    assert "Загрузить ещё" in button.text
    assert button.callback_data == "upload_text"


def test_button_factory_success_keyboard():
    # ButtonFactory создаёт клавиатуру после успеха
    keyboard = ButtonFactory.success_keyboard("text")

    assert len(keyboard) == 2  # 2 строки
    assert len(keyboard[0]) == 2  # 2 кнопки в первой строке
    assert len(keyboard[1]) == 1  # 1 кнопка во второй строке


def test_content_config_has_all_types():
    # CONTENT_CONFIG содержит все типы контента

    expected_types = ["text", "video", "photo", "file"]

    for content_type in expected_types:
        assert content_type in CONTENT_CONFIG


def test_content_config_has_required_keys():
    # Каждый тип в CONTENT_CONFIG имеет необходимые ключи

    required_keys = [
        "icon", "title", "title_plural", "storage_key",
        "daily_key", "unit", "callbacks", "api_endpoint"
    ]

    for content_type, config in CONTENT_CONFIG.items():
        for key in required_keys:
            assert key in config, f"{content_type} missing {key}"


def test_content_config_callbacks_valid():
    # Callbacks в CONTENT_CONFIG валидны

    for content_type, config in CONTENT_CONFIG.items():
        callbacks = config["callbacks"]

        assert "upload" in callbacks
        assert "my_list" in callbacks
        assert isinstance(callbacks["upload"], str)
        assert isinstance(callbacks["my_list"], str)