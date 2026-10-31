"""Static checks for the Streamlit frontend and the deployment configuration."""

import ast
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENDPOINTS = (
    "/auth/login",
    "/auth/register",
    "/chat/upload",
    "/chat/ask",
    "/chat/history",
)


def test_streamlit_app_is_valid_python() -> None:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))

    assert tree.body


def test_streamlit_app_targets_versioned_api() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert 'API_PREFIX = "/api/v1"' in source
    for endpoint in REQUIRED_ENDPOINTS:
        assert f'"{endpoint}"' in source


def test_compose_defines_required_services() -> None:
    compose: dict[str, Any] = yaml.safe_load(
        (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )

    assert set(compose["services"]) == {"api", "db", "frontend"}
    assert compose["services"]["frontend"]["environment"]["API_BASE_URL"] == "http://api:8000"
    assert "GIGACHAT_CREDENTIALS" in compose["services"]["api"]["environment"]
    assert compose["services"]["api"]["depends_on"]["db"]["condition"] == "service_healthy"


def test_compose_runs_migrations_before_api() -> None:
    compose: dict[str, Any] = yaml.safe_load(
        (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )

    command = compose["services"]["api"]["command"]
    assert "alembic upgrade head" in command
    assert "uvicorn src.main:app" in command


def test_images_run_as_non_root() -> None:
    for dockerfile in ("Dockerfile", "Dockerfile.streamlit"):
        content = (ROOT / dockerfile).read_text(encoding="utf-8")
        assert "USER app" in content, dockerfile
