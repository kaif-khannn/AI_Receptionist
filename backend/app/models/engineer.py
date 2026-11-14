"""Engineers, what they can do, and when they work. Used by booking in Phase 5."""

import uuid
from datetime import datetime, time

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantOwned, Timestamps, UUIDPrimaryKey, tenant_fk


class Engineer(UUIDPrimaryKey, TenantOwned, Timestamps, Base):
    __tablename__ = "engineers"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

    name: Mapped[str] = mapped_column(String(200))
    phone_e164: Mapped[str | None] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(320))
    gas_safe_id: Mapped[str | None] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(default=True, server_default="true")

    skills: Mapped[list[EngineerService]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    hours: Mapped[list[EngineerHours]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="[EngineerHours.weekday, EngineerHours.starts_at]",
    )


class EngineerService(TenantOwned, Base):
    """Which services an engineer is qualified to do."""

    __tablename__ = "engineer_services"
    __table_args__ = (
        PrimaryKeyConstraint("engineer_id", "service_id"),
        tenant_fk("engineer_id", "engineers", ondelete="CASCADE"),
        tenant_fk("service_id", "services", ondelete="CASCADE"),
    )

    engineer_id: Mapped[uuid.UUID]
    service_id: Mapped[uuid.UUID] = mapped_column(index=True)


class EngineerHours(UUIDPrimaryKey, TenantOwned, Base):
    """Regular weekly working hours."""

    __tablename__ = "engineer_hours"
    __table_args__ = (
        tenant_fk("engineer_id", "engineers", ondelete="CASCADE"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("starts_at < ends_at", name="starts_before_ends"),
    )

    engineer_id: Mapped[uuid.UUID] = mapped_column(index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday
    starts_at: Mapped[time]
    ends_at: Mapped[time]


class EngineerTimeOff(UUIDPrimaryKey, TenantOwned, Timestamps, Base):
    """Holidays, sickness, training: blocks booking."""

    __tablename__ = "engineer_time_off"
    __table_args__ = (
        tenant_fk("engineer_id", "engineers", ondelete="CASCADE"),
        CheckConstraint("starts_at < ends_at", name="starts_before_ends"),
    )

    engineer_id: Mapped[uuid.UUID] = mapped_column(index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(200))
