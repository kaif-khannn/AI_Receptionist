import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Deterministic constraint names so Alembic migrations are stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKey:
    # UUIDv7 is time-ordered, so inserts stay index-friendly.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def tenant_fk(column: str, target: str, *, ondelete: str) -> ForeignKeyConstraint:
    """FK on (tenant_id, <column>) so a row can never reference another tenant's row.

    Postgres FK checks bypass RLS, so a plain FK on the ID alone would let tenant A link
    to tenant B's service if it knew the UUID. The composite key makes that impossible.
    """
    return ForeignKeyConstraint(
        ["tenant_id", column], [f"{target}.tenant_id", f"{target}.id"], ondelete=ondelete
    )


class TenantOwned:
    """Every business-owned table carries tenant_id and is protected by RLS."""

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
