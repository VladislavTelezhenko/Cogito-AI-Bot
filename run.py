# Единый файл для запуска приложения

import redis
import subprocess
import sys


# Проверка готовности редиса
def check_redis():
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("Redis работает")
        return True
    except:
        print("❌ Redis не запущен!")
        print("   redis-server.exe")
        return False


def main():
    print("Запуск Cogito AI Bot\n")

    if not check_redis():
        sys.exit(1)

    processes = []

    try:
        print("Запуск API...")
        api = subprocess.Popen(
            ['uvicorn', 'main:app', '--reload']
        )
        processes.append(('API', api))

        print("Запуск Celery Worker...")
        celery = subprocess.Popen(
            ['celery', '-A', 'celery_app', 'worker', '--loglevel=info', '--pool=solo']
            # 'celery', '-A', 'celery_app', 'worker', '--beat', '--loglevel=info', '--pool=solo' - автообновление токена для сервера
        )
        processes.append(('Celery', celery))

        print("Запуск бота...")
        bot = subprocess.Popen(
            ['python', 'bot.py']
        )
        processes.append(('Bot', bot))

        print("\nВсе сервисы запущены!")

        # Ждём завершения
        for name, proc in processes:
            proc.wait()

    except KeyboardInterrupt:
        print("\n\nОстановка сервисов...")
        for name, proc in processes:
            proc.terminate()
            print(f"   {name} остановлен")


if __name__ == "__main__":
    main()