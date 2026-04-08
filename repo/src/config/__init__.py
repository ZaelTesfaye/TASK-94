"""
Clean Config Module - Single source of truth for all configuration.
Application logic must never access os.getenv directly.
All environment variables flow through this module.
"""

import os


class _Config:
    """Centralized configuration with type safety and defaults."""

    # --- Application ---
    APP_NAME: str = "Learning & Resource Booking Governance API"
    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    TESTING: bool = False

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 5000

    # --- TLS Toggle (per guide Phase 1) ---
    ENABLE_TLS: bool = False
    TLS_CERT_PATH: str = "/app/certs/cert.pem"
    TLS_KEY_PATH: str = "/app/certs/key.pem"

    # --- Database ---
    DATABASE_URL: str = "sqlite:///app.db"
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # --- JWT ---
    JWT_SECRET_KEY: str = "jwt-change-me-in-production"
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRES_DAYS: int = 14
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "learning-booking-api"

    # --- Encryption ---
    ENCRYPTION_MASTER_KEY: str = "master-key-change-me-in-production"

    # --- Request Signing ---
    REQUEST_SIGNING_SECRET: str = "signing-secret-change-me"
    REQUEST_SIGNING_SKEW_SECONDS: int = 300  # +/- 5 minutes
    NONCE_RETENTION_SECONDS: int = 600  # 10 minutes

    # --- Rate Limiting ---
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 20

    # --- Login Security ---
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    CAPTCHA_THRESHOLD: int = 3

    # --- Booking ---
    HOLD_EXPIRY_MINUTES: int = 10
    BOOKING_BUFFER_MINUTES: int = 5
    MAX_ACTIVE_HOLDS_PER_USER: int = 3
    DEFAULT_SLOT_QUOTA: int = 1
    IDEMPOTENCY_WINDOW_HOURS: int = 24

    # --- Content ---
    RATING_DEMOTION_MIN_COUNT: int = 20
    RATING_DEMOTION_THRESHOLD: float = 2.0
    APPEAL_WINDOW_DAYS: int = 7
    APPEAL_MIN_NOTES_LENGTH: int = 50

    # --- Invitation ---
    INVITATION_EXPIRY_HOURS: int = 72

    # --- Device Risk ---
    DEVICE_RISK_BLACKLIST_THRESHOLD: float = 0.9
    DEVICE_BLACKLIST_RETRY_AFTER_HOURS: int = 24

    # --- Export ---
    EXPORT_DIR: str = "/app/exports"
    EXPORT_DEDUPE_WINDOW_HOURS: int = 1

    # --- Backup ---
    BACKUP_DIR: str = "/app/backups"
    BACKUP_RETENTION_DAYS: int = 30
    BACKUP_SCHEDULE_CRON: str = "0 2 * * *"  # 2 AM daily

    # --- Logging ---
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "structured"

    # --- Pagination ---
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # --- Admin/Debug ---
    ENABLE_DEBUG_ENDPOINTS: bool = False

    # --- Timezone ---
    TIMEZONE: str = "UTC"

    def __init__(self):
        """Load all configuration from environment variables with type-safe defaults."""
        for attr_name in dir(self):
            if attr_name.startswith("_") or attr_name != attr_name.upper():
                continue
            default = getattr(self, attr_name)
            env_val = os.environ.get(attr_name)
            if env_val is not None:
                if isinstance(default, bool):
                    setattr(self, attr_name, env_val.lower() in ("true", "1", "yes"))
                elif isinstance(default, int):
                    setattr(self, attr_name, int(env_val))
                elif isinstance(default, float):
                    setattr(self, attr_name, float(env_val))
                else:
                    setattr(self, attr_name, env_val)

    def as_dict(self, redacted: bool = False) -> dict:
        """Return config as dict, optionally with secrets redacted."""
        sensitive_keys = {
            "SECRET_KEY", "JWT_SECRET_KEY", "ENCRYPTION_MASTER_KEY",
            "REQUEST_SIGNING_SECRET", "DATABASE_URL"
        }
        result = {}
        for attr_name in sorted(dir(self)):
            if attr_name.startswith("_") or attr_name != attr_name.upper():
                continue
            val = getattr(self, attr_name)
            if redacted and attr_name in sensitive_keys:
                result[attr_name] = "***REDACTED***"
            else:
                result[attr_name] = val
        return result


config = _Config()
