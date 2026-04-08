"""
Flask application factory for the Learning & Resource Booking Governance API.
"""

import uuid
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request

from src.config import config
from src.logging import logger
from src.models.base import db


def create_app(testing: bool = False) -> Flask:
    """Application factory.

    Args:
        testing: When True, uses in-memory SQLite and disables the scheduler.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__)

    # --- Configuration ---
    if testing:
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["TESTING"] = True
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = config.SECRET_KEY

    # --- Extensions ---
    db.init_app(app)

    # --- Blueprints ---
    from src.api import (
        auth_bp,
        permissions_bp,
        invitations_bp,
        booking_bp,
        content_bp,
        analytics_bp,
        audit_bp,
        admin_bp,
        health_bp,
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(permissions_bp)
    app.register_blueprint(invitations_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(content_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(health_bp)

    # --- Error Handlers ---
    _register_error_handlers(app)

    # --- Request Middleware ---
    _register_before_request(app)
    _register_after_request(app)

    # --- Create Tables & Bootstrap ---
    with app.app_context():
        # Import models so SQLAlchemy sees them
        import src.models.models  # noqa: F401

        db.create_all()
        _bootstrap_platform_admin()

    # --- Scheduler ---
    if not testing:
        try:
            from src.scheduler import init_scheduler
            init_scheduler(app)
        except (ImportError, AttributeError):
            logger.warning("app", "scheduler", "Scheduler not initialized (module missing or incomplete)")

    return app


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

SENSITIVE_ROUTE_PREFIXES = ("/auth", "/admin")


def _register_error_handlers(app: Flask) -> None:
    """Register global JSON error handlers."""

    @app.errorhandler(400)
    def bad_request(exc):
        return _error_envelope("BAD_REQUEST", str(exc), 400)

    @app.errorhandler(401)
    def unauthorized(exc):
        return _error_envelope("UNAUTHORIZED", "Authentication required.", 401)

    @app.errorhandler(403)
    def forbidden(exc):
        return _error_envelope("FORBIDDEN", "Insufficient permissions.", 403)

    @app.errorhandler(404)
    def not_found(exc):
        return _error_envelope("NOT_FOUND", "Resource not found.", 404)

    @app.errorhandler(405)
    def method_not_allowed(exc):
        return _error_envelope("METHOD_NOT_ALLOWED", "Method not allowed.", 405)

    @app.errorhandler(409)
    def conflict(exc):
        return _error_envelope("CONFLICT", str(exc), 409)

    @app.errorhandler(422)
    def unprocessable(exc):
        return _error_envelope("UNPROCESSABLE_ENTITY", str(exc), 422)

    @app.errorhandler(429)
    def too_many_requests(exc):
        return _error_envelope("TOO_MANY_REQUESTS", "Rate limit exceeded.", 429)

    @app.errorhandler(500)
    def internal_error(exc):
        logger.error("app", "unhandled", f"Internal server error: {exc}")
        return _error_envelope("INTERNAL_SERVER_ERROR", "An unexpected error occurred.", 500)


def _error_envelope(code: str, message: str, status_code: int):
    """Build a standard JSON error response."""
    body = {
        "error": {
            "code": code,
            "message": message,
        },
        "meta": {
            "request_id": getattr(g, "request_id", None),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    return jsonify(body), status_code


def _register_before_request(app: Flask) -> None:
    """Register before-request hooks."""

    @app.before_request
    def assign_request_id():
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    @app.before_request
    def log_request():
        logger.info(
            "http", "request",
            f"{request.method} {request.path}",
            request_id=g.request_id,
            remote_addr=request.remote_addr,
        )


def _register_after_request(app: Flask) -> None:
    """Register after-request hooks."""

    @app.after_request
    def log_response(response):
        logger.info(
            "http", "response",
            f"{request.method} {request.path} -> {response.status_code}",
            request_id=getattr(g, "request_id", None),
        )
        return response

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # No-store for sensitive routes
        if any(request.path.startswith(prefix) for prefix in SENSITIVE_ROUTE_PREFIXES):
            response.headers["Cache-Control"] = "no-store"

        return response


def _bootstrap_platform_admin() -> None:
    """Create the default platform admin if no users exist yet."""
    from src.models.models import User
    from src.models.enums import RoleType

    if User.query.first() is not None:
        return

    from src.security.passwords import hash_password

    admin_username = getattr(config, "ADMIN_USERNAME", None) or "admin"
    admin_password = getattr(config, "ADMIN_PASSWORD", None) or "admin"

    admin = User(
        username=admin_username,
        password_hash=hash_password(admin_password),
        display_name="Platform Administrator",
        role=RoleType.PLATFORM_ADMIN.value,
        is_active=True,
    )
    db.session.add(admin)
    db.session.commit()
    logger.info("app", "bootstrap", f"Platform admin created: {admin_username}")
