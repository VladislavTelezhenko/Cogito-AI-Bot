# Подключение к базе данных

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus

# Загружаем .env из secret/
env_path = Path(__file__).parent.parent / 'secret' / '.env'
load_dotenv(dotenv_path=env_path)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Проверяем что переменные загрузились
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_name = os.getenv('DB_NAME')

if not all([db_user, db_password, db_host, db_port, db_name]):
    logger.error(f"Не все переменные БД загружены")
    raise ValueError("Не загружены переменные окружения для БД из .env")

# URL подключения к PostgreSQL
DATABASE_URL = f"postgresql://{db_user}:{quote_plus(db_password)}@{db_host}:{db_port}/{db_name}"

logger.info(f"Подключение к БД: postgresql://{db_user}@{db_host}:{db_port}/{db_name}")

# Создаём движок БД
try:
    engine = create_engine(DATABASE_URL)
    logger.info("Движок БД успешно создан")
except Exception as e:
    logger.error(f"Ошибка создания движка БД: {e}")
    raise

# Создаём фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей
Base = declarative_base()

# Переменная для Alembic
SQLALCHEMY_DATABASE_URL = DATABASE_URL

# Функция для получения сессии БД
def get_db():
    # Генератор сессии БД для использования в FastAPI Depends
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Ошибка при работе с БД: {e}")
        db.rollback()
        raise
    finally:
        db.close()