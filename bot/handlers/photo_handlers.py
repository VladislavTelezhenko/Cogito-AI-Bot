"""
Handlers для загрузки фото в базу знаний.

Использует буферизацию для загрузки нескольких фото за раз.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
from PIL import Image
import io
import base64
from datetime import datetime

from shared.config import Limits
from utils.bot_utils import (
    check_upload_limits,
    photo_uploader,
    logger
)


def convert_to_jpeg_for_ocr(photo_bytes: bytes) -> str:
    """
    Конвертировать изображение в JPEG для OCR.

    Обрабатывает RGBA, LA, P режимы, конвертируя их в RGB.

    Args:
        photo_bytes: Байты изображения

    Returns:
        Base64 строка JPEG изображения

    Raises:
        ValueError: Если не удалось обработать изображение
    """
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

        # Кодируем в base64
        try:
            jpeg_base64 = base64.b64encode(jpeg_bytes).decode('utf-8')
            return jpeg_base64
        except Exception as e:
            logger.error(f"Ошибка кодирования в base64: {e}")
            raise ValueError(f"Failed to encode to base64: {e}")

    except Exception as e:
        logger.error(f"Ошибка конвертации в JPEG: {e}")
        raise


async def upload_photo(update: Update, context):
    """
    Начало загрузки фото.

    Проверяет лимиты и активирует режим буферизации фото.

    Args:
        update: Telegram Update
        context: Callback context

    Returns:
        ConversationHandler.END
    """
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

    logger.info(f"Пользователь {user.id} начал загрузку фото")

    return ConversationHandler.END


async def global_photo_handler(update: Update, context):
    """
    Глобальный обработчик фото.

    Обрабатывает фото только если активен режим ожидания.
    Конвертирует в JPEG и добавляет в буфер.

    Args:
        update: Telegram Update
        context: Callback context
    """
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

    try:
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

        logger.debug(f"Фото добавлено в буфер: user={user.id}, filename={filename}")

    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        await update.message.reply_text(
            "⚠️ Ошибка обработки фото. Попробуйте ещё раз.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]])
        )