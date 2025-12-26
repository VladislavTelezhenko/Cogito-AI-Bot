# Расширенные тесты утилит бота

import pytest
from unittest.mock import AsyncMock, Mock, patch
from bot.bot_utils import api_request, get_user_stats, safe_message_edit, paginate_documents
from shared.config import Limits

pytestmark = pytest.mark.bot


@pytest.mark.asyncio
async def test_api_request_success():
    # Успешный API запрос

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "success"}

    with patch('httpx.AsyncClient') as mock_client:
        mock_context = Mock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_context)
        mock_context.__aexit__ = AsyncMock()
        mock_context.get = AsyncMock(return_value=mock_response)

        mock_client.return_value = mock_context

        success, data, error = await api_request("GET", "/test")

    assert success is True
    assert data == {"result": "success"}
    assert error is None


@pytest.mark.asyncio
async def test_api_request_404_error():
    # API запрос возвращает 404

    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.text = "Not found"

    with patch('httpx.AsyncClient') as mock_client:
        mock_context = Mock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_context)
        mock_context.__aexit__ = AsyncMock()
        mock_context.get = AsyncMock(return_value=mock_response)

        mock_client.return_value = mock_context

        success, data, error = await api_request("GET", "/nonexistent")

    assert success is False
    assert data is None
    assert "404" in error


@pytest.mark.asyncio
async def test_api_request_timeout():
    # API запрос превышает таймаут

    with patch('httpx.AsyncClient') as mock_client:
        mock_context = Mock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_context)
        mock_context.__aexit__ = AsyncMock()
        mock_context.get = AsyncMock(side_effect=Exception("Timeout"))

        mock_client.return_value = mock_context

        success, data, error = await api_request("GET", "/slow")

    assert success is False
    assert "Timeout" in error or "Ошибка запроса" in error


@pytest.mark.asyncio
async def test_api_request_post_method():
    # API запрос с методом POST

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"created": True}

    with patch('httpx.AsyncClient') as mock_client:
        mock_context = Mock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_context)
        mock_context.__aexit__ = AsyncMock()
        mock_context.post = AsyncMock(return_value=mock_response)

        mock_client.return_value = mock_context

        success, data, error = await api_request("POST", "/create", json={"test": "data"})

    assert success is True
    assert data["created"] is True


@pytest.mark.asyncio
async def test_get_user_stats_success():
    # Успешное получение статистики

    mock_stats = {
        "subscription_name": "Free",
        "subscription_tier": "free",
        "messages_today": 5,
        "messages_limit": 20
    }

    with patch('bot.bot_utils.api_request', return_value=(True, mock_stats, None)):
        success, stats, error = await get_user_stats(12345)

    assert success is True
    assert stats == mock_stats
    assert error is None


@pytest.mark.asyncio
async def test_get_user_stats_api_error():
    # Ошибка при получении статистики

    with patch('bot.bot_utils.api_request', return_value=(False, None, "API Error")):
        success, stats, error = await get_user_stats(12345)

    assert success is False
    assert stats is None
    assert error == "API Error"


@pytest.mark.asyncio
async def test_safe_message_edit_text_message():
    # Редактирование текстового сообщения

    mock_query = Mock()
    mock_query.message.photo = None
    mock_query.edit_message_text = AsyncMock()

    mock_context = Mock()

    await safe_message_edit(
        mock_query,
        mock_context,
        "New text",
        reply_markup=None
    )

    mock_query.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_safe_message_edit_photo_message():
    # Редактирование сообщения с фото (удаляем и отправляем новое)

    mock_query = Mock()
    mock_query.from_user.id = 12345
    mock_query.message.photo = ["fake_photo"]
    mock_query.message.delete = AsyncMock()

    mock_context = Mock()
    mock_context.bot.send_message = AsyncMock()

    await safe_message_edit(
        mock_query,
        mock_context,
        "New text"
    )

    mock_query.message.delete.assert_called_once()
    mock_context.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_paginate_documents_single_page():
    # Пагинация с одной страницей

    documents = [
        {
            "id": 1,
            "filename": "test1.txt",
            "file_type": "text",
            "upload_date": "2025-01-01T12:00:00",
            "extracted_text": "Content 1"
        },
        {
            "id": 2,
            "filename": "test2.txt",
            "file_type": "text",
            "upload_date": "2025-01-02T12:00:00",
            "extracted_text": "Content 2"
        }
    ]

    mock_query = Mock()
    mock_query.edit_message_text = AsyncMock()

    mock_context = Mock()

    await paginate_documents(documents, "text", mock_context, mock_query, 12345)

    # Должен вызваться edit_message_text один раз
    mock_query.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_paginate_documents_multiple_pages():
    # Пагинация с несколькими страницами

    # Создаём 20 документов (больше чем Limits.PAGINATION_ITEMS = 15)
    documents = [
        {
            "id": i,
            "filename": f"test{i}.txt",
            "file_type": "text",
            "upload_date": "2025-01-01T12:00:00",
            "extracted_text": f"Content {i}"
        }
        for i in range(20)
    ]

    mock_query = Mock()
    mock_query.edit_message_text = AsyncMock()
    mock_query.message.photo = None

    mock_context = Mock()
    mock_context.bot.send_message = AsyncMock()

    await paginate_documents(documents, "text", mock_context, mock_query, 12345)

    # Первая страница - edit_message_text
    mock_query.edit_message_text.assert_called_once()

    # Вторая страница - send_message
    mock_context.bot.send_message.assert_called()


def test_limits_constants():
    # Проверка констант лимитов

    assert Limits.PAGINATION_ITEMS == 15
    assert Limits.BUFFER_MAX_ITEMS == 10
    assert Limits.BUFFER_TIMEOUT_SEC == 3
    assert Limits.MAX_FILE_SIZE_MB == 20
    assert Limits.MAX_FILE_SIZE_BYTES == 20 * 1024 * 1024
    assert Limits.MESSAGE_MAX_LENGTH == 4000
    assert Limits.TEXT_PREVIEW_LENGTH == 100


def test_limits_video_info_timeout():
    # Проверка таймаута для видео

    assert Limits.VIDEO_INFO_TIMEOUT_SEC == 15
    assert isinstance(Limits.VIDEO_INFO_TIMEOUT_SEC, int)


def test_limits_api_timeouts():
    # Проверка таймаутов API

    assert Limits.API_REQUEST_TIMEOUT_SEC == 30
    assert Limits.FILE_UPLOAD_TIMEOUT_SEC == 120