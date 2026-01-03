from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timezone
from typing import List, Optional
from backend.models import SupportTicket, SupportMessage, User
from backend.schemas import (
    SupportTicketCreate,
    SupportTicketResponse,
    SupportMessageCreate,
    SupportMessageResponse
)


class SupportService:

    @staticmethod
    def create_ticket(
            db: Session,
            telegram_id: int,
            category: str
    ) -> SupportTicket:
        # Получаем пользователя
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            raise ValueError("User not found")

        # Создаём тикет
        ticket = SupportTicket(
            user_id=user.id,
            telegram_id=telegram_id,
            username=user.username,
            category=category,
            status="open",
            created_at=datetime.now(timezone.utc)
        )

        db.add(ticket)
        db.commit()
        db.refresh(ticket)

        return ticket

    @staticmethod
    def add_message(
            db: Session,
            ticket_id: int,
            sender_type: str,
            sender_id: int,
            message_text: str
    ) -> SupportMessage:
        # Проверяем что тикет существует
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
        if not ticket:
            raise ValueError("Ticket not found")

        # Создаём сообщение
        message = SupportMessage(
            ticket_id=ticket_id,
            sender_type=sender_type,
            sender_id=sender_id,
            message_text=message_text,
            created_at=datetime.now(timezone.utc)
        )

        db.add(message)
        db.commit()
        db.refresh(message)

        return message

    @staticmethod
    def get_user_tickets(
            db: Session,
            telegram_id: int,
            status: Optional[str] = None
    ) -> List[SupportTicket]:
        query = db.query(SupportTicket).filter(
            SupportTicket.telegram_id == telegram_id
        )

        if status:
            query = query.filter(SupportTicket.status == status)

        return query.order_by(SupportTicket.created_at.desc()).all()

    @staticmethod
    def get_all_tickets(
            db: Session,
            status: Optional[str] = None
    ) -> List[SupportTicket]:
        query = db.query(SupportTicket)

        if status:
            query = query.filter(SupportTicket.status == status)

        return query.order_by(SupportTicket.created_at.desc()).all()

    @staticmethod
    def get_ticket_messages(
            db: Session,
            ticket_id: int
    ) -> List[SupportMessage]:
        return db.query(SupportMessage).filter(
            SupportMessage.ticket_id == ticket_id
        ).order_by(SupportMessage.created_at.asc()).all()

    @staticmethod
    def close_ticket(
            db: Session,
            ticket_id: int
    ) -> SupportTicket:
        ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
        if not ticket:
            raise ValueError("Ticket not found")

        ticket.status = "closed"
        ticket.closed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(ticket)

        return ticket

    @staticmethod
    def get_ticket_by_id(
            db: Session,
            ticket_id: int
    ) -> Optional[SupportTicket]:
        return db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()