# Работа с объектным хранилищем S3

from celery_app import celery_app
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
from iam_manager import get_new_iam_token
import base64
import json
import io
import subprocess
from pdf2image import convert_from_bytes
from docx import Document
from dotenv import load_dotenv

load_dotenv()

# Периодическая задача обновления токена спич кита (каждые 11 часов)
@celery_app.task
def refresh_iam_token():
    get_new_iam_token()

# Периодическая задача обновления токена Vision (каждые 11 часов)
@celery_app.task
def refresh_vision_iam_token():
    from iam_manager import get_new_vision_iam_token
    get_new_vision_iam_token()


# Настройка S3
s3_client = boto3.client(
    's3',
    endpoint_url='https://storage.yandexcloud.net',
    aws_access_key_id=os.getenv('YANDEX_ACCESS_KEY'),
    aws_secret_access_key=os.getenv('YANDEX_SECRET_KEY'),
    config=boto3.session.Config(
        proxies={} # отключение проксирования
    )
)

BUCKET_NAME = os.getenv('YC_BUCKET_NAME')


# Обработка видео
@celery_app.task(bind=True, max_retries=3)
def process_video(self, video_url: str, document_id: int):
    temp_dir = None

    try:
        update_document_status(document_id, "processing")

        temp_dir = tempfile.mkdtemp()
        video_path = os.path.join(temp_dir, f"video_{document_id}.mp4")
        audio_path = os.path.join(temp_dir, f"audio_{document_id}.mp3")

        # Скачиваем видео
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': video_path,
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # Извлекаем аудио
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

        # Отправляем в Yandex SpeechKit
        folder_id = os.getenv('YANDEX_FOLDER_ID')
        iam_token = os.getenv('YANDEX_IAM_TOKEN')

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
                update_document_status(document_id, "completed", transcription=transcription)

                # Получаем данные для уведомления
                api_url = os.getenv('API_URL', 'http://localhost:8000')
                doc_response = httpx.get(f"{api_url}/kb/documents/{document_id}/info")

                if doc_response.status_code == 200:
                    user_data = doc_response.json()
                    telegram_id = user_data['telegram_id']
                    filename = user_data['filename']

                    # Формируем уведомление пользователю
                    asyncio.run(notify_user(
                        telegram_id,
                        f"✅ Видео обработано!\n\n"
                        f"🎥 {filename}\n",
                        keyboard=[[{"text": "🎥 Мои видео", "callback_data": "my_videos"}]]
                    ))

                # Удаляем аудио из S3
                s3_client.delete_object(Bucket=BUCKET_NAME, Key=audio_filename)

                break

        # Удаляем временные файлы
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        return {"status": "success", "document_id": document_id}

    except Exception as e:
        print(f"Ошибка обработки видео: {e}")
        update_document_status(document_id, "failed", str(e))

        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        raise


# Отправляем уведомление пользователю
async def notify_user(telegram_id: int, message: str, keyboard: list = None):
    bot_token = os.getenv('TELEGRAM_TOKEN')

    try:
        payload = {
            "chat_id": telegram_id,
            "text": message,
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
    except Exception as e:
        print(f"⚠️ Не удалось отправить уведомление: {e}")


# Обновление статуса обработки
def update_document_status(document_id: int, status: str, error: str = None, transcription: str = None):
    api_url = os.getenv('API_URL', 'http://localhost:8000')

    payload = {
        "status": status,
        "error": error,
        "transcription": transcription
    }

    try:
        response = httpx.put(f"{api_url}/kb/documents/{document_id}/status", json=payload, timeout=30.0)
        if response.status_code != 200:
            print(f"⚠️ Ошибка обновления статуса: {response.text}")
    except Exception as e:
        print(f"⚠️ Не удалось обновить статус: {e}")


# Загрузка фото в S3
def upload_photo_to_s3(photo_base64: str, user_id: int, document_id: int) -> str:

    try:
        # Декодируем base64
        photo_bytes = base64.b64decode(photo_base64)

        # Формируем путь в S3
        s3_key = f"photos/user_{user_id}/photo_{document_id}.jpg"

        # Загружаем в S3
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=photo_bytes,
            ContentType='image/jpeg'
        )

        return s3_key

    except Exception as e:
        print(f"❌ Ошибка загрузки фото в S3: {e}")
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

        return presigned_url

    except Exception as e:
        print(f"❌ Ошибка генерации presigned URL: {e}")
        raise


# Отправка фото через multipart/form-data (InputFile)
async def send_photo_bytes(telegram_id: int, photo_bytes: bytes, caption: str, keyboard: list = None):
    bot_token = os.getenv('TELEGRAM_TOKEN')

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
            data['reply_markup'] = json.dumps({"inline_keyboard": keyboard})

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                files=files,
                data=data
            )

    except Exception as e:
        print(f"⚠️ Ошибка отправки фото: {e}")


# Обработка фото через OCR
@celery_app.task(bind=True, max_retries=3)
def process_photo_ocr(self, document_id: int, s3_key: str):
    try:
        update_document_status(document_id, "processing")

        # Скачиваем ОРИГИНАЛЬНОЕ фото из S3
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        photo_bytes = response['Body'].read()

        # Конвертируем в base64 для Yandex Vision БЕЗ дополнительной конвертации
        photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')

        # Отправляем в Yandex Vision API
        vision_iam_token = os.getenv('YANDEX_VISION_IAM_TOKEN')
        folder_id = os.getenv('YANDEX_FOLDER_ID')

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

        # Извлекаем текст
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

        # Сразу ставим статус completed
        update_document_status(document_id, "completed", transcription=extracted_text.strip())

        # Получаем данные для уведомления
        api_url = os.getenv('API_URL', 'http://localhost:8000')
        doc_response = httpx.get(f"{api_url}/kb/documents/{document_id}/info")

        if doc_response.status_code == 200:
            user_data = doc_response.json()
            telegram_id = user_data['telegram_id']

            # Формируем caption с распознанным текстом (обрезаем если больше 1024 символов)
            caption = f"✅ Фото обработано!\n\n📝 Распознанный текст:\n\n{extracted_text.strip()}"

            if len(caption) > 1024:
                caption = f"✅ Фото обработано!\n\n📝 Распознанный текст:\n\n{extracted_text.strip()[:900]}...\n\n(Текст обрезан. Полный текст в базе знаний)"

            # Кнопки
            keyboard = [
                [
                    {"text": "📤 Загрузить ещё", "callback_data": "upload_photo"},
                    {"text": "🖼 Мои фото", "callback_data": "my_photos"}
                ],
                [
                    {"text": "🏠 Главное меню", "callback_data": "back_to_main"}
                ]
            ]

            # Отправляем фото с текстом и кнопками
            asyncio.run(send_photo_bytes(telegram_id, photo_bytes, caption, keyboard))

        return {"status": "success", "document_id": document_id}

    except Exception as e:
        print(f"❌ Ошибка обработки фото OCR: {e}")
        update_document_status(document_id, "failed", str(e))
        raise

# Удаление фото из S3
def delete_photo_from_s3(s3_key: str) -> bool:
    try:
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=s3_key)
        return True
    except Exception as e:
        print(f"❌ Ошибка удаления фото из S3: {e}")
        return False


# Загрузка файла в S3
def upload_file_to_s3(file_base64: str, user_id: int, document_id: int, extension: str) -> str:
    try:
        # Декодируем base64
        file_bytes = base64.b64decode(file_base64)

        # Формируем путь в S3
        s3_key = f"files/user_{user_id}/document_{document_id}.{extension}"

        # Загружаем в S3
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=file_bytes
        )

        return s3_key

    except Exception as e:
        print(f"❌ Ошибка загрузки файла в S3: {e}")
        raise


# Удаление файла из S3
def delete_file_from_s3(s3_key: str) -> bool:
    try:
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=s3_key)
        print(f"✅ Файл удалён из S3: {s3_key}")
        return True
    except Exception as e:
        print(f"❌ Ошибка удаления файла из S3: {e}")
        return False

def recognize_text_yandex(image_bytes: bytes) -> str:
    """OCR изображения через Yandex Vision"""
    try:
        vision_iam_token = os.getenv('YANDEX_VISION_IAM_TOKEN')
        folder_id = os.getenv('YANDEX_FOLDER_ID')

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
            print(f"⚠️ Ошибка Vision API: {ocr_response.text}")
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
        print(f"❌ Ошибка OCR: {e}")
        return ""

# Извлечение текста из TXT
def extract_text_from_txt(file_bytes: bytes) -> str:
    try:
        # Пробуем UTF-8
        try:
            text = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            # Пробуем CP1251 (кириллица Windows)
            text = file_bytes.decode('cp1251')

        return text.strip()

    except Exception as e:
        print(f"❌ Ошибка чтения TXT: {e}")
        raise


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Извлекает текст из DOCX + OCR всех картинок"""
    doc = Document(io.BytesIO(file_bytes))

    # 1. Извлекаем текст
    text_parts = [p.text for p in doc.paragraphs if p.text.strip()]

    # 2. Извлекаем картинки и делаем OCR
    image_texts = []
    for rel in doc.part.rels.values():
        if "image" in rel.target_ref:
            image_data = rel.target_part.blob
            # OCR через Yandex Vision
            ocr_result = recognize_text_yandex(image_data)
            if ocr_result:
                image_texts.append(ocr_result)
            time.sleep(0.5)  # Rate limit

    # 3. Объединяем
    all_text = "\n".join(text_parts)
    if image_texts:
        all_text += "\n\n=== ТЕКСТ ИЗ ИЗОБРАЖЕНИЙ ===\n" + "\n".join(image_texts)

    return all_text

# Извлечение текста из PDF через OCR
def extract_text_from_pdf_ocr(pdf_bytes: bytes) -> str:
    try:
        # Конвертируем PDF в изображения
        images = convert_from_bytes(pdf_bytes, dpi=300)

        # OCR каждой страницы через Yandex Vision
        vision_iam_token = os.getenv('YANDEX_VISION_IAM_TOKEN')
        folder_id = os.getenv('YANDEX_FOLDER_ID')

        headers = {
            'Authorization': f'Bearer {vision_iam_token}',
            'Content-Type': 'application/json'
        }

        all_text = []

        for i, image in enumerate(images):
            print(f"🔄 Обработка страницы {i + 1}/{len(images)}...")

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
                print(f"⚠️ Ошибка OCR страницы {i + 1}: {ocr_response.text}")
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

            # Пауза между запросами (чтобы не превысить rate limit)
            time.sleep(0.5)

        final_text = '\n\n'.join(all_text).strip()

        if not final_text:
            final_text = "[Текст не распознан]"

        return final_text

    except Exception as e:
        print(f"❌ Ошибка извлечения текста из PDF: {e}")
        raise


# Celery задача обработки файла
@celery_app.task(bind=True, max_retries=3)
def process_file(self, document_id: int, s3_key: str, mime_type: str):
    try:
        update_document_status(document_id, "processing")

        # Скачиваем файл из S3
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        file_bytes = response['Body'].read()

        extracted_text = ""

        # Обрабатываем в зависимости от типа
        if mime_type == "text/plain":
            print("📝 Обработка TXT файла...")
            extracted_text = extract_text_from_txt(file_bytes)

        elif mime_type == "application/pdf":
            print("📄 Обработка PDF файла...")
            extracted_text = extract_text_from_pdf_ocr(file_bytes)

        elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            print("📄 Обработка DOCX файла...")
            extracted_text = extract_text_from_docx(file_bytes)

        else:
            raise Exception(f"Неподдерживаемый тип файла: {mime_type}")

        # Сохраняем результат
        update_document_status(document_id, "completed", transcription=extracted_text)

        # Получаем данные для уведомления
        api_url = os.getenv('API_URL', 'http://localhost:8000')
        doc_response = httpx.get(f"{api_url}/kb/documents/{document_id}/info")

        if doc_response.status_code == 200:
            user_data = doc_response.json()
            telegram_id = user_data['telegram_id']
            filename = user_data['filename']

            # Формируем уведомление
            caption = f"✅ Файл обработан!\n\n📄 {filename}\n\n📝 Распознано символов: {len(extracted_text)}"

            keyboard = [
                [
                    {"text": "📤 Загрузить ещё", "callback_data": "upload_file_doc"},
                    {"text": "📄 Мои файлы", "callback_data": "my_files_docs"}
                ],
                [
                    {"text": "🏠 Главное меню", "callback_data": "back_to_main"}
                ]
            ]

            # Отправляем уведомление
            asyncio.run(notify_user(telegram_id, caption, keyboard))

        return {"status": "success", "document_id": document_id}

    except Exception as e:
        print(f"❌ Ошибка обработки файла: {e}")
        update_document_status(document_id, "failed", str(e))
        raise