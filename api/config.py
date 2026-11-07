"""
Настройки API. Загружаются из .env и переменных окружения через
pydantic-settings.

Приоритет:
1. Переменные окружения процесса.
2. Файл .env в корне репозитория.
3. Значения по умолчанию (только для локальной разработки).
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация API. Читается из env + .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Подключение к БД (по частям, как в основном проекте) -----------
    DB_HOST: str = Field(default="localhost")
    DB_PORT: int = Field(default=5432)
    DB_NAME: str = Field(default="crypto_analyzer")
    DB_USER: str = Field(default="postgres")
    DB_PASSWORD: str = Field(default="postgres")

    # --- Прямой URL (приоритетнее DB_*) --------------------------------
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="postgresql+asyncpg://user:pass@host:port/db",
    )

    # --- HTTP ---------------------------------------------------------
    API_HOST: str = Field(default="127.0.0.1")
    API_PORT: int = Field(default=8000)
    API_DEBUG: bool = Field(default=False)

    # CORS: строка через запятую (pydantic-settings не умеет List[str]
    # из csv-строки, поэтому парсим вручную через property).
    API_CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Origin'ы через запятую или '*'",
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def _ensure_asyncpg(cls, v: Optional[str]) -> Optional[str]:
        """Заменяет sync-драйвер на asyncpg, если пользователь дал готовый URL."""
        if v is None:
            return v
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql+psycopg2://"):
            return v.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        return v

    @property
    def effective_database_url(self) -> str:
        """Итоговый URL для asyncpg-движка."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def cors_origins_list(self) -> List[str]:
        """Разбирает API_CORS_ORIGINS в список."""
        return [x.strip() for x in self.API_CORS_ORIGINS.split(",") if x.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Кэшированный синглтон настроек."""
    return Settings()