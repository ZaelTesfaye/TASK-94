"""Invitation code management API endpoints."""

import json
import uuid

from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, g

from src.models.base import db
from src.models.models import (
    InvitationCode,
    Membership,
    User,
    Organization,
    AuditEvent,
    RefreshToken,
)
from src.models.enums import RoleType, ROLE_HIERARCHY, InvitationStatus, AuditEventType
from src.security.auth_middleware import require_auth, require_role
from src.security.tokens import create_access_token, create_refresh_token, hash_token
from src.utils.responses import success_response, error_response, list_response
from src.utils.pagination import paginate_query
from src.utils.validators import validate_required, validate_uuid
from src.logging import logger
from src.config import config


invitations_bp = Blueprint("invitations", __name__, url_prefix="/invitations")


# ──────────────────────────────────────────
# POST /invitations
# ──────────────────────────────────────────


@invitations_bp.route("", methods=["POST"])
@require_auth
@require_role(RoleType.ORG_ADMIN)
def create_invitation():
    """Create a new invitation code for an organization."""
    try:
        data = request.get_json(silent=True) or {}
        current_user = g.current_user

        # Validate required fields
        errors = validate_required(data, ["organization_id", "target_role"])
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        organization_id = data["organization_id"]
        target_role = data["target_role"]
        email_hint = data.get("email_hint")

        errors = validate_uuid(organization_id, "organization_id")
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        # Validate target_role is a valid RoleType
        try:
            target_role_enum = RoleType(target_role)
        except ValueError:
            valid_roles = [r.value for r in RoleType]
            return error_response(
                "VALIDATION_ERROR",
                f"'target_role' must be one of: {', '.join(valid_roles)}",
            )

        # Verify target role does not exceed caller's role in hierarchy
        try:
            caller_level = ROLE_HIERARCHY[RoleType(current_user.role)]
            target_level = ROLE_HIERARCHY[target_role_enum]
        except (ValueError, KeyError):
            return error_response(
                "ROLE_ERROR", "Invalid role configuration", status_code=500
            )

        if target_level > caller_level:
            return error_response(
                "FORBIDDEN",
                "Cannot create invitation for a role higher than your own",
                status_code=403,
            )

        # Verify organization exists
        org = Organization.query.get(organization_id)
        if not org:
            return error_response(
                "NOT_FOUND", "Organization not found", status_code=404
            )

        # Enforce authorization: caller must belong to the target org (unless platform admin)
        if current_user.role != RoleType.PLATFORM_ADMIN.value:
            caller_membership = Membership.query.filter_by(
                user_id=current_user.user_id,
                organization_id=organization_id,
                is_active=True,
            ).first()
            if not caller_membership:
                return error_response(
                    "FORBIDDEN",
                    "You can only create invitations for organizations you belong to",
                    status_code=403,
                )

        # Generate unique invitation code
        code = uuid.uuid4().hex[:12].upper()

        expiry_hours = getattr(config, "INVITATION_EXPIRY_HOURS", 72)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)

        invitation = InvitationCode(
            code=code,
            issuer_id=current_user.user_id,
            organization_id=organization_id,
            target_role=target_role_enum.value,
            status=InvitationStatus.PENDING.value,
            expires_at=expires_at,
        )
        db.session.add(invitation)

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.INVITATION_CREATED.value,
            actor_id=current_user.user_id,
            actor_ip=request.remote_addr,
            target_type="InvitationCode",
            target_id=invitation.id,
            organization_id=organization_id,
            after_state=json.dumps(
                {
                    "code": code,
                    "target_role": target_role,
                    "organization_id": organization_id,
                    "email_hint": email_hint,
                    "expires_at": expires_at.isoformat(),
                }
            ),
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(
            "api",
            "invitations",
            f"Invitation created: code={code} org={organization_id} role={target_role}",
            user_id=current_user.user_id,
        )
        return success_response(
            {
                "id": invitation.id,
                "code": invitation.code,
                "organization_id": invitation.organization_id,
                "target_role": invitation.target_role,
                "status": invitation.status,
                "email_hint": email_hint,
                "expires_at": (
                    invitation.expires_at.isoformat() if invitation.expires_at else None
                ),
                "created_at": (
                    invitation.created_at.isoformat() if invitation.created_at else None
                ),
            },
            status_code=201,
        )

    except Exception as exc:
        db.session.rollback()
        logger.error("api", "invitations", f"Failed to create invitation: {exc}")
        return error_response(
            "INTERNAL_ERROR", "Failed to create invitation", status_code=500
        )


# ──────────────────────────────────────────
# GET /invitations
# ──────────────────────────────────────────


@invitations_bp.route("", methods=["GET"])
@require_auth
@require_role(RoleType.ORG_ADMIN)
def list_invitations():
    """List invitations for caller's org, or all if platform_admin."""
    try:
        current_user = g.current_user
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)
        status_filter = request.args.get("status")

        query = InvitationCode.query

        # Platform admins see all; org admins see their org only
        if current_user.role != RoleType.PLATFORM_ADMIN.value:
            org_id = current_user.organization_id
            if org_id:
                query = query.filter(InvitationCode.organization_id == org_id)
            else:
                # Org admin with no org context - return empty
                return list_response(
                    [],
                    {
                        "page": 1,
                        "per_page": per_page,
                        "total": 0,
                        "total_pages": 1,
                        "has_next": False,
                        "has_prev": False,
                    },
                )

        # Apply status filter
        if status_filter:
            try:
                InvitationStatus(status_filter)
                query = query.filter(InvitationCode.status == status_filter)
            except ValueError:
                return error_response(
                    "VALIDATION_ERROR",
                    f"Invalid status filter. Must be one of: {', '.join(s.value for s in InvitationStatus)}",
                )

        query = query.order_by(InvitationCode.created_at.desc())
        result = paginate_query(query, page, per_page)

        items = [
            {
                "id": inv.id,
                "code": inv.code,
                "issuer_id": inv.issuer_id,
                "organization_id": inv.organization_id,
                "target_role": inv.target_role,
                "status": inv.status,
                "redeemed_by_id": inv.redeemed_by_id,
                "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "redeemed_at": inv.redeemed_at.isoformat() if inv.redeemed_at else None,
            }
            for inv in result["items"]
        ]

        logger.info(
            "api",
            "invitations",
            f"Listed invitations page={page}",
            user_id=current_user.user_id,
        )
        return list_response(items, result["pagination"])

    except Exception as exc:
        logger.error("api", "invitations", f"Failed to list invitations: {exc}")
        return error_response(
            "INTERNAL_ERROR", "Failed to list invitations", status_code=500
        )


# ──────────────────────────────────────────
# POST /invitations/redeem
# ──────────────────────────────────────────


@invitations_bp.route("/redeem", methods=["POST"])
@require_auth
def redeem_invitation():
    """Redeem an invitation code to join an organization."""
    try:
        data = request.get_json(silent=True) or {}
        current_user = g.current_user

        errors = validate_required(data, ["code"])
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        code = data["code"]

        # Find invitation by code
        invitation = InvitationCode.query.filter_by(code=code).first()
        if not invitation:
            return error_response(
                "NOT_FOUND", "Invitation code not found", status_code=404
            )

        # Must be PENDING
        if invitation.status != InvitationStatus.PENDING.value:
            return error_response(
                "INVALID_STATE",
                f"Invitation is no longer available (status: {invitation.status})",
                status_code=410,
            )

        # Check expiration
        now = datetime.now(timezone.utc)
        exp_at = invitation.expires_at
        if exp_at and exp_at.tzinfo is None:
            exp_at = exp_at.replace(tzinfo=timezone.utc)
        if exp_at and now > exp_at:
            invitation.status = InvitationStatus.EXPIRED.value
            db.session.commit()
            return error_response(
                "EXPIRED", "Invitation code has expired", status_code=410
            )

        # Create or update membership
        membership = Membership.query.filter_by(
            user_id=current_user.user_id,
            organization_id=invitation.organization_id,
        ).first()

        if membership:
            # Update existing membership
            membership.role = invitation.target_role
            membership.is_active = True
        else:
            # Create new membership
            membership = Membership(
                user_id=current_user.user_id,
                organization_id=invitation.organization_id,
                role=invitation.target_role,
                is_active=True,
            )
            db.session.add(membership)

        # Update invitation
        invitation.status = InvitationStatus.REDEEMED.value
        invitation.redeemed_by_id = current_user.user_id
        invitation.redeemed_at = now

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.INVITATION_REDEEMED.value,
            actor_id=current_user.user_id,
            actor_ip=request.remote_addr,
            target_type="InvitationCode",
            target_id=invitation.id,
            organization_id=invitation.organization_id,
            after_state=json.dumps(
                {
                    "code": code,
                    "organization_id": invitation.organization_id,
                    "target_role": invitation.target_role,
                    "redeemed_by_id": current_user.user_id,
                }
            ),
        )
        db.session.add(audit)

        # Re-issue tokens with the new membership role and org context
        user = User.query.get(current_user.user_id)
        from src.api.auth import _resolve_effective_role, _get_user_permissions

        effective_role = _resolve_effective_role(user.role, membership.role)
        org_id = invitation.organization_id
        permission_codes = _get_user_permissions(user.id, org_id)

        access_token = create_access_token(
            user_id=user.id,
            username=user.username,
            role=effective_role,
            organization_id=org_id,
            permissions=permission_codes,
        )
        refresh_token = create_refresh_token(user_id=user.id)

        _rt_hashed = hash_token(refresh_token)
        rt_record = RefreshToken(
            user_id=user.id,
            token_hash=_rt_hashed,
            token_lookup_hash=_rt_hashed,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=config.JWT_REFRESH_TOKEN_EXPIRES_DAYS),
        )
        db.session.add(rt_record)
        db.session.commit()

        logger.info(
            "api",
            "invitations",
            f"Invitation redeemed: code={code} org={invitation.organization_id}",
            user_id=current_user.user_id,
        )
        return success_response(
            {
                "membership_id": membership.id,
                "organization_id": invitation.organization_id,
                "role": effective_role,
                "invitation_id": invitation.id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": config.JWT_ACCESS_TOKEN_EXPIRES_MINUTES * 60,
            }
        )

    except Exception as exc:
        db.session.rollback()
        logger.error("api", "invitations", f"Failed to redeem invitation: {exc}")
        return error_response(
            "INTERNAL_ERROR", "Failed to redeem invitation", status_code=500
        )


# ──────────────────────────────────────────
# POST /invitations/revoke
# ──────────────────────────────────────────


@invitations_bp.route("/revoke", methods=["POST"])
@require_auth
@require_role(RoleType.ORG_ADMIN)
def revoke_invitation():
    """Revoke a pending invitation."""
    try:
        data = request.get_json(silent=True) or {}
        current_user = g.current_user

        errors = validate_required(data, ["invitation_id"])
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        invitation_id = data["invitation_id"]
        errors = validate_uuid(invitation_id, "invitation_id")
        if errors:
            return error_response("VALIDATION_ERROR", "Invalid input", details=errors)

        invitation = InvitationCode.query.get(invitation_id)
        if not invitation:
            return error_response("NOT_FOUND", "Invitation not found", status_code=404)

        # Verify invitation belongs to caller's org (unless platform admin)
        if current_user.role != RoleType.PLATFORM_ADMIN.value:
            if invitation.organization_id != current_user.organization_id:
                return error_response(
                    "FORBIDDEN",
                    "Invitation does not belong to your organization",
                    status_code=403,
                )

        # Must be PENDING to revoke
        if invitation.status != InvitationStatus.PENDING.value:
            return error_response(
                "INVALID_STATE",
                f"Cannot revoke invitation with status '{invitation.status}'",
                status_code=409,
            )

        invitation.status = InvitationStatus.REVOKED.value

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.INVITATION_REVOKED.value,
            actor_id=current_user.user_id,
            actor_ip=request.remote_addr,
            target_type="InvitationCode",
            target_id=invitation.id,
            organization_id=invitation.organization_id,
            before_state=json.dumps({"status": InvitationStatus.PENDING.value}),
            after_state=json.dumps({"status": InvitationStatus.REVOKED.value}),
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(
            "api",
            "invitations",
            f"Invitation revoked: id={invitation_id}",
            user_id=current_user.user_id,
        )
        return success_response(
            {
                "message": "Invitation revoked successfully",
                "invitation_id": invitation_id,
                "status": invitation.status,
            }
        )

    except Exception as exc:
        db.session.rollback()
        logger.error("api", "invitations", f"Failed to revoke invitation: {exc}")
        return error_response(
            "INTERNAL_ERROR", "Failed to revoke invitation", status_code=500
        )
