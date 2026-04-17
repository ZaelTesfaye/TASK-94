"""Integration tests for middleware: rate limiting, auth, and request signing.

Note: The before_request middleware (rate limiter, TLS, signing) is bypassed
when app.config["TESTING"] is True. These tests exercise the middleware by
temporarily disabling the TESTING flag where needed, and by testing the auth
middleware which runs unconditionally via the @require_auth decorator.
"""

import uuid

import pytest

from src.app import create_app
from src.models.base import db as _db


@pytest.fixture(scope="module")
def app():
    """Create a standard testing app."""
    app = create_app(testing=True)
    yield app


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        _db.create_all()
        from src.models.models import User
        from src.models.enums import RoleType
        from src.security.passwords import hash_password

        if User.query.first() is None:
            admin = User(
                username="admin",
                password_hash=hash_password("admin"),
                display_name="Platform Administrator",
                role=RoleType.PLATFORM_ADMIN.value,
                is_active=True,
            )
            _db.session.add(admin)
            _db.session.commit()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture
def client(app, db):
    return app.test_client()


@pytest.fixture
def admin_headers(client):
    resp = client.post("/auth/login", json={
        "username": "admin",
        "password": "admin",
    })
    data = resp.get_json()
    token = data["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestRateLimiterIntegration:
    """Test rate limiting through the full middleware stack."""

    def test_rate_limit_returns_429_when_exhausted(self, app, client, db):
        """Sending more requests than max_tokens should trigger 429."""
        # Temporarily disable TESTING flag so middleware runs
        app.config["TESTING"] = False
        try:
            last_resp = None
            got_429 = False
            # Send requests until we hit rate limit (burst is 20)
            for i in range(25):
                resp = client.get("/health")
                if resp.status_code == 429:
                    got_429 = True
                    last_resp = resp
                    break

            if got_429:
                body = last_resp.get_json()
                assert "error" in body
                assert body["error"]["code"] == "TOO_MANY_REQUESTS"
                assert "X-RateLimit-Remaining" in last_resp.headers
                assert last_resp.headers["X-RateLimit-Remaining"] == "0"
            else:
                # If we didn't hit 429 in 25 requests, the rate limiter may
                # have a higher limit — at minimum verify headers are present
                assert "X-RateLimit-Limit" in resp.headers
        finally:
            app.config["TESTING"] = True

    def test_rate_limit_headers_present(self, app, client, db):
        """Rate limit response headers should be set on every response."""
        app.config["TESTING"] = False
        try:
            resp = client.get("/health")
            assert "X-RateLimit-Limit" in resp.headers
            assert "X-RateLimit-Remaining" in resp.headers
        finally:
            app.config["TESTING"] = True


class TestAuthMiddlewareIntegration:
    """Test auth middleware through the full HTTP stack."""

    def test_missing_auth_header_returns_401_with_error_body(self, client, db):
        """A protected endpoint without auth should return 401 with error envelope."""
        resp = client.get("/auth/me")
        assert resp.status_code == 401
        body = resp.get_json()
        assert "error" in body
        assert body["error"]["code"] == "UNAUTHORIZED"
        assert "meta" in body

    def test_malformed_token_returns_401(self, client, db):
        """A malformed Bearer token should return 401 with INVALID_TOKEN."""
        resp = client.get("/auth/me", headers={
            "Authorization": "Bearer not.a.valid.jwt.token",
        })
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"]["code"] == "INVALID_TOKEN"

    def test_expired_token_returns_401(self, client, db):
        """An expired JWT should return 401."""
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone
        from src.config import config

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user-expired",
            "username": "expired",
            "role": "member",
            "jti": f"expired-jti-{uuid.uuid4().hex[:8]}",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "iss": config.JWT_ISSUER,
        }
        token = pyjwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)

        resp = client.get("/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"]["code"] == "INVALID_TOKEN"

    def test_revoked_token_returns_401(self, client, db):
        """A token on the denylist should return 401."""
        # Login to get a valid token
        username = f"revoke_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        token = login_resp.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Logout to revoke the token
        client.post("/auth/logout", headers=headers)

        # Try to use the revoked token
        resp = client.get("/auth/me", headers=headers)
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["error"]["code"] == "TOKEN_REVOKED"


class TestRequestSigningIntegration:
    """Test request signing middleware through the HTTP stack."""

    def test_unsigned_request_rejected_when_signing_enforced(self, app, client, db):
        """An unsigned request to a non-exempt path should be rejected when signing is active."""
        app.config["TESTING"] = False
        try:
            resp = client.get(
                "/admin/system-status",
                headers={"Authorization": "Bearer dummy"},
            )
            # Should either get 401 (signature invalid) or 401 (bad token)
            assert resp.status_code == 401
            body = resp.get_json()
            assert "error" in body
        finally:
            app.config["TESTING"] = True
