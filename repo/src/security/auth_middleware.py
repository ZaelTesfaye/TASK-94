"""Authentication and authorization middleware - plan section 7 security controls."""

import functools
from types import SimpleNamespace

from flask import g, request

from src.config import config
from src.logging import logger
from src.models.base import db
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

    The effective role is the *higher* of the user's global role and the
    membership role for the current org context.  This ensures that
    platform_admin users are never downgraded by a lower membership role
    while org-scoped roles still come from the Membership table.

    Args:
        min_role: The minimum role required (e.g., "org_admin").
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            current_user = getattr(g, "current_user", None)
            if current_user is None:
                return error_response("UNAUTHORIZED", "Authentication required", status_code=401)

            # Start from the JWT role claim
            effective_role = current_user.role

            # Verify against the database for the current org context
            org_id = getattr(current_user, "organization_id", None)
            if org_id:
                from src.models.models import Membership, User
                membership = Membership.query.filter_by(
                    user_id=current_user.user_id,
                    organization_id=org_id,
                    is_active=True,
                ).first()
                membership_role = membership.role if membership else None

                # Also fetch the global User.role as a floor
                user = User.query.get(current_user.user_id)
                global_role = user.role if user else current_user.role

                # Effective role = max(global, membership) per hierarchy
                try:
                    global_level = ROLE_HIERARCHY[RoleType(global_role)]
                    membership_level = ROLE_HIERARCHY[RoleType(membership_role)] if membership_role else -1
                    effective_role = global_role if global_level >= membership_level else membership_role
                except (ValueError, KeyError):
                    effective_role = current_user.role
            else:
                # No org context — fall back to global User.role from DB
                from src.models.models import User
                user = User.query.get(current_user.user_id)
                if user:
                    try:
                        jwt_level = ROLE_HIERARCHY[RoleType(current_user.role)]
                        db_level = ROLE_HIERARCHY[RoleType(user.role)]
                        effective_role = current_user.role if jwt_level >= db_level else user.role
                    except (ValueError, KeyError):
                        effective_role = user.role

            try:
                user_level = ROLE_HIERARCHY[RoleType(effective_role)]
                required_level = ROLE_HIERARCHY[RoleType(min_role)]
            except (ValueError, KeyError):
                logger.error("security", "auth", f"Unknown role: user={effective_role}, required={min_role}")
                return error_response("ROLE_ERROR", "Invalid role configuration", status_code=500)

            if user_level < required_level:
                logger.warning(
                    "security", "auth",
                    f"Insufficient role: user={current_user.user_id} has={effective_role} needs={min_role}"
                )
                return error_response("FORBIDDEN", "Insufficient permissions", status_code=403)

            # Update g.current_user.role to reflect the DB-verified effective role
            current_user.role = effective_role

            return f(*args, **kwargs)
        return decorated
    return decorator


def require_permission(permission_code: str):
    """Decorator that requires the user to have a specific permission code.

    Platform admins bypass this check entirely (they have implicit access
    to every operation).  For all other callers the decorator performs two
    checks:

    1. **JWT fast-path** — the permission must appear in the JWT ``permissions``
       claim that was embedded at login/refresh time.
    2. **Authoritative DB check** — a matching ``UserPermission`` row must
       exist whose ``organization_id`` equals the caller's current org
       context (or is NULL / global).  This prevents a JWT minted for org-A
       from being replayed against objects in org-B.

    Args:
        permission_code: The permission code to check (e.g., "moderation:review").
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            current_user = getattr(g, "current_user", None)
            if current_user is None:
                return error_response("UNAUTHORIZED", "Authentication required", status_code=401)

            # Platform admins have implicit access to every permission.
            if current_user.role == RoleType.PLATFORM_ADMIN.value:
                return f(*args, **kwargs)

            # 1. JWT fast-path
            if permission_code not in (current_user.permissions or []):
                logger.warning(
                    "security", "auth",
                    f"Missing permission (JWT): user={current_user.user_id} needs={permission_code}"
                )
                return error_response("PERMISSION_DENIED", "Missing required permission", status_code=403)

            # 2. Authoritative DB check — org-scoped grant must exist.
            from src.models.models import Permission, UserPermission
            org_id = getattr(current_user, "organization_id", None)
            db_grant = db.session.query(UserPermission.id).join(
                Permission, Permission.id == UserPermission.permission_id
            ).filter(
                Permission.code == permission_code,
                UserPermission.user_id == current_user.user_id,
            )
            if org_id:
                db_grant = db_grant.filter(
                    db.or_(
                        UserPermission.organization_id == org_id,
                        UserPermission.organization_id.is_(None),
                    )
                )
            else:
                db_grant = db_grant.filter(UserPermission.organization_id.is_(None))

            if not db_grant.first():
                logger.warning(
                    "security", "auth",
                    f"DB permission check failed: user={current_user.user_id} "
                    f"perm={permission_code} org={org_id}"
                )
                return error_response(
                    "PERMISSION_DENIED",
                    "Missing required permission for this organization",
                    status_code=403,
                )

            return f(*args, **kwargs)
        return decorated
    return decorator


def require_org_context(f):
    """Decorator that ensures the current user has an organization_id set.

    Platform admins are exempt: they operate across all organizations and may
    not have an org context in their JWT.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        current_user = getattr(g, "current_user", None)
        if current_user is None:
            return error_response("UNAUTHORIZED", "Authentication required", status_code=401)

        # Platform admins operate across all orgs
        if current_user.role == RoleType.PLATFORM_ADMIN.value:
            return f(*args, **kwargs)

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


def verify_org_scope(obj_organization_id: str) -> bool:
    """Verify the caller's organization context matches the target object's org.

    Purpose-built for actions like moderation where the caller must belong
    to the same organization as the target content.  Platform admins are
    exempt (they operate cross-org).

    Unlike ``check_object_ownership`` this does **not** check user-level
    ownership — it only validates that the caller's JWT ``org_id`` matches
    ``obj_organization_id``.

    Args:
        obj_organization_id: The organization_id of the target object.

    Returns:
        True if the caller may act on objects in this organization.
    """
    current_user = getattr(g, "current_user", None)
    if current_user is None:
        return False

    # Platform admins can act on any organization
    if current_user.role == RoleType.PLATFORM_ADMIN.value:
        return True

    # All other callers must have an org context that matches
    caller_org = getattr(current_user, "organization_id", None)
    if not caller_org:
        return False

    return caller_org == obj_organization_id
