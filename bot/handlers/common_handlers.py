"""
Общие handlers для работы с базой знаний.

Включает меню базы знаний, меню загрузки файлов,
выход из режима загрузки.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from shared.config import CONTENT_CONFIG, Messages
from utils.bot_utils import (
    get_user_stats,
    ButtonFactory,
    photo_uploader,
    file_uploader,
    logger
)


async def knowledge_base_menu(update: Update, context):
    """
    Главное меню базы знаний.

    Args:
        update: Telegram Update
        context: Callback context
    """
    query = update.callback_query
    await query.answer()

    text = """
📚 База знаний

Управляйте своими файлами и обучайте
неросеть под ваши задачи!
"""

    keyboard = [
        [InlineKeyboardButton("📤 Загрузить файл", callback_data="upload_file")],
        [InlineKeyboardButton("📋 Мои файлы", callback_data="my_files")],
        [ButtonFactory.back_to_main()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def upload_file_menu(update: Update, context):
    """
    Меню выбора типа контента для загрузки.

    Показывает только доступные типы на основе тарифа пользователя.

    Args:
        update: Telegram Update
        context: Callback context
    """
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем статистику для определения доступных типов
    success, stats, error = await get_user_stats(user.id)

    if not success:
        await query.edit_message_text(
            Messages.ERROR_CONNECTION,
            reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("knowledge_base")]])
        )
        return

    kb_storage = stats["kb_storage"]

    text = """📤 Загрузка контента\n\nВыберите тип:"""
    keyboard = []

    # Показываем только доступные типы
    for content_type, config in CONTENT_CONFIG.items():
        storage_value = kb_storage.get(config["storage_key"])
        if storage_value and storage_value not in ["0/0"]:
            keyboard.append([InlineKeyboardButton(
                f"{config['icon']} {config['title']}",
                callback_data=config['callbacks']['upload']
            )])

    keyboard.append([ButtonFactory.back_button("knowledge_base")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def exit_upload(update: Update, context):
    """
    Выход из режима загрузки.

    Останавливает все активные режимы ожидания (фото, файлы)
    и возвращает в меню загрузки.

    Args:
        update: Telegram Update
        context: Callback context

    Returns:
        ConversationHandler.END
    """
    query = update.callback_query
    await query.answer()

    # Останавливаем все режимы
    await photo_uploader.stop_upload_mode(context)
    await file_uploader.stop_upload_mode(context)

    logger.info(f"Пользователь {query.from_user.id} вышел из режима загрузки")

    await upload_file_menu(update, context)

    return ConversationHandler.END