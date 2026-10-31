"""SQLAlchemy implementation of the user storage contract."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.db_models import UserModel
from src.repositories.user_repository import DuplicateEmailError, User


class SQLAlchemyUserRepository:
    """Persists users in PostgreSQL (or SQLite in tests)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(UserModel).where(UserModel.email == email))
        model = result.scalar_one_or_none()
        return None if model is None else self._to_domain(model)

    async def get_by_id(self, user_id: str) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return None if model is None else self._to_domain(model)

    async def create(self, *, email: str, hashed_password: str) -> User:
        model = UserModel(id=uuid4().hex, email=email, hashed_password=hashed_password)
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            msg = f"Email already registered: {email}"
            raise DuplicateEmailError(msg) from exc
        await self._session.refresh(model)
        return self._to_domain(model)

    @staticmethod
    def _to_domain(model: UserModel) -> User:
        return User(
            id=model.id,
            email=model.email,
            hashed_password=model.hashed_password,
            is_active=model.is_active,
            created_at=model.created_at,
        )
