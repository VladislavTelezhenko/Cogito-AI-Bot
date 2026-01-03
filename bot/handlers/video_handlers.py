"""
Handlers для загрузки видео в базу знаний.

Поддерживает YouTube, Rutube, Яндекс.Диск и прямые ссылки.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
import yt_dlp
import re
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import ffmpeg

from shared.config import Limits, Messages
from utils.bot_utils import (
    api_request,
    get_user_stats,
    check_upload_limits,
    ButtonFactory,
    logger
)

# Состояние ConversationHandler
WAITING_VIDEO = 1

# Executor для блокирующих операций
executor = ThreadPoolExecutor(max_workers=5)


async def upload_video(update: Update, context):
    """
    Начало загрузки видео.

    Проверяет лимиты и выводит инструкцию по загрузке.

    Args:
        update: Telegram Update
        context: Callback context

    Returns:
        WAITING_VIDEO или ConversationHandler.END
    """
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

    keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")

    logger.info(f"Пользователь {user.id} начал загрузку видео")

    return WAITING_VIDEO


def _get_video_info_sync(url: str, timeout: int = 15) -> tuple:
    """
    Получить информацию о видео через yt-dlp (синхронная функция).

    Args:
        url: URL видео
        timeout: Таймаут запроса

    Returns:
        Кортеж (duration_hours, title, error)
    """
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


async def get_video_duration(url: str) -> tuple:
    """
    Получить длительность видео с таймаутом.

    Поддерживает прямые ссылки (через ffprobe) и платформы (через yt-dlp).

    Args:
        url: URL видео

    Returns:
        Кортеж (duration_hours, title, error)
    """
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


async def handle_video_upload(update: Update, context):
    """
    Обработка ссылок на видео от пользователя.

    Проверяет валидность ссылок, получает длительность,
    проверяет лимиты и отправляет на обработку.

    Args:
        update: Telegram Update
        context: Callback context

    Returns:
        ConversationHandler.END
    """
    # Проверка на вложения
    if update.message.photo or update.message.document or update.message.video:
        await update.message.reply_text(
            "⚠️ Пожалуйста, отправьте только ссылки на видео (без файлов).\n\n"
            "Формат: каждая ссылка с новой строки.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]])
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
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]]),
                disable_web_page_preview=True
            )
            return WAITING_VIDEO
        urls.append(line)

    # Проверяем лимит количества
    if len(urls) > Limits.BUFFER_MAX_ITEMS:
        await update.message.reply_text(
            f"⚠️ Максимум {Limits.BUFFER_MAX_ITEMS} ссылок за раз!\n\n"
            f"Отправлено: {len(urls)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]])
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
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]])
            )
            return WAITING_VIDEO

    # Получаем длительность видео
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]]),
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
        parts = storage_videos.split("/")
        if len(parts) != 2:
            await update.message.reply_text(Messages.ERROR_DATA)
            return ConversationHandler.END

        storage_current = float(parts[0])
        storage_limit = float(parts[1])
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

            keyboard.append([InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")])
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END

    # Проверяем дневной лимит
    if "∞" not in daily_videos:
        parts = daily_videos.split("/")
        if len(parts) != 2:
            await update.message.reply_text(Messages.ERROR_DATA)
            return ConversationHandler.END

        daily_current = float(parts[0])
        daily_limit = float(parts[1])
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

            keyboard.append([InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")])
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

        logger.info(f"Видео отправлены на обработку: user={user.id}, count={len(video_info)}")

        await update.message.reply_text(
            success_text,
            reply_markup=InlineKeyboardMarkup([
                [ButtonFactory.upload_more("video")],
                [InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_main")]
            ])
        )
    else:
        logger.error(f"Ошибка загрузки видео: user={user.id}, error={error}")
        await update.message.reply_text(Messages.ERROR_UPLOAD)

    return ConversationHandler.END


async def handle_wrong_media_in_video(update: Update, context):
    """
    Обработчик неправильного типа медиа при загрузке видео.

    Args:
        update: Telegram Update
        context: Callback context

    Returns:
        WAITING_VIDEO
    """
    await update.message.reply_text(
        "⚠️ Пожалуйста, отправьте только полные ссылки на видео.\n\n",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]])
    )

    return WAITING_VIDEO