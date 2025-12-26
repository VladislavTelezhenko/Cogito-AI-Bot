# Расширенные тесты S3 storage

import pytest
from unittest.mock import Mock, patch, MagicMock
import io

pytestmark = pytest.mark.celery


def test_extract_text_from_docx():
    # Извлечение текста из DOCX
    from backend.s3_storage import extract_text_from_docx

    # Мокируем Document
    with patch('backend.s3_storage.Document') as mock_doc_class:
        mock_doc = Mock()

        # Создаём mock параграфы
        mock_para1 = Mock()
        mock_para1.text = "First paragraph"

        mock_para2 = Mock()
        mock_para2.text = "Second paragraph"

        mock_doc.paragraphs = [mock_para1, mock_para2]
        mock_doc.part.rels.values.return_value = []

        mock_doc_class.return_value = mock_doc

        fake_bytes = b"fake_docx_data"
        text = extract_text_from_docx(fake_bytes)

    assert "First paragraph" in text
    assert "Second paragraph" in text


def test_extract_text_from_pdf_ocr():
    # Извлечение текста из PDF через OCR
    from backend.s3_storage import extract_text_from_pdf_ocr

    with patch('backend.s3_storage.convert_from_bytes') as mock_convert, \
            patch('backend.s3_storage.requests.post') as mock_post:
        # Мокируем конвертацию PDF в изображения
        mock_image = Mock()
        mock_image.save = Mock()
        mock_convert.return_value = [mock_image]

        # Мокируем OCR ответ
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{
                "results": [{
                    "textDetection": {
                        "pages": [{
                            "blocks": [{
                                "lines": [{
                                    "words": [
                                        {"text": "PDF"},
                                        {"text": "text"}
                                    ]
                                }]
                            }]
                        }]
                    }
                }]
            }]
        }
        mock_post.return_value = mock_response

        fake_pdf_bytes = b"fake_pdf_data"
        text = extract_text_from_pdf_ocr(fake_pdf_bytes)

    assert "PDF text" in text


def test_convert_to_jpeg_for_ocr():
    # Конвертация изображения в JPEG для OCR
    from bot.bot_knowledge_base import convert_to_jpeg_for_ocr
    from PIL import Image
    import base64

    # Создаём фейковое PNG изображение
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    png_bytes = img_bytes.getvalue()

    # Конвертируем
    jpeg_base64 = convert_to_jpeg_for_ocr(png_bytes)

    # Проверяем что это валидный base64
    decoded = base64.b64decode(jpeg_base64)
    assert len(decoded) > 0

    # Проверяем что это JPEG
    assert decoded[:2] == b'\xff\xd8'  # JPEG magic bytes


def test_convert_rgba_to_jpeg():
    # Конвертация RGBA в JPEG
    from bot.bot_knowledge_base import convert_to_jpeg_for_ocr
    from PIL import Image

    # Создаём RGBA изображение
    img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    rgba_bytes = img_bytes.getvalue()

    # Конвертируем
    jpeg_base64 = convert_to_jpeg_for_ocr(rgba_bytes)

    # Должно пройти без ошибок
    assert isinstance(jpeg_base64, str)
    assert len(jpeg_base64) > 0


def test_notify_user_success_text():
    # Отправка уведомления об успешной обработке текста
    from backend.s3_storage import notify_user_success
    import asyncio

    with patch('backend.s3_storage.NotificationService') as mock_service:
        mock_service.send_success = AsyncMock()

        asyncio.run(notify_user_success(
            telegram_id=12345,
            content_type="text",
            text="Test text"
        ))

        mock_service.send_success.assert_called_once()


def test_refresh_iam_token_task():
    # Задача обновления IAM токена
    from backend.s3_storage import refresh_iam_token

    with patch('backend.s3_storage.get_new_iam_token') as mock_refresh:
        mock_refresh.return_value = "new_token"

        refresh_iam_token()

        mock_refresh.assert_called_once()


def test_refresh_vision_iam_token_task():
    # Задача обновления Vision IAM токена
    from backend.s3_storage import refresh_vision_iam_token

    with patch('backend.s3_storage.get_new_vision_iam_token') as mock_refresh:
        mock_refresh.return_value = "new_vision_token"

        refresh_vision_iam_token()

        mock_refresh.assert_called_once()