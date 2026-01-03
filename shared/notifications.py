# Сервис уведомлений пользователей

import httpx
import logging
from typing import Optional, List
from shared.config import settings, CONTENT_CONFIG, NOTIFICATION_TEMPLATES

logger = logging.getLogger(__name__)


class NotificationService:
    # Сервис для отправки уведомлений пользователям

    @staticmethod
    async def send_message(
            telegram_id: int,
            text: str,
            keyboard: Optional[List[List[dict]]] = None
    ) -> None:
        # Отправка сообщения пользователю
        # keyboard: список списков с dict вида {"text": "...", "callback_data": "..."}

        bot_token = settings.TELEGRAM_TOKEN

        try:
            payload = {
                "chat_id": telegram_id,
                "text": text,
                "parse_mode": "HTML"
            }

            # Добавляем клавиатуру если есть
            if keyboard:
                payload["reply_markup"] = {
                    "inline_keyboard": keyboard
                }

            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=payload
                )

            logger.info(f"Отправлено уведомление пользователю {telegram_id}")

        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {telegram_id}: {e}")

    @staticmethod
    async def send_photo(
            telegram_id: int,
            photo_bytes: bytes,
            caption: str,
            keyboard: Optional[List[List[dict]]] = None
    ) -> None:
        # Отправка фото с подписью пользователю

        bot_token = settings.TELEGRAM_TOKEN

        try:
            # Формируем multipart request
            files = {
                'photo': ('photo.jpg', photo_bytes, 'image/jpeg')
            }

            data = {
                'chat_id': str(telegram_id),
                'caption': caption,
                'parse_mode': 'HTML'
            }

            if keyboard:
                import json
                data['reply_markup'] = json.dumps({"inline_keyboard": keyboard})

            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                    files=files,
                    data=data
                )

            logger.info(f"Отправлено фото пользователю {telegram_id}")

        except Exception as e:
            logger.error(f"Ошибка отправки фото пользователю {telegram_id}: {e}")

    @staticmethod
    async def send_success(
            telegram_id: int,
            content_type: str,
            **kwargs
    ) -> None:
        # Отправка уведомления об успешной обработке
        # kwargs: параметры для шаблона (filename, text, count и т.д.)

        config = CONTENT_CONFIG[content_type]

        # Формируем текст из шаблона
        template_key = content_type

        # Для фото проверяем длину текста
        if content_type == "photo":
            text = kwargs.get("text", "")
            if len(text) > 900:
                template_key = "photo_truncated"
                kwargs["text"] = text[:900]

        template = NOTIFICATION_TEMPLATES.get(template_key, "✅ Обработка завершена!")
        message_text = template.format(**kwargs)

        # Формируем клавиатуру
        keyboard = [
            [
                {"text": f"📤 Загрузить ещё {config['title_plural_lower']}",
                 "callback_data": config['callbacks']['upload']},
                {"text": f"{config['icon']} Мои {config['title_plural_lower']}",
                 "callback_data": config['callbacks']['my_list']}
            ],
            [
                {"text": "🏠 Главное меню", "callback_data": "back_to_main"}
            ]
        ]

        # Для фото отправляем с изображением
        if content_type == "photo" and "photo_bytes" in kwargs:
            await NotificationService.send_photo(
                telegram_id,
                kwargs["photo_bytes"],
                message_text,
                keyboard
            )
        else:
            await NotificationService.send_message(
                telegram_id,
                message_text,
                keyboard
            )


    # === SUPPORT TICKET NOTIFICATIONS ===

    @staticmethod
    async def notify_admin_new_ticket(bot, ticket_id: int, user_id: int, username: str, category: str):
        """Уведомление админу о новом тикете"""
        from shared.config import settings

        admin_id = settings.ADMIN_TELEGRAM_ID
        if admin_id == 0:
            logger.warning("ADMIN_TELEGRAM_ID не настроен")
            return

        text = (
            f"🆕 <b>Новый тикет поддержки</b>\n\n"
            f"📋 ID тикета: {ticket_id}\n"
            f"👤 Пользователь: @{username or 'без username'} (ID: {user_id})\n"
            f"📂 Категория: {category}\n\n"
            f"Используй /admin_tickets для просмотра"
        )

        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу: {e}")

    @staticmethod
    async def notify_user_admin_reply(bot, user_id: int, ticket_id: int, admin_message: str):
        """Уведомление пользователю об ответе админа"""

        text = (
            f"💬 <b>Ответ от поддержки</b>\n\n"
            f"📋 Тикет #{ticket_id}\n\n"
            f"{admin_message}\n\n"
            f"Используй /my_tickets для просмотра диалога"
        )

        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю: {e}")

    @staticmethod
    async def notify_user_ticket_closed(bot, user_id: int, ticket_id: int):
        """Уведомление пользователю о закрытии тикета"""

        text = (
            f"✅ <b>Тикет закрыт</b>\n\n"
            f"📋 Тикет #{ticket_id} был закрыт.\n\n"
            f"Если у вас остались вопросы, создайте новый тикет: /support"
        )

        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю: {e}")