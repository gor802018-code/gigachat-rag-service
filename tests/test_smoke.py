"""Smoke tests for the project skeleton."""

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.main import app, create_app

LAYER_PACKAGES = [
    "src",
    "src.api",
    "src.api.routers",
    "src.core",
    "src.ingestion",
    "src.rag",
    "src.repositories",
    "src.services",
]


@pytest.mark.parametrize("module_name", LAYER_PACKAGES)
def test_layer_package_is_importable(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None


def test_create_app_returns_fastapi_instance() -> None:
    assert isinstance(create_app(), FastAPI)


def test_health_endpoint_returns_ok() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
