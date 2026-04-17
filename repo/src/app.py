"""
Flask application factory for the Learning & Resource Booking Governance API.
"""

import uuid
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request

from src.config import config
from src.logging import logger
from src.models.base import db
from src.security.signing import verify_request_signature
from src.security.rate_limiter import check_rate_limit


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
        _create_overlap_index()
        _bootstrap_platform_admin()
        _seed_demo_users()

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

# Paths exempt from request signing and rate limiting (health, auth login/register)
SIGNING_EXEMPT_PREFIXES = ("/health",)
RATE_LIMIT_EXEMPT_PREFIXES = ("/health",)


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
    def enforce_tls():
        """Reject non-HTTPS requests when TLS is enabled."""
        if app.config.get("TESTING"):
            return None
        if not config.ENABLE_TLS:
            return None
        # X-Forwarded-Proto is set by reverse proxies; also check wsgi scheme
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        if proto != "https":
            logger.warning("security", "tls", f"Non-HTTPS request rejected: {request.url}")
            return _error_envelope("TLS_REQUIRED", "HTTPS is required.", 403)

    @app.before_request
    def enforce_request_signing():
        """Verify request signature on every non-exempt request."""
        if app.config.get("TESTING"):
            return None
        if any(request.path.startswith(p) for p in SIGNING_EXEMPT_PREFIXES):
            return None
        is_valid, error_code = verify_request_signature(request)
        if not is_valid:
            logger.warning("security", "signing", f"Request signing failed: {error_code}")
            return _error_envelope("SIGNATURE_INVALID", f"Request signature validation failed: {error_code}", 401)

    @app.before_request
    def enforce_rate_limit():
        """Apply rate limiting on every non-exempt request.

        Uses IP-based bucket for all requests. For authenticated requests
        (Bearer token present), also enforces a per-identity bucket keyed
        by user ID.
        """
        if app.config.get("TESTING"):
            return None
        if any(request.path.startswith(p) for p in RATE_LIMIT_EXEMPT_PREFIXES):
            return None

        # IP-based rate limit for all requests
        bucket_key = f"ip:{request.remote_addr}"
        allowed, headers = check_rate_limit(
            bucket_key,
            max_tokens=config.RATE_LIMIT_BURST,
            refill_rate=config.RATE_LIMIT_DEFAULT_PER_MINUTE,
        )
        if not allowed:
            resp = _error_envelope("TOO_MANY_REQUESTS", "Rate limit exceeded.", 429)
            response = resp[0] if isinstance(resp, tuple) else resp
            for k, v in headers.items():
                response.headers[k] = v
            return resp

        # Per-identity rate limit for authenticated requests
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            from src.security.tokens import decode_token as _decode
            token_str = auth_header[7:]
            payload = _decode(token_str)
            if payload and payload.get("sub"):
                user_bucket_key = f"user:{payload['sub']}"
                user_allowed, user_headers = check_rate_limit(
                    user_bucket_key,
                    max_tokens=config.RATE_LIMIT_BURST,
                    refill_rate=config.RATE_LIMIT_DEFAULT_PER_MINUTE,
                )
                if not user_allowed:
                    resp = _error_envelope("TOO_MANY_REQUESTS", "Rate limit exceeded.", 429)
                    response = resp[0] if isinstance(resp, tuple) else resp
                    for k, v in user_headers.items():
                        response.headers[k] = v
                    return resp

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


def _create_overlap_index() -> None:
    """Create DB-level overlap prevention for reservations.

    Layer 1: Partial unique index prevents exact-duplicate (resource, start, end).
    Layer 2: BEFORE INSERT trigger rejects any new HELD/CONFIRMED reservation
             whose time range overlaps an existing HELD/CONFIRMED reservation on
             the same resource.  This closes the gap that the unique index alone
             cannot cover (partial overlaps like 10:00-11:00 vs 10:30-11:30).
    """
    from sqlalchemy import text
    try:
        # Keep the exact-duplicate safety net
        db.session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uix_reservation_no_overlap
            ON reservations (resource_id, start_time, end_time)
            WHERE status IN ('HELD', 'CONFIRMED')
        """))

        # Trigger-based overlap rejection for INSERT
        db.session.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_reservation_no_overlap_insert
            BEFORE INSERT ON reservations
            WHEN NEW.status IN ('HELD', 'CONFIRMED')
            BEGIN
                SELECT RAISE(ABORT, 'OVERLAP_CONFLICT: reservation overlaps an existing active reservation')
                WHERE EXISTS (
                    SELECT 1 FROM reservations
                    WHERE resource_id = NEW.resource_id
                      AND status IN ('HELD', 'CONFIRMED')
                      AND start_time < NEW.end_time
                      AND end_time > NEW.start_time
                );
            END
        """))

        # Trigger-based overlap rejection for UPDATE (e.g. reschedule)
        db.session.execute(text("""
            CREATE TRIGGER IF NOT EXISTS trg_reservation_no_overlap_update
            BEFORE UPDATE ON reservations
            WHEN NEW.status IN ('HELD', 'CONFIRMED')
            BEGIN
                SELECT RAISE(ABORT, 'OVERLAP_CONFLICT: reservation overlaps an existing active reservation')
                WHERE EXISTS (
                    SELECT 1 FROM reservations
                    WHERE resource_id = NEW.resource_id
                      AND id != NEW.id
                      AND status IN ('HELD', 'CONFIRMED')
                      AND start_time < NEW.end_time
                      AND end_time > NEW.start_time
                );
            END
        """))

        db.session.commit()
    except Exception:
        db.session.rollback()


def _bootstrap_platform_admin() -> None:
    """Create the default platform admin if no users exist yet.

    In non-development environments the admin password MUST be explicitly
    overridden via the ADMIN_PASSWORD environment variable.  If the factory
    default (``"admin"``) is still in place the application refuses to start.
    """
    from src.models.models import User
    from src.models.enums import RoleType, UserStatus

    if User.query.first() is not None:
        return

    from src.security.passwords import hash_password

    admin_username = config.ADMIN_USERNAME
    admin_password = config.ADMIN_PASSWORD

    # Fail fast if the default weak password is used outside development / testing
    if admin_password == "admin" and config.APP_ENV not in ("development", "testing"):
        raise RuntimeError(
            "ADMIN_PASSWORD must be set to a strong value in non-development environments. "
            "Set the ADMIN_PASSWORD environment variable before starting the application."
        )

    if admin_password == "admin":
        logger.warning(
            "app", "bootstrap",
            "Using default admin credentials — change ADMIN_PASSWORD before deploying to production",
        )

    admin = User(
        username=admin_username,
        password_hash=hash_password(admin_password),
        display_name="Platform Administrator",
        role=RoleType.PLATFORM_ADMIN.value,
        status=UserStatus.ACTIVE.value,
        is_active=True,
    )
    db.session.add(admin)
    db.session.commit()
    logger.info("app", "bootstrap", f"Platform admin created: {admin_username}")


def _seed_demo_users() -> None:
    """Seed demo users for each role so reviewers can log in immediately.

    Only runs in development/testing environments and only when the demo
    org does not yet exist.  Credentials are documented in the README.
    """
    if config.APP_ENV not in ("development", "testing"):
        return

    from src.models.models import User, Organization, Membership
    from src.models.enums import RoleType, UserStatus
    from src.security.passwords import hash_password

    # Skip if already seeded
    if Organization.query.filter_by(slug="demo-org").first():
        return

    # Create the demo organization
    org = Organization(name="Demo Organization", slug="demo-org", is_active=True)
    db.session.add(org)
    db.session.flush()

    demo_users = [
        ("orgadmin", "OrgAdminPass1!", RoleType.ORG_ADMIN),
        ("member", "MemberPass1!", RoleType.MEMBER),
        ("guest", "GuestPass1!", RoleType.GUEST),
    ]

    for username, password, role in demo_users:
        user = User(
            username=username,
            password_hash=hash_password(password),
            display_name=f"Demo {role.value}",
            role=role.value,
            status=UserStatus.ACTIVE.value,
            is_active=True,
        )
        db.session.add(user)
        db.session.flush()

        # All non-guest demo users get a membership in the demo org
        if role != RoleType.GUEST:
            m = Membership(
                user_id=user.id,
                organization_id=org.id,
                role=role.value,
                is_active=True,
            )
            db.session.add(m)

    db.session.commit()
    logger.info("app", "bootstrap", "Demo users seeded: orgadmin, member, guest")
