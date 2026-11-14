from datetime import time
from enum import StrEnum

from sqlalchemy import CheckConstraint, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantOwned, Timestamps, UUIDPrimaryKey


class EmergencyPolicy(StrEnum):
    """What the AI does after giving gas/CO safety instructions."""

    TRANSFER = "transfer"  # transfer the call to the business's transfer number
    CALLBACK = "callback"  # create an urgent callback task and alert the owner


class Business(UUIDPrimaryKey, TenantOwned, Timestamps, Base):
    """The company profile. One per tenant."""

    __tablename__ = "businesses"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    company_name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/London")
    phone_e164: Mapped[str | None] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(320))
    website: Mapped[str | None] = mapped_column(String(200))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    town: Mapped[str | None] = mapped_column(String(100))
    postcode: Mapped[str | None] = mapped_column(String(10))
    # Live transfers go here (e.g. the owner's mobile).
    transfer_number_e164: Mapped[str | None] = mapped_column(String(16))
    # Where calls go when the AI is switched off or unavailable.
    fallback_number_e164: Mapped[str | None] = mapped_column(String(16))
    emergency_policy: Mapped[EmergencyPolicy] = mapped_column(
        String(20), default=EmergencyPolicy.CALLBACK, server_default=EmergencyPolicy.CALLBACK
    )
    # The AI only mentions Gas Safe registration once a platform admin has verified it.
    gas_safe_number: Mapped[str | None] = mapped_column(String(20))
    gas_safe_verified: Mapped[bool] = mapped_column(default=False, server_default="false")


class BusinessHours(UUIDPrimaryKey, TenantOwned, Base):
    """Opening hours. Several rows per weekday allowed (e.g. a lunch break)."""

    __tablename__ = "business_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("opens_at < closes_at", name="opens_before_closes"),
    )

    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday
    opens_at: Mapped[time]
    closes_at: Mapped[time]
