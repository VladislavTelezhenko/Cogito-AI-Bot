"""
Handlers для загрузки файлов (TXT, PDF, DOCX) в базу знаний.

Использует буферизацию для загрузки нескольких файлов за раз.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
import base64
from datetime import datetime

from shared.config import Limits
from utils.bot_utils import (
    check_upload_limits,
    FileValidator,
    ButtonFactory,
    file_uploader,
    logger
)


async def upload_file_doc(update: Update, context):
    """
    Начало загрузки файлов.

    Проверяет лимиты и активирует режим буферизации файлов.

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

    logger.info(f"Пользователь {user.id} начал загрузку файлов")

    return ConversationHandler.END


async def reject_text_when_waiting_files(update: Update, context):
    """
    Отклонение текстовых сообщений при ожидании файлов.

    Args:
        update: Telegram Update
        context: Callback context
    """
    if context.user_data.get('waiting_for_files'):
        await update.message.reply_text(
            "⚠️ Ожидаю файлы (TXT, PDF, DOCX)!\n\n"
            "Отправьте документы или нажмите кнопку ниже:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]])
        )


async def global_document_handler(update: Update, context):
    """
    Глобальный обработчик документов.

    Обрабатывает документы только если активен режим ожидания.
    Валидирует файл и добавляет в буфер.

    Args:
        update: Telegram Update
        context: Callback context
    """
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
        logger.warning(f"Файл отклонён: {doc.file_name}, причина: {error_message}")

        await update.message.reply_text(
            error_message,
            reply_markup=InlineKeyboardMarkup([[ButtonFactory.back_button("upload_file_menu")]])
        )
        return

    try:
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

        logger.debug(f"Файл добавлен в буфер: user={user.id}, filename={doc.file_name}")

    except Exception as e:
        logger.error(f"Ошибка обработки файла: {e}")
        await update.message.reply_text(
            "⚠️ Ошибка обработки файла. Попробуйте ещё раз.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отменить", callback_data="exit_upload")]])
        )