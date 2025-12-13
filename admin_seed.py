# Администрирование контента в БД

from database import SessionLocal
from models import SubscriptionTier

# Обновление таблицы тарифных планов
def seed_subscriptions():
    db = SessionLocal()

    # Данные тарифов
    tiers_data = [
        {
            "tier_name": "free",
            "display_name": "🆓 Бесплатная",
            "model_name": "GPT-4o-mini",
            "price_rubles": 0,
            "daily_messages": 20,
            "video_hours_limit": 0,
            "files_limit": 1,
            "photos_limit": 0,
            "texts_limit": 5,
            "daily_video_hours": 0,
            "daily_files": 1,
            "daily_photos": 0,
            "daily_texts": 5
        },
        {
            "tier_name": "basic",
            "display_name": "📦 Базовая",
            "model_name": "GPT-4o-mini",
            "price_rubles": 499,
            "daily_messages": 100,
            "video_hours_limit": 2,
            "files_limit": 10,
            "photos_limit": 20,
            "texts_limit": 50,
            "daily_video_hours": 1,
            "daily_files": 5,
            "daily_photos": 10,
            "daily_texts": 25
        },
        {
            "tier_name": "premium",
            "display_name": "💎 Премиум",
            "model_name": "GPT-4o",
            "price_rubles": 999,
            "daily_messages": 500,
            "video_hours_limit": 20,
            "files_limit": 50,
            "photos_limit": 100,
            "texts_limit": 9999,
            "daily_video_hours": 5,
            "daily_files": 10,
            "daily_photos": 20,
            "daily_texts": 50
        },
        {
            "tier_name": "ultra",
            "display_name": "🚀 Ультра",
            "model_name": "Последняя модель Chat GPT!",
            "price_rubles": 2499,
            "daily_messages": 1500,
            "video_hours_limit": 100,
            "files_limit": 9999,
            "photos_limit": 9999,
            "texts_limit": 9999,
            "daily_video_hours": 20,
            "daily_files": 50,
            "daily_photos": 100,
            "daily_texts": 9999
        },
        {
            "tier_name": "admin",
            "display_name": "🏴‍☠ Админ",
            "model_name": "Последняя модель Chat GPT!",
            "price_rubles": 0,
            "daily_messages": 9999,
            "video_hours_limit": 9999,
            "files_limit": 9999,
            "photos_limit": 9999,
            "texts_limit": 9999,
            "daily_video_hours": 9999,
            "daily_files": 9999,
            "daily_photos": 9999,
            "daily_texts": 9999
        }
    ]

    created = 0
    updated = 0

    for tier_data in tiers_data:
        # Ищем существующий тариф
        existing = db.query(SubscriptionTier).filter(
            SubscriptionTier.tier_name == tier_data["tier_name"]
        ).first()

        if existing:
            # Обновляем существующий
            for key, value in tier_data.items():
                setattr(existing, key, value)
            updated += 1
        else:
            # Создаём новый
            new_tier = SubscriptionTier(**tier_data)
            db.add(new_tier)
            created += 1

    db.commit()

    print(f"\n✅ Тарифы синхронизированы:")
    print(f"   • Создано: {created}")
    print(f"   • Обновлено: {updated}")

    db.close()


if __name__ == "__main__":
    print("\n1. Синхронизировать тарифные планы")
    print("0. Выход")
    print("\nВведите номер: ", end="")

    choice = input().strip()

    if choice == "1":
        seed_subscriptions()
    elif choice == "0":
        print("Вы отменили обновление!")
    else:
        print("Введите 0 или 1")