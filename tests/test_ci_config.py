"""Static checks for the GitHub Actions pipeline."""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"


def load_workflow() -> dict[str, Any]:
    raw: dict[Any, Any] = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    # PyYAML resolves the bare ``on`` key to True (YAML 1.1), so normalise it.
    return {"on" if key is True else str(key): value for key, value in raw.items()}


def test_workflow_runs_on_push_and_pull_requests() -> None:
    triggers = load_workflow()["on"]

    assert "push" in triggers
    assert "pull_request" in triggers


def test_workflow_defines_lint_tests_and_docker_jobs() -> None:
    jobs = load_workflow()["jobs"]

    assert {"lint", "tests", "docker"} <= set(jobs)
    assert jobs["docker"]["needs"] == "lint"


def test_lint_job_runs_ruff() -> None:
    steps = str(load_workflow()["jobs"]["lint"]["steps"])

    assert "ruff check ." in steps
    assert "ruff format --check ." in steps


def test_tests_job_runs_pytest_with_coverage() -> None:
    job = load_workflow()["jobs"]["tests"]
    steps = str(job["steps"])

    assert "pytest" in steps
    assert "--cov=src" in steps
    assert job["env"]["APP_ENV"] == "test"


def test_docker_job_builds_both_images_and_validates_compose() -> None:
    steps = str(load_workflow()["jobs"]["docker"]["steps"])

    assert "./Dockerfile" in steps
    assert "./Dockerfile.streamlit" in steps
    assert "docker compose -f docker-compose.yml config" in steps


def test_poetry_version_is_pinned() -> None:
    workflow = load_workflow()

    assert workflow["env"]["POETRY_VERSION"] == "2.5.1"
    assert workflow["env"]["PYTHON_VERSION"] == "3.11"
