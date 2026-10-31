"""Tests for password hashing and JWT helpers."""

from collections.abc import Callable
from datetime import timedelta

import pytest
from jose import jwt

from src.core.config import Settings
from src.core.security import (
    BCRYPT_MAX_PASSWORD_BYTES,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_returns_bcrypt_hash() -> None:
    hashed = hash_password("s3cret-password")

    assert hashed != "s3cret-password"
    assert hashed.startswith("$2b$")
    assert len(hashed) == 60


def test_verify_password_accepts_correct_password() -> None:
    hashed = hash_password("s3cret-password")

    assert verify_password("s3cret-password", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_hash_password_rejects_too_long_password() -> None:
    too_long = "a" * (BCRYPT_MAX_PASSWORD_BYTES + 1)

    with pytest.raises(ValueError, match="must not exceed"):
        hash_password(too_long)


def test_verify_password_returns_false_for_too_long_password() -> None:
    hashed = hash_password("s3cret-password")

    assert verify_password("a" * (BCRYPT_MAX_PASSWORD_BYTES + 1), hashed) is False


def test_verify_password_returns_false_for_malformed_hash() -> None:
    assert verify_password("s3cret-password", "not-a-bcrypt-hash") is False


def test_access_token_roundtrip(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings()

    token = create_access_token("user-42", settings=settings)
    payload = decode_access_token(token, settings=settings)

    assert payload["sub"] == "user-42"
    assert payload["type"] == "access"
    assert payload["exp"] > payload["iat"]


def test_access_token_merges_extra_claims(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings()

    token = create_access_token("user-42", extra_claims={"role": "admin"}, settings=settings)

    assert decode_access_token(token, settings=settings)["role"] == "admin"


def test_expired_token_is_rejected(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings()
    token = create_access_token(
        "user-42",
        expires_delta=timedelta(seconds=-1),
        settings=settings,
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, settings=settings)


def test_token_signed_with_other_secret_is_rejected(
    make_settings: Callable[..., Settings],
) -> None:
    issuer = make_settings(jwt_secret_key="issuer-secret")
    verifier = make_settings(jwt_secret_key="verifier-secret")
    token = create_access_token("user-42", settings=issuer)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, settings=verifier)


def test_foreign_token_type_is_rejected(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings()
    token = jwt.encode(
        {"sub": "user-42", "type": "refresh"},
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError, match="token type"):
        decode_access_token(token, settings=settings)


def test_malformed_token_is_rejected(make_settings: Callable[..., Settings]) -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-jwt", settings=make_settings())
