"""API tests for auth endpoints."""
import uuid

import pytest


class TestRegisterGuest:
    def test_register_guest_success(self, client, db):
        resp = client.post("/auth/register-guest", json={
            "username": f"guest_{uuid.uuid4().hex[:8]}",
            "password": "SecurePass1!",
        })
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert "user" in data
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["role"] == "guest"

    def test_register_guest_duplicate_username(self, client, db):
        username = f"dup_{uuid.uuid4().hex[:8]}"
        resp1 = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        assert resp1.status_code == 201

        resp2 = client.post("/auth/register-guest", json={
            "username": username,
            "password": "AnotherPass2!",
        })
        assert resp2.status_code == 409


class TestLogin:
    def test_login_success(self, client, db):
        username = f"login_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_wrong_password(self, client, db):
        username = f"wrongpw_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        resp = client.post("/auth/login", json={
            "username": username,
            "password": "WrongPassword!",
        })
        assert resp.status_code == 401
        body = resp.get_json()
        assert "error" in body
        assert body["error"]["code"] == "INVALID_CREDENTIALS"

    def test_login_lockout_after_failures(self, client, db):
        username = f"lockout_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        # After CAPTCHA_THRESHOLD (3) failures, captcha is required which
        # blocks further credential checks. Directly set the failure counter
        # to simulate reaching LOGIN_MAX_FAILURES (5) to trigger lockout.
        from src.models.models import LoginFailureCounter
        from datetime import datetime, timezone, timedelta
        from src.config import config

        # Record 3 failures via API
        for _ in range(3):
            client.post("/auth/login", json={
                "username": username,
                "password": "BadPassword!",
            })

        # Manually push counter to lockout threshold
        counter = LoginFailureCounter.query.filter_by(identifier=username).first()
        counter.failure_count = config.LOGIN_MAX_FAILURES
        counter.locked_until = datetime.now(timezone.utc) + timedelta(minutes=config.LOGIN_LOCKOUT_MINUTES)
        db.session.commit()

        # Next attempt should be locked
        resp = client.post("/auth/login", json={
            "username": username,
            "password": "BadPassword!",
        })
        assert resp.status_code == 423
        body = resp.get_json()
        assert "error" in body
        assert body["error"]["code"] == "ACCOUNT_LOCKED"


class TestRefreshToken:
    def test_refresh_token_success(self, client, db):
        username = f"refresh_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        refresh_token = login_resp.get_json()["data"]["refresh_token"]

        resp = client.post("/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_with_invalid_token(self, client, db):
        resp = client.post("/auth/refresh", json={
            "refresh_token": "garbage.token.value",
        })
        assert resp.status_code == 401
        body = resp.get_json()
        assert "error" in body
        assert isinstance(body["error"]["message"], str)


class TestLogout:
    def test_logout_success(self, client, db):
        username = f"logout_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        token = login_resp.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/auth/logout", headers=headers)
        assert resp.status_code == 204
        # Verify the token is now revoked
        me_resp = client.get("/auth/me", headers=headers)
        assert me_resp.status_code == 401

    def test_logout_all_revokes_tokens(self, client, db):
        username = f"logoutall_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        data = login_resp.get_json()["data"]
        token = data["access_token"]
        refresh_token = data["refresh_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/auth/logout-all", headers=headers)
        assert resp.status_code == 204

        # Try to refresh -- should fail because all refresh tokens are revoked
        resp = client.post("/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 401


class TestCaptchaChallenge:
    def test_captcha_required_after_threshold_failures(self, client, db):
        """After CAPTCHA_THRESHOLD (3) failures, login should require captcha."""
        username = f"captcha_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        # Fail 3 times to hit captcha threshold
        for _ in range(3):
            client.post("/auth/login", json={
                "username": username,
                "password": "WrongPassword!",
            })

        # Next attempt should require captcha
        resp = client.post("/auth/login", json={
            "username": username,
            "password": "WrongPassword!",
        })
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"]["code"] == "CAPTCHA_REQUIRED"
        assert "challenge_id" in data["error"]["details"]
        assert "challenge_text" in data["error"]["details"]

    def test_valid_captcha_allows_login_attempt(self, client, db):
        """After solving captcha, user should be able to attempt login."""
        username = f"captcha_solve_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        # Fail 3 times
        for _ in range(3):
            client.post("/auth/login", json={
                "username": username,
                "password": "WrongPassword!",
            })

        # Get captcha challenge
        resp = client.post("/auth/login", json={
            "username": username,
            "password": "WrongPassword!",
        })
        challenge = resp.get_json()["error"]["details"]
        challenge_id = challenge["challenge_id"]

        # Solve the captcha by looking up the expected answer in DB
        from src.models.models import LoginChallenge
        ch = LoginChallenge.query.filter_by(id=challenge_id).first()
        correct_answer = ch.expected_answer

        # Login with captcha (wrong password but captcha accepted — should get INVALID_CREDENTIALS, not CAPTCHA_REQUIRED)
        resp = client.post("/auth/login", json={
            "username": username,
            "password": "WrongPassword!",
            "captcha_id": challenge_id,
            "captcha_answer": correct_answer,
        })
        # Should NOT be CAPTCHA_REQUIRED anymore — either INVALID_CREDENTIALS or success
        assert resp.get_json()["error"]["code"] != "CAPTCHA_REQUIRED"


class TestMe:
    def test_get_me(self, client, db):
        username = f"me_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        token = reg_resp.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.get("/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["username"] == username


class TestDevice:
    def _get_auth(self, client, db):
        username = f"device_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        token = reg_resp.get_json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_device_bind(self, client, db):
        headers = self._get_auth(client, db)
        resp = client.post("/auth/device/bind", json={
            "fingerprint": "abc123-device-fp",
            "device_name": "Test Device",
        }, headers=headers)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert "id" in data
        assert data["device_name"] == "Test Device"

    def test_device_unbind(self, client, db):
        headers = self._get_auth(client, db)
        bind_resp = client.post("/auth/device/bind", json={
            "fingerprint": "abc456-device-fp",
            "device_name": "Unbind Device",
        }, headers=headers)
        device_id = bind_resp.get_json()["data"]["id"]

        resp = client.post("/auth/device/unbind", json={
            "device_id": device_id,
        }, headers=headers)
        assert resp.status_code == 204
        # Verify the device was actually unbound by checking it's gone
        from src.models.models import Device
        device = Device.query.get(device_id)
        assert device is None or device.status != "ACTIVE"
