"""Chat history storage."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.db_models import ChatMessageModel


@dataclass(frozen=True, slots=True)
class ChatMessageRecord:
    id: str
    user_id: str
    question: str
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime | None = None


class SQLAlchemyChatRepository:
    """Stores question/answer pairs used to render the chat history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        user_id: str,
        question: str,
        answer: str,
        sources: list[dict[str, Any]],
    ) -> ChatMessageRecord:
        model = ChatMessageModel(
            id=uuid4().hex,
            user_id=user_id,
            question=question,
            answer=answer,
            sources=sources,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_record(model)

    async def history(self, user_id: str, limit: int = 20) -> list[ChatMessageRecord]:
        result = await self._session.execute(
            select(ChatMessageModel)
            .where(ChatMessageModel.user_id == user_id)
            .order_by(ChatMessageModel.created_at.desc())
            .limit(limit)
        )
        return [self._to_record(model) for model in result.scalars().all()]

    @staticmethod
    def _to_record(model: ChatMessageModel) -> ChatMessageRecord:
        return ChatMessageRecord(
            id=model.id,
            user_id=model.user_id,
            question=model.question,
            answer=model.answer,
            sources=list(model.sources or []),
            created_at=model.created_at,
        )
