"""Shared fixtures.

Tests marked ``db`` run against a real Postgres test database. They are skipped when
TEST_DATABASE_URL / TEST_MIGRATIONS_DATABASE_URL aren't set. The schema is rebuilt from
migrations once per run and every table is wiped before each test, so never point these
at a database with real data.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text

from app.core.config import Environment, Settings
from app.core.db import create_engine
from app.main import create_app

TEST_SECRET = "test-secret-key-not-for-production-0123456789"


class _TestDatabaseEnv(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    test_database_url: SecretStr | None = None
    test_migrations_database_url: SecretStr | None = None


@pytest.fixture
def settings() -> Settings:
    return Settings(environment=Environment.TEST, _env_file=None)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


# ---- database fixtures ---------------------------------------------------------------


def run_sql(url: str, *statements: str, params: dict[str, Any] | None = None) -> list[Any]:
    """Run statements on a fresh connection; returns rows of the last one."""

    async def _go() -> list[Any]:
        engine = create_engine(url, pool_size=1)
        try:
            async with engine.begin() as conn:
                result = None
                for statement in statements:
                    result = await conn.execute(text(statement), params or {})
                return list(result.all()) if result is not None and result.returns_rows else []
        finally:
            await engine.dispose()

    return asyncio.run(_go())


@pytest.fixture(scope="session")
def db_env() -> _TestDatabaseEnv:
    env = _TestDatabaseEnv()
    if env.test_database_url is None or env.test_migrations_database_url is None:
        pytest.skip("TEST_DATABASE_URL / TEST_MIGRATIONS_DATABASE_URL not set")
    return env


@pytest.fixture(scope="session")
def migrated_db(db_env: _TestDatabaseEnv) -> _TestDatabaseEnv:
    """Rebuild the schema from scratch: also proves downgrade and upgrade both work."""
    assert db_env.test_migrations_database_url is not None
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = db_env.test_migrations_database_url.get_secret_value()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    return db_env


@pytest.fixture
def owner_url(migrated_db: _TestDatabaseEnv) -> Iterator[str]:
    assert migrated_db.test_migrations_database_url is not None
    url = migrated_db.test_migrations_database_url.get_secret_value()
    run_sql(url, "TRUNCATE tenants CASCADE")
    yield url


@pytest.fixture
def app_url(migrated_db: _TestDatabaseEnv, owner_url: str) -> str:
    assert migrated_db.test_database_url is not None
    return migrated_db.test_database_url.get_secret_value()


@pytest.fixture
def db_settings(app_url: str) -> Settings:
    return Settings(
        environment=Environment.TEST,
        database_url=SecretStr(app_url),
        secret_key=SecretStr(TEST_SECRET),
        _env_file=None,
    )


@pytest.fixture
def db_client(db_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(db_settings)) as test_client:
        yield test_client


def add_user(owner_url: str, tenant_id: str, email: str, role: str, password: str) -> None:
    """Insert a user directly (no invite flow yet). Runs as the owner role."""
    from argon2 import PasswordHasher

    run_sql(
        owner_url,
        "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, status)"
        " VALUES (gen_random_uuid(), :tenant_id, :email, :hash, 'Test User', :role, 'active')",
        params={
            "tenant_id": tenant_id,
            "email": email,
            "hash": PasswordHasher().hash(password),
            "role": role,
        },
    )


def replace_cookie(client: TestClient, name: str, value: str, path: str = "/") -> None:
    """Overwrite a cookie the server set. ``client.cookies.set`` alone would add a
    second cookie alongside the original, and the server might read the original."""
    existing = [c for c in client.cookies.jar if c.name == name and c.path == path]
    domain = existing[0].domain if existing else ""
    for cookie in existing:
        client.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)
    client.cookies.set(name, value, domain=domain, path=path)
    assert [c.value for c in client.cookies.jar if c.name == name and c.path == path] == [value]


def signup(
    client: TestClient,
    *,
    email: str = "owner@abc-heating.example.com",
    company: str = "ABC Heating",
    password: str = "correct horse battery",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": company,
            "full_name": "Test Owner",
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body
