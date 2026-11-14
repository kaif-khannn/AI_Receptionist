from enum import StrEnum

from sqlalchemy import String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Tenant(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[TenantStatus] = mapped_column(String(20), default=TenantStatus.ACTIVE)
    plan: Mapped[str] = mapped_column(String(40), default="trial")
    # Kill switch: when false, calls go straight to the business's fallback number.
    ai_enabled: Mapped[bool] = mapped_column(server_default=true(), default=True)
