"""
Обработчики команд Telegram бота.

Модули:
- common: Общие handlers (главное меню, база знаний)
- text: Загрузка текста
- video: Загрузка видео
- photo: Загрузка фото
- file: Загрузка файлов
- documents: Просмотр и управление документами
"""

from .common_handlers import (
    knowledge_base_menu,
    upload_file_menu,
    exit_upload
)

from .text_handlers import (
    upload_text,
    handle_text_upload,
    handle_wrong_media_in_text,
    WAITING_TEXT
)

from .video_handlers import (
    upload_video,
    handle_video_upload,
    handle_wrong_media_in_video,
    WAITING_VIDEO
)

from .photo_handlers import (
    upload_photo,
    global_photo_handler
)

from .file_handlers import (
    upload_file_doc,
    reject_text_when_waiting_files,
    global_document_handler
)

from .document_handlers import (
    my_files,
    my_texts,
    my_videos,
    my_photos,
    my_files_docs,
    view_document,
    show_photo_original,
    delete_document
)

__all__ = [
    # Common
    'knowledge_base_menu',
    'upload_file_menu',
    'exit_upload',

    # Text
    'upload_text',
    'handle_text_upload',
    'handle_wrong_media_in_text',
    'WAITING_TEXT',

    # Video
    'upload_video',
    'handle_video_upload',
    'handle_wrong_media_in_video',
    'WAITING_VIDEO',

    # Photo
    'upload_photo',
    'global_photo_handler',

    # File
    'upload_file_doc',
    'reject_text_when_waiting_files',
    'global_document_handler',

    # Documents
    'my_files',
    'my_texts',
    'my_videos',
    'my_photos',
    'my_files_docs',
    'view_document',
    'show_photo_original',
    'delete_document',
]