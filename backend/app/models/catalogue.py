"""Services, packages and coverage: what the AI is allowed to tell callers."""

import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantOwned, Timestamps, UUIDPrimaryKey, tenant_fk


class ServiceCategory(StrEnum):
    BOILER_REPAIR = "boiler_repair"
    BOILER_INSTALLATION = "boiler_installation"
    BOILER_SERVICING = "boiler_servicing"
    HEATING = "heating"
    AIR_CONDITIONING = "air_conditioning"
    OTHER = "other"


class PriceType(StrEnum):
    FIXED = "fixed"  # "£125"
    FROM = "from"  # "from £1,800"
    QUOTE = "quote"  # "priced after a survey": no figure given to callers


class Service(UUIDPrimaryKey, TenantOwned, Timestamps, Base):
    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),  # target of composite tenant FKs
        Index("uq_services_tenant_name", "tenant_id", text("lower(name)"), unique=True),
        CheckConstraint("default_duration_min BETWEEN 15 AND 1440", name="duration_range"),
    )

    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[ServiceCategory] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    default_duration_min: Mapped[int] = mapped_column(default=60)
    active: Mapped[bool] = mapped_column(default=True, server_default="true")


class Package(UUIDPrimaryKey, TenantOwned, Timestamps, Base):
    __tablename__ = "packages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        tenant_fk("service_id", "services", ondelete="RESTRICT"),
        CheckConstraint("currency = 'GBP'", name="gbp_only"),
        CheckConstraint(
            "(price_type = 'quote' AND price_minor IS NULL)"
            " OR (price_type <> 'quote' AND price_minor IS NOT NULL AND price_minor >= 0)",
            name="price_matches_type",
        ),
    )

    service_id: Mapped[uuid.UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    price_type: Mapped[PriceType] = mapped_column(String(10))
    # Pence. £1,850.00 = 185000. NULL when price_type is "quote".
    price_minor: Mapped[int | None]
    currency: Mapped[str] = mapped_column(String(3), default="GBP", server_default="GBP")
    active: Mapped[bool] = mapped_column(default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")

    features: Mapped[list[PackageFeature]] = relationship(
        order_by="PackageFeature.sort_order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PackageFeature(UUIDPrimaryKey, TenantOwned, Base):
    """A line in a package: something included (or explicitly excluded)."""

    __tablename__ = "package_features"
    __table_args__ = (tenant_fk("package_id", "packages", ondelete="CASCADE"),)

    package_id: Mapped[uuid.UUID] = mapped_column(index=True)
    feature: Mapped[str] = mapped_column(String(300))
    included: Mapped[bool] = mapped_column(default=True)
    conditions: Mapped[str | None] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")


class ServiceArea(UUIDPrimaryKey, TenantOwned, Base):
    """A covered postcode area ("M") or district ("M1", "SW1A")."""

    __tablename__ = "service_areas"
    __table_args__ = (UniqueConstraint("tenant_id", "prefix"),)

    prefix: Mapped[str] = mapped_column(String(4))
