"""Shared helpers for tenant-scoped CRUD routes."""

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.deps import require_role
from app.models import UserRole
from app.models.base import Base
from app.services.auth import CurrentUser

# Owners and managers configure the business; engineers can only read.
WriterDep = Annotated[CurrentUser, Depends(require_role(UserRole.OWNER, UserRole.MANAGER))]
OwnerDep = Annotated[CurrentUser, Depends(require_role(UserRole.OWNER))]


async def get_owned[M: Base](session: AsyncSession, model: type[M], id_: uuid.UUID, what: str) -> M:
    """Fetch by ID. Rows of other tenants are invisible under RLS, so they 404 too."""
    obj = await session.get(model, id_)
    if obj is None:
        raise NotFound(what)
    return obj


async def commit(session: AsyncSession, conflicts: dict[str, tuple[str, str]]) -> None:
    """Commit, turning known constraint violations into 409s.

    ``conflicts`` maps a constraint name to (error code, message for the owner).
    """
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        detail = str(exc.orig)
        for constraint, (code, message) in conflicts.items():
            if constraint in detail:
                raise Conflict(code, message) from exc
        raise
