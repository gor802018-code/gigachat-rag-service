"""Async database engine, session factory and declarative base."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import Settings


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the async engine for the configured database URL."""
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory with objects usable after commit."""
    return async_sessionmaker(engine, expire_on_commit=False)
