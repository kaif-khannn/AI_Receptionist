import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantOwned, Timestamps, UUIDPrimaryKey


class AuthSession(UUIDPrimaryKey, TenantOwned, Timestamps, Base):
    """A login session. The refresh token rotates; reuse of an old one revokes the session."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # ID of the only refresh token currently valid for this session.
    current_jti: Mapped[uuid.UUID]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip_address: Mapped[str | None] = mapped_column(String(45))
