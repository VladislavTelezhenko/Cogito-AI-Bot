"""
Сервис для работы с документами в базе знаний.

Управление загрузкой, обработкой и удалением документов.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging

from backend.models import UserDocument, User
from shared.config import DocumentStatus

logger = logging.getLogger(__name__)


class DocumentService:
    """Сервис для управления документами."""

    def __init__(self, db: Session):
        """
        Инициализация сервиса.

        Args:
            db: Сессия базы данных
        """
        self.db = db

    def create_document(
        self,
        user_id: int,
        filename: str,
        file_type: str,
        status: str = DocumentStatus.PENDING,
        **kwargs
    ) -> UserDocument:
        """
        Создать новый документ.

        Args:
            user_id: ID пользователя
            filename: Имя файла
            file_type: Тип (text, video, photo, file)
            status: Статус обработки
            **kwargs: Дополнительные поля (file_url, duration_hours, extracted_text)

        Returns:
            Созданный документ
        """
        new_doc = UserDocument(
            user_id=user_id,
            filename=filename,
            file_type=file_type,
            status=status,
            **kwargs
        )

        self.db.add(new_doc)
        self.db.commit()
        self.db.refresh(new_doc)

        logger.info(f"Создан документ: id={new_doc.id}, type={file_type}, user={user_id}")

        return new_doc

    def get_document_by_id(self, document_id: int) -> Optional[UserDocument]:
        """
        Получить документ по ID.

        Args:
            document_id: ID документа

        Returns:
            Документ или None
        """
        return self.db.query(UserDocument).filter(
            UserDocument.id == document_id
        ).first()

    def get_user_documents(
        self,
        user_id: int,
        file_type: Optional[str] = None,
        include_deleted: bool = False
    ) -> List[UserDocument]:
        """
        Получить документы пользователя.

        Args:
            user_id: ID пользователя
            file_type: Фильтр по типу (опционально)
            include_deleted: Включить удаленные

        Returns:
            Список документов
        """
        query = self.db.query(UserDocument).filter(
            UserDocument.user_id == user_id
        )

        if file_type:
            query = query.filter(UserDocument.file_type == file_type)

        if not include_deleted:
            query = query.filter(UserDocument.is_deleted == False)

        return query.order_by(UserDocument.upload_date.desc()).all()

    def update_document_status(
        self,
        document_id: int,
        status: str,
        error: Optional[str] = None,
        transcription: Optional[str] = None
    ) -> bool:
        """
        Обновить статус документа.

        Args:
            document_id: ID документа
            status: Новый статус
            error: Сообщение об ошибке (опционально)
            transcription: Распознанный текст (опционально)

        Returns:
            True если успешно
        """
        doc = self.get_document_by_id(document_id)

        if not doc:
            logger.warning(f"Документ {document_id} не найден для обновления статуса")
            return False

        # Если есть ошибка - ставим failed
        if error:
            doc.status = DocumentStatus.FAILED
        else:
            doc.status = status

        if transcription:
            doc.extracted_text = transcription

        self.db.commit()

        logger.info(f"Обновлен статус документа {document_id}: {doc.status}")

        return True

    def soft_delete_document(self, document_id: int) -> bool:
        """
        Мягкое удаление документа.

        Args:
            document_id: ID документа

        Returns:
            True если успешно
        """
        doc = self.get_document_by_id(document_id)

        if not doc:
            logger.warning(f"Документ {document_id} не найден для удаления")
            return False

        doc.is_deleted = True
        doc.deleted_at = datetime.now()
        doc.extracted_text = ""  # Очищаем текст

        self.db.commit()

        logger.info(f"Документ {document_id} помечен как удаленный")

        return True

    def get_document_counts(
        self,
        user_id: int,
        file_type: str,
        include_today_only: bool = False
    ) -> int:
        """
        Получить количество документов пользователя.

        Args:
            user_id: ID пользователя
            file_type: Тип файла
            include_today_only: Считать только за сегодня

        Returns:
            Количество документов
        """
        query = self.db.query(func.count(UserDocument.id)).filter(
            UserDocument.user_id == user_id,
            UserDocument.file_type == file_type,
            UserDocument.is_deleted == False
        )

        if file_type in ["photo", "file"]:
            query = query.filter(UserDocument.status == DocumentStatus.COMPLETED)

        if include_today_only:
            today = func.date(func.now())
            query = query.filter(func.date(UserDocument.upload_date) == today)

        return query.scalar() or 0

    def get_video_hours(
        self,
        user_id: int,
        include_today_only: bool = False
    ) -> float:
        """
        Получить общую длительность видео в часах.

        Args:
            user_id: ID пользователя
            include_today_only: Считать только за сегодня

        Returns:
            Длительность в часах
        """
        query = self.db.query(func.sum(UserDocument.duration_hours)).filter(
            UserDocument.user_id == user_id,
            UserDocument.file_type == "video",
            UserDocument.status == DocumentStatus.COMPLETED,
            UserDocument.is_deleted == False
        )

        if include_today_only:
            today = func.date(func.now())
            query = query.filter(func.date(UserDocument.upload_date) == today)

        result = query.scalar()

        return result if result else 0.0