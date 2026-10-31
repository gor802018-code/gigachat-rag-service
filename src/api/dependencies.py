"""Dependency providers wired into the FastAPI routers."""

from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.api.schemas import UserResponse
from src.core.config import Settings, get_settings
from src.core.database import create_engine, create_session_factory
from src.core.security import InvalidTokenError, decode_access_token
from src.rag.embeddings import SentenceTransformerEmbedder
from src.rag.llm_client import LLMClient, create_llm_client
from src.repositories.chat_repository import SQLAlchemyChatRepository
from src.repositories.document_repository import SQLAlchemyDocumentRepository
from src.repositories.sqlalchemy_user_repository import SQLAlchemyUserRepository
from src.repositories.user_repository import User
from src.repositories.vector_repository import VectorRepository
from src.services.auth_service import AuthService
from src.services.rag_service import RAGService

bearer_scheme = HTTPBearer(auto_error=False)

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Single async engine per process."""
    return create_engine(get_settings())


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return create_session_factory(get_engine())


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


def get_user_repository(
    session: AsyncSession = Depends(get_db),
) -> SQLAlchemyUserRepository:
    return SQLAlchemyUserRepository(session)


def get_document_repository(
    session: AsyncSession = Depends(get_db),
) -> SQLAlchemyDocumentRepository:
    return SQLAlchemyDocumentRepository(session)


def get_chat_repository(
    session: AsyncSession = Depends(get_db),
) -> SQLAlchemyChatRepository:
    return SQLAlchemyChatRepository(session)


def get_auth_service(
    user_repository: SQLAlchemyUserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(user_repository, settings)


@lru_cache(maxsize=1)
def get_vector_repository() -> VectorRepository:
    """FAISS is an in-process index, so it must be a process-wide singleton."""
    settings = get_settings()
    embedder = SentenceTransformerEmbedder.from_settings(settings)
    return VectorRepository(embedder, settings.faiss_index_path)


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return create_llm_client(get_settings())


def get_rag_service(
    vector_repository: VectorRepository = Depends(get_vector_repository),
    llm_client: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
) -> RAGService:
    return RAGService.from_settings(
        vector_repository=vector_repository,
        llm_client=llm_client,
        settings=settings,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the JWT to an active user or fail with 401."""
    if credentials is None:
        raise UNAUTHORIZED

    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise UNAUTHORIZED from exc

    user = await SQLAlchemyUserRepository(session).get_by_id(payload["sub"])
    if user is None or not user.is_active:
        raise UNAUTHORIZED
    return user


def get_current_user_response(user: User = Depends(get_current_user)) -> UserResponse:
    """Convenience provider returning the API representation of the user."""
    return UserResponse.from_domain(user)
