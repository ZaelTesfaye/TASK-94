"""API tests for security controls."""
import uuid

import pytest


class TestAuthentication:
    def test_unauthenticated_access_denied(self, client, db):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_invalid_token_rejected(self, client, db):
        resp = client.get("/auth/me", headers={
            "Authorization": "Bearer garbage.invalid.token",
        })
        assert resp.status_code == 401


class TestAuthorization:
    def test_member_cannot_access_admin(self, client, member_user, db):
        resp = client.get("/admin/system-status", headers=member_user["headers"])
        assert resp.status_code == 403


class TestCrossOrgIsolation:
    def test_cross_org_isolation(self, client, admin_headers, member_user, org_setup, db):
        """Content in org A should not be visible to a member of org B."""
        from src.models.models import Organization, Membership
        from src.models.enums import RoleType

        # Create org B
        org_b = Organization(name="Org B", slug=f"org-b-{uuid.uuid4().hex[:6]}", is_active=True)
        db.session.add(org_b)
        db.session.commit()

        # Register user B
        username_b = f"userb_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username_b,
            "password": "SecurePass1!",
        })
        user_b_id = reg_resp.get_json()["data"]["user"]["id"]

        # Give user B membership in org B
        membership = Membership(
            user_id=user_b_id,
            organization_id=org_b.id,
            role=RoleType.MEMBER.value,
        )
        db.session.add(membership)
        db.session.commit()

        # Re-login user B to get token with org B context
        login_resp = client.post("/auth/login", json={
            "username": username_b,
            "password": "SecurePass1!",
        })
        user_b_token = login_resp.get_json()["data"]["access_token"]
        user_b_headers = {"Authorization": f"Bearer {user_b_token}"}

        # Create content in org A with member of org A
        client.post("/content", json={
            "title": "Org A Secret Content",
            "body": "This should not be visible to org B members.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])

        # User B queries content with their org context (org B)
        resp = client.get(
            f"/content?organization_id={org_b.id}",
            headers=user_b_headers,
        )
        assert resp.status_code == 200
        items = resp.get_json()["data"]
        # None of the returned items should be from org A
        for item in items:
            assert item["organization_id"] != org_setup["id"]


class TestSecurityHeaders:
    def test_security_headers_present(self, client, db):
        resp = client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


class TestErrorEnvelope:
    def test_error_response_envelope(self, client, db):
        """A bad request should return the standard error envelope."""
        resp = client.post("/auth/login", json={})
        body = resp.get_json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "meta" in body


class TestPagination:
    def test_pagination_defaults(self, client, member_user, org_setup, db):
        """GET /content with no page params should return pagination envelope."""
        resp = client.get(
            f"/content?organization_id={org_setup['id']}",
            headers=member_user["headers"],
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "pagination" in body
        pagination = body["pagination"]
        assert "page" in pagination
        assert "per_page" in pagination
        assert "total" in pagination
