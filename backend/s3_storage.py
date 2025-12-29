# Работа с объектным хранилищем S3 и Celery задачи

from backend.celery_app import celery_app
import boto3
import yt_dlp
import ffmpeg
import tempfile
import os
import requests
import time
import shutil
import httpx
import asyncio
from utils.iam_manager import get_new_iam_token, get_new_vision_iam_token
import io
from pdf2image import convert_from_bytes
from docx import Document
from shared.config import settings, DocumentStatus, NOTIFICATION_TEMPLATES, S3_BASE_URL
from typing import Optional, Tuple
import logging
import base64
from shared.notifications import NotificationService

# Настройка логирования
logger = logging.getLogger(__name__)


# ============================================================================
# ПЕРИОДИЧЕСКИЕ ЗАДАЧИ ОБНОВЛЕНИЯ ТОКЕНОВ
# ============================================================================

# Обновление токена SpeechKit каждые 11 часов
@celery_app.task
def refresh_iam_token():
    get_new_iam_token()


# Обновление токена Vision API каждые 11 часов
@celery_app.task
def refresh_vision_iam_token():
    get_new_vision_iam_token()


# ============================================================================
# НАСТРОЙКА S3 CLIENT
# ============================================================================

# Клиент для работы с Yandex Object Storage
s3_client = boto3.client(
    's3',
    endpoint_url='https://storage.yandexcloud.net',
    aws_access_key_id=settings.YANDEX_ACCESS_KEY,
    aws_secret_access_key=settings.YANDEX_SECRET_KEY,
    config=boto3.session.Config(
        proxies={}  # Отключение проксирования
    )
)

BUCKET_NAME = settings.YC_BUCKET_NAME


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

# Обновление статуса документа через API
def update_document_status(
        document_id: int,
        status: str,
        error: Optional[str] = None,
        transcription: Optional[str] = None
) -> None:
    api_url = settings.API_URL

    payload = {
        "status": status,
        "error": error,
        "transcription": transcription
    }

    try:
        response = httpx.put(
            f"{api_url}/kb/documents/{document_id}/status",
            json=payload,
            timeout=30.0
        )
        if response.status_code != 200:
            logger.warning(f"Ошибка обновления статуса документа {document_id}: {response.text}")
    except Exception as e:
        logger.error(f"Не удалось обновить статус документа {document_id}: {e}")


async def notify_user_success(
        telegram_id: int,
        content_type: str,
        **kwargs
) -> None:
    from shared.notifications import NotificationService

    await NotificationService.send_success(telegram_id, content_type, **kwargs)


# ============================================================================
# РАБОТА С S3
# ============================================================================

# Загрузка фото в S3
def upload_photo_to_s3(photo_base64: str, user_id: int, document_id: int) -> str:
    try:
        # Декодируем base64
        try:
            photo_bytes = base64.b64decode(photo_base64)
        except Exception as e:
            logger.error(f"Ошибка декодирования base64 для фото document_id={document_id}: {e}")
            raise ValueError(f"Invalid base64 data: {e}")

        # Формируем путь в S3
        s3_key = f"photos/user_{user_id}/photo_{document_id}.jpg"

        # Загружаем в S3
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=photo_bytes,
            ContentType='image/jpeg'
        )

        logger.info(f"Загружено фото в S3: {s3_key}")
        return s3_key

    except ValueError:
        # Пробрасываем ValueError дальше (это ошибка валидации base64)
        raise
    except Exception as e:
        logger.error(f"Ошибка загрузки фото в S3: {e}")
        raise


# Получение presigned URL для скачивания фото
def get_photo_presigned_url(s3_key: str, expiration: int = 3600) -> str:
    try:
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': BUCKET_NAME,
                'Key': s3_key
            },
            ExpiresIn=expiration
        )

        logger.info(f"Сгенерирован presigned URL для {s3_key}")
        return presigned_url

    except Exception as e:
        logger.error(f"Ошибка генерации presigned URL: {e}")
        raise


# Загрузка файла в S3
def upload_file_to_s3(file_base64: str, user_id: int, document_id: int, extension: str) -> str:
    try:
        # Декодируем base64
        try:
            file_bytes = base64.b64decode(file_base64)
        except Exception as e:
            logger.error(f"Ошибка декодирования base64 для файла document_id={document_id}: {e}")
            raise ValueError(f"Invalid base64 data: {e}")

        # Формируем путь в S3
        s3_key = f"files/user_{user_id}/document_{document_id}.{extension}"

        # Загружаем в S3
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=file_bytes
        )

        logger.info(f"Загружен файл в S3: {s3_key}")
        return s3_key

    except ValueError:
        # Пробрасываем ValueError дальше
        raise
    except Exception as e:
        logger.error(f"Ошибка загрузки файла в S3: {e}")
        raise


# Удаление объекта из S3 (универсальная функция)
def delete_from_s3(s3_key: str) -> bool:
    try:
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=s3_key)
        logger.info(f"Удалён объект из S3: {s3_key}")
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления объекта из S3 ({s3_key}): {e}")
        return False


# ============================================================================
# OCR И ОБРАБОТКА ИЗОБРАЖЕНИЙ
# ============================================================================

# OCR изображения через Yandex Vision
def recognize_text_yandex(image_bytes: bytes) -> str:
    try:
        vision_iam_token = settings.YANDEX_VISION_IAM_TOKEN
        folder_id = settings.YANDEX_FOLDER_ID

        headers = {
            'Authorization': f'Bearer {vision_iam_token}',
            'Content-Type': 'application/json'
        }

        # Конвертируем в base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        body = {
            "folderId": folder_id,
            "analyze_specs": [
                {
                    "content": image_base64,
                    "features": [
                        {
                            "type": "TEXT_DETECTION",
                            "text_detection_config": {
                                "language_codes": ["ru", "en"]
                            }
                        }
                    ]
                }
            ]
        }

        ocr_response = requests.post(
            'https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze',
            headers=headers,
            json=body
        )

        if ocr_response.status_code != 200:
            logger.warning(f"Ошибка Vision API: {ocr_response.text}")
            return ""

        # Парсим результат
        result = ocr_response.json()
        extracted_text = ""

        if 'results' in result and len(result['results']) > 0:
            text_annotation = result['results'][0].get('results', [])

            for item in text_annotation:
                if item.get('textDetection'):
                    pages = item['textDetection'].get('pages', [])
                    for page in pages:
                        blocks = page.get('blocks', [])
                        for block in blocks:
                            lines = block.get('lines', [])
                            for line in lines:
                                words = line.get('words', [])
                                line_text = ' '.join([word.get('text', '') for word in words])
                                extracted_text += line_text + '\n'

        return extracted_text.strip()

    except Exception as e:
        logger.error(f"Ошибка OCR: {e}")
        return ""


# ============================================================================
# ОБРАБОТКА ФАЙЛОВ
# ============================================================================

# Извлечение текста из TXT
def extract_text_from_txt(file_bytes: bytes) -> str:
    try:
        # Пробуем UTF-8
        try:
            text = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            # Пробуем CP1251 (кириллица Windows)
            text = file_bytes.decode('cp1251')

        logger.info("Текст извлечён из TXT файла")
        return text.strip()

    except Exception as e:
        logger.error(f"Ошибка чтения TXT: {e}")
        raise


# Извлечение текста из DOCX (текст + OCR картинок)
def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))

    # Извлекаем текст
    text_parts = [p.text for p in doc.paragraphs if p.text.strip()]

    # Извлекаем картинки и делаем OCR
    image_texts = []
    for rel in doc.part.rels.values():
        if "image" in rel.target_ref:
            image_data = rel.target_part.blob
            # OCR через Yandex Vision
            ocr_result = recognize_text_yandex(image_data)
            if ocr_result:
                image_texts.append(ocr_result)
            time.sleep(0.5)  # Rate limit

    # Объединяем
    all_text = "\n".join(text_parts)
    if image_texts:
        all_text += "\n\n=== ТЕКСТ ИЗ ИЗОБРАЖЕНИЙ ===\n" + "\n".join(image_texts)

    logger.info("Текст извлечён из DOCX файла")
    return all_text


# Извлечение текста из PDF через OCR
def extract_text_from_pdf_ocr(pdf_bytes: bytes) -> str:
    try:
        # Конвертируем PDF в изображения
        images = convert_from_bytes(pdf_bytes, dpi=300)

        vision_iam_token = settings.YANDEX_VISION_IAM_TOKEN
        folder_id = settings.YANDEX_FOLDER_ID

        headers = {
            'Authorization': f'Bearer {vision_iam_token}',
            'Content-Type': 'application/json'
        }

        all_text = []

        for i, image in enumerate(images):
            logger.info(f"Обработка страницы {i + 1}/{len(images)}...")

            # Конвертируем изображение в JPEG
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='JPEG', quality=95)
            img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

            # OCR запрос
            body = {
                "folderId": folder_id,
                "analyze_specs": [
                    {
                        "content": img_base64,
                        "features": [
                            {
                                "type": "TEXT_DETECTION",
                                "text_detection_config": {
                                    "language_codes": ["ru", "en"]
                                }
                            }
                        ]
                    }
                ]
            }

            ocr_response = requests.post(
                'https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze',
                headers=headers,
                json=body
            )

            if ocr_response.status_code != 200:
                logger.warning(f"Ошибка OCR страницы {i + 1}: {ocr_response.text}")
                continue

            # Парсим результат
            result = ocr_response.json()
            page_text = ""

            if 'results' in result and len(result['results']) > 0:
                text_annotation = result['results'][0].get('results', [])

                for item in text_annotation:
                    if item.get('textDetection'):
                        pages = item['textDetection'].get('pages', [])
                        for page in pages:
                            blocks = page.get('blocks', [])
                            for block in blocks:
                                lines = block.get('lines', [])
                                for line in lines:
                                    words = line.get('words', [])
                                    line_text = ' '.join([word.get('text', '') for word in words])
                                    page_text += line_text + '\n'

            all_text.append(page_text)

            # Пауза между запросами
            time.sleep(0.5)

        final_text = '\n\n'.join(all_text).strip()

        if not final_text:
            final_text = "[Текст не распознан]"

        logger.info("Текст извлечён из PDF файла")
        return final_text

    except Exception as e:
        logger.error(f"Ошибка извлечения текста из PDF: {e}")
        raise


# ============================================================================
# CELERY ЗАДАЧИ
# ============================================================================

# Обработка видео (скачивание, транскрибация)
@celery_app.task(bind=True, max_retries=3)
def process_video(self, video_url: str, document_id: int):
    temp_dir = None

    try:
        update_document_status(document_id, DocumentStatus.PROCESSING)

        temp_dir = tempfile.mkdtemp()
        video_path = os.path.join(temp_dir, f"video_{document_id}.mp4")
        audio_path = os.path.join(temp_dir, f"audio_{document_id}.mp3")

        # Скачиваем видео
        logger.info(f"Скачивание видео {document_id}...")
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': video_path,
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # Извлекаем аудио
        logger.info(f"Извлечение аудио из видео {document_id}...")
        ffmpeg.input(video_path).output(
            audio_path,
            acodec='libmp3lame',
            audio_bitrate='128k',
            ac=1,
            ar='16000'
        ).overwrite_output().run(quiet=True)

        # Загружаем аудио в S3
        audio_filename = f"audio_{document_id}.mp3"
        s3_client.upload_file(audio_path, BUCKET_NAME, audio_filename)
        audio_url = f"https://storage.yandexcloud.net/{BUCKET_NAME}/{audio_filename}"

        logger.info(f"Аудио загружено в S3: {audio_filename}")

        # Отправляем в Yandex SpeechKit
        folder_id = settings.YANDEX_FOLDER_ID
        iam_token = settings.YANDEX_IAM_TOKEN

        headers = {
            'Authorization': f'Bearer {iam_token}',
            'Content-Type': 'application/json'
        }

        body = {
            "config": {
                "specification": {
                    "languageCode": "auto",
                    "model": "general",
                    "audioEncoding": "MP3",
                    "folderId": folder_id
                }
            },
            "audio": {
                "uri": audio_url
            }
        }

        response = requests.post(
            f'https://transcribe.api.cloud.yandex.net/speech/stt/v2/longRunningRecognize',
            headers=headers,
            json=body
        )

        if response.status_code != 200:
            raise Exception(f"Ошибка SpeechKit: {response.text}")

        operation_id = response.json()['id']
        logger.info(f"Запущена транскрибация видео {document_id}, operation_id: {operation_id}")

        # Ждём результат
        operation_url = f'https://operation.api.cloud.yandex.net/operations/{operation_id}'

        while True:
            time.sleep(10)

            op_response = requests.get(operation_url, headers=headers)
            op_data = op_response.json()

            if op_data.get('done'):
                if 'error' in op_data:
                    raise Exception(f"Ошибка транскрибации: {op_data['error']}")

                # Получаем транскрипцию
                chunks = op_data['response']['chunks']
                transcription = ' '.join([chunk['alternatives'][0]['text'] for chunk in chunks])

                # Сохраняем в БД
                update_document_status(document_id, DocumentStatus.COMPLETED, transcription=transcription)

                # Получаем данные для уведомления
                api_url = settings.API_URL
                doc_response = httpx.get(f"{api_url}/kb/documents/{document_id}/info")

                if doc_response.status_code == 200:
                    user_data = doc_response.json()
                    telegram_id = user_data['telegram_id']
                    filename = user_data['filename']

                    # Отправляем уведомление
                    asyncio.run(notify_user_success(
                        telegram_id,
                        "video",
                        filename=filename
                    ))

                # Удаляем аудио из S3
                delete_from_s3(audio_filename)

                break

        # Удаляем временные файлы
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        logger.info(f"Видео {document_id} успешно обработано")
        return {"status": "success", "document_id": document_id}

    except Exception as e:
        logger.error(f"Ошибка обработки видео {document_id}: {e}")
        update_document_status(document_id, DocumentStatus.FAILED, str(e))

        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        raise


# Обработка фото через OCR
@celery_app.task(bind=True, max_retries=3)
def process_photo_ocr(self, document_id: int, s3_key: str):
    try:
        update_document_status(document_id, DocumentStatus.PROCESSING)

        # Скачиваем фото из S3
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        photo_bytes = response['Body'].read()

        logger.info(f"Начало OCR для фото {document_id}")

        # Конвертируем в base64 для Yandex Vision
        photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')

        # Отправляем в Yandex Vision API
        vision_iam_token = settings.YANDEX_VISION_IAM_TOKEN
        folder_id = settings.YANDEX_FOLDER_ID

        headers = {
            'Authorization': f'Bearer {vision_iam_token}',
            'Content-Type': 'application/json'
        }

        body = {
            "folderId": folder_id,
            "analyze_specs": [
                {
                    "content": photo_base64,
                    "features": [
                        {
                            "type": "TEXT_DETECTION",
                            "text_detection_config": {
                                "language_codes": ["ru", "en"]
                            }
                        }
                    ]
                }
            ]
        }

        ocr_response = requests.post(
            'https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze',
            headers=headers,
            json=body
        )

        if ocr_response.status_code != 200:
            raise Exception(f"Ошибка Yandex Vision: {ocr_response.text}")

        # Парсим результат
        result = ocr_response.json()

        extracted_text = ""

        if 'results' in result and len(result['results']) > 0:
            text_annotation = result['results'][0].get('results', [])

            for item in text_annotation:
                if item.get('textDetection'):
                    pages = item['textDetection'].get('pages', [])
                    for page in pages:
                        blocks = page.get('blocks', [])
                        for block in blocks:
                            lines = block.get('lines', [])
                            for line in lines:
                                words = line.get('words', [])
                                line_text = ' '.join([word.get('text', '') for word in words])
                                extracted_text += line_text + '\n'

        if not extracted_text.strip():
            extracted_text = "[Текст не распознан]"

        # Сохраняем результат
        update_document_status(document_id, DocumentStatus.COMPLETED, transcription=extracted_text.strip())

        # Получаем данные для уведомления
        api_url = settings.API_URL
        doc_response = httpx.get(f"{api_url}/kb/documents/{document_id}/info")

        if doc_response.status_code == 200:
            user_data = doc_response.json()
            telegram_id = user_data['telegram_id']

            # Отправляем уведомление с фото
            asyncio.run(notify_user_success(
                telegram_id,
                "photo",
                text=extracted_text.strip(),
                photo_bytes=photo_bytes
            ))

        logger.info(f"Фото {document_id} успешно обработано")
        return {"status": "success", "document_id": document_id}

    except Exception as e:
        logger.error(f"Ошибка обработки фото {document_id}: {e}")
        update_document_status(document_id, DocumentStatus.FAILED, str(e))
        raise


# Обработка файлов (TXT, PDF, DOCX)
@celery_app.task(bind=True, max_retries=3)
def process_file(self, document_id: int, s3_key: str, mime_type: str):
    try:
        update_document_status(document_id, DocumentStatus.PROCESSING)

        # Скачиваем файл из S3
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        file_bytes = response['Body'].read()

        # Обрабатываем в зависимости от типа
        if mime_type == "text/plain":
            logger.info(f"Обработка TXT файла {document_id}...")
            extracted_text = extract_text_from_txt(file_bytes)

        elif mime_type == "application/pdf":
            logger.info(f"Обработка PDF файла {document_id}...")
            extracted_text = extract_text_from_pdf_ocr(file_bytes)

        elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            logger.info(f"Обработка DOCX файла {document_id}...")
            extracted_text = extract_text_from_docx(file_bytes)

        else:
            raise Exception(f"Неподдерживаемый тип файла: {mime_type}")

        # Сохраняем результат
        update_document_status(document_id, DocumentStatus.COMPLETED, transcription=extracted_text)

        # Получаем данные для уведомления
        api_url = settings.API_URL
        doc_response = httpx.get(f"{api_url}/kb/documents/{document_id}/info")

        if doc_response.status_code == 200:
            user_data = doc_response.json()
            telegram_id = user_data['telegram_id']
            filename = user_data['filename']

            # Отправляем уведомление
            asyncio.run(notify_user_success(
                telegram_id,
                "file",
                filename=filename,
                count=len(extracted_text)
            ))

        logger.info(f"Файл {document_id} успешно обработан")
        return {"status": "success", "document_id": document_id}

    except Exception as e:
        logger.error(f"Ошибка обработки файла {document_id}: {e}")
        update_document_status(document_id, DocumentStatus.FAILED, str(e))
        raise