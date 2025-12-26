# Тесты моделей базы данных

import pytest
from datetime import datetime
from backend.models import (
    User, UserSubscription, SubscriptionTier,
    UserDocument, UserDailyAction
)

pytestmark = pytest.mark.database


def test_create_user(db_session):
    # Создание пользователя
    user = User(
        telegram_id=12345,
        username="testuser",
        referral_code="REF12345"
    )

    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.telegram_id == 12345
    assert user.registration_date is not None


def test_user_referral_code_unique(db_session):
    # Реферальный код уникален
    user1 = User(telegram_id=11111, referral_code="REF11111")
    user2 = User(telegram_id=22222, referral_code="REF11111")  # Дубликат

    db_session.add(user1)
    db_session.commit()

    db_session.add(user2)

    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()


def test_create_subscription(db_session):
    # Создание подписки
    user = User(telegram_id=12345, referral_code="REF12345")
    db_session.add(user)
    db_session.commit()

    tier = db_session.query(SubscriptionTier).filter_by(tier_name="free").first()

    subscription = UserSubscription(
        user_id=user.id,
        tier_id=tier.id,
        status="active",
        source="registration",
        start_date=datetime.now()
    )

    db_session.add(subscription)
    db_session.commit()

    assert subscription.id is not None
    assert subscription.status == "active"


def test_create_document(db_session):
    # Создание документа
    user = User(telegram_id=12345, referral_code="REF12345")
    db_session.add(user)
    db_session.commit()

    doc = UserDocument(
        user_id=user.id,
        filename="test.txt",
        file_type="text",
        status="completed",
        extracted_text="Test content"
    )

    db_session.add(doc)
    db_session.commit()

    assert doc.id is not None
    assert doc.is_deleted is False


def test_soft_delete_document(db_session):
    # Мягкое удаление документа
    user = User(telegram_id=12345, referral_code="REF12345")
    db_session.add(user)
    db_session.commit()

    doc = UserDocument(
        user_id=user.id,
        filename="test.txt",
        file_type="text",
        extracted_text="Test content"
    )

    db_session.add(doc)
    db_session.commit()

    # Удаляем
    doc.is_deleted = True
    doc.deleted_at = datetime.now()
    doc.extracted_text = ""
    db_session.commit()

    assert doc.is_deleted is True
    assert doc.deleted_at is not None
    assert doc.extracted_text == ""


def test_user_daily_action(db_session):
    # Создание записи действия пользователя
    user = User(telegram_id=12345, referral_code="REF12345")
    db_session.add(user)
    db_session.commit()

    action = UserDailyAction(
        user_id=user.id,
        action_type="ai_query",
        action_date=datetime.now()
    )

    db_session.add(action)
    db_session.commit()

    assert action.id is not None


def test_subscription_tier_has_all_limits(db_session):
    # Тариф содержит все лимиты
    tier = db_session.query(SubscriptionTier).filter_by(tier_name="free").first()

    assert tier.daily_messages is not None
    assert tier.video_hours_limit is not None
    assert tier.files_limit is not None
    assert tier.photos_limit is not None
    assert tier.texts_limit is not None
    assert tier.daily_video_hours is not None
    assert tier.daily_files is not None
    assert tier.daily_photos is not None
    assert tier.daily_texts is not None


def test_query_user_documents(db_session):
    # Запрос документов пользователя
    user = User(telegram_id=12345, referral_code="REF12345")
    db_session.add(user)
    db_session.commit()

    # Создаём несколько документов
    for i in range(3):
        doc = UserDocument(
            user_id=user.id,
            filename=f"test{i}.txt",
            file_type="text",
            extracted_text=f"Content {i}"
        )
        db_session.add(doc)

    db_session.commit()

    # Запрашиваем
    docs = db_session.query(UserDocument).filter_by(
        user_id=user.id,
        is_deleted=False
    ).all()

    assert len(docs) == 3


def test_query_active_subscription(db_session):
    # Запрос активной подписки
    user = User(telegram_id=12345, referral_code="REF12345")
    db_session.add(user)
    db_session.commit()

    tier = db_session.query(SubscriptionTier).filter_by(tier_name="free").first()

    subscription = UserSubscription(
        user_id=user.id,
        tier_id=tier.id,
        status="active",
        source="registration",
        start_date=datetime.now()
    )

    db_session.add(subscription)
    db_session.commit()

    # Запрашиваем активную
    active_sub = db_session.query(UserSubscription).filter_by(
        user_id=user.id,
        status="active"
    ).first()

    assert active_sub is not None
    assert active_sub.tier_id == tier.id