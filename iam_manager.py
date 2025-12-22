# Получаем новый токен для спич кита и Vision API

import requests
import json
import jwt
import time
import os
from dotenv import load_dotenv, set_key

load_dotenv()

def get_new_iam_token():
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

        print(f"✅ SpeechKit IAM токен обновлён")
        return iam_token
    else:
        print(f"❌ Ошибка SpeechKit: {response.text}")
        return None


def get_new_vision_iam_token():

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

        print(f"✅ Vision IAM токен обновлён")
        return iam_token
    else:
        print(f"❌ Ошибка Vision: {response.text}")
        return None


if __name__ == "__main__":
    get_new_iam_token()
    get_new_vision_iam_token()