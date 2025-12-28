"""
Handlers для просмотра и управления документами в базе знаний.

Включает просмотр списков, полного текста, фото и удаление.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from shared.config import CONTENT_CONFIG, Messages, Limits
from utils.bot_utils import (
    api_request,
    get_user_stats,
    ButtonFactory,
    paginate_documents,
    logger
)


async def my_files(update: Update, context):
    """
    Меню выбора типа файлов для просмотра.

    Показывает статистику хранилища и кнопки для каждого типа.

    Args:
        update: Telegram Update
        context: Callback context
    """
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


async def my_texts(update: Update, context):
    """
    Показать список текстов пользователя.

    Args:
        update: Telegram Update
        context: Callback context
    """
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


async def my_videos(update: Update, context):
    """
    Показать список видео пользователя.

    Args:
        update: Telegram Update
        context: Callback context
    """
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


async def my_photos(update: Update, context):
    """
    Показать список фото пользователя.

    Args:
        update: Telegram Update
        context: Callback context
    """
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


async def my_files_docs(update: Update, context):
    """
    Показать список файлов пользователя.

    Args:
        update: Telegram Update
        context: Callback context
    """
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


async def view_document(update: Update, context):
    """
    Просмотр полного текста документа.

    Разбивает длинный текст на части по 4000 символов.

    Args:
        update: Telegram Update
        context: Callback context
    """
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

    logger.debug(f"Отображён документ {doc_id} для пользователя {user.id}")


async def show_photo_original(update: Update, context):
    """
    Показать оригинальное фото.

    Args:
        update: Telegram Update
        context: Callback context
    """
    query = update.callback_query
    await query.answer()

    document_id = int(query.data.split("_")[-1])

    # Получаем presigned URL
    success, photo_data, error = await api_request(
        "GET",
        f"/kb/photo/{document_id}/presigned?telegram_id={query.from_user.id}"
    )

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

    logger.debug(f"Отображено оригинальное фото {document_id}")


async def delete_document(update: Update, context):
    """
    Удалить документ из базы знаний.

    Args:
        update: Telegram Update
        context: Callback context
    """
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

        logger.info(f"Документ {doc_id} удалён пользователем {user.id}")
    else:
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(user.id, Messages.ERROR_DATA)
        else:
            await query.edit_message_text(Messages.ERROR_DATA)