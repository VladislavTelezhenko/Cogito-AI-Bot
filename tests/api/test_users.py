# Тесты эндпоинтов пользователей

import pytest
from backend.models import User, UserSubscription

pytestmark = pytest.mark.api


def test_register_new_user(client, free_user_data):
    # Регистрация нового пользователя
    response = client.post("/users/register", json=free_user_data)

    assert response.status_code == 200
    data = response.json()

    assert data["telegram_id"] == free_user_data["telegram_id"]
    assert data["username"] == free_user_data["username"]
    assert "referral_code" in data
    assert data["referral_code"] == f"REF{free_user_data['telegram_id']}"


def test_register_existing_user_returns_same(client, free_user_data):
    # Повторная регистрация возвращает существующего пользователя

    # Регистрируем первый раз
    response1 = client.post("/users/register", json=free_user_data)
    user1_id = response1.json()["id"]

    # Регистрируем второй раз
    response2 = client.post("/users/register", json=free_user_data)
    user2_id = response2.json()["id"]

    # ID должны совпадать
    assert user1_id == user2_id


def test_new_user_gets_free_subscription(client, free_user_data, db_session):
    # Новый пользователь получает бесплатную подписку

    response = client.post("/users/register", json=free_user_data)
    user_id = response.json()["id"]

    # Проверяем что создалась подписка
    subscription = db_session.query(UserSubscription).filter(
        UserSubscription.user_id == user_id
    ).first()

    assert subscription is not None
    assert subscription.status == "active"
    assert subscription.source == "registration"


def test_get_user_stats(client, free_user_data):
    # Получение статистики пользователя

    # Регистрируем пользователя
    client.post("/users/register", json=free_user_data)

    # Получаем статистику
    response = client.get(f"/users/{free_user_data['telegram_id']}/stats")

    assert response.status_code == 200
    data = response.json()

    assert data["subscription_name"] == "🆓 Бесплатная"
    assert data["subscription_tier"] == "free"
    assert data["messages_today"] == 0
    assert data["messages_limit"] == 20
    assert "kb_storage" in data
    assert "kb_daily" in data


def test_get_stats_for_nonexistent_user(client):
    # Запрос статистики несуществующего пользователя

    response = client.get("/users/999999999/stats")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_user_stats_contains_correct_limits(client, free_user_data):
    # Проверка правильности лимитов в статистике

    client.post("/users/register", json=free_user_data)
    response = client.get(f"/users/{free_user_data['telegram_id']}/stats")

    data = response.json()
    kb_storage = data["kb_storage"]

    # Free тариф: 0 видео, 1 файл, 0 фото, 5 текстов
    assert "0/0" in kb_storage.get("video_hours", "")
    assert "0/1" in kb_storage.get("files", "")
    assert "0/0" in kb_storage.get("photos", "")
    assert "0/5" in kb_storage.get("texts", "")