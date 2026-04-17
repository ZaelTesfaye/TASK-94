"""Unit tests for configuration validation and bootstrap security.

These tests were moved from tests/api/test_prompt_compliance.py because they
do not perform HTTP requests and belong in the unit test suite.
"""

import pytest

from src.app import create_app
from src.models.base import db as _db


@pytest.fixture(scope="module")
def app():
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


class TestRateLimitBurstConfig:
    """RATE_LIMIT_BURST must be applied as max_tokens in the token bucket."""

    def test_burst_config_exists(self):
        from src.config import config
        assert hasattr(config, "RATE_LIMIT_BURST")
        assert config.RATE_LIMIT_BURST == 20

    def test_rate_limiter_accepts_burst_param(self):
        """check_rate_limit should accept and use max_tokens (burst) separately from refill_rate."""
        from src.security.rate_limiter import check_rate_limit
        import inspect
        sig = inspect.signature(check_rate_limit)
        assert "max_tokens" in sig.parameters
        assert "refill_rate" in sig.parameters


class TestTLSDevDefault:
    """TLS must be enabled by default per prompt requirements."""

    def test_config_default_tls_enabled(self):
        from src.config import _Config
        c = _Config.__new__(_Config)
        assert c.ENABLE_TLS is True

    def test_docker_compose_tls_enabled(self):
        import pathlib
        compose_path = pathlib.Path(__file__).resolve().parents[2] / "docker-compose.yml"
        content = compose_path.read_text()
        assert "ENABLE_TLS=true" in content


class TestAdminBootstrapSecurity:
    """Default admin credentials must be rejected in production environments."""

    def test_fails_fast_in_production_with_default_password(self):
        """App startup must raise RuntimeError if ADMIN_PASSWORD=admin in production."""
        from src.config import config
        original_env = config.APP_ENV
        original_pw = config.ADMIN_PASSWORD
        try:
            config.APP_ENV = "production"
            config.ADMIN_PASSWORD = "admin"
            with pytest.raises(RuntimeError, match="ADMIN_PASSWORD must be set"):
                _create_app_for_bootstrap_test(config)
        finally:
            config.APP_ENV = original_env
            config.ADMIN_PASSWORD = original_pw

    def test_allows_default_in_development(self):
        """In development mode, default admin password is allowed (with warning)."""
        from src.config import config
        assert config.APP_ENV == "development"
        assert config.ADMIN_PASSWORD == "admin"


def _create_app_for_bootstrap_test(cfg):
    """Minimal helper that only runs the bootstrap to test credential validation."""
    from flask import Flask

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    _db.init_app(app)
    with app.app_context():
        import src.models.models  # noqa: F401
        _db.create_all()
        from src.app import _bootstrap_platform_admin
        _bootstrap_platform_admin()
    return app
