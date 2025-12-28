"""
Утилиты для Telegram бота.

Включает: API запросы, проверку лимитов, валидацию файлов,
буферизацию загрузки, пагинацию и фабрики кнопок.
"""

import aiohttp
import asyncio
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from shared.config import settings, Limits, Messages, CONTENT_CONFIG

# Настройка логирования
logger = logging.getLogger(__name__)


# ============================================================================
# API REQUESTS
# ============================================================================

async def api_request(
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Выполнить HTTP запрос к API.

    Args:
        method: HTTP метод (GET, POST, PUT, DELETE)
        endpoint: Путь эндпоинта (например, /users/register)
        json: JSON данные для POST/PUT
        params: Query параметры для GET

    Returns:
        Кортеж (success, data, error_message)
    """
    url = f"{settings.API_URL}{endpoint}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                    method,
                    url,
                    json=json,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
            ) as response:

                if response.status == 200:
                    data = await response.json()
                    return True, data, None
                else:
                    error_data = await response.json()
                    error_message = error_data.get("detail", f"HTTP {response.status}")
                    logger.error(f"API Error: {method} {endpoint} -> {response.status}: {error_message}")
                    return False, None, error_message

    except asyncio.TimeoutError:
        logger.error(f"Timeout: {method} {endpoint}")
        return False, None, "Request timeout"
    except Exception as e:
        logger.error(f"Exception in API request: {method} {endpoint} -> {e}")
        return False, None, str(e)


async def get_user_stats(telegram_id: int) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Получить статистику пользователя.

    Args:
        telegram_id: ID пользователя в Telegram

    Returns:
        Кортеж (success, stats_dict, error)
    """
    return await api_request("GET", f"/users/{telegram_id}/stats")


# ============================================================================
# ПРОВЕРКА ЛИМИТОВ
# ============================================================================

async def check_upload_limits(
        telegram_id: int,
        content_type: str
) -> Tuple[bool, str, List[List[InlineKeyboardButton]]]:
    """
    Проверить лимиты загрузки для типа контента.

    Args:
        telegram_id: ID пользователя
        content_type: Тип контента (text/photo/video/file)

    Returns:
        Кортеж (can_upload, error_message, keyboard)
    """
    # Получаем статистику
    success, stats, error = await get_user_stats(telegram_id)

    if not success:
        keyboard = [[ButtonFactory.back_button("upload_file_menu")]]
        return False, Messages.ERROR_CONNECTION, keyboard

    kb_storage = stats["kb_storage"]
    kb_daily = stats["kb_daily"]
    subscription_tier = stats["subscription_tier"]

    # Получаем конфигурацию типа контента
    config = CONTENT_CONFIG.get(content_type)
    if not config:
        keyboard = [[ButtonFactory.back_button("upload_file_menu")]]
        return False, "⚠️ Неизвестный тип контента!", keyboard

    storage_value = kb_storage.get(config["storage_key"], "0/0")
    daily_value = kb_daily.get(config["daily_key"], "0/0")

    # Проверка хранилища
    if "∞" not in storage_value:
        parts = storage_value.split("/")
        if len(parts) != 2:
            keyboard = [[ButtonFactory.back_button("upload_file_menu")]]
            return False, Messages.ERROR_DATA, keyboard

        try:
            storage_current = int(parts[0]) if parts[0].isdigit() else float(parts[0])
            storage_limit = int(parts[1]) if parts[1].isdigit() else float(parts[1])
        except ValueError:
            keyboard = [[ButtonFactory.back_button("upload_file_menu")]]
            return False, Messages.ERROR_DATA, keyboard

        if storage_current >= storage_limit:
            keyboard = []
            text = f"⚠️ Хранилище {config['title_genitive']} заполнено!\n\n"
            text += f"Использовано: {storage_current}/{storage_limit} {config['unit']}\n\n"

            if subscription_tier not in ["ultra", "admin"]:
                text += Messages.UPGRADE_PROMPT
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
            else:
                text += Messages.MAX_TIER_INFO

            keyboard.append([ButtonFactory.back_button("upload_file_menu")])
            return False, text, keyboard

    # Проверка дневного лимита
    if "∞" not in daily_value:
        parts = daily_value.split("/")
        if len(parts) != 2:
            keyboard = [[ButtonFactory.back_button("upload_file_menu")]]
            return False, Messages.ERROR_DATA, keyboard

        try:
            daily_current = int(parts[0]) if parts[0].isdigit() else float(parts[0])
            daily_limit = int(parts[1]) if parts[1].isdigit() else float(parts[1])
        except ValueError:
            keyboard = [[ButtonFactory.back_button("upload_file_menu")]]
            return False, Messages.ERROR_DATA, keyboard

        if daily_current >= daily_limit:
            keyboard = []
            text = f"⚠️ Дневной лимит {config['title_genitive']} исчерпан!\n\n"
            text += f"Использовано сегодня: {daily_current}/{daily_limit} {config['unit']}\n\n"

            if subscription_tier not in ["ultra", "admin"]:
                text += Messages.UPGRADE_PROMPT
                keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
            else:
                text += Messages.DAILY_RESET_INFO

            keyboard.append([ButtonFactory.back_button("upload_file_menu")])
            return False, text, keyboard

    # Лимиты OK
    return True, "", []


# ============================================================================
# ВАЛИДАЦИЯ ФАЙЛОВ
# ============================================================================

class FileValidator:
    """Валидатор файлов для загрузки."""

    ALLOWED_EXTENSIONS = {
        "photo": [".jpg", ".jpeg", ".png"],
        "file": [".txt", ".pdf", ".docx"]
    }

    MIME_TYPES = {
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }

    @staticmethod
    def validate_file(filename: str, file_size: int, content_type: str) -> Tuple[bool, str, Optional[str]]:
        """
        Валидация файла.

        Args:
            filename: Имя файла
            file_size: Размер в байтах
            content_type: Тип контента (photo/file)

        Returns:
            Кортеж (is_valid, error_message, mime_type)
        """
        # Проверка расширения
        ext = None
        for allowed_ext in FileValidator.ALLOWED_EXTENSIONS.get(content_type, []):
            if filename.lower().endswith(allowed_ext):
                ext = allowed_ext
                break

        if not ext:
            allowed = ", ".join(FileValidator.ALLOWED_EXTENSIONS.get(content_type, []))
            return False, f"⚠️ Неподдерживаемый формат!\n\nРазрешены: {allowed}", None

        # Проверка размера
        max_size_bytes = Limits.MAX_FILE_SIZE_MB * 1024 * 1024
        if file_size > max_size_bytes:
            return False, f"⚠️ Файл слишком большой!\n\nМаксимум: {Limits.MAX_FILE_SIZE_MB} MB", None

        # Определение MIME типа
        mime_type = FileValidator.MIME_TYPES.get(ext, "application/octet-stream")

        return True, "", mime_type


# ============================================================================
# BUFFERED UPLOADER (С ИСПРАВЛЕНИЕМ RACE CONDITION)
# ============================================================================

class BufferedUploader:
    """
    Менеджер буферизации для загрузки файлов и фото.

    Собирает файлы в буфер, затем отправляет их пакетом.
    Исправлен race condition через asyncio.Lock.
    """

    def __init__(self, upload_type: str, api_endpoint: str, max_items: int, wait_time: int):
        """
        Инициализация BufferedUploader.

        Args:
            upload_type: Тип загрузки (photo/file)
            api_endpoint: Эндпоинт API для отправки
            max_items: Максимальное количество элементов в буфере
            wait_time: Время ожидания (секунды) перед отправкой
        """
        self.upload_type = upload_type
        self.api_endpoint = api_endpoint
        self.max_items = max_items
        self.wait_time = wait_time
        self.lock = asyncio.Lock()  # FIX #19: Защита от race condition

    async def start_upload_mode(self, update: Update, context):
        """
        Запустить режим ожидания файлов.

        Args:
            update: Telegram Update
            context: Callback context
        """
        async with self.lock:
            context.user_data[f'waiting_for_{self.upload_type}s'] = True
            context.user_data[f'{self.upload_type}_buffer'] = []
            context.user_data[f'{self.upload_type}_timer'] = None

    async def is_waiting(self, context):
        """
        Проверить активен ли режим ожидания.

        Args:
            context: Callback context

        Returns:
            True если режим активен
        """
        return context.user_data.get(f'waiting_for_{self.upload_type}s', False)

    async def add_to_buffer(self, update: Update, context, item: dict):
        """
        Добавить элемент в буфер.

        Args:
            update: Telegram Update
            context: Callback context
            item: Элемент для добавления
        """
        async with self.lock:
            buffer = context.user_data.get(f'{self.upload_type}_buffer', [])
            buffer.append(item)
            context.user_data[f'{self.upload_type}_buffer'] = buffer

            # Отменяем старый таймер
            timer = context.user_data.get(f'{self.upload_type}_timer')
            if timer:
                timer.cancel()

            # Если буфер заполнен - отправляем сразу
            if len(buffer) >= self.max_items:
                await self._send_buffer(update, context)
            else:
                # Иначе запускаем новый таймер
                timer = asyncio.create_task(self._wait_and_send(update, context))
                context.user_data[f'{self.upload_type}_timer'] = timer

    async def _wait_and_send(self, update: Update, context):
        """
        Подождать и отправить буфер.

        Args:
            update: Telegram Update
            context: Callback context
        """
        try:
            await asyncio.sleep(self.wait_time)
            async with self.lock:
                await self._send_buffer(update, context)
        except asyncio.CancelledError:
            logger.debug(f"Таймер {self.upload_type} отменён")

    async def _send_buffer(self, update: Update, context):
        """
        Отправить буфер в API.

        Args:
            update: Telegram Update
            context: Callback context
        """
        buffer = context.user_data.get(f'{self.upload_type}_buffer', [])

        if not buffer:
            return

        user_id = update.effective_user.id

        await context.bot.send_message(
            user_id,
            f"⏳ Отправляю {len(buffer)} {self.upload_type}(s) на обработку..."
        )

        # Формируем payload
        if self.upload_type == "photo":
            payload = {
                "telegram_id": user_id,
                "photos": buffer
            }
        else:  # file
            payload = {
                "telegram_id": user_id,
                "files": buffer
            }

        # Отправляем в API
        success, data, error = await api_request("POST", self.api_endpoint, json=payload)

        if success:
            logger.info(f"{len(buffer)} {self.upload_type}(s) отправлено на обработку для пользователя {user_id}")

            success_text = f"✅ {len(buffer)} {self.upload_type}(s) добавлено в базу знаний!"

            keyboard = ButtonFactory.success_keyboard(self.upload_type)
            await context.bot.send_message(
                user_id,
                success_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            logger.error(f"Ошибка загрузки {self.upload_type}s: {error}")
            await context.bot.send_message(user_id, Messages.ERROR_UPLOAD)

        # Очищаем состояние
        await self.stop_upload_mode(context)

    async def stop_upload_mode(self, context):
        """
        Остановить режим ожидания и очистить буфер.

        Args:
            context: Callback context
        """
        async with self.lock:
            # Отменяем таймер если есть
            timer = context.user_data.get(f'{self.upload_type}_timer')
            if timer and not timer.done():
                timer.cancel()

            # Очищаем состояние
            context.user_data[f'waiting_for_{self.upload_type}s'] = False
            context.user_data[f'{self.upload_type}_buffer'] = []
            context.user_data[f'{self.upload_type}_timer'] = None

            logger.debug(f"Режим загрузки {self.upload_type} остановлен")


# Создаём глобальные инстансы
photo_uploader = BufferedUploader(
    upload_type="photo",
    api_endpoint="/kb/upload/photos",
    max_items=Limits.BUFFER_MAX_ITEMS,
    wait_time=Limits.BUFFER_WAIT_TIME_SEC
)

file_uploader = BufferedUploader(
    upload_type="file",
    api_endpoint="/kb/upload/files",
    max_items=Limits.BUFFER_MAX_ITEMS,
    wait_time=Limits.BUFFER_WAIT_TIME_SEC
)


# ============================================================================
# ПАГИНАЦИЯ ДОКУМЕНТОВ
# ============================================================================

async def paginate_documents(
        documents: List[Dict],
        content_type: str,
        context: ContextTypes.DEFAULT_TYPE,
        query,
        user_id: int,
        page: int = 0,
        items_per_page: int = 5
):
    """
    Пагинация списка документов.

    Args:
        documents: Список документов
        content_type: Тип контента
        context: Callback context
        query: Callback query
        user_id: ID пользователя
        page: Номер страницы
        items_per_page: Элементов на странице
    """
    total = len(documents)
    total_pages = (total + items_per_page - 1) // items_per_page

    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_documents = documents[start_idx:end_idx]

    config = CONTENT_CONFIG.get(content_type, {})

    text = f"{config.get('icon', '📝')} {config.get('title_plural', 'Файлы')} ({total})\n\n"

    keyboard = []

    for doc in page_documents:
        filename = doc['filename']
        upload_date = doc['upload_date'][:10]

        button_text = f"📄 {filename[:25]}... ({upload_date})"

        if content_type == "photo":
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_doc_{doc['id']}")])
            keyboard.append([InlineKeyboardButton("🖼 Показать оригинал", callback_data=f"show_photo_{doc['id']}")])
        else:
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_doc_{doc['id']}")])

    # Навигация
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data=f"page_{content_type}_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Вперёд ▶️", callback_data=f"page_{content_type}_{page + 1}"))

    if nav_row:
        keyboard.append(nav_row)

    # Кнопки действий
    keyboard.append([ButtonFactory.upload_more(content_type)])
    keyboard.append([ButtonFactory.back_button("my_files")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if query.message.photo:
        await query.message.delete()
        await context.bot.send_message(user_id, text, reply_markup=reply_markup)
    else:
        await query.edit_message_text(text, reply_markup=reply_markup)


# ============================================================================
# ФАБРИКИ КНОПОК
# ============================================================================

class ButtonFactory:
    """Фабрика для создания стандартных кнопок."""

    @staticmethod
    def back_button(callback: str) -> InlineKeyboardButton:
        """
        Кнопка "Назад".

        Args:
            callback: Callback data

        Returns:
            InlineKeyboardButton
        """
        return InlineKeyboardButton("◀️ Назад", callback_data=callback)

    @staticmethod
    def upload_more(content_type: str) -> InlineKeyboardButton:
        """
        Кнопка "Загрузить ещё".

        Args:
            content_type: Тип контента

        Returns:
            InlineKeyboardButton
        """
        config = CONTENT_CONFIG.get(content_type, {})
        return InlineKeyboardButton(
            f"➕ Загрузить ещё {config.get('title_accusative', 'файлы')}",
            callback_data=config.get('callbacks', {}).get('upload', 'upload_file')
        )

    @staticmethod
    def success_keyboard(content_type: str) -> List[List[InlineKeyboardButton]]:
        """
        Клавиатура после успешной загрузки.

        Args:
            content_type: Тип контента

        Returns:
            Список списков кнопок
        """
        return [
            [ButtonFactory.upload_more(content_type)],
            [ButtonFactory.back_button("upload_file_menu")]
        ]