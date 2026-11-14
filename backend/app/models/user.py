from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantOwned, Timestamps, UUIDPrimaryKey


class UserRole(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    ENGINEER = "engineer"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class User(UUIDPrimaryKey, TenantOwned, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        # One login per email across the platform (case-insensitive).
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(String(20))
    status: Mapped[UserStatus] = mapped_column(String(20), default=UserStatus.ACTIVE)
    failed_login_count: Mapped[int] = mapped_column(default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
