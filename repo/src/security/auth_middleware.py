"""Authentication and authorization middleware - plan section 7 security controls."""

import functools
from types import SimpleNamespace

from flask import g, request

from src.config import config
from src.logging import logger
from src.models.enums import RoleType, ROLE_HIERARCHY
from src.models.models import AccessTokenDenylist
from src.security.tokens import decode_token
from src.utils.responses import error_response


def require_auth(f):
    """Decorator that requires a valid JWT Bearer token.

    Extracts the token from the Authorization header, decodes it, checks
    it is not in the denylist, and populates g.current_user with user info.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("security", "auth", "Missing or malformed Authorization header")
            return error_response("UNAUTHORIZED", "Missing or invalid authorization header", status_code=401)

        token = auth_header[7:]  # Strip "Bearer "
        payload = decode_token(token)
        if payload is None:
            logger.warning("security", "auth", "Token decode failed")
            return error_response("INVALID_TOKEN", "Invalid or expired token", status_code=401)

        # Check denylist
        jti = payload.get("jti")
        if jti and AccessTokenDenylist.query.filter_by(jti=jti).first():
            logger.warning("security", "auth", f"Denylisted token used: jti={jti}")
            return error_response("TOKEN_REVOKED", "Token has been revoked", status_code=401)

        # Populate g.current_user
        g.current_user = SimpleNamespace(
            user_id=payload.get("sub"),
            username=payload.get("username"),
            role=payload.get("role"),
            organization_id=payload.get("org_id"),
            permissions=payload.get("permissions", []),
            jti=jti,
        )

        return f(*args, **kwargs)
    return decorated


def require_role(min_role: str):
    """Decorator that requires the user's role to meet a minimum level.

    Role hierarchy: guest < member < org_admin < platform_admin.

    Args:
        min_role: The minimum role required (e.g., "org_admin").
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            current_user = getattr(g, "current_user", None)
            if current_user is None:
                return error_response("UNAUTHORIZED", "Authentication required", status_code=401)

            user_role = current_user.role
            try:
                user_level = ROLE_HIERARCHY[RoleType(user_role)]
                required_level = ROLE_HIERARCHY[RoleType(min_role)]
            except (ValueError, KeyError):
                logger.error("security", "auth", f"Unknown role: user={user_role}, required={min_role}")
                return error_response("ROLE_ERROR", "Invalid role configuration", status_code=500)

            if user_level < required_level:
                logger.warning(
                    "security", "auth",
                    f"Insufficient role: user={current_user.user_id} has={user_role} needs={min_role}"
                )
                return error_response("FORBIDDEN", "Insufficient permissions", status_code=403)

            return f(*args, **kwargs)
        return decorated
    return decorator


def require_permission(permission_code: str):
    """Decorator that requires the user to have a specific permission code.

    Args:
        permission_code: The permission code to check (e.g., "booking.create").
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            current_user = getattr(g, "current_user", None)
            if current_user is None:
                return error_response("UNAUTHORIZED", "Authentication required", status_code=401)

            if permission_code not in (current_user.permissions or []):
                logger.warning(
                    "security", "auth",
                    f"Missing permission: user={current_user.user_id} needs={permission_code}"
                )
                return error_response("PERMISSION_DENIED", "Missing required permission", status_code=403)

            return f(*args, **kwargs)
        return decorated
    return decorator


def require_org_context(f):
    """Decorator that ensures the current user has an organization_id set."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        current_user = getattr(g, "current_user", None)
        if current_user is None:
            return error_response("UNAUTHORIZED", "Authentication required", status_code=401)

        if not current_user.organization_id:
            logger.warning(
                "security", "auth",
                f"Missing org context: user={current_user.user_id}"
            )
            return error_response("ORG_CONTEXT_REQUIRED", "Organization context required", status_code=403)

        return f(*args, **kwargs)
    return decorated


def check_object_ownership(obj, user_id_field: str = "user_id", org_id_field: str = "organization_id") -> bool:
    """Check if the current user owns an object or is a platform admin.

    Verifies either direct ownership (matching user_id) or organizational
    scope (matching organization_id for org_admins). Platform admins bypass
    all ownership checks.

    Args:
        obj: The database object to check ownership of.
        user_id_field: The attribute name for the owner user ID on the object.
        org_id_field: The attribute name for the organization ID on the object.

    Returns:
        True if the current user has access to the object.
    """
    current_user = getattr(g, "current_user", None)
    if current_user is None:
        return False

    # Platform admins can access everything
    if current_user.role == RoleType.PLATFORM_ADMIN.value:
        return True

    # Check direct ownership
    obj_user_id = getattr(obj, user_id_field, None)
    if obj_user_id and obj_user_id == current_user.user_id:
        return True

    # Check organization scope for org_admins
    if current_user.role == RoleType.ORG_ADMIN.value:
        obj_org_id = getattr(obj, org_id_field, None)
        if obj_org_id and obj_org_id == current_user.organization_id:
            return True

    return False
