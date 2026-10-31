"""Structured logging setup based on structlog."""

import logging
import sys
from typing import Any

import structlog
from structlog.typing import FilteringBoundLogger

from src.core.config import Settings, get_settings


def _resolve_level(level_name: str) -> int:
    level = logging.getLevelName(level_name.upper())
    return level if isinstance(level, int) else logging.INFO


def _build_processors(is_production: bool) -> list[Any]:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if is_production:
        processors.append(structlog.processors.JSONRenderer(sort_keys=True))
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()))
    return processors


def configure_logging(settings: Settings | None = None) -> None:
    """Configure structlog and the stdlib root logger.

    JSON output is used in production so logs can be shipped to a collector,
    a human-readable console renderer is used everywhere else.
    """
    settings = settings or get_settings()
    level = _resolve_level(settings.log_level)

    structlog.configure(
        processors=_build_processors(settings.is_production),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
