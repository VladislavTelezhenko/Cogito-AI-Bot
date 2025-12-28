# Главный файл Telegram бота

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler
)

from shared.config import settings, CONTENT_CONFIG
from utils.bot_utils import api_request, get_user_stats, logger

# Импорт handlers из модулей
from bot_knowledge_base import (
    knowledge_base_menu,
    upload_file_menu,
    upload_text,
    handle_text_upload,
    handle_wrong_media_in_text,
    upload_video,
    handle_video_upload,
    handle_wrong_media_in_video,
    upload_photo,
    global_photo_handler,
    upload_file_doc,
    reject_text_when_waiting_files,
    reject_photo_when_waiting_files,
    global_document_handler,
    my_files,
    my_texts,
    my_videos,
    my_photos,
    my_files_docs,
    view_document,
    show_photo_original,
    delete_document,
    exit_upload,
    WAITING_TEXT,
    WAITING_VIDEO,
    executor
)

from bot_subscriptions import (
    subscriptions_menu,
    handle_subscription_selection
)
import signal
import sys


# ============================================================================
# РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ
# ============================================================================

# Регистрация пользователя через API
async def register_user_in_api(telegram_id: int, username: str = None):
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

# Команда /start
async def start(update: Update, context):
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


# ============================================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================================

# Формирование главного меню
async def build_main_menu(user_id: int, first_name: str):
    # Получаем статистику
    success, stats, error = await get_user_stats(user_id)

    if not success:
        return None, None

    # Формируем приветствие
    subscription_name = stats["subscription_name"]
    subscription_tier = stats["subscription_tier"]
    subscription_end = stats.get("subscription_end")
    messages_left = stats["messages_limit"] - stats["messages_today"]
    messages_total = stats["messages_limit"]

    kb_storage = stats["kb_storage"]
    kb_daily = stats["kb_daily"]

    welcome_text = f"""
👋 Привет, {first_name}!

Твой доступ к последним моделям ChatGPT 
с персональной базой знаний начинается тут.

🤑 Подписка: {subscription_name}
"""

    if subscription_end:
        welcome_text += f"   Активна до: {subscription_end[:10]}\n"

    welcome_text += f"""
💬 Сообщений: {messages_left}/{messages_total} сегодня

📚 Ваша база знаний:
"""

    # Показываем типы файлов через CONTENT_CONFIG
    for content_type, config in CONTENT_CONFIG.items():
        storage_value = kb_storage.get(config["storage_key"])

        if storage_value and storage_value not in ["0/0"]:
            if "∞" in storage_value:
                welcome_text += f"   {config['icon']} {config['title_plural']}: {storage_value} {config['unit']}\n"
            else:
                welcome_text += f"   {config['icon']} {config['title_plural']}: {storage_value}\n"

    welcome_text += """
📤 Лимит загрузки сегодня:
"""

    # Показываем дневные лимиты
    for content_type, config in CONTENT_CONFIG.items():
        daily_value = kb_daily.get(config["daily_key"])

        if daily_value and daily_value not in ["0/0"]:
            if "∞" in daily_value:
                welcome_text += f"   {config['icon']} {config['title_plural']}: {daily_value} {config['unit']}\n"
            else:
                welcome_text += f"   {config['icon']} {config['title_plural']}: {daily_value}"

    # Предложение апгрейда
    if subscription_tier not in ["ultra", "admin"]:
        welcome_text += "\n\n💎 Расширь свои возможности — купи \nследующий уровень подписки!"

    keyboard = [
        [InlineKeyboardButton("⭐ Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton("📚 База знаний", callback_data="knowledge_base")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    return welcome_text, reply_markup


# Возврат в главное меню
async def back_to_main(update: Update, context):
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

# Установка команд бота
async def post_init(application):
    commands = [
        BotCommand("start", "🏠 Главное меню"),
    ]
    await application.bot.set_my_commands(commands)


# Обработчик завершения работы
async def shutdown(application):
    logger.info("🛑 Закрытие ресурсов...")

    # Закрываем ThreadPoolExecutor
    logger.info("Закрытие ThreadPoolExecutor...")
    executor.shutdown(wait=True)

    logger.info("✓ Ресурсы освобождены")


# ============================================================================
# ИНИЦИАЛИЗАЦИЯ БОТА
# ============================================================================

def main():
    # Запуск бота
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
    logger.info("🛑 Получен сигнал завершения (Ctrl+C)")
    sys.exit(0)


# Регистрируем обработчик сигналов
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    main()