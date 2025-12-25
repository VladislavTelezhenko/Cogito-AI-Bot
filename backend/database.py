# Подключение к базе данных

import os
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# URL подключения к PostgreSQL
DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{quote_plus(os.getenv('DB_PASSWORD'))}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

logger.info(f"Подключение к БД: postgresql://{os.getenv('DB_USER')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}")

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

# Функция для получения сессии БД
def get_db():
    """Генератор сессии БД для использования в FastAPI Depends"""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Ошибка при работе с БД: {e}")
        db.rollback()
        raise
    finally:
        db.close()