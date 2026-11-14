"""Password hashing (Argon2id) and signed session tokens (JWT, HS256)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi.concurrency import run_in_threadpool

_hasher = PasswordHasher()  # Argon2id with the library's recommended parameters
# Verified when an email doesn't exist, so response time doesn't reveal which emails exist.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")

ISSUER = "hvac-receptionist"
ALGORITHM = "HS256"


async def hash_password(password: str) -> str:
    return await run_in_threadpool(_hasher.hash, password)


async def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-work check. Pass None for unknown users to keep timing uniform."""

    def _verify() -> bool:
        try:
            return (
                _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
            )
        except VerificationError, InvalidHashError:
            return False

    return await run_in_threadpool(_verify)


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True, slots=True)
class TokenClaims:
    type: TokenType
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    session_id: uuid.UUID
    jti: uuid.UUID
    role: str


class InvalidTokenError(Exception):
    pass


def encode_token(claims: TokenClaims, *, secret: str, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "iss": ISSUER,
        "typ": claims.type.value,
        "sub": str(claims.user_id),
        "tid": str(claims.tenant_id),
        "sid": str(claims.session_id),
        "jti": str(claims.jti),
        "role": claims.role,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, *, secret: str, expected_type: TokenType) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iat", "iss", "sub", "tid", "sid", "jti", "typ"]},
        )
        if payload["typ"] != expected_type.value:
            raise InvalidTokenError("wrong token type")
        return TokenClaims(
            type=expected_type,
            user_id=uuid.UUID(payload["sub"]),
            tenant_id=uuid.UUID(payload["tid"]),
            session_id=uuid.UUID(payload["sid"]),
            jti=uuid.UUID(payload["jti"]),
            role=str(payload.get("role", "")),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidTokenError(str(exc)) from exc
