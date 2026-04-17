"""Unit tests for booking.py internal helper functions."""

import hashlib
from datetime import datetime, timezone, timedelta

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


class TestHashIdempotencyKey:
    def test_produces_sha256(self):
        from src.api.booking import _hash_idempotency_key

        key = "test-key-123"
        result = _hash_idempotency_key(key)
        expected = hashlib.sha256(key.encode("utf-8")).hexdigest()
        assert result == expected

    def test_deterministic(self):
        from src.api.booking import _hash_idempotency_key

        assert _hash_idempotency_key("abc") == _hash_idempotency_key("abc")

    def test_different_keys_different_hashes(self):
        from src.api.booking import _hash_idempotency_key

        assert _hash_idempotency_key("key-a") != _hash_idempotency_key("key-b")


class TestCheckOverlap:
    def test_no_reservations_no_conflict(self, app, db):
        """With no existing reservations, there should be no overlap."""
        from src.api.booking import _check_overlap
        from src.models.models import Resource, Organization

        with app.app_context():
            org = Organization(name="Test Org", slug="overlap-test")
            db.session.add(org)
            db.session.flush()

            resource = Resource(
                organization_id=org.id, name="Room A", capacity=1
            )
            db.session.add(resource)
            db.session.commit()

            start = datetime(2099, 6, 1, 10, 0, tzinfo=timezone.utc)
            end = datetime(2099, 6, 1, 11, 0, tzinfo=timezone.utc)

            has_conflict, count = _check_overlap(resource.id, start, end)
            assert has_conflict is False
            assert count == 0

    def test_overlapping_reservation_detected(self, app, db):
        """An existing HELD reservation within the window should be detected."""
        from src.api.booking import _check_overlap
        from src.models.models import Resource, Organization, Reservation
        from src.models.enums import ReservationStatus

        with app.app_context():
            org = Organization(name="Test Org 2", slug="overlap-test-2")
            db.session.add(org)
            db.session.flush()

            resource = Resource(
                organization_id=org.id, name="Room B", capacity=1
            )
            db.session.add(resource)
            db.session.flush()

            admin = _db.session.query(
                __import__("src.models.models", fromlist=["User"]).User
            ).first()

            existing = Reservation(
                user_id=admin.id,
                resource_id=resource.id,
                organization_id=org.id,
                status=ReservationStatus.HELD.value,
                start_time=datetime(2099, 6, 1, 10, 0, tzinfo=timezone.utc),
                end_time=datetime(2099, 6, 1, 11, 0, tzinfo=timezone.utc),
                hold_expires_at=datetime(2099, 6, 1, 12, 0, tzinfo=timezone.utc),
                version=1,
            )
            db.session.add(existing)
            db.session.commit()

            start = datetime(2099, 6, 1, 10, 30, tzinfo=timezone.utc)
            end = datetime(2099, 6, 1, 11, 30, tzinfo=timezone.utc)

            has_conflict, count = _check_overlap(resource.id, start, end)
            assert has_conflict is True
            assert count >= 1

    def test_cancelled_reservation_not_counted(self, app, db):
        """A CANCELLED reservation should not count as an overlap."""
        from src.api.booking import _check_overlap
        from src.models.models import Resource, Organization, Reservation, User
        from src.models.enums import ReservationStatus

        with app.app_context():
            org = Organization(name="Test Org 3", slug="overlap-test-3")
            db.session.add(org)
            db.session.flush()

            resource = Resource(
                organization_id=org.id, name="Room C", capacity=1
            )
            db.session.add(resource)
            db.session.flush()

            admin = User.query.first()

            cancelled = Reservation(
                user_id=admin.id,
                resource_id=resource.id,
                organization_id=org.id,
                status=ReservationStatus.CANCELLED.value,
                start_time=datetime(2099, 6, 1, 10, 0, tzinfo=timezone.utc),
                end_time=datetime(2099, 6, 1, 11, 0, tzinfo=timezone.utc),
                version=1,
            )
            db.session.add(cancelled)
            db.session.commit()

            start = datetime(2099, 6, 1, 10, 0, tzinfo=timezone.utc)
            end = datetime(2099, 6, 1, 11, 0, tzinfo=timezone.utc)

            has_conflict, count = _check_overlap(resource.id, start, end)
            assert has_conflict is False
            assert count == 0


class TestGetSlotQuota:
    def test_falls_back_to_resource_capacity(self, app, db):
        """Without a matching slot template, should return resource capacity."""
        from src.api.booking import _get_slot_quota
        from src.models.models import Resource, Organization

        with app.app_context():
            org = Organization(name="Quota Org", slug="quota-test")
            db.session.add(org)
            db.session.flush()

            resource = Resource(
                organization_id=org.id, name="Quota Room", capacity=5
            )
            db.session.add(resource)
            db.session.commit()

            start = datetime(2099, 6, 1, 10, 0, tzinfo=timezone.utc)
            end = datetime(2099, 6, 1, 11, 0, tzinfo=timezone.utc)

            quota = _get_slot_quota(resource.id, start, end)
            assert quota == 5

    def test_uses_template_quota_when_matched(self, app, db):
        """A matching slot template should provide the quota."""
        from src.api.booking import _get_slot_quota
        from src.models.models import Resource, Organization, SlotTemplate
        from datetime import time as dt_time

        with app.app_context():
            org = Organization(name="Template Org", slug="tmpl-test")
            db.session.add(org)
            db.session.flush()

            resource = Resource(
                organization_id=org.id, name="Template Room", capacity=1
            )
            db.session.add(resource)
            db.session.flush()

            start = datetime(2099, 6, 1, 10, 0, tzinfo=timezone.utc)
            end = datetime(2099, 6, 1, 11, 0, tzinfo=timezone.utc)

            # Compute day_of_week from the actual start date so the template matches
            template = SlotTemplate(
                resource_id=resource.id,
                day_of_week=start.weekday(),
                start_time=dt_time(9, 0),
                end_time=dt_time(17, 0),
                quota=3,
                is_active=True,
            )
            db.session.add(template)
            db.session.commit()

            quota = _get_slot_quota(resource.id, start, end)
            assert quota == 3
