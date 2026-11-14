"""Initial schema: tenants, users, businesses, auth sessions, audit log, with RLS.

Revision ID: 0001
Revises:
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("users", "businesses", "auth_sessions", "audit_logs")


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _tenant_fk() -> sa.Column[object]:
    return sa.Column(
        "tenant_id",
        sa.Uuid(),
        sa.ForeignKey("tenants.id", name=None, ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    app_role = get_settings().app_db_role

    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("plan", sa.String(40), nullable=False),
        sa.Column("ai_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_fk(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        *_timestamps(),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "businesses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_fk(),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("phone_e164", sa.String(16)),
        sa.Column("email", sa.String(320)),
        sa.Column("address_line1", sa.String(200)),
        sa.Column("address_line2", sa.String(200)),
        sa.Column("town", sa.String(100)),
        sa.Column("postcode", sa.String(10)),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", name="uq_businesses_tenant_id"),
    )
    op.create_index("ix_businesses_tenant_id", "businesses", ["tenant_id"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_fk(),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("current_jti", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent", sa.String(300)),
        sa.Column("ip_address", sa.String(45)),
        *_timestamps(),
    )
    op.create_index("ix_auth_sessions_tenant_id", "auth_sessions", ["tenant_id"])
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_fk(),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(40)),
        sa.Column("target_id", sa.Uuid()),
        sa.Column(
            "details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ---- Row-level security -------------------------------------------------------------
    # The app connects as a non-owner role, so these policies always apply to it.
    # NULLIF: an unset tenant context matches no rows instead of erroring.
    op.execute(
        """
        CREATE FUNCTION app_current_tenant() RETURNS uuid
        LANGUAGE sql STABLE
        AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$
        """
    )

    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON tenants"
        " USING (id = app_current_tenant()) WITH CHECK (id = app_current_tenant())"
    )
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table}"
            " USING (tenant_id = app_current_tenant())"
            " WITH CHECK (tenant_id = app_current_tenant())"
        )

    # Login must find a user before the tenant is known. This SECURITY DEFINER function
    # (runs as the owner, who is not subject to RLS) returns only the two IDs needed to
    # set the tenant context; the user row itself is then read under RLS.
    op.execute(
        """
        CREATE FUNCTION auth_lookup_user(p_email text)
        RETURNS TABLE (user_id uuid, tenant_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$ SELECT u.id, u.tenant_id FROM public.users u WHERE lower(u.email) = lower(p_email) $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION auth_lookup_user(text) FROM PUBLIC")

    # ---- Grants for the runtime role ----------------------------------------------------
    op.execute(f"GRANT USAGE ON SCHEMA public TO {app_role}")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_current_tenant() TO {app_role}")
    op.execute(f"GRANT EXECUTE ON FUNCTION auth_lookup_user(text) TO {app_role}")
    for table in ("tenants", "users", "businesses", "auth_sessions"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {app_role}")
    # Audit log is append-only for the app.
    op.execute(f"GRANT SELECT, INSERT ON audit_logs TO {app_role}")


def downgrade() -> None:
    app_role = get_settings().app_db_role
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {app_role}")
    op.execute("DROP FUNCTION IF EXISTS auth_lookup_user(text)")
    for table in ("audit_logs", "auth_sessions", "businesses", "users", "tenants"):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS app_current_tenant()")
