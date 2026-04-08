"""Auth endpoints - plan section 6.1."""

import json
from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, g

from src.models.base import db
from src.models.models import (
    User, RefreshToken, AccessTokenDenylist, Device, AuditEvent, Membership, Organization,
)
from src.models.enums import RoleType, ROLE_HIERARCHY, AuditEventType, DeviceStatus, UserStatus
from src.security.passwords import hash_password, verify_password
from src.security.tokens import create_access_token, create_refresh_token, decode_token, hash_token
from src.security.lockout import (
    check_lockout, record_failure, reset_failures, needs_captcha,
    create_captcha_challenge, verify_captcha,
)
from src.security.auth_middleware import require_auth
from src.security.encryption import encrypt_field, compute_fingerprint_lookup_hash
from src.utils.responses import success_response, error_response
from src.logging import logger
from src.config import config


def _resolve_effective_role(user_role: str, membership_role: str | None) -> str:
    """Return the higher of the user's global role and their membership role.

    Platform admins always retain platform_admin regardless of membership.
    For all other cases the membership role wins when it is higher than the
    global role in the hierarchy, and the global role acts as a floor.
    """
    if membership_role is None:
        return user_role
    try:
        user_level = ROLE_HIERARCHY[RoleType(user_role)]
        membership_level = ROLE_HIERARCHY[RoleType(membership_role)]
    except (ValueError, KeyError):
        return user_role
    return user_role if user_level >= membership_level else membership_role


def _get_user_permissions(user_id: str, org_id: str) -> list:
    """Load effective permission codes for a user in an org context."""
    from src.models.models import Permission, UserPermission
    query = db.session.query(Permission.code).join(
        UserPermission, UserPermission.permission_id == Permission.id
    ).filter(
        UserPermission.user_id == user_id,
    )
    if org_id:
        query = query.filter(
            db.or_(
                UserPermission.organization_id == org_id,
                UserPermission.organization_id.is_(None),
            ),
        )
    else:
        # No org context: load unscoped permissions only
        query = query.filter(UserPermission.organization_id.is_(None))
    return [r.code for r in query.all()]

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

FAILED_LOGIN_ALERT_THRESHOLD = 20
FAILED_LOGIN_WINDOW_SECONDS = 3600  # 1 hour


def _accumulate_device_risk(fingerprint_lookup_hash: str, ip: str):
    """Increment device risk score on failed login and auto-blacklist if threshold exceeded.

    When a device's accumulated risk score reaches DEVICE_RISK_BLACKLIST_THRESHOLD,
    the device is automatically transitioned to BLACKLISTED status with a cooldown
    period defined by DEVICE_BLACKLIST_RETRY_AFTER_HOURS.
    """
    try:
        device = Device.query.filter_by(
            fingerprint_lookup_hash=fingerprint_lookup_hash,
        ).first()
        if device is None or device.status == DeviceStatus.BLACKLISTED.value:
            return

        device.risk_score = min(
            device.risk_score + config.DEVICE_RISK_INCREMENT_PER_FAILURE,
            1.0,
        )

        if device.risk_score >= config.DEVICE_RISK_BLACKLIST_THRESHOLD:
            device.status = DeviceStatus.BLACKLISTED.value
            device.blacklisted_until = (
                datetime.now(timezone.utc)
                + timedelta(hours=config.DEVICE_BLACKLIST_RETRY_AFTER_HOURS)
            )

            audit = AuditEvent(
                event_type=AuditEventType.DEVICE_BLACKLISTED.value,
                actor_id="system",
                actor_ip=ip,
                target_type="Device",
                target_id=device.id,
                metadata_json=json.dumps({
                    "reason": "risk_score_threshold_exceeded",
                    "risk_score": device.risk_score,
                    "threshold": config.DEVICE_RISK_BLACKLIST_THRESHOLD,
                    "blacklisted_until": device.blacklisted_until.isoformat(),
                }),
            )
            db.session.add(audit)
            logger.warning(
                "auth", "device-risk",
                f"Device auto-blacklisted: device_id={device.id} "
                f"risk_score={device.risk_score}",
            )

        db.session.commit()
    except Exception as exc:
        logger.warning("auth", "device-risk", f"Failed to accumulate device risk: {exc}")


def _check_login_spike(username: str, ip: str):
    """Create an alert if failed login attempts exceed threshold within the window."""
    try:
        from src.utils.alert_writer import create_alert
        from src.models.enums import AlertSeverity

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=FAILED_LOGIN_WINDOW_SECONDS)
        count = AuditEvent.query.filter(
            AuditEvent.event_type == AuditEventType.USER_LOGIN_FAILED.value,
            AuditEvent.created_at >= cutoff,
        ).count()

        if count > FAILED_LOGIN_ALERT_THRESHOLD:
            # Avoid duplicate alerts: check if one was already raised recently
            from src.models.models import Alert
            existing = Alert.query.filter(
                Alert.alert_type == "FAILED_LOGIN_SPIKE",
                Alert.created_at >= cutoff,
            ).first()
            if not existing:
                create_alert(
                    alert_type="FAILED_LOGIN_SPIKE",
                    severity=AlertSeverity.HIGH.value,
                    title=f"Login failure spike detected: {count} failures in last hour",
                    description=f"Username: {username}, IP: {ip}, Count: {count}",
                )
    except Exception as exc:
        logger.warning("auth", "alert", f"Failed to check login spike: {exc}")


# ------------------------------------------------------------------
# POST /auth/register-guest
# ------------------------------------------------------------------
@auth_bp.route("/register-guest", methods=["POST"])
def register_guest():
    try:
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        display_name = data.get("display_name")

        if not username:
            return error_response("VALIDATION_ERROR", "username is required", status_code=400)
        if not password:
            return error_response("VALIDATION_ERROR", "password is required", status_code=400)

        # Check uniqueness
        if User.query.filter_by(username=username).first():
            return error_response("USERNAME_TAKEN", "Username is already taken", status_code=409)

        password_hashed = hash_password(password)

        user = User(
            username=username,
            password_hash=password_hashed,
            display_name=display_name,
            role=RoleType.GUEST.value,
        )
        db.session.add(user)
        db.session.flush()  # populate user.id

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.USER_REGISTERED.value,
            actor_id=user.id,
            actor_ip=request.remote_addr,
            target_type="User",
            target_id=user.id,
        )
        db.session.add(audit)
        db.session.commit()

        access_token = create_access_token(
            user_id=user.id,
            username=user.username,
            role=user.role,
        )
        refresh_token = create_refresh_token(user_id=user.id)

        # Store refresh token hash (encrypted at rest + deterministic lookup)
        _rt_hashed = hash_token(refresh_token)
        rt_record = RefreshToken(
            user_id=user.id,
            token_hash=_rt_hashed,
            token_lookup_hash=_rt_hashed,
            expires_at=datetime.now(timezone.utc) + timedelta(days=config.JWT_REFRESH_TOKEN_EXPIRES_DAYS),
        )
        db.session.add(rt_record)
        db.session.commit()

        logger.info("auth", "register-guest", f"Guest registered: user_id={user.id}")

        return success_response({
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role,
                "status": user.status,
                "is_active": user.is_active,
                "last_login_at": None,
                "created_at": user.created_at.isoformat(),
            },
            "access_token": access_token,
            "refresh_token": refresh_token,
        }, status_code=201)

    except Exception as exc:
        db.session.rollback()
        logger.error("auth", "register-guest", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ------------------------------------------------------------------
# POST /auth/login
# ------------------------------------------------------------------
@auth_bp.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        device_fingerprint = data.get("device_fingerprint")
        captcha_id = data.get("captcha_id")
        captcha_answer = data.get("captcha_answer")

        if not username or not password:
            return error_response("VALIDATION_ERROR", "username and password are required", status_code=400)

        # Check lockout
        is_locked, retry_after = check_lockout(username)
        if is_locked:
            return error_response("ACCOUNT_LOCKED", "Account is temporarily locked", details={"retry_after": retry_after}, status_code=423)

        # Check captcha requirement
        if needs_captcha(username):
            if not captcha_id or captcha_answer is None:
                challenge = create_captcha_challenge(username, request.remote_addr)
                return error_response(
                    "CAPTCHA_REQUIRED",
                    "Captcha verification required",
                    details=challenge,
                    status_code=403,
                )
            if not verify_captcha(captcha_id, str(captcha_answer)):
                return error_response("CAPTCHA_INVALID", "Invalid captcha answer", status_code=403)

        # Check device blacklist using deterministic lookup hash with cooldown
        if device_fingerprint:
            fp_lookup = compute_fingerprint_lookup_hash(device_fingerprint)
            blacklisted_device = Device.query.filter_by(
                fingerprint_lookup_hash=fp_lookup,
                status=DeviceStatus.BLACKLISTED.value,
            ).first()
            if blacklisted_device:
                now = datetime.now(timezone.utc)
                bl_until = blacklisted_device.blacklisted_until
                if bl_until and bl_until.tzinfo is None:
                    bl_until = bl_until.replace(tzinfo=timezone.utc)
                # If blacklisted_until is set and has passed, the cooldown expired
                if bl_until and now >= bl_until:
                    # Cooldown expired — reactivate the device
                    blacklisted_device.status = DeviceStatus.ACTIVE.value
                    blacklisted_device.blacklisted_until = None
                    db.session.commit()
                else:
                    # Still blacklisted — compute retry_after from blacklisted_until
                    if bl_until:
                        retry_seconds = int((bl_until - now).total_seconds())
                    else:
                        retry_seconds = config.DEVICE_BLACKLIST_RETRY_AFTER_HOURS * 3600
                    return error_response(
                        "DEVICE_BLACKLISTED",
                        "This device has been blacklisted",
                        details={"retry_after": retry_seconds},
                        status_code=403,
                    )

        # Look up user and verify credentials
        user = User.query.filter_by(username=username).first()
        if user is None or not verify_password(password, user.password_hash):
            record_failure(username)
            # Audit failed login
            audit = AuditEvent(
                event_type=AuditEventType.USER_LOGIN_FAILED.value,
                actor_id=user.id if user else None,
                actor_ip=request.remote_addr,
                target_type="User",
                target_id=user.id if user else None,
            )
            db.session.add(audit)
            db.session.commit()

            # Check for login failure spike and create alert
            _check_login_spike(username, request.remote_addr)

            # Accumulate device risk score on failed login
            if device_fingerprint:
                fp_lookup = compute_fingerprint_lookup_hash(device_fingerprint)
                _accumulate_device_risk(fp_lookup, request.remote_addr)

            logger.info("auth", "login", f"Login failed for username={username}")
            return error_response("INVALID_CREDENTIALS", "Invalid username or password", status_code=401)

        if not user.is_active:
            return error_response("ACCOUNT_DISABLED", "Account is disabled", status_code=403)

        # Success path
        reset_failures(username)

        # Record last login timestamp
        user.last_login_at = datetime.now(timezone.utc)

        # Determine org_id and effective role from first active membership
        org_id = None
        membership_role = None
        active_membership = Membership.query.filter_by(user_id=user.id, is_active=True).first()
        if active_membership:
            org_id = active_membership.organization_id
            membership_role = active_membership.role
        effective_role = _resolve_effective_role(user.role, membership_role)

        permission_codes = _get_user_permissions(user.id, org_id)

        access_token = create_access_token(
            user_id=user.id,
            username=user.username,
            role=effective_role,
            organization_id=org_id,
            permissions=permission_codes,
        )
        refresh_token = create_refresh_token(user_id=user.id)

        # Store refresh token hash (encrypted at rest + deterministic lookup)
        _rt_hashed = hash_token(refresh_token)
        rt_record = RefreshToken(
            user_id=user.id,
            token_hash=_rt_hashed,
            token_lookup_hash=_rt_hashed,
            expires_at=datetime.now(timezone.utc) + timedelta(days=config.JWT_REFRESH_TOKEN_EXPIRES_DAYS),
        )
        db.session.add(rt_record)

        # Audit successful login
        audit = AuditEvent(
            event_type=AuditEventType.USER_LOGIN.value,
            actor_id=user.id,
            actor_ip=request.remote_addr,
            target_type="User",
            target_id=user.id,
        )
        db.session.add(audit)
        db.session.commit()

        logger.info("auth", "login", f"User logged in: user_id={user.id}")

        return success_response({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": config.JWT_ACCESS_TOKEN_EXPIRES_MINUTES * 60,
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role,
                "status": user.status,
                "is_active": user.is_active,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
                "created_at": user.created_at.isoformat(),
            },
        })

    except Exception as exc:
        db.session.rollback()
        logger.error("auth", "login", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ------------------------------------------------------------------
# POST /auth/refresh
# ------------------------------------------------------------------
@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    try:
        data = request.get_json(silent=True) or {}
        raw_token = data.get("refresh_token")

        if not raw_token:
            return error_response("VALIDATION_ERROR", "refresh_token is required", status_code=400)

        payload = decode_token(raw_token)
        if payload is None:
            return error_response("INVALID_TOKEN", "Invalid or expired refresh token", status_code=401)

        if payload.get("type") != "refresh":
            return error_response("INVALID_TOKEN", "Token is not a refresh token", status_code=401)

        token_hashed = hash_token(raw_token)
        rt_record = RefreshToken.query.filter_by(token_lookup_hash=token_hashed).first()

        if rt_record is None:
            return error_response("INVALID_TOKEN", "Refresh token not found", status_code=401)
        if rt_record.is_revoked:
            return error_response("TOKEN_REVOKED", "Refresh token has been revoked", status_code=401)
        expires_at = rt_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return error_response("TOKEN_EXPIRED", "Refresh token has expired", status_code=401)

        # Revoke old refresh token (rotation)
        rt_record.is_revoked = True

        user_id = payload["sub"]
        user = User.query.get(user_id)
        if user is None or not user.is_active:
            db.session.commit()
            return error_response("INVALID_TOKEN", "User not found or inactive", status_code=401)

        # Determine org_id and effective role from membership
        org_id = None
        membership_role = None
        active_membership = Membership.query.filter_by(user_id=user.id, is_active=True).first()
        if active_membership:
            org_id = active_membership.organization_id
            membership_role = active_membership.role
        effective_role = _resolve_effective_role(user.role, membership_role)

        permission_codes = _get_user_permissions(user.id, org_id)

        new_access = create_access_token(
            user_id=user.id,
            username=user.username,
            role=effective_role,
            organization_id=org_id,
            permissions=permission_codes,
        )
        new_refresh = create_refresh_token(user_id=user.id)

        _new_rt_hashed = hash_token(new_refresh)
        new_rt_record = RefreshToken(
            user_id=user.id,
            token_hash=_new_rt_hashed,
            token_lookup_hash=_new_rt_hashed,
            expires_at=datetime.now(timezone.utc) + timedelta(days=config.JWT_REFRESH_TOKEN_EXPIRES_DAYS),
        )
        db.session.add(new_rt_record)

        # Audit
        audit = AuditEvent(
            event_type=AuditEventType.TOKEN_REFRESHED.value,
            actor_id=user.id,
            actor_ip=request.remote_addr,
            target_type="RefreshToken",
            target_id=rt_record.id,
        )
        db.session.add(audit)
        db.session.commit()

        logger.info("auth", "refresh", f"Token refreshed for user_id={user.id}")

        return success_response({
            "access_token": new_access,
            "refresh_token": new_refresh,
            "expires_in": config.JWT_ACCESS_TOKEN_EXPIRES_MINUTES * 60,
        })

    except Exception as exc:
        db.session.rollback()
        logger.error("auth", "refresh", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ------------------------------------------------------------------
# POST /auth/logout
# ------------------------------------------------------------------
@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    try:
        current = g.current_user
        data = request.get_json(silent=True) or {}
        raw_refresh = data.get("refresh_token")

        # Decode the current access token to get expiry
        auth_header = request.headers.get("Authorization", "")
        access_token_str = auth_header[7:]  # Strip "Bearer "
        access_payload = decode_token(access_token_str)

        # Denylist the access token JTI
        if current.jti and access_payload:
            exp_dt = datetime.fromtimestamp(access_payload["exp"], tz=timezone.utc)
            denylist_entry = AccessTokenDenylist(
                jti=current.jti,
                expires_at=exp_dt,
            )
            db.session.add(denylist_entry)

        # Revoke the provided refresh token
        if raw_refresh:
            rt_hash = hash_token(raw_refresh)
            rt_record = RefreshToken.query.filter_by(token_lookup_hash=rt_hash, user_id=current.user_id).first()
            if rt_record:
                rt_record.is_revoked = True

        # Audit
        audit = AuditEvent(
            event_type=AuditEventType.USER_LOGOUT.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="User",
            target_id=current.user_id,
        )
        db.session.add(audit)
        db.session.commit()

        logger.info("auth", "logout", f"User logged out: user_id={current.user_id}")
        return "", 204

    except Exception as exc:
        db.session.rollback()
        logger.error("auth", "logout", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ------------------------------------------------------------------
# POST /auth/logout-all
# ------------------------------------------------------------------
@auth_bp.route("/logout-all", methods=["POST"])
@require_auth
def logout_all():
    try:
        current = g.current_user

        # Denylist the current access token
        auth_header = request.headers.get("Authorization", "")
        access_token_str = auth_header[7:]
        access_payload = decode_token(access_token_str)

        if current.jti and access_payload:
            exp_dt = datetime.fromtimestamp(access_payload["exp"], tz=timezone.utc)
            denylist_entry = AccessTokenDenylist(
                jti=current.jti,
                expires_at=exp_dt,
            )
            db.session.add(denylist_entry)

        # Revoke ALL refresh tokens for this user
        RefreshToken.query.filter_by(user_id=current.user_id, is_revoked=False).update(
            {"is_revoked": True}
        )

        # Audit
        audit = AuditEvent(
            event_type=AuditEventType.USER_LOGOUT_ALL.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="User",
            target_id=current.user_id,
        )
        db.session.add(audit)
        db.session.commit()

        logger.info("auth", "logout-all", f"All sessions revoked: user_id={current.user_id}")
        return "", 204

    except Exception as exc:
        db.session.rollback()
        logger.error("auth", "logout-all", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ------------------------------------------------------------------
# POST /auth/device/bind
# ------------------------------------------------------------------
@auth_bp.route("/device/bind", methods=["POST"])
@require_auth
def device_bind():
    try:
        current = g.current_user
        data = request.get_json(silent=True) or {}
        fingerprint = data.get("fingerprint")
        device_name = data.get("device_name")

        if not fingerprint:
            return error_response("VALIDATION_ERROR", "fingerprint is required", status_code=400)

        fp_encrypted = encrypt_field(fingerprint, config.ENCRYPTION_MASTER_KEY, "device_fingerprint")
        fp_lookup = compute_fingerprint_lookup_hash(fingerprint)

        device = Device(
            user_id=current.user_id,
            fingerprint_hash=fp_encrypted,
            fingerprint_lookup_hash=fp_lookup,
            device_name=device_name,
            risk_score=0.0,
            status=DeviceStatus.ACTIVE.value,
        )
        db.session.add(device)
        db.session.flush()

        # Audit
        audit = AuditEvent(
            event_type=AuditEventType.DEVICE_BOUND.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="Device",
            target_id=device.id,
        )
        db.session.add(audit)
        db.session.commit()

        logger.info("auth", "device-bind", f"Device bound: device_id={device.id} user_id={current.user_id}")

        return success_response({
            "id": device.id,
            "user_id": device.user_id,
            "device_name": device.device_name,
            "risk_score": device.risk_score,
            "status": device.status,
            "created_at": device.created_at.isoformat(),
        }, status_code=201)

    except Exception as exc:
        db.session.rollback()
        logger.error("auth", "device-bind", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ------------------------------------------------------------------
# POST /auth/device/unbind
# ------------------------------------------------------------------
@auth_bp.route("/device/unbind", methods=["POST"])
@require_auth
def device_unbind():
    try:
        current = g.current_user
        data = request.get_json(silent=True) or {}
        device_id = data.get("device_id")

        if not device_id:
            return error_response("VALIDATION_ERROR", "device_id is required", status_code=400)

        device = Device.query.get(device_id)
        if device is None:
            return error_response("NOT_FOUND", "Device not found", status_code=404)

        if device.user_id != current.user_id:
            return error_response("FORBIDDEN", "You do not own this device", status_code=403)

        device_id_for_audit = device.id
        db.session.delete(device)

        # Audit
        audit = AuditEvent(
            event_type=AuditEventType.DEVICE_UNBOUND.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="Device",
            target_id=device_id_for_audit,
        )
        db.session.add(audit)
        db.session.commit()

        logger.info("auth", "device-unbind", f"Device unbound: device_id={device_id_for_audit} user_id={current.user_id}")
        return "", 204

    except Exception as exc:
        db.session.rollback()
        logger.error("auth", "device-unbind", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ------------------------------------------------------------------
# GET /auth/me
# ------------------------------------------------------------------
@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():
    try:
        current = g.current_user
        user = User.query.get(current.user_id)

        if user is None:
            return error_response("NOT_FOUND", "User not found", status_code=404)

        # Build memberships list
        memberships = []
        for m in user.memberships.filter_by(is_active=True).all():
            org = Organization.query.get(m.organization_id)
            memberships.append({
                "id": m.id,
                "organization_id": m.organization_id,
                "organization_name": org.name if org else None,
                "role": m.role,
                "is_active": m.is_active,
                "created_at": m.created_at.isoformat(),
            })

        # Active device count
        active_device_count = user.devices.filter_by(status=DeviceStatus.ACTIVE.value).count()

        logger.info("auth", "me", f"Profile retrieved: user_id={user.id}")

        return success_response({
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "is_active": user.is_active,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat(),
            "memberships": memberships,
            "active_device_count": active_device_count,
        })

    except Exception as exc:
        db.session.rollback()
        logger.error("auth", "me", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)
