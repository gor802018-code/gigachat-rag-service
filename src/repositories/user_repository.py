"""User persistence contract and the domain entity shared by services."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class User:
    """Domain user (never carries the plaintext password)."""

    id: str
    email: str
    hashed_password: str
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class DuplicateEmailError(RuntimeError):
    """Raised by a repository when the unique email constraint is violated."""


@runtime_checkable
class UserRepository(Protocol):
    """Storage contract implemented by the SQLAlchemy repository."""

    async def get_by_email(self, email: str) -> User | None:
        """Return a user with the given (already normalised) email."""
        ...

    async def get_by_id(self, user_id: str) -> User | None:
        """Return a user by id."""
        ...

    async def create(self, *, email: str, hashed_password: str) -> User:
        """Persist a new user and return it with a generated id."""
        ...
