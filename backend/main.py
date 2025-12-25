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
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# Инициализируем таблицы в БД
models.Base.metadata.create_all(bind=engine)
logger.info("Инициализированы таблицы в БД")

app = FastAPI(title="Cogito AI Bot API", version="1.0.0")


# ЭНДПОИНТЫ ПОЛЬЗОВАТЕЛЕЙ

# Регистрация нового пользователя или авторизация старого
@app.post("/users/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    logger.info(f"Запрос регистрации пользователя: telegram_id={user.telegram_id}")

    # Проверяем, существует ли пользователь
    existing_user = db.query(models.User).filter(
        models.User.telegram_id == user.telegram_id
    ).first()

    if existing_user:
        logger.info(f"Пользователь {user.telegram_id} уже зарегистрирован")
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

    logger.info(f"Создан новый пользователь: id={new_user.id}, telegram_id={user.telegram_id}")

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

    logger.info(f"Пользователю {new_user.id} назначена бесплатная подписка")

    return new_user

# Получаем статистику пользователя для главного меню
@app.get("/users/{telegram_id}/stats", response_model=schemas.UserStats)
def get_user_stats(telegram_id: int, db: Session = Depends(get_db)):
    logger.debug(f"Запрос статистики пользователя: telegram_id={telegram_id}")

    # Получаем пользователя
    user = db.query(models.User).filter(
        models.User.telegram_id == telegram_id
    ).first()

    if not user:
        logger.warning(f"Пользователь не найден: telegram_id={telegram_id}")
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем активную подписку
    active_subscription = db.query(models.UserSubscription).filter(
        models.UserSubscription.user_id == user.id,
        models.UserSubscription.status == "active"
    ).first()

    if not active_subscription:
        logger.error(f"У пользователя {telegram_id} нет активной подписки")
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
        models.UserDocument.file_type == "photo",
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
        models.UserDocument.file_type == "photo",
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

    logger.debug(f"Статистика для {telegram_id}: подписка={tier.tier_name}, сообщений={messages_today}/{tier.daily_messages}")

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
    logger.debug("Запрос списка тарифных планов")

    tiers = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.tier_name.notin_(["free", "admin"])
    ).order_by(models.SubscriptionTier.price_rubles).all()

    logger.debug(f"Возвращено {len(tiers)} тарифных планов")
    return tiers


# ЭНДПОИНТЫ БАЗЫ ЗНАНИЙ

# Загрузка текста в базу знаний
@app.post("/kb/upload/text", response_model=schemas.TextUploadResponse)
def upload_text_to_kb(data: schemas.TextUploadRequest, db: Session = Depends(get_db)):
    logger.info(f"Загрузка текста пользователем telegram_id={data.telegram_id}")

    # Находим пользователя
    user = db.query(models.User).filter(models.User.telegram_id == data.telegram_id).first()
    if not user:
        logger.warning(f"Пользователь не найден: telegram_id={data.telegram_id}")
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем активную подписку
    subscription = db.query(models.UserSubscription).filter(
        models.UserSubscription.user_id == user.id,
        models.UserSubscription.status == "active"
    ).first()

    if not subscription:
        logger.error(f"У пользователя {data.telegram_id} нет активной подписки")
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
        logger.warning(f"Пользователь {data.telegram_id} превысил лимит хранилища текстов: {total_texts}/{tier.texts_limit}")
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
        logger.warning(f"Пользователь {data.telegram_id} превысил дневной лимит текстов: {daily_texts}/{tier.daily_texts}")
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

    logger.info(f"Текст успешно загружен: document_id={new_doc.id}, user={data.telegram_id}")

    return {"success": True, "document_id": new_doc.id}

# Список всех файлов в базе знаний
@app.get("/kb/documents/{telegram_id}", response_model=schemas.DocumentsListResponse)
def get_user_documents(telegram_id: int, db: Session = Depends(get_db)):
    logger.debug(f"Запрос списка документов: telegram_id={telegram_id}")

    # Находим пользователя
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if not user:
        logger.warning(f"Пользователь не найден: telegram_id={telegram_id}")
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем все НЕ удалённые файлы
    documents = db.query(models.UserDocument).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.is_deleted == False
    ).order_by(models.UserDocument.upload_date.desc()).all()

    logger.debug(f"Возвращено {len(documents)} документов для пользователя {telegram_id}")

    return {
        "documents": documents,
        "total_count": len(documents)
    }


# Создание задач на обработку видео
@app.post("/kb/upload/video", response_model=schemas.VideoUploadResponse)
def upload_videos_to_kb(data: schemas.VideoUploadRequest, db: Session = Depends(get_db)):
    logger.info(f"Загрузка {len(data.videos)} видео пользователем telegram_id={data.telegram_id}")

    # Находим пользователя
    user = db.query(models.User).filter(models.User.telegram_id == data.telegram_id).first()
    if not user:
        logger.warning(f"Пользователь не найден: telegram_id={data.telegram_id}")
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

    logger.info(f"Приоритет обработки для пользователя {data.telegram_id} (тариф {tier_name}): {priority}")

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

        logger.info(f"Создана задача на обработку видео: task_id={task.id}, document_id={new_doc.id}")

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
    logger.debug(f"Проверка статуса задачи: task_id={task_id}")

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
    logger.debug(f"Обновление статуса документа: document_id={document_id}, status={data.get('status')}")

    doc = db.query(models.UserDocument).filter(models.UserDocument.id == document_id).first()
    if not doc:
        logger.warning(f"Документ не найден: document_id={document_id}")
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = data.get('status')

    if data.get('error'):
        doc.status = 'failed'
        logger.error(f"Ошибка обработки документа {document_id}: {data.get('error')}")

    if data.get('transcription'):
        doc.extracted_text = data['transcription']

    db.commit()

    logger.info(f"Статус документа {document_id} обновлён: {doc.status}")

    return {"success": True}

# Возвращаем информацию о документе (для видео и фото)
@app.get("/kb/documents/{document_id}/info")
def get_document_info(document_id: int, db: Session = Depends(get_db)):
    logger.debug(f"Запрос информации о документе: document_id={document_id}")

    doc = db.query(models.UserDocument).filter(models.UserDocument.id == document_id).first()
    if not doc:
        logger.warning(f"Документ не найден: document_id={document_id}")
        raise HTTPException(status_code=404, detail="Document not found")

    user = db.query(models.User).filter(models.User.id == doc.user_id).first()

    return {
        "telegram_id": user.telegram_id,
        "filename": doc.filename,
        "extracted_text": doc.extracted_text,
        "file_url": doc.file_url,
        "status": doc.status
    }

# Загрузка фото в базу знаний
@app.post("/kb/upload/photos", response_model=schemas.PhotoUploadResponse)
def upload_photos_to_kb(data: schemas.PhotoUploadRequest, db: Session = Depends(get_db)):
    logger.info(f"Загрузка {len(data.photos)} фото пользователем telegram_id={data.telegram_id}")

    # Находим пользователя
    user = db.query(models.User).filter(models.User.telegram_id == data.telegram_id).first()
    if not user:
        logger.warning(f"Пользователь не найден: telegram_id={data.telegram_id}")
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем подписку и тариф
    subscription = db.query(models.UserSubscription).filter(
        models.UserSubscription.user_id == user.id,
        models.UserSubscription.status == "active"
    ).first()

    if not subscription:
        logger.error(f"У пользователя {data.telegram_id} нет активной подписки")
        raise HTTPException(status_code=400, detail="No active subscription")

    tier = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.id == subscription.tier_id
    ).first()

    # Проверяем лимиты хранилища
    total_photos = db.query(func.count(models.UserDocument.id)).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "photo",
        models.UserDocument.status == "completed",
        models.UserDocument.is_deleted == False
    ).scalar()

    if tier.photos_limit != 9999 and total_photos >= tier.photos_limit:
        logger.warning(f"Пользователь {data.telegram_id} превысил лимит хранилища фото: {total_photos}/{tier.photos_limit}")
        raise HTTPException(status_code=400, detail="Storage limit exceeded")

    # Проверяем дневной лимит
    today = func.date(func.now())
    daily_photos = db.query(func.count(models.UserDocument.id)).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "photo",
        func.date(models.UserDocument.upload_date) == today
    ).scalar()

    if tier.daily_photos != 9999 and daily_photos >= tier.daily_photos:
        logger.warning(f"Пользователь {data.telegram_id} превысил дневной лимит фото: {daily_photos}/{tier.daily_photos}")
        raise HTTPException(status_code=400, detail="Daily limit exceeded")

    # Определяем приоритет
    tier_name = tier.tier_name
    priority = get_priority(tier_name)

    # Создаём записи в БД для каждого фото и запускаем задачи
    task_ids = []

    from s3_storage import upload_photo_to_s3, process_photo_ocr

    for photo in data.photos:
        # Создаём запись в БД
        new_doc = models.UserDocument(
            user_id=user.id,
            filename=photo['filename'],
            file_type="photo",
            status="pending",
            extracted_text=None,
            file_url=None,
            duration_hours=None
        )

        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        # Загружаем фото в S3
        s3_key = upload_photo_to_s3(photo['base64'], user.id, new_doc.id)

        # Сохраняем S3 URL в БД
        s3_url = f"https://storage.yandexcloud.net/{os.getenv('YC_BUCKET_NAME')}/{s3_key}"
        new_doc.file_url = s3_url
        db.commit()

        # Запускаем Celery задачу с приоритетом
        task = process_photo_ocr.apply_async(
            args=[new_doc.id, s3_key],
            priority=priority
        )
        task_ids.append(task.id)

        logger.info(f"Создана задача на OCR фото: task_id={task.id}, document_id={new_doc.id}")

    return {
        "success": True,
        "uploaded_count": len(data.photos),
        "task_ids": task_ids
    }

# Получение presigned URL для фото
@app.get("/kb/photo/{document_id}/presigned")
def get_photo_presigned_url_endpoint(document_id: int, db: Session = Depends(get_db)):
    logger.debug(f"Запрос presigned URL для фото: document_id={document_id}")

    # Находим документ
    doc = db.query(models.UserDocument).filter(
        models.UserDocument.id == document_id,
        models.UserDocument.file_type == "photo"
    ).first()

    if not doc:
        logger.warning(f"Фото не найдено: document_id={document_id}")
        raise HTTPException(status_code=404, detail="Photo not found")

    # Извлекаем s3_key из file_url
    bucket_name = os.getenv('YC_BUCKET_NAME')
    s3_key = doc.file_url.split(f"{bucket_name}/")[1]

    # Генерируем presigned URL
    from s3_storage import get_photo_presigned_url
    presigned_url = get_photo_presigned_url(s3_key)

    logger.debug(f"Сгенерирован presigned URL для документа {document_id}")

    return {
        "presigned_url": presigned_url,
        "expires_in": 3600
    }


# Загрузка файлов в базу знаний
@app.post("/kb/upload/files", response_model=schemas.FileUploadResponse)
def upload_files_to_kb(data: schemas.FileUploadRequest, db: Session = Depends(get_db)):
    logger.info(f"Загрузка {len(data.files)} файлов пользователем telegram_id={data.telegram_id}")

    # Находим пользователя
    user = db.query(models.User).filter(models.User.telegram_id == data.telegram_id).first()
    if not user:
        logger.warning(f"Пользователь не найден: telegram_id={data.telegram_id}")
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем подписку и тариф
    subscription = db.query(models.UserSubscription).filter(
        models.UserSubscription.user_id == user.id,
        models.UserSubscription.status == "active"
    ).first()

    if not subscription:
        logger.error(f"У пользователя {data.telegram_id} нет активной подписки")
        raise HTTPException(status_code=400, detail="No active subscription")

    tier = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.id == subscription.tier_id
    ).first()

    # Проверяем лимиты хранилища
    total_files = db.query(func.count(models.UserDocument.id)).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "file",
        models.UserDocument.status == "completed",
        models.UserDocument.is_deleted == False
    ).scalar()

    if tier.files_limit != 9999 and total_files >= tier.files_limit:
        logger.warning(f"Пользователь {data.telegram_id} превысил лимит хранилища файлов: {total_files}/{tier.files_limit}")
        raise HTTPException(status_code=400, detail="Storage limit exceeded")

    # Проверяем дневной лимит
    today = func.date(func.now())
    daily_files = db.query(func.count(models.UserDocument.id)).filter(
        models.UserDocument.user_id == user.id,
        models.UserDocument.file_type == "file",
        func.date(models.UserDocument.upload_date) == today
    ).scalar()

    if tier.daily_files != 9999 and daily_files >= tier.daily_files:
        logger.warning(f"Пользователь {data.telegram_id} превысил дневной лимит файлов: {daily_files}/{tier.daily_files}")
        raise HTTPException(status_code=400, detail="Daily limit exceeded")

    # Определяем приоритет
    tier_name = tier.tier_name
    priority = get_priority(tier_name)

    # Создаём записи в БД для каждого файла и запускаем задачи
    task_ids = []

    from s3_storage import upload_file_to_s3, process_file

    for file_data in data.files:
        # Определяем расширение
        extension = file_data['filename'].split('.')[-1].lower()

        # Создаём запись в БД
        new_doc = models.UserDocument(
            user_id=user.id,
            filename=file_data['filename'],
            file_type="file",
            status="pending",
            extracted_text=None,
            file_url=None,
            duration_hours=None
        )

        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        # Загружаем файл в S3
        s3_key = upload_file_to_s3(file_data['file_bytes'], user.id, new_doc.id, extension)

        # Сохраняем S3 URL в БД
        s3_url = f"https://storage.yandexcloud.net/{os.getenv('YC_BUCKET_NAME')}/{s3_key}"
        new_doc.file_url = s3_url
        db.commit()

        # Запускаем Celery задачу с приоритетом
        task = process_file.apply_async(
            args=[new_doc.id, s3_key, file_data['mime_type']],
            priority=priority
        )
        task_ids.append(task.id)

        logger.info(f"Создана задача на обработку файла: task_id={task.id}, document_id={new_doc.id}")

    return {
        "success": True,
        "uploaded_count": len(data.files),
        "task_ids": task_ids
    }


# Удаление файла из базы знаний
@app.delete("/kb/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    logger.info(f"Запрос на удаление документа: document_id={document_id}")

    # Находим файл
    document = db.query(models.UserDocument).filter(
        models.UserDocument.id == document_id
    ).first()

    if not document:
        logger.warning(f"Документ не найден: document_id={document_id}")
        raise HTTPException(status_code=404, detail="Document not found")

    # Если это фото или файл — удаляем из S3
    if document.file_type in ["photo", "file"] and document.file_url:
        bucket_name = os.getenv('YC_BUCKET_NAME')
        try:
            s3_key = document.file_url.split(f"{bucket_name}/")[1]

            # Удаляем из S3 через универсальную функцию
            from s3_storage import delete_from_s3
            delete_from_s3(s3_key)

            logger.info(f"Файл удалён из S3: s3_key={s3_key}")
        except Exception as e:
            logger.error(f"Не удалось извлечь s3_key или удалить файл: {e}")

    # Мягкое удаление с очисткой текста
    document.is_deleted = True
    document.deleted_at = datetime.now()
    document.extracted_text = ""

    db.commit()

    logger.info(f"Документ {document_id} помечен как удалённый")

    return {"success": True, "message": "Document deleted"}


# Запуск сервера
if __name__ == "__main__":
    logger.info(f"Запуск API сервера на {os.getenv('API_HOST')}:{os.getenv('API_PORT')}")

    uvicorn.run(
        app,
        host=os.getenv("API_HOST"),
        port=int(os.getenv("API_PORT"))
    )