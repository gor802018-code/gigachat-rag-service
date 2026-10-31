"""Pydantic schemas for the public HTTP API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.repositories.user_repository import User
from src.services.auth_service import AuthResult
from src.services.rag_service import RAGAnswer


class UserRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, examples=["user@example.com"])
    password: str = Field(min_length=8, max_length=72, examples=["strong-password"])


class UserLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=72)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    is_active: bool
    created_at: datetime

    @classmethod
    def from_domain(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
        )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user_id: str

    @classmethod
    def from_auth_result(cls, result: AuthResult) -> "TokenResponse":
        return cls(
            access_token=result.access_token,
            token_type=result.token_type,
            expires_in=result.expires_in,
            user_id=result.user_id,
        )


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000, examples=["Какой срок оплаты?"])
    top_k: int | None = Field(default=None, ge=1, le=20)


class SourceResponse(BaseModel):
    file_name: str
    chunk_index: int | None = None
    chunk_id: str | None = None
    score: float


class AnswerResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]
    model: str
    usage: dict[str, Any] | None = None

    @classmethod
    def from_answer(cls, answer: RAGAnswer) -> "AnswerResponse":
        return cls(
            answer=answer.answer,
            sources=[
                SourceResponse(
                    file_name=source.file_name,
                    chunk_index=source.chunk_index,
                    chunk_id=source.chunk_id,
                    score=source.score,
                )
                for source in answer.sources
            ],
            model=answer.model,
            usage=answer.usage,
        )


class DocumentUploadResponse(BaseModel):
    document_id: str
    file_name: str
    chunks: int


class ChatHistoryItem(BaseModel):
    id: str
    question: str
    answer: str
    sources: list[SourceResponse]
    created_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
