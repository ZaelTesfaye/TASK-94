"""Unit tests for JWT token service."""
import pytest
import jwt as pyjwt
from datetime import datetime, timedelta, timezone

from src.security.tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
)
from src.config import config


@pytest.fixture(autouse=True)
def _app_context(app):
    """Ensure Flask app context is active for all tests in this module."""
    with app.app_context():
        yield


def test_create_access_token_has_required_claims():
    """Access token should contain sub, username, role, jti, iat, exp, iss."""
    token = create_access_token(
        user_id="user-123",
        username="testuser",
        role="member",
    )
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["username"] == "testuser"
    assert payload["role"] == "member"
    assert "jti" in payload
    assert "iat" in payload
    assert "exp" in payload
    assert payload["iss"] == config.JWT_ISSUER


def test_create_refresh_token_has_type_claim():
    """Refresh token should contain type='refresh'."""
    token = create_refresh_token(user_id="user-456")
    payload = decode_token(token)
    assert payload is not None
    assert payload["type"] == "refresh"


def test_decode_expired_token_returns_none():
    """An expired token should decode to None."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "user-789",
        "jti": "test-jti",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
        "iss": config.JWT_ISSUER,
    }
    token = pyjwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
    result = decode_token(token)
    assert result is None


def test_decode_invalid_token_returns_none():
    """A garbage string should decode to None."""
    result = decode_token("this.is.not.a.valid.jwt")
    assert result is None


def test_hash_token_consistent():
    """Hashing the same token twice should produce the same result."""
    token = "some-token-value"
    assert hash_token(token) == hash_token(token)


def test_hash_token_different_inputs():
    """Different tokens should produce different hashes."""
    assert hash_token("token-a") != hash_token("token-b")
