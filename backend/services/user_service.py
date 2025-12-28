"""
Сервис для работы с пользователями.

Предоставляет методы для регистрации, получения информации
и управления пользователями.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
import logging

from backend.models import User, UserSubscription, SubscriptionTier
from backend import schemas

logger = logging.getLogger(__name__)


class UserService:
    """Сервис для управления пользователями."""

    def __init__(self, db: Session):
        """
        Инициализация сервиса.

        Args:
            db: Сессия базы данных
        """
        self.db = db

    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """
        Получить пользователя по Telegram ID.

        Args:
            telegram_id: ID пользователя в Telegram

        Returns:
            Объект User или None если не найден
        """
        return self.db.query(User).filter(
            User.telegram_id == telegram_id
        ).first()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Получить пользователя по ID в базе.

        Args:
            user_id: ID пользователя в БД

        Returns:
            Объект User или None если не найден
        """
        return self.db.query(User).filter(User.id == user_id).first()

    def create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        referred_by: Optional[int] = None
    ) -> User:
        """
        Создать нового пользователя.

        Args:
            telegram_id: ID в Telegram
            username: Имя пользователя
            referred_by: ID пригласившего пользователя

        Returns:
            Созданный пользователь
        """
        new_user = User(
            telegram_id=telegram_id,
            username=username,
            referral_code=f"REF{telegram_id}",
            referred_by=referred_by
        )

        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)

        logger.info(f"Создан пользователь: id={new_user.id}, telegram_id={telegram_id}")

        return new_user

    def register_or_get_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        referred_by: Optional[int] = None
    ) -> User:
        """
        Зарегистрировать пользователя или вернуть существующего.

        Args:
            telegram_id: ID в Telegram
            username: Имя пользователя
            referred_by: ID пригласившего

        Returns:
            Пользователь (существующий или новый)
        """
        # Проверяем существование
        existing_user = self.get_user_by_telegram_id(telegram_id)

        if existing_user:
            logger.info(f"Пользователь {telegram_id} уже существует")
            return existing_user

        # Создаем нового
        new_user = self.create_user(telegram_id, username, referred_by)

        # Выдаем бесплатную подписку
        from backend.services.subscription_service import SubscriptionService
        subscription_service = SubscriptionService(self.db)
        subscription_service.assign_free_subscription(new_user.id)

        return new_user

    def get_user_stats(self, telegram_id: int) -> Dict[str, Any]:
        """
        Получить статистику пользователя для главного меню.

        Args:
            telegram_id: ID пользователя в Telegram

        Returns:
            Словарь со статистикой

        Raises:
            ValueError: Если пользователь не найден
        """
        from backend.models import UserDocument, UserDailyAction
        from sqlalchemy import case, and_

        # Получаем пользователя
        user = self.get_user_by_telegram_id(telegram_id)
        if not user:
            raise ValueError(f"User with telegram_id={telegram_id} not found")

        # Получаем активную подписку с тарифом
        from sqlalchemy.orm import joinedload

        active_subscription = self.db.query(UserSubscription).options(
            joinedload(UserSubscription.tier)
        ).filter(
            UserSubscription.user_id == user.id,
            UserSubscription.status == "active"
        ).first()

        if not active_subscription:
            raise ValueError(f"User {telegram_id} has no active subscription")

        tier = active_subscription.tier

        # Считаем сообщения сегодня
        today = func.date(func.now())
        messages_today = self.db.query(UserDailyAction).filter(
            UserDailyAction.user_id == user.id,
            UserDailyAction.action_type == "ai_query",
            func.date(UserDailyAction.action_date) == today
        ).count()

        # ОПТИМИЗИРОВАННЫЙ запрос статистики по документам (один запрос)
        stats = self.db.query(
            # Общее хранилище
            func.coalesce(
                func.sum(case((UserDocument.file_type == "video", UserDocument.duration_hours), else_=0)),
                0
            ).label("video_hours"),
            func.count(case((UserDocument.file_type == "file", UserDocument.id))).label("files_count"),
            func.count(case((UserDocument.file_type == "photo", UserDocument.id))).label("photos_count"),
            func.count(case((UserDocument.file_type == "text", UserDocument.id))).label("texts_count"),

            # Дневное использование
            func.coalesce(
                func.sum(case(
                    (and_(UserDocument.file_type == "video", func.date(UserDocument.upload_date) == today),
                     UserDocument.duration_hours),
                    else_=0
                )),
                0
            ).label("daily_video_hours"),
            func.count(case(
                (and_(UserDocument.file_type == "file", func.date(UserDocument.upload_date) == today),
                 UserDocument.id)
            )).label("daily_files"),
            func.count(case(
                (and_(UserDocument.file_type == "photo", func.date(UserDocument.upload_date) == today),
                 UserDocument.id)
            )).label("daily_photos"),
            func.count(case(
                (and_(UserDocument.file_type == "text", func.date(UserDocument.upload_date) == today),
                 UserDocument.id)
            )).label("daily_texts"),
        ).filter(
            UserDocument.user_id == user.id,
            UserDocument.status == "completed",
            UserDocument.is_deleted == False
        ).first()

        # Формируем ответ
        return {
            "subscription_name": tier.display_name,
            "subscription_tier": tier.tier_name,
            "subscription_end": active_subscription.end_date_plan,
            "messages_today": messages_today,
            "messages_limit": tier.daily_messages,
            "kb_storage": {
                "video_hours": f"{stats.video_hours:.2f}/{tier.video_hours_limit if tier.video_hours_limit != 9999 else '∞'}",
                "files": f"{stats.files_count}/{tier.files_limit if tier.files_limit != 9999 else '∞'}",
                "photos": f"{stats.photos_count}/{tier.photos_limit if tier.photos_limit != 9999 else '∞'}",
                "texts": f"{stats.texts_count}/{tier.texts_limit if tier.texts_limit != 9999 else '∞'}"
            },
            "kb_daily": {
                "video_hours": f"{stats.daily_video_hours:.2f}/{tier.daily_video_hours if tier.daily_video_hours != 9999 else '∞'}",
                "files": f"{stats.daily_files}/{tier.daily_files if tier.daily_files != 9999 else '∞'}",
                "photos": f"{stats.daily_photos}/{tier.daily_photos if tier.daily_photos != 9999 else '∞'}",
                "texts": f"{stats.daily_texts}/{tier.daily_texts if tier.daily_texts != 9999 else '∞'}"
            }
        }