"""Database engine, sessions and per-transaction tenant context for row-level security.

Every transaction on a session that has a tenant runs
``SELECT set_config('app.tenant_id', <id>, true)`` first, so Postgres RLS policies
only ever expose that tenant's rows. ``true`` makes the setting transaction-local, which
is safe with Neon's transaction-mode connection pooler.
"""

import ssl
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, SessionTransaction

from app.core.config import Settings

TENANT_KEY = "tenant_id"

# libpq-style query params that asyncpg doesn't accept as-is.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding"}


def to_asyncpg_url(url: str) -> tuple[str, dict[str, Any]]:
    """Convert a Neon/libpq URL into an asyncpg SQLAlchemy URL plus connect_args."""
    parts = urlsplit(url)
    scheme = "postgresql+asyncpg"
    query = dict(parse_qsl(parts.query))
    sslmode = query.get("sslmode")
    for key in _LIBPQ_ONLY_PARAMS:
        query.pop(key, None)

    connect_args: dict[str, Any] = {}
    if sslmode and sslmode != "disable":
        connect_args["ssl"] = ssl.create_default_context()
    if parts.hostname and "-pooler" in parts.hostname:
        # PgBouncer in transaction mode: don't rely on server-side prepared statement caches.
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid.uuid4()}__"

    clean = urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return clean, connect_args


def create_engine(url: str, *, pool_size: int = 5) -> AsyncEngine:
    async_url, connect_args = to_asyncpg_url(url)
    return create_async_engine(
        async_url,
        connect_args=connect_args,
        pool_size=pool_size,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=300,
    )


@event.listens_for(Session, "after_begin")
def _apply_tenant_context(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    tenant_id = session.info.get(TENANT_KEY)
    if tenant_id is not None:
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
        )


def set_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Scope this session to one tenant. Must be called before the first query."""
    if session.in_transaction():
        raise RuntimeError("set_tenant must be called before the session starts a transaction")
    session.info[TENANT_KEY] = tenant_id


class Database:
    def __init__(self, settings: Settings) -> None:
        if settings.database_url is None:
            raise RuntimeError("DATABASE_URL is not configured")
        self.engine = create_engine(settings.database_url.get_secret_value())
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def tenant_session(self, tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
        """A session that can only see and write this tenant's rows."""
        async with self.sessionmaker() as session:
            set_tenant(session, tenant_id)
            yield session

    @asynccontextmanager
    async def system_session(self) -> AsyncIterator[AsyncSession]:
        """A session with no tenant: RLS hides every tenant row. Only for narrow
        lookups through SECURITY DEFINER functions (e.g. finding a user at login)."""
        async with self.sessionmaker() as session:
            yield session

    async def ping(self) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def assert_rls_enforced(self) -> None:
        """Refuse to run as a role that bypasses row-level security."""
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
                    )
                )
            ).scalar_one()
        if row:
            raise RuntimeError(
                "DATABASE_URL uses a role that bypasses row-level security. "
                "Use the non-owner app role (see docs/03_DATABASE_SCHEMA.md)."
            )

    async def dispose(self) -> None:
        await self.engine.dispose()
