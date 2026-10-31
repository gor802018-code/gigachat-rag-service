"""Document metadata storage."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.db_models import DocumentModel


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    id: str
    user_id: str
    file_name: str
    chunks: int
    created_at: datetime


class SQLAlchemyDocumentRepository:
    """Stores one row per ingested document."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        document_id: str,
        user_id: str,
        file_name: str,
        chunks: int,
    ) -> DocumentRecord:
        model = DocumentModel(
            id=document_id,
            user_id=user_id,
            file_name=file_name,
            chunks=chunks,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return self._to_record(model)

    async def list_for_user(self, user_id: str, limit: int = 50) -> list[DocumentRecord]:
        result = await self._session.execute(
            select(DocumentModel)
            .where(DocumentModel.user_id == user_id)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
        )
        return [self._to_record(model) for model in result.scalars().all()]

    @staticmethod
    def _to_record(model: DocumentModel) -> DocumentRecord:
        return DocumentRecord(
            id=model.id,
            user_id=model.user_id,
            file_name=model.file_name,
            chunks=model.chunks,
            created_at=model.created_at,
        )
