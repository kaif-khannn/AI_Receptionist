"""Request dependencies: database, auth, tenant-scoped sessions, CSRF origin check."""

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import Database
from app.core.errors import AppError, Forbidden, Unauthorized
from app.models import UserRole
from app.services.auth import AuthService, ClientInfo, CurrentUser

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_db(request: Request) -> Database:
    db: Database | None = getattr(request.app.state, "db", None)
    if db is None:
        raise AppError(503, "database_unavailable", "Database is not configured")
    return db


DbDep = Annotated[Database, Depends(get_db)]


def get_auth_service(request: Request, db: DbDep) -> AuthService:
    service: AuthService | None = getattr(request.app.state, "auth", None)
    if service is None:
        raise AppError(503, "auth_unavailable", "Authentication is not configured")
    return service


AuthDep = Annotated[AuthService, Depends(get_auth_service)]


def client_info(request: Request) -> ClientInfo:
    return ClientInfo(
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )


def verify_origin(request: Request, settings: SettingsDep) -> None:
    """CSRF defence for cookie-authenticated routes: state-changing requests sent by a
    browser must come from one of our own dashboard origins."""
    if request.method not in _UNSAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        raise Forbidden("Request origin not allowed")


async def tenant_session(request: Request, db: DbDep, auth: AuthDep) -> AsyncIterator[AsyncSession]:
    """A DB session scoped to the signed-in user's tenant (RLS enforced)."""
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise Unauthorized()
    async with db.tenant_session(auth.peek_tenant(token)) as session:
        yield session


TenantSessionDep = Annotated[AsyncSession, Depends(tenant_session)]


async def current_user(request: Request, session: TenantSessionDep, auth: AuthDep) -> CurrentUser:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise Unauthorized()
    return await auth.authenticate(token, session)


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]


def require_role(
    *roles: UserRole,
) -> Callable[[CurrentUser], Coroutine[Any, Any, CurrentUser]]:
    async def check(user: CurrentUserDep) -> CurrentUser:
        if user.user.role not in roles:
            raise Forbidden()
        return user

    return check
