"""Permissions and memberships API endpoints."""

import json

from flask import Blueprint, request, g

from datetime import datetime, timezone, timedelta

from src.models.base import db
from src.models.models import Permission, UserPermission, Membership, User, Organization, AuditEvent, RefreshToken
from src.models.enums import RoleType, ROLE_HIERARCHY, AuditEventType
from src.security.auth_middleware import require_auth, require_role
from src.security.tokens import create_access_token, create_refresh_token, hash_token
from src.utils.responses import success_response, error_response, list_response
from src.utils.pagination import paginate_query
from src.utils.validators import validate_required, validate_string, validate_uuid
from src.logging import logger
from src.config import config


permissions_bp = Blueprint("permissions", __name__, url_prefix="/permissions")


# ──────────────────────────────────────────
# GET /permissions
# ──────────────────────────────────────────

@permissions_bp.route("", methods=["GET"])
@require_auth
def list_permissions():
    """List all permissions. Platform admins see all; others see org-scoped."""
    try:
        current_user = g.current_user
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)

        query = Permission.query

        # Non-platform-admins only see permissions scoped to their org
        if current_user.role != RoleType.PLATFORM_ADMIN.value:
            org_id = current_user.organization_id
            if org_id:
                # Show permissions that are either unscoped or scoped to "organization"
                query = query.filter(
                    db.or_(
                        Permission.data_scope.is_(None),
                        Permission.data_scope == "organization",
                    )
                )
            else:
                query = query.filter(Permission.data_scope.is_(None))

        query = query.order_by(Permission.code)
        result = paginate_query(query, page, per_page)

        items = [
            {
                "id": p.id,
                "code": p.code,
                "description": p.description,
                "action": p.action,
                "category": p.category,
                "assignable": p.assignable,
                "data_scope": p.data_scope,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in result["items"]
        ]

        logger.info("api", "permissions", f"Listed permissions page={page}", user_id=current_user.user_id)
        return list_response(items, result["pagination"])

    except Exception as exc:
        logger.error("api", "permissions", f"Failed to list permissions: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to list permissions", status_code=500)


# ──────────────────────────────────────────
# POST /permissions
# ──────────────────────────────────────────

@permissions_bp.route("", methods=["POST"])
@require_auth
@require_role(RoleType.PLATFORM_ADMIN)
def create_permission():
    """Create a new permission definition. Platform admin only."""
    try:
        data = request.get_json(silent=True) or {}
        current_user = g.current_user

        # Validate required fields
        errors = validate_required(data, ["code"])
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        code = data["code"]
        errors = validate_string(code, "code", min_len=1, max_len=255)
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        # Check uniqueness
        existing = Permission.query.filter_by(code=code).first()
        if existing:
            return error_response("DUPLICATE", f"Permission with code '{code}' already exists", status_code=409)

        description = data.get("description")
        data_scope = data.get("data_scope")
        action = data.get("action")
        category = data.get("category")
        assignable = data.get("assignable", True)

        permission = Permission(
            code=code,
            description=description,
            action=action,
            category=category,
            assignable=assignable,
            data_scope=data_scope,
        )
        db.session.add(permission)

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.PERMISSION_CREATED.value,
            actor_id=current_user.user_id,
            actor_ip=request.remote_addr,
            target_type="Permission",
            target_id=permission.id,
            after_state=json.dumps({"code": code, "description": description, "data_scope": data_scope}),
        )
        db.session.add(audit)
        db.session.commit()

        logger.info("api", "permissions", f"Permission created: {code}", user_id=current_user.user_id)
        return success_response(
            {
                "id": permission.id,
                "code": permission.code,
                "description": permission.description,
                "action": permission.action,
                "category": permission.category,
                "assignable": permission.assignable,
                "data_scope": permission.data_scope,
                "created_at": permission.created_at.isoformat() if permission.created_at else None,
            },
            status_code=201,
        )

    except Exception as exc:
        db.session.rollback()
        logger.error("api", "permissions", f"Failed to create permission: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to create permission", status_code=500)


# ──────────────────────────────────────────
# POST /permissions/assign
# ──────────────────────────────────────────

@permissions_bp.route("/assign", methods=["POST"])
@require_auth
@require_role(RoleType.ORG_ADMIN)
def assign_permission():
    """Assign a permission to a user within an organization."""
    try:
        data = request.get_json(silent=True) or {}
        current_user = g.current_user

        # Validate required fields
        errors = validate_required(data, ["user_id", "permission_code"])
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        user_id = data["user_id"]
        permission_code = data["permission_code"]
        organization_id = data.get("organization_id", current_user.organization_id)

        errors = validate_uuid(user_id, "user_id")
        if organization_id:
            errors += validate_uuid(organization_id, "organization_id")
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        if not organization_id:
            return error_response("VALIDATION_ERROR", "Organization context is required")

        # Enforce permission boundary: caller must belong to the target org (unless platform admin)
        if current_user.role != RoleType.PLATFORM_ADMIN.value:
            caller_membership = Membership.query.filter_by(
                user_id=current_user.user_id,
                organization_id=organization_id,
                is_active=True,
            ).first()
            if not caller_membership:
                return error_response(
                    "FORBIDDEN",
                    "You can only manage permissions in organizations you belong to",
                    status_code=403,
                )

        # Verify the permission exists
        permission = Permission.query.filter_by(code=permission_code).first()
        if not permission:
            return error_response("NOT_FOUND", f"Permission '{permission_code}' not found", status_code=404)

        # Verify target user exists
        target_user = User.query.get(user_id)
        if not target_user:
            return error_response("NOT_FOUND", "User not found", status_code=404)

        # Verify target user has membership in the org
        membership = Membership.query.filter_by(
            user_id=user_id,
            organization_id=organization_id,
            is_active=True,
        ).first()
        if not membership:
            return error_response("FORBIDDEN", "Target user has no active membership in this organization", status_code=403)

        # Cannot assign permissions to users with higher role level
        try:
            caller_level = ROLE_HIERARCHY[RoleType(current_user.role)]
            target_level = ROLE_HIERARCHY[RoleType(membership.role)]
        except (ValueError, KeyError):
            return error_response("ROLE_ERROR", "Invalid role configuration", status_code=500)

        if target_level > caller_level:
            return error_response("FORBIDDEN", "Cannot assign permissions to a user with a higher role", status_code=403)

        # Check for existing assignment
        existing = UserPermission.query.filter_by(
            user_id=user_id,
            permission_id=permission.id,
            organization_id=organization_id,
        ).first()
        if existing:
            return error_response("DUPLICATE", "Permission already assigned to this user in this organization", status_code=409)

        user_perm = UserPermission(
            user_id=user_id,
            permission_id=permission.id,
            organization_id=organization_id,
            granted_by=current_user.user_id,
        )
        db.session.add(user_perm)

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.PERMISSION_ASSIGNED.value,
            actor_id=current_user.user_id,
            actor_ip=request.remote_addr,
            target_type="UserPermission",
            target_id=user_perm.id,
            organization_id=organization_id,
            after_state=json.dumps({
                "user_id": user_id,
                "permission_code": permission_code,
                "organization_id": organization_id,
            }),
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(
            "api", "permissions",
            f"Permission '{permission_code}' assigned to user {user_id}",
            user_id=current_user.user_id,
            organization_id=organization_id,
        )
        return success_response(
            {
                "id": user_perm.id,
                "user_id": user_perm.user_id,
                "permission_code": permission_code,
                "organization_id": user_perm.organization_id,
                "granted_by": user_perm.granted_by,
                "created_at": user_perm.created_at.isoformat() if user_perm.created_at else None,
            },
            status_code=201,
        )

    except Exception as exc:
        db.session.rollback()
        logger.error("api", "permissions", f"Failed to assign permission: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to assign permission", status_code=500)


# ──────────────────────────────────────────
# POST /permissions/revoke
# ──────────────────────────────────────────

@permissions_bp.route("/revoke", methods=["POST"])
@require_auth
@require_role(RoleType.ORG_ADMIN)
def revoke_permission():
    """Revoke a permission from a user."""
    try:
        data = request.get_json(silent=True) or {}
        current_user = g.current_user

        # Validate required fields
        errors = validate_required(data, ["user_id", "permission_code"])
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        user_id = data["user_id"]
        permission_code = data["permission_code"]
        organization_id = data.get("organization_id", current_user.organization_id)

        errors = validate_uuid(user_id, "user_id")
        if organization_id:
            errors += validate_uuid(organization_id, "organization_id")
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        if not organization_id:
            return error_response("VALIDATION_ERROR", "Organization context is required")

        # Enforce permission boundary: caller must belong to the target org (unless platform admin)
        if current_user.role != RoleType.PLATFORM_ADMIN.value:
            caller_membership = Membership.query.filter_by(
                user_id=current_user.user_id,
                organization_id=organization_id,
                is_active=True,
            ).first()
            if not caller_membership:
                return error_response(
                    "FORBIDDEN",
                    "You can only manage permissions in organizations you belong to",
                    status_code=403,
                )

        # Find the permission record
        permission = Permission.query.filter_by(code=permission_code).first()
        if not permission:
            return error_response("NOT_FOUND", f"Permission '{permission_code}' not found", status_code=404)

        # Find the user-permission assignment
        user_perm = UserPermission.query.filter_by(
            user_id=user_id,
            permission_id=permission.id,
            organization_id=organization_id,
        ).first()
        if not user_perm:
            return error_response("NOT_FOUND", "Permission assignment not found", status_code=404)

        perm_id = user_perm.id
        db.session.delete(user_perm)

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.PERMISSION_REVOKED.value,
            actor_id=current_user.user_id,
            actor_ip=request.remote_addr,
            target_type="UserPermission",
            target_id=perm_id,
            organization_id=organization_id,
            before_state=json.dumps({
                "user_id": user_id,
                "permission_code": permission_code,
                "organization_id": organization_id,
            }),
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(
            "api", "permissions",
            f"Permission '{permission_code}' revoked from user {user_id}",
            user_id=current_user.user_id,
            organization_id=organization_id,
        )
        return success_response({"message": "Permission revoked successfully"})

    except Exception as exc:
        db.session.rollback()
        logger.error("api", "permissions", f"Failed to revoke permission: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to revoke permission", status_code=500)


# ──────────────────────────────────────────
# GET /permissions/memberships  (mounted at /memberships via blueprint prefix workaround)
# ──────────────────────────────────────────
# Note: These are registered on the same blueprint so they live at
#   /permissions/memberships and /permissions/memberships/switch-context
# but the spec says /memberships. We register them here; if a separate
# url_prefix is needed, the app factory can mount them differently.

@permissions_bp.route("/memberships", methods=["GET"])
@require_auth
def list_memberships():
    """List caller's memberships, or filter by user_id if platform_admin."""
    try:
        current_user = g.current_user

        if current_user.role == RoleType.PLATFORM_ADMIN.value:
            filter_user_id = request.args.get("user_id", current_user.user_id)
        else:
            filter_user_id = current_user.user_id

        memberships = Membership.query.filter_by(
            user_id=filter_user_id,
            is_active=True,
        ).all()

        items = []
        for m in memberships:
            org = Organization.query.get(m.organization_id)
            items.append({
                "id": m.id,
                "user_id": m.user_id,
                "organization_id": m.organization_id,
                "organization_name": org.name if org else None,
                "organization_slug": org.slug if org else None,
                "role": m.role,
                "is_active": m.is_active,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            })

        logger.info("api", "memberships", f"Listed memberships for user {filter_user_id}", user_id=current_user.user_id)
        return success_response(items)

    except Exception as exc:
        logger.error("api", "memberships", f"Failed to list memberships: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to list memberships", status_code=500)


# ──────────────────────────────────────────
# POST /permissions/memberships/switch-context
# ──────────────────────────────────────────

@permissions_bp.route("/memberships/switch-context", methods=["POST"])
@require_auth
def switch_context():
    """Switch active org context and return new tokens with the membership role."""
    try:
        data = request.get_json(silent=True) or {}
        current_user = g.current_user

        errors = validate_required(data, ["organization_id"])
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        organization_id = data["organization_id"]
        errors = validate_uuid(organization_id, "organization_id")
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        # Verify caller has active membership
        membership = Membership.query.filter_by(
            user_id=current_user.user_id,
            organization_id=organization_id,
            is_active=True,
        ).first()
        if not membership:
            return error_response("FORBIDDEN", "No active membership in the specified organization", status_code=403)

        org = Organization.query.get(organization_id)

        # Resolve effective role: max(global user role, membership role)
        user = User.query.get(current_user.user_id)
        from src.api.auth import _resolve_effective_role, _get_user_permissions
        effective_role = _resolve_effective_role(user.role, membership.role)

        permission_codes = _get_user_permissions(user.id, organization_id)

        # Issue new token pair scoped to the target org
        access_token = create_access_token(
            user_id=user.id,
            username=user.username,
            role=effective_role,
            organization_id=organization_id,
            permissions=permission_codes,
        )
        refresh_token = create_refresh_token(user_id=user.id)

        _rt_hashed = hash_token(refresh_token)
        rt_record = RefreshToken(
            user_id=user.id,
            token_hash=_rt_hashed,
            token_lookup_hash=_rt_hashed,
            expires_at=datetime.now(timezone.utc) + timedelta(days=config.JWT_REFRESH_TOKEN_EXPIRES_DAYS),
        )
        db.session.add(rt_record)
        db.session.commit()

        logger.info(
            "api", "memberships",
            f"Context switch to org {organization_id}",
            user_id=current_user.user_id,
        )
        return success_response({
            "organization_id": organization_id,
            "organization_name": org.name if org else None,
            "organization_slug": org.slug if org else None,
            "role": effective_role,
            "membership_id": membership.id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": config.JWT_ACCESS_TOKEN_EXPIRES_MINUTES * 60,
        })

    except Exception as exc:
        db.session.rollback()
        logger.error("api", "memberships", f"Failed to switch context: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to switch context", status_code=500)
