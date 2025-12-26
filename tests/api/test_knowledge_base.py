# Тесты эндпоинтов базы знаний

import pytest
from backend.models import UserDocument

pytestmark = pytest.mark.api


def test_upload_text(client, free_user_data):
    # Загрузка текста в базу знаний

    # Регистрируем пользователя
    client.post("/users/register", json=free_user_data)

    # Загружаем текст
    text_data = {
        "telegram_id": free_user_data["telegram_id"],
        "text": "Тестовый текст для базы знаний"
    }

    response = client.post("/kb/upload/text", json=text_data)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "document_id" in data


def test_upload_text_creates_document(client, free_user_data, db_session):
    # Загрузка текста создаёт запись в БД

    client.post("/users/register", json=free_user_data)

    text_data = {
        "telegram_id": free_user_data["telegram_id"],
        "text": "Тестовый текст"
    }

    response = client.post("/kb/upload/text", json=text_data)
    doc_id = response.json()["document_id"]

    # Проверяем что документ создан
    doc = db_session.query(UserDocument).filter_by(id=doc_id).first()

    assert doc is not None
    assert doc.file_type == "text"
    assert doc.status == "completed"
    assert doc.extracted_text == "Тестовый текст"


def test_get_user_documents(client, free_user_data):
    # Получение списка документов пользователя

    client.post("/users/register", json=free_user_data)

    # Загружаем несколько текстов
    for i in range(3):
        client.post("/kb/upload/text", json={
            "telegram_id": free_user_data["telegram_id"],
            "text": f"Текст {i}"
        })

    # Получаем список
    response = client.get(f"/kb/documents/{free_user_data['telegram_id']}")

    assert response.status_code == 200
    data = response.json()

    assert data["total_count"] == 3
    assert len(data["documents"]) == 3


def test_get_documents_for_nonexistent_user(client):
    # Запрос документов несуществующего пользователя

    response = client.get("/kb/documents/999999999")

    assert response.status_code == 404


def test_delete_document(client, free_user_data, db_session):
    # Удаление документа

    client.post("/users/register", json=free_user_data)

    # Загружаем текст
    upload_response = client.post("/kb/upload/text", json={
        "telegram_id": free_user_data["telegram_id"],
        "text": "Текст для удаления"
    })
    doc_id = upload_response.json()["document_id"]

    # Удаляем
    delete_response = client.delete(f"/kb/documents/{doc_id}")

    assert delete_response.status_code == 200
    assert delete_response.json()["success"] is True

    # Проверяем что документ помечен удалённым
    doc = db_session.query(UserDocument).filter_by(id=doc_id).first()
    assert doc.is_deleted is True
    assert doc.extracted_text == ""  # Текст очищен


def test_delete_nonexistent_document(client):
    # Удаление несуществующего документа

    response = client.delete("/kb/documents/999999")

    assert response.status_code == 404