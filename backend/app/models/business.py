from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantOwned, Timestamps, UUIDPrimaryKey


class Business(UUIDPrimaryKey, TenantOwned, Timestamps, Base):
    """The company profile. One per tenant; extended in Phase 2."""

    __tablename__ = "businesses"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    company_name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/London")
    phone_e164: Mapped[str | None] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(320))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    town: Mapped[str | None] = mapped_column(String(100))
    postcode: Mapped[str | None] = mapped_column(String(10))
