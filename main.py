# API бота

import os
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date
import uvicorn
from database import get_db, engine
import models
import schemas
from celery_app import celery_app
from celery.result import AsyncResult
from s3_storage import process_video
from dotenv import load_dotenv

load_dotenv()

# Инициализируем таблицы в БД
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cogito AI Bot API", version="1.0.0")


# ЭНДПОИНТЫ ПОЛЬЗОВАТЕЛЕЙ

# Регистрация нового пользователя или авторизация старого
@app.post("/users/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):

    # Проверяем, существует ли пользователь
    existing_user = db.query(models.User).filter(
        models.User.telegram_id == user.telegram_id
    ).first()

    if existing_user:
        return existing_user

    # Если пользователь новый
    # 1. Создаём запись пользователя
    new_user = models.User(
        telegram_id=user.telegram_id,
        username=user.username,
        referral_code=f"REF{user.telegram_id}",
        referred_by=user.referred_by
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 2. Даём бесплатную подписку
    free_tier = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.tier_name == "free"
    ).first()

    new_subscription = models.UserSubscription(
        user_id=new_user.id,
        tier_id=free_tier.id,
        transaction_id=None,
        source="registration",
        status="active",
        start_date=datetime.now(),
        end_date_plan=None,
        end_date_fact=None
    )

    db.add(new_subscription)
    db.commit()

    return new_user

# Получаем статистику пользователя для главного меню
@app.get("/users/{telegram_id}/stats", response_model=schemas.UserStats)
def get_user_stats(telegram_id: int, db: Session = Depends(get_db)):

    # Получаем пользователя
    user = db.query(models.User).filter(
        models.User.telegram_id == telegram_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем активную подписку
    active_subscription = db.query(models.UserSubscription).filter(
        models.UserSubscription.user_id == user.id,
        models.UserSubscription.status == "active"
    ).first()

    if not active_subscription:
        raise HTTPException(status_code=404, detail="No active subscription")

    # Получаем тариф
    tier = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.id == active_subscription.tier_id
    ).first()

    # Считаем сообщения сегодня
    today = date.today()
    messages_today = db.query(models.UserDailyAction).filter(
        models.UserDailyAction.user_id == user.id,
        models.UserDailyAction.action_type == "ai_query",
        func.date(models.UserDailyAction.action_date) == today
    ).count()

    # Считаем использование базы знаний
    # Видео (часы)
    video_hours = db.query(
        func.coalesce(func.sum(models.UserDocument.duration_hours), 0)
    ).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "video",
        models.UserDocument.status == "completed",
        models.UserDocument.is_deleted == False
    ).scalar() or 0

    # Файлы (количество)
    files_count = db.query(models.UserDocument).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "file",
        models.UserDocument.status == "completed",
        models.UserDocument.is_deleted == False
    ).count()

    # Фото (количество)
    photos_count = db.query(models.UserDocument).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "image",
        models.UserDocument.status == "completed",
        models.UserDocument.is_deleted == False
    ).count()

    # Тексты (количество)
    texts_count = db.query(models.UserDocument).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "text",
        models.UserDocument.status == "completed",
        models.UserDocument.is_deleted == False
    ).count()

    # Считаем дневное использование загрузки
    # Видео (часы за сегодня)
    daily_video_hours = db.query(
        func.coalesce(func.sum(models.UserDocument.duration_hours), 0)
    ).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "video",
        models.UserDocument.status == "completed",
        func.date(models.UserDocument.upload_date) == today
    ).scalar() or 0

    # Файлы за сегодня
    daily_files = db.query(models.UserDocument).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "file",
        models.UserDocument.status == "completed",
        func.date(models.UserDocument.upload_date) == today
    ).count()

    # Фото за сегодня
    daily_photos = db.query(models.UserDocument).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "image",
        models.UserDocument.status == "completed",
        func.date(models.UserDocument.upload_date) == today
    ).count()

    # Тексты за сегодня
    daily_texts = db.query(models.UserDocument).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "text",
        models.UserDocument.status == "completed",
        func.date(models.UserDocument.upload_date) == today
    ).count()

    # Формируем ответ
    return schemas.UserStats(
        subscription_name=tier.display_name,
        subscription_tier=tier.tier_name,
        subscription_end=active_subscription.end_date_plan,
        messages_today=messages_today,
        messages_limit=tier.daily_messages,
        kb_storage={
            "video_hours": f"{video_hours:.2f}/{tier.video_hours_limit if tier.video_hours_limit != 9999 else '∞'}",
            "files": f"{files_count}/{tier.files_limit if tier.files_limit != 9999 else '∞'}",
            "photos": f"{photos_count}/{tier.photos_limit if tier.photos_limit != 9999 else '∞'}",
            "texts": f"{texts_count}/{tier.texts_limit if tier.texts_limit != 9999 else '∞'}"
        },
        kb_daily={
            "video_hours": f"{daily_video_hours:.2f}/{tier.daily_video_hours if tier.daily_video_hours != 9999 else '∞'}",
            "files": f"{daily_files}/{tier.daily_files if tier.daily_files != 9999 else '∞'}",
            "photos": f"{daily_photos}/{tier.daily_photos if tier.daily_photos != 9999 else '∞'}",
            "texts": f"{daily_texts}/{tier.daily_texts if tier.daily_texts != 9999 else '∞'}"
        }
    )


# ЭНДПОИНТЫ ПОДПИСОК

# Получаем список доступных к покупке подписок
@app.get("/subscriptions/tiers", response_model=list[schemas.SubscriptionTierResponse])
def get_subscription_tiers(db: Session = Depends(get_db)):

    tiers = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.tier_name.notin_(["free", "admin"])
    ).order_by(models.SubscriptionTier.price_rubles).all()

    return tiers


# ЭНДПОИНТЫ БАЗЫ ЗНАНИЙ

# Загрузка текста в базу знаний
@app.post("/kb/upload/text", response_model=schemas.TextUploadResponse)
def upload_text_to_kb(data: schemas.TextUploadRequest, db: Session = Depends(get_db)):

    # Находим пользователя
    user = db.query(models.User).filter(models.User.telegram_id == data.telegram_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем активную подписку
    subscription = db.query(models.UserSubscription).filter(
        models.UserSubscription.user_id == user.id,
        models.UserSubscription.status == "active"
    ).first()

    if not subscription:
        raise HTTPException(status_code=400, detail="No active subscription")

    # Получаем тариф
    tier = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.id == subscription.tier_id
    ).first()

    # Проверяем лимиты хранилища
    total_texts = db.query(func.count(models.UserDocument.id)).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "text",
        models.UserDocument.is_deleted == False
    ).scalar()

    if tier.texts_limit != 9999 and total_texts >= tier.texts_limit:
        raise HTTPException(status_code=400, detail="Storage limit exceeded")

    # Проверяем дневной лимит
    today = func.date(func.now())
    daily_texts = db.query(func.count(models.UserDocument.id)).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "text",
        func.date(models.UserDocument.upload_date) == today,
        models.UserDocument.is_deleted == False
    ).scalar()

    if tier.daily_texts != 9999 and daily_texts >= tier.daily_texts:
        raise HTTPException(status_code=400, detail="Daily limit exceeded")

    # Создаём запись
    new_doc = models.UserDocument(
        user_id=user.id,
        filename=f"text_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        file_type="text",
        status="completed",
        extracted_text=data.text,
        file_url=None,
        duration_hours=None
    )

    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    return {"success": True, "document_id": new_doc.id}

# Список всех файлов в базе знаний
@app.get("/kb/documents/{telegram_id}", response_model=schemas.DocumentsListResponse)
def get_user_documents(telegram_id: int, db: Session = Depends(get_db)):

    # Находим пользователя
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем все НЕ удалённые файлы
    documents = db.query(models.UserDocument).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.is_deleted == False
    ).order_by(models.UserDocument.upload_date.desc()).all()

    return {
        "documents": documents,
        "total_count": len(documents)
    }

# Удаление файла из базы знаний
@app.delete("/kb/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):

    # Находим файл
    document = db.query(models.UserDocument).filter(
        models.UserDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Мягкое удаление с очисткой текста
    document.is_deleted = True
    document.deleted_at = datetime.now()
    document.extracted_text = ""

    db.commit()

    return {"success": True, "message": "Document deleted"}

# Загрузка видео в базу знаний
@app.post("/kb/upload/video", response_model=schemas.VideoUploadResponse)
def upload_video_to_kb(data: schemas.VideoUploadRequest, db: Session = Depends(get_db)):
    # Находим пользователя
    user = db.query(models.User).filter(models.User.telegram_id == data.telegram_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем активную подписку
    subscription = db.query(models.UserSubscription).filter(
        models.UserSubscription.user_id == user.id,
        models.UserSubscription.status == "active"
    ).first()

    if not subscription:
        raise HTTPException(status_code=400, detail="No active subscription")

    # Получаем тариф
    tier = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.id == subscription.tier_id
    ).first()

    # Проверяем лимиты хранилища
    total_video_hours = db.query(func.sum(models.UserDocument.duration_hours)).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "video",
        models.UserDocument.is_deleted == False
    ).scalar() or 0

    if tier.video_hours_limit != 9999 and total_video_hours >= tier.video_hours_limit:
        raise HTTPException(status_code=400, detail="Storage limit exceeded")

    # Проверяем дневной лимит
    today = func.date(func.now())
    daily_video_hours = db.query(func.sum(models.UserDocument.duration_hours)).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "video",
        func.date(models.UserDocument.upload_date) == today,
        models.UserDocument.is_deleted == False
    ).scalar() or 0

    if tier.daily_video_hours != 9999 and daily_video_hours >= tier.daily_video_hours:
        raise HTTPException(status_code=400, detail="Daily limit exceeded")

    # Создаём записи для каждого видео и запускаем задачи
    task_ids = []

    for video in data.videos:
        new_doc = models.UserDocument(
            user_id=user.id,
            filename=video['title'],
            file_type="video",
            status="pending",
            file_url=video['url'],
            duration_hours=video['duration'],
            extracted_text=None
        )

        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        # Запускаем Celery задачу
        from s3_storage import process_video
        task = process_video.delay(video['url'], new_doc.id)
        task_ids.append(task.id)

    return {
        "success": True,
        "task_id": ",".join(task_ids),
        "message": f"Добавлено {len(data.videos)} видео в обработку"
    }

# Создание задач на обработку видео
@app.post("/kb/upload/video", response_model=schemas.VideoUploadResponse)
def upload_videos_to_kb(data: schemas.VideoUploadRequest, db: Session = Depends(get_db)):
    # Находим пользователя
    user = db.query(models.User).filter(models.User.telegram_id == data.telegram_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем подписку и тариф для определения приоритета
    subscription = db.query(models.UserSubscription).filter(
        models.UserSubscription.user_id == user.id,
        models.UserSubscription.status == "active"
    ).first()

    tier = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.id == subscription.tier_id
    ).first()

    tier_name = tier.tier_name
    priority = get_priority(tier_name)

    # Создаём записи в БД для каждого видео
    task_ids = []

    for video in data.videos:
        new_doc = models.UserDocument(
            user_id=user.id,
            filename=video['title'],
            file_type="video",
            status="pending",
            file_url=video['url'],
            duration_hours=video['duration'],
            extracted_text=None
        )

        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        # Запускаем Celery задачу с приоритетом
        task = process_video.apply_async(
            args=[video['url'], new_doc.id],
            priority=priority
        )
        task_ids.append(task.id)

    return {
        "success": True,
        "task_id": ",".join(task_ids),
        "message": f"Добавлено {len(data.videos)} видео в обработку"
    }

# Определяем приоритет обработки видео
def get_priority(tier: str) -> int:
    priorities = {
        'admin': 0,
        'ultra': 1,
        'premium': 2,
        'free': 3,
        'basic': 4
    }
    return priorities.get(tier, 4)

# Проверка статуса обработки видео
@app.get("/kb/video/status/{task_id}", response_model=schemas.VideoStatusResponse)
def get_video_status(task_id: str):

    task = AsyncResult(task_id, app=celery_app)

    return {
        "task_id": task_id,
        "status": task.state.lower(),
        "progress": task.info.get('progress') if isinstance(task.info, dict) else None,
        "error": str(task.info) if task.state == 'FAILURE' else None
    }

# Обновление статуса обработки
@app.put("/kb/documents/{document_id}/status")
def update_document_status(document_id: int, data: dict, db: Session = Depends(get_db)):
    doc = db.query(models.UserDocument).filter(models.UserDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = data.get('status')

    if data.get('error'):
        doc.status = 'failed'

    if data.get('transcription'):
        doc.extracted_text = data['transcription']

    db.commit()

    return {"success": True}

# Возвращаем информацию статусе обработки видео
@app.get("/kb/documents/{document_id}/info")
def get_document_info(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.UserDocument).filter(models.UserDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    user = db.query(models.User).filter(models.User.id == doc.user_id).first()

    return {
        "telegram_id": user.telegram_id,
        "filename": doc.filename
    }


# Запуск сервера
if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("API_HOST"),
        port=int(os.getenv("API_PORT"))
    )