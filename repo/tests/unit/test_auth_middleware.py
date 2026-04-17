"""Unit tests for auth middleware decorators and helper functions."""

from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from src.app import create_app
from src.models.base import db as _db
from src.models.enums import RoleType


@pytest.fixture(scope="module")
def app():
    app = create_app(testing=True)
    yield app


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        _db.create_all()
        from src.models.models import User
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


# ─── require_auth ────────────────────────────────────────────────────────


class TestRequireAuth:
    def test_valid_token_passes(self, app, db):
        """A valid token should populate g.current_user and call the wrapped function."""
        from src.security.tokens import create_access_token

        with app.test_request_context():
            token = create_access_token(
                user_id="user-1", username="testuser", role="member"
            )

        from src.security.auth_middleware import require_auth

        @require_auth
        def dummy():
            from flask import g
            return {"user_id": g.current_user.user_id}, 200

        with app.test_request_context(
            headers={"Authorization": f"Bearer {token}"}
        ):
            result, status = dummy()
            assert status == 200
            assert result["user_id"] == "user-1"

    def test_expired_token_returns_401(self, app, db):
        """An expired token should return 401."""
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone
        from src.config import config

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user-2",
            "username": "expired",
            "role": "member",
            "jti": "test-jti-expired",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "iss": config.JWT_ISSUER,
        }
        token = pyjwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)

        from src.security.auth_middleware import require_auth

        @require_auth
        def dummy():
            return {"ok": True}, 200

        with app.test_request_context(
            headers={"Authorization": f"Bearer {token}"}
        ):
            resp = dummy()
            assert resp[1] == 401

    def test_missing_header_returns_401(self, app, db):
        """No Authorization header should return 401."""
        from src.security.auth_middleware import require_auth

        @require_auth
        def dummy():
            return {"ok": True}, 200

        with app.test_request_context():
            resp = dummy()
            assert resp[1] == 401


# ─── require_role ────────────────────────────────────────────────────────


class TestRequireRole:
    def test_sufficient_role_passes(self, app, db):
        """A platform_admin should pass a require_role('org_admin') check."""
        from flask import g
        from src.security.auth_middleware import require_role

        @require_role(RoleType.ORG_ADMIN.value)
        def dummy():
            return {"ok": True}, 200

        with app.test_request_context():
            from src.models.models import User
            admin_user = User.query.filter_by(username="admin").first()
            g.current_user = SimpleNamespace(
                user_id=admin_user.id,
                username="admin",
                role=RoleType.PLATFORM_ADMIN.value,
                organization_id=None,
                permissions=[],
                jti="test-jti",
            )
            result, status = dummy()
            assert status == 200

    def test_insufficient_role_returns_403(self, app, db):
        """A guest should be rejected by require_role('org_admin')."""
        from flask import g
        from src.security.auth_middleware import require_role
        from src.models.models import User
        from src.security.passwords import hash_password

        with app.test_request_context():
            # Create a guest user
            guest = User(
                username="guestuser",
                password_hash=hash_password("GuestPass1!"),
                role=RoleType.GUEST.value,
                is_active=True,
            )
            db.session.add(guest)
            db.session.commit()

            g.current_user = SimpleNamespace(
                user_id=guest.id,
                username="guestuser",
                role=RoleType.GUEST.value,
                organization_id=None,
                permissions=[],
                jti="test-jti-guest",
            )

            @require_role(RoleType.ORG_ADMIN.value)
            def dummy():
                return {"ok": True}, 200

            resp = dummy()
            assert resp[1] == 403


# ─── check_object_ownership & verify_org_scope ───────────────────────────


class TestOwnershipHelpers:
    def test_platform_admin_owns_everything(self, app, db):
        from flask import g
        from src.security.auth_middleware import check_object_ownership

        with app.test_request_context():
            g.current_user = SimpleNamespace(
                user_id="admin-id",
                role=RoleType.PLATFORM_ADMIN.value,
                organization_id=None,
            )
            obj = SimpleNamespace(user_id="other-user", organization_id="org-1")
            assert check_object_ownership(obj) is True

    def test_direct_owner_passes(self, app, db):
        from flask import g
        from src.security.auth_middleware import check_object_ownership

        with app.test_request_context():
            g.current_user = SimpleNamespace(
                user_id="user-1",
                role=RoleType.MEMBER.value,
                organization_id="org-1",
            )
            obj = SimpleNamespace(user_id="user-1", organization_id="org-1")
            assert check_object_ownership(obj) is True

    def test_non_owner_fails(self, app, db):
        from flask import g
        from src.security.auth_middleware import check_object_ownership

        with app.test_request_context():
            g.current_user = SimpleNamespace(
                user_id="user-1",
                role=RoleType.MEMBER.value,
                organization_id="org-1",
            )
            obj = SimpleNamespace(user_id="user-2", organization_id="org-2")
            assert check_object_ownership(obj) is False

    def test_verify_org_scope_matching(self, app, db):
        from flask import g
        from src.security.auth_middleware import verify_org_scope

        with app.test_request_context():
            g.current_user = SimpleNamespace(
                user_id="user-1",
                role=RoleType.ORG_ADMIN.value,
                organization_id="org-1",
            )
            assert verify_org_scope("org-1") is True
            assert verify_org_scope("org-2") is False
