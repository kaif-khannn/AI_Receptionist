"""Business setup: profile fields, opening hours, services, packages, coverage, engineers.

Every cross-table reference is a composite (tenant_id, id) foreign key, because Postgres
FK checks bypass RLS: a plain FK on id alone would let one tenant link to another's rows.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = (
    "business_hours",
    "services",
    "packages",
    "package_features",
    "service_areas",
    "engineers",
    "engineer_services",
    "engineer_hours",
    "engineer_time_off",
)


def _id() -> sa.Column[Any]:
    return sa.Column("id", sa.Uuid(), primary_key=True)


def _tenant() -> sa.Column[Any]:
    return sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )


def _timestamps() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _tenant_fk(column: str, target: str, ondelete: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id", column],
        [f"{target}.tenant_id", f"{target}.id"],
        ondelete=ondelete,
        name=name,
    )


def upgrade() -> None:
    app_role = get_settings().app_db_role

    # ---- Business profile additions ---------------------------------------------------
    op.add_column("businesses", sa.Column("website", sa.String(200)))
    op.add_column("businesses", sa.Column("transfer_number_e164", sa.String(16)))
    op.add_column("businesses", sa.Column("fallback_number_e164", sa.String(16)))
    op.add_column(
        "businesses",
        sa.Column("emergency_policy", sa.String(20), server_default="callback", nullable=False),
    )
    op.add_column("businesses", sa.Column("gas_safe_number", sa.String(20)))
    op.add_column(
        "businesses",
        sa.Column("gas_safe_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_table(
        "business_hours",
        _id(),
        _tenant(),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=False),
        sa.Column("closes_at", sa.Time(), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_business_hours_weekday_range"),
        sa.CheckConstraint("opens_at < closes_at", name="ck_business_hours_opens_before_closes"),
    )
    op.create_index("ix_business_hours_tenant_id", "business_hours", ["tenant_id"])

    # ---- Catalogue -------------------------------------------------------------------
    op.create_table(
        "services",
        _id(),
        _tenant(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("default_duration_min", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "id", name="uq_services_tenant_id"),
        sa.CheckConstraint(
            "default_duration_min BETWEEN 15 AND 1440", name="ck_services_duration_range"
        ),
    )
    op.create_index("ix_services_tenant_id", "services", ["tenant_id"])
    op.create_index(
        "uq_services_tenant_name", "services", ["tenant_id", sa.text("lower(name)")], unique=True
    )

    op.create_table(
        "packages",
        _id(),
        _tenant(),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("price_type", sa.String(10), nullable=False),
        sa.Column("price_minor", sa.Integer()),
        sa.Column("currency", sa.String(3), server_default="GBP", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "id", name="uq_packages_tenant_id"),
        _tenant_fk("service_id", "services", "RESTRICT", "fk_packages_tenant_id_services"),
        sa.CheckConstraint("currency = 'GBP'", name="ck_packages_gbp_only"),
        sa.CheckConstraint(
            "(price_type = 'quote' AND price_minor IS NULL)"
            " OR (price_type <> 'quote' AND price_minor IS NOT NULL AND price_minor >= 0)",
            name="ck_packages_price_matches_type",
        ),
    )
    op.create_index("ix_packages_tenant_id", "packages", ["tenant_id"])
    op.create_index("ix_packages_service_id", "packages", ["service_id"])

    op.create_table(
        "package_features",
        _id(),
        _tenant(),
        sa.Column("package_id", sa.Uuid(), nullable=False),
        sa.Column("feature", sa.String(300), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False),
        sa.Column("conditions", sa.String(300)),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        _tenant_fk("package_id", "packages", "CASCADE", "fk_package_features_tenant_id_packages"),
    )
    op.create_index("ix_package_features_tenant_id", "package_features", ["tenant_id"])
    op.create_index("ix_package_features_package_id", "package_features", ["package_id"])

    op.create_table(
        "service_areas",
        _id(),
        _tenant(),
        sa.Column("prefix", sa.String(4), nullable=False),
        sa.UniqueConstraint("tenant_id", "prefix", name="uq_service_areas_tenant_id"),
    )
    op.create_index("ix_service_areas_tenant_id", "service_areas", ["tenant_id"])

    # ---- Engineers -------------------------------------------------------------------
    op.create_table(
        "engineers",
        _id(),
        _tenant(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone_e164", sa.String(16)),
        sa.Column("email", sa.String(320)),
        sa.Column("gas_safe_id", sa.String(20)),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "id", name="uq_engineers_tenant_id"),
    )
    op.create_index("ix_engineers_tenant_id", "engineers", ["tenant_id"])

    op.create_table(
        "engineer_services",
        _tenant(),
        sa.Column("engineer_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("engineer_id", "service_id", name="pk_engineer_services"),
        _tenant_fk(
            "engineer_id", "engineers", "CASCADE", "fk_engineer_services_tenant_id_engineers"
        ),
        _tenant_fk("service_id", "services", "CASCADE", "fk_engineer_services_tenant_id_services"),
    )
    op.create_index("ix_engineer_services_tenant_id", "engineer_services", ["tenant_id"])
    op.create_index("ix_engineer_services_service_id", "engineer_services", ["service_id"])

    op.create_table(
        "engineer_hours",
        _id(),
        _tenant(),
        sa.Column("engineer_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("starts_at", sa.Time(), nullable=False),
        sa.Column("ends_at", sa.Time(), nullable=False),
        _tenant_fk("engineer_id", "engineers", "CASCADE", "fk_engineer_hours_tenant_id_engineers"),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_engineer_hours_weekday_range"),
        sa.CheckConstraint("starts_at < ends_at", name="ck_engineer_hours_starts_before_ends"),
    )
    op.create_index("ix_engineer_hours_tenant_id", "engineer_hours", ["tenant_id"])
    op.create_index("ix_engineer_hours_engineer_id", "engineer_hours", ["engineer_id"])

    op.create_table(
        "engineer_time_off",
        _id(),
        _tenant(),
        sa.Column("engineer_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(200)),
        *_timestamps(),
        _tenant_fk(
            "engineer_id", "engineers", "CASCADE", "fk_engineer_time_off_tenant_id_engineers"
        ),
        sa.CheckConstraint("starts_at < ends_at", name="ck_engineer_time_off_starts_before_ends"),
    )
    op.create_index("ix_engineer_time_off_tenant_id", "engineer_time_off", ["tenant_id"])
    op.create_index("ix_engineer_time_off_engineer_id", "engineer_time_off", ["engineer_id"])

    # ---- RLS and grants --------------------------------------------------------------
    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table}"
            " USING (tenant_id = app_current_tenant())"
            " WITH CHECK (tenant_id = app_current_tenant())"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {app_role}")


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
    for column in (
        "gas_safe_verified",
        "gas_safe_number",
        "emergency_policy",
        "fallback_number_e164",
        "transfer_number_e164",
        "website",
    ):
        op.drop_column("businesses", column)
