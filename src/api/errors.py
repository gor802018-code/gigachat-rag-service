"""HTTP mapping for infrastructure exceptions."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.core.logging import get_logger
from src.rag.llm_client import LLMConfigurationError, LLMGenerationError
from src.repositories.vector_repository import VectorIndexError

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Translate provider and storage failures into 502/503 instead of bare 500s."""

    @app.exception_handler(LLMGenerationError)
    async def handle_llm_generation(_: Request, exc: LLMGenerationError) -> JSONResponse:
        logger.warning("llm_generation_failed", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "LLM provider request failed"},
        )

    @app.exception_handler(LLMConfigurationError)
    async def handle_llm_configuration(_: Request, exc: LLMConfigurationError) -> JSONResponse:
        logger.error("llm_not_configured", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "LLM provider is not configured"},
        )

    @app.exception_handler(VectorIndexError)
    async def handle_vector_store(_: Request, exc: VectorIndexError) -> JSONResponse:
        logger.error("vector_store_unavailable", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Vector store is unavailable"},
        )
