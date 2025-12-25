# Утилиты для Telegram бота

import logging
import httpx
from typing import Optional, Tuple, List, Dict, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from shared.config import settings, Messages, Limits, CONTENT_CONFIG, NOTIFICATION_TEMPLATES
import asyncio
import os

# ============================================================================
# НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


# ============================================================================
# API WRAPPER
# ============================================================================

# Универсальная обёртка для запросов к API
# Возвращает (success, data, error)
async def api_request(
        method: str,
        endpoint: str,
        timeout: int = Limits.API_REQUEST_TIMEOUT_SEC,
        **kwargs
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    url = f"{settings.API_URL}{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response: httpx.Response
            if method.upper() == "GET":
                response = await client.get(url, **kwargs)
            elif method.upper() == "POST":
                response = await client.post(url, **kwargs)
            elif method.upper() == "PUT":
                response = await client.put(url, **kwargs)
            elif method.upper() == "DELETE":
                response = await client.delete(url, **kwargs)
            else:
                logger.error(f"Неподдерживаемый HTTP метод: {method}")
                return False, None, f"Неподдерживаемый метод: {method}"

            if response.status_code == 200:
                data = response.json()
                logger.info(f"API запрос успешен: {method} {endpoint}")
                return True, data, None
            else:
                error_msg = f"API вернул код {response.status_code}: {response.text}"
                logger.warning(error_msg)
                return False, None, error_msg

    except httpx.TimeoutException:
        error_msg = "Превышено время ожидания ответа от сервера"
        logger.error(f"Timeout: {method} {endpoint}")
        return False, None, error_msg

    except Exception as e:
        error_msg = f"Ошибка запроса: {str(e)}"
        logger.error(f"Ошибка API: {method} {endpoint} - {e}")
        return False, None, error_msg


# ============================================================================
# ПОЛУЧЕНИЕ СТАТИСТИКИ ПОЛЬЗОВАТЕЛЯ
# ============================================================================

# Получение статистики пользователя из API
# Возвращает (success, stats, error)
async def get_user_stats(telegram_id: int) -> Tuple[bool, Optional[Dict], Optional[str]]:
    success, data, error = await api_request("GET", f"/users/{telegram_id}/stats")

    if not success:
        logger.error(f"Не удалось получить статистику пользователя {telegram_id}: {error}")

    return success, data, error


# ============================================================================
# ПРОВЕРКА ЛИМИТОВ ЗАГРУЗКИ
# ============================================================================

# Проверка лимитов загрузки контента
# Возвращает (can_upload, error_message, keyboard)
async def check_upload_limits(
        telegram_id: int,
        content_type: str
) -> Tuple[bool, str, List[List[InlineKeyboardButton]]]:
    # Получаем конфигурацию типа контента
    config = CONTENT_CONFIG.get(content_type)
    if not config:
        logger.error(f"Неизвестный тип контента: {content_type}")
        return False, Messages.ERROR_DATA, []

    # Получаем статистику пользователя
    success, stats, error = await get_user_stats(telegram_id)

    if not success:
        logger.error(f"Ошибка получения статистики для проверки лимитов: {error}")
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")]]
        return False, Messages.ERROR_CONNECTION, keyboard

    # Извлекаем данные о лимитах
    kb_storage = stats.get("kb_storage", {})
    kb_daily = stats.get("kb_daily", {})
    subscription_tier = stats.get("subscription_tier", "free")

    storage_key = config["storage_key"]
    daily_key = config["daily_key"]

    storage_value = kb_storage.get(storage_key, "0/0")
    daily_value = kb_daily.get(daily_key, "0/0")

    # Проверяем хранилище (пропускаем если есть ∞)
    if "∞" not in storage_value:
        try:
            storage_current, storage_limit = storage_value.split("/")
            storage_current = float(storage_current)
            storage_limit = float(storage_limit)

            if storage_current >= storage_limit:
                error_text = Messages.LIMIT_STORAGE_EXCEEDED.format(
                    content_type=config["title_genitive"],
                    current=storage_current,
                    limit=storage_limit,
                    unit=config["unit"]
                )
                error_text += "\n\n"

                keyboard = []

                if subscription_tier not in ["ultra", "admin"]:
                    error_text += Messages.UPGRADE_PROMPT
                    keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
                else:
                    error_text += Messages.MAX_TIER_INFO.format(content_type=config["title_plural_lower"])

                keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")])

                logger.info(f"Пользователь {telegram_id} превысил лимит хранилища {content_type}")
                return False, error_text, keyboard

        except ValueError as e:
            logger.error(f"Ошибка парсинга лимита хранилища {storage_value}: {e}")

    # Проверяем дневной лимит (пропускаем если есть ∞)
    if "∞" not in daily_value:
        try:
            daily_current, daily_limit = daily_value.split("/")
            daily_current = float(daily_current)
            daily_limit = float(daily_limit)

            if daily_current >= daily_limit:
                error_text = Messages.LIMIT_DAILY_EXCEEDED.format(
                    content_type=config["title_genitive"],
                    current=daily_current,
                    limit=daily_limit,
                    unit=config["unit"]
                )
                error_text += "\n\n"

                keyboard = []

                if subscription_tier not in ["ultra", "admin"]:
                    error_text += Messages.UPGRADE_PROMPT
                    keyboard.append([InlineKeyboardButton("⭐ Смотреть подписки", callback_data="subscriptions")])
                else:
                    error_text += Messages.DAILY_RESET_INFO

                keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="exit_upload")])

                logger.info(f"Пользователь {telegram_id} превысил дневной лимит {content_type}")
                return False, error_text, keyboard

        except ValueError as e:
            logger.error(f"Ошибка парсинга дневного лимита {daily_value}: {e}")

    logger.info(f"Проверка лимитов {content_type} для пользователя {telegram_id}: OK")
    return True, "", []


# ============================================================================
# ВАЛИДАЦИЯ ФАЙЛОВ
# ============================================================================

# Валидатор файлов
class FileValidator:
    # Разрешённые расширения для каждого типа
    ALLOWED_EXTENSIONS = {
        "file": ['.txt', '.pdf', '.docx'],
        "photo": ['.jpg', '.jpeg', '.png'],
    }

    # MIME типы
    MIME_TYPES = {
        'txt': 'text/plain',
        'pdf': 'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
    }

    @classmethod
    def validate_file(
            cls,
            filename: str,
            file_size: int,
            content_type: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        # Валидация файла
        # Возвращает (is_valid, error_message, mime_type)

        # Проверка расширения
        file_extension = os.path.splitext(filename)[1].lower()

        allowed = cls.ALLOWED_EXTENSIONS.get(content_type, [])

        if file_extension not in allowed:
            error = f"⚠️ Неподдерживаемый формат файла: {file_extension}\n\n"
            error += f"✅ Поддерживаемые форматы: {', '.join(allowed).upper()}"
            logger.warning(f"Отклонён файл с расширением {file_extension}")
            return False, error, None

        # Проверка размера
        if file_size > Limits.MAX_FILE_SIZE_BYTES:
            size_mb = file_size / (1024 * 1024)
            error = f"⚠️ Файл слишком большой!\n\n"
            error += f"Размер: {size_mb:.2f} MB\n"
            error += f"Максимум: {Limits.MAX_FILE_SIZE_MB} MB"
            logger.warning(f"Отклонён файл размером {size_mb:.2f} MB")
            return False, error, None

        # Определяем MIME type
        extension = file_extension[1:]
        mime_type = cls.MIME_TYPES.get(extension)

        if not mime_type:
            error = f"⚠️ Не удалось определить тип файла: {filename}"
            logger.error(f"Неизвестный MIME type для расширения {extension}")
            return False, error, None

        logger.info(f"Файл {filename} прошёл валидацию")
        return True, None, mime_type


# ============================================================================
# ФАБРИКА КНОПОК
# ============================================================================

# Фабрика для создания стандартных кнопок
class ButtonFactory:

    @staticmethod
    def back_to_main() -> InlineKeyboardButton:
        # Кнопка возврата в главное меню
        return InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")

    @staticmethod
    def back_button(callback_data: str) -> InlineKeyboardButton:
        # Кнопка "Назад"
        return InlineKeyboardButton("◀️ Назад", callback_data=callback_data)

    @staticmethod
    def upload_more(content_type: str) -> InlineKeyboardButton:
        # Кнопка "Загрузить ещё"
        config = CONTENT_CONFIG[content_type]
        return InlineKeyboardButton(
            f"📤 Загрузить ещё {config['title_plural_lower']}",
            callback_data=config['callbacks']['upload']
        )

    @staticmethod
    def view_list(content_type: str) -> InlineKeyboardButton:
        # Кнопка "Мои [тип контента]"
        config = CONTENT_CONFIG[content_type]
        return InlineKeyboardButton(
            f"{config['icon']} Мои {config['title_plural_lower']}",
            callback_data=config['callbacks']['my_list']
        )

    @staticmethod
    def success_keyboard(content_type: str) -> List[List[InlineKeyboardButton]]:
        # Клавиатура после успешной загрузки
        return [
            [ButtonFactory.upload_more(content_type), ButtonFactory.view_list(content_type)],
            [ButtonFactory.back_to_main()]
        ]


# ============================================================================
# УМНОЕ РЕДАКТИРОВАНИЕ СООБЩЕНИЙ
# ============================================================================

# Умное редактирование сообщения (обрабатывает случай с фото)
async def safe_message_edit(
        query,
        context,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: Optional[str] = None
) -> None:
    user_id = query.from_user.id

    try:
        # Если сообщение с фото — удаляем и отправляем новое
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(
                user_id,
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            logger.info(f"Удалено сообщение с фото, отправлено новое для пользователя {user_id}")
        else:
            # Обычное текстовое сообщение — редактируем
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            logger.debug(f"Отредактировано сообщение для пользователя {user_id}")

    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения: {e}")
        # Fallback: отправляем новое сообщение
        try:
            await context.bot.send_message(
                user_id,
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except Exception as e2:
            logger.error(f"Ошибка отправки fallback сообщения: {e2}")


# ============================================================================
# ОБЩИЕ FALLBACKS ДЛЯ CONVERSATIONHANDLER
# ============================================================================

# Общие fallbacks для всех ConversationHandler
COMMON_FALLBACKS = [
    "exit_upload",
    "upload_file",
    "knowledge_base",
    "back_to_main"
]


# ============================================================================
# БУФЕРИЗАЦИЯ ЗАГРУЗОК
# ============================================================================

# Класс для буферизации загрузок (фото и файлы)
# Собирает элементы в буфер и отправляет пакетом после таймаута или достижения лимита
class BufferedUploader:

    def __init__(self, content_type: str):
        # Инициализация буфера
        self.content_type = content_type
        self.config = CONTENT_CONFIG[content_type]
        self.max_items = Limits.BUFFER_MAX_ITEMS
        self.timeout = Limits.BUFFER_TIMEOUT_SEC

        logger.info(f"Инициализирован BufferedUploader для {content_type}")

    def get_buffer_key(self) -> str:
        # Ключ для хранения буфера в context.user_data
        return f"{self.content_type}_buffer"

    def get_waiting_key(self) -> str:
        # Ключ для флага ожидания в context.user_data
        return f"waiting_for_{self.content_type}s"

    def get_status_msg_key(self) -> str:
        # Ключ для ID статусного сообщения
        return f"{self.content_type}_status_msg_id"

    def get_timer_key(self) -> str:
        # Ключ для таймера в context.user_data
        return f"{self.content_type}_timer"

    async def start_upload_mode(
            self,
            update: Update,
            context
    ) -> None:
        # Включение режима ожидания загрузки
        user_id = update.effective_user.id

        # Включаем флаг ожидания
        context.user_data[self.get_waiting_key()] = True

        # Инициализируем буфер
        context.user_data[self.get_buffer_key()] = []

        logger.info(f"Включен режим загрузки {self.content_type} для пользователя {user_id}")

    def stop_upload_mode(self, context) -> None:
        # Выключение режима ожидания загрузки

        # Выключаем флаг
        context.user_data[self.get_waiting_key()] = False

        # Очищаем буфер
        context.user_data[self.get_buffer_key()] = []

        # Отменяем таймер если есть
        timer_key = self.get_timer_key()
        if timer_key in context.user_data and context.user_data[timer_key]:
            context.user_data[timer_key].cancel()
            context.user_data[timer_key] = None

        logger.info(f"Выключен режим загрузки {self.content_type}")

    def is_waiting(self, context) -> bool:
        # Проверка, ждём ли мы этот тип контента
        return context.user_data.get(self.get_waiting_key(), False)

    async def add_to_buffer(
            self,
            update: Update,
            context,
            item_data: dict
    ) -> None:
        # Добавление элемента в буфер

        user = update.effective_user
        buffer_key = self.get_buffer_key()

        # Добавляем в буфер
        if buffer_key not in context.user_data:
            context.user_data[buffer_key] = []

        context.user_data[buffer_key].append(item_data)

        count = len(context.user_data[buffer_key])

        logger.info(f"Добавлен {self.content_type} в буфер пользователя {user.id}. Всего в буфере: {count}")

        # Обновляем статусное сообщение
        status_msg_key = self.get_status_msg_key()

        if count == 1:
            # Первый элемент — создаём статусное сообщение
            status_msg = await update.message.reply_text(
                f"⏳ Получено {self.config['title_genitive']}: {count}"
            )
            context.user_data[status_msg_key] = status_msg.message_id
        else:
            # Обновляем существующее
            try:
                await context.bot.edit_message_text(
                    chat_id=user.id,
                    message_id=context.user_data[status_msg_key],
                    text=f"⏳ Получено {self.config['title_genitive']}: {count}"
                )
            except Exception as e:
                logger.warning(f"Не удалось обновить статусное сообщение: {e}")

        # Проверяем достигнут ли лимит
        if count >= self.max_items:
            logger.info(f"Достигнут лимит буфера ({self.max_items}), отправляем немедленно")
            await self._finish_upload(update, context)
            return

        # Отменяем старый таймер
        timer_key = self.get_timer_key()
        if timer_key in context.user_data and context.user_data[timer_key]:
            context.user_data[timer_key].cancel()

        # Создаём новый таймер
        async def timer_callback():
            await asyncio.sleep(self.timeout)
            await self._finish_upload(update, context)

        context.user_data[timer_key] = asyncio.create_task(timer_callback())

        logger.debug(f"Установлен таймер на {self.timeout} секунд")

    async def _finish_upload(
            self,
            update: Update,
            context
    ) -> None:
        # Завершение загрузки и отправка буфера в API

        user = update.effective_user if update.message else update.effective_user
        buffer_key = self.get_buffer_key()
        status_msg_key = self.get_status_msg_key()

        items = context.user_data.get(buffer_key, [])
        total = len(items)

        if total == 0:
            logger.warning(f"Попытка завершить загрузку с пустым буфером")
            return

        logger.info(f"Начинается отправка {total} {self.config['title_genitive']} в API")

        # Обновляем статусное сообщение
        try:
            await context.bot.edit_message_text(
                chat_id=user.id,
                message_id=context.user_data[status_msg_key],
                text=f"⏳ Отправляю {total} {self.config['title_genitive']} на обработку..."
            )
        except Exception as e:
            logger.warning(f"Не удалось обновить статусное сообщение: {e}")

        # Формируем запрос к API
        payload = {
            "telegram_id": user.id,
            self.content_type + "s": items  # "photos" или "files"
        }

        # Определяем таймаут в зависимости от типа
        timeout = Limits.FILE_UPLOAD_TIMEOUT_SEC if self.content_type == "file" else Limits.API_REQUEST_TIMEOUT_SEC

        # Отправляем в API
        success, data, error = await api_request(
            "POST",
            self.config["api_endpoint"],
            timeout=timeout,
            json=payload
        )

        if success:
            logger.info(f"Успешно отправлено {total} {self.config['title_genitive']} для пользователя {user.id}")

            # Формируем клавиатуру
            keyboard = ButtonFactory.success_keyboard(self.content_type)

            # Обновляем сообщение
            try:
                await context.bot.edit_message_text(
                    chat_id=user.id,
                    message_id=context.user_data[status_msg_key],
                    text=f"✅ {total} {self.config['title_genitive']} отправлено на обработку!\n\nУведомление придёт после распознавания",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logger.error(f"Ошибка обновления финального сообщения: {e}")
        else:
            logger.error(f"Ошибка отправки {self.content_type} в API: {error}")
            await context.bot.send_message(
                user.id,
                Messages.ERROR_UPLOAD
            )

        # Выключаем режим ожидания
        self.stop_upload_mode(context)


# ============================================================================
# ГЛОБАЛЬНЫЕ ЭКЗЕМПЛЯРЫ UPLOADERS
# ============================================================================

# Создаём глобальные экземпляры для использования в handlers
photo_uploader = BufferedUploader("photo")
file_uploader = BufferedUploader("file")


# ============================================================================
# СЕРВИС УВЕДОМЛЕНИЙ
# ============================================================================

# Сервис для отправки уведомлений пользователям
class NotificationService:

    @staticmethod
    async def send_message(
            telegram_id: int,
            text: str,
            keyboard: Optional[List[List[dict]]] = None
    ) -> None:
        # Отправка сообщения пользователю
        # keyboard: список списков с dict вида {"text": "...", "callback_data": "..."}

        bot_token = settings.TELEGRAM_TOKEN

        try:
            payload = {
                "chat_id": telegram_id,
                "text": text,
                "parse_mode": "HTML"
            }

            # Добавляем клавиатуру если есть
            if keyboard:
                payload["reply_markup"] = {
                    "inline_keyboard": keyboard
                }

            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json=payload
                )

            logger.info(f"Отправлено уведомление пользователю {telegram_id}")

        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {telegram_id}: {e}")

    @staticmethod
    async def send_photo(
            telegram_id: int,
            photo_bytes: bytes,
            caption: str,
            keyboard: Optional[List[List[dict]]] = None
    ) -> None:
        # Отправка фото с подписью пользователю

        bot_token = settings.TELEGRAM_TOKEN

        try:
            # Формируем multipart request
            files = {
                'photo': ('photo.jpg', photo_bytes, 'image/jpeg')
            }

            data = {
                'chat_id': str(telegram_id),
                'caption': caption,
                'parse_mode': 'HTML'
            }

            if keyboard:
                import json
                data['reply_markup'] = json.dumps({"inline_keyboard": keyboard})

            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                    files=files,
                    data=data
                )

            logger.info(f"Отправлено фото пользователю {telegram_id}")

        except Exception as e:
            logger.error(f"Ошибка отправки фото пользователю {telegram_id}: {e}")

    @staticmethod
    async def send_success(
            telegram_id: int,
            content_type: str,
            **kwargs
    ) -> None:
        # Отправка уведомления об успешной обработке
        # kwargs: параметры для шаблона (filename, text, count и т.д.)

        config = CONTENT_CONFIG[content_type]

        # Формируем текст из шаблона
        template_key = content_type

        # Для фото проверяем длину текста
        if content_type == "photo":
            text = kwargs.get("text", "")
            if len(text) > 900:
                template_key = "photo_truncated"
                kwargs["text"] = text[:900]

        template = NOTIFICATION_TEMPLATES.get(template_key, "✅ Обработка завершена!")
        message_text = template.format(**kwargs)

        # Формируем клавиатуру
        keyboard = [
            [
                {"text": f"📤 Загрузить ещё {config['title_plural_lower']}",
                 "callback_data": config['callbacks']['upload']},
                {"text": f"{config['icon']} Мои {config['title_plural_lower']}",
                 "callback_data": config['callbacks']['my_list']}
            ],
            [
                {"text": "🏠 Главное меню", "callback_data": "back_to_main"}
            ]
        ]

        # Для фото отправляем с изображением
        if content_type == "photo" and "photo_bytes" in kwargs:
            await NotificationService.send_photo(
                telegram_id,
                kwargs["photo_bytes"],
                message_text,
                keyboard
            )
        else:
            await NotificationService.send_message(
                telegram_id,
                message_text,
                keyboard
            )


# ============================================================================
# ПАГИНАЦИЯ ДОКУМЕНТОВ
# ============================================================================

# Универсальная пагинация списка документов
async def paginate_documents(
        documents: List[dict],
        content_type: str,
        context,
        query,
        user_id: int
) -> None:
    # Пагинация документов с автоматическим форматированием

    config = CONTENT_CONFIG[content_type]

    # Разбиваем на страницы
    items_per_page = Limits.PAGINATION_ITEMS
    total_pages = (len(documents) + items_per_page - 1) // items_per_page

    # Формируем страницы
    for page in range(total_pages):
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(documents))
        page_docs = documents[start_idx:end_idx]

        is_first_page = (page == 0)
        is_last_page = (page == total_pages - 1)

        # Формируем текст страницы
        if total_pages > 1:
            files_text = f"{config['icon']} Мои {config['title_plural_lower']} ({len(documents)}) — страница {page + 1}/{total_pages}\n\n"
        else:
            files_text = f"{config['icon']} Мои {config['title_plural_lower']} ({len(documents)}):\n\n"

        keyboard = []

        for doc in page_docs:
            # Превью текста (первые 100 символов)
            preview = doc.get("extracted_text", "[Текст не распознан]")[:Limits.TEXT_PREVIEW_LENGTH]
            if len(doc.get("extracted_text", "")) > Limits.TEXT_PREVIEW_LENGTH:
                preview += "..."

            datetime_str = doc['upload_date'][:16].replace('T', ' ')

            # Формируем строку документа в зависимости от типа
            if config.get("has_link"):
                # Видео со ссылкой
                files_text += f"{config['icon']} Видео {doc['id']}: <a href='{doc['file_url']}'>{doc['filename']}</a>\n"
            else:
                # Остальные типы
                if content_type == "file":
                    files_text += f"{config['icon']} {doc['filename']}\n"
                else:
                    files_text += f"{config['icon']} {config['title']} {doc['id']}\n"

            files_text += f"<blockquote>{preview}</blockquote>\n"
            files_text += f"📅 {datetime_str}\n\n"

            # Кнопка "Полный текст"
            doc_buttons = [
                InlineKeyboardButton(f"👁 Полный текст {doc['id']}", callback_data=f"view_doc_{doc['id']}")
            ]

            # Кнопка "Показать фото" если это фото
            if config.get("has_preview_button"):
                doc_buttons.append(
                    InlineKeyboardButton(f"🖼 Показать фото {doc['id']}", callback_data=f"show_photo_{doc['id']}")
                )

            keyboard.append(doc_buttons)

            # Кнопка удаления на отдельной строке
            keyboard.append([
                InlineKeyboardButton(f"🗑 Удалить {doc['id']}", callback_data=f"delete_doc_{doc['id']}")
            ])

        # Кнопки навигации только на последней странице
        if is_last_page:
            keyboard.append([InlineKeyboardButton(f"📤 Загрузить {config['title_plural_lower']}",
                                                  callback_data=config['callbacks']['upload'])])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="my_files")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Первую страницу редактируем, остальные отправляем новыми
        if is_first_page:
            # Проверяем тип сообщения
            if query.message.photo:
                await query.message.delete()
                await context.bot.send_message(
                    user_id,
                    files_text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            else:
                await query.edit_message_text(
                    files_text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
        else:
            await context.bot.send_message(
                user_id,
                files_text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=True
            )

    logger.info(
        f"Отображено {len(documents)} {config['title_genitive']} на {total_pages} страницах для пользователя {user_id}")