# Кастомные настройки для отображения задач в Flower

# Приоритеты задач (для фильтрации)
TASK_PRIORITIES = {
    0: {
        'name': 'Admin',
        'color': '#dc3545',  # Красный
        'icon': '🏴‍☠️'
    },
    1: {
        'name': 'Ultra',
        'color': '#ffc107',  # Золотой
        'icon': '👑'
    },
    2: {
        'name': 'Premium',
        'color': '#17a2b8',  # Голубой
        'icon': '💎'
    },
    3: {
        'name': 'Free',
        'color': '#6c757d',  # Серый
        'icon': '🆓'
    },
    4: {
        'name': 'Basic',
        'color': '#28a745',  # Зелёный
        'icon': '📦'
    }
}

# Типы задач
TASK_TYPES = {
    'process_video': {
        'name': 'Обработка видео',
        'icon': '🎥',
        'description': 'Скачивание и транскрибация видео'
    },
    'process_photo_ocr': {
        'name': 'OCR фото',
        'icon': '🖼',
        'description': 'Распознавание текста на фото'
    },
    'process_file': {
        'name': 'Обработка файла',
        'icon': '📄',
        'description': 'Извлечение текста из документов'
    },
    'refresh_iam_token': {
        'name': 'Обновление SpeechKit токена',
        'icon': '🔑',
        'description': 'Обновление IAM токена Yandex SpeechKit'
    },
    'refresh_vision_iam_token': {
        'name': 'Обновление Vision токена',
        'icon': '👁',
        'description': 'Обновление IAM токена Yandex Vision'
    }
}


# Форматирование аргументов задач для читаемости
def format_task_args(task_name, args, kwargs):
    # Форматирует аргументы задачи для отображения в Flower

    if task_name == 'process_video':
        # args: [video_url, document_id]
        if len(args) >= 2:
            return f"URL: {args[0][:50]}..., Doc ID: {args[1]}"

    elif task_name == 'process_photo_ocr':
        # args: [document_id, s3_key]
        if len(args) >= 2:
            return f"Doc ID: {args[0]}, S3: {args[1]}"

    elif task_name == 'process_file':
        # args: [document_id, s3_key, mime_type]
        if len(args) >= 3:
            return f"Doc ID: {args[0]}, Type: {args[2]}"

    # По умолчанию
    return f"Args: {args}, Kwargs: {kwargs}"