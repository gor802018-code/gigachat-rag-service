"""Shared pytest fixtures."""

from collections.abc import Callable

import pytest

from src.core.config import Settings

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
