# Расширенные тесты эндпоинтов базы знаний

import pytest
from unittest.mock import Mock, patch, AsyncMock
from backend.models import UserDocument

pytestmark = pytest.mark.api


def test_upload_video_endpoint(client, free_user_data, db_session):
    # Тест загрузки видео через API
    from backend.models import User, SubscriptionTier, UserSubscription
    from datetime import datetime

    # Регистрируем пользователя
    client.post("/users/register", json=free_user_data)

    # Меняем тариф на premium (у free нет лимита на видео)
    user = db_session.query(User).filter_by(
        telegram_id=free_user_data["telegram_id"]
    ).first()

    premium_tier = db_session.query(SubscriptionTier).filter_by(
        tier_name="premium"
    ).first()

    old_sub = db_session.query(UserSubscription).filter_by(
        user_id=user.id,
        status="active"
    ).first()
    old_sub.status = "expired"

    new_sub = UserSubscription(
        user_id=user.id,
        tier_id=premium_tier.id,
        status="active",
        source="test",
        start_date=datetime.now()
    )
    db_session.add(new_sub)
    db_session.commit()

    # Мокируем Celery task
    with patch('backend.main.process_video') as mock_task:
        mock_result = Mock()
        mock_result.id = "fake-task-id"
        mock_task.apply_async.return_value = mock_result

        video_data = {
            "telegram_id": free_user_data["telegram_id"],
            "videos": [
                {
                    "url": "https://youtube.com/watch?v=test",
                    "title": "Test Video",
                    "duration": 0.5
                }
            ]
        }

        response = client.post("/kb/upload/video", json=video_data)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "task_id" in data
    assert "message" in data


def test_upload_video_creates_pending_document(client, premium_user_data, db_session):
    # Загрузка видео создаёт pending документ
    from backend.models import User, SubscriptionTier, UserSubscription
    from datetime import datetime

    client.post("/users/register", json=premium_user_data)

    user = db_session.query(User).filter_by(
        telegram_id=premium_user_data["telegram_id"]
    ).first()

    premium_tier = db_session.query(SubscriptionTier).filter_by(
        tier_name="premium"
    ).first()

    old_sub = db_session.query(UserSubscription).filter_by(
        user_id=user.id,
        status="active"
    ).first()
    old_sub.status = "expired"

    new_sub = UserSubscription(
        user_id=user.id,
        tier_id=premium_tier.id,
        status="active",
        source="test",
        start_date=datetime.now()
    )
    db_session.add(new_sub)
    db_session.commit()

    with patch('backend.main.process_video') as mock_task:
        mock_result = Mock()
        mock_result.id = "fake-task-id"
        mock_task.apply_async.return_value = mock_result

        video_data = {
            "telegram_id": premium_user_data["telegram_id"],
            "videos": [
                {
                    "url": "https://youtube.com/watch?v=test",
                    "title": "Test Video",
                    "duration": 0.5
                }
            ]
        }

        client.post("/kb/upload/video", json=video_data)

    # Проверяем что создался документ
    doc = db_session.query(UserDocument).filter_by(
        user_id=user.id,
        file_type="video"
    ).first()

    assert doc is not None
    assert doc.status == "pending"
    assert doc.filename == "Test Video"
    assert doc.duration_hours == 0.5


def test_upload_photos_endpoint(client, free_user_data):
    # Тест загрузки фото через API

    # У free тарифа лимит фото = 0, меняем на premium
    from backend.models import User, SubscriptionTier, UserSubscription
    from datetime import datetime

    client.post("/users/register", json=free_user_data)

    # Меняем тариф
    # (используем db_session из фикстуры через client)

    with patch('backend.main.upload_photo_to_s3') as mock_upload, \
            patch('backend.main.process_photo_ocr') as mock_task:
        mock_upload.return_value = "photos/user_1/photo_1.jpg"

        mock_result = Mock()
        mock_result.id = "fake-task-id"
        mock_task.apply_async.return_value = mock_result

        # Тест с free тарифом должен вернуть ошибку лимита
        photo_data = {
            "telegram_id": free_user_data["telegram_id"],
            "photos": [
                {
                    "base64": "fake_base64_data",
                    "filename": "test.jpg"
                }
            ]
        }

        response = client.post("/kb/upload/photos", json=photo_data)

    # Free тариф - должна быть ошибка лимита
    assert response.status_code == 400
    assert "limit exceeded" in response.json()["detail"].lower()


def test_upload_files_endpoint(client, free_user_data):
    # Тест загрузки файлов через API

    client.post("/users/register", json=free_user_data)

    with patch('backend.main.upload_file_to_s3') as mock_upload, \
            patch('backend.main.process_file') as mock_task:
        mock_upload.return_value = "files/user_1/document_1.txt"

        mock_result = Mock()
        mock_result.id = "fake-task-id"
        mock_task.apply_async.return_value = mock_result

        file_data = {
            "telegram_id": free_user_data["telegram_id"],
            "files": [
                {
                    "filename": "test.txt",
                    "file_bytes": "ZmFrZV9maWxlX2RhdGE=",  # base64
                    "mime_type": "text/plain"
                }
            ]
        }

        response = client.post("/kb/upload/files", json=file_data)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["uploaded_count"] == 1
    assert len(data["task_ids"]) == 1


def test_get_photo_presigned_url_endpoint(client, free_user_data, db_session):
    # Тест получения presigned URL для фото
    from backend.models import User

    client.post("/users/register", json=free_user_data)

    user = db_session.query(User).filter_by(
        telegram_id=free_user_data["telegram_id"]
    ).first()

    # Создаём фото документ
    doc = UserDocument(
        user_id=user.id,
        filename="test.jpg",
        file_type="photo",
        status="completed",
        file_url="https://storage.yandexcloud.net/cogito-ai-bot/photos/user_1/photo_1.jpg"
    )
    db_session.add(doc)
    db_session.commit()

    with patch('backend.main.get_photo_presigned_url') as mock_presigned:
        mock_presigned.return_value = "https://fake-presigned-url.com"

        response = client.get(f"/kb/photo/{doc.id}/presigned")

    assert response.status_code == 200
    data = response.json()

    assert "presigned_url" in data
    assert data["expires_in"] == 3600


def test_get_photo_presigned_url_nonexistent(client):
    # Тест получения presigned URL для несуществующего фото

    response = client.get("/kb/photo/999999/presigned")

    assert response.status_code == 404


def test_get_document_info_endpoint(client, free_user_data, db_session):
    # Тест получения информации о документе
    from backend.models import User

    client.post("/users/register", json=free_user_data)

    user = db_session.query(User).filter_by(
        telegram_id=free_user_data["telegram_id"]
    ).first()

    # Создаём документ
    doc = UserDocument(
        user_id=user.id,
        filename="test.txt",
        file_type="text",
        status="completed",
        extracted_text="Test content"
    )
    db_session.add(doc)
    db_session.commit()

    response = client.get(f"/kb/documents/{doc.id}/info")

    assert response.status_code == 200
    data = response.json()

    assert data["telegram_id"] == free_user_data["telegram_id"]
    assert data["filename"] == "test.txt"
    assert data["extracted_text"] == "Test content"
    assert data["status"] == "completed"


def test_get_video_status_endpoint(client):
    # Тест получения статуса обработки видео

    with patch('backend.main.AsyncResult') as mock_result:
        mock_task = Mock()
        mock_task.state = "SUCCESS"
        mock_task.info = {"progress": "100%"}
        mock_result.return_value = mock_task

        response = client.get("/kb/video/status/fake-task-id")

    assert response.status_code == 200
    data = response.json()

    assert data["task_id"] == "fake-task-id"
    assert data["status"] == "success"


def test_update_document_status_endpoint(client, free_user_data, db_session):
    # Тест обновления статуса документа
    from backend.models import User

    client.post("/users/register", json=free_user_data)

    user = db_session.query(User).filter_by(
        telegram_id=free_user_data["telegram_id"]
    ).first()

    # Создаём документ
    doc = UserDocument(
        user_id=user.id,
        filename="test_video.mp4",
        file_type="video",
        status="pending"
    )
    db_session.add(doc)
    db_session.commit()

    # Обновляем статус
    update_data = {
        "status": "completed",
        "transcription": "Video transcription text"
    }

    response = client.put(f"/kb/documents/{doc.id}/status", json=update_data)

    assert response.status_code == 200
    assert response.json()["success"] is True

    # Проверяем что статус обновился
    db_session.refresh(doc)
    assert doc.status == "completed"
    assert doc.extracted_text == "Video transcription text"


def test_update_document_status_with_error(client, free_user_data, db_session):
    # Тест обновления статуса с ошибкой
    from backend.models import User

    client.post("/users/register", json=free_user_data)

    user = db_session.query(User).filter_by(
        telegram_id=free_user_data["telegram_id"]
    ).first()

    doc = UserDocument(
        user_id=user.id,
        filename="test.mp4",
        file_type="video",
        status="processing"
    )
    db_session.add(doc)
    db_session.commit()

    # Обновляем с ошибкой
    update_data = {
        "status": "processing",
        "error": "Video not found"
    }

    response = client.put(f"/kb/documents/{doc.id}/status", json=update_data)

    assert response.status_code == 200

    db_session.refresh(doc)
    assert doc.status == "failed"