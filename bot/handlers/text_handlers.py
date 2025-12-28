"""
Handlers для загрузки текста в базу знаний.

Включает ConversationHandler для приёма текста от пользователя.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from shared.config import Messages
from utils.bot_utils import (
    api_request,
    check_upload_limits,
    ButtonFactory,
    logger
)

# Состояние ConversationHandler
WAITING_TEXT = 0


async def upload_text(update: Update, context):
    """
    Начало загрузки текста.

    Проверяет лимиты и переводит пользователя в режим ожидания текста.

    Args:
        update: Telegram Update
        context: Callback context

    Returns:
        WAITING_TEXT или ConversationHandler.END
    """
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Проверяем лимиты
    can_upload, error_message, keyboard = await check_upload_limits(user.id, "text")

    if not can_upload:
        await query.edit_message_text(error_message, reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    # Лимиты OK - ждём текст
    text = """
📝 Загрузка текста

Отправьте ваш текст в следующем сообщении:
"""

    keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="exit_upload")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)

    logger.info(f"Пользователь {user.id} начал загрузку текста")

    return WAITING_TEXT


async def handle_text_upload(update: Update, context):
    """
    Обработка текста от пользователя.

    Отправляет текст в API для сохранения в базу знаний.

    Args:
        update: Telegram Update
        context: Callback context

    Returns:
        ConversationHandler.END
    """
    # Проверка на вложения
    if update.message.photo or update.message.document or update.message.video:
        keyboard = [[ButtonFactory.back_button("exit_upload")]]
        await update.message.reply_text(
            "⚠️ Отправьте только текст без вложений.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_TEXT

    text_content = update.message.text
    user = update.effective_user

    await update.message.reply_text("⏳ Сохраняю текст в базу знаний...")

    # Отправляем в API
    success, data, error = await api_request(
        "POST",
        "/kb/upload/text",
        json={
            "telegram_id": user.id,
            "text": text_content
        }
    )

    if success:
        logger.info(f"Текст успешно загружен для пользователя {user.id}")

        await update.message.reply_text(
            "✅ Текст успешно добавлен в базу знаний!\n\n"
            "Теперь вы можете задавать вопросы по этому материалу\nили обучать нейросеть.",
            reply_markup=InlineKeyboardMarkup(ButtonFactory.success_keyboard("text"))
        )
    else:
        logger.error(f"Ошибка загрузки текста для пользователя {user.id}: {error}")
        await update.message.reply_text(Messages.ERROR_UPLOAD)

    return ConversationHandler.END


async def handle_wrong_media_in_text(update: Update, context):
    """
    Обработчик неправильного типа медиа при загрузке текста.

    Напоминает пользователю отправить только текст.

    Args:
        update: Telegram Update
        context: Callback context

    Returns:
        WAITING_TEXT
    """
    await update.message.reply_text(
        "⚠️ Пожалуйста, отправьте только текст без вложений.\n\n"
        "Для загрузки файлов, фото или видео используйте соответствующий раздел меню.",
        reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("exit_upload")]])
    )

    return WAITING_TEXT