"""
FastAPI приложение - основной API сервер бота.

Предоставляет REST API для:
- Регистрации и управления пользователями
- Управления подписками
- Загрузки и управления документами в базе знаний
- Обработки видео, фото и файлов
"""

import os
from fastapi import FastAPI, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from datetime import datetime
import uvicorn
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import Optional, List

from backend.database import get_db, engine
from backend import models, schemas
from backend.celery_app import celery_app
from celery.result import AsyncResult
from backend.s3_storage import (
    process_video,
    upload_photo_to_s3,
    process_photo_ocr,
    upload_file_to_s3,
    process_file,
    delete_from_s3,
    get_photo_presigned_url
)
from dotenv import load_dotenv
from pathlib import Path
from shared.config import S3_BASE_URL

# Импорт сервисов
from backend.services import (
    UserService,
    SubscriptionService,
    DocumentService,
    LimitsService
)

# Настройка логирования
BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / 'api.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

env_path = Path(__file__).parent.parent / 'secret' / '.env'
load_dotenv(dotenv_path=env_path)

# Инициализируем таблицы в БД
models.Base.metadata.create_all(bind=engine)
logger.info("Инициализированы таблицы в БД")

# Инициализация FastAPI
app = FastAPI(
    title="Cogito AI Bot API",
    version="2.0.0",
    description="API для управления базой знаний и подписками"
)

# Rate Limiting (защита от DoS)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

def get_priority(tier: str) -> int:
    """
    Определить приоритет обработки задачи по тарифу.

    Args:
        tier: Название тарифа

    Returns:
        Приоритет (0 = highest, 10 = lowest)
    """
    priorities = {
        'admin': 0,
        'ultra': 1,
        'premium': 2,
        'free': 3,
        'basic': 4
    }
    return priorities.get(tier, 4)


# ============================================================================
# ЭНДПОИНТЫ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================================

@app.post("/users/register", response_model=schemas.UserResponse)
@limiter.limit("10/minute")
def register_user(request: Request, user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Регистрация нового пользователя или авторизация существующего.

    При регистрации автоматически назначается бесплатная подписка.
    """
    logger.info(f"Запрос регистрации: telegram_id={user.telegram_id}")

    user_service = UserService(db)

    registered_user = user_service.register_or_get_user(
        telegram_id=user.telegram_id,
        username=user.username,
        referred_by=user.referred_by
    )

    return registered_user


@app.get("/users/{telegram_id}/stats", response_model=schemas.UserStats)
@limiter.limit("30/minute")
def get_user_stats(request: Request, telegram_id: int, db: Session = Depends(get_db)):
    """
    Получить статистику пользователя для главного меню.

    Включает информацию о подписке, лимитах и использовании базы знаний.
    """
    logger.debug(f"Запрос статистики: telegram_id={telegram_id}")

    user_service = UserService(db)

    try:
        stats = user_service.get_user_stats(telegram_id)
        return stats
    except ValueError as e:
        logger.warning(f"Ошибка получения статистики: {e}")
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# ЭНДПОИНТЫ ПОДПИСОК
# ============================================================================

@app.get("/subscriptions/tiers", response_model=list[schemas.SubscriptionTierResponse])
@limiter.limit("20/minute")
def get_subscription_tiers(request: Request, db: Session = Depends(get_db)):
    """
    Получить список доступных для покупки тарифных планов.

    Исключает внутренние тарифы (free, admin).
    """
    logger.debug("Запрос списка тарифных планов")

    subscription_service = SubscriptionService(db)
    tiers = subscription_service.get_all_tiers(exclude_internal=True)

    logger.debug(f"Возвращено {len(tiers)} тарифных планов")
    return tiers


# ============================================================================
# ЭНДПОИНТЫ БАЗЫ ЗНАНИЙ
# ============================================================================

@app.post("/kb/upload/text", response_model=schemas.TextUploadResponse)
@limiter.limit("20/minute")
def upload_text_to_kb(request: Request, data: schemas.TextUploadRequest, db: Session = Depends(get_db)):
    """
    Загрузить текст в базу знаний.

    Проверяет лимиты пользователя перед загрузкой.
    """
    logger.info(f"Загрузка текста: telegram_id={data.telegram_id}")

    user_service = UserService(db)
    subscription_service = SubscriptionService(db)
    limits_service = LimitsService(db)
    document_service = DocumentService(db)

    # Получаем пользователя
    user = user_service.get_user_by_telegram_id(data.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем активную подписку
    subscription_info = subscription_service.get_active_subscription(user.id)
    if not subscription_info:
        raise HTTPException(status_code=400, detail="No active subscription")

    _, tier = subscription_info

    # Проверяем лимиты
    can_upload, error = limits_service.check_text_limits(user.id, tier)
    if not can_upload:
        logger.warning(f"Превышен лимит: user={data.telegram_id}, error={error}")
        raise HTTPException(status_code=400, detail=error)

    # Создаём документ
    new_doc = document_service.create_document(
        user_id=user.id,
        filename=f"text_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        file_type="text",
        status="completed",
        extracted_text=data.text
    )

    logger.info(f"Текст загружен: document_id={new_doc.id}, user={data.telegram_id}")

    return {"success": True, "document_id": new_doc.id}


@app.get("/kb/documents/{telegram_id}", response_model=schemas.DocumentsListResponse)
@limiter.limit("30/minute")
def get_user_documents(request: Request, telegram_id: int, db: Session = Depends(get_db)):
    """
    Получить список всех документов пользователя в базе знаний.

    Возвращает только неудалённые документы.
    """
    logger.debug(f"Запрос списка документов: telegram_id={telegram_id}")

    user_service = UserService(db)
    document_service = DocumentService(db)

    user = user_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    documents = document_service.get_user_documents(user.id)

    logger.debug(f"Возвращено {len(documents)} документов")

    return {
        "documents": documents,
        "total_count": len(documents)
    }


@app.post("/kb/upload/video", response_model=schemas.VideoUploadResponse)
@limiter.limit("10/minute")
def upload_videos_to_kb(request: Request, data: schemas.VideoUploadRequest, db: Session = Depends(get_db)):
    """
    Загрузить видео в базу знаний для обработки.

    Создаёт Celery задачи для транскрибации видео.
    """
    logger.info(f"Загрузка {len(data.videos)} видео: telegram_id={data.telegram_id}")

    user_service = UserService(db)
    subscription_service = SubscriptionService(db)
    document_service = DocumentService(db)

    user = user_service.get_user_by_telegram_id(data.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем тариф для определения приоритета
    subscription_info = subscription_service.get_active_subscription(user.id)
    if not subscription_info:
        raise HTTPException(status_code=400, detail="No active subscription")

    _, tier = subscription_info
    priority = get_priority(tier.tier_name)

    logger.info(f"Приоритет обработки: {priority} (tier={tier.tier_name})")

    # Создаём документы и задачи
    task_ids = []

    for video in data.videos:
        new_doc = document_service.create_document(
            user_id=user.id,
            filename=video['title'],
            file_type="video",
            status="pending",
            file_url=video['url'],
            duration_hours=video['duration']
        )

        # Запускаем Celery задачу
        task = process_video.apply_async(
            args=[video['url'], new_doc.id],
            priority=priority
        )
        task_ids.append(task.id)

        logger.info(f"Создана задача: task_id={task.id}, document_id={new_doc.id}")

    return {
        "success": True,
        "task_id": ",".join(task_ids),
        "message": f"Добавлено {len(data.videos)} видео в обработку"
    }


@app.get("/kb/video/status/{task_id}", response_model=schemas.VideoStatusResponse)
@limiter.limit("60/minute")
def get_video_status(request: Request, task_id: str):
    """
    Проверить статус обработки видео по ID задачи.
    """
    logger.debug(f"Проверка статуса: task_id={task_id}")

    task = AsyncResult(task_id, app=celery_app)

    return {
        "task_id": task_id,
        "status": task.state.lower(),
        "progress": task.info.get('progress') if isinstance(task.info, dict) else None,
        "error": str(task.info) if task.state == 'FAILURE' else None
    }


@app.put("/kb/documents/{document_id}/status")
@limiter.limit("100/minute")
def update_document_status(request: Request, document_id: int, data: dict, db: Session = Depends(get_db)):
    """
    Обновить статус обработки документа.

    Используется Celery задачами для обновления прогресса.
    """
    logger.debug(f"Обновление статуса: document_id={document_id}, status={data.get('status')}")

    document_service = DocumentService(db)

    success = document_service.update_document_status(
        document_id=document_id,
        status=data.get('status'),
        error=data.get('error'),
        transcription=data.get('transcription')
    )

    if not success:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"success": True}


@app.get("/kb/documents/{document_id}/info")
@limiter.limit("60/minute")
def get_document_info(request: Request, document_id: int, db: Session = Depends(get_db)):
    """
    Получить информацию о документе.

    Возвращает данные для отправки уведомлений пользователю.
    """
    logger.debug(f"Запрос информации: document_id={document_id}")

    user_service = UserService(db)
    document_service = DocumentService(db)

    doc = document_service.get_document_by_id(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    user = user_service.get_user_by_id(doc.user_id)

    return {
        "telegram_id": user.telegram_id,
        "filename": doc.filename,
        "extracted_text": doc.extracted_text,
        "file_url": doc.file_url,
        "status": doc.status
    }


@app.post("/kb/upload/photos", response_model=schemas.PhotoUploadResponse)
@limiter.limit("10/minute")
def upload_photos_to_kb(request: Request, data: schemas.PhotoUploadRequest, db: Session = Depends(get_db)):
    """
    Загрузить фото в базу знаний для OCR.
    """
    logger.info(f"Загрузка {len(data.photos)} фото: telegram_id={data.telegram_id}")

    user_service = UserService(db)
    subscription_service = SubscriptionService(db)
    limits_service = LimitsService(db)
    document_service = DocumentService(db)

    user = user_service.get_user_by_telegram_id(data.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем тариф
    subscription_info = subscription_service.get_active_subscription(user.id)
    if not subscription_info:
        raise HTTPException(status_code=400, detail="No active subscription")

    _, tier = subscription_info

    # Проверяем лимиты
    can_upload, error = limits_service.check_photo_limits(user.id, tier)
    if not can_upload:
        raise HTTPException(status_code=400, detail=error)

    priority = get_priority(tier.tier_name)
    task_ids = []

    for photo in data.photos:
        # Создаём документ
        new_doc = document_service.create_document(
            user_id=user.id,
            filename=photo['filename'],
            file_type="photo",
            status="pending"
        )

        # Загружаем в S3
        s3_key = upload_photo_to_s3(photo['base64'], user.id, new_doc.id)
        s3_url = f"{S3_BASE_URL}/{s3_key}"

        # Обновляем URL
        doc = document_service.get_document_by_id(new_doc.id)
        doc.file_url = s3_url
        db.commit()

        # Запускаем OCR
        task = process_photo_ocr.apply_async(
            args=[new_doc.id, s3_key],
            priority=priority
        )
        task_ids.append(task.id)

        logger.info(f"OCR задача создана: task_id={task.id}, document_id={new_doc.id}")

    return {
        "success": True,
        "uploaded_count": len(data.photos),
        "task_ids": task_ids
    }


@app.get("/kb/photo/{document_id}/presigned")
@limiter.limit("60/minute")
def get_photo_presigned_url_endpoint(
    request: Request,
    document_id: int,
    telegram_id: int,
    db: Session = Depends(get_db)
):
    """
    Получить presigned URL для просмотра оригинального фото.
    """
    logger.debug(f"Запрос presigned URL: document_id={document_id}, telegram_id={telegram_id}")

    user_service = UserService(db)
    document_service = DocumentService(db)

    # Проверяем пользователя
    user = user_service.get_user_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Получаем документ
    doc = document_service.get_document_by_id(document_id)
    if not doc or doc.file_type != "photo":
        raise HTTPException(status_code=404, detail="Photo not found")

    # ПРОВЕРКА ПРАВ ДОСТУПА
    if doc.user_id != user.id:
        logger.warning(f"Попытка доступа к чужому фото: user={user.id}, doc.user_id={doc.user_id}")
        raise HTTPException(status_code=403, detail="Access denied")

    # Извлекаем S3 ключ
    s3_key = doc.file_url.replace(f"{S3_BASE_URL}/", "")

    # Генерируем URL
    presigned_url = get_photo_presigned_url(s3_key, expiration=3600)

    return {
        "presigned_url": presigned_url,
        "expires_in": 3600
    }


@app.post("/kb/upload/files", response_model=schemas.FileUploadResponse)
@limiter.limit("10/minute")
def upload_files_to_kb(request: Request, data: schemas.FileUploadRequest, db: Session = Depends(get_db)):
    """
    Загрузить файлы (TXT, PDF, DOCX) в базу знаний.
    """
    logger.info(f"Загрузка {len(data.files)} файлов: telegram_id={data.telegram_id}")

    user_service = UserService(db)
    subscription_service = SubscriptionService(db)
    limits_service = LimitsService(db)
    document_service = DocumentService(db)

    user = user_service.get_user_by_telegram_id(data.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    subscription_info = subscription_service.get_active_subscription(user.id)
    if not subscription_info:
        raise HTTPException(status_code=400, detail="No active subscription")

    _, tier = subscription_info

    # Проверяем лимиты
    can_upload, error = limits_service.check_file_limits(user.id, tier)
    if not can_upload:
        raise HTTPException(status_code=400, detail=error)

    priority = get_priority(tier.tier_name)
    task_ids = []

    for file_data in data.files:
        extension = file_data['filename'].split('.')[-1].lower()

        # Создаём документ
        new_doc = document_service.create_document(
            user_id=user.id,
            filename=file_data['filename'],
            file_type="file",
            status="pending"
        )

        # Загружаем в S3
        s3_key = upload_file_to_s3(file_data['file_bytes'], user.id, new_doc.id, extension)
        s3_url = f"{S3_BASE_URL}/{s3_key}"

        # Обновляем URL
        doc = document_service.get_document_by_id(new_doc.id)
        doc.file_url = s3_url
        db.commit()

        # Запускаем обработку
        task = process_file.apply_async(
            args=[new_doc.id, s3_key, file_data['mime_type']],
            priority=priority
        )
        task_ids.append(task.id)

        logger.info(f"Файл обработка: task_id={task.id}, document_id={new_doc.id}")

    return {
        "success": True,
        "uploaded_count": len(data.files),
        "task_ids": task_ids
    }


@app.delete("/kb/documents/{document_id}")
@limiter.limit("30/minute")
def delete_document(request: Request, document_id: int, db: Session = Depends(get_db)):
    """
    Удалить документ из базы знаний (мягкое удаление).

    Для фото и файлов также удаляется объект из S3.
    """
    logger.info(f"Запрос на удаление: document_id={document_id}")

    document_service = DocumentService(db)

    document = document_service.get_document_by_id(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Удаляем из S3 если это фото или файл
    if document.file_type in ["photo", "file"] and document.file_url:
        try:
            s3_key = document.file_url.replace(f"{S3_BASE_URL}/", "")
            delete_from_s3(s3_key)
            logger.info(f"Удалён из S3: {s3_key}")
        except Exception as e:
            logger.error(f"Ошибка удаления из S3: {e}")

    # Мягкое удаление
    document_service.soft_delete_document(document_id)

    logger.info(f"Документ {document_id} удалён")

    return {"success": True, "message": "Document deleted"}


# === SUPPORT TICKET ENDPOINTS ===

@app.post("/support/tickets", response_model=schemas.SupportTicketResponse)
def create_support_ticket(
        ticket_data: schemas.SupportTicketCreate,
        db: Session = Depends(get_db)
):
    try:
        from backend.services.support_service import SupportService

        ticket = SupportService.create_ticket(
            db=db,
            telegram_id=ticket_data.telegram_id,
            category=ticket_data.category
        )

        return ticket
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка создания тикета: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/support/tickets/{ticket_id}/messages", response_model=schemas.SupportMessageResponse)
def add_ticket_message(
        ticket_id: int,
        message_data: schemas.SupportMessageCreate,
        db: Session = Depends(get_db)
):
    try:
        from backend.services.support_service import SupportService

        message = SupportService.add_message(
            db=db,
            ticket_id=ticket_id,
            sender_type=message_data.sender_type,
            sender_id=message_data.sender_id,
            message_text=message_data.message_text
        )

        return message
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка добавления сообщения: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/support/tickets", response_model=schemas.SupportTicketListResponse)
def get_user_tickets(
        telegram_id: int,
        status: Optional[str] = None,
        db: Session = Depends(get_db)
):
    try:
        from backend.services.support_service import SupportService

        tickets = SupportService.get_user_tickets(
            db=db,
            telegram_id=telegram_id,
            status=status
        )

        return {"tickets": tickets}
    except Exception as e:
        logger.error(f"Ошибка получения тикетов: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/support/tickets/all", response_model=schemas.SupportTicketListResponse)
def get_all_tickets(
        status: Optional[str] = None,
        db: Session = Depends(get_db)
):
    try:
        from backend.services.support_service import SupportService

        tickets = SupportService.get_all_tickets(
            db=db,
            status=status
        )

        return {"tickets": tickets}
    except Exception as e:
        logger.error(f"Ошибка получения всех тикетов: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/support/tickets/{ticket_id}/messages", response_model=List[schemas.SupportMessageResponse])
def get_ticket_messages(
        ticket_id: int,
        db: Session = Depends(get_db)
):
    try:
        from backend.services.support_service import SupportService

        messages = SupportService.get_ticket_messages(
            db=db,
            ticket_id=ticket_id
        )

        return messages
    except Exception as e:
        logger.error(f"Ошибка получения сообщений: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/support/tickets/{ticket_id}/close", response_model=schemas.SupportTicketResponse)
def close_ticket(
        ticket_id: int,
        db: Session = Depends(get_db)
):
    try:
        from backend.services.support_service import SupportService

        ticket = SupportService.close_ticket(
            db=db,
            ticket_id=ticket_id
        )

        return ticket
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка закрытия тикета: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# ЗАПУСК СЕРВЕРА
# ============================================================================

if __name__ == "__main__":
    logger.info(f"Запуск API на {os.getenv('API_HOST')}:{os.getenv('API_PORT')}")

    uvicorn.run(
        app,
        host=os.getenv("API_HOST"),
        port=int(os.getenv("API_PORT"))
    )