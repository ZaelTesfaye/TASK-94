"""API Blueprints - all domain endpoints."""
from src.api.auth import auth_bp
from src.api.permissions import permissions_bp
from src.api.invitations import invitations_bp
from src.api.booking import booking_bp
from src.api.content import content_bp
from src.api.analytics import analytics_bp
from src.api.audit import audit_bp
from src.api.admin import admin_bp
from src.api.health import health_bp

__all__ = [
    "auth_bp",
    "permissions_bp",
    "invitations_bp",
    "booking_bp",
    "content_bp",
    "analytics_bp",
    "audit_bp",
    "admin_bp",
    "health_bp",
]
