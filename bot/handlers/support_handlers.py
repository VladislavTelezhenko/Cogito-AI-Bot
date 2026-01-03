from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import logging
import httpx
from shared.config import settings
from shared.notifications import NotificationService
from utils.bot_utils import ButtonFactory

logger = logging.getLogger(__name__)


# === МЕНЮ ПОДДЕРЖКИ ===

async def support_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню поддержки"""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("📝 Новая заявка", callback_data="new_ticket")],
        [InlineKeyboardButton("📋 Мои заявки", callback_data="my_tickets")],
        [ButtonFactory.back_to_main()]
    ]

    await query.edit_message_text(
        "🆘 <b>Служба поддержки</b>\n\n"
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def new_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание новой заявки"""
    query = update.callback_query
    await query.answer()

    user = update.effective_user

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.API_URL}/support/tickets",
                json={
                    "telegram_id": user.id,
                    "category": "general"
                },
                timeout=10.0
            )

            if response.status_code == 200:
                ticket_data = response.json()
                ticket_id = ticket_data["id"]

                context.user_data['active_ticket_id'] = ticket_id

                keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="support")]]

                await query.edit_message_text(
                    f"✅ <b>Заявка #{ticket_id} создана</b>\n\n"
                    f"Опишите вашу проблему в следующем сообщении.\n"
                    f"Поддержка ответит в ближайшее время.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML"
                )

                # Уведомляем админа
                await NotificationService.notify_admin_new_ticket(
                    bot=context.bot,
                    ticket_id=ticket_id,
                    user_id=user.id,
                    username=user.username,
                    category="general"
                )

            else:
                await query.edit_message_text(
                    "❌ Ошибка создания заявки. Попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="support")]])
                )

    except Exception as e:
        logger.error(f"Ошибка создания заявки: {e}")
        await query.edit_message_text(
            "❌ Ошибка создания заявки. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="support")]])
        )


async def my_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр заявок пользователя"""
    query = update.callback_query
    await query.answer()

    user = update.effective_user

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.API_URL}/support/tickets",
                params={"telegram_id": user.id},
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                tickets = data["tickets"]

                if not tickets:
                    await query.edit_message_text(
                        "📋 У вас пока нет заявок.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="support")]])
                    )
                    return

                text = "📋 <b>Ваши заявки:</b>\n\n"
                keyboard = []

                for ticket in tickets:
                    status_emoji = "🟢" if ticket["status"] == "open" else "⚪"
                    text += (
                        f"{status_emoji} Заявка #{ticket['id']}\n"
                        f"Статус: {ticket['status']}\n\n"
                    )

                    if ticket["status"] == "open":
                        keyboard.append([
                            InlineKeyboardButton(
                                f"Открыть #{ticket['id']}",
                                callback_data=f"view_ticket_{ticket['id']}"
                            )
                        ])

                keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="support")])

                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML"
                )
            else:
                await query.edit_message_text(
                    "❌ Ошибка получения заявок",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="support")]])
                )

    except Exception as e:
        logger.error(f"Ошибка получения заявок: {e}")
        await query.edit_message_text(
            "❌ Ошибка получения заявок",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="support")]])
        )


async def view_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр диалога в заявке"""
    query = update.callback_query
    await query.answer()

    ticket_id = int(query.data.split("_")[-1])

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.API_URL}/support/tickets/{ticket_id}/messages",
                timeout=10.0
            )

            if response.status_code == 200:
                messages = response.json()

                text = f"📋 <b>Заявка #{ticket_id}</b>\n\n"

                if not messages:
                    text += "Сообщений пока нет.\n\n"
                else:
                    for msg in messages:
                        sender = "👤 Вы" if msg["sender_type"] == "user" else "🛠 Поддержка"
                        text += f"{sender}:\n{msg['message_text']}\n\n"

                text += "💬 Напишите сообщение для ответа:"

                context.user_data['active_ticket_id'] = ticket_id

                keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="my_tickets")]]

                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML"
                )
            else:
                await query.edit_message_text(
                    "❌ Ошибка загрузки заявки",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="my_tickets")]])
                )

    except Exception as e:
        logger.error(f"Ошибка просмотра заявки: {e}")
        await query.edit_message_text(
            "❌ Ошибка загрузки заявки",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="my_tickets")]])
        )


async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщения в заявку"""

    ticket_id = context.user_data.get('active_ticket_id')
    if not ticket_id:
        return

    user = update.effective_user
    message_text = update.message.text

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.API_URL}/support/tickets/{ticket_id}/messages",
                json={
                    "sender_type": "user",
                    "sender_id": user.id,
                    "message_text": message_text
                },
                timeout=10.0
            )

            if response.status_code == 200:
                await update.message.reply_text(
                    "✅ Сообщение отправлено!\n\n"
                    "Поддержка ответит в ближайшее время.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("◀️ К заявкам", callback_data="my_tickets")]])
                )

                context.user_data.pop('active_ticket_id', None)
            else:
                await update.message.reply_text("❌ Ошибка отправки сообщения")

    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        await update.message.reply_text("❌ Ошибка отправки сообщения")


# === ДЛЯ АДМИНА ===

async def admin_tickets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ смотрит все заявки"""
    user = update.effective_user

    if user.id != settings.ADMIN_TELEGRAM_ID:
        await update.message.reply_text("❌ Нет доступа")
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.API_URL}/support/tickets/all",
                params={"status": "open"},
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                tickets = data["tickets"]

                if not tickets:
                    await update.message.reply_text("📋 Нет открытых заявок")
                    return

                text = "📋 <b>Открытые заявки:</b>\n\n"
                keyboard = []

                for ticket in tickets:
                    text += (
                        f"🆔 #{ticket['id']}\n"
                        f"👤 @{ticket['username'] or 'no username'}\n\n"
                    )

                    keyboard.append([
                        InlineKeyboardButton(
                            f"Открыть #{ticket['id']}",
                            callback_data=f"admin_view_{ticket['id']}"
                        )
                    ])

                await update.message.reply_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text("❌ Ошибка")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка")


async def admin_view_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ открывает заявку"""
    query = update.callback_query
    await query.answer()

    ticket_id = int(query.data.split("_")[-1])

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.API_URL}/support/tickets/{ticket_id}/messages",
                timeout=10.0
            )

            if response.status_code == 200:
                messages = response.json()

                text = f"📋 <b>Заявка #{ticket_id}</b>\n\n"

                if messages:
                    for msg in messages:
                        sender = "👤 User" if msg["sender_type"] == "user" else "🛠 Admin"
                        text += f"{sender}:\n{msg['message_text']}\n\n"

                text += "💬 Напишите ответ:"

                context.user_data['admin_reply_ticket'] = ticket_id

                keyboard = [
                    [InlineKeyboardButton("✅ Закрыть", callback_data=f"admin_close_{ticket_id}")]
                ]

                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML"
                )
            else:
                await query.edit_message_text("❌ Ошибка")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await query.edit_message_text("❌ Ошибка")


async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответа админа"""

    ticket_id = context.user_data.get('admin_reply_ticket')
    if not ticket_id:
        return

    admin = update.effective_user
    if admin.id != settings.ADMIN_TELEGRAM_ID:
        return

    message_text = update.message.text

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.API_URL}/support/tickets/{ticket_id}/messages",
                json={
                    "sender_type": "admin",
                    "sender_id": admin.id,
                    "message_text": message_text
                },
                timeout=10.0
            )

            if response.status_code == 200:
                # Получаем telegram_id пользователя
                messages_response = await client.get(
                    f"{settings.API_URL}/support/tickets/{ticket_id}/messages",
                    timeout=10.0
                )

                if messages_response.status_code == 200:
                    msgs = messages_response.json()
                    if msgs:
                        user_id = msgs[0]["sender_id"]
                        await NotificationService.notify_user_admin_reply(
                            bot=context.bot,
                            user_id=user_id,
                            ticket_id=ticket_id,
                            admin_message=message_text
                        )

                await update.message.reply_text("✅ Ответ отправлен!")
                context.user_data.pop('admin_reply_ticket', None)
            else:
                await update.message.reply_text("❌ Ошибка")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка")


async def admin_close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ закрывает заявку"""
    query = update.callback_query
    await query.answer()

    ticket_id = int(query.data.split("_")[-1])

    try:
        async with httpx.AsyncClient() as client:
            # Получаем user_id
            messages_response = await client.get(
                f"{settings.API_URL}/support/tickets/{ticket_id}/messages",
                timeout=10.0
            )

            user_id = None
            if messages_response.status_code == 200:
                msgs = messages_response.json()
                if msgs:
                    user_id = msgs[0]["sender_id"]

            # Закрываем
            response = await client.post(
                f"{settings.API_URL}/support/tickets/{ticket_id}/close",
                timeout=10.0
            )

            if response.status_code == 200:
                await query.edit_message_text(f"✅ Заявка #{ticket_id} закрыта")

                if user_id:
                    await NotificationService.notify_user_ticket_closed(
                        bot=context.bot,
                        user_id=user_id,
                        ticket_id=ticket_id
                    )
            else:
                await query.edit_message_text("❌ Ошибка")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await query.edit_message_text("❌ Ошибка")