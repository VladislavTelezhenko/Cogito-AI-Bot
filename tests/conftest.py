# Фикстуры для pytest

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.database import Base, get_db
from backend.models import SubscriptionTier

# Используем in-memory SQLite для тестов
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    # Создаём чистую тестовую БД для каждого теста
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()

    # Заполняем тарифы
    seed_tiers(db)

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def seed_tiers(db):
    # Заполняет тестовую БД тарифами
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

    for tier_data in tiers_data:
        tier = SubscriptionTier(**tier_data)
        db.add(tier)

    db.commit()


@pytest.fixture(scope="function")
def client(db_session):
    # Создаёт тестовый клиент FastAPI с подменённой БД

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def free_user_data():
    # Данные бесплатного пользователя
    return {
        "telegram_id": 123456,
        "username": "free_user"
    }


@pytest.fixture
def premium_user_data():
    # Данные премиум пользователя
    return {
        "telegram_id": 789012,
        "username": "premium_user"
    }


@pytest.fixture
def admin_user_data():
    # Данные админа
    return {
        "telegram_id": 999999,
        "username": "admin_user"
    }


@pytest.fixture
def mock_s3_client(monkeypatch):
    # Мок S3 клиента
    class MockS3Client:
        def put_object(self, **kwargs):
            return {"ETag": "fake_etag"}

        def get_object(self, **kwargs):
            class Response:
                def __init__(self):
                    self.body = type('obj', (object,), {'read': lambda: b'fake_data'})()

            return Response()

        def delete_object(self, **kwargs):
            return {}

        def generate_presigned_url(self, *args, **kwargs):
            return "https://fake-presigned-url.com"

    return MockS3Client()


@pytest.fixture
def mock_celery_task(monkeypatch):
    # Мок Celery задачи
    class MockTask:
        def apply_async(self, *args, **kwargs):
            class Result:
                id = "fake-task-id"

            return Result()

    return MockTask()