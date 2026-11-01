"""ASGI entry point for the RAG service."""

from fastapi import FastAPI

from src.api.errors import register_exception_handlers
from src.api.routers import auth, chat
from src.api.schemas import HealthResponse
from src.core.config import Settings, get_settings
from src.core.logging import configure_logging, get_logger

APP_NAME = "RAG Service"
APP_VERSION = "0.1.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = settings or get_settings()
    configure_logging(settings)
    logger = get_logger(__name__)

    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description="Retrieval-Augmented Generation service over your own documents.",
    )
    register_exception_handlers(app)

    app.include_router(auth.router, prefix=settings.api_v1_prefix)
    app.include_router(chat.router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["system"], response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Liveness probe used by Docker and CI."""
        return HealthResponse(status="ok")

    logger.info("application_configured", api_prefix=settings.api_v1_prefix)
    return app


app = create_app()
