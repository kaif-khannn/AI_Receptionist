"""Signup, login, token refresh and logout.

Sessions: a short-lived access token plus a rotating refresh token. Each refresh issues a
new refresh token and invalidates the previous one; presenting an old one is treated as
theft and revokes the whole session.
"""

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import Database
from app.core.errors import AppError, Conflict, Forbidden, Unauthorized
from app.core.security import (
    InvalidTokenError,
    TokenClaims,
    TokenType,
    decode_token,
    encode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.models import AuthSession, Business, Tenant, TenantStatus, User, UserRole, UserStatus
from app.schemas.auth import LoginRequest, SignupRequest
from app.services import audit

BAD_CREDENTIALS = "Incorrect email or password"


@dataclass(frozen=True, slots=True)
class ClientInfo:
    user_agent: str | None
    ip_address: str | None


@dataclass(frozen=True, slots=True)
class IssuedSession:
    user: User
    tenant: Tenant
    access_token: str
    refresh_token: str


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user: User
    tenant: Tenant
    session_id: uuid.UUID


def _now() -> datetime:
    return datetime.now(UTC)


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "business"
    return f"{base}-{secrets.token_hex(3)}"


class AuthService:
    def __init__(self, db: Database, settings: Settings) -> None:
        if settings.secret_key is None:
            raise RuntimeError("SECRET_KEY is not configured")
        self._db = db
        self._settings = settings
        self._secret = settings.secret_key.get_secret_value()

    # ---- token helpers ----------------------------------------------------------------

    def _issue_tokens(self, user: User, session: AuthSession) -> tuple[str, str]:
        def claims(token_type: TokenType, jti: uuid.UUID) -> TokenClaims:
            return TokenClaims(
                type=token_type,
                user_id=user.id,
                tenant_id=user.tenant_id,
                session_id=session.id,
                jti=jti,
                role=user.role,
            )

        access = encode_token(
            claims(TokenType.ACCESS, uuid.uuid4()),
            secret=self._secret,
            ttl=timedelta(minutes=self._settings.access_token_ttl_minutes),
        )
        refresh = encode_token(
            claims(TokenType.REFRESH, session.current_jti),
            secret=self._secret,
            ttl=timedelta(days=self._settings.refresh_token_ttl_days),
        )
        return access, refresh

    def _new_session(self, user: User, client: ClientInfo) -> AuthSession:
        return AuthSession(
            id=uuid.uuid7(),
            tenant_id=user.tenant_id,
            user_id=user.id,
            current_jti=uuid.uuid4(),
            expires_at=_now() + timedelta(days=self._settings.refresh_token_ttl_days),
            user_agent=(client.user_agent or "")[:300] or None,
            ip_address=client.ip_address,
        )

    async def _lookup_user_ids(self, email: str) -> tuple[uuid.UUID, uuid.UUID] | None:
        async with self._db.system_session() as session:
            row = (
                await session.execute(
                    text("SELECT user_id, tenant_id FROM auth_lookup_user(:email)"),
                    {"email": email},
                )
            ).first()
        return (row.user_id, row.tenant_id) if row else None

    # ---- flows --------------------------------------------------------------------------

    async def signup(self, req: SignupRequest, client: ClientInfo) -> IssuedSession:
        if not self._settings.allow_public_signup:
            raise Forbidden("Sign-up is by invitation only")
        if await self._lookup_user_ids(req.email) is not None:
            raise Conflict("email_taken", "An account with this email already exists")

        password_hash = await hash_password(req.password)
        tenant_id = uuid.uuid7()
        async with self._db.tenant_session(tenant_id) as session:
            tenant = Tenant(
                id=tenant_id,
                name=req.company_name,
                slug=_slugify(req.company_name),
                status=TenantStatus.ACTIVE,
                plan="trial",
                ai_enabled=True,
            )
            user = User(
                id=uuid.uuid7(),
                tenant_id=tenant_id,
                email=req.email,
                password_hash=password_hash,
                full_name=req.full_name,
                role=UserRole.OWNER,
                status=UserStatus.ACTIVE,
                last_login_at=_now(),
            )
            session.add(tenant)
            await session.flush()  # tenant row must exist before rows that reference it
            session.add_all([user, Business(tenant_id=tenant_id, company_name=req.company_name)])
            await session.flush()
            auth_session = self._new_session(user, client)
            session.add(auth_session)
            audit.record(
                session,
                tenant_id=tenant_id,
                actor_user_id=user.id,
                action="tenant.signup",
                target_type="tenant",
                target_id=tenant_id,
            )
            try:
                await session.commit()
            except IntegrityError as exc:
                # Race: the same email signed up between the check and the insert.
                if "uq_users_email_lower" in str(exc):
                    raise Conflict(
                        "email_taken", "An account with this email already exists"
                    ) from exc
                raise
            access, refresh = self._issue_tokens(user, auth_session)
            return IssuedSession(user, tenant, access, refresh)

    async def login(self, req: LoginRequest, client: ClientInfo) -> IssuedSession:
        ids = await self._lookup_user_ids(req.email)
        if ids is None:
            await verify_password(None, req.password)  # equalise timing
            raise Unauthorized(BAD_CREDENTIALS)
        user_id, tenant_id = ids

        async with self._db.tenant_session(tenant_id) as session:
            user = (
                await session.execute(select(User).where(User.id == user_id).with_for_update())
            ).scalar_one()
            tenant = await session.get_one(Tenant, tenant_id)
            now = _now()

            if user.locked_until and user.locked_until > now:
                await verify_password(None, req.password)
                raise AppError(429, "account_locked", "Too many failed attempts. Try again later.")

            if not await verify_password(user.password_hash, req.password):
                user.failed_login_count += 1
                locked = user.failed_login_count >= self._settings.max_failed_logins
                if locked:
                    user.locked_until = now + timedelta(minutes=self._settings.lockout_minutes)
                    user.failed_login_count = 0
                audit.record(
                    session,
                    tenant_id=tenant_id,
                    actor_user_id=user.id,
                    action="auth.login_failed",
                    details={"locked": locked},
                )
                await session.commit()
                raise Unauthorized(BAD_CREDENTIALS)

            if user.status != UserStatus.ACTIVE or tenant.status != TenantStatus.ACTIVE:
                raise Forbidden("This account is disabled")

            user.failed_login_count = 0
            user.locked_until = None
            user.last_login_at = now
            if needs_rehash(user.password_hash):
                user.password_hash = await hash_password(req.password)
            auth_session = self._new_session(user, client)
            session.add(auth_session)
            audit.record(session, tenant_id=tenant_id, actor_user_id=user.id, action="auth.login")
            await session.commit()
            access, refresh = self._issue_tokens(user, auth_session)
            return IssuedSession(user, tenant, access, refresh)

    async def refresh(self, refresh_token: str) -> IssuedSession:
        claims = self._decode(refresh_token, TokenType.REFRESH)
        async with self._db.tenant_session(claims.tenant_id) as session:
            auth_session = (
                await session.execute(
                    select(AuthSession).where(AuthSession.id == claims.session_id).with_for_update()
                )
            ).scalar_one_or_none()
            now = _now()
            if (
                auth_session is None
                or auth_session.revoked_at is not None
                or auth_session.expires_at <= now
            ):
                raise Unauthorized("Session expired")

            if auth_session.current_jti != claims.jti:
                # An already-used refresh token: assume it was stolen. Kill the session.
                auth_session.revoked_at = now
                audit.record(
                    session,
                    tenant_id=claims.tenant_id,
                    actor_user_id=claims.user_id,
                    action="auth.refresh_reuse_detected",
                    target_type="auth_session",
                    target_id=auth_session.id,
                )
                await session.commit()
                raise Unauthorized("Session expired")

            user = await session.get_one(User, auth_session.user_id)
            tenant = await session.get_one(Tenant, claims.tenant_id)
            if user.status != UserStatus.ACTIVE or tenant.status != TenantStatus.ACTIVE:
                raise Unauthorized("Session expired")

            auth_session.current_jti = uuid.uuid4()
            await session.commit()
            access, refresh = self._issue_tokens(user, auth_session)
            return IssuedSession(user, tenant, access, refresh)

    async def logout(self, token: str, token_type: TokenType) -> None:
        try:
            claims = self._decode(token, token_type)
        except Unauthorized:
            return  # already invalid: nothing to revoke
        async with self._db.tenant_session(claims.tenant_id) as session:
            auth_session = await session.get(AuthSession, claims.session_id)
            if auth_session and auth_session.revoked_at is None:
                auth_session.revoked_at = _now()
                audit.record(
                    session,
                    tenant_id=claims.tenant_id,
                    actor_user_id=claims.user_id,
                    action="auth.logout",
                )
                await session.commit()

    async def authenticate(self, access_token: str, session: AsyncSession) -> CurrentUser:
        """Resolve an access token to a live user. ``session`` must be scoped to the
        token's tenant (see deps.py). Checks the session isn't revoked, so logout is
        immediate rather than waiting for the access token to expire."""
        claims = self._decode(access_token, TokenType.ACCESS)
        row = (
            await session.execute(
                select(User, Tenant, AuthSession.revoked_at)
                .join(Tenant, Tenant.id == User.tenant_id)
                .join(AuthSession, AuthSession.user_id == User.id)
                .where(User.id == claims.user_id, AuthSession.id == claims.session_id)
            )
        ).first()
        if row is None:
            raise Unauthorized()
        user, tenant, revoked_at = row
        if (
            revoked_at is not None
            or user.status != UserStatus.ACTIVE
            or tenant.status != TenantStatus.ACTIVE
        ):
            raise Unauthorized()
        return CurrentUser(user=user, tenant=tenant, session_id=claims.session_id)

    def peek_tenant(self, access_token: str) -> uuid.UUID:
        """Tenant ID from a verified access token, used to scope the request's DB session."""
        return self._decode(access_token, TokenType.ACCESS).tenant_id

    def _decode(self, token: str, token_type: TokenType) -> TokenClaims:
        try:
            return decode_token(token, secret=self._secret, expected_type=token_type)
        except InvalidTokenError as exc:
            raise Unauthorized("Session expired") from exc
