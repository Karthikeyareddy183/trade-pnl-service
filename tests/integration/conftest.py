"""Integration tests run against a real PostgreSQL, because the guarantees under test
(unique-key idempotency, row locks, CHECK constraints) are database behaviour that a
mock or SQLite cannot reproduce.

``TEST_DATABASE_URL`` picks the server; the database is created if missing and migrated
with Alembic. If no server is reachable the whole suite is skipped, not failed.
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import Settings, to_sync_url
from app.db.create_database import ensure_database
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


class _TestEnv(BaseSettings):
    """Reads TEST_DATABASE_URL from the environment or the project's .env file."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    test_database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trades_test"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url = _TestEnv().test_database_url
    sync_url = sa.make_url(to_sync_url(url))
    try:
        ensure_database(sync_url)
    except sa.exc.OperationalError as exc:
        reason = f"PostgreSQL not reachable at {sync_url.render_as_string()}: {exc.orig}"
        if os.getenv("REQUIRE_DATABASE"):
            pytest.fail(reason)
        pytest.skip(reason)

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", sync_url.render_as_string(hide_password=False))
    cfg.attributes["configure_logger"] = False
    # Down then up: proves both directions of the migration work on every run.
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield url


@pytest.fixture
async def app(database_url: str) -> AsyncIterator[FastAPI]:
    application = create_app(Settings(database_url=database_url, log_level="WARNING"))
    async with application.state.engine.begin() as conn:
        await conn.execute(sa.text("TRUNCATE trades, positions, prices RESTART IDENTITY"))
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
