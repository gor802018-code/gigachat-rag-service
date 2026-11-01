"""API tests for document upload, answering and history."""

from collections.abc import Callable
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_settings
from src.core.config import Settings
from src.rag.llm_client import LLMGenerationError
from src.repositories.vector_repository import VectorIndexError
from tests.conftest import TEST_PASSWORD

UPLOAD_URL = "/api/v1/chat/upload"
ASK_URL = "/api/v1/chat/ask"
HISTORY_URL = "/api/v1/chat/history"


def upload(
    client: TestClient,
    headers: dict[str, str],
    *,
    content: bytes = "Договор поставки".encode(),
    file_name: str = "notes.txt",
    content_type: str = "text/plain",
) -> object:
    return client.post(
        UPLOAD_URL,
        headers=headers,
        files={"file": (file_name, content, content_type)},
    )


def test_upload_indexes_document(
    client: TestClient,
    auth_headers: dict[str, str],
    fake_rag_service: MagicMock,
) -> None:
    response = upload(client, auth_headers)

    assert response.status_code == 201
    assert response.json() == {
        "document_id": "doc-1",
        "file_name": "notes.txt",
        "chunks": 2,
    }
    fake_rag_service.ingest.assert_awaited_once()
    _, kwargs = fake_rag_service.ingest.call_args
    assert kwargs["user_id"]


def test_upload_requires_authentication(client: TestClient) -> None:
    response = upload(client, {})

    assert response.status_code == 401


def test_upload_rejects_unsupported_extension(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = upload(client, auth_headers, file_name="table.xlsx")

    assert response.status_code == 415


def test_upload_rejects_empty_file(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = upload(client, auth_headers, content=b"")

    assert response.status_code == 400


def test_upload_rejects_oversized_file(
    app: FastAPI,
    client: TestClient,
    auth_headers: dict[str, str],
    make_settings: Callable[..., Settings],
) -> None:
    app.dependency_overrides[get_settings] = lambda: make_settings(max_upload_size_mb=1)

    response = upload(client, auth_headers, content=b"a" * (1024 * 1024 + 1))

    assert response.status_code == 413


def test_ask_returns_answer_with_sources(
    client: TestClient,
    auth_headers: dict[str, str],
    fake_rag_service: MagicMock,
) -> None:
    response = client.post(
        ASK_URL,
        headers=auth_headers,
        json={"question": "Какой срок оплаты?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Оплата в течение 30 дней [1]."
    assert body["model"] == "GigaChat"
    assert body["usage"] == {"total_tokens": 42}
    assert body["sources"] == [
        {
            "file_name": "contract.pdf",
            "chunk_index": 0,
            "chunk_id": "doc-1:0",
            "score": 0.93,
            "page": 1,
        }
    ]
    fake_rag_service.ask.assert_awaited_once()
    args, kwargs = fake_rag_service.ask.call_args
    assert args == ("Какой срок оплаты?", None)
    assert kwargs["user_id"]


def test_ask_passes_top_k_to_service(
    client: TestClient,
    auth_headers: dict[str, str],
    fake_rag_service: MagicMock,
) -> None:
    response = client.post(
        ASK_URL,
        headers=auth_headers,
        json={"question": "Какой срок оплаты?", "top_k": 2},
    )

    assert response.status_code == 200
    _, kwargs = fake_rag_service.ask.call_args
    assert fake_rag_service.ask.call_args.args == ("Какой срок оплаты?", 2)
    assert kwargs["user_id"]


def test_ask_rejects_empty_question(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(ASK_URL, headers=auth_headers, json={"question": ""})

    assert response.status_code == 422


def test_history_returns_saved_answers(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client.post(
        ASK_URL,
        headers=auth_headers,
        json={"question": "Какой срок оплаты?"},
    )

    response = client.get(HISTORY_URL, headers=auth_headers)

    assert response.status_code == 200
    history = response.json()
    assert len(history) == 1
    assert history[0]["question"] == "Какой срок оплаты?"
    assert history[0]["sources"][0]["chunk_id"] == "doc-1:0"


def test_history_is_scoped_per_user(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client.post(ASK_URL, headers=auth_headers, json={"question": "Вопрос первого юзера"})

    client.post(
        "/api/v1/auth/register",
        json={"email": "second@example.com", "password": TEST_PASSWORD},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "second@example.com", "password": TEST_PASSWORD},
    )
    second_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get(HISTORY_URL, headers=second_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_history_rejects_invalid_limit(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.get(f"{HISTORY_URL}?limit=0", headers=auth_headers)

    assert response.status_code == 422


def test_llm_failure_is_mapped_to_502(
    client: TestClient,
    auth_headers: dict[str, str],
    fake_rag_service: MagicMock,
) -> None:
    fake_rag_service.ask.side_effect = LLMGenerationError("provider timeout")

    response = client.post(ASK_URL, headers=auth_headers, json={"question": "Вопрос"})

    assert response.status_code == 502
    assert response.json() == {"detail": "LLM provider request failed"}


def test_broken_vector_store_is_mapped_to_503(
    client: TestClient,
    auth_headers: dict[str, str],
    fake_rag_service: MagicMock,
) -> None:
    fake_rag_service.ask.side_effect = VectorIndexError("corrupted index")

    response = client.post(ASK_URL, headers=auth_headers, json={"question": "Вопрос"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Vector store is unavailable"}
