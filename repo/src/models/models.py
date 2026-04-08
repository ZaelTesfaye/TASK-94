"""
All SQLAlchemy models implementing the canonical data model from plan sections 5.1-5.3.
Core tables + required support tables with all critical constraints.
"""

import uuid
from datetime import datetime, timezone

from src.models.base import db
from src.models.enums import (
    RoleType, ReservationStatus, ContentQualityState, ModerationAction,
    LearningEventType, ExportStatus, AlertSeverity, AlertStatus,
    AuditEventType, InvitationStatus, DeviceStatus, ContentType,
)


def generate_uuid():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────
# 5.1 Core Tables
# ──────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    username = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.Text, nullable=False)
    display_name = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(50), nullable=False, default=RoleType.GUEST.value)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    memberships = db.relationship("Membership", back_populates="user", lazy="dynamic")
    devices = db.relationship("Device", back_populates="user", lazy="dynamic")
    reservations = db.relationship("Reservation", back_populates="user", lazy="dynamic")


class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    memberships = db.relationship("Membership", back_populates="organization", lazy="dynamic")
    resources = db.relationship("Resource", back_populates="organization", lazy="dynamic")


class Membership(db.Model):
    __tablename__ = "memberships"
    __table_args__ = (
        db.UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
    )

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    role = db.Column(db.String(50), nullable=False, default=RoleType.MEMBER.value)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="memberships")
    organization = db.relationship("Organization", back_populates="memberships")


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    code = db.Column(db.String(255), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    data_scope = db.Column(db.String(50), nullable=True)  # organization/site/resource/project
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class UserPermission(db.Model):
    """Junction table for user-permission assignments."""
    __tablename__ = "user_permissions"
    __table_args__ = (
        db.UniqueConstraint("user_id", "permission_id", "organization_id", name="uq_user_perm_org"),
    )

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    permission_id = db.Column(db.String(36), db.ForeignKey("permissions.id"), nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=True, index=True)
    granted_by = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    user = db.relationship("User", foreign_keys=[user_id])
    permission = db.relationship("Permission")
    organization = db.relationship("Organization")


class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    fingerprint_hash = db.Column(db.String(512), nullable=False)
    device_name = db.Column(db.String(255), nullable=True)
    risk_score = db.Column(db.Float, default=0.0, nullable=False)
    status = db.Column(db.String(50), nullable=False, default=DeviceStatus.ACTIVE.value)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="devices")


class Resource(db.Model):
    __tablename__ = "resources"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    resource_type = db.Column(db.String(100), nullable=True)
    capacity = db.Column(db.Integer, default=1, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    organization = db.relationship("Organization", back_populates="resources")
    slot_templates = db.relationship("SlotTemplate", back_populates="resource", lazy="dynamic")


class SlotTemplate(db.Model):
    __tablename__ = "slot_templates"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    resource_id = db.Column(db.String(36), db.ForeignKey("resources.id"), nullable=False, index=True)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    quota = db.Column(db.Integer, default=1, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    resource = db.relationship("Resource", back_populates="slot_templates")


class Reservation(db.Model):
    __tablename__ = "reservations"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    resource_id = db.Column(db.String(36), db.ForeignKey("resources.id"), nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    status = db.Column(db.String(50), nullable=False, default=ReservationStatus.HELD.value)
    start_time = db.Column(db.DateTime(timezone=True), nullable=False)
    end_time = db.Column(db.DateTime(timezone=True), nullable=False)
    hold_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    idempotency_key = db.Column(db.String(255), nullable=True, index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = db.relationship("User", back_populates="reservations")
    resource = db.relationship("Resource")
    organization = db.relationship("Organization")


class ContentItem(db.Model):
    __tablename__ = "content_items"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    creator_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(500), nullable=False)
    body = db.Column(db.Text, nullable=True)
    content_type = db.Column(db.String(50), nullable=False, default=ContentType.ARTICLE.value)
    quality_state = db.Column(db.String(50), nullable=False, default=ContentQualityState.ACTIVE.value)
    fingerprint_hash = db.Column(db.String(64), nullable=True, index=True)
    avg_rating = db.Column(db.Float, default=0.0, nullable=False)
    rating_count = db.Column(db.Integer, default=0, nullable=False)
    view_count = db.Column(db.Integer, default=0, nullable=False)
    download_count = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    creator = db.relationship("User")
    organization = db.relationship("Organization")


class ModerationCase(db.Model):
    __tablename__ = "moderation_cases"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    content_id = db.Column(db.String(36), db.ForeignKey("content_items.id"), nullable=False, index=True)
    reporter_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    reviewer_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(50), nullable=False, default=ModerationAction.REPORT.value)
    reason = db.Column(db.Text, nullable=True)
    decision_notes = db.Column(db.Text, nullable=True)
    appeal_notes = db.Column(db.Text, nullable=True)
    appeal_decision_notes = db.Column(db.Text, nullable=True)
    appealed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    decided_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    content = db.relationship("ContentItem")
    reporter = db.relationship("User", foreign_keys=[reporter_id])
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])


class LearningEvent(db.Model):
    __tablename__ = "learning_events"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    content_id = db.Column(db.String(36), db.ForeignKey("content_items.id"), nullable=True)
    event_type = db.Column(db.String(50), nullable=False)
    metadata_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    content_id = db.Column(db.String(36), db.ForeignKey("content_items.id"), nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    question_text = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.Text, nullable=False)
    options_json = db.Column(db.Text, nullable=True)
    difficulty_bucket = db.Column(db.String(50), nullable=True)
    total_attempts = db.Column(db.Integer, default=0, nullable=False)
    correct_attempts = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    content = db.relationship("ContentItem")


class Attempt(db.Model):
    __tablename__ = "attempts"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    question_id = db.Column(db.String(36), db.ForeignKey("questions.id"), nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    answer_given = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    user = db.relationship("User")
    question = db.relationship("Question")


class Export(db.Model):
    __tablename__ = "exports"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    requester_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    export_type = db.Column(db.String(100), nullable=False)
    parameters_json = db.Column(db.Text, nullable=True)
    parameters_hash = db.Column(db.String(64), nullable=True, index=True)
    status = db.Column(db.String(50), nullable=False, default=ExportStatus.PENDING.value)
    file_path = db.Column(db.String(500), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    requester = db.relationship("User")
    organization = db.relationship("Organization")


# ──────────────────────────────────────────
# 5.2 Required Support Tables
# ──────────────────────────────────────────

class RefreshToken(db.Model):
    __tablename__ = "refresh_tokens"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(512), unique=True, nullable=False, index=True)
    device_id = db.Column(db.String(36), db.ForeignKey("devices.id"), nullable=True)
    is_revoked = db.Column(db.Boolean, default=False, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    user = db.relationship("User")


class AccessTokenDenylist(db.Model):
    __tablename__ = "access_token_denylist"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    jti = db.Column(db.String(255), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class InvitationCode(db.Model):
    __tablename__ = "invitation_codes"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    code = db.Column(db.String(255), unique=True, nullable=False, index=True)
    issuer_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False)
    target_role = db.Column(db.String(50), nullable=False, default=RoleType.MEMBER.value)
    status = db.Column(db.String(50), nullable=False, default=InvitationStatus.PENDING.value)
    redeemed_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    redeemed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    issuer = db.relationship("User", foreign_keys=[issuer_id])
    organization = db.relationship("Organization")
    redeemed_by = db.relationship("User", foreign_keys=[redeemed_by_id])


class IdempotencyRecord(db.Model):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        db.UniqueConstraint("user_id", "endpoint", "key_hash", name="uq_idempotency"),
    )

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    endpoint = db.Column(db.String(255), nullable=False)
    key_hash = db.Column(db.String(64), nullable=False, index=True)
    response_code = db.Column(db.Integer, nullable=False)
    response_body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)


class NonceStore(db.Model):
    __tablename__ = "nonce_store"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    nonce = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)


class RateLimitBucket(db.Model):
    __tablename__ = "rate_limit_buckets"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    bucket_key = db.Column(db.String(255), nullable=False, index=True)
    tokens = db.Column(db.Integer, nullable=False)
    last_refill_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class LoginChallenge(db.Model):
    __tablename__ = "login_challenges"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    ip_address = db.Column(db.String(45), nullable=False)
    challenge_type = db.Column(db.String(50), nullable=False, default="captcha")
    challenge_data = db.Column(db.Text, nullable=False)
    expected_answer = db.Column(db.String(255), nullable=False)
    is_solved = db.Column(db.Boolean, default=False, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class LoginFailureCounter(db.Model):
    __tablename__ = "login_failure_counters"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    identifier = db.Column(db.String(255), unique=True, nullable=False, index=True)
    failure_count = db.Column(db.Integer, default=0, nullable=False)
    first_failure_at = db.Column(db.DateTime(timezone=True), nullable=True)
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class AuditEvent(db.Model):
    __tablename__ = "audit_events"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    event_type = db.Column(db.String(100), nullable=False, index=True)
    actor_id = db.Column(db.String(36), nullable=True, index=True)
    actor_ip = db.Column(db.String(45), nullable=True)
    target_type = db.Column(db.String(100), nullable=True)
    target_id = db.Column(db.String(36), nullable=True)
    organization_id = db.Column(db.String(36), nullable=True, index=True)
    before_state = db.Column(db.Text, nullable=True)
    after_state = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    alert_type = db.Column(db.String(100), nullable=False, index=True)
    severity = db.Column(db.String(50), nullable=False, default=AlertSeverity.MEDIUM.value)
    status = db.Column(db.String(50), nullable=False, default=AlertStatus.OPEN.value)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=True)
    organization_id = db.Column(db.String(36), nullable=True, index=True)
    acknowledged_by = db.Column(db.String(36), nullable=True)
    acknowledged_at = db.Column(db.DateTime(timezone=True), nullable=True)
    resolved_by = db.Column(db.String(36), nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class UserCohort(db.Model):
    __tablename__ = "user_cohorts"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    cohort_tag = db.Column(db.String(100), nullable=False, index=True)
    organization_id = db.Column(db.String(36), db.ForeignKey("organizations.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "cohort_tag", "organization_id", name="uq_user_cohort"),
    )


class ContentRating(db.Model):
    __tablename__ = "content_ratings"
    __table_args__ = (
        db.UniqueConstraint("user_id", "content_id", name="uq_user_content_rating"),
    )

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    content_id = db.Column(db.String(36), db.ForeignKey("content_items.id"), nullable=False, index=True)
    score = db.Column(db.Integer, nullable=False)  # 1-5
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ContentComment(db.Model):
    __tablename__ = "content_comments"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    content_id = db.Column(db.String(36), db.ForeignKey("content_items.id"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    is_visible = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class ContentFavorite(db.Model):
    __tablename__ = "content_favorites"
    __table_args__ = (
        db.UniqueConstraint("user_id", "content_id", name="uq_user_content_favorite"),
    )

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    content_id = db.Column(db.String(36), db.ForeignKey("content_items.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class ContentDownload(db.Model):
    __tablename__ = "content_downloads"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    content_id = db.Column(db.String(36), db.ForeignKey("content_items.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
