"""Password hashing and JWT helpers."""

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config import Settings, get_settings

BCRYPT_MAX_PASSWORD_BYTES = 72
ACCESS_TOKEN_TYPE = "access"

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class InvalidTokenError(Exception):
    """Raised when a JWT is malformed, expired or signed with an unknown key."""


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        msg = f"Password must not exceed {BCRYPT_MAX_PASSWORD_BYTES} bytes"
        raise ValueError(msg)
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    if len(plain_password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return False
    try:
        return _pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        return False


def create_access_token(
    subject: str,
    *,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> str:
    """Issue a signed access token for ``subject`` (usually the user id)."""
    settings = settings or get_settings()
    now = datetime.now(UTC)
    expires_at = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))

    payload: dict[str, Any] = {
        "sub": subject,
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Verify a token signature and expiry, returning its claims."""
    settings = settings or get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        msg = "Invalid or expired token"
        raise InvalidTokenError(msg) from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        msg = "Unexpected token type"
        raise InvalidTokenError(msg)
    if not payload.get("sub"):
        msg = "Token has no subject"
        raise InvalidTokenError(msg)

    return payload
