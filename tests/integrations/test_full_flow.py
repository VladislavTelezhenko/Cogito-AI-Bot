# Интеграционные тесты (полный цикл)

import pytest
from backend.models import User, UserDocument, UserSubscription

pytestmark = pytest.mark.integration


def test_full_user_registration_flow(client, free_user_data, db_session):
    # Полный цикл: регистрация → проверка подписки → проверка статистики

    # Шаг 1: Регистрация
    response = client.post("/users/register", json=free_user_data)
    assert response.status_code == 200
    user_id = response.json()["id"]

    # Шаг 2: Проверяем что создалась подписка
    subscription = db_session.query(UserSubscription).filter_by(
        user_id=user_id,
        status="active"
    ).first()
    assert subscription is not None

    # Шаг 3: Проверяем статистику
    stats_response = client.get(f"/users/{free_user_data['telegram_id']}/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()

    assert stats["subscription_tier"] == "free"
    assert stats["messages_today"] == 0


def test_full_text_upload_flow(client, free_user_data, db_session):
    # Полный цикл: регистрация → загрузка текста → просмотр → удаление

    # Регистрация
    client.post("/users/register", json=free_user_data)

    # Загрузка текста
    text_data = {
        "telegram_id": free_user_data["telegram_id"],
        "text": "Integration test text"
    }
    upload_response = client.post("/kb/upload/text", json=text_data)
    doc_id = upload_response.json()["document_id"]

    # Проверяем что документ создан
    doc = db_session.query(UserDocument).filter_by(id=doc_id).first()
    assert doc is not None
    assert doc.extracted_text == "Integration test text"

    # Получаем список документов
    docs_response = client.get(f"/kb/documents/{free_user_data['telegram_id']}")
    docs = docs_response.json()["documents"]
    assert len(docs) == 1

    # Удаляем
    delete_response = client.delete(f"/kb/documents/{doc_id}")
    assert delete_response.json()["success"] is True

    # Проверяем мягкое удаление
    db_session.refresh(doc)
    assert doc.is_deleted is True


def test_limit_enforcement_flow(client, free_user_data):
    # Полный цикл: загрузка до лимита → ошибка при превышении

    client.post("/users/register", json=free_user_data)

    # Загружаем 5 текстов (лимит free тарифа)
    for i in range(5):
        response = client.post("/kb/upload/text", json={
            "telegram_id": free_user_data["telegram_id"],
            "text": f"Text {i}"
        })
        assert response.status_code == 200

    # 6-й текст должен вернуть ошибку
    response = client.post("/kb/upload/text", json={
        "telegram_id": free_user_data["telegram_id"],
        "text": "Extra text"
    })
    assert response.status_code == 400

    # Проверяем статистику
    stats = client.get(f"/users/{free_user_data['telegram_id']}/stats").json()
    assert "5/5" in stats["kb_storage"]["texts"]