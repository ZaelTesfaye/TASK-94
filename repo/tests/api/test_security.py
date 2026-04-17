"""API tests for security controls."""
import uuid

import pytest


class TestAuthentication:
    def test_unauthenticated_access_denied(self, client, db):
        resp = client.get("/auth/me")
        assert resp.status_code == 401
        body = resp.get_json()
        assert "error" in body
        assert body["error"]["code"] == "UNAUTHORIZED"

    def test_invalid_token_rejected(self, client, db):
        resp = client.get("/auth/me", headers={
            "Authorization": "Bearer garbage.invalid.token",
        })
        assert resp.status_code == 401
        body = resp.get_json()
        assert "error" in body
        assert body["error"]["code"] == "INVALID_TOKEN"


class TestAuthorization:
    def test_member_cannot_access_admin(self, client, member_user, db):
        resp = client.get("/admin/system-status", headers=member_user["headers"])
        assert resp.status_code == 403
        body = resp.get_json()
        assert "error" in body
        assert body["error"]["code"] == "FORBIDDEN"


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


class TestCrossOrgContentCreation:
    def test_user_cannot_create_content_in_foreign_org(self, client, admin_headers, member_user, org_setup, db):
        """A member should not be able to create content in an org they don't belong to."""
        from src.models.models import Organization

        # Create a second org that member_user does NOT belong to
        org_b = Organization(name="Foreign Org", slug=f"foreign-{uuid.uuid4().hex[:6]}", is_active=True)
        db.session.add(org_b)
        db.session.commit()

        resp = client.post("/content", json={
            "title": "Should Be Blocked",
            "body": "Attempting cross-org content creation.",
            "organization_id": org_b.id,
        }, headers=member_user["headers"])
        assert resp.status_code == 403
        body = resp.get_json()
        assert "error" in body
        assert isinstance(body["error"]["message"], str)

    def test_member_can_create_content_in_own_org(self, client, member_user, org_setup, db):
        resp = client.post("/content", json={
            "title": "Own Org Content",
            "body": "This should succeed.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        assert resp.status_code == 201


class TestCrossOrgInvitations:
    def test_org_admin_cannot_create_invitation_for_other_org(self, client, db, org_setup):
        """An org_admin should not be able to create invitations for a foreign org."""
        from src.models.models import Organization, User, Membership
        from src.models.enums import RoleType

        # Create org B
        org_b = Organization(name="Other Org", slug=f"other-{uuid.uuid4().hex[:6]}", is_active=True)
        db.session.add(org_b)
        db.session.commit()

        # Create an org_admin user in org A
        reg_resp = client.post("/auth/register-guest", json={
            "username": f"orgadmin_{uuid.uuid4().hex[:8]}",
            "password": "SecurePass1!",
        })
        user_id = reg_resp.get_json()["data"]["user"]["id"]
        user = User.query.get(user_id)
        user.role = RoleType.ORG_ADMIN.value
        m = Membership(user_id=user_id, organization_id=org_setup["id"], role=RoleType.ORG_ADMIN.value, is_active=True)
        db.session.add(m)
        db.session.commit()

        # Login to get token
        login_resp = client.post("/auth/login", json={
            "username": user.username,
            "password": "SecurePass1!",
        })
        token = login_resp.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Try to create invitation for org B (should fail)
        resp = client.post("/invitations", json={
            "organization_id": org_b.id,
            "target_role": "member",
        }, headers=headers)
        assert resp.status_code == 403
        body = resp.get_json()
        assert "error" in body
        assert isinstance(body["error"]["message"], str)


class TestCrossOrgPermissions:
    def test_org_admin_cannot_assign_permissions_in_other_org(self, client, db, org_setup):
        """An org_admin should not assign permissions in an org they don't belong to."""
        from src.models.models import Organization, User, Membership, Permission
        from src.models.enums import RoleType

        # Create org B
        org_b = Organization(name="Perm Other Org", slug=f"perm-other-{uuid.uuid4().hex[:6]}", is_active=True)
        db.session.add(org_b)
        db.session.commit()

        # Create org_admin in org A
        reg_resp = client.post("/auth/register-guest", json={
            "username": f"permadmin_{uuid.uuid4().hex[:8]}",
            "password": "SecurePass1!",
        })
        user_id = reg_resp.get_json()["data"]["user"]["id"]
        user = User.query.get(user_id)
        user.role = RoleType.ORG_ADMIN.value
        m = Membership(user_id=user_id, organization_id=org_setup["id"], role=RoleType.ORG_ADMIN.value, is_active=True)
        db.session.add(m)

        # Create a permission
        perm = Permission.query.filter_by(code="test:perm").first()
        if not perm:
            perm = Permission(code="test:perm", description="Test permission")
            db.session.add(perm)
        db.session.commit()

        login_resp = client.post("/auth/login", json={
            "username": user.username,
            "password": "SecurePass1!",
        })
        token = login_resp.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Try to assign permission in org B (should fail)
        resp = client.post("/permissions/assign", json={
            "user_id": user_id,
            "permission_code": "test:perm",
            "organization_id": org_b.id,
        }, headers=headers)
        assert resp.status_code == 403
        body = resp.get_json()
        assert "error" in body
        assert isinstance(body["error"]["message"], str)


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
