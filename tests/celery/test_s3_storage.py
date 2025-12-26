# Тесты функций работы с S3

import pytest
from unittest.mock import Mock, patch, MagicMock
import base64
import io

pytestmark = pytest.mark.celery


def test_upload_photo_to_s3_creates_correct_key():
    # upload_photo_to_s3 создаёт правильный путь в S3
    from backend.s3_storage import upload_photo_to_s3

    # Создаём фейковый base64
    fake_image = base64.b64encode(b"fake_image_data").decode('utf-8')

    with patch('backend.s3_storage.s3_client') as mock_s3:
        mock_s3.put_object.return_value = {"ETag": "fake"}

        s3_key = upload_photo_to_s3(fake_image, user_id=123, document_id=456)

        assert s3_key == "photos/user_123/photo_456.jpg"
        mock_s3.put_object.assert_called_once()


def test_upload_file_to_s3_creates_correct_key():
    # upload_file_to_s3 создаёт правильный путь с расширением
    from backend.s3_storage import upload_file_to_s3

    fake_file = base64.b64encode(b"fake_file_data").decode('utf-8')

    with patch('backend.s3_storage.s3_client') as mock_s3:
        mock_s3.put_object.return_value = {"ETag": "fake"}

        s3_key = upload_file_to_s3(fake_file, user_id=789, document_id=101, extension="pdf")

        assert s3_key == "files/user_789/document_101.pdf"
        mock_s3.put_object.assert_called_once()


def test_delete_from_s3_calls_delete_object():
    # delete_from_s3 вызывает s3_client.delete_object
    from backend.s3_storage import delete_from_s3

    with patch('backend.s3_storage.s3_client') as mock_s3:
        mock_s3.delete_object.return_value = {}

        result = delete_from_s3("test/path/file.jpg")

        assert result is True
        mock_s3.delete_object.assert_called_once_with(
            Bucket='cogito-ai-bot',
            Key='test/path/file.jpg'
        )


def test_delete_from_s3_handles_errors():
    # delete_from_s3 обрабатывает ошибки
    from backend.s3_storage import delete_from_s3

    with patch('backend.s3_storage.s3_client') as mock_s3:
        mock_s3.delete_object.side_effect = Exception("S3 Error")

        result = delete_from_s3("test/path/file.jpg")

        assert result is False


def test_get_photo_presigned_url_generates_url():
    # get_photo_presigned_url генерирует presigned URL
    from backend.s3_storage import get_photo_presigned_url

    with patch('backend.s3_storage.s3_client') as mock_s3:
        mock_s3.generate_presigned_url.return_value = "https://fake-url.com"

        url = get_photo_presigned_url("photos/user_1/photo_1.jpg")

        assert url == "https://fake-url.com"
        mock_s3.generate_presigned_url.assert_called_once()


def test_recognize_text_yandex_extracts_text():
    # recognize_text_yandex извлекает текст из ответа Vision API
    from backend.s3_storage import recognize_text_yandex

    fake_response = {
        "results": [{
            "results": [{
                "textDetection": {
                    "pages": [{
                        "blocks": [{
                            "lines": [{
                                "words": [
                                    {"text": "Привет"},
                                    {"text": "мир"}
                                ]
                            }]
                        }]
                    }]
                }
            }]
        }]
    }

    with patch('backend.s3_storage.requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = fake_response
        mock_post.return_value = mock_response

        text = recognize_text_yandex(b"fake_image_bytes")

        assert "Привет мир" in text


def test_recognize_text_yandex_returns_empty_on_error():
    # recognize_text_yandex возвращает пустую строку при ошибке
    from backend.s3_storage import recognize_text_yandex

    with patch('backend.s3_storage.requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Error"
        mock_post.return_value = mock_response

        text = recognize_text_yandex(b"fake_image_bytes")

        assert text == ""


def test_extract_text_from_txt_utf8():
    # extract_text_from_txt читает UTF-8
    from backend.s3_storage import extract_text_from_txt

    text_bytes = "Привет мир".encode('utf-8')

    result = extract_text_from_txt(text_bytes)

    assert result == "Привет мир"


def test_extract_text_from_txt_cp1251():
    # extract_text_from_txt читает CP1251
    from backend.s3_storage import extract_text_from_txt

    text_bytes = "Привет мир".encode('cp1251')

    result = extract_text_from_txt(text_bytes)

    assert result == "Привет мир"


def test_update_document_status_calls_api():
    # update_document_status отправляет PUT запрос
    from backend.s3_storage import update_document_status

    with patch('backend.s3_storage.httpx.put') as mock_put:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_put.return_value = mock_response

        update_document_status(123, "completed", transcription="Test text")

        mock_put.assert_called_once()
        call_args = mock_put.call_args
        assert "123" in str(call_args)