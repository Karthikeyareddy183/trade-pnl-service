from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables or a local ``.env`` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trades"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def to_sync_url(async_url: str) -> str:
    """Alembic runs synchronously, so swap the asyncpg driver for psycopg."""
    return async_url.replace("+asyncpg", "+psycopg")
