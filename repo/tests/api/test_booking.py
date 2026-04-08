"""API tests for the booking engine endpoints."""
import uuid
from datetime import datetime, timezone, timedelta

import pytest


def _setup_booking(client, admin_headers, org_id, db):
    """Create resource and slot template, return resource_id."""
    resp = client.post("/resources", json={
        "name": "Test Room",
        "organization_id": org_id,
        "capacity": 1,
    }, headers=admin_headers)
    assert resp.status_code == 201
    resource_id = resp.get_json()["data"]["id"]

    today = datetime.now(timezone.utc)
    resp = client.post("/slot-templates", json={
        "resource_id": resource_id,
        "day_of_week": today.weekday(),
        "start_time": "09:00",
        "end_time": "17:00",
        "quota": 1,
    }, headers=admin_headers)
    assert resp.status_code == 201

    return resource_id


def _future_slot():
    """Return (start_time, end_time) as ISO strings for a slot today starting
    at the next whole hour (at least 1 hour from now)."""
    now = datetime.now(timezone.utc)
    start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
    # Clamp within the 09:00-17:00 window
    if start.hour < 9:
        start = start.replace(hour=9)
    if start.hour >= 16:
        # Push to tomorrow if too late in the day; tests should still work
        start = start + timedelta(days=1)
        start = start.replace(hour=9, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    return start.isoformat(), end.isoformat()


class TestResources:
    def test_create_resource(self, client, admin_headers, org_setup, db):
        resp = client.post("/resources", json={
            "name": "Conference Room A",
            "organization_id": org_setup["id"],
            "capacity": 10,
        }, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["name"] == "Conference Room A"
        assert data["capacity"] == 10

    def test_list_resources(self, client, admin_headers, org_setup, db):
        client.post("/resources", json={
            "name": "Room B",
            "organization_id": org_setup["id"],
            "capacity": 5,
        }, headers=admin_headers)

        resp = client.get("/resources", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["data"]) >= 1


class TestSlotTemplates:
    def test_create_slot_template(self, client, admin_headers, org_setup, db):
        # Create resource first
        res_resp = client.post("/resources", json={
            "name": "Slot Room",
            "organization_id": org_setup["id"],
            "capacity": 1,
        }, headers=admin_headers)
        resource_id = res_resp.get_json()["data"]["id"]

        resp = client.post("/slot-templates", json={
            "resource_id": resource_id,
            "day_of_week": 0,
            "start_time": "09:00",
            "end_time": "17:00",
            "quota": 2,
        }, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["quota"] == 2


class TestAvailability:
    def test_get_availability(self, client, admin_headers, org_setup, db):
        resource_id = _setup_booking(client, admin_headers, org_setup["id"], db)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        resp = client.get(
            f"/availability?resource_id={resource_id}&date={today_str}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "slots" in data


class TestReservations:
    def test_hold_reservation(self, client, admin_headers, member_user, org_setup, db):
        resource_id = _setup_booking(client, admin_headers, org_setup["id"], db)
        start, end = _future_slot()

        resp = client.post("/reservations/hold", json={
            "resource_id": resource_id,
            "start_time": start,
            "end_time": end,
            "organization_id": org_setup["id"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["status"] == "HELD"

    def test_confirm_reservation(self, client, admin_headers, member_user, org_setup, db):
        resource_id = _setup_booking(client, admin_headers, org_setup["id"], db)
        start, end = _future_slot()

        hold_resp = client.post("/reservations/hold", json={
            "resource_id": resource_id,
            "start_time": start,
            "end_time": end,
            "organization_id": org_setup["id"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        reservation_id = hold_resp.get_json()["data"]["id"]
        version = hold_resp.get_json()["data"]["version"]

        resp = client.post(f"/reservations/{reservation_id}/confirm", json={
            "version": version,
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "CONFIRMED"

    def test_cancel_held_reservation(self, client, admin_headers, member_user, org_setup, db):
        resource_id = _setup_booking(client, admin_headers, org_setup["id"], db)
        start, end = _future_slot()

        hold_resp = client.post("/reservations/hold", json={
            "resource_id": resource_id,
            "start_time": start,
            "end_time": end,
            "organization_id": org_setup["id"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        res_data = hold_resp.get_json()["data"]

        resp = client.post(f"/reservations/{res_data['id']}/cancel", json={
            "version": res_data["version"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "CANCELLED"

    def test_cancel_confirmed_reservation(self, client, admin_headers, member_user, org_setup, db):
        resource_id = _setup_booking(client, admin_headers, org_setup["id"], db)
        start, end = _future_slot()

        # Hold
        hold_resp = client.post("/reservations/hold", json={
            "resource_id": resource_id,
            "start_time": start,
            "end_time": end,
            "organization_id": org_setup["id"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        res_data = hold_resp.get_json()["data"]

        # Confirm
        confirm_resp = client.post(f"/reservations/{res_data['id']}/confirm", json={
            "version": res_data["version"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        confirmed = confirm_resp.get_json()["data"]

        # Cancel
        resp = client.post(f"/reservations/{confirmed['id']}/cancel", json={
            "version": confirmed["version"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "CANCELLED"

    def test_reschedule_reservation(self, client, admin_headers, member_user, org_setup, db):
        resource_id = _setup_booking(client, admin_headers, org_setup["id"], db)
        start, end = _future_slot()

        # Hold
        hold_resp = client.post("/reservations/hold", json={
            "resource_id": resource_id,
            "start_time": start,
            "end_time": end,
            "organization_id": org_setup["id"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        res_data = hold_resp.get_json()["data"]

        # Confirm
        confirm_resp = client.post(f"/reservations/{res_data['id']}/confirm", json={
            "version": res_data["version"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        confirmed = confirm_resp.get_json()["data"]

        # Reschedule: shift 1 day forward, same duration
        old_start = datetime.fromisoformat(confirmed["start_time"])
        old_end = datetime.fromisoformat(confirmed["end_time"])
        new_start = old_start + timedelta(days=1)
        new_end = old_end + timedelta(days=1)

        resp = client.post(f"/reservations/{confirmed['id']}/reschedule", json={
            "new_start_time": new_start.isoformat(),
            "new_end_time": new_end.isoformat(),
            "version": confirmed["version"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "new_reservation" in data
        assert data["new_reservation"]["status"] == "CONFIRMED"

    def test_hold_overlap_rejected(self, client, admin_headers, member_user, org_setup, db):
        resource_id = _setup_booking(client, admin_headers, org_setup["id"], db)
        start, end = _future_slot()

        # First hold succeeds
        resp1 = client.post("/reservations/hold", json={
            "resource_id": resource_id,
            "start_time": start,
            "end_time": end,
            "organization_id": org_setup["id"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        assert resp1.status_code == 201

        # Second hold on same slot should fail (quota=1)
        resp2 = client.post("/reservations/hold", json={
            "resource_id": resource_id,
            "start_time": start,
            "end_time": end,
            "organization_id": org_setup["id"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        assert resp2.status_code == 409
        assert resp2.get_json()["error"]["code"] == "SLOT_UNAVAILABLE"


class TestIdempotency:
    def test_idempotency_replay(self, client, admin_headers, member_user, org_setup, db):
        resource_id = _setup_booking(client, admin_headers, org_setup["id"], db)
        start, end = _future_slot()
        idem_key = str(uuid.uuid4())

        # First request
        resp1 = client.post("/reservations/hold", json={
            "resource_id": resource_id,
            "start_time": start,
            "end_time": end,
            "organization_id": org_setup["id"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": idem_key,
        })
        assert resp1.status_code == 201

        # Replay with same key
        resp2 = client.post("/reservations/hold", json={
            "resource_id": resource_id,
            "start_time": start,
            "end_time": end,
            "organization_id": org_setup["id"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": idem_key,
        })
        # Should return same response with replay header
        assert resp2.status_code == 201
        assert resp2.headers.get("X-Idempotent-Replay") == "true"


class TestVersionConflict:
    def test_version_mismatch(self, client, admin_headers, member_user, org_setup, db):
        resource_id = _setup_booking(client, admin_headers, org_setup["id"], db)
        start, end = _future_slot()

        hold_resp = client.post("/reservations/hold", json={
            "resource_id": resource_id,
            "start_time": start,
            "end_time": end,
            "organization_id": org_setup["id"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        res_data = hold_resp.get_json()["data"]

        # Confirm with wrong version
        resp = client.post(f"/reservations/{res_data['id']}/confirm", json={
            "version": 999,
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "VERSION_CONFLICT"


class TestHoldExpiry:
    def test_hold_expired_returns_410(self, client, admin_headers, member_user, org_setup, db):
        resource_id = _setup_booking(client, admin_headers, org_setup["id"], db)
        start, end = _future_slot()

        hold_resp = client.post("/reservations/hold", json={
            "resource_id": resource_id,
            "start_time": start,
            "end_time": end,
            "organization_id": org_setup["id"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        res_data = hold_resp.get_json()["data"]

        # Manually expire the hold
        from src.models.models import Reservation
        reservation = Reservation.query.get(res_data["id"])
        reservation.hold_expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db.session.commit()

        # Try to confirm the expired hold
        resp = client.post(f"/reservations/{res_data['id']}/confirm", json={
            "version": res_data["version"],
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": str(uuid.uuid4()),
        })
        assert resp.status_code == 410
