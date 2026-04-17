"""API tests for permissions and membership endpoints."""
import uuid

import pytest


class TestPermissions:
    def test_create_permission_as_admin(self, client, admin_headers, db):
        code = f"test.perm.{uuid.uuid4().hex[:6]}"
        resp = client.post("/permissions", json={
            "code": code,
            "description": "A test permission",
        }, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["code"] == code

    def test_create_permission_as_member_fails(self, client, member_user, db):
        code = f"test.perm.{uuid.uuid4().hex[:6]}"
        resp = client.post("/permissions", json={
            "code": code,
            "description": "Should fail",
        }, headers=member_user["headers"])
        assert resp.status_code == 403
        body = resp.get_json()
        assert "error" in body
        assert body["error"]["code"] == "FORBIDDEN"

    def test_list_permissions(self, client, admin_headers, db):
        # Create one permission first
        code = f"test.list.{uuid.uuid4().hex[:6]}"
        client.post("/permissions", json={
            "code": code,
        }, headers=admin_headers)

        resp = client.get("/permissions", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" in body

    def test_assign_permission(self, client, admin_headers, member_user, org_setup, db):
        # Create a permission
        code = f"test.assign.{uuid.uuid4().hex[:6]}"
        client.post("/permissions", json={
            "code": code,
        }, headers=admin_headers)

        # Assign to member
        resp = client.post("/permissions/assign", json={
            "user_id": member_user["user_id"],
            "permission_code": code,
            "organization_id": org_setup["id"],
        }, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["permission_code"] == code
        assert data["user_id"] == member_user["user_id"]

    def test_revoke_permission(self, client, admin_headers, member_user, org_setup, db):
        # Create and assign
        code = f"test.revoke.{uuid.uuid4().hex[:6]}"
        client.post("/permissions", json={
            "code": code,
        }, headers=admin_headers)
        client.post("/permissions/assign", json={
            "user_id": member_user["user_id"],
            "permission_code": code,
            "organization_id": org_setup["id"],
        }, headers=admin_headers)

        # Revoke
        resp = client.post("/permissions/revoke", json={
            "user_id": member_user["user_id"],
            "permission_code": code,
            "organization_id": org_setup["id"],
        }, headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" in body
        assert isinstance(body["data"]["message"], str)


class TestMemberships:
    def test_list_memberships(self, client, admin_headers, db):
        resp = client.get("/permissions/memberships", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" in body
