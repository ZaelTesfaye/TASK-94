"""Unit tests for alert_writer utility."""

import pytest

from src.app import create_app
from src.models.base import db as _db
from src.models.enums import AlertSeverity, AlertStatus


@pytest.fixture(scope="module")
def app():
    app = create_app(testing=True)
    yield app


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


class TestCreateAlert:
    def test_creates_alert_with_correct_structure(self, app, db):
        """Alert is created with the expected fields and persisted to the DB."""
        from src.utils.alert_writer import create_alert
        from src.models.models import Alert

        with app.app_context():
            alert = create_alert(
                alert_type="TEST_ALERT",
                severity=AlertSeverity.HIGH.value,
                title="Test alert title",
                description="Detailed description",
                organization_id="org-123",
            )

            assert alert.id is not None
            assert alert.alert_type == "TEST_ALERT"
            assert alert.severity == AlertSeverity.HIGH.value
            assert alert.status == AlertStatus.OPEN.value
            assert alert.title == "Test alert title"
            assert alert.description == "Detailed description"
            assert alert.organization_id == "org-123"

            # Verify it was persisted
            fetched = Alert.query.get(alert.id)
            assert fetched is not None
            assert fetched.title == "Test alert title"

    def test_creates_alert_without_optional_fields(self, app, db):
        """Alert can be created without description or organization_id."""
        from src.utils.alert_writer import create_alert

        with app.app_context():
            alert = create_alert(
                alert_type="MINIMAL_ALERT",
                severity=AlertSeverity.LOW.value,
                title="Minimal alert",
            )

            assert alert.id is not None
            assert alert.description is None
            assert alert.organization_id is None

    def test_multiple_alerts_persisted(self, app, db):
        """Multiple alerts can be created and all are persisted."""
        from src.utils.alert_writer import create_alert
        from src.models.models import Alert

        with app.app_context():
            create_alert(
                alert_type="ALERT_A",
                severity=AlertSeverity.LOW.value,
                title="First alert",
            )
            create_alert(
                alert_type="ALERT_B",
                severity=AlertSeverity.CRITICAL.value,
                title="Second alert",
            )

            count = Alert.query.count()
            assert count == 2

    def test_duplicate_alert_types_allowed(self, app, db):
        """Writing two alerts with the same type should both persist."""
        from src.utils.alert_writer import create_alert
        from src.models.models import Alert

        with app.app_context():
            a1 = create_alert(
                alert_type="DUPLICATE_TYPE",
                severity=AlertSeverity.MEDIUM.value,
                title="First",
            )
            a2 = create_alert(
                alert_type="DUPLICATE_TYPE",
                severity=AlertSeverity.MEDIUM.value,
                title="Second",
            )

            assert a1.id != a2.id
            dupes = Alert.query.filter_by(alert_type="DUPLICATE_TYPE").all()
            assert len(dupes) == 2
