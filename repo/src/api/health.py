"""Health check endpoint - public, no auth required."""

from datetime import datetime, timezone

from flask import Blueprint

from src.models.base import db
from src.utils.responses import success_response, error_response
from src.logging import logger
from src.config import config

health_bp = Blueprint("health", __name__, url_prefix="")


# ──────────────────────────────────────────
# GET /health
# ──────────────────────────────────────────

@health_bp.route("/health", methods=["GET"])
def health_check():
    """Public health check endpoint. Returns system and database status."""
    db_status = "disconnected"
    status = "unhealthy"
    status_code = 503

    try:
        db.session.execute(db.text("SELECT 1"))
        db_status = "connected"
        status = "healthy"
        status_code = 200
    except Exception as exc:
        logger.error("api", "health", f"Database health check failed: {exc}")

    response_data = {
        "status": status,
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": config.APP_NAME,
    }

    if status_code == 200:
        logger.info("api", "health", "Health check passed")
        return success_response(response_data, status_code=200)
    else:
        logger.warning("api", "health", "Health check failed - database disconnected")
        return error_response("UNHEALTHY", "Service is unhealthy", details=response_data, status_code=503)
