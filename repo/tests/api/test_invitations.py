"""API tests for invitation lifecycle endpoints."""
import uuid
from datetime import datetime, timezone

import pytest


class TestInvitations:
    def _create_invitation(self, client, admin_headers, org_id):
        """Helper to create a pending invitation and return the response data."""
        resp = client.post("/invitations", json={
            "organization_id": org_id,
            "target_role": "member",
        }, headers=admin_headers)
        assert resp.status_code == 201
        return resp.get_json()["data"]

    def _register_guest(self, client):
        """Register a fresh guest and return (user_id, headers, refresh_token)."""
        username = f"inv_guest_{uuid.uuid4().hex[:8]}"
        resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        data = resp.get_json()["data"]
        return (
            data["user"]["id"],
            {"Authorization": f"Bearer {data['access_token']}"},
            data["refresh_token"],
        )

    def test_create_invitation(self, client, admin_headers, org_setup, db):
        inv = self._create_invitation(client, admin_headers, org_setup["id"])
        assert "code" in inv
        assert inv["status"] == "PENDING"
        assert inv["organization_id"] == org_setup["id"]

    def test_redeem_invitation(self, client, admin_headers, org_setup, db):
        inv = self._create_invitation(client, admin_headers, org_setup["id"])
        code = inv["code"]

        user_id, guest_headers, _ = self._register_guest(client)

        resp = client.post("/invitations/redeem", json={
            "code": code,
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["organization_id"] == org_setup["id"]
        assert data["role"] == "member"

    def test_redeem_expired_invitation(self, client, admin_headers, org_setup, db):
        inv = self._create_invitation(client, admin_headers, org_setup["id"])
        code = inv["code"]

        # Manually expire the invitation
        from src.models.models import InvitationCode
        invitation = InvitationCode.query.filter_by(code=code).first()
        invitation.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db.session.commit()

        user_id, guest_headers, _ = self._register_guest(client)

        resp = client.post("/invitations/redeem", json={
            "code": code,
        }, headers=guest_headers)
        assert resp.status_code == 410

    def test_redeem_already_redeemed(self, client, admin_headers, org_setup, db):
        inv = self._create_invitation(client, admin_headers, org_setup["id"])
        code = inv["code"]

        # First redeem
        _, guest1_headers, _ = self._register_guest(client)
        resp = client.post("/invitations/redeem", json={
            "code": code,
        }, headers=guest1_headers)
        assert resp.status_code == 200

        # Second redeem with different user
        _, guest2_headers, _ = self._register_guest(client)
        resp = client.post("/invitations/redeem", json={
            "code": code,
        }, headers=guest2_headers)
        # Should be 410 (INVALID_STATE since already redeemed)
        assert resp.status_code == 410

    def test_revoke_invitation(self, client, admin_headers, org_setup, db):
        inv = self._create_invitation(client, admin_headers, org_setup["id"])

        resp = client.post("/invitations/revoke", json={
            "invitation_id": inv["id"],
        }, headers=admin_headers)
        assert resp.status_code == 200
