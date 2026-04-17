"""Unit tests for scheduler job functions."""

import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from src.app import create_app
from src.models.base import db as _db


@pytest.fixture(scope="module")
def app():
    app = create_app(testing=True)
    yield app


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        _db.create_all()
        from src.models.models import User
        from src.models.enums import RoleType
        from src.security.passwords import hash_password

        if User.query.first() is None:
            admin = User(
                username="admin",
                password_hash=hash_password("admin"),
                display_name="Platform Administrator",
                role=RoleType.PLATFORM_ADMIN.value,
                is_active=True,
            )
            _db.session.add(admin)
            _db.session.commit()
        yield _db
        _db.session.rollback()
        _db.drop_all()


class TestReleaseExpiredHolds:
    def test_releases_expired_held_reservations(self, app, db):
        """Expired HELD reservations should be transitioned to RELEASED."""
        from src.scheduler import _release_expired_holds
        from src.models.models import Reservation, Resource, Organization, User
        from src.models.enums import ReservationStatus

        with app.app_context():
            org = Organization(name="Sched Org", slug="sched-test")
            db.session.add(org)
            db.session.flush()

            resource = Resource(
                organization_id=org.id, name="Sched Room", capacity=1
            )
            db.session.add(resource)
            db.session.flush()

            admin = User.query.first()
            reservation = Reservation(
                user_id=admin.id,
                resource_id=resource.id,
                organization_id=org.id,
                status=ReservationStatus.HELD.value,
                start_time=datetime(2099, 6, 1, 10, 0, tzinfo=timezone.utc),
                end_time=datetime(2099, 6, 1, 11, 0, tzinfo=timezone.utc),
                hold_expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),  # already expired
                version=1,
            )
            db.session.add(reservation)
            db.session.commit()
            res_id = reservation.id

            _release_expired_holds()

            updated = Reservation.query.get(res_id)
            assert updated.status == ReservationStatus.RELEASED.value
            assert updated.version == 2

    def test_does_not_release_non_expired_holds(self, app, db):
        """HELD reservations with future expiry should not be released."""
        from src.scheduler import _release_expired_holds
        from src.models.models import Reservation, Resource, Organization, User
        from src.models.enums import ReservationStatus

        with app.app_context():
            org = Organization(name="Sched Org 2", slug="sched-test-2")
            db.session.add(org)
            db.session.flush()

            resource = Resource(
                organization_id=org.id, name="Sched Room 2", capacity=1
            )
            db.session.add(resource)
            db.session.flush()

            admin = User.query.first()
            reservation = Reservation(
                user_id=admin.id,
                resource_id=resource.id,
                organization_id=org.id,
                status=ReservationStatus.HELD.value,
                start_time=datetime(2099, 6, 1, 10, 0, tzinfo=timezone.utc),
                end_time=datetime(2099, 6, 1, 11, 0, tzinfo=timezone.utc),
                hold_expires_at=datetime(2099, 6, 1, 12, 0, tzinfo=timezone.utc),  # far future
                version=1,
            )
            db.session.add(reservation)
            db.session.commit()
            res_id = reservation.id

            _release_expired_holds()

            updated = Reservation.query.get(res_id)
            assert updated.status == ReservationStatus.HELD.value
            assert updated.version == 1


class TestCleanupNonces:
    def test_removes_expired_nonces(self, app, db):
        """Expired nonces should be deleted."""
        from src.scheduler import _cleanup_nonces
        from src.models.models import NonceStore

        with app.app_context():
            expired = NonceStore(
                nonce="expired-nonce",
                expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
            active = NonceStore(
                nonce="active-nonce",
                expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            )
            db.session.add_all([expired, active])
            db.session.commit()

            _cleanup_nonces()

            assert NonceStore.query.filter_by(nonce="expired-nonce").first() is None
            assert NonceStore.query.filter_by(nonce="active-nonce").first() is not None


class TestCleanupDenylist:
    def test_removes_expired_denylist_entries(self, app, db):
        """Expired denylist entries should be deleted."""
        from src.scheduler import _cleanup_denylist
        from src.models.models import AccessTokenDenylist

        with app.app_context():
            expired = AccessTokenDenylist(
                jti="expired-jti",
                expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
            active = AccessTokenDenylist(
                jti="active-jti",
                expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            )
            db.session.add_all([expired, active])
            db.session.commit()

            _cleanup_denylist()

            assert AccessTokenDenylist.query.filter_by(jti="expired-jti").first() is None
            assert AccessTokenDenylist.query.filter_by(jti="active-jti").first() is not None


class TestCleanupIdempotency:
    def test_removes_expired_idempotency_records(self, app, db):
        """Expired idempotency records should be deleted."""
        from src.scheduler import _cleanup_idempotency
        from src.models.models import IdempotencyRecord

        with app.app_context():
            expired = IdempotencyRecord(
                user_id="user-1",
                endpoint="/reservations/hold",
                key_hash="abc123",
                response_code=201,
                response_body="{}",
                expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
            active = IdempotencyRecord(
                user_id="user-1",
                endpoint="/reservations/hold",
                key_hash="def456",
                response_code=201,
                response_body="{}",
                expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            )
            db.session.add_all([expired, active])
            db.session.commit()

            _cleanup_idempotency()

            assert IdempotencyRecord.query.filter_by(key_hash="abc123").first() is None
            assert IdempotencyRecord.query.filter_by(key_hash="def456").first() is not None


class TestEvaluateAnomalyAlerts:
    def test_no_alerts_when_below_threshold(self, app, db):
        """No alerts should be created when event counts are below threshold."""
        from src.scheduler import _evaluate_anomaly_alerts
        from src.models.models import Alert

        with app.app_context():
            _evaluate_anomaly_alerts()

            alerts = Alert.query.filter_by(alert_type="FAILED_LOGIN_SPIKE").all()
            assert len(alerts) == 0

    def test_creates_alert_on_login_spike(self, app, db):
        """A FAILED_LOGIN_SPIKE alert should be created when failures exceed 20."""
        from src.scheduler import _evaluate_anomaly_alerts
        from src.models.models import AuditEvent, Alert
        from src.models.enums import AuditEventType

        with app.app_context():
            # Insert 21 failed login events in the last hour
            for i in range(21):
                event = AuditEvent(
                    event_type=AuditEventType.USER_LOGIN_FAILED.value,
                    actor_id=f"user-{i}",
                    actor_ip="127.0.0.1",
                )
                db.session.add(event)
            db.session.commit()

            _evaluate_anomaly_alerts()

            alerts = Alert.query.filter_by(alert_type="FAILED_LOGIN_SPIKE").all()
            assert len(alerts) == 1
            assert "21" in alerts[0].title


class TestPurgeOldBackups:
    def test_purges_files_older_than_retention(self, app, db):
        """Backup files older than BACKUP_RETENTION_DAYS should be deleted."""
        from src.scheduler import _purge_old_backups
        from src.config import config

        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = config.BACKUP_DIR
            config.BACKUP_DIR = tmpdir

            try:
                # Create an "old" file
                old_file = os.path.join(tmpdir, "backup_old.db")
                with open(old_file, "w") as f:
                    f.write("old")
                # Set mtime to 30 days ago
                old_time = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
                os.utime(old_file, (old_time, old_time))

                # Create a "recent" file
                recent_file = os.path.join(tmpdir, "backup_recent.db")
                with open(recent_file, "w") as f:
                    f.write("recent")

                with app.app_context():
                    _purge_old_backups()

                assert not os.path.exists(old_file)
                assert os.path.exists(recent_file)
            finally:
                config.BACKUP_DIR = original_dir
