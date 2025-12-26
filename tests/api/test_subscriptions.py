# Тесты эндпоинтов подписок

import pytest

pytestmark = pytest.mark.api


def test_get_subscription_tiers(client):
    # Получение списка доступных тарифов

    response = client.get("/subscriptions/tiers")

    assert response.status_code == 200
    tiers = response.json()

    # Должны вернуться только платные тарифы (не free и не admin)
    tier_names = [tier["tier_name"] for tier in tiers]

    assert "free" not in tier_names
    assert "admin" not in tier_names
    assert "premium" in tier_names


def test_tiers_sorted_by_price(client):
    # Тарифы отсортированы по цене

    response = client.get("/subscriptions/tiers")
    tiers = response.json()

    prices = [tier["price_rubles"] for tier in tiers]

    # Проверяем что цены идут по возрастанию
    assert prices == sorted(prices)


def test_tier_contains_all_fields(client):
    # Каждый тариф содержит все необходимые поля

    response = client.get("/subscriptions/tiers")
    tiers = response.json()

    required_fields = [
        "tier_name", "display_name", "model_name", "price_rubles",
        "daily_messages", "video_hours_limit", "files_limit",
        "photos_limit", "texts_limit", "daily_video_hours",
        "daily_files", "daily_photos", "daily_texts"
    ]

    for tier in tiers:
        for field in required_fields:
            assert field in tier


def test_premium_tier_has_correct_limits(client):
    # Проверка лимитов премиум тарифа

    response = client.get("/subscriptions/tiers")
    tiers = response.json()

    premium = next(t for t in tiers if t["tier_name"] == "premium")

    assert premium["price_rubles"] == 999
    assert premium["daily_messages"] == 500
    assert premium["video_hours_limit"] == 20
    assert premium["files_limit"] == 50