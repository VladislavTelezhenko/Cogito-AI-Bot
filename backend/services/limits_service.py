"""
Сервис для проверки лимитов пользователя.

Проверяет лимиты хранилища и дневные лимиты загрузки
для всех типов контента.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Tuple
import logging

from backend.models import UserDocument, SubscriptionTier

logger = logging.getLogger(__name__)

# Константа для безлимитных тарифов
UNLIMITED = 9999


class LimitsService:
    """Сервис для проверки лимитов пользователя."""

    def __init__(self, db: Session):
        """
        Инициализация сервиса.

        Args:
            db: Сессия базы данных
        """
        self.db = db

    def check_text_limits(self, user_id: int, tier: SubscriptionTier) -> Tuple[bool, str]:
        """
        Проверяет лимиты для загрузки текста.

        Args:
            user_id: ID пользователя
            tier: Тариф пользователя

        Returns:
            Кортеж (can_upload, error_message)
        """
        # Проверяем лимит хранилища
        if tier.texts_limit != UNLIMITED:
            total_texts = self.db.query(func.count(UserDocument.id)).filter(
                UserDocument.user_id == user_id,
                UserDocument.file_type == "text",
                UserDocument.is_deleted == False
            ).scalar()

            if total_texts >= tier.texts_limit:
                return False, "Storage limit exceeded"

        # Проверяем дневной лимит
        if tier.daily_texts != UNLIMITED:
            today = func.date(func.now())
            daily_texts = self.db.query(func.count(UserDocument.id)).filter(
                UserDocument.user_id == user_id,
                UserDocument.file_type == "text",
                func.date(UserDocument.upload_date) == today,
                UserDocument.is_deleted == False
            ).scalar()

            if daily_texts >= tier.daily_texts:
                return False, "Daily limit exceeded"

        return True, ""

    def check_photo_limits(self, user_id: int, tier: SubscriptionTier) -> Tuple[bool, str]:
        """
        Проверяет лимиты для загрузки фото.

        Args:
            user_id: ID пользователя
            tier: Тариф пользователя

        Returns:
            Кортеж (can_upload, error_message)
        """
        # Проверяем лимит хранилища
        if tier.photos_limit != UNLIMITED:
            total_photos = self.db.query(func.count(UserDocument.id)).filter(
                UserDocument.user_id == user_id,
                UserDocument.file_type == "photo",
                UserDocument.status == "completed",
                UserDocument.is_deleted == False
            ).scalar()

            if total_photos >= tier.photos_limit:
                return False, "Storage limit exceeded"

        # Проверяем дневной лимит
        if tier.daily_photos != UNLIMITED:
            today = func.date(func.now())
            daily_photos = self.db.query(func.count(UserDocument.id)).filter(
                UserDocument.user_id == user_id,
                UserDocument.file_type == "photo",
                func.date(UserDocument.upload_date) == today
            ).scalar()

            if daily_photos >= tier.daily_photos:
                return False, "Daily limit exceeded"

        return True, ""

    def check_file_limits(self, user_id: int, tier: SubscriptionTier) -> Tuple[bool, str]:
        """
        Проверяет лимиты для загрузки файлов.

        Args:
            user_id: ID пользователя
            tier: Тариф пользователя

        Returns:
            Кортеж (can_upload, error_message)
        """
        # Проверяем лимит хранилища
        if tier.files_limit != UNLIMITED:
            total_files = self.db.query(func.count(UserDocument.id)).filter(
                UserDocument.user_id == user_id,
                UserDocument.file_type == "file",
                UserDocument.status == "completed",
                UserDocument.is_deleted == False
            ).scalar()

            if total_files >= tier.files_limit:
                return False, "Storage limit exceeded"

        # Проверяем дневной лимит
        if tier.daily_files != UNLIMITED:
            today = func.date(func.now())
            daily_files = self.db.query(func.count(UserDocument.id)).filter(
                UserDocument.user_id == user_id,
                UserDocument.file_type == "file",
                func.date(UserDocument.upload_date) == today
            ).scalar()

            if daily_files >= tier.daily_files:
                return False, "Daily limit exceeded"

        return True, ""

    def check_video_limits(
        self,
        user_id: int,
        tier: SubscriptionTier,
        duration_hours: float
    ) -> Tuple[bool, str]:
        """
        Проверяет лимиты для загрузки видео.

        Args:
            user_id: ID пользователя
            tier: Тариф пользователя
            duration_hours: Длительность видео в часах

        Returns:
            Кортеж (can_upload, error_message)
        """
        # Проверяем лимит хранилища
        if tier.video_hours_limit != UNLIMITED:
            total_hours = self.db.query(
                func.coalesce(func.sum(UserDocument.duration_hours), 0)
            ).filter(
                UserDocument.user_id == user_id,
                UserDocument.file_type == "video",
                UserDocument.status == "completed",
                UserDocument.is_deleted == False
            ).scalar()

            if total_hours + duration_hours > tier.video_hours_limit:
                return False, f"Storage limit exceeded (available: {tier.video_hours_limit - total_hours:.2f}h)"

        # Проверяем дневной лимит
        if tier.daily_video_hours != UNLIMITED:
            today = func.date(func.now())
            daily_hours = self.db.query(
                func.coalesce(func.sum(UserDocument.duration_hours), 0)
            ).filter(
                UserDocument.user_id == user_id,
                UserDocument.file_type == "video",
                func.date(UserDocument.upload_date) == today
            ).scalar()

            if daily_hours + duration_hours > tier.daily_video_hours:
                return False, f"Daily limit exceeded (available: {tier.daily_video_hours - daily_hours:.2f}h)"

        return True, ""