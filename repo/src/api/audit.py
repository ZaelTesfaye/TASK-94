"""Audit events and alerts API endpoints - plan section 9."""

from datetime import datetime, timezone

from flask import Blueprint, request, g

from src.models.base import db
from src.models.models import AuditEvent, Alert
from src.models.enums import (
    AlertSeverity, AlertStatus, AuditEventType, RoleType,
)
from src.security.auth_middleware import require_auth, require_role
from src.utils.responses import success_response, error_response, list_response
from src.utils.pagination import paginate_query
from src.logging import logger

audit_bp = Blueprint("audit", __name__, url_prefix="")


# ──────────────────────────────────────────
# GET /audit-events
# ──────────────────────────────────────────

@audit_bp.route("/audit-events", methods=["GET"])
@require_auth
@require_role(RoleType.ORG_ADMIN)
def list_audit_events():
    """List audit events (immutable, read-only). Org-scoped unless platform admin."""
    try:
        current_user = g.current_user

        # Pagination params
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        query = AuditEvent.query

        # Org-scoped unless platform admin
        if current_user.role != RoleType.PLATFORM_ADMIN.value:
            query = query.filter(AuditEvent.organization_id == current_user.organization_id)

        # Optional filters
        event_type = request.args.get("event_type")
        if event_type:
            query = query.filter(AuditEvent.event_type == event_type)

        actor_id = request.args.get("actor_id")
        if actor_id:
            query = query.filter(AuditEvent.actor_id == actor_id)

        target_type = request.args.get("target_type")
        if target_type:
            query = query.filter(AuditEvent.target_type == target_type)

        start_date = request.args.get("start_date")
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date)
                query = query.filter(AuditEvent.created_at >= start_dt)
            except (ValueError, TypeError):
                return error_response("VALIDATION_ERROR", "Invalid start_date format", status_code=400)

        end_date = request.args.get("end_date")
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date)
                query = query.filter(AuditEvent.created_at <= end_dt)
            except (ValueError, TypeError):
                return error_response("VALIDATION_ERROR", "Invalid end_date format", status_code=400)

        # Sorting
        sort_column = getattr(AuditEvent, sort_by, None)
        if sort_column is None:
            sort_column = AuditEvent.created_at
        if sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        result = paginate_query(query, page, per_page)

        items = [
            {
                "id": e.id,
                "event_type": e.event_type,
                "actor_id": e.actor_id,
                "actor_ip": e.actor_ip,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "organization_id": e.organization_id,
                "before_state": e.before_state,
                "after_state": e.after_state,
                "metadata_json": e.metadata_json,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in result["items"]
        ]

        logger.info(
            "api", "audit-events",
            f"Listed audit events page={page}",
            user_id=current_user.user_id,
        )
        return list_response(items, result["pagination"])

    except Exception as exc:
        logger.error("api", "audit-events", f"Failed to list audit events: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to list audit events", status_code=500)


# ──────────────────────────────────────────
# GET /alerts
# ──────────────────────────────────────────

@audit_bp.route("/alerts", methods=["GET"])
@require_auth
@require_role(RoleType.ORG_ADMIN)
def list_alerts():
    """List alerts. Org-scoped unless platform admin."""
    try:
        current_user = g.current_user

        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)

        query = Alert.query

        # Org-scoped unless platform admin
        if current_user.role != RoleType.PLATFORM_ADMIN.value:
            query = query.filter(Alert.organization_id == current_user.organization_id)

        # Optional filters
        severity = request.args.get("severity")
        if severity:
            query = query.filter(Alert.severity == severity)

        status = request.args.get("status")
        if status:
            query = query.filter(Alert.status == status)

        alert_type = request.args.get("alert_type")
        if alert_type:
            query = query.filter(Alert.alert_type == alert_type)

        query = query.order_by(Alert.created_at.desc())

        result = paginate_query(query, page, per_page)

        items = [
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "status": a.status,
                "title": a.title,
                "description": a.description,
                "organization_id": a.organization_id,
                "acknowledged_by": a.acknowledged_by,
                "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                "resolved_by": a.resolved_by,
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            }
            for a in result["items"]
        ]

        logger.info(
            "api", "alerts",
            f"Listed alerts page={page}",
            user_id=current_user.user_id,
        )
        return list_response(items, result["pagination"])

    except Exception as exc:
        logger.error("api", "alerts", f"Failed to list alerts: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to list alerts", status_code=500)


# ──────────────────────────────────────────
# POST /alerts/<id>/ack
# ──────────────────────────────────────────

@audit_bp.route("/alerts/<alert_id>/ack", methods=["POST"])
@require_auth
@require_role(RoleType.ORG_ADMIN)
def acknowledge_alert(alert_id):
    """Acknowledge an open alert."""
    try:
        current_user = g.current_user

        alert = Alert.query.get(alert_id)
        if alert is None:
            return error_response("NOT_FOUND", "Alert not found", status_code=404)

        # Org scope check
        if current_user.role != RoleType.PLATFORM_ADMIN.value:
            if alert.organization_id != current_user.organization_id:
                return error_response("FORBIDDEN", "Alert does not belong to your organization", status_code=403)

        # Verify status is OPEN
        if alert.status != AlertStatus.OPEN.value:
            return error_response(
                "INVALID_STATE",
                f"Alert must be OPEN to acknowledge, current status is {alert.status}",
                status_code=409,
            )

        alert.status = AlertStatus.ACKNOWLEDGED.value
        alert.acknowledged_by = current_user.user_id
        alert.acknowledged_at = datetime.now(timezone.utc)
        db.session.commit()

        logger.info(
            "api", "alerts",
            f"Alert acknowledged: alert_id={alert_id}",
            user_id=current_user.user_id,
        )

        return success_response({
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "status": alert.status,
            "title": alert.title,
            "description": alert.description,
            "organization_id": alert.organization_id,
            "acknowledged_by": alert.acknowledged_by,
            "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            "resolved_by": alert.resolved_by,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
        })

    except Exception as exc:
        db.session.rollback()
        logger.error("api", "alerts", f"Failed to acknowledge alert: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to acknowledge alert", status_code=500)


# ──────────────────────────────────────────
# POST /alerts/<id>/resolve
# ──────────────────────────────────────────

@audit_bp.route("/alerts/<alert_id>/resolve", methods=["POST"])
@require_auth
@require_role(RoleType.ORG_ADMIN)
def resolve_alert(alert_id):
    """Resolve an open or acknowledged alert."""
    try:
        current_user = g.current_user

        alert = Alert.query.get(alert_id)
        if alert is None:
            return error_response("NOT_FOUND", "Alert not found", status_code=404)

        # Org scope check
        if current_user.role != RoleType.PLATFORM_ADMIN.value:
            if alert.organization_id != current_user.organization_id:
                return error_response("FORBIDDEN", "Alert does not belong to your organization", status_code=403)

        # Verify status is OPEN or ACKNOWLEDGED
        allowed_statuses = {AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value}
        if alert.status not in allowed_statuses:
            return error_response(
                "INVALID_STATE",
                f"Alert must be OPEN or ACKNOWLEDGED to resolve, current status is {alert.status}",
                status_code=409,
            )

        alert.status = AlertStatus.RESOLVED.value
        alert.resolved_by = current_user.user_id
        alert.resolved_at = datetime.now(timezone.utc)
        db.session.commit()

        logger.info(
            "api", "alerts",
            f"Alert resolved: alert_id={alert_id}",
            user_id=current_user.user_id,
        )

        return success_response({
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "status": alert.status,
            "title": alert.title,
            "description": alert.description,
            "organization_id": alert.organization_id,
            "acknowledged_by": alert.acknowledged_by,
            "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            "resolved_by": alert.resolved_by,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
        })

    except Exception as exc:
        db.session.rollback()
        logger.error("api", "alerts", f"Failed to resolve alert: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to resolve alert", status_code=500)
