# Получение новых IAM токенов для Yandex SpeechKit и Vision API

import requests
import json
import jwt
import time
import os
import logging
from dotenv import load_dotenv, set_key
from pathlib import Path

# Пути к файлам
BASE_DIR = Path(__file__).parent.parent  # Корень проекта
SECRET_DIR = BASE_DIR / 'secret'
LOGS_DIR = BASE_DIR / 'logs'
env_path = SECRET_DIR / '.env'

# Создаём папку logs если её нет
LOGS_DIR.mkdir(exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / 'iam_manager.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv(dotenv_path=env_path)


def get_new_iam_token():
    """Получение нового IAM токена для SpeechKit"""
    logger.info("Запрос на обновление SpeechKit IAM токена...")

    try:
        # Путь к key.json в папке secret
        key_path = SECRET_DIR / 'key.json'

        with open(key_path, 'r') as f:
            key_data = json.load(f)

        now = int(time.time())
        payload = {
            'aud': 'https://iam.api.cloud.yandex.net/iam/v1/tokens',
            'iss': key_data['service_account_id'],
            'iat': now,
            'exp': now + 360
        }

        token = jwt.encode(
            payload,
            key_data['private_key'],
            algorithm='PS256',
            headers={'kid': key_data['id']}
        )

        response = requests.post(
            'https://iam.api.cloud.yandex.net/iam/v1/tokens',
            json={'jwt': token}
        )

        if response.status_code == 200:
            iam_token = response.json()['iamToken']

            # Обновляем .env в папке secret
            set_key(str(env_path), 'YANDEX_IAM_TOKEN', iam_token)

            logger.info("✅ SpeechKit IAM токен успешно обновлён")
            return iam_token
        else:
            logger.error(f"❌ Ошибка получения токена SpeechKit: {response.status_code} - {response.text}")
            return None

    except FileNotFoundError:
        logger.error(f"❌ Файл key.json не найден в папке {SECRET_DIR}")
        return None
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при обновлении SpeechKit токена: {e}")
        return None


def get_new_vision_iam_token():
    """Получение нового IAM токена для Vision API"""
    logger.info("Запрос на обновление Vision IAM токена...")

    try:
        # Путь к ocr_key.json в папке secret
        key_path = SECRET_DIR / 'ocr_key.json'

        with open(key_path, 'r') as f:
            key_data = json.load(f)

        now = int(time.time())
        payload = {
            'aud': 'https://iam.api.cloud.yandex.net/iam/v1/tokens',
            'iss': key_data['service_account_id'],
            'iat': now,
            'exp': now + 360
        }

        token = jwt.encode(
            payload,
            key_data['private_key'],
            algorithm='PS256',
            headers={'kid': key_data['id']}
        )

        response = requests.post(
            'https://iam.api.cloud.yandex.net/iam/v1/tokens',
            json={'jwt': token}
        )

        if response.status_code == 200:
            iam_token = response.json()['iamToken']

            # Обновляем .env в папке secret
            set_key(str(env_path), 'YANDEX_VISION_IAM_TOKEN', iam_token)

            logger.info("✅ Vision IAM токен успешно обновлён")
            return iam_token
        else:
            logger.error(f"❌ Ошибка получения токена Vision: {response.status_code} - {response.text}")
            return None

    except FileNotFoundError:
        logger.error(f"❌ Файл ocr_key.json не найден в папке {SECRET_DIR}")
        return None
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при обновлении Vision токена: {e}")
        return None


if __name__ == "__main__":
    logger.info("=== РУЧНОЕ ОБНОВЛЕНИЕ IAM ТОКЕНОВ ===")

    speechkit_token = get_new_iam_token()
    vision_token = get_new_vision_iam_token()

    if speechkit_token and vision_token:
        logger.info("✅ Все токены успешно обновлены")
    else:
        logger.warning("⚠️ Не все токены были обновлены, проверьте логи выше")