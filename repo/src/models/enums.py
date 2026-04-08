"""All application enums - single source of truth."""
import enum


class RoleType(str, enum.Enum):
    GUEST = "guest"
    MEMBER = "member"
    ORG_ADMIN = "org_admin"
    PLATFORM_ADMIN = "platform_admin"


ROLE_HIERARCHY = {
    RoleType.GUEST: 0,
    RoleType.MEMBER: 1,
    RoleType.ORG_ADMIN: 2,
    RoleType.PLATFORM_ADMIN: 3,
}


class ReservationStatus(str, enum.Enum):
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    RELEASED = "RELEASED"
    RESCHEDULED = "RESCHEDULED"


# Valid state transitions for reservations
RESERVATION_TRANSITIONS = {
    ReservationStatus.HELD: {ReservationStatus.CONFIRMED, ReservationStatus.CANCELLED, ReservationStatus.RELEASED},
    ReservationStatus.CONFIRMED: {ReservationStatus.CANCELLED, ReservationStatus.RESCHEDULED},
    ReservationStatus.CANCELLED: set(),
    ReservationStatus.RELEASED: set(),
    ReservationStatus.RESCHEDULED: set(),
}


class ContentQualityState(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DUPLICATE_DEMOTED = "DUPLICATE_DEMOTED"
    RATING_DEMOTED = "RATING_DEMOTED"
    REPORTED = "REPORTED"
    SUPPRESSED = "SUPPRESSED"
    REINSTATED = "REINSTATED"


class ModerationAction(str, enum.Enum):
    REPORT = "REPORT"
    REVIEW = "REVIEW"
    SUPPRESS = "SUPPRESS"
    REINSTATE = "REINSTATE"
    APPEAL = "APPEAL"
    APPEAL_APPROVED = "APPEAL_APPROVED"
    APPEAL_DENIED = "APPEAL_DENIED"


class LearningEventType(str, enum.Enum):
    PAGE_VIEW = "PAGE_VIEW"
    VIDEO_WATCH = "VIDEO_WATCH"
    QUIZ_ATTEMPT = "QUIZ_ATTEMPT"
    ASSIGNMENT_SUBMIT = "ASSIGNMENT_SUBMIT"
    DISCUSSION_POST = "DISCUSSION_POST"
    RESOURCE_DOWNLOAD = "RESOURCE_DOWNLOAD"
    MODULE_COMPLETE = "MODULE_COMPLETE"
    COURSE_COMPLETE = "COURSE_COMPLETE"


class DifficultyBucket(str, enum.Enum):
    EASY = "EASY"           # correct_rate >= 0.8
    MEDIUM = "MEDIUM"       # 0.5 <= correct_rate < 0.8
    HARD = "HARD"           # 0.2 <= correct_rate < 0.5
    VERY_HARD = "VERY_HARD" # correct_rate < 0.2


DIFFICULTY_THRESHOLDS = [
    (0.8, DifficultyBucket.EASY),
    (0.5, DifficultyBucket.MEDIUM),
    (0.2, DifficultyBucket.HARD),
    (0.0, DifficultyBucket.VERY_HARD),
]


class ExportStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AlertSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class AuditEventType(str, enum.Enum):
    # Auth
    USER_REGISTERED = "USER_REGISTERED"
    USER_LOGIN = "USER_LOGIN"
    USER_LOGIN_FAILED = "USER_LOGIN_FAILED"
    USER_LOGOUT = "USER_LOGOUT"
    USER_LOGOUT_ALL = "USER_LOGOUT_ALL"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    # Device
    DEVICE_BOUND = "DEVICE_BOUND"
    DEVICE_UNBOUND = "DEVICE_UNBOUND"
    DEVICE_BLACKLISTED = "DEVICE_BLACKLISTED"
    # Permissions
    PERMISSION_CREATED = "PERMISSION_CREATED"
    PERMISSION_ASSIGNED = "PERMISSION_ASSIGNED"
    PERMISSION_REVOKED = "PERMISSION_REVOKED"
    ROLE_CHANGED = "ROLE_CHANGED"
    # Invitations
    INVITATION_CREATED = "INVITATION_CREATED"
    INVITATION_REDEEMED = "INVITATION_REDEEMED"
    INVITATION_REVOKED = "INVITATION_REVOKED"
    # Booking
    RESERVATION_HELD = "RESERVATION_HELD"
    RESERVATION_CONFIRMED = "RESERVATION_CONFIRMED"
    RESERVATION_CANCELLED = "RESERVATION_CANCELLED"
    RESERVATION_RELEASED = "RESERVATION_RELEASED"
    RESERVATION_RESCHEDULED = "RESERVATION_RESCHEDULED"
    # Content
    CONTENT_CREATED = "CONTENT_CREATED"
    CONTENT_DEMOTED = "CONTENT_DEMOTED"
    CONTENT_REPORTED = "CONTENT_REPORTED"
    # Moderation
    MODERATION_DECISION = "MODERATION_DECISION"
    MODERATION_APPEAL = "MODERATION_APPEAL"
    MODERATION_APPEAL_DECISION = "MODERATION_APPEAL_DECISION"
    # Export
    EXPORT_CREATED = "EXPORT_CREATED"
    EXPORT_DOWNLOADED = "EXPORT_DOWNLOADED"
    # Backup
    BACKUP_COMPLETED = "BACKUP_COMPLETED"
    BACKUP_FAILED = "BACKUP_FAILED"
    # Admin
    ADMIN_ACTION = "ADMIN_ACTION"


class InvitationStatus(str, enum.Enum):
    PENDING = "PENDING"
    REDEEMED = "REDEEMED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class DeviceStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    BLACKLISTED = "BLACKLISTED"


class ContentType(str, enum.Enum):
    ARTICLE = "ARTICLE"
    VIDEO = "VIDEO"
    QUIZ = "QUIZ"
    COURSE = "COURSE"
    MODULE = "MODULE"
    ASSIGNMENT = "ASSIGNMENT"
