# Единый файл для запуска приложения с Flower

import redis
import subprocess
import sys
import logging
from pathlib import Path

# Пути к файлам
BASE_DIR = Path(__file__).parent.parent  # Корень проекта
LOGS_DIR = BASE_DIR / 'logs'

# Создаём папку logs если её нет
LOGS_DIR.mkdir(exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / 'run_flower.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Проверка готовности редиса
def check_redis():
    """Проверка подключения к Redis"""
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        logger.info("✅ Redis работает")
        return True
    except Exception as e:
        logger.error(f"❌ Redis не запущен! Ошибка: {e}")
        logger.info("   Запустите: redis-server")
        return False


def main():
    logger.info("=== ЗАПУСК COGITO AI BOT (С FLOWER) ===")

    if not check_redis():
        logger.error("Невозможно запустить приложение без Redis")
        sys.exit(1)

    processes = []

    try:
        logger.info("▶ Запуск API сервера...")
        api = subprocess.Popen(
            ['uvicorn', 'backend.main:app', '--reload']
        )
        processes.append(('API', api))

        logger.info("▶ Запуск Celery Worker...")
        celery = subprocess.Popen(
            ['celery', '-A', 'backend.celery_app', 'worker', '--loglevel=info', '--pool=solo']
            # 'celery', '-A', 'backend.celery_app', 'worker', '--beat', '--loglevel=info', '--pool=solo' - автообновление токена для сервера
        )
        processes.append(('Celery', celery))

        logger.info("▶ Запуск Flower (мониторинг Celery)...")
        flower = subprocess.Popen(
            ['celery', '-A', 'backend.celery_app', 'flower', '--port=5555']
        )
        processes.append(('Flower', flower))

        logger.info("▶ Запуск Telegram бота...")
        bot = subprocess.Popen(
            ['python', '-m', 'bot.bot']
        )
        processes.append(('Bot', bot))

        logger.info("✅ Все сервисы успешно запущены!")
        logger.info("")
        logger.info("🌐 Доступные интерфейсы:")
        logger.info("   📡 API:    http://localhost:8000")
        logger.info("   🌸 Flower: http://localhost:5555")
        logger.info("")

        # Ждём завершения
        for name, proc in processes:
            proc.wait()

    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки (Ctrl+C)")
        logger.info("Останавливаю сервисы...")

        for name, proc in processes:
            proc.terminate()
            logger.info(f"   ✓ {name} остановлен")

        logger.info("✅ Все сервисы остановлены")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске: {e}")
        for name, proc in processes:
            proc.terminate()
        sys.exit(1)


if __name__ == "__main__":
    main()