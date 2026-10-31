"""Tests for the authentication service."""

from collections.abc import Callable
from uuid import uuid4

import pytest

from src.core.config import Settings
from src.core.security import decode_access_token, verify_password
from src.repositories.user_repository import User
from src.services.auth_service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidEmailError,
    WeakPasswordError,
)

PASSWORD = "strong-password"


class InMemoryUserRepository:
    """Minimal in-memory implementation of the UserRepository contract."""

    def __init__(self) -> None:
        self.users: dict[str, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return next((user for user in self.users.values() if user.email == email), None)

    async def get_by_id(self, user_id: str) -> User | None:
        return self.users.get(user_id)

    async def create(self, *, email: str, hashed_password: str) -> User:
        user = User(id=uuid4().hex, email=email, hashed_password=hashed_password)
        self.users[user.id] = user
        return user


@pytest.fixture
def repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def service(
    repository: InMemoryUserRepository,
    make_settings: Callable[..., Settings],
) -> AuthService:
    return AuthService(repository, make_settings())


async def test_register_stores_normalised_email_and_hash(service: AuthService) -> None:
    user = await service.register("  User@Example.COM ", PASSWORD)

    assert user.email == "user@example.com"
    assert user.hashed_password != PASSWORD
    assert verify_password(PASSWORD, user.hashed_password) is True
    assert user.is_active is True


async def test_duplicate_email_is_rejected(service: AuthService) -> None:
    await service.register("user@example.com", PASSWORD)

    with pytest.raises(EmailAlreadyRegisteredError):
        await service.register("USER@example.com", PASSWORD)


@pytest.mark.parametrize("email", ["not-an-email", "user@", "@example.com", "user@example"])
async def test_invalid_email_is_rejected(service: AuthService, email: str) -> None:
    with pytest.raises(InvalidEmailError):
        await service.register(email, PASSWORD)


@pytest.mark.parametrize("password", ["short", "a" * 73])
async def test_weak_password_is_rejected(service: AuthService, password: str) -> None:
    with pytest.raises(WeakPasswordError):
        await service.register("user@example.com", password)


async def test_login_issues_token_for_registered_user(service: AuthService) -> None:
    user = await service.register("user@example.com", PASSWORD)

    result = await service.login("user@example.com", PASSWORD)

    assert result.user_id == user.id
    assert result.token_type == "bearer"
    assert result.expires_in == 3600
    payload = decode_access_token(result.access_token)
    assert payload["sub"] == user.id
    assert payload["email"] == "user@example.com"


async def test_login_with_wrong_password_is_rejected(service: AuthService) -> None:
    await service.register("user@example.com", PASSWORD)

    with pytest.raises(InvalidCredentialsError):
        await service.login("user@example.com", "another-password")


async def test_login_with_unknown_user_is_rejected(service: AuthService) -> None:
    with pytest.raises(InvalidCredentialsError):
        await service.login("nobody@example.com", PASSWORD)


async def test_inactive_user_cannot_log_in(
    service: AuthService,
    repository: InMemoryUserRepository,
) -> None:
    user = await service.register("user@example.com", PASSWORD)
    repository.users[user.id] = User(
        id=user.id,
        email=user.email,
        hashed_password=user.hashed_password,
        is_active=False,
    )

    with pytest.raises(InactiveUserError):
        await service.login("user@example.com", PASSWORD)
