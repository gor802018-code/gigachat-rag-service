"""Shared pytest fixtures."""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.dependencies import get_db, get_rag_service
from src.core.config import Settings
from src.core.database import Base
from src.main import create_app
from src.repositories import db_models  # noqa: F401 - registers ORM models on Base
from src.services.rag_service import IngestResult, RAGAnswer, SourceRef

ENV_KEYS = (
    "APP_ENV",
    "LOG_LEVEL",
    "DATABASE_URL",
    "JWT_SECRET_KEY",
    "JWT_ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "RETRIEVER_TOP_K",
    "FAISS_INDEX_PATH",
)

TEST_EMAIL = "user@example.com"
TEST_PASSWORD = "strong-password"

INGEST_RESULT = IngestResult(document_id="doc-1", file_name="notes.txt", chunks=2)
RAG_RESULT = RAGAnswer(
    answer="Оплата в течение 30 дней [1].",
    sources=[
        SourceRef(
            file_name="contract.pdf",
            chunk_index=0,
            chunk_id="doc-1:0",
            score=0.93,
        )
    ],
    model="GigaChat",
    usage={"total_tokens": 42},
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove settings-related variables so tests start from defaults."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def make_settings(clean_env: None) -> Callable[..., Settings]:
    """Build a Settings instance without reading a local ``.env`` file."""

    def _make_settings(**overrides: object) -> Settings:
        return Settings(_env_file=None, **overrides)

    return _make_settings


@pytest.fixture
def session_factory(tmp_path: Path) -> async_sessionmaker[AsyncSession]:
    """File-based SQLite database with the production schema created."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")

    async def _create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_schema())
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def fake_rag_service() -> MagicMock:
    service = MagicMock()
    service.ingest = AsyncMock(return_value=INGEST_RESULT)
    service.ask = AsyncMock(return_value=RAG_RESULT)
    return service


@pytest.fixture
def app(
    session_factory: async_sessionmaker[AsyncSession],
    fake_rag_service: MagicMock,
) -> FastAPI:
    application = create_app()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_rag_service] = lambda: fake_rag_service
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    """Register and log in the default test user."""
    client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
