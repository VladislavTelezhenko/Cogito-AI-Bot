# Схемы валидации для API

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# СХЕМЫ ДЛЯ ЭНДПОИНТОВ ПОЛЬЗОВАТЕЛЕЙ

# Данные для регистрации
class UserCreate(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    referred_by: Optional[int] = None

#  Ответ с данными пользователя
class UserResponse(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str]
    referral_code: str
    registration_date: datetime

    class Config:
        from_attributes = True

# Статистика для главного меню бота
class UserStats(BaseModel):
    subscription_name: str
    subscription_tier: str
    subscription_end: Optional[datetime]
    messages_today: int
    messages_limit: int
    kb_storage: dict
    kb_daily: dict


# СХЕМЫ ДЛЯ ЭНДПОИНТОВ ПОДПИСОК

# Информация о доступных подписках
class SubscriptionTierResponse(BaseModel):
    tier_name: str
    display_name: str
    model_name: str
    price_rubles: int
    daily_messages: int
    video_hours_limit: int
    files_limit: int
    photos_limit: int
    texts_limit: int
    daily_video_hours: int
    daily_files: int
    daily_photos: int
    daily_texts: int

    class Config:
        from_attributes = True

# СХЕМЫ ДЛЯ БАЗЫ ЗНАНИЙ

# Запрос на загрузку текста
class TextUploadRequest(BaseModel):
    telegram_id: int
    text: str

# Ответ после загрузки текста
class TextUploadResponse(BaseModel):
    success: bool
    document_id: int

# Информация о файле в базе знаний
class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    upload_date: datetime
    extracted_text: Optional[str] = None
    file_url: Optional[str] = None
    duration_hours: Optional[float] = None
    status: Optional[str] = None
    is_deleted: Optional[bool] = False

    class Config:
        from_attributes = True

# Список файлов пользователя
class DocumentsListResponse(BaseModel):
    documents: list[DocumentResponse]
    total_count: int

# Запрос на обработку видео
class VideoUploadRequest(BaseModel):
    telegram_id: int
    videos: list[dict]

# Ответ от обработчика видео с ID задачи
class VideoUploadResponse(BaseModel):
    success: bool
    task_id: str
    message: str

# Статус обработки видео
class VideoStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: Optional[str] = None
    error: Optional[str] = None