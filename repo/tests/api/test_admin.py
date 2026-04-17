"""API tests for admin, health, and debug endpoints."""
import uuid

import pytest


class TestHealthEndpoint:
    def test_health_endpoint(self, client, db):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "healthy"


class TestSystemStatus:
    def test_system_status_admin_only(self, client, member_user, db):
        resp = client.get("/admin/system-status", headers=member_user["headers"])
        assert resp.status_code == 403
        body = resp.get_json()
        assert "error" in body
        assert body["error"]["code"] == "FORBIDDEN"

    def test_system_status_success(self, client, admin_headers, db):
        resp = client.get("/admin/system-status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "total_users" in data
        assert "total_organizations" in data


class TestDebugEndpoints:
    def test_debug_routes_disabled(self, client, admin_headers, db):
        """Debug routes should be disabled by default (ENABLE_DEBUG_ENDPOINTS=False)."""
        resp = client.get("/admin/debug/routes", headers=admin_headers)
        assert resp.status_code == 403
        body = resp.get_json()
        assert "error" in body
        assert isinstance(body["error"]["message"], str)

    def test_config_redacted(self, client, admin_headers, db):
        """Enable debug endpoints, then verify secrets are redacted."""
        from src.config import config

        original = config.ENABLE_DEBUG_ENDPOINTS
        try:
            config.ENABLE_DEBUG_ENDPOINTS = True

            resp = client.get("/admin/debug/config-redacted", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.get_json()["data"]
            cfg = data["config"]
            assert cfg["SECRET_KEY"] == "***REDACTED***"
            assert cfg["JWT_SECRET_KEY"] == "***REDACTED***"
            assert cfg["ENCRYPTION_MASTER_KEY"] == "***REDACTED***"
        finally:
            config.ENABLE_DEBUG_ENDPOINTS = original
