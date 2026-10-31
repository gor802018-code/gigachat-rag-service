"""API tests for registration and login."""

from fastapi.testclient import TestClient

from tests.conftest import TEST_EMAIL, TEST_PASSWORD

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"


def test_register_creates_user(client: TestClient) -> None:
    response = client.post(
        REGISTER_URL,
        json={"email": " New@Example.com ", "password": TEST_PASSWORD},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["is_active"] is True
    assert body["id"]
    assert "hashed_password" not in body
    assert "password" not in body


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    payload = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
    client.post(REGISTER_URL, json=payload)

    response = client.post(REGISTER_URL, json=payload)

    assert response.status_code == 409


def test_register_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        REGISTER_URL,
        json={"email": "not-an-email", "password": TEST_PASSWORD},
    )

    assert response.status_code == 422


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        REGISTER_URL,
        json={"email": "user@example.com", "password": "short"},
    )

    assert response.status_code == 422


def test_login_returns_access_token(client: TestClient) -> None:
    client.post(REGISTER_URL, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})

    response = client.post(LOGIN_URL, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["access_token"]
    assert body["user_id"]


def test_login_rejects_wrong_password(client: TestClient) -> None:
    client.post(REGISTER_URL, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})

    response = client.post(LOGIN_URL, json={"email": TEST_EMAIL, "password": "wrong-password"})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_login_rejects_unknown_user(client: TestClient) -> None:
    response = client.post(LOGIN_URL, json={"email": "nobody@example.com", "password": "whatever1"})

    assert response.status_code == 401


def test_protected_endpoint_requires_token(client: TestClient) -> None:
    response = client.get("/api/v1/chat/history")

    assert response.status_code == 401


def test_protected_endpoint_rejects_malformed_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/chat/history",
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert response.status_code == 401
