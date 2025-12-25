# Handlers для работы с базой знаний

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import yt_dlp
import re
import asyncio
from PIL import Image
import io
import base64
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import ffmpeg

from shared.config import settings, CONTENT_CONFIG, Limits, Messages
from bot_utils import (
    api_request,
    get_user_stats,
    check_upload_limits,
    FileValidator,
    ButtonFactory,
    safe_message_edit,
    photo_uploader,
    file_uploader,
    paginate_documents,
    logger
)

# Executor для блокирующих операций
executor = ThreadPoolExecutor(max_workers=5)

# Состояния диалога
WAITING_TEXT, WAITING_VIDEO = range(2)


# ============================================================================
# ГЛАВНОЕ МЕНЮ БАЗЫ ЗНАНИЙ
# ============================================================================

# Меню базы знаний
async def knowledge_base_menu(update: Update, context):
    query = update.callback_query
    await query.answer()

    text = """
📚 База знаний

Управляйте своими файлами и обучайте\nнеросеть под ваши задачи!
"""

    keyboard = [
        [InlineKeyboardButton("📤 Загрузить файл", callback_data="upload_file")],
        [InlineKeyboardButton("📋 Мои файлы", callback_data="my_files")],
        [ButtonFactory.back_to_main()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


# Меню загрузки файла
async def upload_file_menu(update: Update, context):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем статистику
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

    # Показываем только доступные типы через CONTENT_CONFIG
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


# ============================================================================
# ЗАГРУЗКА ТЕКСТА
# ============================================================================

# Загрузка текста в базу знаний
async def upload_text(update: Update, context):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Проверяем лимиты
    can_upload, error_message, keyboard = await check_upload_limits(user.id, "text")

    if not can_upload:
        await query.edit_message_text(error_message, reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    # Лимиты OK
    text = """
📝 Загрузка текста

Отправьте ваш текст в следующем сообщении:
"""

    keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="exit_upload")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)

    return WAITING_TEXT


# Обработка текста от пользователя
async def handle_text_upload(update: Update, context):
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

    # Отправляем через API
    success, data, error = await api_request(
        "POST",
        "/kb/upload/text",
        json={
            "telegram_id": user.id,
            "text": text_content
        }
    )

    if success:
        await update.message.reply_text(
            "✅ Текст успешно добавлен в базу знаний!\n\n"
            "Теперь вы можете задавать вопросы по этому материалу\nили обучать нейросеть.",
            reply_markup=InlineKeyboardMarkup(ButtonFactory.success_keyboard("text"))
        )
    else:
        await update.message.reply_text(Messages.ERROR_UPLOAD)

    return ConversationHandler.END


# Обработчик вложений при загрузке текста
async def handle_wrong_media_in_text(update: Update, context):
    await update.message.reply_text(
        "⚠️ Пожалуйста, отправьте только текст без вложений.\n\n"
        "Для загрузки файлов, фото или видео используйте соответствующий раздел меню.",
        reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("exit_upload")]])
    )
    return WAITING_TEXT


# ============================================================================
# ЗАГРУЗКА ВИДЕО
# ============================================================================

# Загрузка видео в базу знаний
async def upload_video(update: Update, context):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Проверяем лимиты
    can_upload, error_message, keyboard = await check_upload_limits(user.id, "video")

    if not can_upload:
        await query.edit_message_text(error_message, reply_markup=InlineKeyboardMarkup(keyboard))
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
                probe = ffmpeg.probe(url, timeout=Limits.VIDEO_INFO_TIMEOUT_SEC)
                duration_seconds = float(probe['format']['duration'])
                duration_hours = duration_seconds / 3600

                filename = url.split('/')[-1].split('?')[0]
                title = filename if filename else f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                return duration_hours, title, None

            except Exception as e:
                return None, None, "Не удалось получить информацию о видео"

        # Для YouTube, Rutube — запускаем в отдельном потоке
        loop = asyncio.get_event_loop()

        try:
            duration_hours, title, error = await asyncio.wait_for(
                loop.run_in_executor(executor, _get_video_info_sync, url, Limits.VIDEO_INFO_TIMEOUT_SEC),
                timeout=Limits.VIDEO_INFO_TIMEOUT_SEC
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
                    return None, None, "Непредвиденная ошибка! Возможно, видео не существует или имеет ограниченный доступ."

            return duration_hours, title, None

        except asyncio.TimeoutError:
            return None, None, "Превышено время ожидания. Возможно, видео недоступно или требует авторизации"

    except Exception as e:
        logger.error(f"Ошибка для {url}: {e}")
        return None, None, "Не удалось получить информацию о видео"


# Обработка загрузки видео
async def handle_video_upload(update: Update, context):
    if update.message.photo or update.message.document or update.message.video:
        await update.message.reply_text(
            "⚠️ Пожалуйста, отправьте только ссылки на видео (без файлов).\n\n"
            "Формат: каждая ссылка с новой строки.",
            reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("exit_upload")]])
        )
        return WAITING_VIDEO

    text = update.message.text.strip()
    user = update.effective_user

    # Разбиваем на строки
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    # Проверяем что все строки — это ссылки
    url_pattern = re.compile(r'^https?://')
    urls = []

    for line in lines:
        if not url_pattern.match(line):
            await update.message.reply_text(
                "⚠️ Отправьте только полные ссылки на видео!\n\n"
                f"Некорректная строка: {line[:50]}...\n\n",
                reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("exit_upload")]]),
                disable_web_page_preview=True
            )
            return WAITING_VIDEO
        urls.append(line)

    # Проверяем лимит
    if len(urls) > Limits.BUFFER_MAX_ITEMS:
        await update.message.reply_text(
            f"⚠️ Максимум {Limits.BUFFER_MAX_ITEMS} ссылок за раз!\n\n"
            f"Отправлено: {len(urls)}",
            reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("exit_upload")]])
        )
        return WAITING_VIDEO

    # Убираем дубликаты
    unique_urls = list(dict.fromkeys(urls))

    # Проверяем поддерживаемые источники
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
            await update.message.reply_text(
                f"⚠️ Неподдерживаемый источник!\n\n"
                f"Ссылка: {url[:50]}...\n\n"
                "Поддерживаемые источники:\n"
                "• Прямые ссылки (.mp4, .mkv, .avi)\n"
                "• YouTube\n"
                "• Rutube\n"
                "• Яндекс.Диск",
                reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("exit_upload")]])
            )
            return WAITING_VIDEO

    # Получаем длительность
    await update.message.reply_text("⏳ Проверяю длительность видео...")

    video_info = []
    total_duration = 0
    failed_videos = []

    for url in unique_urls:
        duration, title, error = await get_video_duration(url)

        if error:
            failed_videos.append({'url': url, 'title': title, 'error': error})
        else:
            video_info.append({'url': url, 'title': title, 'duration': duration})
            total_duration += duration

    # Если есть ошибки
    if failed_videos:
        error_text = "⚠️ Не удалось обработать следующие видео:\n\n"
        for item in failed_videos:
            error_text += f"🔗 {item['url']}\n❌ {item['error']}\n\n"

        await update.message.reply_text(
            error_text,
            reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("exit_upload")]]),
            disable_web_page_preview=True
        )
        return WAITING_VIDEO

    # Проверяем лимиты с учётом длительности
    success, stats, error = await get_user_stats(user.id)

    if not success:
        await update.message.reply_text(Messages.ERROR_CONNECTION)
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
                text += Messages.UPGRADE_PROMPT
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
            else:
                text += Messages.MAX_TIER_INFO

            keyboard.append([ButtonFactory.back_button("exit_upload")])
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
                text += Messages.UPGRADE_PROMPT
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
            else:
                text += Messages.DAILY_RESET_INFO

            keyboard.append([ButtonFactory.back_button("exit_upload")])
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

    # Отправляем на обработку
    await update.message.reply_text("⏳ Отправляю видео на обработку...")

    success, data, error = await api_request(
        "POST",
        "/kb/upload/video",
        json={
            "telegram_id": user.id,
            "videos": video_info
        }
    )

    if success:
        success_text = f"✅ Видео добавлены в обработку!\n\n"
        success_text += f"📊 Количество: {len(video_info)}\n"
        success_text += f"⏱ Общая длительность: {total_duration:.2f}ч\n\n"
        success_text += "Мы пришлём уведомление, когда обработка завершится!"

        await update.message.reply_text(
            success_text,
            reply_markup=InlineKeyboardMarkup(ButtonFactory.success_keyboard("video"))
        )
    else:
        await update.message.reply_text(Messages.ERROR_UPLOAD)

    return ConversationHandler.END


# Обработка неверных медиа при загрузке видео
async def handle_wrong_media_in_video(update: Update, context):
    await update.message.reply_text(
        "⚠️ Пожалуйста, отправьте только полные ссылки на видео.\n\n",
        reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("exit_upload")]])
    )
    return WAITING_VIDEO


# ============================================================================
# ЗАГРУЗКА ФОТО
# ============================================================================

# Конвертация фото в JPEG
def convert_to_jpeg_for_ocr(photo_bytes: bytes) -> str:
    try:
        image = Image.open(io.BytesIO(photo_bytes))

        # Конвертируем в RGB
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

        return base64.b64encode(jpeg_bytes).decode('utf-8')

    except Exception as e:
        logger.error(f"Ошибка конвертации в JPEG: {e}")
        raise


# Загрузка фото
async def upload_photo(update: Update, context):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Проверяем лимиты
    can_upload, error_message, keyboard = await check_upload_limits(user.id, "photo")

    if not can_upload:
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(user.id, error_message, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text(error_message, reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    text = f"""🖼 Загрузка фото\n\nОтправьте <b>в одном сообщении</b> до {Limits.BUFFER_MAX_ITEMS} фото с текстом, который нужно распознать.\n\nПоддерживаемые форматы: JPG, PNG"""

    keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="exit_upload")]]

    if query.message.photo:
        await query.message.delete()
        await context.bot.send_message(user.id, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    # Запускаем режим ожидания фото
    await photo_uploader.start_upload_mode(update, context)

    return ConversationHandler.END


# Глобальный обработчик фото
async def global_photo_handler(update: Update, context):
    user = update.effective_user

    # Проверяем режим ожидания файлов
    if context.user_data.get('waiting_for_files'):
        await update.message.reply_text(
            "⚠️ Ожидаю файлы (TXT, PDF, DOCX), а не фото!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]])
        )
        return

    # Проверяем режим ожидания фото
    if not await photo_uploader.is_waiting(context):
        return

    # Обрабатываем фото
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = await file.download_as_bytearray()
    jpeg_base64 = convert_to_jpeg_for_ocr(bytes(photo_bytes))
    filename = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"

    # Добавляем в буфер
    await photo_uploader.add_to_buffer(update, context, {
        "base64": jpeg_base64,
        "filename": filename
    })


# ============================================================================
# ЗАГРУЗКА ФАЙЛОВ
# ============================================================================

# Загрузка файлов
async def upload_file_doc(update: Update, context):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Проверяем лимиты
    can_upload, error_message, keyboard = await check_upload_limits(user.id, "file")

    if not can_upload:
        await query.edit_message_text(error_message, reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    text = f"""📄 Загрузка файлов

Отправьте до {Limits.BUFFER_MAX_ITEMS} файлов <b>в одном сообщении</b>.

Поддерживаемые форматы:
- TXT
- PDF
- DOCX

Максимальный размер: {Limits.MAX_FILE_SIZE_MB} MB на файл"""

    keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="exit_upload")]]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    # Запускаем режим ожидания файлов
    await file_uploader.start_upload_mode(update, context)

    return ConversationHandler.END


# Отклонение текста при ожидании файлов
async def reject_text_when_waiting_files(update: Update, context):
    if context.user_data.get('waiting_for_files'):
        await update.message.reply_text(
            "⚠️ Ожидаю файлы (TXT, PDF, DOCX)!\n\n"
            "Отправьте документы или нажмите кнопку ниже:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]])
        )


# Отклонение фото при ожидании файлов
async def reject_photo_when_waiting_files(update: Update, context):
    if context.user_data.get('waiting_for_files'):
        await update.message.reply_text(
            "⚠️ Ожидаю файлы (TXT, PDF, DOCX)!\n\n"
            "Отправьте документы или нажмите кнопку ниже:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]])
        )


# Глобальный обработчик документов
async def global_document_handler(update: Update, context):
    user = update.effective_user

    # Проверяем наличие документа
    if not update.message.document:
        return

    # Проверяем режим ожидания
    if not await file_uploader.is_waiting(context):
        return

    doc = update.message.document

    # Валидация файла
    is_valid, error_message, mime_type = FileValidator.validate_file(
        doc.file_name,
        doc.file_size,
        "file"
    )

    if not is_valid:
        await update.message.reply_text(
            error_message,
            reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("upload_file_menu")]])
        )
        return

    # Скачиваем файл
    file = await context.bot.get_file(doc.file_id)
    file_bytes = await file.download_as_bytearray()
    file_base64 = base64.b64encode(bytes(file_bytes)).decode('utf-8')

    # Добавляем в буфер
    await file_uploader.add_to_buffer(update, context, {
        "filename": doc.file_name,
        "file_bytes": file_base64,
        "mime_type": mime_type
    })


# ============================================================================
# АДМИНИСТРИРОВАНИЕ ФАЙЛОВ
# ============================================================================

# Меню выбора типа файла
async def my_files(update: Update, context):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем статистику
    success, stats, error = await get_user_stats(user.id)

    if not success:
        await query.edit_message_text(
            Messages.ERROR_DATA,
            reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("knowledge_base")]])
        )
        return

    kb_storage = stats["kb_storage"]

    # Проверяем наличие файлов
    has_files = False

    for content_type, config in CONTENT_CONFIG.items():
        storage_value = kb_storage.get(config["storage_key"])
        if storage_value and storage_value not in ["0/0", "0/∞"]:
            current = float(storage_value.split("/")[0]) if "." in storage_value.split("/")[0] else int(
                storage_value.split("/")[0])
            if current > 0:
                has_files = True
                break

    # Если БЗ пустая
    if not has_files:
        await query.edit_message_text(
            "📋 Ваша база знаний пуста!\n\n"
            "Загрузите файлы, чтобы начать работу\nс базой знаний.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Загрузить файл", callback_data="upload_file")],
                [ButtonFactory.back_button("knowledge_base")]
            ])
        )
        return

    # Формируем меню
    text = "📋 Мои файлы\n\n📊 Ваше хранилище:\n"

    for content_type, config in CONTENT_CONFIG.items():
        storage_value = kb_storage.get(config["storage_key"])
        if storage_value and storage_value not in ["0/0"]:
            text += f"   {config['icon']} {config['title_plural']}: {storage_value} {config['unit']}\n"

    text += "\nВыберите тип файлов для просмотра:"

    keyboard = []

    for content_type, config in CONTENT_CONFIG.items():
        storage_value = kb_storage.get(config["storage_key"])
        if storage_value and storage_value not in ["0/0"]:
            keyboard.append([InlineKeyboardButton(
                f"{config['icon']} {config['title_plural']}",
                callback_data=config['callbacks']['my_list']
            )])

    keyboard.append([ButtonFactory.back_button("knowledge_base")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# Список текстов
async def my_texts(update: Update, context):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем документы
    success, data, error = await api_request("GET", f"/kb/documents/{user.id}")

    if not success:
        await query.edit_message_text(
            Messages.ERROR_DATA,
            reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("my_files")]])
        )
        return

    all_documents = data.get("documents", [])

    # Фильтруем тексты
    texts = [doc for doc in all_documents if doc["file_type"] == "text"]
    texts.sort(key=lambda x: x["upload_date"])

    # Если пусто
    if not texts:
        await query.edit_message_text(
            "📝 У вас пока нет текстов!",
            reply_markup=InlineKeyboardMarkup([
                [ButtonFactory.upload_more("text")],
                [ButtonFactory.back_button("my_files")]
            ])
        )
        return

    # Пагинация
    await paginate_documents(texts, "text", context, query, user.id)


# Список видео
async def my_videos(update: Update, context):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем документы
    success, data, error = await api_request("GET", f"/kb/documents/{user.id}")

    if not success:
        await query.edit_message_text(
            Messages.ERROR_DATA,
            reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("my_files")]])
        )
        return

    all_documents = data.get("documents", [])

    # Фильтруем видео
    videos = [doc for doc in all_documents if doc["file_type"] == "video" and doc.get("status") == "completed"]
    videos.sort(key=lambda x: x["upload_date"])

    # Если пусто
    if not videos:
        await query.edit_message_text(
            "🎥 У вас пока нет обработанных видео!",
            reply_markup=InlineKeyboardMarkup([
                [ButtonFactory.upload_more("video")],
                [ButtonFactory.back_button("my_files")]
            ])
        )
        return

    # Пагинация
    await paginate_documents(videos, "video", context, query, user.id)


# Список фото
async def my_photos(update: Update, context):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем документы
    success, data, error = await api_request("GET", f"/kb/documents/{user.id}")

    if not success:
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(user.id, Messages.ERROR_DATA)
        else:
            await query.edit_message_text(Messages.ERROR_DATA)
        return

    all_documents = data.get("documents", [])

    # Фильтруем фото
    photos = [doc for doc in all_documents if doc["file_type"] == "photo" and doc["status"] == "completed"]
    photos.sort(key=lambda x: x["upload_date"], reverse=True)

    # Если пусто
    if not photos:
        text = "🖼 У вас пока нет фото в базе знаний."
        keyboard = [
            [ButtonFactory.upload_more("photo")],
            [ButtonFactory.back_button("my_files")]
        ]

        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(user.id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Пагинация
    await paginate_documents(photos, "photo", context, query, user.id)


# Список файлов
async def my_files_docs(update: Update, context):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем документы
    success, data, error = await api_request("GET", f"/kb/documents/{user.id}")

    if not success:
        await query.edit_message_text(
            Messages.ERROR_DATA,
            reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("my_files")]])
        )
        return

    all_documents = data.get("documents", [])

    # Фильтруем файлы
    files = [doc for doc in all_documents if doc["file_type"] == "file" and doc["status"] == "completed"]
    files.sort(key=lambda x: x["upload_date"], reverse=True)

    # Если пусто
    if not files:
        await query.edit_message_text(
            "📄 У вас пока нет файлов!",
            reply_markup=InlineKeyboardMarkup([
                [ButtonFactory.upload_more("file")],
                [ButtonFactory.back_button("my_files")]
            ])
        )
        return

    # Пагинация
    await paginate_documents(files, "file", context, query, user.id)


# ============================================================================
# ПРОСМОТР И УДАЛЕНИЕ
# ============================================================================

# Просмотр полного текста
async def view_document(update: Update, context):
    query = update.callback_query
    await query.answer()

    doc_id = int(query.data.split("_")[2])
    user = query.from_user

    # Получаем документы
    success, data, error = await api_request("GET", f"/kb/documents/{user.id}")

    if not success:
        await query.edit_message_text(Messages.ERROR_DATA)
        return

    documents = data.get("documents", [])
    document = next((d for d in documents if d["id"] == doc_id), None)

    if not document:
        await query.edit_message_text("⚠️ Документ не найден.")
        return

    # Определяем callback для кнопки "Назад"
    file_type = document['file_type']
    back_callback = CONTENT_CONFIG.get(file_type, {}).get("callbacks", {}).get("my_list", "my_files")

    # Формируем текст
    config = CONTENT_CONFIG.get(file_type, {})
    title = f"{config.get('icon', '📝')} Полный текст"
    full_text = f"{title} {doc_id}\n\n{document['extracted_text']}"

    # Разбиваем на части
    text_parts = []
    for i in range(0, len(full_text), Limits.MESSAGE_MAX_LENGTH):
        text_parts.append(full_text[i:i + Limits.MESSAGE_MAX_LENGTH])

    # Инициализируем хранилище для message_id
    if 'doc_messages' not in context.user_data:
        context.user_data['doc_messages'] = {}

    message_ids = []
    total_parts = len(text_parts)

    # Отправляем части
    for i, part in enumerate(text_parts):
        is_last = (i == total_parts - 1)

        if is_last:
            keyboard = [
                [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_doc_{doc_id}")],
                [ButtonFactory.back_button(back_callback)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if i == 0:
                edited_msg = await query.edit_message_text(part, reply_markup=reply_markup)
                message_ids.append(edited_msg.message_id)
            else:
                sent_msg = await query.message.reply_text(part, reply_markup=reply_markup)
                message_ids.append(sent_msg.message_id)
        else:
            if i == 0:
                edited_msg = await query.edit_message_text(part)
                message_ids.append(edited_msg.message_id)
            else:
                sent_msg = await query.message.reply_text(part)
                message_ids.append(sent_msg.message_id)

    # Сохраняем ID сообщений
    context.user_data['doc_messages'][doc_id] = message_ids


# Показать оригинальное фото
async def show_photo_original(update: Update, context):
    query = update.callback_query
    await query.answer()

    document_id = int(query.data.split("_")[-1])

    # Получаем presigned URL
    success, photo_data, error = await api_request("GET", f"/kb/photo/{document_id}/presigned")

    if not success:
        await query.answer(Messages.ERROR_DATA, show_alert=True)
        return

    photo_url = photo_data["presigned_url"]

    keyboard = [[InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_doc_{document_id}")]]

    await query.message.reply_photo(
        photo=photo_url,
        caption="🖼 Оригинальное фото",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# Удаление документа
async def delete_document(update: Update, context):
    query = update.callback_query
    await query.answer()

    doc_id = int(query.data.split("_")[2])
    user = query.from_user

    # Получаем информацию о документе
    success, data, error = await api_request("GET", f"/kb/documents/{user.id}")

    if not success:
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(user.id, Messages.ERROR_DATA)
        else:
            await query.edit_message_text(Messages.ERROR_DATA)
        return

    documents = data.get("documents", [])
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
    success, delete_data, error = await api_request("DELETE", f"/kb/documents/{doc_id}")

    if success:
        # Удаляем предыдущие сообщения
        if 'doc_messages' in context.user_data and doc_id in context.user_data['doc_messages']:
            message_ids = context.user_data['doc_messages'][doc_id]

            for msg_id in message_ids[:-1]:
                try:
                    await context.bot.delete_message(chat_id=user.id, message_id=msg_id)
                except Exception as e:
                    logger.warning(f"Не удалось удалить сообщение {msg_id}: {e}")

            del context.user_data['doc_messages'][doc_id]

        # Определяем callback для возврата
        back_callback = CONTENT_CONFIG.get(file_type, {}).get("callbacks", {}).get("my_list", "my_files")
        keyboard = [[ButtonFactory.back_button(back_callback)]]

        # Отправляем подтверждение
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(
                user.id,
                "✅ Текст успешно удалён из базы знаний!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                "✅ Текст успешно удалён из базы знаний!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(user.id, Messages.ERROR_DATA)
        else:
            await query.edit_message_text(Messages.ERROR_DATA)


# ============================================================================
# ВЫХОД ИЗ ЗАГРУЗКИ
# ============================================================================

# Выход из режима загрузки
async def exit_upload(update: Update, context):
    query = update.callback_query
    await query.answer()

    # Останавливаем все режимы ожидания
    await photo_uploader.stop_upload_mode(context)
    await file_uploader.stop_upload_mode(context)

    await upload_file_menu(update, context)
    return ConversationHandler.END