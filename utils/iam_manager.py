# Получение новых IAM токенов для Yandex SpeechKit и Vision API

import requests
import json
import jwt
import time
import os
import logging
from dotenv import load_dotenv, set_key
from pathlib import Path


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('iam_manager.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

env_path = Path(__file__).parent.parent / 'secret' / '.env'
load_dotenv(dotenv_path=env_path)


def get_new_iam_token():
    """Получение нового IAM токена для SpeechKit"""
    logger.info("Запрос на обновление SpeechKit IAM токена...")

    try:
        with open('key.json', 'r') as f:
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

            # Обновляем .env
            env_path = os.path.join(os.getcwd(), '.env')
            set_key(env_path, 'YANDEX_IAM_TOKEN', iam_token)

            logger.info("✅ SpeechKit IAM токен успешно обновлён")
            return iam_token
        else:
            logger.error(f"❌ Ошибка получения токена SpeechKit: {response.status_code} - {response.text}")
            return None

    except FileNotFoundError:
        logger.error("❌ Файл key.json не найден")
        return None
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при обновлении SpeechKit токена: {e}")
        return None


def get_new_vision_iam_token():
    """Получение нового IAM токена для Vision API"""
    logger.info("Запрос на обновление Vision IAM токена...")

    try:
        with open('ocr_key.json', 'r') as f:
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

            # Обновляем .env
            env_path = os.path.join(os.getcwd(), '.env')
            set_key(env_path, 'YANDEX_VISION_IAM_TOKEN', iam_token)

            logger.info("✅ Vision IAM токен успешно обновлён")
            return iam_token
        else:
            logger.error(f"❌ Ошибка получения токена Vision: {response.status_code} - {response.text}")
            return None

    except FileNotFoundError:
        logger.error("❌ Файл ocr_key.json не найден")
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