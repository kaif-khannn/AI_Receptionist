"""Row-level security tests, run directly against Postgres as the runtime app role.

These prove isolation holds even if application code forgets a tenant filter.
"""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.core.db import Database
from tests.conftest import run_sql, signup

pytestmark = pytest.mark.db

TENANT_TABLES = ("users", "businesses", "auth_sessions", "audit_logs")


def as_tenant(tenant_id: str, *statements: str) -> tuple[str, ...]:
    """Prefix statements with the same tenant context the app sets per transaction."""
    return (f"SELECT set_config('app.tenant_id', '{uuid.UUID(tenant_id)}', true)", *statements)


@pytest.fixture
def two_tenants(db_client: TestClient) -> tuple[str, str]:
    a = signup(db_client, email="owner@abc.test", company="ABC Heating")["tenant"]["id"]
    db_client.cookies.clear()
    b = signup(db_client, email="owner@london-boiler.test", company="London Boiler Care")["tenant"][
        "id"
    ]
    return a, b


def test_tenant_sees_only_its_own_rows(app_url: str, two_tenants: tuple[str, str]) -> None:
    a, _ = two_tenants
    for table in TENANT_TABLES:
        rows = run_sql(app_url, *as_tenant(a, f"SELECT DISTINCT tenant_id::text AS t FROM {table}"))
        assert [r.t for r in rows] == [a], table
    rows = run_sql(app_url, *as_tenant(a, "SELECT id::text AS t FROM tenants"))
    assert [r.t for r in rows] == [a]


def test_no_tenant_context_sees_nothing(app_url: str, two_tenants: tuple[str, str]) -> None:
    for table in (*TENANT_TABLES, "tenants"):
        rows = run_sql(app_url, f"SELECT count(*) AS n FROM {table}")
        assert rows[0].n == 0, table


def test_cannot_write_rows_for_another_tenant(app_url: str, two_tenants: tuple[str, str]) -> None:
    a, b = two_tenants
    with pytest.raises(DBAPIError, match="row-level security"):
        run_sql(
            app_url,
            *as_tenant(
                a,
                "INSERT INTO businesses (id, tenant_id, company_name, timezone)"
                f" VALUES ('{uuid.uuid4()}', '{b}', 'Injected', 'Europe/London')",
            ),
        )


def test_cannot_update_or_delete_another_tenants_rows(
    app_url: str, owner_url: str, two_tenants: tuple[str, str]
) -> None:
    a, b = two_tenants
    run_sql(
        app_url,
        *as_tenant(a, f"UPDATE businesses SET company_name = 'Hacked' WHERE tenant_id = '{b}'"),
        *as_tenant(a, f"DELETE FROM users WHERE tenant_id = '{b}'"),
    )
    (biz,) = run_sql(owner_url, f"SELECT company_name FROM businesses WHERE tenant_id = '{b}'")
    assert biz.company_name == "London Boiler Care"
    (users,) = run_sql(owner_url, f"SELECT count(*) AS n FROM users WHERE tenant_id = '{b}'")
    assert users.n == 1


def test_cannot_move_a_row_into_another_tenant(app_url: str, two_tenants: tuple[str, str]) -> None:
    a, b = two_tenants
    with pytest.raises(DBAPIError, match="row-level security"):
        run_sql(app_url, *as_tenant(a, f"UPDATE businesses SET tenant_id = '{b}'"))


def test_audit_log_is_append_only_for_app(app_url: str, two_tenants: tuple[str, str]) -> None:
    a, _ = two_tenants
    with pytest.raises(DBAPIError, match="permission denied"):
        run_sql(app_url, *as_tenant(a, "DELETE FROM audit_logs"))
    with pytest.raises(DBAPIError, match="permission denied"):
        run_sql(app_url, *as_tenant(a, "UPDATE audit_logs SET action = 'x'"))


def test_login_lookup_exposes_only_ids(app_url: str, two_tenants: tuple[str, str]) -> None:
    rows = run_sql(app_url, "SELECT * FROM auth_lookup_user('owner@abc.test')")
    assert len(rows) == 1
    assert set(rows[0]._fields) == {"user_id", "tenant_id"}


def test_app_role_does_not_bypass_rls(app_url: str) -> None:
    (row,) = run_sql(
        app_url,
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user",
    )
    assert not row.rolsuper and not row.rolbypassrls


def test_app_refuses_to_start_with_an_rls_bypassing_role(owner_url: str) -> None:
    settings = Settings(database_url=SecretStr(owner_url), _env_file=None)

    async def _check() -> None:
        db = Database(settings)
        try:
            await db.assert_rls_enforced()
        finally:
            await db.dispose()

    # Owner role on Neon has BYPASSRLS; in CI the owner is a superuser. Either way: refuse.
    with pytest.raises(RuntimeError, match="bypasses row-level security"):
        asyncio.run(_check())


def test_api_never_returns_another_tenants_data(db_client: TestClient) -> None:
    signup(db_client, email="owner@abc.test", company="ABC Heating")
    db_client.cookies.clear()
    signup(db_client, email="owner@london-boiler.test", company="London Boiler Care")
    me = db_client.get("/api/v1/me").json()
    assert me["tenant"]["name"] == "London Boiler Care"
    assert me["user"]["email"] == "owner@london-boiler.test"
