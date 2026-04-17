"""API tests for audit events and alerts endpoints."""
import uuid

import pytest


class TestAuditEvents:
    def test_audit_events_recorded(self, client, db):
        """Performing a login should generate an audit event."""
        from src.models.models import AuditEvent

        # The admin bootstrap already creates the admin user.
        # Login generates a USER_LOGIN audit event.
        client.post("/auth/login", json={
            "username": "admin",
            "password": "admin",
        })

        events = AuditEvent.query.filter_by(event_type="USER_LOGIN").all()
        assert len(events) >= 1

    def test_list_audit_events(self, client, admin_headers, db):
        # Trigger some activity first (login already generates events)
        client.get("/auth/me", headers=admin_headers)

        resp = client.get("/audit-events", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" in body
        assert "pagination" in body
        assert "page" in body["pagination"]
        assert "total" in body["pagination"]
        assert "per_page" in body["pagination"]
        # At least the USER_LOGIN event from admin_headers fixture
        assert len(body["data"]) >= 1
        # Validate field structure of the first event
        event = body["data"][0]
        assert "id" in event
        assert "event_type" in event
        assert "actor_id" in event
        assert "created_at" in event
        assert isinstance(event["event_type"], str)
        assert isinstance(event["created_at"], str)
        # Verify we can find the USER_LOGIN event
        event_types = [e["event_type"] for e in body["data"]]
        assert "USER_LOGIN" in event_types


class TestAlerts:
    def test_list_alerts(self, client, admin_headers, db):
        resp = client.get("/alerts", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" in body

    def test_alert_lifecycle(self, client, admin_headers, db):
        from src.models.models import Alert
        from src.models.enums import AlertSeverity, AlertStatus

        # Create an alert manually
        alert = Alert(
            alert_type="test_alert",
            severity=AlertSeverity.MEDIUM.value,
            status=AlertStatus.OPEN.value,
            title="Test Alert",
            description="Alert created for lifecycle test.",
        )
        db.session.add(alert)
        db.session.commit()
        alert_id = alert.id

        # Acknowledge
        resp = client.post(f"/alerts/{alert_id}/ack", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "ACKNOWLEDGED"

        # Resolve
        resp = client.post(f"/alerts/{alert_id}/resolve", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "RESOLVED"
