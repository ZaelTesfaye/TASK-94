"""
Scheduler module - hold release, backup, alert threshold, cleanup jobs.
Uses APScheduler for cron-like scheduling within the Flask app context.
"""

import os
import shutil
from datetime import datetime, timezone, timedelta

from src.config import config
from src.logging import logger


def init_scheduler(app):
    """Initialize the APScheduler with all background jobs."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("scheduler", "init", "APScheduler not installed, scheduler disabled")
        return

    scheduler = BackgroundScheduler()

    # --- Job 1: Hold auto-release (runs every minute) ---
    def release_expired_holds():
        with app.app_context():
            _release_expired_holds()

    scheduler.add_job(
        release_expired_holds,
        "interval",
        minutes=1,
        id="release_expired_holds",
        replace_existing=True,
    )

    # --- Job 2: Nonce cleanup (runs every 10 minutes) ---
    def cleanup_nonces():
        with app.app_context():
            _cleanup_nonces()

    scheduler.add_job(
        cleanup_nonces,
        "interval",
        minutes=10,
        id="cleanup_nonces",
        replace_existing=True,
    )

    # --- Job 3: Denylist cleanup (runs every hour) ---
    def cleanup_denylist():
        with app.app_context():
            _cleanup_denylist()

    scheduler.add_job(
        cleanup_denylist,
        "interval",
        hours=1,
        id="cleanup_denylist",
        replace_existing=True,
    )

    # --- Job 4: Backup (daily at configured time) ---
    def run_backup():
        with app.app_context():
            _run_backup()

    cron_parts = config.BACKUP_SCHEDULE_CRON.split()
    if len(cron_parts) == 5:
        scheduler.add_job(
            run_backup,
            "cron",
            minute=cron_parts[0],
            hour=cron_parts[1],
            day=cron_parts[2] if cron_parts[2] != "*" else None,
            month=cron_parts[3] if cron_parts[3] != "*" else None,
            day_of_week=cron_parts[4] if cron_parts[4] != "*" else None,
            id="run_backup",
            replace_existing=True,
        )

    # --- Job 5: Backup retention purge (daily at 3 AM) ---
    def purge_old_backups():
        with app.app_context():
            _purge_old_backups()

    scheduler.add_job(
        purge_old_backups,
        "cron",
        hour=3,
        minute=0,
        id="purge_old_backups",
        replace_existing=True,
    )

    # --- Job 6: Idempotency record cleanup (every 6 hours) ---
    def cleanup_idempotency():
        with app.app_context():
            _cleanup_idempotency()

    scheduler.add_job(
        cleanup_idempotency,
        "interval",
        hours=6,
        id="cleanup_idempotency",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("scheduler", "init", "Scheduler started with all jobs registered")


def _release_expired_holds():
    """Release reservations whose hold has expired."""
    from src.models.base import db
    from src.models.models import Reservation, AuditEvent, Alert
    from src.models.enums import ReservationStatus, AuditEventType, AlertSeverity, AlertStatus

    now = datetime.now(timezone.utc)
    expired = Reservation.query.filter(
        Reservation.status == ReservationStatus.HELD.value,
        Reservation.hold_expires_at <= now,
    ).all()

    count = 0
    for reservation in expired:
        reservation.status = ReservationStatus.RELEASED.value
        reservation.version += 1
        reservation.updated_at = now

        audit = AuditEvent(
            event_type=AuditEventType.RESERVATION_RELEASED.value,
            actor_id="system",
            target_type="reservation",
            target_id=reservation.id,
            organization_id=reservation.organization_id,
            metadata_json='{"reason": "hold_expired"}',
        )
        db.session.add(audit)
        count += 1

    if count > 0:
        db.session.commit()
        logger.info("scheduler", "hold_release", f"Released {count} expired holds")


def _cleanup_nonces():
    """Remove expired nonces from the store."""
    from src.models.base import db
    from src.models.models import NonceStore

    now = datetime.now(timezone.utc)
    deleted = NonceStore.query.filter(NonceStore.expires_at <= now).delete()
    db.session.commit()
    if deleted:
        logger.info("scheduler", "nonce_cleanup", f"Cleaned up {deleted} expired nonces")


def _cleanup_denylist():
    """Remove expired access token denylist entries."""
    from src.models.base import db
    from src.models.models import AccessTokenDenylist

    now = datetime.now(timezone.utc)
    deleted = AccessTokenDenylist.query.filter(AccessTokenDenylist.expires_at <= now).delete()
    db.session.commit()
    if deleted:
        logger.info("scheduler", "denylist_cleanup", f"Cleaned up {deleted} expired denylist entries")


def _cleanup_idempotency():
    """Remove expired idempotency records."""
    from src.models.base import db
    from src.models.models import IdempotencyRecord

    now = datetime.now(timezone.utc)
    deleted = IdempotencyRecord.query.filter(IdempotencyRecord.expires_at <= now).delete()
    db.session.commit()
    if deleted:
        logger.info("scheduler", "idempotency_cleanup", f"Cleaned up {deleted} expired idempotency records")


def _run_backup():
    """Perform SQLite database backup to configured backup directory."""
    from src.models.base import db
    from src.models.models import AuditEvent, Alert
    from src.models.enums import AuditEventType, AlertSeverity, AlertStatus

    backup_dir = config.BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_filename)

    try:
        db_url = config.DATABASE_URL
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
            source_path = db_path
        else:
            logger.warning("scheduler", "backup", "Non-SQLite database, backup skipped")
            return

        if os.path.exists(source_path):
            shutil.copy2(source_path, backup_path)

            audit = AuditEvent(
                event_type=AuditEventType.BACKUP_COMPLETED.value,
                actor_id="system",
                metadata_json=f'{{"backup_path": "{backup_path}", "size_bytes": {os.path.getsize(backup_path)}}}',
            )
            db.session.add(audit)
            db.session.commit()

            logger.info("scheduler", "backup", f"Backup completed: {backup_path}")
        else:
            raise FileNotFoundError(f"Database file not found: {source_path}")

    except Exception as e:
        logger.error("scheduler", "backup", f"Backup failed: {e}")

        try:
            alert = Alert(
                alert_type="BACKUP_FAILURE",
                severity=AlertSeverity.CRITICAL.value,
                status=AlertStatus.OPEN.value,
                title="Database backup failed",
                description=str(e),
            )
            db.session.add(alert)

            audit = AuditEvent(
                event_type=AuditEventType.BACKUP_FAILED.value,
                actor_id="system",
                metadata_json=f'{{"error": "{str(e)}"}}',
            )
            db.session.add(audit)
            db.session.commit()
        except Exception:
            logger.error("scheduler", "backup", "Failed to create backup failure alert")


def _purge_old_backups():
    """Remove backups older than retention period."""
    backup_dir = config.BACKUP_DIR
    if not os.path.exists(backup_dir):
        return

    retention_days = config.BACKUP_RETENTION_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    purged = 0

    for filename in os.listdir(backup_dir):
        filepath = os.path.join(backup_dir, filename)
        if os.path.isfile(filepath):
            file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath), tz=timezone.utc)
            if file_mtime < cutoff:
                os.remove(filepath)
                purged += 1

    if purged:
        logger.info("scheduler", "backup_purge", f"Purged {purged} old backup files")
