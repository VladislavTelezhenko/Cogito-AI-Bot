# Handlers для работы с подписками

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from utils.bot_utils import api_request, logger


# ============================================================================
# МЕНЮ ПОДПИСОК
# ============================================================================

# Меню с выбором подписки
async def subscriptions_menu(update: Update, context):
    query = update.callback_query
    await query.answer()

    # Получаем тарифы из API
    success, tiers, error = await api_request("GET", "/subscriptions/tiers")

    if not success:
        await query.edit_message_text(
            "⚠️ Ошибка получения данных. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_main")]])
        )
        return

    # Формируем текст меню
    text = "⭐ Подписки" + "⠀" * 20 + "\n\n"  # Невидимые пробелы Брайля для ширины

    for tier in tiers:
        text += f"<b>{tier['display_name']} — {tier['price_rubles']}₽/мес</b>\n"
        text += f"• {tier['model_name']}\n"
        text += f"• {tier['daily_messages']} сообщений в день\n\n"

        text += "📚 База знаний:\n"

        # Видео
        if tier['video_hours_limit'] == 9999:
            text += "   🎥 Безлимит видео\n"
        elif tier['video_hours_limit'] > 0:
            text += f"   🎥 {tier['video_hours_limit']}ч видео\n"

        # Файлы
        if tier['files_limit'] == 9999:
            text += "   📄 Безлимит файлов\n"
        elif tier['files_limit'] > 0:
            text += f"   📄 {tier['files_limit']} файлов\n"

        # Фото
        if tier['photos_limit'] == 9999:
            text += "   🖼 Безлимит фото\n"
        elif tier['photos_limit'] > 0:
            text += f"   🖼 {tier['photos_limit']} фото\n"

        # Тексты
        if tier['texts_limit'] == 9999:
            text += "   📝 Безлимит текстов\n"
        elif tier['texts_limit'] > 0:
            text += f"   📝 {tier['texts_limit']} текстов\n"

        text += "\n📤 Загрузка в день:\n"

        # Дневное видео
        if tier['daily_video_hours'] == 9999:
            text += "   🎥 Безлимит видео\n"
        elif tier['daily_video_hours'] > 0:
            text += f"   🎥 {tier['daily_video_hours']}ч видео\n"

        # Дневные файлы
        if tier['daily_files'] == 9999:
            text += "   📄 Безлимит файлов\n"
        elif tier['daily_files'] > 0:
            text += f"   📄 {tier['daily_files']} файлов\n"

        # Дневные фото
        if tier['daily_photos'] == 9999:
            text += "   🖼 Безлимит фото\n"
        elif tier['daily_photos'] > 0:
            text += f"   🖼 {tier['daily_photos']} фото\n"

        # Дневные тексты
        if tier['daily_texts'] == 9999:
            text += "   📝 Безлимит текстов\n"
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

    keyboard.append([InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")


# ============================================================================
# ПОКУПКА ПОДПИСКИ
# ============================================================================

# Обработка выбора подписки (заглушка для будущей интеграции платежей)
async def handle_subscription_selection(update: Update, context):
    query = update.callback_query
    await query.answer()

    tier_name = query.data.split("_")[1]

    logger.info(f"Пользователь {query.from_user.id} выбрал подписку: {tier_name}")

    # TODO: Интеграция с платёжной системой (ЮKassa, Stripe)
    await query.edit_message_text(
        "💳 Оплата подписок будет доступна в следующей версии!\n\n"
        f"Выбранный тариф: {tier_name}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_main")]])
    )