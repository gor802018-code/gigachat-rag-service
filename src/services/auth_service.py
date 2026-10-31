"""Registration, authentication and token issuing."""

import asyncio
import re
from dataclasses import dataclass
from functools import lru_cache

from src.core.config import Settings, get_settings
from src.core.security import (
    BCRYPT_MAX_PASSWORD_BYTES,
    create_access_token,
    hash_password,
    verify_password,
)
from src.repositories.user_repository import User, UserRepository

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
MIN_PASSWORD_LENGTH = 8


class AuthError(Exception):
    """Base class for authentication failures."""


class InvalidEmailError(ValueError):
    """Raised when an email address has an invalid shape."""


class WeakPasswordError(ValueError):
    """Raised when a password does not satisfy the policy."""


class EmailAlreadyRegisteredError(AuthError):
    """Raised when the email is taken."""


class InvalidCredentialsError(AuthError):
    """Raised for both unknown users and wrong passwords."""


class InactiveUserError(AuthError):
    """Raised when a deactivated account tries to log in."""


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Token payload returned by login."""

    access_token: str
    token_type: str
    expires_in: int
    user_id: str


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """Pre-computed hash used to keep unknown-user login timing constant."""
    return hash_password("dummy-password-for-timing-equalisation")


class AuthService:
    """Business logic for user registration and login."""

    def __init__(
        self,
        user_repository: UserRepository,
        settings: Settings | None = None,
    ) -> None:
        self._users = user_repository
        self._settings = settings or get_settings()

    async def register(self, email: str, password: str) -> User:
        """Create a user with a bcrypt password hash."""
        normalized_email = self._normalize_email(email)
        self._validate_password(password)

        if await self._users.get_by_email(normalized_email) is not None:
            msg = f"Email already registered: {normalized_email}"
            raise EmailAlreadyRegisteredError(msg)

        hashed_password = await asyncio.to_thread(hash_password, password)
        return await self._users.create(email=normalized_email, hashed_password=hashed_password)

    async def authenticate(self, email: str, password: str) -> User:
        """Return the user if the credentials are valid."""
        normalized_email = self._normalize_email(email)
        user = await self._users.get_by_email(normalized_email)

        if user is None:
            await asyncio.to_thread(verify_password, password, _dummy_password_hash())
            msg = "Invalid email or password"
            raise InvalidCredentialsError(msg)

        if not await asyncio.to_thread(verify_password, password, user.hashed_password):
            msg = "Invalid email or password"
            raise InvalidCredentialsError(msg)

        if not user.is_active:
            msg = "User account is deactivated"
            raise InactiveUserError(msg)

        return user

    async def login(self, email: str, password: str) -> AuthResult:
        """Authenticate the user and issue a JWT access token."""
        user = await self.authenticate(email, password)
        token = create_access_token(
            user.id,
            extra_claims={"email": user.email},
            settings=self._settings,
        )
        return AuthResult(
            access_token=token,
            token_type="bearer",
            expires_in=self._settings.access_token_expire_minutes * 60,
            user_id=user.id,
        )

    @staticmethod
    def _normalize_email(email: str) -> str:
        normalized = email.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            msg = f"Invalid email address: {email!r}"
            raise InvalidEmailError(msg)
        return normalized

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            msg = f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
            raise WeakPasswordError(msg)
        if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
            msg = f"Password must not exceed {BCRYPT_MAX_PASSWORD_BYTES} bytes"
            raise WeakPasswordError(msg)
