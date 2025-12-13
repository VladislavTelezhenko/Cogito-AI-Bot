# === БАЗА ЗНАНИЙ ===

async def knowledge_base_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню базы знаний"""
    query = update.callback_query
    await query.answer()

    text = """
📚 База знаний

Управляйте своими файлами:
"""

    keyboard = [
        [InlineKeyboardButton("📤 Загрузить файл", callback_data="upload_file")],
        [InlineKeyboardButton("📋 Мои файлы", callback_data="my_files")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)
    return KB_MENU


async def upload_file_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = """
📤 Загрузка контента

Выберите тип:
"""

    keyboard = [
        [InlineKeyboardButton("🎥 Видео", callback_data="upload_video")],
        [InlineKeyboardButton("📄 Документ", callback_data="upload_document")],
        [InlineKeyboardButton("🖼 Фото", callback_data="upload_photo")],
        [InlineKeyboardButton("📝 Текст", callback_data="upload_text")],
        [InlineKeyboardButton("◀️ Назад", callback_data="knowledge_base")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)
    return UPLOAD_TYPE


async def upload_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = """
🎥 Загрузка видео

Отправьте:
• Видеофайл (до 50 MB)
• Ссылку на YouTube
• Ссылку на Google Drive
• Ссылку на Яндекс.Диск

Пример: https://youtube.com/watch?v=...
"""

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Отмена", callback_data="upload_file")
        ]])
    )
    # TODO: переход в состояние ожидания файла


async def upload_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = """
📄 Загрузка документа

Отправьте:
• PDF файл
• DOCX файл
• Ссылку на документ

Поддерживаемые форматы: PDF, DOCX
"""

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Отмена", callback_data="upload_file")
        ]])
    )


async def upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = """
🖼 Загрузка фото

Отправьте изображение с текстом или графиками.

Поддерживаемые форматы: JPG, PNG
"""

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Отмена", callback_data="upload_file")
        ]])
    )

    return WAITING_PHOTO


async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка загрузки фото в базу знаний"""

    # Проверяем что это ТОЛЬКО фото
    if not update.message.photo:
        await update.message.reply_text(
            "⚠️ Пожалуйста, отправьте только фото.\n\n"
            "Для загрузки текста или документов используйте соответствующий раздел меню."
        )
        return WAITING_PHOTO

    user = update.effective_user

    await update.message.reply_text("⏳ Сохраняю фото...")

    try:
        async with httpx.AsyncClient() as client:
            # Получаем текущую статистику
            stats_response = await client.get(f"{API_URL}/users/{user.id}/stats")
            stats = stats_response.json()

            # Проверяем лимит хранилища (всего в базе)
            storage_photos = stats["kb_storage"]["photos"]
            storage_current, storage_limit = map(int, storage_photos.split("/"))

            # Проверяем дневной лимит загрузки
            daily_photos = stats["kb_daily"]["photos"]
            daily_current, daily_limit = map(int, daily_photos.split("/"))

            # Сколько можем загрузить = минимум из двух лимитов
            available_storage = storage_limit - storage_current
            available_daily = daily_limit - daily_current
            max_can_upload = min(available_storage, available_daily)

            if max_can_upload < 1:
                keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="upload_file")]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                reason = ""
                if available_storage < available_daily:
                    reason = f"Заполнено хранилище: {storage_current}/{storage_limit}"
                else:
                    reason = f"Дневной лимит: {daily_current}/{daily_limit}"

                await update.message.reply_text(
                    f"⚠️ Превышен лимит!\n\n{reason}",
                    reply_markup=reply_markup
                )
                return ConversationHandler.END

            # Берём самое большое качество (последнее фото в списке)
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            file_bytes = await file.download_as_bytearray()

            # Загружаем в Яндекс.Облако
            photo_url = upload_photo_to_s3(bytes(file_bytes), user.id)

            # Сохраняем в БД через API
            response = await client.post(
                f"{API_URL}/kb/upload/photos",
                json={
                    "telegram_id": user.id,
                    "photo_urls": [photo_url]
                },
                timeout=30.0
            )

            if response.status_code == 200:
                keyboard = [
                    [InlineKeyboardButton("📤 Загрузить ещё фото", callback_data="upload_photo")],
                    [InlineKeyboardButton("🖼 Мои фото", callback_data="my_photos")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    "✅ Фото успешно добавлено в базу знаний!",
                    reply_markup=reply_markup
                )
            else:
                keyboard = [[InlineKeyboardButton("◀️ Назад к выбору типа", callback_data="upload_file")]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    "⚠️ Ошибка при сохранении. Попробуйте позже.",
                    reply_markup=reply_markup
                )

    except Exception as e:
        print(f"Ошибка загрузки фото: {e}")

        keyboard = [[InlineKeyboardButton("◀️ Назад к выбору типа", callback_data="upload_file")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "⚠️ Ошибка подключения к серверу.",
            reply_markup=reply_markup
        )

    return ConversationHandler.END


async def handle_wrong_media_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка неправильных вложений при загрузке фото"""

    keyboard = [[InlineKeyboardButton("◀️ Назад к выбору типа", callback_data="upload_file")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚠️ Пожалуйста, отправьте только фото.\n\n"
        "Для загрузки текста или документов используйте соответствующие разделы меню.",
        reply_markup=reply_markup
    )
    return UPLOAD_TYPE


async def upload_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = """
📝 Загрузка текста

Отправьте ваш текст в следующем сообщении.

Это может быть:
- Конспект лекции
- Заметки
- Любая текстовая информация
"""

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Отмена", callback_data="upload_file")
        ]])
    )

    return WAITING_TEXT



# === НАСТРОЙКИ РЕЖИМА ОТВЕТОВ ===

async def chat_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = """
⚙️ Настройки режима ответов

Выберите стиль общения бота или создайте свой:
"""

    keyboard = [
        [InlineKeyboardButton("📋 Мои пресеты", callback_data="my_presets")],
        [InlineKeyboardButton("✨ Встроенные стили", callback_data="builtin_presets")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)
    return CHAT_MENU


async def builtin_presets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = """
✨ Встроенные стили

Выберите готовый стиль ответов:
"""

    keyboard = [
        [InlineKeyboardButton("🎯 Подготовка к тесту", callback_data="preset_builtin_test")],
        [InlineKeyboardButton("✍️ Помощь с эссе", callback_data="preset_builtin_essay")],
        [InlineKeyboardButton("⚡ Быстрые ответы", callback_data="preset_builtin_quick")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")],
        [InlineKeyboardButton("◀️ Назад", callback_data="chat_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def my_presets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # TODO: Получить пресеты из API
    text = """
📝 Мои пресеты (2/5 слотов)

1️⃣ Мой стиль для экзаменов
   "Отвечай чётко и структурированно..."

2️⃣ Для домашних заданий
   "Объясняй подробно с примерами..."

Доступно слотов: 3
"""

    keyboard = [
        [InlineKeyboardButton("1️⃣ Мой стиль для экзаменов", callback_data="preset_user_1")],
        [InlineKeyboardButton("2️⃣ Для домашних заданий", callback_data="preset_user_2")],
        [InlineKeyboardButton("➕ Создать новый пресет", callback_data="create_preset")],
        [InlineKeyboardButton("◀️ Назад", callback_data="chat_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def activate_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Пресет активирован! ✅")

    text = """
✅ Пресет активирован!

Теперь просто пишите свои вопросы, и я буду отвечать в выбранном стиле.

Для возврата в меню: /start
"""

    await query.edit_message_text(text)


# === РЕФЕРАЛЬНАЯ СИСТЕМА ===

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    # TODO: Получить реферальную ссылку из API
    ref_link = f"https://t.me/your_bot?start=ref_{user.id}"
    invited_count = 0  # TODO: получить из API

    text = f"""
👥 Пригласить друга

Приглашай друзей и получай бонусы! 🎁

🔗 Твоя реферальная ссылка:
`{ref_link}`

📊 Статистика:
• Приглашено: {invited_count} человек

🎁 Бонусы:
• За каждого друга: +7 дней Базовой подписки
• Друг получает: +3 дня Базовой подписки

Просто отправь ссылку другу!
"""

    keyboard = [
        [InlineKeyboardButton("📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)


# === ТЕХ ПОДДЕРЖКА ===

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Тех поддержка
    query = update.callback_query
    await query.answer()

    text = """
🆘 Техническая поддержка

💬 Telegram: @your_support_bot

Опишите вашу проблему, и мы ответим в течение 24 часов.
"""

    keyboard = [
        [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


# === НАВИГАЦИЯ ===
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем реальные данные из API
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_URL}/users/{user.id}/stats")
            stats = response.json()
        except:
            await query.edit_message_text("⚠️ Ошибка получения данных. Попробуйте /start")
            return

    # Формируем приветствие
    subscription_name = stats["subscription_name"]
    subscription_tier = stats["subscription_tier"]
    subscription_end = stats.get("subscription_end")
    messages_left = f"{stats['messages_left']}/{stats['messages_limit']}"

    kb_storage = stats["kb_storage"]
    kb_daily = stats["kb_daily"]

    welcome_text = f"""
👋 Привет, {user.first_name}!

Твой доступ к последним моделям ChatGPT 
с персональной базой знаний начинается тут.

📅 Подписка: {subscription_name}
"""

    if subscription_end:
        welcome_text += f"   Активна до: {subscription_end}\n"

    welcome_text += f"""
💬 Сообщений: {messages_left} сегодня

📚 Ваша база знаний:
"""

    if kb_storage["video_hours"] != "0/0":
        welcome_text += f"   🎥 Видео: {kb_storage['video_hours']}\n"

    welcome_text += f"""   📄 Файлы: {kb_storage['files']}
   🖼 Фото: {kb_storage['photos']}
   📝 Тексты: {kb_storage['texts']}

📤 Лимит загрузки в базу сегодня:
"""

    if kb_daily["video_minutes"] != "0/0":
        welcome_text += f"   🎥 Видео: {kb_daily['video_minutes']} мин\n"

    welcome_text += f"""   📄 Файлы: {kb_daily['files']}
   🖼 Фото: {kb_daily['photos']}
   📝 Тексты: {kb_daily['texts']}"""

    if subscription_tier != "ultra":
        welcome_text += "\n\n💎 Расширь свои возможности — купи следующий уровень подписки!"

    keyboard = [
        [InlineKeyboardButton("⭐ Подписки", callback_data="subscriptions")],
        [InlineKeyboardButton("📚 База знаний", callback_data="knowledge_base")],
        [InlineKeyboardButton("⚙️ Настройки режима ответов", callback_data="chat_settings")],
        [InlineKeyboardButton("👥 Пригласить друга", callback_data="referral")],
        [InlineKeyboardButton("🆘 Тех. поддержка", callback_data="support")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(welcome_text, reply_markup=reply_markup)
    return MAIN_MENU


# === ОБРАБОТКА СООБЩЕНИЙ ===

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка текстовых вопросов
    user_question = update.message.text

    # TODO: Отправка вопроса в backend API
    # TODO: RAG поиск в базе знаний
    # TODO: Получение ответа от LLM

    await update.message.reply_text(
        f"🤖 Вы спросили: {user_question}\n\n"
        "Здесь будет ответ на основе вашей базы знаний.\n\n"
        "(В разработке)"
    )


# ЗАПУСК
def main():
    # Запуск бота
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Устанавливаем меню команд
    app.post_init = post_init

    # Команды
    # Обработчик загрузки текста
    text_upload_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(upload_text, pattern="^upload_text$")
        ],
        states={
            WAITING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_upload),
                MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_wrong_media)
            ],
            UPLOAD_TYPE: [  # ← Добавь это состояние
                CallbackQueryHandler(upload_text, pattern="^upload_text$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(upload_file_menu, pattern="^upload_file$"),
            CallbackQueryHandler(knowledge_base_menu, pattern="^knowledge_base$"),
            CommandHandler("start", start)
        ],
        per_message=False
    )
    app.add_handler(text_upload_handler)
    # Обработчик загрузки фото
    photo_upload_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(upload_photo, pattern="^upload_photo$")
        ],
        states={
            WAITING_PHOTO: [
                MessageHandler(filters.PHOTO, handle_photo_upload),
                MessageHandler(filters.TEXT | filters.VIDEO | filters.Document.ALL, handle_wrong_media_photo)
            ],
            UPLOAD_TYPE: [
                CallbackQueryHandler(upload_photo, pattern="^upload_photo$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(upload_file_menu, pattern="^upload_file$"),
            CallbackQueryHandler(knowledge_base_menu, pattern="^knowledge_base$"),
            CommandHandler("start", start)
        ],
        per_message=False
    )
    app.add_handler(photo_upload_handler)
    app.add_handler(CommandHandler("start", start))

    # Callback кнопки
    app.add_handler(CallbackQueryHandler(subscriptions_menu, pattern="^subscriptions$"))
    app.add_handler(CallbackQueryHandler(process_payment, pattern="^sub_"))

    app.add_handler(CallbackQueryHandler(knowledge_base_menu, pattern="^knowledge_base$"))
    app.add_handler(CallbackQueryHandler(upload_file_menu, pattern="^upload_file$"))
    app.add_handler(CallbackQueryHandler(upload_video, pattern="^upload_video$"))
    app.add_handler(CallbackQueryHandler(upload_document, pattern="^upload_document$"))
    app.add_handler(CallbackQueryHandler(upload_photo, pattern="^upload_photo$"))
    app.add_handler(CallbackQueryHandler(my_files, pattern="^my_files$"))
    app.add_handler(CallbackQueryHandler(view_document, pattern="^view_doc_"))
    app.add_handler(CallbackQueryHandler(delete_document, pattern="^delete_doc_"))

    app.add_handler(CallbackQueryHandler(chat_settings, pattern="^chat_settings$"))
    app.add_handler(CallbackQueryHandler(builtin_presets, pattern="^builtin_presets$"))
    app.add_handler(CallbackQueryHandler(my_presets, pattern="^my_presets$"))
    app.add_handler(CallbackQueryHandler(activate_preset, pattern="^preset_"))

    app.add_handler(CallbackQueryHandler(referral, pattern="^referral$"))

    app.add_handler(CallbackQueryHandler(support, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))

    # Обработка текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()