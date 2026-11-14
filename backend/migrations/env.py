"""Alembic environment. Runs migrations as the owner role over a direct connection."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.db import create_engine
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    # Tests pass their own URL; otherwise use MIGRATIONS_DATABASE_URL.
    override = config.attributes.get("database_url")
    if override:
        return str(override)
    url = get_settings().migrations_database_url
    if url is None:
        raise RuntimeError("MIGRATIONS_DATABASE_URL is not configured")
    return url.get_secret_value()


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_engine(_database_url(), pool_size=1)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) migrations are not supported")

asyncio.run(_run_async())
