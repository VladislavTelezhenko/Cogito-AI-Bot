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
from dotenv import load_dotenv

load_dotenv()

# Периодическая задача обновления токена (каждые 11 часов)
@celery_app.task
def refresh_iam_token():
    get_new_iam_token()
    print("🔄 IAM токен обновлён автоматически")

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