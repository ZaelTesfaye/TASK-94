"""Booking endpoints - plan section 6.4."""

from datetime import datetime, timezone, timedelta, time as dt_time

from flask import Blueprint, request, g, make_response
from sqlalchemy import and_, or_

import hashlib
import json
import uuid

from src.models.base import db
from src.models.models import Resource, SlotTemplate, Reservation, IdempotencyRecord, AuditEvent, Membership
from src.models.enums import RoleType, ReservationStatus, RESERVATION_TRANSITIONS, AuditEventType
from src.security.auth_middleware import require_auth, require_role, require_org_context, check_object_ownership
from src.utils.responses import success_response, error_response, list_response
from src.utils.pagination import paginate_query
from src.utils.validators import validate_required, validate_uuid, validate_datetime_str
from src.logging import logger
from src.config import config

booking_bp = Blueprint("booking", __name__, url_prefix="")


# ──────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────

def _hash_idempotency_key(key: str) -> str:
    """SHA-256 hash of an idempotency key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _check_idempotency(user_id: str, endpoint: str, key: str):
    """Look up an existing idempotency record.

    Returns (response_code, response_body) tuple if a valid (non-expired)
    record exists, otherwise None.
    """
    key_hash = _hash_idempotency_key(key)
    record = IdempotencyRecord.query.filter_by(
        user_id=user_id,
        endpoint=endpoint,
        key_hash=key_hash,
    ).first()
    if record is None:
        return None
    rec_expires = record.expires_at
    if rec_expires.tzinfo is None:
        rec_expires = rec_expires.replace(tzinfo=timezone.utc)
    if rec_expires < datetime.now(timezone.utc):
        # Expired record - delete it and treat as new request
        db.session.delete(record)
        db.session.commit()
        return None
    return record.response_code, record.response_body


def _store_idempotency(user_id: str, endpoint: str, key: str, response_code: int, response_body: str):
    """Store an idempotency record with configured TTL."""
    key_hash = _hash_idempotency_key(key)
    record = IdempotencyRecord(
        user_id=user_id,
        endpoint=endpoint,
        key_hash=key_hash,
        response_code=response_code,
        response_body=response_body,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=config.IDEMPOTENCY_WINDOW_HOURS),
    )
    db.session.add(record)


def _check_overlap(resource_id: str, start_time: datetime, end_time: datetime, exclude_reservation_id: str = None):
    """Check for overlapping HELD/CONFIRMED reservations including buffer.

    Args:
        resource_id: The resource to check against.
        start_time: Desired reservation start.
        end_time: Desired reservation end.
        exclude_reservation_id: Reservation ID to exclude (used during reschedule).

    Returns:
        Tuple of (has_conflict: bool, count: int) where count is the number
        of active reservations that overlap the buffered time window.
    """
    buffer = timedelta(minutes=config.BOOKING_BUFFER_MINUTES)
    buffered_start = start_time - buffer
    buffered_end = end_time + buffer

    active_statuses = [ReservationStatus.HELD.value, ReservationStatus.CONFIRMED.value]

    query = Reservation.query.filter(
        Reservation.resource_id == resource_id,
        Reservation.status.in_(active_statuses),
        Reservation.start_time < buffered_end,
        Reservation.end_time > buffered_start,
    )
    if exclude_reservation_id:
        query = query.filter(Reservation.id != exclude_reservation_id)

    count = query.count()
    return (count > 0, count)


def _get_slot_quota(resource_id: str, start_time: datetime, end_time: datetime) -> int:
    """Determine the quota for a given time window.

    Looks up the matching SlotTemplate for the resource and day_of_week.
    If no template matches, falls back to the resource's capacity field.
    """
    target_date = start_time.date()
    day_of_week = target_date.weekday()
    request_start_time = start_time.time()
    request_end_time = end_time.time()

    # Find a matching slot template
    template = SlotTemplate.query.filter(
        SlotTemplate.resource_id == resource_id,
        SlotTemplate.day_of_week == day_of_week,
        SlotTemplate.is_active == True,
        SlotTemplate.start_time <= request_start_time,
        SlotTemplate.end_time >= request_end_time,
    ).first()

    if template:
        return template.quota

    # Fallback: use the resource capacity
    resource = Resource.query.get(resource_id)
    if resource:
        return resource.capacity
    return 1


def _serialize_resource(resource: Resource) -> dict:
    """Serialize a Resource model to dict."""
    return {
        "id": resource.id,
        "organization_id": resource.organization_id,
        "name": resource.name,
        "description": resource.description,
        "resource_type": resource.resource_type,
        "capacity": resource.capacity,
        "is_active": resource.is_active,
        "created_at": resource.created_at.isoformat(),
        "updated_at": resource.updated_at.isoformat(),
    }


def _serialize_slot_template(template: SlotTemplate) -> dict:
    """Serialize a SlotTemplate model to dict."""
    return {
        "id": template.id,
        "resource_id": template.resource_id,
        "day_of_week": template.day_of_week,
        "start_time": template.start_time.strftime("%H:%M"),
        "end_time": template.end_time.strftime("%H:%M"),
        "quota": template.quota,
        "is_active": template.is_active,
        "created_at": template.created_at.isoformat(),
    }


def _serialize_reservation(reservation: Reservation) -> dict:
    """Serialize a Reservation model to dict."""
    return {
        "id": reservation.id,
        "user_id": reservation.user_id,
        "resource_id": reservation.resource_id,
        "organization_id": reservation.organization_id,
        "status": reservation.status,
        "start_time": reservation.start_time.isoformat(),
        "end_time": reservation.end_time.isoformat(),
        "hold_expires_at": reservation.hold_expires_at.isoformat() if reservation.hold_expires_at else None,
        "version": reservation.version,
        "notes": reservation.notes,
        "created_at": reservation.created_at.isoformat(),
        "updated_at": reservation.updated_at.isoformat(),
    }


def _is_platform_admin() -> bool:
    """Check if the current user is a platform admin."""
    return getattr(g.current_user, "role", None) == RoleType.PLATFORM_ADMIN.value


def _make_idempotent_response(resp_code: int, resp_body: str):
    """Build a Flask response for an idempotent replay."""
    response = make_response(resp_body, resp_code)
    response.headers["Content-Type"] = "application/json"
    response.headers["X-Idempotent-Replay"] = "true"
    return response


# ──────────────────────────────────────────
# POST /resources
# ──────────────────────────────────────────
@booking_bp.route("/resources", methods=["POST"])
@require_auth
@require_role(RoleType.ORG_ADMIN)
def create_resource():
    """Create a new bookable resource."""
    try:
        data = request.get_json(silent=True) or {}
        errors = validate_required(data, ["name", "organization_id"])
        if errors:
            return error_response("VALIDATION_ERROR", "Missing required fields", details=errors, status_code=400)

        name = data["name"]
        description = data.get("description")
        resource_type = data.get("resource_type")
        capacity = data.get("capacity", 1)
        organization_id = data["organization_id"]

        uuid_errors = validate_uuid(organization_id, "organization_id")
        if uuid_errors:
            return error_response("VALIDATION_ERROR", "Invalid organization_id", details=uuid_errors, status_code=400)

        # Org admin can only create for their org; platform admin for any
        current = g.current_user
        if not _is_platform_admin():
            if current.organization_id != organization_id:
                # Also check membership
                membership = Membership.query.filter_by(
                    user_id=current.user_id,
                    organization_id=organization_id,
                    is_active=True,
                ).first()
                if not membership:
                    return error_response("FORBIDDEN", "You can only create resources for your own organization", status_code=403)

        resource = Resource(
            name=name,
            description=description,
            resource_type=resource_type,
            capacity=capacity,
            organization_id=organization_id,
        )
        db.session.add(resource)
        db.session.commit()

        logger.info("booking", "create-resource", f"Resource created: id={resource.id} org={organization_id}")

        return success_response(_serialize_resource(resource), status_code=201)

    except Exception as exc:
        db.session.rollback()
        logger.error("booking", "create-resource", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# GET /resources
# ──────────────────────────────────────────
@booking_bp.route("/resources", methods=["GET"])
@require_auth
def list_resources():
    """List resources, scoped by organization."""
    try:
        current = g.current_user
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", config.DEFAULT_PAGE_SIZE, type=int)
        resource_type = request.args.get("resource_type")
        is_active = request.args.get("is_active")

        query = Resource.query

        # Scope by org
        if _is_platform_admin():
            org_filter = request.args.get("organization_id")
            if org_filter:
                query = query.filter(Resource.organization_id == org_filter)
        else:
            if current.organization_id:
                query = query.filter(Resource.organization_id == current.organization_id)
            else:
                # User has no org context - return empty
                return list_response([], {"page": 1, "per_page": per_page, "total": 0, "total_pages": 1, "has_next": False, "has_prev": False})

        # Optional filters
        if resource_type:
            query = query.filter(Resource.resource_type == resource_type)
        if is_active is not None:
            active_val = is_active.lower() in ("true", "1", "yes") if isinstance(is_active, str) else bool(is_active)
            query = query.filter(Resource.is_active == active_val)

        query = query.order_by(Resource.created_at.desc())
        result = paginate_query(query, page, per_page)

        items = [_serialize_resource(r) for r in result["items"]]
        return list_response(items, result["pagination"])

    except Exception as exc:
        logger.error("booking", "list-resources", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /slot-templates
# ──────────────────────────────────────────
@booking_bp.route("/slot-templates", methods=["POST"])
@require_auth
@require_role(RoleType.ORG_ADMIN)
def create_slot_template():
    """Create a recurring slot template for a resource."""
    try:
        data = request.get_json(silent=True) or {}
        errors = validate_required(data, ["resource_id", "day_of_week", "start_time", "end_time"])
        if errors:
            return error_response("VALIDATION_ERROR", "Missing required fields", details=errors, status_code=400)

        resource_id = data["resource_id"]
        day_of_week = data["day_of_week"]
        start_time_str = data["start_time"]
        end_time_str = data["end_time"]
        quota = data.get("quota", config.DEFAULT_SLOT_QUOTA)

        # Validate resource_id
        uuid_errors = validate_uuid(resource_id, "resource_id")
        if uuid_errors:
            return error_response("VALIDATION_ERROR", "Invalid resource_id", details=uuid_errors, status_code=400)

        # Validate day_of_week
        if not isinstance(day_of_week, int) or day_of_week < 0 or day_of_week > 6:
            return error_response("VALIDATION_ERROR", "day_of_week must be an integer 0-6", status_code=400)

        # Parse times
        try:
            start_time = dt_time.fromisoformat(start_time_str)
        except (ValueError, TypeError):
            return error_response("VALIDATION_ERROR", "start_time must be HH:MM format", status_code=400)
        try:
            end_time = dt_time.fromisoformat(end_time_str)
        except (ValueError, TypeError):
            return error_response("VALIDATION_ERROR", "end_time must be HH:MM format", status_code=400)

        if start_time >= end_time:
            return error_response("VALIDATION_ERROR", "start_time must be before end_time", status_code=400)

        # Verify resource exists and belongs to caller's org
        resource = Resource.query.get(resource_id)
        if resource is None:
            return error_response("NOT_FOUND", "Resource not found", status_code=404)

        current = g.current_user
        if not _is_platform_admin():
            if resource.organization_id != current.organization_id:
                membership = Membership.query.filter_by(
                    user_id=current.user_id,
                    organization_id=resource.organization_id,
                    is_active=True,
                ).first()
                if not membership:
                    return error_response("FORBIDDEN", "Resource does not belong to your organization", status_code=403)

        template = SlotTemplate(
            resource_id=resource_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            quota=quota,
        )
        db.session.add(template)
        db.session.commit()

        logger.info("booking", "create-slot-template", f"Slot template created: id={template.id} resource={resource_id}")

        return success_response(_serialize_slot_template(template), status_code=201)

    except Exception as exc:
        db.session.rollback()
        logger.error("booking", "create-slot-template", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# GET /availability
# ──────────────────────────────────────────
@booking_bp.route("/availability", methods=["GET"])
@require_auth
def get_availability():
    """Return per-slot availability for a resource on a given date."""
    try:
        resource_id = request.args.get("resource_id")
        date_str = request.args.get("date")

        if not resource_id:
            return error_response("VALIDATION_ERROR", "resource_id is required", status_code=400)
        if not date_str:
            return error_response("VALIDATION_ERROR", "date is required", status_code=400)

        uuid_errors = validate_uuid(resource_id, "resource_id")
        if uuid_errors:
            return error_response("VALIDATION_ERROR", "Invalid resource_id", details=uuid_errors, status_code=400)

        # Parse date
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return error_response("VALIDATION_ERROR", "date must be YYYY-MM-DD format", status_code=400)

        resource = Resource.query.get(resource_id)
        if resource is None:
            return error_response("NOT_FOUND", "Resource not found", status_code=404)

        # day_of_week: Monday=0, Sunday=6
        day_of_week = target_date.weekday()

        templates = SlotTemplate.query.filter_by(
            resource_id=resource_id,
            day_of_week=day_of_week,
            is_active=True,
        ).all()

        active_statuses = [ReservationStatus.HELD.value, ReservationStatus.CONFIRMED.value]
        slots = []

        for template in templates:
            slot_start = datetime.combine(target_date, template.start_time, tzinfo=timezone.utc)
            slot_end = datetime.combine(target_date, template.end_time, tzinfo=timezone.utc)

            # Count existing active reservations overlapping this window
            booked_count = Reservation.query.filter(
                Reservation.resource_id == resource_id,
                Reservation.status.in_(active_statuses),
                Reservation.start_time < slot_end,
                Reservation.end_time > slot_start,
            ).count()

            available_count = max(0, template.quota - booked_count)
            slots.append({
                "slot_template_id": template.id,
                "start_time": slot_start.isoformat(),
                "end_time": slot_end.isoformat(),
                "quota": template.quota,
                "booked_count": booked_count,
                "available_count": available_count,
            })

        return success_response({
            "resource_id": resource_id,
            "date": date_str,
            "slots": slots,
        })

    except Exception as exc:
        logger.error("booking", "availability", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /reservations/hold
# ──────────────────────────────────────────
@booking_bp.route("/reservations/hold", methods=["POST"])
@require_auth
def create_hold():
    """Create a new reservation hold (two-phase booking step 1)."""
    try:
        current = g.current_user

        # Idempotency-Key from header (required)
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return error_response("VALIDATION_ERROR", "Idempotency-Key header is required", status_code=400)

        data = request.get_json(silent=True) or {}

        errors = validate_required(data, ["resource_id", "start_time", "end_time", "organization_id"])
        if errors:
            return error_response("VALIDATION_ERROR", "Missing required fields", details=errors, status_code=400)

        resource_id = data["resource_id"]
        start_time_str = data["start_time"]
        end_time_str = data["end_time"]
        organization_id = data["organization_id"]
        notes = data.get("notes")

        # Validate UUIDs
        uuid_errors = validate_uuid(resource_id, "resource_id")
        uuid_errors += validate_uuid(organization_id, "organization_id")
        if uuid_errors:
            return error_response("VALIDATION_ERROR", "Invalid UUID field", details=uuid_errors, status_code=400)

        # Validate datetimes
        dt_errors = validate_datetime_str(start_time_str, "start_time")
        dt_errors += validate_datetime_str(end_time_str, "end_time")
        if dt_errors:
            return error_response("VALIDATION_ERROR", "Invalid datetime format", details=dt_errors, status_code=400)

        # Idempotency check (before any mutations)
        existing = _check_idempotency(current.user_id, "reservations/hold", idempotency_key)
        if existing is not None:
            resp_code, resp_body = existing
            return _make_idempotent_response(resp_code, resp_body)

        # Parse times
        start_time = datetime.fromisoformat(start_time_str)
        end_time = datetime.fromisoformat(end_time_str)

        # Ensure timezone-aware (default to UTC)
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        if start_time >= end_time:
            return error_response("VALIDATION_ERROR", "start_time must be before end_time", status_code=400)

        # Future-only check
        now = datetime.now(timezone.utc)
        if start_time <= now:
            return error_response("VALIDATION_ERROR", "start_time must be in the future", status_code=400)

        # Check resource exists
        resource = Resource.query.get(resource_id)
        if resource is None:
            return error_response("NOT_FOUND", "Resource not found", status_code=404)

        # Active hold cap per user
        held_count = Reservation.query.filter_by(
            user_id=current.user_id,
            status=ReservationStatus.HELD.value,
        ).count()
        if held_count >= config.MAX_ACTIVE_HOLDS_PER_USER:
            return error_response(
                "HOLD_LIMIT_REACHED",
                f"Maximum {config.MAX_ACTIVE_HOLDS_PER_USER} active holds allowed",
                status_code=429,
            )

        # Overlap detection (with buffer) - quota-aware
        has_conflict, overlap_count = _check_overlap(resource_id, start_time, end_time)
        slot_quota = _get_slot_quota(resource_id, start_time, end_time)
        if overlap_count >= slot_quota:
            return error_response(
                "SLOT_UNAVAILABLE",
                "The requested time slot overlaps with an existing reservation",
                status_code=409,
            )

        # Create reservation
        reservation = Reservation(
            user_id=current.user_id,
            resource_id=resource_id,
            organization_id=organization_id,
            status=ReservationStatus.HELD.value,
            start_time=start_time,
            end_time=end_time,
            hold_expires_at=now + timedelta(minutes=config.HOLD_EXPIRY_MINUTES),
            version=1,
            notes=notes,
        )
        db.session.add(reservation)
        db.session.flush()

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.RESERVATION_HELD.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="Reservation",
            target_id=reservation.id,
            organization_id=organization_id,
            after_state=json.dumps(_serialize_reservation(reservation)),
        )
        db.session.add(audit)

        # Prepare response body for idempotency storage
        response_data = _serialize_reservation(reservation)
        from src.utils.responses import _meta
        response_body = json.dumps({"data": response_data, "meta": _meta()})

        _store_idempotency(current.user_id, "reservations/hold", idempotency_key, 201, response_body)

        db.session.commit()

        logger.info(
            "booking", "hold",
            f"Hold created: reservation_id={reservation.id} resource={resource_id} user={current.user_id}",
        )

        return success_response(response_data, status_code=201)

    except Exception as exc:
        db.session.rollback()
        logger.error("booking", "hold", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /reservations/<id>/confirm
# ──────────────────────────────────────────
@booking_bp.route("/reservations/<reservation_id>/confirm", methods=["POST"])
@require_auth
def confirm_reservation(reservation_id):
    """Confirm a held reservation (two-phase booking step 2)."""
    try:
        current = g.current_user

        # Idempotency-Key from header (required)
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return error_response("VALIDATION_ERROR", "Idempotency-Key header is required", status_code=400)

        data = request.get_json(silent=True) or {}

        errors = validate_required(data, ["version"])
        if errors:
            return error_response("VALIDATION_ERROR", "Missing required fields", details=errors, status_code=400)

        version = data["version"]

        # Idempotency check
        endpoint = f"reservations/{reservation_id}/confirm"
        existing = _check_idempotency(current.user_id, endpoint, idempotency_key)
        if existing is not None:
            resp_code, resp_body = existing
            return _make_idempotent_response(resp_code, resp_body)

        # Find reservation
        reservation = Reservation.query.get(reservation_id)
        if reservation is None:
            return error_response("NOT_FOUND", "Reservation not found", status_code=404)

        # Ownership check
        if not check_object_ownership(reservation):
            return error_response("FORBIDDEN", "You do not have access to this reservation", status_code=403)

        # Optimistic concurrency check
        if version != reservation.version:
            return error_response(
                "VERSION_CONFLICT",
                f"Expected version {reservation.version}, got {version}",
                status_code=409,
            )

        # Check status is HELD (valid transition)
        current_status = ReservationStatus(reservation.status)
        if ReservationStatus.CONFIRMED not in RESERVATION_TRANSITIONS.get(current_status, set()):
            return error_response(
                "INVALID_STATE",
                f"Cannot confirm reservation in state {reservation.status}",
                status_code=409,
            )

        # Check hold not expired
        now = datetime.now(timezone.utc)
        hold_exp = reservation.hold_expires_at
        if hold_exp and hold_exp.tzinfo is None:
            hold_exp = hold_exp.replace(tzinfo=timezone.utc)
        if hold_exp and hold_exp < now:
            # Auto-release the expired hold
            before_state = json.dumps(_serialize_reservation(reservation))
            reservation.status = ReservationStatus.RELEASED.value
            reservation.version += 1

            audit = AuditEvent(
                event_type=AuditEventType.RESERVATION_RELEASED.value,
                actor_id=current.user_id,
                actor_ip=request.remote_addr,
                target_type="Reservation",
                target_id=reservation.id,
                organization_id=reservation.organization_id,
                before_state=before_state,
                after_state=json.dumps(_serialize_reservation(reservation)),
            )
            db.session.add(audit)
            db.session.commit()

            logger.info(
                "booking", "confirm",
                f"Hold expired, auto-released: id={reservation.id} user={current.user_id}",
            )
            return error_response(
                "HOLD_EXPIRED",
                "The hold has expired and the reservation has been released",
                status_code=410,
            )

        # Perform the confirmation
        before_state = json.dumps(_serialize_reservation(reservation))
        reservation.status = ReservationStatus.CONFIRMED.value
        reservation.version += 1
        reservation.hold_expires_at = None  # Clear hold expiry on confirm

        audit = AuditEvent(
            event_type=AuditEventType.RESERVATION_CONFIRMED.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="Reservation",
            target_id=reservation.id,
            organization_id=reservation.organization_id,
            before_state=before_state,
            after_state=json.dumps(_serialize_reservation(reservation)),
        )
        db.session.add(audit)

        # Store idempotency record
        response_data = _serialize_reservation(reservation)
        from src.utils.responses import _meta
        response_body = json.dumps({"data": response_data, "meta": _meta()})
        _store_idempotency(current.user_id, endpoint, idempotency_key, 200, response_body)

        db.session.commit()

        logger.info("booking", "confirm", f"Reservation confirmed: id={reservation.id} user={current.user_id}")

        return success_response(response_data)

    except Exception as exc:
        db.session.rollback()
        logger.error("booking", "confirm", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /reservations/<id>/cancel
# ──────────────────────────────────────────
@booking_bp.route("/reservations/<reservation_id>/cancel", methods=["POST"])
@require_auth
def cancel_reservation(reservation_id):
    """Cancel a held or confirmed reservation."""
    try:
        current = g.current_user

        # Idempotency-Key from header (required)
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return error_response("VALIDATION_ERROR", "Idempotency-Key header is required", status_code=400)

        data = request.get_json(silent=True) or {}

        errors = validate_required(data, ["version"])
        if errors:
            return error_response("VALIDATION_ERROR", "Missing required fields", details=errors, status_code=400)

        version = data["version"]

        # Idempotency check
        endpoint = f"reservations/{reservation_id}/cancel"
        existing = _check_idempotency(current.user_id, endpoint, idempotency_key)
        if existing is not None:
            resp_code, resp_body = existing
            return _make_idempotent_response(resp_code, resp_body)

        # Find reservation
        reservation = Reservation.query.get(reservation_id)
        if reservation is None:
            return error_response("NOT_FOUND", "Reservation not found", status_code=404)

        # Ownership check
        if not check_object_ownership(reservation):
            return error_response("FORBIDDEN", "You do not have access to this reservation", status_code=403)

        # Version check
        if version != reservation.version:
            return error_response(
                "VERSION_CONFLICT",
                f"Expected version {reservation.version}, got {version}",
                status_code=409,
            )

        # Check valid transition (HELD->CANCELLED or CONFIRMED->CANCELLED)
        current_status = ReservationStatus(reservation.status)
        if ReservationStatus.CANCELLED not in RESERVATION_TRANSITIONS.get(current_status, set()):
            return error_response(
                "INVALID_STATE",
                f"Cannot cancel reservation in state {reservation.status}",
                status_code=409,
            )

        before_state = json.dumps(_serialize_reservation(reservation))
        reservation.status = ReservationStatus.CANCELLED.value
        reservation.version += 1

        audit = AuditEvent(
            event_type=AuditEventType.RESERVATION_CANCELLED.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="Reservation",
            target_id=reservation.id,
            organization_id=reservation.organization_id,
            before_state=before_state,
            after_state=json.dumps(_serialize_reservation(reservation)),
        )
        db.session.add(audit)

        # Store idempotency record
        response_data = _serialize_reservation(reservation)
        from src.utils.responses import _meta
        response_body = json.dumps({"data": response_data, "meta": _meta()})
        _store_idempotency(current.user_id, endpoint, idempotency_key, 200, response_body)

        db.session.commit()

        logger.info("booking", "cancel", f"Reservation cancelled: id={reservation.id} user={current.user_id}")

        return success_response(response_data)

    except Exception as exc:
        db.session.rollback()
        logger.error("booking", "cancel", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /reservations/<id>/reschedule
# ──────────────────────────────────────────
@booking_bp.route("/reservations/<reservation_id>/reschedule", methods=["POST"])
@require_auth
def reschedule_reservation(reservation_id):
    """Reschedule a confirmed reservation to a new time window."""
    try:
        current = g.current_user

        # Idempotency-Key from header (required)
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return error_response("VALIDATION_ERROR", "Idempotency-Key header is required", status_code=400)

        data = request.get_json(silent=True) or {}

        errors = validate_required(data, ["new_start_time", "new_end_time", "version"])
        if errors:
            return error_response("VALIDATION_ERROR", "Missing required fields", details=errors, status_code=400)

        new_start_str = data["new_start_time"]
        new_end_str = data["new_end_time"]
        version = data["version"]

        # Validate datetimes
        dt_errors = validate_datetime_str(new_start_str, "new_start_time")
        dt_errors += validate_datetime_str(new_end_str, "new_end_time")
        if dt_errors:
            return error_response("VALIDATION_ERROR", "Invalid datetime format", details=dt_errors, status_code=400)

        # Idempotency check
        endpoint = f"reservations/{reservation_id}/reschedule"
        existing = _check_idempotency(current.user_id, endpoint, idempotency_key)
        if existing is not None:
            resp_code, resp_body = existing
            return _make_idempotent_response(resp_code, resp_body)

        # Find reservation
        reservation = Reservation.query.get(reservation_id)
        if reservation is None:
            return error_response("NOT_FOUND", "Reservation not found", status_code=404)

        # Ownership check
        if not check_object_ownership(reservation):
            return error_response("FORBIDDEN", "You do not have access to this reservation", status_code=403)

        # Version check
        if version != reservation.version:
            return error_response(
                "VERSION_CONFLICT",
                f"Expected version {reservation.version}, got {version}",
                status_code=409,
            )

        # Must be CONFIRMED to reschedule
        if reservation.status != ReservationStatus.CONFIRMED.value:
            return error_response(
                "INVALID_STATE",
                "Only CONFIRMED reservations can be rescheduled",
                status_code=409,
            )

        # Parse new times
        new_start = datetime.fromisoformat(new_start_str)
        new_end = datetime.fromisoformat(new_end_str)

        if new_start.tzinfo is None:
            new_start = new_start.replace(tzinfo=timezone.utc)
        if new_end.tzinfo is None:
            new_end = new_end.replace(tzinfo=timezone.utc)

        if new_start >= new_end:
            return error_response("VALIDATION_ERROR", "new_start_time must be before new_end_time", status_code=400)

        # Same duration check
        old_duration = reservation.end_time - reservation.start_time
        new_duration = new_end - new_start
        if abs((new_duration - old_duration).total_seconds()) > 1:  # 1-second tolerance
            return error_response(
                "VALIDATION_ERROR",
                "New time window must have the same duration as the original",
                status_code=400,
            )

        # Future-only check
        now = datetime.now(timezone.utc)
        if new_start <= now:
            return error_response("VALIDATION_ERROR", "new_start_time must be in the future", status_code=400)

        # Overlap check on new window (exclude current reservation)
        has_conflict, overlap_count = _check_overlap(
            reservation.resource_id, new_start, new_end, exclude_reservation_id=reservation.id,
        )
        slot_quota = _get_slot_quota(reservation.resource_id, new_start, new_end)
        if overlap_count >= slot_quota:
            return error_response(
                "SLOT_UNAVAILABLE",
                "The new time slot overlaps with an existing reservation",
                status_code=409,
            )

        # Mark old reservation as RESCHEDULED
        before_state = json.dumps(_serialize_reservation(reservation))
        reservation.status = ReservationStatus.RESCHEDULED.value
        reservation.version += 1

        # Create new CONFIRMED reservation
        new_reservation = Reservation(
            user_id=current.user_id,
            resource_id=reservation.resource_id,
            organization_id=reservation.organization_id,
            status=ReservationStatus.CONFIRMED.value,
            start_time=new_start,
            end_time=new_end,
            hold_expires_at=None,
            version=1,
            notes=f"Rescheduled from reservation {reservation.id}",
        )
        db.session.add(new_reservation)
        db.session.flush()

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.RESERVATION_RESCHEDULED.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="Reservation",
            target_id=reservation.id,
            organization_id=reservation.organization_id,
            before_state=before_state,
            after_state=json.dumps({
                "old_reservation": _serialize_reservation(reservation),
                "new_reservation": _serialize_reservation(new_reservation),
            }),
        )
        db.session.add(audit)

        # Store idempotency record
        response_data = {
            "old_reservation": _serialize_reservation(reservation),
            "new_reservation": _serialize_reservation(new_reservation),
        }
        from src.utils.responses import _meta
        response_body = json.dumps({"data": response_data, "meta": _meta()})
        _store_idempotency(current.user_id, endpoint, idempotency_key, 200, response_body)

        db.session.commit()

        logger.info(
            "booking", "reschedule",
            f"Reservation rescheduled: old={reservation.id} new={new_reservation.id} user={current.user_id}",
        )

        return success_response(response_data)

    except Exception as exc:
        db.session.rollback()
        logger.error("booking", "reschedule", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# GET /reservations
# ──────────────────────────────────────────
@booking_bp.route("/reservations", methods=["GET"])
@require_auth
def list_reservations():
    """List reservations with org-scoped filtering, pagination, and sorting."""
    try:
        current = g.current_user
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", config.DEFAULT_PAGE_SIZE, type=int)
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")
        status_filter = request.args.get("status")
        resource_id_filter = request.args.get("resource_id")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")

        query = Reservation.query

        # Scope by user/org/platform
        if _is_platform_admin():
            pass  # No scoping - can see all
        elif current.role == RoleType.ORG_ADMIN.value and current.organization_id:
            query = query.filter(Reservation.organization_id == current.organization_id)
        else:
            query = query.filter(Reservation.user_id == current.user_id)

        # Apply filters
        if status_filter:
            query = query.filter(Reservation.status == status_filter)
        if resource_id_filter:
            query = query.filter(Reservation.resource_id == resource_id_filter)
        if start_date:
            try:
                from_dt = datetime.fromisoformat(start_date)
                if from_dt.tzinfo is None:
                    from_dt = from_dt.replace(tzinfo=timezone.utc)
                query = query.filter(Reservation.start_time >= from_dt)
            except ValueError:
                return error_response("VALIDATION_ERROR", "start_date must be a valid ISO datetime", status_code=400)
        if end_date:
            try:
                to_dt = datetime.fromisoformat(end_date)
                if to_dt.tzinfo is None:
                    to_dt = to_dt.replace(tzinfo=timezone.utc)
                query = query.filter(Reservation.start_time <= to_dt)
            except ValueError:
                return error_response("VALIDATION_ERROR", "end_date must be a valid ISO datetime", status_code=400)

        # Sorting
        if sort_by == "start_time":
            sort_column = Reservation.start_time
        else:
            sort_column = Reservation.created_at

        if sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        result = paginate_query(query, page, per_page)

        items = [_serialize_reservation(r) for r in result["items"]]
        return list_response(items, result["pagination"])

    except Exception as exc:
        logger.error("booking", "list-reservations", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)
