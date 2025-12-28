# Тесты буферизации загрузок

import pytest
from unittest.mock import AsyncMock, Mock, patch
from utils.bot_utils import BufferedUploader

pytestmark = pytest.mark.bot


def test_buffered_uploader_initialization():
    # BufferedUploader инициализируется правильно
    uploader = BufferedUploader("photo")

    assert uploader.content_type == "photo"
    assert uploader.max_items == 10
    assert uploader.timeout == 3


def test_buffered_uploader_get_buffer_key():
    # Правильное формирование ключа буфера
    uploader = BufferedUploader("photo")

    key = uploader.get_buffer_key()

    assert key == "photo_buffer"


def test_buffered_uploader_get_waiting_key():
    # Правильное формирование ключа ожидания
    uploader = BufferedUploader("file")

    key = uploader.get_waiting_key()

    assert key == "waiting_for_files"


@pytest.mark.asyncio
async def test_buffered_uploader_start_upload_mode():
    # start_upload_mode устанавливает флаг ожидания
    uploader = BufferedUploader("photo")

    mock_update = Mock()
    mock_update.effective_user.id = 12345

    mock_context = Mock()
    mock_context.user_data = {}

    await uploader.start_upload_mode(mock_update, mock_context)

    assert mock_context.user_data["waiting_for_photos"] is True
    assert mock_context.user_data["photo_buffer"] == []


def test_buffered_uploader_stop_upload_mode():
    # stop_upload_mode очищает флаг и буфер
    uploader = BufferedUploader("photo")

    mock_context = Mock()
    mock_context.user_data = {
        "waiting_for_photos": True,
        "photo_buffer": [{"test": "data"}],
        "photo_timer": None
    }

    uploader.stop_upload_mode(mock_context)

    assert mock_context.user_data["waiting_for_photos"] is False
    assert mock_context.user_data["photo_buffer"] == []


def test_buffered_uploader_is_waiting():
    # is_waiting правильно проверяет флаг
    uploader = BufferedUploader("photo")

    mock_context = Mock()
    mock_context.user_data = {"waiting_for_photos": True}

    assert uploader.is_waiting(mock_context) is True

    mock_context.user_data = {"waiting_for_photos": False}
    assert uploader.is_waiting(mock_context) is False


@pytest.mark.asyncio
async def test_buffered_uploader_add_to_buffer():
    # add_to_buffer добавляет элемент в буфер
    uploader = BufferedUploader("photo")

    mock_update = Mock()
    mock_update.effective_user.id = 12345
    mock_update.message.reply_text = AsyncMock(return_value=Mock(message_id=100))

    mock_context = Mock()
    mock_context.user_data = {"photo_buffer": []}
    mock_context.bot.edit_message_text = AsyncMock()

    with patch('asyncio.create_task'):
        await uploader.add_to_buffer(mock_update, mock_context, {"test": "data"})

    assert len(mock_context.user_data["photo_buffer"]) == 1
    assert mock_context.user_data["photo_buffer"][0] == {"test": "data"}