"""Admin and debug API endpoints - plan section 9."""

import os
from datetime import datetime, timezone

from flask import Blueprint, request, g, current_app

from src.models.base import db
from src.models.models import User, Organization, Reservation, ContentItem, Export
from src.models.enums import RoleType
from src.security.auth_middleware import require_auth, require_role
from src.utils.responses import success_response, error_response
from src.logging import logger
from src.config import config

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ──────────────────────────────────────────
# GET /admin/system-status
# ──────────────────────────────────────────

@admin_bp.route("/system-status", methods=["GET"])
@require_auth
@require_role(RoleType.PLATFORM_ADMIN)
def system_status():
    """Return system-wide status information. Platform admin only."""
    try:
        total_users = User.query.count()
        total_organizations = Organization.query.count()
        total_reservations = Reservation.query.count()
        total_content_items = ContentItem.query.count()
        total_exports = Export.query.count()

        # Database file size (SQLite only)
        db_file_size = None
        db_url = config.DATABASE_URL
        if db_url.startswith("sqlite"):
            # Extract file path from sqlite:///path or sqlite:////abs/path
            db_path = db_url.replace("sqlite:///", "", 1)
            if os.path.isfile(db_path):
                db_file_size = os.path.getsize(db_path)

        logger.info(
            "api", "admin",
            "System status retrieved",
            user_id=g.current_user.user_id,
        )

        return success_response({
            "total_users": total_users,
            "total_organizations": total_organizations,
            "total_reservations": total_reservations,
            "total_content_items": total_content_items,
            "total_exports": total_exports,
            "database_file_size": db_file_size,
            "app_env": config.APP_ENV,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as exc:
        logger.error("api", "admin", f"Failed to retrieve system status: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to retrieve system status", status_code=500)


# ──────────────────────────────────────────
# GET /admin/debug/routes
# ──────────────────────────────────────────

@admin_bp.route("/debug/routes", methods=["GET"])
@require_auth
@require_role(RoleType.PLATFORM_ADMIN)
def debug_routes():
    """List all registered Flask routes. Requires debug endpoints enabled."""
    try:
        if not config.ENABLE_DEBUG_ENDPOINTS:
            return error_response("FORBIDDEN", "Debug endpoints are disabled", status_code=403)

        routes = []
        for rule in current_app.url_map.iter_rules():
            routes.append({
                "endpoint": rule.endpoint,
                "methods": sorted(rule.methods - {"HEAD", "OPTIONS"}),
                "rule": rule.rule,
            })

        routes.sort(key=lambda r: r["rule"])

        logger.info(
            "api", "admin",
            "Debug routes listed",
            user_id=g.current_user.user_id,
        )

        return success_response({"routes": routes})

    except Exception as exc:
        logger.error("api", "admin", f"Failed to list debug routes: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to list routes", status_code=500)


# ──────────────────────────────────────────
# GET /admin/debug/config-redacted
# ──────────────────────────────────────────

@admin_bp.route("/debug/config-redacted", methods=["GET"])
@require_auth
@require_role(RoleType.PLATFORM_ADMIN)
def debug_config_redacted():
    """Return redacted application configuration. Requires debug endpoints enabled."""
    try:
        if not config.ENABLE_DEBUG_ENDPOINTS:
            return error_response("FORBIDDEN", "Debug endpoints are disabled", status_code=403)

        redacted_config = config.as_dict(redacted=True)

        logger.info(
            "api", "admin",
            "Debug config (redacted) retrieved",
            user_id=g.current_user.user_id,
        )

        return success_response({"config": redacted_config})

    except Exception as exc:
        logger.error("api", "admin", f"Failed to retrieve redacted config: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to retrieve configuration", status_code=500)
