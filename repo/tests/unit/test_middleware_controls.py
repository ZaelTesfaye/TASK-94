"""Unit tests for security middleware controls that are bypassed in integration tests.

These tests exercise the actual middleware functions directly so that TLS
enforcement, request signing, and rate limiting have static test coverage
independent of the ``TESTING`` flag.
"""

import hashlib
import hmac
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.app import create_app
from src.models.base import db as _db


@pytest.fixture(scope="module")
def app():
    """Create a real (non-testing) app for middleware tests."""
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


# ─── TLS Enforcement ───────────────────────────────────────────────────

class TestTLSEnforcement:
    """Test the TLS enforcement middleware function directly."""

    def test_rejects_http_when_tls_enabled(self, app, db):
        """When ENABLE_TLS is true the before_request hook must reject non-HTTPS."""
        from src.config import config

        original_tls = config.ENABLE_TLS
        original_db = config.DATABASE_URL
        try:
            config.ENABLE_TLS = True
            config.DATABASE_URL = "sqlite:///:memory:"
            # Build a non-testing app to avoid the TESTING bypass
            test_app = create_app(testing=False)
            test_app.config["TESTING"] = False

            with test_app.test_client() as c:
                resp = c.get("/health")
                # The request comes in as http (no X-Forwarded-Proto),
                # so TLS enforcement should reject it.
                assert resp.status_code == 403
                body = resp.get_json()
                assert body["error"]["code"] == "TLS_REQUIRED"
        finally:
            config.ENABLE_TLS = original_tls
            config.DATABASE_URL = original_db

    def test_allows_https_via_forwarded_proto(self, app, db):
        """When X-Forwarded-Proto is https, TLS enforcement passes."""
        from src.config import config

        original_tls = config.ENABLE_TLS
        original_db = config.DATABASE_URL
        try:
            config.ENABLE_TLS = True
            config.DATABASE_URL = "sqlite:///:memory:"
            test_app = create_app(testing=False)
            test_app.config["TESTING"] = False

            with test_app.test_client() as c:
                resp = c.get("/health", headers={"X-Forwarded-Proto": "https"})
                # Should pass TLS check; may still fail on signing,
                # so accept 401 (signature missing) or 200 as success.
                assert resp.status_code in (200, 401)
        finally:
            config.ENABLE_TLS = original_tls
            config.DATABASE_URL = original_db


# ─── Request Signing ───────────────────────────────────────────────────

class TestRequestSigning:
    """Test the verify_request_signature function directly."""

    def test_rejects_missing_headers(self, app, db):
        """Requests without signature headers are rejected."""
        from src.security.signing import verify_request_signature

        with app.test_request_context("/test", method="GET"):
            from flask import request
            is_valid, error_code = verify_request_signature(request)
            assert is_valid is False
            assert error_code == "MISSING_SIGNATURE_HEADERS"

    def test_rejects_expired_timestamp(self, app, db):
        """Requests with a timestamp outside the allowed skew are rejected."""
        from src.security.signing import verify_request_signature

        old_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with app.test_request_context(
            "/test", method="GET",
            headers={
                "X-Timestamp": old_time,
                "X-Nonce": uuid.uuid4().hex,
                "X-Signature": "dummy",
            },
        ):
            from flask import request
            is_valid, error_code = verify_request_signature(request)
            assert is_valid is False
            assert error_code == "TIMESTAMP_EXPIRED"

    def test_rejects_invalid_signature(self, app, db):
        """Requests with wrong signature value are rejected."""
        from src.security.signing import verify_request_signature

        now = datetime.now(timezone.utc).isoformat()
        with app.test_request_context(
            "/test", method="GET",
            headers={
                "X-Timestamp": now,
                "X-Nonce": uuid.uuid4().hex,
                "X-Signature": "bad_signature_value",
            },
        ):
            from flask import request
            is_valid, error_code = verify_request_signature(request)
            assert is_valid is False
            assert error_code == "INVALID_SIGNATURE"

    def test_accepts_valid_signature(self, app, db):
        """A correctly signed request is accepted."""
        from src.security.signing import verify_request_signature
        from src.config import config

        now = datetime.now(timezone.utc).isoformat()
        nonce = uuid.uuid4().hex
        method = "GET"
        path = "/test"
        body = b""
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"{method}:{path}:{now}:{nonce}:{body_hash}"
        signature = hmac.new(
            config.REQUEST_SIGNING_SECRET.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        with app.test_request_context(
            path, method=method,
            headers={
                "X-Timestamp": now,
                "X-Nonce": nonce,
                "X-Signature": signature,
            },
        ):
            from flask import request
            is_valid, error_code = verify_request_signature(request)
            assert is_valid is True
            assert error_code is None

    def test_rejects_replayed_nonce(self, app, db):
        """The same nonce used twice is rejected."""
        from src.security.signing import verify_request_signature
        from src.config import config

        now = datetime.now(timezone.utc).isoformat()
        nonce = uuid.uuid4().hex
        method = "GET"
        path = "/test-replay"
        body = b""
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"{method}:{path}:{now}:{nonce}:{body_hash}"
        signature = hmac.new(
            config.REQUEST_SIGNING_SECRET.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        with app.test_request_context(
            path, method=method,
            headers={
                "X-Timestamp": now,
                "X-Nonce": nonce,
                "X-Signature": signature,
            },
        ):
            from flask import request
            # First call — accepted
            is_valid, _ = verify_request_signature(request)
            assert is_valid is True

        # Second call with same nonce
        with app.test_request_context(
            path, method=method,
            headers={
                "X-Timestamp": now,
                "X-Nonce": nonce,
                "X-Signature": signature,
            },
        ):
            from flask import request
            is_valid, error_code = verify_request_signature(request)
            assert is_valid is False
            assert error_code == "NONCE_REPLAYED"


# ─── Rate Limiting ─────────────────────────────────────────────────────

class TestRateLimiting:
    """Test the token-bucket rate limiter function directly."""

    def test_allows_within_limit(self, app, db):
        """Requests within burst limit are allowed."""
        from src.security.rate_limiter import check_rate_limit

        bucket_key = f"test:allow:{uuid.uuid4().hex}"
        allowed, headers = check_rate_limit(bucket_key, max_tokens=5, refill_rate=60)
        assert allowed is True
        assert int(headers["X-RateLimit-Remaining"]) >= 0

    def test_rejects_when_exhausted(self, app, db):
        """Requests are blocked once all tokens are consumed."""
        from src.security.rate_limiter import check_rate_limit

        bucket_key = f"test:exhaust:{uuid.uuid4().hex}"
        # Consume all tokens (bucket starts with max_tokens, first call takes 1)
        for _ in range(3):
            allowed, _ = check_rate_limit(bucket_key, max_tokens=3, refill_rate=60)

        # Next request should be denied
        allowed, headers = check_rate_limit(bucket_key, max_tokens=3, refill_rate=60)
        assert allowed is False
        assert int(headers["Retry-After"]) > 0

    def test_burst_capacity_matches_max_tokens(self, app, db):
        """The burst capacity should equal max_tokens, not refill_rate."""
        from src.security.rate_limiter import check_rate_limit

        bucket_key = f"test:burst:{uuid.uuid4().hex}"
        burst = 5

        # Should be able to make exactly `burst` requests
        for i in range(burst):
            allowed, _ = check_rate_limit(bucket_key, max_tokens=burst, refill_rate=60)
            assert allowed is True, f"Request {i+1} should be allowed (burst={burst})"

        # Request burst+1 should be denied
        allowed, _ = check_rate_limit(bucket_key, max_tokens=burst, refill_rate=60)
        assert allowed is False

    def test_per_identity_bucket_isolation(self, app, db):
        """Different bucket keys are independent."""
        from src.security.rate_limiter import check_rate_limit

        key_a = f"user:a:{uuid.uuid4().hex}"
        key_b = f"user:b:{uuid.uuid4().hex}"

        # Exhaust key_a
        for _ in range(2):
            check_rate_limit(key_a, max_tokens=2, refill_rate=60)
        allowed_a, _ = check_rate_limit(key_a, max_tokens=2, refill_rate=60)
        assert allowed_a is False

        # key_b should still be fine
        allowed_b, _ = check_rate_limit(key_b, max_tokens=2, refill_rate=60)
        assert allowed_b is True
