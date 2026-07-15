from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

import logging

# Подавляем логи SQLAlchemy
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.dialects').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.orm').setLevel(logging.WARNING)

# Создаем асинхронный движок
# echo=False - отключает вывод SQL запросов в консоль
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # <-- КЛЮЧЕВОЙ ПАРАМЕТР! Было echo=True
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

# Фабрика асинхронных сессий
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

# Dependency Injection для эндпоинтов FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
