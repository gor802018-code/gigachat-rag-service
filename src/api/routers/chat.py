"""Chat endpoints: document upload, question answering and history."""

import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from src.api.dependencies import (
    get_chat_repository,
    get_current_user,
    get_document_repository,
    get_rag_service,
)
from src.api.schemas import (
    AnswerResponse,
    ChatHistoryItem,
    DocumentUploadResponse,
    QuestionRequest,
    SourceResponse,
)
from src.core.config import Settings, get_settings
from src.ingestion.loader import SUPPORTED_EXTENSIONS, DocumentLoadError
from src.repositories.chat_repository import SQLAlchemyChatRepository
from src.repositories.document_repository import SQLAlchemyDocumentRepository
from src.repositories.user_repository import User
from src.services.rag_service import RAGService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and index a document",
)
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    rag_service: RAGService = Depends(get_rag_service),
    documents: SQLAlchemyDocumentRepository = Depends(get_document_repository),
    settings: Settings = Depends(get_settings),
) -> DocumentUploadResponse:
    original_name = Path(file.filename or "upload").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {suffix or original_name}",
        )

    payload = await file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    if len(payload) > settings.upload_limit_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
        )

    with tempfile.TemporaryDirectory() as tmp_dir:
        target = Path(tmp_dir) / f"upload{suffix}"
        target.write_bytes(payload)
        try:
            result = await rag_service.ingest(target, document_id=uuid4().hex)
        except (DocumentLoadError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    await documents.create(
        document_id=result.document_id,
        user_id=user.id,
        file_name=original_name,
        chunks=result.chunks,
    )
    return DocumentUploadResponse(
        document_id=result.document_id,
        file_name=original_name,
        chunks=result.chunks,
    )


@router.post(
    "/ask", response_model=AnswerResponse, summary="Ask a question about indexed documents"
)
async def ask_question(
    payload: QuestionRequest,
    user: User = Depends(get_current_user),
    rag_service: RAGService = Depends(get_rag_service),
    chats: SQLAlchemyChatRepository = Depends(get_chat_repository),
) -> AnswerResponse:
    answer = await rag_service.ask(payload.question, payload.top_k)
    await chats.add(
        user_id=user.id,
        question=payload.question,
        answer=answer.answer,
        sources=[
            {
                "file_name": source.file_name,
                "chunk_index": source.chunk_index,
                "chunk_id": source.chunk_id,
                "score": source.score,
            }
            for source in answer.sources
        ],
    )
    return AnswerResponse.from_answer(answer)


@router.get("/history", response_model=list[ChatHistoryItem], summary="Recent question history")
async def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    chats: SQLAlchemyChatRepository = Depends(get_chat_repository),
) -> list[ChatHistoryItem]:
    messages = await chats.history(user.id, limit=limit)
    return [
        ChatHistoryItem(
            id=message.id,
            question=message.question,
            answer=message.answer,
            sources=[SourceResponse(**source) for source in message.sources],
            created_at=message.created_at,
        )
        for message in messages
    ]
