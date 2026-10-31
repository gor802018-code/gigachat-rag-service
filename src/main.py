"""ASGI entry point for the RAG service."""

from fastapi import FastAPI

APP_NAME = "RAG Service"
APP_VERSION = "0.1.0"


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description="Retrieval-Augmented Generation service over your own documents.",
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        """Liveness probe used by Docker and CI."""
        return {"status": "ok"}

    return app


app = create_app()
