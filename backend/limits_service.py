# Сервис по подсчету лимитов пользователя

from sqlalchemy.orm import Session
from backend.models import UserDocument
from sqlalchemy import func


class LimitsService:
    # Сервис для проверки лимитов пользователя на основе данных из БД

    def __init__(self, db: Session):
        self.db = db

    def check_text_limits(self, user_id: int, tier) -> tuple[bool, str]:
        # Проверяет лимиты для загрузки текста

        # Проверяем лимит хранилища
        total_texts = self.db.query(func.count(UserDocument.id)).filter(
            UserDocument.user_id == user_id,
            UserDocument.file_type == "text",
            UserDocument.is_deleted == False
        ).scalar()

        if tier.texts_limit != 9999 and total_texts >= tier.texts_limit:
            return False, "Storage limit exceeded"

        # Проверяем дневной лимит
        today = func.date(func.now())
        daily_texts = self.db.query(func.count(UserDocument.id)).filter(
            UserDocument.user_id == user_id,
            UserDocument.file_type == "text",
            func.date(UserDocument.upload_date) == today,
            UserDocument.is_deleted == False
        ).scalar()

        if tier.daily_texts != 9999 and daily_texts >= tier.daily_texts:
            return False, "Daily limit exceeded"

        return True, ""

    def check_photo_limits(self, user_id: int, tier) -> tuple[bool, str]:
        # Проверяет лимиты для загрузки фото

        # Проверяем лимит хранилища
        total_photos = self.db.query(func.count(UserDocument.id)).filter(
            UserDocument.user_id == user_id,
            UserDocument.file_type == "photo",
            UserDocument.status == "completed",
            UserDocument.is_deleted == False
        ).scalar()

        if tier.photos_limit != 9999 and total_photos >= tier.photos_limit:
            return False, "Storage limit exceeded"

        # Проверяем дневной лимит
        today = func.date(func.now())
        daily_photos = self.db.query(func.count(UserDocument.id)).filter(
            UserDocument.user_id == user_id,
            UserDocument.file_type == "photo",
            func.date(UserDocument.upload_date) == today
        ).scalar()

        if tier.daily_photos != 9999 and daily_photos >= tier.daily_photos:
            return False, "Daily limit exceeded"

        return True, ""

    def check_file_limits(self, user_id: int, tier) -> tuple[bool, str]:
        # Проверяет лимиты для загрузки файлов

        # Проверяем лимит хранилища
        total_files = self.db.query(func.count(UserDocument.id)).filter(
            UserDocument.user_id == user_id,
            UserDocument.file_type == "file",
            UserDocument.status == "completed",
            UserDocument.is_deleted == False
        ).scalar()

        if tier.files_limit != 9999 and total_files >= tier.files_limit:
            return False, "Storage limit exceeded"

        # Проверяем дневной лимит
        today = func.date(func.now())
        daily_files = self.db.query(func.count(UserDocument.id)).filter(
            UserDocument.user_id == user_id,
            UserDocument.file_type == "file",
            func.date(UserDocument.upload_date) == today
        ).scalar()

        if tier.daily_files != 9999 and daily_files >= tier.daily_files:
            return False, "Daily limit exceeded"

        return True, ""