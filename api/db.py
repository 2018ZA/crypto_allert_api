"""
Асинхронное подключение к PostgreSQL через SQLAlchemy + asyncpg.

Движок создаётся один раз на процесс. Сессия — на каждый HTTP-запрос
через FastAPI-зависимость `get_db` и закрывается автоматически.
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

engine = create_async_engine(
    _settings.effective_database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=_settings.API_DEBUG,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI-зависимость: одна сессия на запрос.

    Гарантирует закрытие сессии даже при исключении в обработчике.
    """
    async with SessionLocal() as session:
        yield session