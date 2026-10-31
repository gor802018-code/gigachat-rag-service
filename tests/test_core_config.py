"""Tests for the application settings."""

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core.config import DEV_JWT_SECRET, Settings, get_settings


def test_defaults_are_development_friendly(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings()

    assert settings.app_env == "development"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.log_level == "INFO"
    assert settings.is_production is False
    assert settings.chunk_size == 1000
    assert settings.chunk_overlap == 200
    assert settings.retriever_top_k == 4
    assert settings.upload_limit_bytes == 20 * 1024 * 1024


def test_secret_values_are_masked(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings(gigachat_credentials="client-id:client-secret")

    assert str(settings.gigachat_credentials) == "**********"
    assert settings.gigachat_credentials is not None
    assert settings.gigachat_credentials.get_secret_value() == "client-id:client-secret"


def test_environment_variables_override_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHUNK_SIZE", "500")
    monkeypatch.setenv("CHUNK_OVERLAP", "50")
    monkeypatch.setenv("RETRIEVER_TOP_K", "8")
    monkeypatch.setenv("FAISS_INDEX_PATH", "./tmp/index")

    settings = Settings(_env_file=None)

    assert settings.chunk_size == 500
    assert settings.chunk_overlap == 50
    assert settings.retriever_top_k == 8
    assert settings.faiss_index_path == Path("tmp/index")


def test_overlap_must_be_smaller_than_chunk_size(make_settings: Callable[..., Settings]) -> None:
    with pytest.raises(ValidationError, match="CHUNK_OVERLAP"):
        make_settings(chunk_size=100, chunk_overlap=100)


def test_production_requires_custom_jwt_secret(make_settings: Callable[..., Settings]) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        make_settings(app_env="production")


def test_production_accepts_custom_jwt_secret(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings(
        app_env="production",
        jwt_secret_key="a-strong-production-secret",
        gigachat_credentials="client-id:client-secret",
    )

    assert settings.is_production is True
    assert settings.jwt_secret_key.get_secret_value() != DEV_JWT_SECRET


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
