# Инструкция по инициализации таблиц и полей в базе данных PostgreSQL

from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


# users - общая информация о пользователях
class User(Base):
    __tablename__ = "users"

    # id пользователя
    id = Column(Integer, primary_key=True, index=True)
    # id пользователя в телеграм
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    # Имя пользователя в телеграм
    username = Column(String)

    # Дата регистрации
    registration_date = Column(DateTime, default=datetime.now, nullable=False)
    # Реферальный код пользователя
    referral_code = Column(String, unique=True, nullable=False)
    # Кто пригласил пользователя
    referred_by = Column(Integer)

    # Relationships
    documents = relationship("UserDocument", back_populates="user")
    actions = relationship("UserDailyAction", back_populates="user")
    subscriptions = relationship("UserSubscription", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")


# user_actions - лог действий пользователей
class UserDailyAction(Base):
    __tablename__ = "user_actions"

    # id записи
    id = Column(Integer, primary_key=True, index=True)
    # id пользователя
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # id документа в базе знаний
    document_id = Column(Integer, ForeignKey("user_documents.id"))
    # Дата действия
    action_date = Column(DateTime, nullable=False)
    # Тип действия
    action_type = Column(String, nullable=False)

    # Relationships
    user = relationship("User", back_populates="actions")
    document = relationship("UserDocument", back_populates="actions")


# user_documents - файлы пользователей в базе знаний
class UserDocument(Base):
    __tablename__ = "user_documents"

    # id документа
    id = Column(Integer, primary_key=True, index=True)
    # id пользователя
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Дата попытки загрузки
    upload_date = Column(DateTime, default=datetime.now, nullable=False)
    # Название файла
    filename = Column(String, nullable=False)
    # Тип файла
    file_type = Column(String, nullable=False)
    # Статус обработки
    status = Column(String, default="processing", nullable=False)
    # Извлеченный текст
    extracted_text = Column(Text)
    # Ссылка на файл в S3
    file_url = Column(String)
    # Длина видео
    duration_hours = Column(Float)
    # Флаг удаления
    is_deleted = Column(Boolean, default=False)
    # Дата удаления
    deleted_at = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="documents")
    actions = relationship("UserDailyAction", back_populates="document")


# subscription_tiers - тарифные планы
class SubscriptionTier(Base):
    __tablename__ = "subscription_tiers"

    # id подписки
    id = Column(Integer, primary_key=True, index=True)
    # Внутреннее название подписки
    tier_name = Column(String, unique=True, nullable=False)
    # Отображаемое пользователю название подписки
    display_name = Column(String, unique=True, nullable=False)
    # Отображаемое пользователю название модели Chat GPT
    model_name = Column(String, nullable=False)
    # Цена в рублях за подписку
    price_rubles = Column(Integer, nullable=False)

    # Лимит сообщений боту в день
    daily_messages = Column(Integer, nullable=False)

    # Лимит на хранение видео в часах
    video_hours_limit = Column(Integer, nullable=False)
    # Лимит на хранение файлов
    files_limit = Column(Integer, nullable=False)
    # Лимит на хранение фото
    photos_limit = Column(Integer, nullable=False)
    # Лимит на текстовые сообщения
    texts_limit = Column(Integer, nullable=False)

    # Дневной лимит загрузки видео в часах
    daily_video_hours = Column(Integer, nullable=False)
    # Дневной лимит загрузки файлов
    daily_files = Column(Integer, nullable=False)
    # Дневной лимит загрузки фото
    daily_photos = Column(Integer, nullable=False)
    # Дневной лимит загрузки текстов
    daily_texts = Column(Integer, nullable=False)

    # Relationships
    subscriptions = relationship("UserSubscription", back_populates="tier")
    transactions = relationship("Transaction", back_populates="tier")


# transactions - оплаты подписок
class Transaction(Base):
    __tablename__ = "transactions"

    # id операции
    id = Column(Integer, primary_key=True, index=True)
    # id оплаты у провайдера
    payment_provider_id = Column(String, nullable=False, unique=True)
    # id пользователя
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # id подписки
    tier_id = Column(Integer, ForeignKey("subscription_tiers.id"), nullable=False)

    # Сумма
    amount = Column(Float, nullable=False)
    # Валюта
    currency = Column(String, nullable=False)
    # Статус платежа
    status = Column(String, nullable=False)
    # Платёжная система
    payment_method = Column(String, nullable=False)
    # Провайдер оплаты (юкасса)
    payment_provider = Column(String, nullable=False)
    # Дата создания платежа
    created_at = Column(DateTime, nullable=False)
    # Дата завершения платежа
    completed_at = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="transactions")
    tier = relationship("SubscriptionTier", back_populates="transactions")
    subscription = relationship("UserSubscription", back_populates="transaction")


# user_subscriptions - история изменения подписок пользователями
class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    # id изменения
    id = Column(Integer, primary_key=True, index=True)
    # id пользователя
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # id подписки
    tier_id = Column(Integer, ForeignKey("subscription_tiers.id"), nullable=False)
    # id оплаты
    transaction_id = Column(Integer, ForeignKey("transactions.id"))

    # Основание получения подписки (покупка, рефералка)
    source = Column(String)
    # Статус подписки
    status = Column(String, nullable=False)
    # Дата начала подписки
    start_date = Column(DateTime, nullable=False)
    # Плановая дата окончания
    end_date_plan = Column(DateTime)
    # Фактическая дата окончания
    # не равна плану в случае перехода на более высокий тариф
    end_date_fact = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    tier = relationship("SubscriptionTier", back_populates="subscriptions")
    transaction = relationship("Transaction", back_populates="subscription")

    @property
    def is_active(self):
        # Проверка активности подписки
        return self.status == "active" and (self.end_date_fact is None or self.end_date_fact > datetime.now())