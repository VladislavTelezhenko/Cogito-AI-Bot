"""
Сервис для работы с подписками.

Управление тарифами и подписками пользователей.
"""

from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
import logging

from backend.models import SubscriptionTier, UserSubscription, User

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Сервис для управления подписками."""

    def __init__(self, db: Session):
        """
        Инициализация сервиса.

        Args:
            db: Сессия базы данных
        """
        self.db = db

    def get_all_tiers(self, exclude_internal: bool = True) -> List[SubscriptionTier]:
        """
        Получить список всех тарифных планов.

        Args:
            exclude_internal: Исключить внутренние тарифы (free, admin)

        Returns:
            Список тарифов
        """
        query = self.db.query(SubscriptionTier)

        if exclude_internal:
            query = query.filter(
                SubscriptionTier.tier_name.notin_(["free", "admin"])
            )

        return query.order_by(SubscriptionTier.price_rubles).all()

    def get_tier_by_name(self, tier_name: str) -> Optional[SubscriptionTier]:
        """
        Получить тариф по имени.

        Args:
            tier_name: Название тарифа (free, basic, premium, ultra, admin)

        Returns:
            Объект тарифа или None
        """
        return self.db.query(SubscriptionTier).filter(
            SubscriptionTier.tier_name == tier_name
        ).first()

    def get_tier_by_id(self, tier_id: int) -> Optional[SubscriptionTier]:
        """
        Получить тариф по ID.

        Args:
            tier_id: ID тарифа

        Returns:
            Объект тарифа или None
        """
        return self.db.query(SubscriptionTier).filter(
            SubscriptionTier.id == tier_id
        ).first()

    def get_active_subscription(self, user_id: int) -> Optional[Tuple[UserSubscription, SubscriptionTier]]:
        """
        Получить активную подписку пользователя с тарифом.

        Args:
            user_id: ID пользователя

        Returns:
            Кортеж (подписка, тариф) или None
        """
        from sqlalchemy.orm import joinedload

        subscription = self.db.query(UserSubscription).options(
            joinedload(UserSubscription.tier)
        ).filter(
            UserSubscription.user_id == user_id,
            UserSubscription.status == "active"
        ).first()

        if subscription:
            return subscription, subscription.tier

        return None

    def assign_free_subscription(self, user_id: int) -> UserSubscription:
        """
        Назначить бесплатную подписку пользователю.

        Args:
            user_id: ID пользователя

        Returns:
            Созданная подписка
        """
        free_tier = self.get_tier_by_name("free")

        if not free_tier:
            raise ValueError("Free tier not found in database")

        new_subscription = UserSubscription(
            user_id=user_id,
            tier_id=free_tier.id,
            transaction_id=None,
            source="registration",
            status="active",
            start_date=datetime.now(),
            end_date_plan=None,
            end_date_fact=None
        )

        self.db.add(new_subscription)
        self.db.commit()
        self.db.refresh(new_subscription)

        logger.info(f"Назначена бесплатная подписка пользователю {user_id}")

        return new_subscription

    def upgrade_subscription(
        self,
        user_id: int,
        new_tier_id: int,
        transaction_id: Optional[int] = None
    ) -> UserSubscription:
        """
        Повысить подписку пользователя.

        Args:
            user_id: ID пользователя
            new_tier_id: ID нового тарифа
            transaction_id: ID транзакции оплаты

        Returns:
            Новая подписка
        """
        # Завершаем текущую подписку
        current = self.get_active_subscription(user_id)

        if current:
            current_sub, _ = current
            current_sub.status = "expired"
            current_sub.end_date_fact = datetime.now()

        # Создаем новую
        new_subscription = UserSubscription(
            user_id=user_id,
            tier_id=new_tier_id,
            transaction_id=transaction_id,
            source="purchase",
            status="active",
            start_date=datetime.now()
        )

        self.db.add(new_subscription)
        self.db.commit()
        self.db.refresh(new_subscription)

        logger.info(f"Подписка пользователя {user_id} обновлена до tier_id={new_tier_id}")

        return new_subscription