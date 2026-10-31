"""Tests for the structlog configuration."""

from collections.abc import Callable

import structlog
from structlog.testing import capture_logs

from src.core.config import Settings
from src.core.logging import configure_logging, get_logger


def test_production_uses_json_renderer(make_settings: Callable[..., Settings]) -> None:
    configure_logging(make_settings(app_env="production", jwt_secret_key="production-secret"))

    processors = structlog.get_config()["processors"]

    assert isinstance(processors[-1], structlog.processors.JSONRenderer)


def test_development_uses_console_renderer(make_settings: Callable[..., Settings]) -> None:
    configure_logging(make_settings())

    processors = structlog.get_config()["processors"]

    assert isinstance(processors[-1], structlog.dev.ConsoleRenderer)


def test_logger_returns_structured_event(make_settings: Callable[..., Settings]) -> None:
    configure_logging(make_settings())
    logger = get_logger("tests.logging")

    with capture_logs() as logs:
        logger.info("document_indexed", document_id="doc-1", chunks=3)

    assert logs == [
        {
            "event": "document_indexed",
            "document_id": "doc-1",
            "chunks": 3,
            "log_level": "info",
        }
    ]


def test_debug_is_filtered_by_log_level(make_settings: Callable[..., Settings]) -> None:
    configure_logging(make_settings(log_level="WARNING"))
    logger = get_logger("tests.logging")

    with capture_logs() as logs:
        logger.debug("should_not_appear")
        logger.warning("should_appear")

    assert [entry["event"] for entry in logs] == ["should_appear"]
