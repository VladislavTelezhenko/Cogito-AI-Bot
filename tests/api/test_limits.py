# Тесты проверки лимитов

import pytest
from datetime import datetime

pytestmark = pytest.mark.api


def test_free_user_cant_exceed_text_storage_limit(client, free_user_data):
    # Free пользователь не может превысить лимит хранилища текстов (5 шт)

    client.post("/users/register", json=free_user_data)

    # Загружаем 5 текстов (лимит)
    for i in range(5):
        response = client.post("/kb/upload/text", json={
            "telegram_id": free_user_data["telegram_id"],
            "text": f"Текст {i}"
        })
        assert response.status_code == 200

    # 6-й текст должен вернуть ошибку
    response = client.post("/kb/upload/text", json={
        "telegram_id": free_user_data["telegram_id"],
        "text": "Лишний текст"
    })

    assert response.status_code == 400
    assert "limit exceeded" in response.json()["detail"].lower()


def test_free_user_cant_exceed_text_daily_limit(client, free_user_data):
    # Free пользователь не может превысить дневной лимит текстов (5 шт)

    client.post("/users/register", json=free_user_data)

    # Загружаем 5 текстов
    for i in range(5):
        response = client.post("/kb/upload/text", json={
            "telegram_id": free_user_data["telegram_id"],
            "text": f"Текст {i}"
        })
        assert response.status_code == 200

    # 6-й текст за сегодня - ошибка
    response = client.post("/kb/upload/text", json={
        "telegram_id": free_user_data["telegram_id"],
        "text": "Лишний текст"
    })

    assert response.status_code == 400


def test_premium_user_has_higher_limits(client, premium_user_data, db_session):
    # Премиум пользователь имеет более высокие лимиты
    from backend.models import User, UserSubscription, SubscriptionTier

    # Регистрируем пользователя
    client.post("/users/register", json=premium_user_data)

    # Меняем подписку на premium
    user = db_session.query(User).filter_by(
        telegram_id=premium_user_data["telegram_id"]
    ).first()

    premium_tier = db_session.query(SubscriptionTier).filter_by(
        tier_name="premium"
    ).first()

    # Завершаем старую подписку
    old_sub = db_session.query(UserSubscription).filter_by(
        user_id=user.id,
        status="active"
    ).first()
    old_sub.status = "expired"
    old_sub.end_date_fact = datetime.now()

    # Создаём новую
    new_sub = UserSubscription(
        user_id=user.id,
        tier_id=premium_tier.id,
        status="active",
        source="test",
        start_date=datetime.now()
    )
    db_session.add(new_sub)
    db_session.commit()

    # Проверяем что можем загрузить много текстов (лимит 9999)
    for i in range(10):
        response = client.post("/kb/upload/text", json={
            "telegram_id": premium_user_data["telegram_id"],
            "text": f"Премиум текст {i}"
        })
        assert response.status_code == 200


def test_get_priority_returns_correct_values():
    # Функция get_priority возвращает правильные приоритеты
    from backend.main import get_priority

    assert get_priority("admin") == 0
    assert get_priority("ultra") == 1
    assert get_priority("premium") == 2
    assert get_priority("free") == 3
    assert get_priority("basic") == 4
    assert get_priority("unknown") == 4  # По умолчанию