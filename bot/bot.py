"""
Главный файл Telegram бота.

Регистрирует все handlers, настраивает команды и запускает бота.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler
)
import signal
import sys
import logging

from shared.config import settings, CONTENT_CONFIG
from utils.bot_utils import api_request, get_user_stats, logger

# Импорт handlers из модулей
from bot.handlers import (
    # Common
    knowledge_base_menu,
    upload_file_menu,
    exit_upload,

    # Text
    upload_text,
    handle_text_upload,
    handle_wrong_media_in_text,
    WAITING_TEXT,

    # Video
    upload_video,
    handle_video_upload,
    handle_wrong_media_in_video,
    WAITING_VIDEO,

    # Photo
    upload_photo,
    global_photo_handler,

    # File
    upload_file_doc,
    reject_text_when_waiting_files,
    global_document_handler,

    # Documents
    my_files,
    my_texts,
    my_videos,
    my_photos,
    my_files_docs,
    view_document,
    show_photo_original,
    delete_document,
)

from bot.handlers.support_handlers import (
        support_menu,
        new_ticket_callback,
        my_tickets_callback,
        view_ticket_callback,
        handle_support_message,
        admin_tickets_command,
        admin_view_ticket,
        handle_admin_message,
        admin_close_ticket
    )

from bot.bot_subscriptions import (
    subscriptions_menu,
    handle_subscription_selection
)

# Executor для блокирующих операций (импортируем из video_handlers)
from bot.handlers.video_handlers import executor

import logging

# Отключаем verbose логи от библиотек
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# ============================================================================
# РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ
# ============================================================================

async def register_user_in_api(telegram_id: int, username: str = None):
    """
    Регистрация пользователя через API.

    Args:
        telegram_id: ID пользователя в Telegram
        username: Имя пользователя

    Returns:
        Данные пользователя или None при ошибке
    """
    success, data, error = await api_request(
        "POST",
        "/users/register",
        json={
            "telegram_id": telegram_id,
            "username": username
        }
    )

    if success:
        return data

    logger.error(f"Ошибка регистрации пользователя {telegram_id}: {error}")
    return None


# ============================================================================
# КОМАНДА /START
# ============================================================================

async def start(update: Update, context):
    """
    Команда /start - регистрация и главное меню.

    Args:
        update: Telegram Update
        context: Callback context
    """
    user = update.effective_user

    # Регистрируем пользователя
    api_user = await register_user_in_api(user.id, user.username)

    if not api_user:
        await update.message.reply_text("⚠️ Ошибка подключения к серверу. Попробуйте позже.")
        return

    # Получаем главное меню
    welcome_text, reply_markup = await build_main_menu(user.id, user.first_name)

    if not welcome_text:
        await update.message.reply_text("⚠️ Ошибка получения данных. Попробуйте позже.")
        return

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


async def build_main_menu(user_id: int, first_name: str):
    """
    Формирование главного меню со статистикой.

    Args:
        user_id: ID пользователя
        first_name: Имя пользователя

    Returns:
        Кортеж (текст, клавиатура) или (None, None) при ошибке
    """
    # Получаем статистику
    success, stats, error = await get_user_stats(user_id)

    if not success:
        return None, None

    # Формируем приветствие
    subscription_name = stats["subscription_name"]
    subscription_tier = stats["subscription_tier"]
    subscription_end = stats.get("subscription_end")
    messages_today = stats["messages_today"]
    messages_total = stats["messages_limit"]

    kb_storage = stats["kb_storage"]
    kb_daily = stats["kb_daily"]

    welcome_text = f"""👋 Привет, {first_name}!

Твой доступ к последним моделям ChatGPT 
с персональной базой знаний начинается тут.

🤑 Подписка: {subscription_name}"""

    if subscription_end:
        welcome_text += f"\n   Активна до: {subscription_end[:10]}"

    welcome_text += f"""

💬 Сообщений: {messages_today}/{messages_total} сегодня

📚 Ваша база знаний:"""

    content_order = ["video", "file", "photo", "text"]

    for content_type in content_order:
        config = CONTENT_CONFIG[content_type]
        storage_value = kb_storage.get(config["storage_key"])

        if storage_value and storage_value not in ["0/0", "0.00/0"]:
            if content_type == "video":
                welcome_text += f"\n   {config['icon']} {config['title_plural']}: {storage_value} {config['unit']}"
            else:
                welcome_text += f"\n   {config['icon']} {config['title_plural']}: {storage_value}"

    welcome_text += """

📤 Лимит загрузки сегодня:"""

    for content_type in content_order:
        config = CONTENT_CONFIG[content_type]
        daily_value = kb_daily.get(config["daily_key"])

        if daily_value and daily_value not in ["0/0", "0.00/0"]:
            if content_type == "video":
                welcome_text += f"\n   {config['icon']} {config['title_plural']}: {daily_value} {config['unit']}"
            else:
                welcome_text += f"\n   {config['icon']} {config['title_plural']}: {daily_value}"

    # Предложение апгрейда
    if subscription_tier not in ["ultra", "admin"]:
        welcome_text += "\n\n💎 Расширь свои возможности — купи \nследующий уровень подписки!"

    # Все 5 кнопок
    keyboard = [
        [InlineKeyboardButton("⭐ Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton("📚 База знаний бота", callback_data="knowledge_base")],
        [InlineKeyboardButton("⚙️ Режимы ответов", callback_data="settings_mode")],
        [InlineKeyboardButton("🆘 Тех. поддержка", callback_data="support")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    return welcome_text, reply_markup


async def back_to_main(update: Update, context):
    """
    Возврат в главное меню.

    Args:
        update: Telegram Update
        context: Callback context
    """
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем главное меню
    welcome_text, reply_markup = await build_main_menu(user.id, user.first_name)

    if not welcome_text:
        error_text = "⚠️ Ошибка получения данных. Попробуйте /start"

        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(user.id, error_text)
        else:
            await query.edit_message_text(error_text)
        return

    # Проверяем тип сообщения
    if query.message.photo:
        await query.message.delete()
        await context.bot.send_message(user.id, welcome_text, reply_markup=reply_markup)
    else:
        await query.edit_message_text(welcome_text, reply_markup=reply_markup)


# ============================================================================
# УСТАНОВКА КОМАНД БОТА
# ============================================================================

async def post_init(application):
    """
    Установка меню команд бота.

    Args:
        application: Telegram Application
    """
    commands = [
        BotCommand("start", "🏠 Главное меню"),
    ]
    await application.bot.set_my_commands(commands)

    logger.info("Команды бота установлены")


async def shutdown(application):
    """
    Обработчик завершения работы бота.

    Закрывает все ресурсы и потоки.

    Args:
        application: Telegram Application
    """
    logger.info("🛑 Закрытие ресурсов...")

    # Закрываем ThreadPoolExecutor
    logger.info("Закрытие ThreadPoolExecutor...")
    executor.shutdown(wait=True)

    logger.info("✓ Ресурсы освобождены")


# ============================================================================
# ИНИЦИАЛИЗАЦИЯ БОТА
# ============================================================================

def main():
    """Запуск бота с регистрацией всех handlers."""

    # Создание приложения
    app = ApplicationBuilder().token(settings.TELEGRAM_TOKEN).build()

    # Устанавливаем меню команд
    app.post_init = post_init

    # Регистрируем shutdown
    app.post_shutdown = shutdown

    # Команда /start
    app.add_handler(CommandHandler("start", start))

    # ========================================================================
    # CONVERSATION HANDLERS
    # ========================================================================

    # ConversationHandler для загрузки текста
    upload_text_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(upload_text, pattern="^upload_text$"),
        ],
        states={
            WAITING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_upload),
                MessageHandler(filters.PHOTO | filters.Document.ALL | filters.VIDEO, handle_wrong_media_in_text),
            ]
        },
        fallbacks=[
            CallbackQueryHandler(exit_upload, pattern="^exit_upload$"),
            CallbackQueryHandler(upload_file_menu, pattern="^upload_file$"),
            CallbackQueryHandler(knowledge_base_menu, pattern="^knowledge_base$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$"),
        ]
    )
    app.add_handler(upload_text_handler)

    # ConversationHandler для загрузки видео
    upload_video_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(upload_video, pattern="^upload_video$"),
        ],
        states={
            WAITING_VIDEO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_upload),
                MessageHandler(filters.PHOTO | filters.Document.ALL | filters.VIDEO, handle_wrong_media_in_video),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(exit_upload, pattern="^exit_upload$"),
            CallbackQueryHandler(upload_file_menu, pattern="^upload_file$"),
            CallbackQueryHandler(knowledge_base_menu, pattern="^knowledge_base$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$"),
        ],
    )
    app.add_handler(upload_video_handler)

    # ========================================================================
    # ГЛОБАЛЬНЫЕ ОБРАБОТЧИКИ (group=0)
    # ========================================================================

    app.add_handler(MessageHandler(filters.PHOTO, global_photo_handler), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reject_text_when_waiting_files), group=0)
    app.add_handler(MessageHandler(filters.Document.ALL, global_document_handler), group=0)

    # ========================================================================
    # CALLBACK HANDLERS
    # ========================================================================

    # Главное меню
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))

    # Подписки
    app.add_handler(CallbackQueryHandler(subscriptions_menu, pattern="^subscriptions$"))
    app.add_handler(CallbackQueryHandler(handle_subscription_selection, pattern="^sub_"))

    # База знаний
    app.add_handler(CallbackQueryHandler(knowledge_base_menu, pattern="^knowledge_base$"))
    app.add_handler(CallbackQueryHandler(upload_file_menu, pattern="^upload_file$"))
    app.add_handler(CallbackQueryHandler(my_files, pattern="^my_files$"))
    app.add_handler(CallbackQueryHandler(my_texts, pattern="^my_texts$"))
    app.add_handler(CallbackQueryHandler(my_videos, pattern="^my_videos$"))
    app.add_handler(CallbackQueryHandler(my_photos, pattern="^my_photos$"))
    app.add_handler(CallbackQueryHandler(my_files_docs, pattern="^my_files_docs$"))
    app.add_handler(CallbackQueryHandler(view_document, pattern="^view_doc_"))
    app.add_handler(CallbackQueryHandler(show_photo_original, pattern="^show_photo_"))
    app.add_handler(CallbackQueryHandler(delete_document, pattern="^delete_doc_"))
    app.add_handler(CallbackQueryHandler(upload_photo, pattern="^upload_photo$"))
    app.add_handler(CallbackQueryHandler(upload_file_doc, pattern="^upload_file_doc$"))
    app.add_handler(CallbackQueryHandler(exit_upload, pattern="^exit_upload$"))

    # Тех. поддержка
    app.add_handler(CallbackQueryHandler(support_menu, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(new_ticket_callback, pattern="^new_ticket$"))
    app.add_handler(CallbackQueryHandler(my_tickets_callback, pattern="^my_tickets$"))
    app.add_handler(CallbackQueryHandler(view_ticket_callback, pattern="^view_ticket_"))
    app.add_handler(CallbackQueryHandler(admin_view_ticket, pattern="^admin_view_"))
    app.add_handler(CallbackQueryHandler(admin_close_ticket, pattern="^admin_close_"))
    app.add_handler(CommandHandler("admin_tickets", admin_tickets_command))

    # Message handler для тикетов (group=1, после глобальных)
    async def support_message_router(update: Update, context):
        if context.user_data.get('admin_reply_ticket'):
            await handle_admin_message(update, context)
        elif context.user_data.get('active_ticket_id'):
            await handle_support_message(update, context)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, support_message_router), group=1)

    logger.info("🤖 Бот запущен!")

    # Запускаем бота с graceful shutdown
    try:
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    finally:
        logger.info("✅ Завершение работы бота")


# ============================================================================
# GRACEFUL SHUTDOWN
# ============================================================================

def signal_handler(sig, frame):
    """
    Обработчик сигналов остановки.

    Args:
        sig: Сигнал
        frame: Фрейм
    """
    logger.info("🛑 Получен сигнал завершения (Ctrl+C)")
    sys.exit(0)


# Регистрируем обработчик сигналов
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    main()