import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
import yt_dlp
import re
import subprocess
import json
import httpx
import ffmpeg
import asyncio
from PIL import Image
import io
import base64
from datetime import datetime
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

# ТОКЕН БОТА
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# FastAPI
API_URL = os.getenv("API_URL")

# Executor для блокирующих операций
executor = ThreadPoolExecutor(max_workers=5)

# СОСТОЯНИЯ ДИАЛОГА
MAIN_MENU, PAYMENT_MENU, KB_MENU, CHAT_MENU, UPLOAD_TYPE, WAITING_TEXT, WAITING_PHOTO, WAITING_VIDEO = range(8)


# РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ
async def register_user_in_api(telegram_id: int, username: str = None):
    # Добавляем нового пользователя или получаем данные об авторизации
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_URL}/users/register",
                json={
                    "telegram_id": telegram_id,
                    "username": username
                }
            )
            return response.json()
        except Exception as e:
            print(f"Ошибка при регистрации: {e}")
            return None


# СТАРТ
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Регистрируем пользователя в API
    api_user = await register_user_in_api(user.id, user.username)

    if not api_user:
        await update.message.reply_text("⚠️ Ошибка подключения к серверу. Попробуйте позже.")
        return

    # Получаем текст и клавиатуру главного меню
    welcome_text, reply_markup = await build_main_menu(user.id, user.first_name)

    if not welcome_text:
        await update.message.reply_text("⚠️ Ошибка получения данных. Попробуйте позже.")
        return

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


# ГЛАВНОЕ МЕНЮ
async def build_main_menu(user_id: int, first_name: str):

    # Получаем статистику из API
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/users/{user_id}/stats")
            stats = response.json()
        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
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

    # Показываем все типы файлов с лимитом > 0
    video_storage = kb_storage["video_hours"]
    if video_storage not in ["0/0"]:
        if "∞" in video_storage:
            welcome_text += f"   🎥 Видео: {video_storage} ч\n"
        else:
            current, limit = video_storage.split("/")
            welcome_text += f"   🎥 Видео: {current}/{limit} ч\n"

    if kb_storage["files"] not in ["0/0"]:
        welcome_text += f"   📄 Файлы: {kb_storage['files']}\n"

    if kb_storage["photos"] not in ["0/0"]:
        welcome_text += f"   🖼 Фото: {kb_storage['photos']}\n"

    if kb_storage["texts"] not in ["0/0"]:
        welcome_text += f"   📝 Тексты: {kb_storage['texts']}\n"

    welcome_text += """
📤 Лимит загрузки сегодня:
"""

    # Показываем все дневные лимиты с лимитом > 0
    video_daily = kb_daily["video_hours"]
    if video_daily not in ["0/0"]:
        if "∞" in video_daily:
            welcome_text += f"   🎥 Видео: {video_daily} ч\n"
        else:
            current, limit = video_daily.split("/")
            welcome_text += f"   🎥 Видео: {current}/{limit} ч\n"

    if kb_daily["files"] not in ["0/0"]:
        welcome_text += f"   📄 Файлы: {kb_daily['files']}\n"

    if kb_daily["photos"] not in ["0/0"]:
        welcome_text += f"   🖼 Фото: {kb_daily['photos']}\n"

    if kb_daily["texts"] not in ["0/0"]:
        welcome_text += f"   📝 Тексты: {kb_daily['texts']}"

    # Предложение апгрейда
    if subscription_tier not in ["ultra", "admin"]:
        welcome_text += "\n\n💎 Расширь свои возможности — купи \nследующий уровень подписки!"

    keyboard = [
        [InlineKeyboardButton("⭐ Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton("📚 База знаний", callback_data="knowledge_base")],
        [InlineKeyboardButton("⚙️ Настройки режима ответов", callback_data="chat_settings")],
        [InlineKeyboardButton("👥 Пригласить друга", callback_data="referral")],
        [InlineKeyboardButton("🆘 Тех. поддержка", callback_data="support")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    return welcome_text, reply_markup


# ВОЗВРАТ В ГЛАВНОЕ МЕНЮ
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем текст и клавиатуру главного меню
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


# МЕНЮ КОМАНД
async def post_init(application):
    commands = [
        BotCommand("start", "🏠 Главное меню"),
    ]
    await application.bot.set_my_commands(commands)


# РАЗДЕЛ ПОДПИСОК

# Меню с выбором подписки
async def subscriptions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Получаем тарифы из API
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/subscriptions/tiers")
            tiers = response.json()
        except Exception as e:
            print(f"Ошибка получения тарифов: {e}")
            await query.edit_message_text(
                "⚠️ Ошибка получения данных. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
                ]])
            )
            return

    # Формируем текст меню
    text = "⭐ Подписки" + "⠀" * 20 + "\n\n"  # Невидимые пробелы Брайля для ширины

    for tier in tiers:

        text += f"<b>{tier['display_name']} — {tier['price_rubles']}₽/мес</b>\n"
        text += f"• {tier['model_name']}\n"
        text += f"• {tier['daily_messages']} сообщений в день\n\n"

        text += "📚 База знаний:\n"

        # Показываем только доступные типы
        if tier['video_hours_limit'] == 9999:
            text += f"   🎥 Безлимит видео\n"
        elif tier['video_hours_limit'] > 0:
            text += f"   🎥 {tier['video_hours_limit']}ч видео\n"

        if tier['files_limit'] == 9999:
            text += f"   📄 Безлимит файлов\n"
        elif tier['files_limit'] > 0:
            text += f"   📄 {tier['files_limit']} файлов\n"

        if tier['photos_limit'] == 9999:
            text += f"   🖼 Безлимит фото\n"
        elif tier['photos_limit'] > 0:
            text += f"   🖼 {tier['photos_limit']} фото\n"

        if tier['texts_limit'] == 9999:
            text += f"   📝 Безлимит текстов\n"
        elif tier['texts_limit'] > 0:
            text += f"   📝 {tier['texts_limit']} текстов\n"

        text += "\n📤 Загрузка в день:\n"

        if tier['daily_video_hours'] == 9999:
            text += f"   🎥 Безлимит видео\n"
        elif tier['daily_video_hours'] > 0:
            text += f"   🎥 {tier['daily_video_hours']}ч видео\n"

        if tier['daily_files'] == 9999:
            text += f"   📄 Безлимит файлов\n"
        elif tier['daily_files'] > 0:
            text += f"   📄 {tier['daily_files']} файлов\n"

        if tier['daily_photos'] == 9999:
            text += f"   🖼 Безлимит фото\n"
        elif tier['daily_photos'] > 0:
            text += f"   🖼 {tier['daily_photos']} фото\n"

        if tier['daily_texts'] == 9999:
            text += f"   📝 Безлимит текстов\n"
        elif tier['daily_texts'] > 0:
            text += f"   📝 {tier['daily_texts']} текстов\n"

        text += "\n\n"

    # Формируем кнопки
    keyboard = []
    for tier in tiers:
        button_text = f"{tier['display_name']} ({tier['price_rubles']}₽/мес)"
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"sub_{tier['tier_name']}"
        )])

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")


# РАЗДЕЛ БАЗЫ ЗНАНИЙ

# Меню базы знаний
async def knowledge_base_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = """
📚 База знаний

Управляйте своими файлами и обучайте\nнеросеть под ваши задачи!
"""

    keyboard = [
        [InlineKeyboardButton("📤 Загрузить файл", callback_data="upload_file")],
        [InlineKeyboardButton("📋 Мои файлы", callback_data="my_files")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)

# Меню загрузки файла
async def upload_file_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем статистику для проверки доступности типов
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/users/{user.id}/stats")
            stats = response.json()
        except Exception as e:
            print(f"Ошибка получения статистики в меню загрузки файла: {e}")
            await query.edit_message_text(
                "⚠️ Ошибка получения данных.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="knowledge_base")
                ]])
            )
            return

    kb_storage = stats["kb_storage"]

    text = """📤 Загрузка контента\n\nВыберите тип:"""

    keyboard = []

    # Показываем только доступные типы (лимит > 0)
    if kb_storage.get("video_hours") not in ["0/0"]:
        keyboard.append([InlineKeyboardButton("🎥 Видео", callback_data="upload_video")])

    if kb_storage.get("files") not in ["0/0"]:
        keyboard.append([InlineKeyboardButton("📄 Файл", callback_data="upload_file_doc")])

    if kb_storage.get("photos") not in ["0/0"]:
        keyboard.append([InlineKeyboardButton("🖼 Фото", callback_data="upload_photo")])

    if kb_storage.get("texts") not in ["0/0"]:
        keyboard.append([InlineKeyboardButton("📝 Текст", callback_data="upload_text")])

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="knowledge_base")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)

# Загрузка текста в базу знаний
async def upload_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем статистику для проверки лимитов
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/users/{user.id}/stats")
            stats = response.json()
        except Exception as e:
            print(f"Ошибка получения статистики по лимитам на текст: {e}")
            await query.edit_message_text(
                "⚠️ Ошибка подключения к серверу.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")
                ]])
            )
            return ConversationHandler.END

    # Проверяем лимиты
    kb_storage = stats["kb_storage"]
    kb_daily = stats["kb_daily"]
    subscription_tier = stats["subscription_tier"]

    # Парсим текущие значения
    storage_texts = kb_storage.get("texts", "0/0")
    daily_texts = kb_daily.get("texts", "0/0")

    # Проверяем хранилище
    if "∞" not in storage_texts:
        storage_current, storage_limit = map(int, storage_texts.split("/"))
        if storage_current >= storage_limit:
            # Лимит хранилища переполнен
            text = "⚠️ Хранилище текстов заполнено!\n\n"
            text += f"Использовано: {storage_current}/{storage_limit}\n\n"

            keyboard = []

            if subscription_tier not in ["ultra", "admin"]:
                text += "💎 Увеличьте лимиты — купите подписку уровнем выше!"
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])

            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")])

            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

    # Проверяем дневной лимит
    if "∞" not in storage_texts:
        daily_current, daily_limit = map(int, daily_texts.split("/"))
        if daily_current >= daily_limit:
            # Дневной лимит переполнен
            text = "⚠️ Дневной лимит загрузки текстов исчерпан!\n\n"
            text += f"Использовано сегодня: {daily_current}/{daily_limit}\n\n"

            keyboard = []

            if subscription_tier not in ["ultra", "admin"]:
                text += "💎 Увеличьте лимиты — купите подписку уровнем выше!"
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
            else:
                text += "Дневной лимит обновится завтра."

            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")])

            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

    # Лимиты не переполнены — предлагаем загрузить текст
    text = """
📝 Загрузка текста

Отправьте ваш текст в следующем сообщении:
"""

    keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="exit_upload")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)

    return WAITING_TEXT  # Переходим в состояние ожидания текста

# Обработка текста от пользователя
async def handle_text_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Проверяем, что это только текст
    if update.message.photo or update.message.document or update.message.video:
        keyboard = [[InlineKeyboardButton("◀️ Назад к выбору типа", callback_data="exit_upload")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

    text_content = update.message.text
    user = update.effective_user

    await update.message.reply_text("⏳ Сохраняю текст в базу знаний...")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_URL}/kb/upload/text",
                json={
                    "telegram_id": user.id,
                    "text": text_content
                },
                timeout=30.0
            )

            if response.status_code == 200:
                keyboard = [
                    [InlineKeyboardButton("📤 Загрузить ещё текст", callback_data="upload_text")],
                    [InlineKeyboardButton("📋 Мои тексты", callback_data="my_texts")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    "✅ Текст успешно добавлен в базу знаний!\n\n"
                    "Теперь вы можете задавать вопросы по этому материалу\nили обучать нейросеть.",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text("⚠️ Ошибка при сохранении. Попробуйте позже.")

        except Exception as e:
            print(f"Ошибка загрузки текста: {e}")
            await update.message.reply_text("⚠️ Ошибка подключения к серверу.")

    return ConversationHandler.END  # Выходим из состояния ожидания

# Обработчик вложений при загрузке текста
async def handle_wrong_media_in_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("◀️ Назад к выбору типа", callback_data="exit_upload")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚠️ Пожалуйста, отправьте только текст без вложений.\n\n"
        "Для загрузки файлов, фото или видео используйте соответствующий раздел меню.",
        reply_markup=reply_markup
    )

    return WAITING_TEXT  # Остаёмся в состоянии ожидания

# Меню выбора типа файла для администрирования
async def my_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем статистику для отображения счётчиков
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/users/{user.id}/stats")
            stats = response.json()
        except Exception as e:
            print(f"Ошибка получения статистики файлов в БЗ: {e}")
            await query.edit_message_text(
                "⚠️ Ошибка получения данных.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="knowledge_base")
                ]])
            )
            return

    kb_storage = stats["kb_storage"]

    # Проверяем, есть ли хоть один файл
    has_files = False

    if kb_storage.get("video_hours") not in ["0/0", "0/∞"]:
        video_count = float(kb_storage["video_hours"].split("/")[0])
        if video_count > 0:
            has_files = True

    if kb_storage.get("files") not in ["0/0", "0/∞"]:
        files_count = int(kb_storage["files"].split("/")[0])
        if files_count > 0:
            has_files = True

    if kb_storage.get("photos") not in ["0/0", "0/∞"]:
        photos_count = int(kb_storage["photos"].split("/")[0])
        if photos_count > 0:
            has_files = True

    if kb_storage.get("texts") not in ["0/0", "0/∞"]:
        texts_count = int(kb_storage["texts"].split("/")[0])
        if texts_count > 0:
            has_files = True

    # Если база знаний пустая
    if not has_files:
        await query.edit_message_text(
            "📋 Ваша база знаний пуста!\n\n"
            "Загрузите файлы, чтобы начать работу\nс базой знаний.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Загрузить файл", callback_data="upload_file")],
                [InlineKeyboardButton("◀️ Назад", callback_data="knowledge_base")]
            ])
        )
        return

    # Формируем текст со статистикой
    text = "📋 Мои файлы\n\n"
    text += "📊 Ваше хранилище:\n"

    # Показываем статистику только для доступных типов
    if kb_storage.get("video_hours") not in ["0/0"]:
        text += f"   🎥 Видео: {kb_storage['video_hours']} ч\n"

    if kb_storage.get("files") not in ["0/0"]:
        text += f"   📄 Файлы: {kb_storage['files']}\n"

    if kb_storage.get("photos") not in ["0/0"]:
        text += f"   🖼 Фото: {kb_storage['photos']}\n"

    if kb_storage.get("texts") not in ["0/0"]:
        text += f"   📝 Тексты: {kb_storage['texts']}\n"

    text += "\nВыберите тип файлов для просмотра:"

    keyboard = []

    # Показываем кнопки только для доступных типов
    if kb_storage.get("video_hours") not in ["0/0"]:
        keyboard.append([InlineKeyboardButton("🎥 Видео", callback_data="my_videos")])

    if kb_storage.get("files") not in ["0/0"]:
        keyboard.append([InlineKeyboardButton("📄 Файлы", callback_data="my_files_docs")])

    if kb_storage.get("photos") not in ["0/0"]:
        keyboard.append([InlineKeyboardButton("🖼 Фото", callback_data="my_photos")])

    if kb_storage.get("texts") not in ["0/0"]:
        keyboard.append([InlineKeyboardButton("📝 Тексты", callback_data="my_texts")])

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="knowledge_base")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)

# Список текстов в базе знаний
async def my_texts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем все файлы
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/kb/documents/{user.id}")
            data = response.json()
            all_documents = data.get("documents", [])
        except Exception as e:
            print(f"Ошибка получения файлов: {e}")
            await query.edit_message_text(
                "⚠️ Ошибка получения данных.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="my_files")
                ]])
            )
            return

    # Фильтруем только тексты и сортируем по возрастанию даты загрузки
    texts = [doc for doc in all_documents if doc["file_type"] == "text"]
    texts.sort(key=lambda x: x["upload_date"])

    # Если текстов нет
    if not texts:
        await query.edit_message_text(
            "📝 У вас пока нет текстов!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Загрузить текст", callback_data="upload_text")],
                [InlineKeyboardButton("◀️ Назад", callback_data="my_files")]
            ])
        )
        return

    # Разбиваем на страницы
    items_per_page = 15
    total_pages = (len(texts) + items_per_page - 1) // items_per_page

    # Формируем страницы
    for page in range(total_pages):
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(texts))
        page_texts = texts[start_idx:end_idx]

        is_first_page = (page == 0)
        is_last_page = (page == total_pages - 1)

        # Формируем текст страницы
        if total_pages > 1:
            files_text = f"📝 Мои тексты ({len(texts)}) — страница {page + 1}/{total_pages}\n\n"
        else:
            files_text = f"📝 Мои тексты:\n\n"

        keyboard = []

        for doc in page_texts:
            # Превью (первые 100 символов)
            preview = doc["extracted_text"][:100]
            if len(doc.get("extracted_text", "")) > 100:
                preview += "..."

            datetime_str = doc['upload_date'][:16].replace('T', ' ')
            files_text += f"📝 Текст {doc['id']}\n"
            files_text += f"<blockquote>{preview}</blockquote>\n"
            files_text += f"📅 {datetime_str}\n\n"

            keyboard.append([
                InlineKeyboardButton(f"👁 Полный текст {doc['id']}", callback_data=f"view_doc_{doc['id']}"),
                InlineKeyboardButton(f"🗑 Удалить текст {doc['id']}", callback_data=f"delete_doc_{doc['id']}")
            ])

        # Кнопки навигации только на последней странице
        if is_last_page:
            keyboard.append([InlineKeyboardButton("📤 Загрузить текст", callback_data="upload_text")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="my_files")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Первую страницу редактируем, остальные отправляем новыми
        if is_first_page:
            await query.edit_message_text(files_text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await context.bot.send_message(user.id, files_text, reply_markup=reply_markup, parse_mode="HTML")

# Список видео в базе знаний
async def my_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    # Получаем все файлы
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/kb/documents/{user.id}")
            data = response.json()
            all_documents = data.get("documents", [])

        except Exception as e:
            print(f"Ошибка получения файлов: {e}")
            await query.edit_message_text(
                "⚠️ Ошибка получения данных.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="my_files")
                ]])
            )
            return

    # Фильтруем только видео со статусом completed
    videos = [doc for doc in all_documents if doc["file_type"] == "video" and doc.get("status") == "completed"]
    videos.sort(key=lambda x: x["upload_date"])

    # Если видео нет
    if not videos:
        await query.edit_message_text(
            "🎥 У вас пока нет обработанных видео!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Загрузить видео", callback_data="upload_video")],
                [InlineKeyboardButton("◀️ Назад", callback_data="my_files")]
            ])
        )
        return

    # Разбиваем на страницы (15 видео на страницу)
    items_per_page = 15
    total_pages = (len(videos) + items_per_page - 1) // items_per_page

    # Формируем страницы
    for page in range(total_pages):
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(videos))
        page_videos = videos[start_idx:end_idx]

        is_first_page = (page == 0)
        is_last_page = (page == total_pages - 1)

        # Формируем текст страницы
        if total_pages > 1:
            files_text = f"🎥 Мои видео ({len(videos)}) — страница {page + 1}/{total_pages}\n\n"
        else:
            files_text = f"🎥 Мои видео:\n\n"

        keyboard = []

        for doc in page_videos:
            # Превью транскрипции (первые 100 символов)
            preview = doc.get("extracted_text", "")[:100]
            if len(doc.get("extracted_text", "")) > 100:
                preview += "..."

            datetime_str = doc['upload_date'][:16].replace('T', ' ')

            files_text += f"🎥 Видео {doc['id']}: <a href='{doc['file_url']}'>{doc['filename']}</a>\n"
            files_text += f"<blockquote>{preview}</blockquote>\n"
            files_text += f"📅 {datetime_str}\n\n"

            keyboard.append([
                InlineKeyboardButton(f"👁 Полный текст {doc['id']}", callback_data=f"view_doc_{doc['id']}"),
                InlineKeyboardButton(f"🗑 Удалить {doc['id']}", callback_data=f"delete_doc_{doc['id']}")
            ])

        # Кнопки навигации только на последней странице
        if is_last_page:
            keyboard.append([InlineKeyboardButton("📤 Загрузить видео", callback_data="upload_video")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="my_files")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Первую страницу редактируем, остальные отправляем новыми
        if is_first_page:
            await query.edit_message_text(files_text, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True)
        else:
            await context.bot.send_message(user.id, files_text, reply_markup=reply_markup, parse_mode="HTML", disable_web_page_preview=True)

# Загрузка видео в базу знаний
async def upload_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем статистику для проверки лимитов
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/users/{user.id}/stats")
            stats = response.json()
        except Exception as e:
            print(f"❌ Ошибка получения статистики по лимитам на видео: {e}")
            await query.edit_message_text(
                "⚠️ Ошибка подключения к серверу.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")
                ]])
            )
            return ConversationHandler.END

    # Проверяем лимиты
    kb_storage = stats["kb_storage"]
    kb_daily = stats["kb_daily"]
    subscription_tier = stats["subscription_tier"]

    # Парсим текущие значения
    storage_videos = kb_storage.get("video_hours", "0/0")
    daily_videos = kb_daily.get("video_hours", "0/0")

    # Проверяем хранилище (пропускаем безлимит)
    if "∞" not in storage_videos:
        storage_current, storage_limit = map(float, storage_videos.split("/"))
        if storage_current >= storage_limit:
            # Лимит хранилища переполнен
            text = "⚠️ Хранилище видео заполнено!\n\n"
            text += f"Использовано: {storage_current}ч/{storage_limit}ч\n\n"

            keyboard = []

            if subscription_tier not in ["ultra", "admin"]:
                text += "💎 Увеличьте лимиты — купите подписку уровнем выше!"
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
            else:
                text += "Вы на максимальном тарифе. Удалите старые видео, чтобы загрузить новые."

            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")])

            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

    # Проверяем дневной лимит (пропускаем безлимит)
    if "∞" not in daily_videos:
        daily_current, daily_limit = map(float, daily_videos.split("/"))
        if daily_current >= daily_limit:
            # Дневной лимит переполнен
            text = "⚠️ Дневной лимит загрузки видео исчерпан!\n\n"
            text += f"Использовано сегодня: {daily_current}ч/{daily_limit}ч\n\n"

            keyboard = []

            if subscription_tier not in ["ultra", "admin"]:
                text += "💎 Увеличьте лимиты — купите подписку уровнем выше!"
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
            else:
                text += "Дневной лимит обновится завтра."

            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")])

            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

    text = """
🎥 Загрузка видео

Мы принимаем ссылки на видео из следующих источников:

📌 <b>Прямые ссылки</b>
https://example.com/video.mp4

📌 <b>YouTube</b>
https://youtube.com/watch?v=XXXXXX

📌 <b>Rutube</b>
https://rutube.ru/video/XXXXXX

📌 <b>Яндекс.Диск</b>
https://disk.yandex.ru/i/XXXXXX

Отправьте ссылки на видео в следующем сообщении в таком формате:

<em>ссылка</em>
<em>ссылка</em>

Не более 10 ссылок за один раз!
"""

    keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="exit_upload")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")

    return WAITING_VIDEO

# Получение длительности видео для прямой ссылки
async def get_direct_video_duration(url: str) -> tuple:
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            url
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return None, "Не удалось получить информацию о видео"

        data = json.loads(result.stdout)
        duration_seconds = float(data.get('format', {}).get('duration', 0))

        if duration_seconds == 0:
            return None, "Не удалось определить длительность видео"

        duration_hours = duration_seconds / 3600
        return duration_hours, None

    except subprocess.TimeoutExpired:
        return None, "Превышено время ожидания ответа от сервера"
    except Exception as e:
        print(f"❌ Ошибка ffprobe для {url}: {e}")
        return None, "Не удалось получить информацию о видео"

# Получение длительности видео
# Синхронная функция для yt_dlp
def _get_video_info_sync(url: str, timeout: int = 15) -> tuple:
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'socket_timeout': timeout,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration_seconds = info.get('duration', 0)
            title = info.get('title') or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            if duration_seconds == 0 or duration_seconds is None:
                return None, None, "Не удалось определить длительность видео"

            duration_hours = duration_seconds / 3600
            return duration_hours, title, None

    except Exception as e:
        return None, None, str(e)

# Получение длительности видео с таймаутом
async def get_video_duration(url: str) -> tuple:
    try:
        # Если это прямая ссылка — используем ffprobe
        if re.search(r'\.(mp4|mkv|avi|mov|webm)(\?|$)', url):
            try:
                probe = ffmpeg.probe(url, timeout=15)
                duration_seconds = float(probe['format']['duration'])
                duration_hours = duration_seconds / 3600

                filename = url.split('/')[-1].split('?')[0]
                title = filename if filename else f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                return duration_hours, title, None

            except Exception as e:
                return None, None, "Не удалось получить информацию о видео"

        # Для YouTube, Rutube — запускаем в отдельном потоке с таймаутом
        loop = asyncio.get_event_loop()

        try:
            duration_hours, title, error = await asyncio.wait_for(
                loop.run_in_executor(executor, _get_video_info_sync, url, 15),
                timeout=15
            )

            if error:
                error_str = error.lower()

                if 'private' in error_str or 'авторизац' in error_str:
                    return None, None, "Видео приватное или требует авторизации"
                elif 'not available' in error_str or 'removed' in error_str or 'deleted' in error_str:
                    return None, None, "Видео удалено или недоступно"
                elif '404' in error_str:
                    return None, None, "Видео не найдено (404)"
                else:
                    return None, None, f"Непредвиденная ошибка! Возможно, видео не существует или имеет ограниченный доступ."

            return duration_hours, title, None

        except asyncio.TimeoutError:
            return None, None, "Превышено время ожидания. Возможно, видео недоступно или требует авторизации"

    except Exception as e:
        print(f"❌ Ошибка для {url}: {e}")
        return None, None, "Не удалось получить информацию о видео"

# Обработка загрузки видео
async def handle_video_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Проверяем что это только текст (без медиа)
    if update.message.photo or update.message.document or update.message.video:
        keyboard = [[InlineKeyboardButton("◀️ Назад к выбору типа", callback_data="exit_upload")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "⚠️ Пожалуйста, отправьте только ссылки на видео (без файлов).\n\n"
            "Формат: каждая ссылка с новой строки.",
            reply_markup=reply_markup
        )
        return WAITING_VIDEO

    text = update.message.text.strip()
    user = update.effective_user

    # Разбиваем на строки и убираем пустые
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # Регулярка для проверки URL
    url_pattern = re.compile(r'^https?://')

    # Проверяем что все строки — это ссылки
    urls = []
    for line in lines:
        if not url_pattern.match(line):
            keyboard = [[InlineKeyboardButton("◀️ Назад к выбору типа", callback_data="exit_upload")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "⚠️ Отправьте только полные ссылки на видео!\n\n"
                f"Некорректная строка: {line[:50]}...\n\n",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            return WAITING_VIDEO
        urls.append(line)

    # Проверяем лимит кол-ва ссылок в одном сообщении
    MAX_URLS = 10
    if len(urls) > MAX_URLS:
        keyboard = [[InlineKeyboardButton("◀️ Назад к выбору типа", callback_data="exit_upload")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"⚠️ Максимум {MAX_URLS} ссылок за раз!\n\n"
            f"Отправлено: {len(urls)}",
            reply_markup=reply_markup
        )
        return WAITING_VIDEO

    # Чистим дублирующиеся ссылки
    unique_urls = list(dict.fromkeys(urls))
    duplicates_count = len(urls) - len(unique_urls)

    # Проверяем поддерживаемые источники видео
    supported_patterns = [
        (r'\.(mp4|mkv|avi|mov|webm)(\?|$)', 'Прямая ссылка'),
        (r'(youtube\.com/watch\?v=|youtu\.be/)', 'YouTube'),
        (r'rutube\.ru/video/', 'Rutube'),
        (r'disk\.yandex\.(ru|com)/', 'Яндекс.Диск'),
    ]

    for url in unique_urls:
        is_supported = False
        for pattern, source in supported_patterns:
            if re.search(pattern, url):
                is_supported = True
                break

        if not is_supported:
            keyboard = [[InlineKeyboardButton("◀️ Назад к выбору типа", callback_data="exit_upload")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"⚠️ Неподдерживаемый источник!\n\n"
                f"Ссылка: {url[:50]}...\n\n"
                "Поддерживаемые источники:\n"
                "• Прямые ссылки (.mp4, .mkv, .avi)\n"
                "• YouTube\n"
                "• Rutube\n"
                "• Яндекс.Диск",
                reply_markup=reply_markup
            )
            return WAITING_VIDEO

    # Получение длительности видео
    await update.message.reply_text("⏳ Проверяю длительность видео...")

    video_info = []
    total_duration = 0
    failed_videos = []

    for url in unique_urls:
        duration, title, error = await get_video_duration(url)

        if error:
            failed_videos.append({
                'url': url,
                'title': title,
                'error': error
            })
        else:
            video_info.append({
                'url': url,
                'title': title,
                'duration': duration
            })
            total_duration += duration

    # Если не удалось получить инфо о каких-то видео
    if failed_videos:
        keyboard = [[InlineKeyboardButton("◀️ Назад к выбору типа", callback_data="exit_upload")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        error_text = "⚠️ Не удалось обработать следующие видео:\n\n"

        for item in failed_videos:
            error_text += f"🔗 {item['url']}\n"
            error_text += f"❌ {item['error']}\n\n"

        await update.message.reply_text(error_text, reply_markup=reply_markup, disable_web_page_preview=True)
        return WAITING_VIDEO

    # Получаем текущие лимиты пользователя
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/users/{user.id}/stats")
            stats = response.json()
        except Exception as e:
            print(f"Ошибка получения лимитов: {e}")
            await update.message.reply_text("⚠️ Ошибка подключения к серверу.")
            return ConversationHandler.END

    kb_storage = stats["kb_storage"]
    kb_daily = stats["kb_daily"]
    subscription_tier = stats["subscription_tier"]

    storage_videos = kb_storage.get("video_hours", "0/0")
    daily_videos = kb_daily.get("video_hours", "0/0")

    # Проверяем хранилище
    if "∞" not in storage_videos:
        storage_current, storage_limit = map(float, storage_videos.split("/"))
        available_storage = storage_limit - storage_current

        if total_duration > available_storage:
            keyboard = []

            text = f"⚠️ Недостаточно места в хранилище!\n\n"
            text += f"Требуется: {total_duration:.2f}ч\n"
            text += f"Доступно: {available_storage:.2f}ч\n"
            text += f"Хранилище: {storage_current:.2f}ч/{storage_limit:.2f}ч\n\n"

            if subscription_tier not in ["ultra", "admin"]:
                text += "💎 Увеличьте лимиты — купите подписку уровнем выше!"
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
            else:
                text += "Удалите старые видео, чтобы освободить место."

            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")])

            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

    # Проверяем дневной лимит
    if "∞" not in daily_videos:
        daily_current, daily_limit = map(float, daily_videos.split("/"))
        available_daily = daily_limit - daily_current

        if total_duration > available_daily:
            keyboard = []

            text = f"⚠️ Превышен дневной лимит загрузки!\n\n"
            text += f"Требуется: {total_duration:.2f}ч\n"
            text += f"Доступно сегодня: {available_daily:.2f}ч\n"
            text += f"Использовано: {daily_current:.2f}ч/{daily_limit:.2f}ч\n\n"

            if subscription_tier not in ["ultra", "admin"]:
                text += "💎 Увеличьте лимиты — купите подписку уровнем выше!"
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
            else:
                text += "Дневной лимит обновится завтра."

            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")])

            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

        # Отправляем на обработку
        await update.message.reply_text("⏳ Отправляю видео на обработку...")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{API_URL}/kb/upload/video",
                    json={
                        "telegram_id": user.id,
                        "videos": video_info
                    },
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()

                    success_text = f"✅ Видео добавлены в обработку!\n\n"
                    success_text += f"📊 Количество: {len(video_info)}\n"
                    success_text += f"⏱ Общая длительность: {total_duration:.2f}ч\n\n"
                    success_text += f"Мы пришлём уведомление, когда обработка завершится!"

                    keyboard = [
                    [InlineKeyboardButton("📤 Добавить ещё видео", callback_data="upload_video")],
                        [InlineKeyboardButton("🎥 Мои видео", callback_data="my_videos")],
                        [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await update.message.reply_text(success_text, reply_markup=reply_markup)
                else:
                    await update.message.reply_text("⚠️ Ошибка при отправке на обработку.")

            except Exception as e:
                print(f"Ошибка отправки видео: {e}")
                await update.message.reply_text("⚠️ Ошибка подключения к серверу.")

        return ConversationHandler.END

# Обработка неверно отправленных видео
async def handle_wrong_media_in_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("◀️ Назад к выбору типа", callback_data="exit_upload")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚠️ Пожалуйста, отправьте только полные ссылки на видео.\n\n",
        reply_markup=reply_markup
    )

    return WAITING_VIDEO  # Остаёмся в состоянии ожидания

# Конвертация фото в JPEG
def convert_to_jpeg_for_ocr(photo_bytes: bytes) -> str:

    try:
        # Открываем изображение
        image = Image.open(io.BytesIO(photo_bytes))

        # Конвертируем в RGB (если PNG с прозрачностью)
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        # Сохраняем в JPEG
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=100, optimize=True)
        jpeg_bytes = output.getvalue()

        # Конвертируем в base64
        jpeg_base64 = base64.b64encode(jpeg_bytes).decode('utf-8')

        return jpeg_base64

    except Exception as e:
        print(f"❌ Ошибка конвертации в JPEG: {e}")
        raise

# Глобальный обработчик фото
async def global_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Проверяем, ждём ли мы фото от этого юзера
    if context.user_data.get('waiting_for_photos'):

        if 'photo_buffer' not in context.user_data:
            context.user_data['photo_buffer'] = []

        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        jpeg_base64 = convert_to_jpeg_for_ocr(bytes(photo_bytes))
        filename = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"

        context.user_data['photo_buffer'].append({
            "base64": jpeg_base64,
            "filename": filename
        })

        count = len(context.user_data['photo_buffer'])

        if count == 1:
            status_msg = await update.message.reply_text(f"⏳ Получено фото: {count}")
            context.user_data['status_msg_id'] = status_msg.message_id
        else:
            try:
                await context.bot.edit_message_text(
                    chat_id=user.id,
                    message_id=context.user_data['status_msg_id'],
                    text=f"⏳ Получено фото: {count}"
                )
            except:
                pass

        # Отменяем старый таймер
        if 'timer' in context.user_data and context.user_data['timer']:
            context.user_data['timer'].cancel()

        # Новый таймер на 3 секунды
        async def finish_upload():
            await asyncio.sleep(3)

            photos = context.user_data['photo_buffer']
            total = len(photos)

            try:
                await context.bot.edit_message_text(
                    chat_id=user.id,
                    message_id=context.user_data['status_msg_id'],
                    text=f"⏳ Отправляю {total} фото на обработку..."
                )
            except:
                pass

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_URL}/kb/upload/photos",
                    json={"telegram_id": user.id, "photos": photos},
                    timeout=60.0
                )

            if response.status_code == 200:
                keyboard = [
                    [InlineKeyboardButton("📤 Загрузить ещё фото", callback_data="upload_photo")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
                ]
                try:
                    await context.bot.edit_message_text(
                        chat_id=user.id,
                        message_id=context.user_data['status_msg_id'],
                        text=f"✅ {total} фото отправлено на обработку!\n\nУведомление придет после распознавания",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except:
                    pass
            else:
                await context.bot.send_message(user.id, "⚠️ Ошибка загрузки")

            # ВАЖНО: Выключаем режим ожидания фото
            context.user_data['waiting_for_photos'] = False
            context.user_data['photo_buffer'] = []

        context.user_data['timer'] = asyncio.create_task(finish_upload())

# Загрузка фото в базу знаний
async def upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем статистику для проверки лимитов
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/users/{user.id}/stats")
            stats = response.json()
        except Exception as e:
            print(f"❌ Ошибка получения статистики по лимитам на фото: {e}")

            error_text = "⚠️ Ошибка подключения к серверу."
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")]]

            if query.message.photo:
                await query.message.delete()
                await context.bot.send_message(user.id, error_text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await query.edit_message_text(error_text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

    # Проверяем лимиты
    kb_storage = stats["kb_storage"]
    kb_daily = stats["kb_daily"]
    subscription_tier = stats["subscription_tier"]

    storage_photos = kb_storage.get("photos", "0/0")
    daily_photos = kb_daily.get("photos", "0/0")

    # Проверяем хранилище
    if "∞" not in storage_photos:
        storage_current, storage_limit = map(int, storage_photos.split("/"))
        if storage_current >= storage_limit:
            text = "⚠️ Хранилище фото заполнено!\n\n"
            text += f"Использовано: {storage_current}/{storage_limit}\n\n"

            keyboard = []

            if subscription_tier not in ["ultra", "admin"]:
                text += "💎 Увеличьте лимиты — купите подписку уровнем выше!"
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
            else:
                text += "Вы на максимальном тарифе. Удалите старые фото, чтобы загрузить новые."

            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")])

            if query.message.photo:
                await query.message.delete()
                await context.bot.send_message(user.id, text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

    # Проверяем дневной лимит
    if "∞" not in daily_photos:
        daily_current, daily_limit = map(int, daily_photos.split("/"))
        if daily_current >= daily_limit:
            text = "⚠️ Дневной лимит загрузки фото исчерпан!\n\n"
            text += f"Использовано сегодня: {daily_current}/{daily_limit}\n\n"

            keyboard = []

            if subscription_tier not in ["ultra", "admin"]:
                text += "💎 Увеличьте лимиты — купите подписку уровнем выше!"
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
            else:
                text += "Дневной лимит обновится завтра."

            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")])

            if query.message.photo:
                await query.message.delete()
                await context.bot.send_message(user.id, text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

    # Лимиты не переполнены — предлагаем загрузить фото
    text = """🖼 Загрузка фото\n\nОтправьте <b>в одном сообщении</b> до 10 фото с текстом, который нужно распознать.\n\nПоддерживаемые форматы: JPG, PNG"""

    keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="exit_upload")]]

    if query.message.photo:
        await query.message.delete()
        await context.bot.send_message(user.id, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    # Включаем режим ожидания фото
    context.user_data['waiting_for_photos'] = True

    return ConversationHandler.END

# Просмотр загруженных фото
async def my_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/kb/documents/{user.id}")

        if response.status_code == 200:
            data = response.json()
            documents = data.get("documents", [])

            # Фильтруем только фото со статусом completed
            photos = [doc for doc in documents if doc["file_type"] == "photo" and doc["status"] == "completed"]

            if not photos:
                text = "🖼 У вас пока нет фото в базе знаний."
                keyboard = [
                    [InlineKeyboardButton("📤 Загрузить фото", callback_data="upload_photo")],
                    [InlineKeyboardButton("◀️ Назад", callback_data="my_files")]
                ]

                if query.message.photo:
                    await query.message.delete()
                    await context.bot.send_message(user.id, text, reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
                return

            # Сортируем по дате (новые сверху)
            photos.sort(key=lambda x: x["upload_date"], reverse=True)

            # Разбиваем на страницы
            # Каждый элемент: ~200 символов текста + 2 строки кнопок
            # Лимит Telegram: 4096 символов текста + 100 кнопок
            # Безопасно: ~15 фото на страницу
            items_per_page = 15
            total_pages = (len(photos) + items_per_page - 1) // items_per_page

            # Формируем страницы
            for page in range(total_pages):
                start_idx = page * items_per_page
                end_idx = min(start_idx + items_per_page, len(photos))
                page_photos = photos[start_idx:end_idx]

                is_first_page = (page == 0)
                is_last_page = (page == total_pages - 1)

                # Формируем текст страницы
                if total_pages > 1:
                    files_text = f"🖼 Мои фото ({len(photos)}) — страница {page + 1}/{total_pages}\n\n"
                else:
                    files_text = f"🖼 Мои фото ({len(photos)}):\n\n"

                keyboard = []

                for doc in page_photos:
                    # Превью текста (первые 100 символов)
                    preview = doc.get("extracted_text", "[Текст не распознан]")[:100]
                    if len(doc.get("extracted_text", "")) > 100:
                        preview += "..."

                    datetime_str = doc['upload_date'][:16].replace('T', ' ')
                    files_text += f"🖼 Фото {doc['id']}\n"
                    files_text += f"<blockquote>{preview}</blockquote>\n"
                    files_text += f"📅 {datetime_str}\n\n"

                    keyboard.append([
                        InlineKeyboardButton(f"👁 Полный текст {doc['id']}", callback_data=f"view_doc_{doc['id']}"),
                        InlineKeyboardButton(f"🖼 Показать фото {doc['id']}", callback_data=f"show_photo_{doc['id']}")
                    ])
                    keyboard.append([
                        InlineKeyboardButton(f"🗑 Удалить {doc['id']}", callback_data=f"delete_doc_{doc['id']}")
                    ])

                # Кнопки навигации только на последней странице
                if is_last_page:
                    keyboard.append([InlineKeyboardButton("📤 Загрузить фото", callback_data="upload_photo")])
                    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="my_files")])

                reply_markup = InlineKeyboardMarkup(keyboard)

                # Первую страницу редактируем, остальные отправляем новыми
                if is_first_page:
                    if query.message.photo:
                        await query.message.delete()
                        await context.bot.send_message(user.id, files_text, reply_markup=reply_markup,
                                                       parse_mode="HTML")
                    else:
                        await query.edit_message_text(files_text, reply_markup=reply_markup, parse_mode="HTML")
                else:
                    await context.bot.send_message(user.id, files_text, reply_markup=reply_markup, parse_mode="HTML")

        else:
            if query.message.photo:
                await query.message.delete()
                await context.bot.send_message(user.id, "⚠️ Ошибка получения списка фото.")
            else:
                await query.edit_message_text("⚠️ Ошибка получения списка фото.")

    except Exception as e:
        print(f"Ошибка получения фото: {e}")
        try:
            if query.message.photo:
                await query.message.delete()
                await context.bot.send_message(user.id, "⚠️ Произошла ошибка.")
            else:
                await query.edit_message_text("⚠️ Произошла ошибка.")
        except:
            pass

# Показать оригинальное фото
async def show_photo_original(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    document_id = int(query.data.split("_")[-1])

    try:
        async with httpx.AsyncClient() as client:
            # Получаем presigned URL
            photo_response = await client.get(f"{API_URL}/kb/photo/{document_id}/presigned")

            if photo_response.status_code != 200:
                await query.answer("⚠️ Не удалось загрузить фото.", show_alert=True)
                return

            photo_data = photo_response.json()
            photo_url = photo_data["presigned_url"]

            keyboard = [
                [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_doc_{document_id}")]
            ]

            # Отправляем фото
            await query.message.reply_photo(
                photo=photo_url,
                caption="🖼 Оригинальное фото",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    except Exception as e:
        print(f"Ошибка показа фото: {e}")
        await query.answer("⚠️ Произошла ошибка.", show_alert=True)

# Просмотр полного текста файла
async def view_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    doc_id = int(query.data.split("_")[2])
    user = query.from_user

    # Получаем документы
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/kb/documents/{user.id}")
            data = response.json()
            documents = data.get("documents", [])

            # Находим нужный документ
            document = next((d for d in documents if d["id"] == doc_id), None)

            if not document:
                await query.edit_message_text("⚠️ Документ не найден.")
                return

            # Определяем тип файла для кнопки "Назад"
            file_type = document['file_type']
            back_callbacks = {
                'text': 'my_texts',
                'video': 'my_videos',
                'file': 'my_files_docs',
                'photo': 'my_photos'
            }
            back_callback = back_callbacks.get(file_type, 'my_files')

            # Показываем полный текст
            title = "📝 Полный текст"
            full_text = f"{title} {doc_id}\n\n{document['extracted_text']}"

            # Разбиваем на части по 4000 символов
            max_length = 4000
            text_parts = []

            for i in range(0, len(full_text), max_length):
                text_parts.append(full_text[i:i + max_length])

            # Инициализируем хранилище для message_id
            if 'doc_messages' not in context.user_data:
                context.user_data['doc_messages'] = {}

            # Список для хранения ID отправленных сообщений
            message_ids = []

            # Отправляем части
            total_parts = len(text_parts)

            for i, part in enumerate(text_parts):
                is_last = (i == total_parts - 1)

                if is_last:
                    # Последнее сообщение с кнопками
                    keyboard = [
                        [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_doc_{doc_id}")],
                        [InlineKeyboardButton("◀️ Назад к списку", callback_data=back_callback)]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    if i == 0:
                        # Единственное сообщение - редактируем
                        edited_msg = await query.edit_message_text(part, reply_markup=reply_markup)
                        message_ids.append(edited_msg.message_id)
                    else:
                        # Последняя часть - отправляем новое
                        sent_msg = await query.message.reply_text(part, reply_markup=reply_markup)
                        message_ids.append(sent_msg.message_id)
                else:
                    # Промежуточные сообщения без кнопок
                    if i == 0:
                        # Первое сообщение - редактируем
                        edited_msg = await query.edit_message_text(part)
                        message_ids.append(edited_msg.message_id)
                    else:
                        # Последующие части - новые сообщения
                        sent_msg = await query.message.reply_text(part)
                        message_ids.append(sent_msg.message_id)

            # Сохраняем ID всех сообщений для этого документа
            context.user_data['doc_messages'][doc_id] = message_ids

        except Exception as e:
            print(f"Ошибка просмотра документа: {e}")
            await query.edit_message_text("⚠️ Ошибка загрузки документа.")

# Удаление файла из базы знаний
async def delete_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    doc_id = int(query.data.split("_")[2])
    user = query.from_user

    # Сначала получаем информацию о документе для определения типа
    async with httpx.AsyncClient() as client:
        try:
            # Получаем документы пользователя
            response = await client.get(f"{API_URL}/kb/documents/{user.id}")
            data = response.json()
            documents = data.get("documents", [])

            # Находим документ для определения типа
            document = next((d for d in documents if d["id"] == doc_id), None)

            if not document:
                if query.message.photo:
                    await query.message.delete()
                    await context.bot.send_message(user.id, "⚠️ Документ не найден.")
                else:
                    await query.edit_message_text("⚠️ Документ не найден.")
                return

            file_type = document['file_type']

            # Удаляем через API
            delete_response = await client.delete(f"{API_URL}/kb/documents/{doc_id}")

            if delete_response.status_code == 200:
                # Удаляем предыдущие сообщения (если они были сохранены)
                if 'doc_messages' in context.user_data and doc_id in context.user_data['doc_messages']:
                    message_ids = context.user_data['doc_messages'][doc_id]

                    # Удаляем все сообщения кроме последнего
                    for msg_id in message_ids[:-1]:
                        try:
                            await context.bot.delete_message(chat_id=user.id, message_id=msg_id)
                        except Exception as e:
                            print(f"⚠️ Не удалось удалить сообщение {msg_id}: {e}")

                    # Очищаем сохранённые ID
                    del context.user_data['doc_messages'][doc_id]

                # Определяем куда возвращаться
                back_callbacks = {
                    'text': 'my_texts',
                    'video': 'my_videos',
                    'file': 'my_files_docs',
                    'photo': 'my_photos'
                }
                back_callback = back_callbacks.get(file_type, 'my_files')

                keyboard = [[InlineKeyboardButton("◀️ Назад к списку", callback_data=back_callback)]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                # Проверяем тип сообщения
                if query.message.photo:
                    await query.message.delete()
                    await context.bot.send_message(
                        user.id,
                        f"✅ Текст успешно удалён из базы знаний!",
                        reply_markup=reply_markup
                    )
                else:
                    # Редактируем последнее сообщение (где была кнопка "Удалить")
                    await query.edit_message_text(
                        f"✅ Текст успешно удалён из базы знаний!",
                        reply_markup=reply_markup
                    )
            else:
                if query.message.photo:
                    await query.message.delete()
                    await context.bot.send_message(user.id, "⚠️ Ошибка при удалении.")
                else:
                    await query.edit_message_text("⚠️ Ошибка при удалении.")

        except Exception as e:
            print(f"Ошибка удаления документа: {e}")
            if query.message.photo:
                await query.message.delete()
                await context.bot.send_message(user.id, "⚠️ Ошибка подключения к серверу.")
            else:
                await query.edit_message_text("⚠️ Ошибка подключения к серверу.")

# Выход из загрузки медиа или текста в меню выбора типа
async def exit_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Выключаем режим ожидания фото (если был включен)
    context.user_data['waiting_for_photos'] = False
    context.user_data['photo_buffer'] = []

    # Отменяем таймер если есть
    if 'timer' in context.user_data and context.user_data['timer']:
        context.user_data['timer'].cancel()

    # Вызываем меню загрузки файлов
    await upload_file_menu(update, context)

    return ConversationHandler.END


# ИНИЦИАЛИЗАЦИЯ БОТА
def main():
    # Запуск бота
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Устанавливаем меню команд
    app.post_init = post_init
    app.add_handler(CommandHandler("start", start))

    # Хэндлер для загрузки текста
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

    # Хэндлер для загрузки видео
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

    app.add_handler(MessageHandler(filters.PHOTO, global_photo_handler), group=0)

    # Callback кнопки
    app.add_handler(CallbackQueryHandler(subscriptions_menu, pattern="^subscriptions$"))
    app.add_handler(CallbackQueryHandler(knowledge_base_menu, pattern="^knowledge_base$"))
    app.add_handler(CallbackQueryHandler(upload_file_menu, pattern="^upload_file$"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
    app.add_handler(CallbackQueryHandler(my_files, pattern="^my_files$"))
    app.add_handler(CallbackQueryHandler(my_texts, pattern="^my_texts$"))
    app.add_handler(CallbackQueryHandler(view_document, pattern="^view_doc_"))
    app.add_handler(CallbackQueryHandler(delete_document, pattern="^delete_doc_"))
    app.add_handler(CallbackQueryHandler(my_videos, pattern="^my_videos$"))
    app.add_handler(CallbackQueryHandler(my_photos, pattern="^my_photos$"))
    app.add_handler(CallbackQueryHandler(show_photo_original, pattern="^show_photo_"))
    app.add_handler(CallbackQueryHandler(upload_photo, pattern="^upload_photo$"))
    app.add_handler(CallbackQueryHandler(exit_upload, pattern="^exit_upload$"))

    print("🤖 Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()

# TODO: в коде найти все проверки на 0/inf и заменить их на проверку вхождения inf в строку
# TODO: везде где пользователь при загрузке файла получает ошибку или лимит, нужно проверить,
#  чтобы было exit_upload а не menu_upload, иначе хендлер не прервется